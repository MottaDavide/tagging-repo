"""Aggregazione deterministica dei tag di un documento in tag unici (no LLM).

Chiave di unicità: `(Risk Model, MO, OdC, Ente)`. Due tag che condividono tutti e
quattro i campi sono lo stesso tag unico e vengono contati una volta sola (le loro
pagine/citazioni confluiscono nelle `occorrenze`).

I tag in input sono già completi: il filtro upstream in `_build_output` garantisce
che MO, OdC ed Ente siano sempre valorizzati prima di produrre un `OutputTag`.

L'input è la lista di `OutputTag` prodotta dallo stage `tag`.
"""

import logging

from core.models.summary import TagOccorrenza, UniqueTag
from core.models.tagging.output import OutputTag
from core.models.tagging.types import TagKey

logger = logging.getLogger(__name__)


def group_unique_tags(tags: list[OutputTag]) -> list[UniqueTag]:
    """Raggruppa i tag GT per chiave `(RM, MO, OdC, Ente)`.

    Preserva l'ordine di prima apparizione della chiave. Deduplica le occorrenze
    identiche `(Pagina, Citazione)` all'interno di uno stesso tag unico.
    """
    groups: dict[TagKey, UniqueTag] = {}

    for tag in tags:
        if tag.mo is None or tag.odc is None or tag.ente is None:
            continue
        rm = tag.risk_model.strip()
        key = TagKey(risk_model=rm, mo=tag.mo, odc=tag.odc, ente=tag.ente)
        unique = groups.get(key)
        if unique is None:
            unique = UniqueTag(risk_model=rm, mo=tag.mo, odc=tag.odc, ente=tag.ente)
            groups[key] = unique

        occ = TagOccorrenza(
            pagina=tag.pagina.strip(),
            citazione=tag.citazione.strip(),
            table_content=tag.table_content,
        )
        # `table_content` entra nella dedup: due tabelle distinte sulla stessa pagina condividono
        # l'etichetta breve `Tabella a pagina N` ma hanno contenuti diversi → restano occorrenze separate.
        if not any(
            o.pagina == occ.pagina and o.citazione == occ.citazione and o.table_content == occ.table_content
            for o in unique.occorrenze
        ):
            unique.occorrenze.append(occ)

    logger.info("  Tag unici: %d (da %d tag totali)", len(groups), len(tags))
    return list(groups.values())
