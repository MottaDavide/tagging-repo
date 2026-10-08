"""Estrazione entità SOA tramite il pacchetto soa_detection.

Per ogni batch di entità definito in ``enti.json`` viene invocata
``soa_entity_from_text``. Le N chiamate sono eseguite in parallelo via
``ThreadPoolExecutor``. I risultati vengono mergiati in un unico dizionario
``entity_extracted``.

In caso di risultato finale vuoto (``entity_extracted: {}``), è previsto un
meccanismo di retry configurabile tramite ``entity_extraction.yaml``.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from soa_detection.core import soa_entity_from_text

from core.config import ENTI_JSON
from core.services.text.markdown import RE_PAGE_SPLIT

logger = logging.getLogger(__name__)

_CONFIG = get_obj_from_config_path("entity_extraction.yaml")["soa_detection"]


MAX_WORKERS: int = _CONFIG.get("max_workers")
MAX_RETRIES: int = _CONFIG.get("max_retries")
RETRY_DELAY_S: float = _CONFIG.get("retry_delay_s")
ISP_CODE: str = _CONFIG.get("isp_code")


# ---------------------------------------------------------------------------
# Helpers interni
# ---------------------------------------------------------------------------


def _load_entity_batches() -> list[list[dict[str, str]]]:
    """Carica ``enti.json`` e restituisce i batch come lista di liste.

    Ogni valore del dizionario è una lista di ``{"entity_id": "description"}``
    e corrisponde a un singolo ``lst_entities`` da passare a
    ``soa_entity_from_text``.
    """
    data: dict[str, list[dict[str, str]]] = json.loads(ENTI_JSON.read_text(encoding="utf-8"))
    return list(data.values())


def _call_single_batch(
    text_file_in: dict[str, Any],
    lst_entities: list[dict[str, str]],
    token: str,
    service: str,
    language: str,
    use_case: str,
    env: str,
    params: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Esegue una singola chiamata a ``soa_entity_from_text`` per un batch."""

    find_children_in_hierarchy = not any(ISP_CODE in entity for entity in lst_entities)

    result: dict[str, Any] | None = soa_entity_from_text(
        text_file_in=text_file_in,
        lst_entities=lst_entities,
        token=token,
        use_case=use_case,
        service=service,
        language=language,
        env=env,
        params=params,
        find_children_in_hierarchy=find_children_in_hierarchy,
    )
    return result


def _merge_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Fonde i risultati di N chiamate in un unico ``entity_extracted``.

    Le entità estratte dalla stessa pagina vengono unite; in caso di chiave
    duplicata l'ultima risposta sovrascrive la precedente.
    """
    merged: dict[str, dict[str, Any]] = {}
    extra: dict[str, Any] = {}
    total_tokens: int = 0
    for result in results:
        for page_key, page_entities in result.get("entity_extracted", {}).items():
            if page_key not in merged:
                merged[page_key] = {}
            merged[page_key].update(page_entities)
        result_extra = result.get("extra") or {}
        if not extra and result_extra:
            extra = {k: v for k, v in result_extra.items() if k != "total_tokens"}
        total_tokens += result_extra.get("total_tokens") or 0
    if extra:
        extra["total_tokens"] = total_tokens
    sorted_merged = dict(sorted(merged.items(), key=lambda kv: int(kv[0].split("_")[-1])))
    return {"entity_extracted": sorted_merged, "extra": extra}


def _is_empty_result(result: dict[str, Any]) -> bool:
    return not result.get("entity_extracted")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def extract_entities(
    cleaned_md: str,
    token: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Estrae le entità SOA per tutti i batch definiti in ``enti.json``.

    Il testo del documento (markdown pulito) viene strutturato in pagine
    e inviato a ciascun batch di entità definito in ``enti.json``.
    Le chiamate ai batch sono parallelizzate via ``ThreadPoolExecutor``.
    Il risultato finale è il merge di tutte le risposte.

    In caso di ``entity_extracted`` vuoto, la funzione ritenta fino a
    ``MAX_RETRIES`` volte, attendendo ``RETRY_DELAY_S`` secondi tra un
    tentativo e il successivo.

    :param cleaned_md:
        Contenuto markdown pulito del documento (output di ``clean_document``).
    :param token:
        Token di autenticazione per i servizi Cloud.
    :param run_id:
        Identificativo della run corrente, usato solo per il logging.
    :returns:
        Dizionario mergiato ``{"entity_extracted": {...}, "extra": {}}``.
    :raises RuntimeError:
        Se dopo tutti i retry il risultato è ancora vuoto.
    """
    service = _CONFIG["service"]
    language = _CONFIG["language"]
    use_case = _CONFIG["use_case"]
    env = os.getenv("ISP_AMBIENTE", "test")
    params: dict[str, Any] | None = _CONFIG.get("params") or None

    text_file_in = {
        "texts": {f"pag_{int(page_n)}": page_text.strip() for page_n, page_text in RE_PAGE_SPLIT.findall(cleaned_md)},
        "extra": {},
    }

    entity_batches = _load_entity_batches()
    logger.info("[run_id=%s] Caricati %d batch di entità da %s", run_id, len(entity_batches), ENTI_JSON.name)

    attempt = 0
    while attempt <= MAX_RETRIES:
        if attempt > 0:
            logger.warning(
                "[run_id=%s] Risultato entità vuoto, retry %d/%d (attesa %.1fs)",
                run_id,
                attempt,
                MAX_RETRIES,
                RETRY_DELAY_S,
            )
            time.sleep(RETRY_DELAY_S)

        batch_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(
                    _call_single_batch,
                    text_file_in,
                    lst_entities,
                    token,
                    service,
                    language,
                    use_case,
                    env,
                    params,
                ): idx
                for idx, lst_entities in enumerate(entity_batches)
            }
            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    result = future.result()
                except Exception:
                    logger.exception("[run_id=%s] Batch %d: errore inatteso, skip", run_id, batch_idx)
                    continue
                if result is not None:
                    batch_results.append(result)
                else:
                    logger.warning(
                        "[run_id=%s] Batch %d: soa_entity_from_text ha restituito None, skip",
                        run_id,
                        batch_idx,
                    )

        merged = _merge_results(batch_results)
        if not _is_empty_result(merged):
            logger.info(
                "[run_id=%s] Estrazione entità completata (tentativo %d): %d pagine annotate",
                run_id,
                attempt + 1,
                len(merged["entity_extracted"]),
            )
            return merged

        attempt += 1
    raise RuntimeError(f"SOA entity extraction returned empty result after {MAX_RETRIES} retries.")
