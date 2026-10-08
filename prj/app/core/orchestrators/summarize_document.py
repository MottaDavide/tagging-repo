"""Orchestratore dello step di summary per un singolo documento (Stage 7).

Compone i building block di `core.services.summary`:
  1. carica i tag prodotti dallo stage `tag` (JSON formato GT);
  2. li raggruppa in tag unici `(RM, MO, OdC, Ente)`, scartando gli incompleti;
  3. per ogni tag unico genera l'analisi espositiva del documento (1 call LLM,
     call parallele a tag via `ThreadPoolExecutor`).
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from pydantic import TypeAdapter

from core.models.registry.hierarchy import Hierarchy
from core.models.registry.risk_models import RiskModel
from core.models.summary import (
    DocumentSummaries,
    TagSummary,
    TagSummaryEntry,
    UniqueTag,
)
from core.models.tagging.output import OutputTag
from core.services.llm_client import DEFAULT_MODEL, Layer
from core.services.summary.grouping import group_unique_tags
from core.services.summary.tag_summary import (
    lookup_descriptions,
    lookup_rm_description,
    summarize_tag,
)
from core.services.text.markdown import extract_title

logger = logging.getLogger(__name__)

_tags_adapter: TypeAdapter[list[OutputTag]] = TypeAdapter(list[OutputTag])

MODEL: str = DEFAULT_MODEL
SUMMARY_MAX_WORKERS: int = get_obj_from_config_path("tagging.yaml")["tag_summary"]["max_workers"]


def summarize_tags(
    layer: Layer,
    doc_id: str,
    doc_title: str,
    doc_text: str,
    tags: list[OutputTag],
    system_prompt: str,
    hierarchy: Hierarchy | None = None,
    risk_models: list[RiskModel] | None = None,
    model: str = MODEL,
    max_workers: int = SUMMARY_MAX_WORKERS,
    run_id: str | None = None,
) -> DocumentSummaries:
    """Produce le `DocumentSummaries` **in-memory** (nessuna scrittura su disco).

    Raggruppa i tag GT in tag unici, genera in parallelo l'analisi per tag
    (1 call LLM ciascuna, fail-soft) e assembla le entries. È il core riusato sia
    dall'orchestratore su disco (`summarize_document`) sia dall'API.
    """
    unique_tags = group_unique_tags(tags)
    if not unique_tags:
        logger.info("[run_id=%s][%s] Nessun tag unico completo: nessuna analisi generata.", run_id, doc_id)
        return DocumentSummaries(summaries=[])

    logger.info(
        "[run_id=%s][%s] %d tag unici da analizzare (workers=%d)...", run_id, doc_id, len(unique_tags), max_workers
    )

    t0 = time.time()
    results: dict[int, TagSummary] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _summarize_one,
                layer,
                unique_tag,
                doc_title,
                doc_text,
                system_prompt,
                hierarchy,
                risk_models,
                model,
            ): idx
            for idx, unique_tag in enumerate(unique_tags)
        }
        for future in as_completed(futures):
            idx = futures[future]
            summary, elapsed = future.result()
            if summary is not None:
                results[idx] = summary
                logger.info(
                    "[run_id=%s][%s] [%d/%d] analisi generata (%.1fs)",
                    run_id,
                    doc_id,
                    idx + 1,
                    len(unique_tags),
                    elapsed,
                )
            else:
                logger.warning(
                    "[run_id=%s][%s] [%d/%d] analisi FALLITA (%.1fs)",
                    run_id,
                    doc_id,
                    idx + 1,
                    len(unique_tags),
                    elapsed,
                )

    summaries = [
        TagSummaryEntry(tag=unique_tag, analisi=results[idx])
        for idx, unique_tag in enumerate(unique_tags)
        if idx in results
    ]
    logger.info(
        "[run_id=%s][%s] Completato: %d/%d analisi in %.1fs",
        run_id,
        doc_id,
        len(summaries),
        len(unique_tags),
        time.time() - t0,
    )
    return DocumentSummaries(summaries=summaries)


def summarize_document(
    layer: Layer,
    tagged_json_path: Path,
    doc_path: Path,
    system_prompt: str,
    hierarchy: Hierarchy | None = None,
    risk_models: list[RiskModel] | None = None,
    model: str = MODEL,
    max_workers: int = SUMMARY_MAX_WORKERS,
) -> DocumentSummaries:
    """Genera le `DocumentSummaries` per un documento a partire dai file su disco.

    `tagged_json_path` è il JSON di tagging (formato GT); `doc_path` è il markdown
    annotato completo (testo sorgente delle analisi). Carica i file e delega il
    calcolo a `summarize_tags`; nessuna scrittura su disco.
    """
    doc_id = tagged_json_path.stem
    raw_tags = json.loads(tagged_json_path.read_text(encoding="utf-8")).get("tags", [])
    tags = _tags_adapter.validate_python(raw_tags)
    doc_text = doc_path.read_text(encoding="utf-8")
    doc_title = extract_title(doc_text)

    return summarize_tags(
        layer, doc_id, doc_title, doc_text, tags, system_prompt, hierarchy, risk_models, model, max_workers
    )


def _summarize_one(
    layer: Layer,
    unique_tag: UniqueTag,
    doc_title: str,
    doc_text: str,
    system_prompt: str,
    hierarchy: Hierarchy | None,
    risk_models: list[RiskModel] | None,
    model: str,
) -> tuple[TagSummary | None, float]:
    mo_desc, odc_desc = lookup_descriptions(hierarchy, unique_tag)
    rm_desc = lookup_rm_description(risk_models, unique_tag.risk_model) if risk_models else None
    return summarize_tag(layer, unique_tag, doc_title, doc_text, system_prompt, model, mo_desc, odc_desc, rm_desc)
