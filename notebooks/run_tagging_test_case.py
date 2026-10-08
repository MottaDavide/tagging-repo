"""Batch submit verso `/v1/tagging/test-case` + export/evaluation offline.

Uso tipico:

1. Avvia il servizio FastAPI normalmente.
2. Lancia lo script dalla root del repository, ad esempio:

   `python notebooks/run_tagging_test_case.py`

Flusso:
- inizializza una sola volta `init_genfactory(...)` e riusa il `Layer`; il token
  HTTP è recuperato via `TokenCache.get()` attraverso `layer.token()`;
- invia tutti i file di una cartella a `/v1/tagging/test-case`;
- polla `/v1/tagging/test-case/retrieve/{run_id}` fino al completamento;
- normalizza i payload finali nel formato atteso da `evaluation`: `RM/MO/OdC`
  restano codici API, `Ente` viene riportato a nome;
- salva le predizioni in JSON;
- se è fornita `--gt`, normalizza la GT agli stessi codici per `(RM, MO, OdC)`,
  mantenendo l'Ente come nome, e richiama `evaluation.evaluate()` per generare
  l'Excel con precision/recall/F1;
- se `--gt` è assente, salta la evaluation e salva un Excel con tutte le prediction.

Alla fine, se tutti i job sono completati, lo script pulisce la cartella condivisa
dei risultati test-case configurata in `prj/app/config/tagging.yaml`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import openpyxl


def _bootstrap_paths() -> None:
    """Aggiunge alla `sys.path` i path minimi per usare il codice del progetto dal notebook."""
    project_dir = Path(__file__).resolve().parents[1]
    extra_paths = [project_dir / "prj" / "app", project_dir / "prj", project_dir]
    for path in extra_paths:
        raw = str(path)
        if raw not in sys.path:
            sys.path.insert(0, raw)


_bootstrap_paths()

import requests  # noqa: E402
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path  # noqa: E402
from genfactory.config.enums import Environment  # noqa: E402
from prj.evaluation.orchestrators.evaluation import RM_FILTER, TIPO_VALUES, evaluate  # noqa: E402
from prj.evaluation.services.matcher import DEFAULT_THRESHOLD  # noqa: E402
from prj.scripts.build_gt_tableid import DEFAULT_GT  # noqa: E402

from core.config import (  # noqa: E402
    ANNOTATED_WITH_DESC_DIR,
    DATA_DIR,
    DOCUMENTS_DIR,
    ENV_FILE,
    resolve_ambiente,
)
from core.models.entities.entities import (  # noqa: E402
    DocumentInsertResponse,
    TaggingResponse,
    TaggingTestCaseStatusResponse,
)
from core.models.tagging.output import OutputTag  # noqa: E402
from core.services.llm_client import Layer, init_genfactory  # noqa: E402
from core.services.registry.enti import ente_name  # noqa: E402
from core.services.registry.hierarchy import mo_code, odc_code, rm_code  # noqa: E402
from core.utils.logging import setup_logging  # noqa: E402

logger = logging.getLogger("notebooks.run_tagging_test_case")
_TEST_CASE_RESULT_DIR = Path(get_obj_from_config_path("tagging.yaml")["temp_file"]["test-case-result-path"])

# da settare senza / finale
BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class SubmittedDoc:
    """Documento accettato dal servizio con il `run_id` associato."""

    path: Path
    run_id: str

    @property
    def stem(self) -> str:
        return self.path.stem


@dataclass(frozen=True)
class BatchEvalOptions:
    """Opzioni CLI del batch endpoint/evaluation."""

    endpoint: str
    input_dir: Path
    tagged_dir: Path
    results_dir: Path
    gt: Path | None
    output: Path
    docs_dir: Path
    scope: str
    rms: tuple[str, ...]
    tipi: tuple[str, ...]
    no_ente: bool
    threshold: float
    timeout_s: float
    poll_interval_s: float
    parallelism: int
    submit_sleep_s: float
    recursive: bool
    force: bool
    ambiente: str
    verbose: bool


def _iter_input_files(input_dir: Path, recursive: bool) -> list[Path]:
    """Ritorna i file input candidati, con ricerca opzionalmente ricorsiva."""
    pattern = "**/*" if recursive else "*"
    files = [p for p in input_dir.glob(pattern) if p.is_file()]
    return sorted(files)


def _dedup_by_stem(paths: Iterable[Path]) -> list[Path]:
    """Deduplica i file per stem, mantenendo il primo e loggando gli scarti."""
    chosen: dict[str, Path] = {}
    duplicates: dict[str, list[Path]] = {}
    for path in paths:
        prev = chosen.get(path.stem)
        if prev is None:
            chosen[path.stem] = path
            continue
        duplicates.setdefault(path.stem, [prev]).append(path)

    for stem, dup_paths in sorted(duplicates.items()):
        logger.warning(
            "Stem duplicato '%s': verrà usato solo il primo file (%s); scartati: %s",
            stem,
            dup_paths[0],
            ", ".join(str(p) for p in dup_paths[1:]),
        )
    return sorted(chosen.values())


def _filter_already_processed(paths: list[Path], tagged_dir: Path, force: bool) -> list[Path]:
    """Salta i documenti già presenti in `tagged_dir`, a meno di `force=True`."""
    if force:
        return paths
    return [path for path in paths if not (tagged_dir / f"{path.stem}.json").exists()]


def _access_token(layer: Layer) -> str:
    """Estrae il bearer token dal `Layer`, invocando `TokenCache.get()` se necessario."""

    # Nei test/unit fake può essere passato un `MagicMock()` al posto di un vero Layer:
    # in quel caso `layer.token` non è necessariamente una stringa/callable reale ma può
    # essere un altro mock annidato. Facciamo fallback a `str(...)` per mantenere il
    # comportamento robusto e compatibile con i test esistenti.
    token = layer.token if isinstance(layer.token, str) else layer.token()
    return str(token)


def _submit_document(
    session: requests.Session,
    layer: Layer,
    endpoint_url: str,
    scope: str,
    path: Path,
) -> SubmittedDoc:
    """Invia un singolo documento all'endpoint di submit e ritorna il `run_id`."""
    with path.open("rb") as handle:
        response = session.post(
            endpoint_url,
            headers={"Authorization": f"Bearer {_access_token(layer)}"},
            data={"file_name": path.name, "scope": scope},
            files={"file": (path.name, handle, "application/octet-stream")},
            timeout=60,
        )
    response.raise_for_status()
    payload = DocumentInsertResponse.model_validate(response.json())
    run_id = payload.run_id
    logger.info("Submit OK: %s -> run_id=%s", path.name, run_id)
    return SubmittedDoc(path=path, run_id=run_id)


def _poll_document_result(
    session: requests.Session,
    layer: Layer,
    base_url: str,
    submitted: SubmittedDoc,
    timeout_s: float,
    poll_interval_s: float,
) -> TaggingTestCaseStatusResponse | None:
    """Polla lo stato di un run finché non ottiene il risultato finale o scade il timeout."""
    status_url = f"{base_url.rstrip('/')}/retrieve/{submitted.run_id}"
    deadline = time.monotonic() + timeout_s

    while True:
        response = session.get(status_url, headers={"Authorization": f"Bearer {_access_token(layer)}"}, timeout=60)
        if response.status_code == requests.codes.not_found:
            raise RuntimeError(f"run_id non trovato durante il polling: {submitted.run_id}")

        response.raise_for_status()
        payload = TaggingTestCaseStatusResponse.model_validate(response.json())
        if response.status_code == requests.codes.ok:
            logger.info(
                "Risultato finale ricevuto per %s (run_id=%s, state=%s)",
                submitted.path.name,
                submitted.run_id,
                payload.state,
            )
            return payload

        if time.monotonic() >= deadline:
            return None

        time.sleep(poll_interval_s)


def _normalize_response_to_prediction(response: TaggingResponse) -> dict[str, Any]:
    """Converte il payload endpoint nel formato JSON consumato da `evaluation`."""
    normalized_tags = [
        OutputTag(
            pagina=",".join(str(page) for page in (tag.pages or [])),
            risk_model=(tag.risk_model.value or "").strip(),
            rm_confidence=None,
            mo=(tag.macro_obiettivo.value or "").strip(),
            mo_confidence=None,
            odc=(tag.obiettivo_di_controllo.value or "").strip(),
            odc_confidence=None,
            ente=ente_name(tag.ente),
            citazione=tag.citazione or "",
            tipo_citazione=tag.tipo_citazione,
        ).model_dump(
            by_alias=True,
            exclude_none=True,
            exclude={"rm_confidence", "mo_confidence", "odc_confidence"},
        )
        for tag in response.tagging_results.tags
    ]

    return {
        "filename": response.file_name,
        "date": response.tagging_results.date.model_dump() if response.tagging_results.date else None,
        "tags": normalized_tags,
    }


def _save_json(path: Path, payload: Any) -> None:
    """Salva un payload JSON UTF-8 con indentazione, creando la directory se manca."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_result_and_prediction(
    submitted: SubmittedDoc,
    payload: TaggingTestCaseStatusResponse,
    results_dir: Path,
    tagged_dir: Path,
) -> None:
    """Salva sia il payload raw finale del polling sia la prediction normalizzata."""
    raw_result_path = results_dir / f"{submitted.stem}.result.json"
    pred_path = tagged_dir / f"{submitted.stem}.json"

    _save_json(raw_result_path, payload.model_dump(by_alias=True))
    if payload.error is not None:
        logger.warning(
            "Risultato errore per %s (run_id=%s): %s",
            submitted.path.name,
            submitted.run_id,
            payload.error,
        )
        pred_payload = {"filename": submitted.path.name, "tags": [], "error": payload.error.model_dump(by_alias=True)}
    elif payload.data is None:
        pred_payload = {
            "filename": submitted.path.name,
            "tags": [],
            "error": {"step": payload.state, "exceptionMessage": "Payload finale senza data né error"},
        }
    else:
        pred_payload = _normalize_response_to_prediction(payload.data)
        pred_payload.setdefault("filename", submitted.path.name)
    _save_json(pred_path, pred_payload)


def _save_missing_prediction(submitted: SubmittedDoc, tagged_dir: Path) -> None:
    """Scrive un placeholder di prediction per i run che non chiudono entro timeout."""
    pred_path = tagged_dir / f"{submitted.stem}.json"
    pred_payload = {
        "filename": submitted.path.name,
        "tags": [],
        "error": {"step": "polling", "exceptionMessage": "Risultato non ricevuto entro timeout"},
    }
    _save_json(pred_path, pred_payload)


def _self_auth_environment() -> Environment:
    """Deriva l'ambiente genfactory usato dal notebook per l'auto-autenticazione."""
    if "ISP_AMBIENTE" in os.environ:
        return Environment.PRODUCTION if os.environ["ISP_AMBIENTE"] in {"svil", "test", "prod"} else Environment.TEST
    logger.warning("There is no isp ambiente, layer set to TEST")
    return Environment.TEST


def _process_document(
    layer: Layer,
    endpoint_url: str,
    scope: str,
    path: Path,
    timeout_s: float,
    poll_interval_s: float,
    results_dir: Path,
    tagged_dir: Path,
    submit_sleep_s: float,
) -> tuple[SubmittedDoc, bool]:
    """Esegue submit + polling di un documento e salva i file di output relativi."""

    # `requests.Session` non è pensata per essere condivisa tra thread: ogni worker usa la propria.
    with requests.Session() as session:
        submitted = _submit_document(session, layer, endpoint_url, scope, path)
        if submit_sleep_s > 0:
            time.sleep(submit_sleep_s)

        payload = _poll_document_result(
            session,
            layer,
            endpoint_url,
            submitted,
            timeout_s,
            poll_interval_s,
        )

    if payload is None:
        _save_missing_prediction(submitted, tagged_dir)
        return submitted, False

    _save_result_and_prediction(submitted, payload, results_dir, tagged_dir)
    return submitted, True


def _cleanup_test_case_result_dir() -> None:
    """Rimuove la cartella condivisa dei risultati test-case del servizio, se presente."""
    if not _TEST_CASE_RESULT_DIR.exists():
        return
    shutil.rmtree(_TEST_CASE_RESULT_DIR)
    logger.info("Cartella risultati test-case rimossa: %s", _TEST_CASE_RESULT_DIR)


def _normalize_gt_payload(gt_data: list[dict[str, Any]], ambiente: str) -> list[dict[str, Any]]:
    """Normalizza la GT ai codici RM/MO/OdC dell'API, lasciando l'Ente come nome."""
    normalized_docs: list[dict[str, Any]] = []
    for doc in gt_data:
        normalized_tags = []
        for tag in doc.get("tags", []):
            normalized_tag = dict(tag)
            normalized_tag["Risk Model"] = (
                rm_code(tag.get("Risk Model"), ambiente=ambiente) or str(tag.get("Risk Model") or "").strip()
            )
            normalized_tag["Ente"] = str(tag.get("Ente") or "").strip()
            normalized_tag["MO"] = mo_code(tag.get("MO"), ambiente=ambiente) or str(tag.get("MO") or "").strip()
            normalized_tag["OdC"] = odc_code(tag.get("OdC"), ambiente=ambiente) or str(tag.get("OdC") or "").strip()
            normalized_tags.append(normalized_tag)

        normalized_docs.append(
            {
                **doc,
                "tags": normalized_tags,
            }
        )
    return normalized_docs


def _write_predictions_excel(tagged_dir: Path, output: Path) -> None:
    """Esporta in Excel tutte le prediction salvate in `tagged_dir`, con eventuali errori."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Predictions"

    headers = [
        "Documento",
        "Pagina",
        "Risk Model",
        "Ente",
        "MO",
        "OdC",
        "Citazione",
        "Tipo Citazione",
        "Errore step",
        "Errore messaggio",
    ]
    ws.append(headers)

    for path in sorted(tagged_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        filename = str(payload.get("filename") or path.name)
        error = payload.get("error") or {}
        tags = payload.get("tags") or []

        if not tags:
            ws.append(
                [
                    filename,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    str(error.get("step") or ""),
                    str(error.get("exceptionMessage") or ""),
                ]
            )
            continue

        for tag in tags:
            ws.append(
                [
                    filename,
                    str(tag.get("Pagina") or ""),
                    str(tag.get("Risk Model") or ""),
                    str(tag.get("Ente") or ""),
                    str(tag.get("MO") or ""),
                    str(tag.get("OdC") or ""),
                    str(tag.get("Citazione") or ""),
                    str(tag.get("Tipo Citazione") or ""),
                    str(error.get("step") or ""),
                    str(error.get("exceptionMessage") or ""),
                ]
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)


def _evaluate_predictions(options: BatchEvalOptions) -> None:
    """Genera l'Excel finale: metriche se c'è GT, export prediction-only altrimenti."""
    if options.gt is None:
        _write_predictions_excel(options.tagged_dir, options.output)
        logger.info("GT non fornita: salvato Excel con tutte le prediction in %s", options.output)
        return

    gt_data = json.loads(options.gt.read_text(encoding="utf-8"))
    normalized_gt = _normalize_gt_payload(gt_data, options.ambiente)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        temp_gt_path = Path(handle.name)
        json.dump(normalized_gt, handle, ensure_ascii=False, indent=2)

    try:
        evaluate(
            tagged_dir=options.tagged_dir,
            gt_file=temp_gt_path,
            rm_filter=frozenset(options.rms) if options.rms else RM_FILTER,
            tipo_filter=frozenset(options.tipi),
            ignore_ente=options.no_ente,
            threshold=options.threshold,
            output=options.output,
            docs_dir=options.docs_dir,
        )
    finally:
        temp_gt_path.unlink(missing_ok=True)


@click.command(
    help=(
        "Chiama /v1/tagging/test-case su una cartella intera, polla i risultati e genera l'Excel di "
        "evaluation oppure, senza GT, un Excel con tutte le prediction."
    )
)
@click.option("--endpoint", default="/v1/tagging/test-case", show_default=True, help="Path dell'endpoint tagging.")
@click.option(
    "--input-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DOCUMENTS_DIR,
    show_default=True,
    help="Cartella dei documenti da inviare. Per default usa data/original-documents.",
)
@click.option(
    "--tagged-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DATA_DIR / "tagged-endpoint",
    show_default=True,
    help="Cartella dove salvare i JSON normalizzati per evaluation.",
)
@click.option(
    "--results-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DATA_DIR / "tagging-endpoint-results",
    show_default=True,
    help="Cartella dove salvare i payload raw finali ricevuti dal polling.",
)
@click.option(
    "--gt",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help=(
        "Ground truth opzionale da usare nella evaluation. Se omessa, salva solo l'Excel delle prediction. "
        f"Default precedente: {DEFAULT_GT}"
    ),
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DATA_DIR / "metriche_tagging_endpoint.xlsx",
    show_default=True,
    help="Excel finale: metriche se passi --gt, altrimenti export di tutte le prediction.",
)
@click.option(
    "--docs-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=ANNOTATED_WITH_DESC_DIR,
    show_default=True,
    help="Cartella dei markdown usata da evaluation per risolvere i TableId delle tabelle legacy.",
)
@click.option(
    "--scope",
    type=click.Choice(("fac", "vigilanza")),
    default="fac",
    show_default=True,
    help="Valore del parametro scope dell'endpoint.",
)
@click.option(
    "--rm",
    "rms",
    multiple=True,
    default=(),
    metavar="RM",
    help="Filtro Risk Model per evaluation (ripetibile). Default: come evaluation.",
)
@click.option(
    "--tipo",
    "tipi",
    multiple=True,
    type=click.Choice(sorted(TIPO_VALUES)),
    default=(),
    metavar="TIPO",
    help="Filtro Tipo Citazione per evaluation (ripetibile).",
)
@click.option(
    "--no-ente",
    is_flag=True,
    help="Disabilita il confronto sull'Ente, come nello script evaluate.py.",
)
@click.option(
    "--threshold",
    type=float,
    default=DEFAULT_THRESHOLD,
    show_default=True,
    help="Soglia overlap citazione usata da evaluation.",
)
@click.option(
    "--timeout-s",
    type=float,
    default=1800.0,
    show_default=True,
    help="Timeout massimo d'attesa per tutti i risultati finali.",
)
@click.option(
    "--poll-interval-s",
    type=float,
    default=2.0,
    show_default=True,
    help="Intervallo di polling verso l'endpoint di stato.",
)
@click.option(
    "--parallelism",
    type=int,
    default=1,
    show_default=True,
    help=(
        "Numero massimo di documenti processati in parallelo dal notebook. "
        "Tenerlo coerente con la capacità del servizio (worker FastAPI e servizi downstream)."
    ),
)
@click.option(
    "--submit-sleep-s",
    type=float,
    default=0.0,
    show_default=True,
    help="Pausa opzionale tra una submit e la successiva.",
)
@click.option(
    "--recursive",
    is_flag=True,
    help="Se impostato, cerca file anche nelle sottocartelle di input-dir.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Rielabora anche documenti che hanno già un JSON in tagged-dir.",
)
@click.option(
    "--ambiente",
    type=click.Choice(("prod", "non_prod")),
    default=resolve_ambiente(),
    show_default=True,
    help="Ambiente usato per decodificare i codici API (RM/MO/OdC). Deve combaciare col servizio.",
)
@click.option("--verbose", is_flag=True, help="Log verboso.")
def main(
    endpoint: str,
    input_dir: Path,
    tagged_dir: Path,
    results_dir: Path,
    gt: Path | None,
    output: Path,
    docs_dir: Path,
    scope: str,
    rms: tuple[str, ...],
    tipi: tuple[str, ...],
    no_ente: bool,
    threshold: float,
    timeout_s: float,
    poll_interval_s: float,
    parallelism: int,
    submit_sleep_s: float,
    recursive: bool,
    force: bool,
    ambiente: str,
    verbose: bool,
) -> None:
    """Entry point CLI: esegue batch submit/polling e produce l'Excel finale."""
    options = BatchEvalOptions(
        endpoint=endpoint,
        input_dir=input_dir,
        tagged_dir=tagged_dir,
        results_dir=results_dir,
        gt=gt,
        output=output,
        docs_dir=docs_dir,
        scope=scope,
        rms=rms,
        tipi=tipi,
        no_ente=no_ente,
        threshold=threshold,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        parallelism=parallelism,
        submit_sleep_s=submit_sleep_s,
        recursive=recursive,
        force=force,
        ambiente=ambiente,
        verbose=verbose,
    )
    setup_logging(logger.name)
    if options.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    layer = init_genfactory(env_file=str(ENV_FILE), env=_self_auth_environment())

    endpoint_url = f"{BASE_URL}{options.endpoint}"
    logger.info("Endpoint tagging: %s", endpoint_url)

    if not options.input_dir.exists():
        raise click.ClickException(f"Input dir non trovata: {options.input_dir}")
    if options.gt is not None and not options.gt.exists():
        raise click.ClickException(f"GT non trovata: {options.gt}")
    if options.parallelism < 1:
        raise click.ClickException("parallelism deve essere >= 1")

    input_files = _iter_input_files(options.input_dir, options.recursive)
    input_files = _dedup_by_stem(input_files)
    input_files = _filter_already_processed(input_files, options.tagged_dir, options.force)
    if not input_files:
        logger.warning("Nessun documento da processare in %s", options.input_dir)
        return

    options.tagged_dir.mkdir(parents=True, exist_ok=True)
    options.results_dir.mkdir(parents=True, exist_ok=True)

    missing: list[str] = []
    max_workers = min(options.parallelism, len(input_files))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tagging-batch") as executor:
        future_to_path = {
            executor.submit(
                _process_document,
                layer,
                endpoint_url,
                options.scope,
                path,
                options.timeout_s,
                options.poll_interval_s,
                options.results_dir,
                options.tagged_dir,
                options.submit_sleep_s,
            ): path
            for path in input_files
        }

        for index, future in enumerate(as_completed(future_to_path), start=1):
            path = future_to_path[future]
            try:
                submitted, completed = future.result()
            except Exception:
                logger.exception("Errore durante l'elaborazione di %s", path.name)
                raise

            logger.info("Completati %d/%d documenti", index, len(input_files))
            if not completed:
                logger.warning("Timeout polling per %s (run_id=%s)", submitted.path.name, submitted.run_id)
                missing.append(submitted.run_id)

    if missing:
        logger.warning("Run_id senza risultato finale: %s", ", ".join(sorted(missing)))

    _evaluate_predictions(options)
    logger.info("Excel salvato in %s", options.output)
    if missing:
        logger.warning(
            "Cleanup cartella risultati test-case saltato: alcuni job possono essere ancora in esecuzione lato servizio."
        )
    else:
        _cleanup_test_case_result_dir()


if __name__ == "__main__":
    main()
