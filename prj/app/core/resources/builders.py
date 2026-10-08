"""Builder dei prompt parametrici (blocchi OdC per classify, prompt img-table)."""

from core.models.registry.hierarchy import Hierarchy
from core.resources.img_table_user import IMG_TABLE_USER


def rm_odc_prompt_block(hierarchy: Hierarchy, rm_name: str) -> str:
    """Blocco prompt con TUTTI gli OdC del Risk Model, raggruppati per MO (per lo stadio classify).

    L'MO è mostrato solo come raggruppamento/contesto e viene derivato dall'OdC scelto, senza una
    call dedicata.
    """
    rm = hierarchy.get_rm(rm_name)
    if not rm:
        return f"(Nessun OdC disponibile per il Risk Model '{rm_name}')"

    n_odc = sum(len(mo.odcs) for mo in rm.mos)
    lines = [
        f"## OBIETTIVI DI CONTROLLO per il Risk Model '{rm_name}' ({n_odc} OdC, raggruppati per Macro Obiettivo)\n"
    ]
    for mo in rm.mos:
        lines.append(f"### Macro Obiettivo: {mo.label}")
        for odc in mo.odcs:
            lines.append(f"- **{odc.label}**")
            lines.append(f"  {odc.description.strip()}")
        lines.append("")
    return "\n".join(lines)


def build_img_table_user_prompt(page_number: int, figures_json: str, tables_json: str) -> str:
    """User prompt per la descrizione LLM di figure/tabelle di una pagina."""
    return IMG_TABLE_USER.format(
        page_number=page_number,
        figures_json=figures_json,
        tables_json=tables_json,
    )
