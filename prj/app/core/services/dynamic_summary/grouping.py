"""Aggregazione deterministica dei tag passati dall'utente in gruppi per quadrupla (no LLM).

Chiave di raggruppamento: la **quadrupla** `(Risk Model, MO, OdC, Ente)`. Due tag
che condividono tutti e quattro i campi appartengono allo stesso gruppo e i loro
estratti confluiscono nelle `estratti` del gruppo.

I tag **incompleti** — privi di MO o di OdC — vengono scartati: la quadrupla non è
valorizzata e quindi non c'è contesto su cui basare l'analisi (stessa scelta dello
step di summary statico, vedi `core.services.summary.grouping`).

L'input è la lista di tag nel formato GT/tagging (chiavi PascalCase italiane:
`"Risk Model"`, `"MO"`, `"OdC"`, `"Ente"`, `"Pagina"`, `"Citazione"`), con in più
una eventuale provenienza (`"documento"` / `"Documento"` / `"fonte"`) — così come
prodotta dallo stage `tag` o estratta dalla GT.
"""

import logging
from typing import Any

from core.models.dynamic_summary import GroupedTag, TagExtract
from core.models.tagging.types import TagKey

logger = logging.getLogger(__name__)

# Chiavi accettate per la provenienza dell'estratto (in ordine di preferenza).
_DOC_KEYS: tuple[str, ...] = ("documento", "Documento", "fonte", "Fonte")


def _extract_documento(tag: dict[str, Any]) -> str | None:
    """Provenienza dell'estratto, normalizzata: prima chiave valorizzata o `None`."""
    for key in _DOC_KEYS:
        val = tag.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


def group_input_tags(tags: list[dict[str, Any]]) -> list[GroupedTag]:
    """Raggruppa i tag passati per quadrupla `(RM, MO, OdC, Ente)`, scartando gli incompleti.

    Preserva l'ordine di prima apparizione della chiave. Deduplica gli estratti
    identici `(documento, pagina, citazione)` all'interno di uno stesso gruppo.
    """
    groups: dict[TagKey, GroupedTag] = {}
    n_skipped = 0

    for tag in tags:
        rm = (tag.get("Risk Model") or "").strip()
        mo = tag.get("MO")
        odc = tag.get("OdC")
        if not mo or not odc:
            n_skipped += 1
            continue

        ente = tag.get("Ente")
        key = TagKey(risk_model=rm, mo=mo, odc=odc, ente=ente)
        group = groups.get(key)
        if group is None:
            group = GroupedTag(risk_model=rm, mo=mo, odc=odc, ente=ente)
            groups[key] = group

        extract = TagExtract(
            documento=_extract_documento(tag),
            pagina=str(tag.get("Pagina") or "").strip(),
            citazione=(tag.get("Citazione") or "").strip(),
        )
        if not any(
            e.documento == extract.documento and e.pagina == extract.pagina and e.citazione == extract.citazione
            for e in group.estratti
        ):
            group.estratti.append(extract)

    logger.info(
        "  Gruppi (quadruple): %d (da %d tag passati, %d incompleti scartati)",
        len(groups),
        len(tags),
        n_skipped,
    )
    return list(groups.values())
