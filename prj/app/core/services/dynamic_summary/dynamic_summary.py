"""Generazione dell'analisi espositiva LLM per un gruppo di estratti (summary dinamica).

Una call LLM per gruppo `(RM, MO, OdC, Ente)`: riceve la quadrupla
contestualizzata (criteri RM + descrizioni MO/OdC + Ente) e i soli estratti
testuali associati, e restituisce un'analisi espositiva strutturata
(`DynamicTagSummary`, template fisso). A differenza dello step di summary statico
**non** riceve il documento intero: il materiale d'analisi sono gli estratti
passati dall'utente.

Le funzioni di lookup delle descrizioni vivono qui per essere riusate da
orchestratore e da future API.
"""

import logging

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.config import resolve_ambiente
from core.models.dynamic_summary import DynamicTagSummary, GroupedTag
from core.models.registry.hierarchy import Hierarchy, extract_code
from core.models.registry.risk_models import RiskModel
from core.services.llm_client import Layer, call_llm_timed
from core.services.registry.hierarchy import _rm_code_to_name

logger = logging.getLogger(__name__)

DYNAMIC_SUMMARY_MAX_TOKENS: int = get_obj_from_config_path("llm.yaml")["calls"]["dynamic_summary"]["max_tokens"]


def lookup_descriptions(
    hierarchy: Hierarchy | None,
    group: GroupedTag,
) -> tuple[str | None, str | None]:
    """Recupera le descrizioni di MO e OdC dalla gerarchia (best-effort).

    Le label hanno formato `'CODICE - Nome'`: si estrae il codice e si interroga
    la gerarchia. Ritorna `(None, None)` se la gerarchia non è disponibile o il
    RM/MO/OdC non vi è presente.
    """
    if hierarchy is None:
        return None, None
    rm_hier = hierarchy.get_rm(_rm_code_to_name(resolve_ambiente()).get(group.risk_model, group.risk_model))
    if rm_hier is None:
        return None, None
    mo = rm_hier.get_mo(extract_code(group.mo))
    odc = rm_hier.get_odc(extract_code(group.odc))
    return (mo.description if mo else None), (odc.description if odc else None)


def lookup_rm_description(risk_models: list[RiskModel], rm_name_or_code: str) -> str | None:
    """Recupera i criteri completi del Risk Model per nome (match esatto).

    Restituisce il campo `criteria` del `RiskModel` trovato (testo completo) da
    usare come contesto nel user message, o `None` se il RM non è presente.
    """
    canonical_rm_name = _rm_code_to_name(resolve_ambiente()).get(rm_name_or_code, rm_name_or_code)
    for rm in risk_models:
        if rm.name == canonical_rm_name:
            return rm.criteria
    return None


def _format_extract_header(documento: str | None, pagina: str) -> str:
    """Header bibliografico di un estratto: `[Documento — Pag. N]` o varianti."""
    parts: list[str] = []
    if documento:
        parts.append(documento)
    if pagina:
        parts.append(f"Pag. {pagina}")
    return f"[{' — '.join(parts)}]" if parts else "[estratto]"


def build_dynamic_summary_user_msg(
    group: GroupedTag,
    mo_description: str | None = None,
    odc_description: str | None = None,
    rm_description: str | None = None,
) -> str:
    """Costruisce il messaggio utente: quadrupla contestualizzata + estratti testuali.

    Non include alcun documento: il materiale d'analisi sono i soli estratti del
    gruppo. Le descrizioni MO/OdC e i criteri RM, quando disponibili, vengono
    iniettati per contestualizzare l'analisi sulla quadrupla.
    """
    tag_lines = [
        "## TAG IN ESAME (quadrupla)",
        "",
        f"Risk Model: **{group.risk_model}**",
    ]
    if rm_description:
        tag_lines.extend(["  Perimetro e criteri del RM:", rm_description.strip(), ""])
    tag_lines.append(f"Modello Operativo (MO): **{group.mo}**")
    if mo_description:
        tag_lines.append(f"  Definizione MO: {mo_description.strip()}")
    tag_lines.append(f"Obiettivo di Controllo (OdC): **{group.odc}**")
    if odc_description:
        tag_lines.append(f"  Definizione OdC: {odc_description.strip()}")
    tag_lines.append(f"Ente di riferimento: {group.ente or 'non specificato'}")

    estratti_lines = ["## ESTRATTI TESTUALI DA ANALIZZARE", ""]
    for e in group.estratti:
        estratti_lines.append(f'{_format_extract_header(e.documento, e.pagina)} "{e.citazione}"')
    estratti_lines.append("")

    return f"{chr(10).join(tag_lines)}\n\n---\n\n{chr(10).join(estratti_lines)}"


def summarize_group(
    layer: Layer,
    group: GroupedTag,
    system_prompt: str,
    model: str,
    mo_description: str | None = None,
    odc_description: str | None = None,
    rm_description: str | None = None,
) -> tuple[DynamicTagSummary | None, float]:
    """Una call LLM: analisi espositiva degli estratti del `group`.

    Ritorna `(DynamicTagSummary, elapsed_s)`; `(None, elapsed_s)` se la call
    fallisce (fail-soft per non bloccare gli altri gruppi del batch).
    """
    user_msg = build_dynamic_summary_user_msg(group, mo_description, odc_description, rm_description)
    return call_llm_timed(layer, system_prompt, user_msg, DynamicTagSummary, DYNAMIC_SUMMARY_MAX_TOKENS, model)
