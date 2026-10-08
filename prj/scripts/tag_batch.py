from __future__ import annotations

import json
import logging
import multiprocessing as mp
import time
from pathlib import Path

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from genfactory.config.enums import Environment

from core.config import ANNOTATED_WITH_DESC_DIR, ENV_FILE, TAGGED_DIR
from core.models.registry.hierarchy_data import build_hierarchy
from core.orchestrators.tag_document import MODEL, tag_document_units
from core.services.llm_client import init_genfactory
from core.utils.logging import setup_logging

logger = logging.getLogger(__name__)


_CONFIG = get_obj_from_config_path("tagging.yaml")["runner"]

INPUT_DIR = ANNOTATED_WITH_DESC_DIR
OUTPUT_DIR = TAGGED_DIR

DEFAULT_USE_CASES: tuple[str, ...] = ("AUDIT-SVIL",)
PARALLEL_USE_CASES: tuple[str, ...] = ("AUDIT-SVIL", "AUDIT")
_ENV_BY_USE_CASE: dict[str, Environment] = {
    "AUDIT-SVIL": Environment.SVIL,
    "AUDIT": Environment.TEST,
}
SLEEP_BETWEEN_DOCS_S: int = _CONFIG["sleep_between_docs_s"]


def _env_for(use_case_id: str) -> Environment:
    """Env genfactory associato al use_case (default 'TEST')."""
    return _ENV_BY_USE_CASE.get(use_case_id, Environment.TEST)


# Sentinel per chiudere ordinatamente i worker.
_STOP_SENTINEL = "__STOP__"


def run(
    input_dir: Path = INPUT_DIR,
    output_dir: Path = OUTPUT_DIR,
    model: str = MODEL,
    use_cases: tuple[str, ...] = DEFAULT_USE_CASES,
    single_file: str | None = None,
    force: bool = False,
    gt_file: Path | None = None,
) -> None:
    """Batch entry-point unificato.

    `use_cases` controlla il livello di parallelismo a livello documento:
    un solo `use_case_id` → loop in-process; più `use_case_id` → un processo
    worker per ciascuno, distribuzione round-robin tramite queue condivisa.
    `gt_file` (opz.): tagga solo i documenti presenti nella ground truth.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    allowed_stems = _gt_stems(gt_file) if gt_file else None
    doc_paths = _resolve_doc_paths(input_dir, single_file, output_dir, force, allowed_stems)
    if not doc_paths:
        return

    logger.info("Documenti da processare: %d", len(doc_paths))

    if len(use_cases) == 1:
        _run_serial(doc_paths, output_dir, model, use_cases[0])
    else:
        _run_parallel(doc_paths, output_dir, model, use_cases)


# Path helpers -------------------------------------------------------------


def _gt_stems(gt_file: Path) -> set[str]:
    """Stem dei documenti presenti nella ground truth (per limitare il tagging a quelli)."""
    data = json.loads(gt_file.read_text(encoding="utf-8"))
    return {Path(entry["filename"]).stem for entry in data}


def _resolve_doc_paths(
    input_dir: Path,
    single_file: str | None,
    output_dir: Path,
    force: bool,
    allowed_stems: set[str] | None = None,
) -> list[Path]:
    if single_file:
        doc_paths = [input_dir / single_file]
        if not doc_paths[0].exists():
            doc_paths = [input_dir / f"{Path(single_file).stem}.md"]
    else:
        doc_paths = sorted(input_dir.glob("*.md"))
        if allowed_stems is not None:
            doc_paths = [p for p in doc_paths if p.stem in allowed_stems]

    if not doc_paths:
        logger.error("Nessun documento trovato in %s", input_dir)
        return []

    if not force:
        doc_paths = [p for p in doc_paths if not (output_dir / f"{p.stem}.json").exists()]
    return doc_paths


# Serial path --------------------------------------------------------------


def _run_serial(
    doc_paths: list[Path],
    output_dir: Path,
    model: str,
    use_case_id: str,
) -> None:
    logger.info("Caricamento risorse...")
    hierarchy = build_hierarchy()

    logger.info("Inizializzazione Layer (use_case=%s)...", use_case_id)
    layer = init_genfactory(env_file=str(ENV_FILE), use_case_id=use_case_id, env=_env_for(use_case_id))

    t_global = time.time()
    for i, doc_path in enumerate(doc_paths):
        output_path = output_dir / f"{doc_path.stem}.json"
        try:
            result = tag_document_units(layer, doc_path, hierarchy, model)
            output_path.write_text(
                result.model_dump_json(by_alias=True, indent=2),
                encoding="utf-8",
            )
            logger.info("  Salvato: %s", output_path.name)
        except Exception:
            logger.exception(
                "[%s] ERRORE - output non salvato, documento riprocessabile al prossimo lancio",
                doc_path.stem,
            )
        if i < len(doc_paths) - 1:
            logger.info("  Pausa %ds tra documenti...", SLEEP_BETWEEN_DOCS_S)
            time.sleep(SLEEP_BETWEEN_DOCS_S)

    logger.info("\nCompletato in %.1fs", time.time() - t_global)


# Parallel path ------------------------------------------------------------


def _run_parallel(
    doc_paths: list[Path],
    output_dir: Path,
    model: str,
    use_cases: tuple[str, ...],
) -> None:
    n_workers = len(use_cases)
    logger.info("Avvio %d worker process (use_case=%s)...", n_workers, ", ".join(use_cases))

    # `spawn` garantisce import fresh dei moduli in ogni figlio e quindi una
    # `GenfactoryConfig` non condivisa con gli altri worker.
    ctx = mp.get_context("spawn")
    doc_queue: mp.Queue[str] = ctx.Queue()
    result_queue: mp.Queue[tuple[str, str | None]] = ctx.Queue()

    for p in doc_paths:
        doc_queue.put(str(p))
    for _ in range(n_workers):
        doc_queue.put(_STOP_SENTINEL)

    procs: list[mp.process.BaseProcess] = []
    for use_case_id in use_cases:
        proc: mp.process.BaseProcess = ctx.Process(
            target=_worker_main,
            args=(
                use_case_id,
                str(ENV_FILE),
                str(output_dir),
                model,
                doc_queue,
                result_queue,
            ),
            name=f"tagger-{use_case_id}",
        )
        proc.start()
        procs.append(proc)

    t_global = time.time()
    n_ok = 0
    n_err = 0
    for _ in range(len(doc_paths)):
        doc_path_str, err = result_queue.get()
        if err is None:
            n_ok += 1
        else:
            n_err += 1
            logger.warning("Documento fallito: %s (%s)", Path(doc_path_str).stem, err)

    for proc in procs:
        proc.join(timeout=30)
        if proc.is_alive():
            logger.warning("Worker %s non terminato entro il timeout, kill.", proc.name)
            proc.terminate()
            proc.join()

    logger.info(
        "\nCompletato in %.1fs (%d ok, %d errori su %d documenti, %d worker)",
        time.time() - t_global,
        n_ok,
        n_err,
        len(doc_paths),
        n_workers,
    )


def _worker_main(
    use_case_id: str,
    env_file: str,
    output_dir_str: str,
    model: str,
    doc_queue: mp.Queue[str],
    result_queue: mp.Queue[tuple[str, str | None]],
) -> None:
    """Entry-point del processo worker.

    Reinizializza logging, ricarica le risorse (sotto `spawn` ogni figlio
    reimporta i moduli da zero) e cicla sulla `doc_queue` finché non riceve
    il sentinel di stop.
    """
    worker_logger = setup_logging(f"pipeline.runner.{use_case_id}")
    output_dir = Path(output_dir_str)

    worker_logger.info("[%s] Caricamento risorse...", use_case_id)
    hierarchy = build_hierarchy()

    worker_logger.info("[%s] Inizializzazione Layer...", use_case_id)
    layer = init_genfactory(env_file=env_file, use_case_id=use_case_id, env=_env_for(use_case_id))
    worker_logger.info("[%s] Pronto.", use_case_id)

    while True:
        doc_path_str = doc_queue.get()
        if doc_path_str == _STOP_SENTINEL:
            break

        doc_path = Path(doc_path_str)
        output_path = output_dir / f"{doc_path.stem}.json"
        try:
            result = tag_document_units(layer, doc_path, hierarchy, model)
            output_path.write_text(
                result.model_dump_json(by_alias=True, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            worker_logger.exception(
                "[%s][%s] ERRORE - output non salvato, documento riprocessabile al prossimo lancio",
                use_case_id,
                doc_path.stem,
            )
            result_queue.put((doc_path_str, str(e)))
        else:
            worker_logger.info("[%s] Salvato: %s", use_case_id, output_path.name)
            result_queue.put((doc_path_str, None))

    worker_logger.info("[%s] Worker terminato.", use_case_id)
