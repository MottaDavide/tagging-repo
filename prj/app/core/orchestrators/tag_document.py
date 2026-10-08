"""Orchestratore della pipeline di tagging per un singolo documento."""

import logging
from pathlib import Path

from core.models.registry.hierarchy import Hierarchy
from core.models.tagging.candidates import BranoCandidate
from core.models.tagging.output import DocumentTaggingOutput, OutputTag
from core.models.tagging.stages import DocumentDateOutput
from core.models.tagging.stats import TaggerStats
from core.services.llm_client import DEFAULT_MODEL, Layer
from core.services.tagging import extract_document_date
from core.services.tagging.classify import classify_candidates
from core.services.tagging.discover import discover_candidates
from core.services.tagging.resolve_entes import resolve_entes
from core.services.text.tables import Table, enumerate_tables, table_html_clean

logger = logging.getLogger(__name__)

MODEL: str = DEFAULT_MODEL


def tag_document_units(
    layer: Layer,
    doc_path: Path,
    hierarchy: Hierarchy,
    model: str = MODEL,
    run_id: str | None = None,
) -> DocumentTaggingOutput:
    """Pipeline discovery per unità → classify+extract → fan-out ente."""
    doc_id = doc_path.stem
    doc_text = doc_path.read_text(encoding="utf-8")
    logger.info("[run_id=%s][%s] Avvio tagging...", run_id, doc_id)

    stats = TaggerStats()
    stats.input_chars = len(doc_text)
    date_result = extract_document_date(layer=layer, doc_id=doc_id, doc_text=doc_text, stats=stats)

    candidates = discover_candidates(layer, doc_text, model, stats)
    if not candidates:
        logger.info("[run_id=%s][%s] Nessuna unità pertinente a Credito/AML.", run_id, doc_id)
        stats.n_tags_final = 0
        return _build_output(doc_id, [], stats, date_result, doc_text)

    logger.info("[run_id=%s][%s] classify+extract: %d unità...", run_id, doc_id, len(candidates))
    candidates = classify_candidates(layer, candidates, hierarchy, model, stats)

    logger.info("[run_id=%s][%s] ente: fan-out struttura analizzata...", run_id, doc_id)
    candidates = resolve_entes(layer, candidates, doc_text, model, stats)

    output = _build_output(doc_id, candidates, stats, date_result, doc_text)
    logger.info(
        "[run_id=%s][%s] [OK] %d tag finali, %d chiamate LLM in %.1fs",
        run_id,
        doc_id,
        output.stats.n_tags_final,
        output.stats.llm_calls,
        output.stats.llm_time_s,
    )
    return output


def _citation_fields(c: BranoCandidate, tables_by_id: dict[str, Table]) -> tuple[str, str | None]:
    """`(citazione, table_content)` per un candidato.

    Per le tabelle la citazione è l'etichetta ``Tabella a pagina N`` e `table_content` è
    l'HTML integrale ripulito dai marker (`None` se l'id-tabella non è risolvibile). Per il
    testo la citazione è il brano verbatim e `table_content` è `None`.
    """
    if c.tipo_citazione != "table":
        return c.brano, None
    pagina = c.pagina.strip() or "n.d."
    citazione = f"Tabella a pagina {pagina}"
    table = tables_by_id.get(c.table_id) if c.table_id else None
    table_content = table_html_clean(table.html) if table else None
    return citazione, table_content


def _build_output(
    doc_id: str,
    candidates: list[BranoCandidate],
    stats: TaggerStats,
    date_result: DocumentDateOutput | None = None,
    doc_text: str = "",
) -> DocumentTaggingOutput:
    """Output in formato identico alla ground truth.

    Sono inclusi solo i candidati completi di MO, OdC ed Ente. Per le citazioni di tipo
    tabella la `citazione` è un'etichetta breve (``Tabella a pagina N``) e il contenuto
    integrale della tabella (HTML ripulito dai marker) viene esposto in `table_content`.
    """
    tables_by_id: dict[str, Table] = {t.id: t for t in enumerate_tables(doc_text)}

    tags: list[OutputTag] = []
    for c in candidates:
        if c.mo and c.odc and c.ente:
            citazione, table_content = _citation_fields(c, tables_by_id)
            tags.append(
                OutputTag(
                    pagina=c.pagina,
                    risk_model=c.risk_model,
                    rm_confidence=c.rm_confidence,
                    mo=c.mo,
                    mo_confidence=c.mo_confidence,
                    odc=c.odc,
                    odc_confidence=c.odc_confidence,
                    ente=c.ente,
                    citazione=citazione,
                    tipo_citazione=c.tipo_citazione,
                    table_id=c.table_id,
                    table_content=table_content,
                )
            )
    stats.n_tags_final = len(tags)
    return DocumentTaggingOutput(
        filename=doc_id,
        date=date_result.date if date_result else None,
        tags=tags,
        stats=stats,
    )
