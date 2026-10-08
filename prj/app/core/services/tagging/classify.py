"""Stadio classify+extract: da unità (già ricondotte a un RM) a candidati finali.

Sostituisce `tag_mo`+`tag_odc` nella pipeline v2. Per ogni unità una sola call LLM: estrae i
brani verbatim pertinenti e, per ciascuno, l'insieme degli OdC che tratta; il **MO è DERIVATO
dall'OdC** (albero stretto), senza una call dedicata. Uno stesso brano genera più tag (uno per
OdC). L'ente resta `None` (fan-out demandato alla fase dedicata). Call parallele per unità.
"""

import logging
from functools import partial
from typing import Any

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.models.registry.hierarchy import Hierarchy, RMHierarchy, extract_code
from core.models.tagging.candidates import BranoCandidate
from core.models.tagging.stages import AmlClassifyOutput, ClassifiedBrano, ClassifyOutput, CreditoClassifyOutput
from core.models.tagging.stats import TaggerStats
from core.resources.builders import rm_odc_prompt_block
from core.resources.classify_system import CLASSIFY_SYSTEM
from core.services.llm_client import Layer, call_llm_timed
from core.services.registry.hierarchy import SUPPORTED_RMS, canonicalize_label
from core.services.tagging._parallel import TAGGING_MAX_WORKERS, parallel_llm_map

logger = logging.getLogger(__name__)

CLASSIFY_MAX_TOKENS: int = get_obj_from_config_path("llm.yaml")["calls"]["classify"]["max_tokens"]

_CLASSIFY_OUTPUT_BY_RM: dict[str, type[ClassifyOutput[Any]]] = {
    "Credito": CreditoClassifyOutput,
    "AML": AmlClassifyOutput,
}
assert set(_CLASSIFY_OUTPUT_BY_RM) == SUPPORTED_RMS


def _odc_index(rm_hier: RMHierarchy) -> tuple[list[str], dict[str, str]]:
    """(etichette OdC valide, mappa codice-OdC → etichetta MO) per il Risk Model."""
    valid_labels: list[str] = []
    code_to_mo: dict[str, str] = {}
    for mo in rm_hier.mos:
        for odc in mo.odcs:
            valid_labels.append(odc.label)
            code_to_mo[odc.code] = mo.label
    return valid_labels, code_to_mo


def _classify_user_msg(cand: BranoCandidate, prompt_block: str) -> str:
    return (
        f"## UNITÀ DA CLASSIFICARE\n\n"
        f"Risk Model: **{cand.risk_model}**\n"
        f"Pagina/e: {cand.pagina}\n\n"
        f"### Testo dell'unità:\n\n{cand.brano}\n\n"
        f"---\n\n{prompt_block}"
    )


def _classify_unit(
    layer: Layer, cand: BranoCandidate, idx: int, hierarchy: Hierarchy, model: str
) -> tuple[int, list[ClassifiedBrano[Any]], float]:
    response_format = _CLASSIFY_OUTPUT_BY_RM.get(cand.risk_model)
    if response_format is None:
        return idx, [], 0.0

    user_msg = _classify_user_msg(cand, rm_odc_prompt_block(hierarchy, cand.risk_model))
    result, elapsed = call_llm_timed(layer, CLASSIFY_SYSTEM, user_msg, response_format, CLASSIFY_MAX_TOKENS, model)
    if result is None:
        return idx, [], elapsed
    return idx, result.brani, elapsed


def _expand(cand: BranoCandidate, brani: list[ClassifiedBrano[Any]], rm_hier: RMHierarchy) -> list[BranoCandidate]:
    """Da (unità, brani estratti) ai candidati finali: un tag per (brano, OdC), MO derivato."""
    valid_labels, code_to_mo = _odc_index(rm_hier)
    is_table = cand.tipo_citazione == "table"
    out: list[BranoCandidate] = []
    for brano in brani:
        # Per le tabelle la citazione non è confrontata per testo (match per id): si tiene la tabella intera.
        citazione = cand.brano if is_table else brano.citazione
        for odc in brano.odc:
            odc_label = canonicalize_label(odc.odc_label, valid_labels)
            mo_label = code_to_mo.get(extract_code(odc_label))
            if mo_label is None:
                continue
            out.append(
                BranoCandidate(
                    risk_model=cand.risk_model,
                    ente=None,
                    brano=citazione,
                    pagina=cand.pagina,
                    rationale=cand.rationale,
                    rm_confidence=cand.rm_confidence,
                    mo=mo_label,
                    mo_confidence=odc.confidence,
                    odc=odc_label,
                    odc_confidence=odc.confidence,
                    tipo_citazione=cand.tipo_citazione,
                    table_id=cand.table_id,
                    table_entities=cand.table_entities,
                )
            )
    return out


def classify_candidates(
    layer: Layer,
    candidates: list[BranoCandidate],
    hierarchy: Hierarchy,
    model: str,
    stats: TaggerStats,
) -> list[BranoCandidate]:
    """Classifica ogni unità e produce i candidati finali (brano + MO + OdC). Ente resta None."""
    to_classify = [(idx, cand) for idx, cand in enumerate(candidates) if hierarchy.is_supported(cand.risk_model)]
    if not to_classify:
        return []

    logger.info("  classify: %d unità da classificare (workers=%d)", len(to_classify), TAGGING_MAX_WORKERS)
    tasks = [partial(_classify_unit, layer, cand, idx, hierarchy, model) for idx, cand in to_classify]
    results = parallel_llm_map(tasks, stats)

    final: list[BranoCandidate] = []
    for idx, cand in enumerate(candidates):
        unit_brani = results.get(idx)
        rm_hier = hierarchy.get_rm(cand.risk_model)
        if not unit_brani or not rm_hier:
            # Candidato non supportato o senza brani estratti: scartato.
            continue
        final.extend(_expand(cand, unit_brani, rm_hier))
    stats.n_tags_with_mo = len(final)
    stats.n_tags_with_odc = len(final)
    logger.info("  classify: %d tag finali (brano+MO+OdC)", len(final))
    return final
