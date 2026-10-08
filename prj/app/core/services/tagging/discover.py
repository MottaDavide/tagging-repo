"""Stage 1 (discovery): enumera le unità del documento e le classifica per Risk Model.

Sostituisce la scansione whole-document di `tag_rm`: il documento viene segmentato in unità
(sezioni + tabelle, `segment_document`) e ogni unità passa per un **gate RM** (una call LLM,
permissiva, scope Credito/AML). Le unità pertinenti diventano `BranoCandidate` — una per RM —
che gli stage `tag_mo`/`tag_odc` classificheranno. Nessun cap: il fan-out su ente/MO/OdC
avviene a valle. Le call sono parallele per unità (`ThreadPoolExecutor`).
"""

import logging
from functools import partial

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.models.tagging.candidates import BranoCandidate
from core.models.tagging.stages import RMGateOutput
from core.models.tagging.stats import TaggerStats
from core.models.tagging.units import Unit
from core.resources.discovery_system import DISCOVERY_SYSTEM
from core.services.llm_client import Layer, call_llm_timed
from core.services.tagging._parallel import TAGGING_MAX_WORKERS, parallel_llm_map
from core.services.text.segmentation import segment_document

logger = logging.getLogger(__name__)

DISCOVERY_MAX_TOKENS: int = get_obj_from_config_path("llm.yaml")["calls"]["discover"]["max_tokens"]

# Brani lunghi vengono troncati (head+tail) prima della call LLM.
BRANO_MAX_CHARS_FOR_LLM: int = get_obj_from_config_path("tagging.yaml")["classify"]["brano_max_chars_for_llm"]

TABLE_MIN_ENTITIES = 2


def _truncate_brano(brano: str, max_chars: int = BRANO_MAX_CHARS_FOR_LLM) -> str:
    """Tronca il brano mantenendo inizio e fine, segnalando il taglio."""
    if len(brano) <= max_chars:
        return brano
    half = max_chars // 2
    return brano[:half] + f"\n\n[...testo troncato, {len(brano):,} chars totali...]\n\n" + brano[-half:]


def _unit_user_msg(unit: Unit) -> str:
    kind = "tabella" if unit.kind == "table" else "sezione"
    return (
        f"## UNITÀ DA CLASSIFICARE ({kind})\n\n"
        f"Sezione: {unit.heading or '(nessuna)'}\n"
        f"Pagina: {unit.page if unit.page is not None else 'n/d'}\n\n"
        f"### Testo dell'unità:\n\n{_truncate_brano(unit.text)}"
    )


def _gate_unit(layer: Layer, unit: Unit, idx: int, model: str) -> tuple[int, RMGateOutput | None, float]:
    result, elapsed = call_llm_timed(
        layer, DISCOVERY_SYSTEM, _unit_user_msg(unit), RMGateOutput, DISCOVERY_MAX_TOKENS, model
    )
    return idx, result, elapsed


def discover_candidates(layer: Layer, doc_text: str, model: str, stats: TaggerStats) -> list[BranoCandidate]:
    """Segmenta il documento e gate-RM ogni unità → candidati (una per RM pertinente)."""
    units = segment_document(doc_text)
    n_tables = sum(1 for u in units if u.kind == "table")
    # Gate tabelle: scarta le tabelle generiche (poche righe-ente) prima di spendere call LLM.
    units = [u for u in units if u.kind != "table" or u.n_entities >= TABLE_MIN_ENTITIES]
    n_tables_kept = sum(1 for u in units if u.kind == "table")
    logger.info(
        "  discovery: %d unità (workers=%d) — tabelle %d/%d oltre il gate (≥%d enti)",
        len(units),
        TAGGING_MAX_WORKERS,
        n_tables_kept,
        n_tables,
        TABLE_MIN_ENTITIES,
    )

    tasks = [partial(_gate_unit, layer, unit, idx, model) for idx, unit in enumerate(units)]
    results = parallel_llm_map(tasks, stats)

    candidates: list[BranoCandidate] = []
    for idx, unit in enumerate(units):
        result = results.get(idx)
        if not result:
            continue
        for assignment in result.assignments:
            candidates.append(
                BranoCandidate(
                    risk_model=assignment.risk_model,
                    ente=None,
                    brano=unit.text,
                    pagina=str(unit.page) if unit.page is not None else "",
                    rationale=assignment.reasoning,
                    rm_confidence=assignment.confidence,
                    tipo_citazione="table" if unit.kind == "table" else "text",
                    table_id=unit.table_id,
                    table_entities=unit.entities,
                )
            )

    stats.n_tag_rm_tags = len(candidates)
    stats.n_tag_rm_after_postprocess = len(candidates)
    logger.info("  discovery: %d candidati (Credito/AML)", len(candidates))
    return candidates
