"""Stage di estrazione della data documento dalla prima pagina."""

import logging

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.models.tagging.stages import DocumentDateOutput
from core.models.tagging.stats import TaggerStats
from core.resources.date_extraction_system import DATE_EXTRACTION_SYSTEM
from core.services.llm_client import DEFAULT_MODEL, Layer, call_llm_timed
from core.services.text.markdown import extract_first_page

logger = logging.getLogger(__name__)

_DATE_EXTRACTION_CONFIG = get_obj_from_config_path("llm.yaml")["calls"]["date_extraction"]

DATE_EXTRACTION_MODEL: str = _DATE_EXTRACTION_CONFIG.get("model", DEFAULT_MODEL)
DATE_EXTRACTION_MAX_TOKENS: int = _DATE_EXTRACTION_CONFIG["max_tokens"]


def extract_document_date(
    layer: Layer,
    doc_id: str,
    doc_text: str,
    model: str = DATE_EXTRACTION_MODEL,
    stats: TaggerStats | None = None,
) -> DocumentDateOutput | None:
    """Estrae la data documento dalla prima pagina con anno separato dal trimestre/quarter.

    Fail-soft: `None` se la call LLM fallisce dopo i retry, non blocca il resto del tagging."""
    first_page_text = extract_first_page(doc_text)

    user_msg = f"## PRIMA PAGINA DEL DOCUMENTO\n\nID documento: {doc_id}\n\n{first_page_text}"

    logger.info("  Estrazione data documento dalla prima pagina...")

    result, elapsed = call_llm_timed(
        layer, DATE_EXTRACTION_SYSTEM, user_msg, DocumentDateOutput, DATE_EXTRACTION_MAX_TOKENS, model
    )
    if stats is not None:
        stats.llm_calls += 1
        stats.llm_time_s += elapsed

    if result is None:
        logger.warning("  Data documento: estrazione fallita (%.1fs)", elapsed)
        return None

    logger.info(
        "  Data documento: %s %s (%.1fs)",
        result.date.year or "[year not found]",
        result.date.quarter or "[quarter not found]",
        elapsed,
    )
    return result
