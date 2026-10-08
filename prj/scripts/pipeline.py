"""Entry point: orchestratore CLI della pipeline di tagging.

Sotto-comandi click per ciascuno stadio. Esempi:

  python prj/scripts/pipeline.py parse
  python prj/scripts/pipeline.py prepare --workers 8
  python prj/scripts/pipeline.py tag --parallel --force
  python prj/scripts/pipeline.py annotate-schede --single documento.md
  python prj/scripts/pipeline.py all
"""

import logging
import multiprocessing
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import click

from core.config import (
    ANNOTATED_WITH_DESC_DIR,
    CLEAN_DIR,
    CLEAN_WITH_DESC_DIR,
    DOCUMENTS_DIR,
    ENTI_ESTRATTI_JSON,
    PARSED_DIR,
    SCHEDE_TAGGED_JSON,
    TAGGED_DIR,
)
from core.orchestrators.tag_document import MODEL as TAG_MODEL
from core.services.enrichment.annotate import run_batch as annotate_run_batch
from core.services.enrichment.annotate_schede import run_batch as annotate_schede_run_batch
from core.services.enrichment.img_table import MODEL as IMG_MODEL
from core.services.enrichment.img_table import run_batch as img_table_run_batch
from core.services.parsing.parse import (
    NUM_WORKERS as PARSE_WORKERS,
)
from core.services.parsing.parse import (
    SUPPORTED_EXTENSIONS as PARSE_EXTENSIONS,
)
from core.services.parsing.parse import (
    init_genfactory_for_parsing,
)
from core.services.parsing.parse import (
    process_file as parse_process_file,
)
from core.services.parsing.prepare import NUM_WORKERS as PREPARE_WORKERS
from core.services.parsing.prepare import process_file as prepare_process_file
from core.utils.logging import setup_logging
from tag_batch import DEFAULT_USE_CASES, PARALLEL_USE_CASES
from tag_batch import run as tag_run

logger = logging.getLogger(__name__)


@click.group(help="Orchestratore della pipeline di tagging.")
def cli() -> None:
    """Group entry point."""


# Stage 1: parse ----------------------------------------------------------


def _run_parse_batch(input_dir: Path, output_dir: Path, num_workers: int) -> None:
    """Orchestratore batch del parsing PDF.

    Vive nello script (non in `core.services.parsing.parse`) perché il batching è
    competenza dello script: il modulo `core` espone solo i building block
    (`init_worker`, `process_file`) usabili anche da future API.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"INPUT_DIR non trovata: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_files = [f for f in input_dir.rglob("*") if f.is_file() and f.suffix.lower() in PARSE_EXTENSIONS][:100]
    if not all_files:
        logger.warning("Nessun documento trovato in %s con estensioni %s", input_dir, PARSE_EXTENSIONS)
        return

    files = [f for f in all_files if not (output_dir / (f.stem + ".md")).exists()]
    skipped = len(all_files) - len(files)
    if skipped:
        logger.info("Saltati %d documenti già processati in %s.", skipped, output_dir)
    if not files:
        logger.info("Tutti i documenti risultano già processati.")
        return

    logger.info("Trovati %d documenti da processare con %d worker(s).", len(files), num_workers)
    tasks: list[tuple[Path, Path]] = [(f, output_dir) for f in files]
    t_global = time.time()
    layer = init_genfactory_for_parsing()

    if num_workers > 1:
        worker = partial(parse_process_file, layer=layer)
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            results = list(executor.map(worker, tasks))
    else:
        results = [parse_process_file(task, layer) for task in tasks]

    successes = sum(1 for _, ok, _ in results if ok)
    logger.info(
        "Completato: %d/%d documenti in %.1fs totali.",
        successes,
        len(files),
        time.time() - t_global,
    )


@cli.command(help="Parsing PDF → markdown via Azure Document Intelligence.")
@click.option("--input-dir", type=click.Path(path_type=Path, file_okay=False), default=DOCUMENTS_DIR, show_default=True)
@click.option("--output-dir", type=click.Path(path_type=Path, file_okay=False), default=PARSED_DIR, show_default=True)
@click.option("--workers", type=int, default=PARSE_WORKERS, show_default=True, help="Worker paralleli.")
def parse(input_dir: Path, output_dir: Path, workers: int) -> None:
    setup_logging("pipeline.parse")
    _run_parse_batch(input_dir=input_dir, output_dir=output_dir, num_workers=workers)


# Stage 2: prepare --------------------------------------------------------


def _run_prepare_batch(input_dir: Path, output_dir: Path, num_workers: int, force: bool) -> None:
    """Orchestratore batch del cleaning markdown.

    Vive nello script (non in `core.services.parsing.prepare`) perché il batching è
    competenza dello script: il modulo `core` espone solo i building block
    (`clean_document`, `process_file`, le step di cleaning) usabili anche da future API.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory non trovata: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.glob("*.md"))
    if not files:
        logger.warning("Nessun file .md trovato in %s", input_dir)
        return

    if force:
        to_process = files
    else:
        to_process = [f for f in files if not (output_dir / f.name).exists()]
        skipped = len(files) - len(to_process)
        if skipped:
            logger.info("Saltati %d file già presenti in %s", skipped, output_dir)
    if not to_process:
        logger.info("Tutti i file risultano già preparati.")
        return

    logger.info("Preparazione di %d documenti con %d worker(s)", len(to_process), num_workers)
    tasks = [(f, output_dir) for f in to_process]
    t0 = time.time()

    if num_workers > 1:
        with multiprocessing.Pool(processes=num_workers) as pool:
            results = pool.map(prepare_process_file, tasks)
    else:
        results = [prepare_process_file(t) for t in tasks]

    ok = sum(1 for _, success, _ in results if success)
    logger.info("Completato: %d/%d documenti in %.1fs", ok, len(to_process), time.time() - t0)


@cli.command(help="Pulizia statica dei markdown parsati (regex deterministica).")
@click.option("--input-dir", type=click.Path(path_type=Path, file_okay=False), default=PARSED_DIR, show_default=True)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=CLEAN_DIR,
    show_default=True,
)
@click.option("--workers", type=int, default=PREPARE_WORKERS, show_default=True, help="Worker paralleli.")
@click.option("--force", is_flag=True, help="Riprocessa anche file già presenti in output.")
def prepare(input_dir: Path, output_dir: Path, workers: int, force: bool) -> None:
    setup_logging("pipeline.prepare")
    _run_prepare_batch(input_dir=input_dir, output_dir=output_dir, num_workers=workers, force=force)


# Stage 3: img-table ------------------------------------------------------


@cli.command(name="img-table", help="Descrizione LLM di figure e tabelle (una call per pagina).")
@click.option("--input-dir", type=click.Path(path_type=Path, file_okay=False), default=CLEAN_DIR, show_default=True)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=CLEAN_WITH_DESC_DIR,
    show_default=True,
)
@click.option("--model", type=str, default=IMG_MODEL, show_default=True)
@click.option("--single", "-d", "single", type=str, default=None, metavar="FILE", help="Singolo documento (stem).")
@click.option("--page", "-p", "page", type=int, default=None, help="Pagina specifica (richiede --single).")
@click.option("--force", is_flag=True, help="Riprocessa documenti già descritti.")
def img_table(
    input_dir: Path,
    output_dir: Path,
    model: str,
    single: str | None,
    page: int | None,
    force: bool,
) -> None:
    setup_logging("pipeline.img_table")
    if page is not None and not single:
        logger.warning("--page ignorato perché --single non specificato.")
        page = None
    img_table_run_batch(
        input_dir=input_dir,
        output_dir=output_dir,
        model=model,
        single_file=single,
        target_page=page,
        force=force,
    )


# Stage 5: annotate -------------------------------------------------------


@cli.command(help="Annotazione marker «ENTE[ente_raw|canonical]» nei markdown.")
@click.option(
    "--input-dir", type=click.Path(path_type=Path, file_okay=False), default=CLEAN_WITH_DESC_DIR, show_default=True
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=ANNOTATED_WITH_DESC_DIR,
    show_default=True,
)
@click.option(
    "--enti-json", type=click.Path(path_type=Path, dir_okay=False), default=ENTI_ESTRATTI_JSON, show_default=True
)
@click.option("--single", type=str, default=None, metavar="FILE", help="Singolo documento (stem).")
@click.option("--force", is_flag=True, help="Riprocessa documenti già annotati.")
def annotate(input_dir: Path, output_dir: Path, enti_json: Path, single: str | None, force: bool) -> None:
    setup_logging("pipeline.annotate")
    annotate_run_batch(
        input_dir=input_dir,
        output_dir=output_dir,
        entities_path=enti_json,
        single_file=single,
        force=force,
    )


# Stage opzionale: annotate-schede (marker RM/MO/ODC dalle schede di controllo) -----
# Non incluso in `all`: richiede il file schede_tagged.json e si lancia esplicitamente
# quando il documento è coperto da schede di controllo.


@cli.command(name="annotate-schede", help="Annotazione marker «RM[...] | MO[...] | ODC[...]» nei markdown.")
@click.option(
    "--input-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=ANNOTATED_WITH_DESC_DIR,
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=ANNOTATED_WITH_DESC_DIR,
    show_default=True,
)
@click.option(
    "--schede-json",
    type=click.Path(path_type=Path, dir_okay=False),
    default=SCHEDE_TAGGED_JSON,
    show_default=True,
)
@click.option("--single", type=str, default=None, metavar="FILE", help="Singolo documento.")
@click.option("--force", is_flag=True, help="Riprocessa documenti già annotati.")
def annotate_schede(
    input_dir: Path,
    output_dir: Path,
    schede_json: Path,
    single: str | None,
    force: bool,
) -> None:
    setup_logging("pipeline.annotate_schede")
    annotate_schede_run_batch(
        input_dir=input_dir,
        output_dir=output_dir,
        schede_path=schede_json,
        single_file=single,
        force=force,
    )


# Stage 6: tag (3-stage tagger) -------------------------------------------


@cli.command(help="Tagger (discovery per unità). Default: serial. Con --parallel: 2 use_case in multiprocess.")
@click.option(
    "--input-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=ANNOTATED_WITH_DESC_DIR,
    show_default=True,
)
@click.option("--output-dir", type=click.Path(path_type=Path, file_okay=False), default=TAGGED_DIR, show_default=True)
@click.option("--model", type=str, default=TAG_MODEL, show_default=True)
@click.option(
    "--use-case",
    "use_case",
    multiple=True,
    metavar="ID",
    help=(
        "Use-case id (ripetibile). Specificandone più di uno si abilita il parallelismo "
        f"multiprocess (1 worker per use-case). Default: {DEFAULT_USE_CASES[0]}."
    ),
)
@click.option(
    "--parallel",
    is_flag=True,
    help=f"Scorciatoia: usa {PARALLEL_USE_CASES} (multiprocessing, 2 worker).",
)
@click.option("--single", type=str, default=None, metavar="FILE")
@click.option("--force", is_flag=True, help="Riprocessa già taggati.")
@click.option(
    "--gt-file",
    "gt_file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Se fornito, tagga solo i documenti presenti nella ground truth (es. data/gt.json).",
)
def tag(
    input_dir: Path,
    output_dir: Path,
    model: str,
    use_case: tuple[str, ...],
    parallel: bool,
    single: str | None,
    force: bool,
    gt_file: Path | None,
) -> None:
    setup_logging("pipeline.runner")
    if parallel and use_case:
        raise click.UsageError("usa --parallel OPPURE --use-case, non entrambi.")
    if parallel:
        use_cases = PARALLEL_USE_CASES
    elif use_case:
        use_cases = tuple(use_case)
    else:
        use_cases = DEFAULT_USE_CASES

    tag_run(
        input_dir=input_dir,
        output_dir=output_dir,
        model=model,
        use_cases=use_cases,
        single_file=single,
        force=force,
        gt_file=gt_file,
    )


# `all`: tutti gli stadi con i default --------------------------------------


_ALL_STEPS: tuple[tuple[str, click.Command], ...] = (
    ("parse", parse),
    ("prepare", prepare),
    ("img-table", img_table),
    ("annotate", annotate),
    ("tag", tag),
)


@cli.command(name="all", help="Esegue tutti gli stadi in sequenza con i default.")
@click.pass_context
def all_steps(ctx: click.Context) -> None:
    setup_logging("pipeline.cli")
    for step_name, cmd in _ALL_STEPS:
        logger.info("\n========== STEP: %s ==========", step_name)
        try:
            ctx.invoke(cmd)
        except SystemExit as e:
            if e.code not in (0, None):
                logger.exception("Step %s terminato con codice %s, proseguo.", step_name, e.code)
        except Exception:
            logger.exception("Step %s fallito, proseguo.", step_name)
    logger.info("\n========== PIPELINE COMPLETA ==========")


if __name__ == "__main__":
    cli()
