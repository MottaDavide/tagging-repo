"""Orchestratore della summary dinamica: bag di tag dell'utente → analisi per quadrupla.

Compone i building block di `core.services.dynamic_summary`:
  1. raggruppa i tag passati per quadrupla `(RM, MO, OdC, Ente)`, scartando gli incompleti;
  2. per ogni gruppo genera l'analisi espositiva dei suoi estratti (1 call LLM,
     call parallele a gruppo via `ThreadPoolExecutor`).

`summarize_tags` produce le `DynamicSummaries` **in-memory** (nessuna scrittura su
disco); è la funzione componibile (richiamabile da una futura API a partire da
tag già in memoria). `run` è il front-door da CLI che carica i tag da un file
JSON e le risorse, poi delega a `summarize_tags` (il `Layer` va inizializzato dal
chiamante e passato in input, come per gli altri orchestratori).

A differenza dello step di summary statico (`summarize_document` + `summary_batch`)
non c'è iterazione per-documento: l'input è un unico insieme di tag e produce
un'unica run di output. Il servizio è quindi document-agnostico.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.config import resolve_ambiente
from core.models.dynamic_summary import (
    DynamicSummaries,
    DynamicSummaryEntry,
    DynamicTagSummary,
    GroupedTag,
)
from core.models.registry.hierarchy import Hierarchy, extract_code
from core.models.registry.risk_models import RiskModel
from core.services.dynamic_summary.dynamic_summary import (
    lookup_descriptions,
    lookup_rm_description,
    summarize_group,
)
from core.services.dynamic_summary.grouping import group_input_tags
from core.services.dynamic_summary.resources import load_dynamic_summary_resources
from core.services.llm_client import DEFAULT_MODEL, Layer
from core.services.registry.hierarchy import _rm_code_to_name

logger = logging.getLogger(__name__)

MODEL: str = DEFAULT_MODEL
DYNAMIC_SUMMARY_MAX_WORKERS: int = get_obj_from_config_path("tagging.yaml")["dynamic_summary"]["max_workers"]


def render_dynamic_summary_markdown(summaries: DynamicSummaries, hierarchy: Hierarchy) -> str:
    """Rende l'analisi in markdown leggibile per la review umana."""
    lines = []
    for summary in summaries.entries:
        rm_hier = hierarchy.get_rm(summary.risk_model)
        rm = rm_hier.risk_model if rm_hier else summary.risk_model
        mo = mo_obj.label if rm_hier and (mo_obj := rm_hier.get_mo(summary.mo)) else summary.mo
        odc = odc_obj.label if rm_hier and (odc_obj := rm_hier.get_odc(summary.odc)) else summary.odc

        lines = [
            f"# {summary.analisi.titolo}",
            "",
            f"- **Risk Model:** {rm}",
            f"- **Macro-obiettivo:** {mo}",
            f"- **Obiettivo di Controllo:** {odc}",
            f"- **Ente:** {summary.ente or '—'}",
        ]
        if summary.estratti:
            lines.append(f"- **Documenti:** {', '.join(summary.documenti)}")
        lines.extend(
            [
                "",
                "## Sintesi",
                "",
                summary.analisi.sintesi.strip(),
                "",
                "## Analisi per tema",
                "",
            ]
        )
        for tema in summary.analisi.temi:
            titolo_tema = f"{tema.riferimento}"
            lines.append(f"### {titolo_tema}")
            lines.append("")
            lines.append(tema.descrizione.strip())
            lines.append("")
        lines.extend(
            [
                "## Quadro complessivo",
                "",
                summary.analisi.quadro_complessivo.strip(),
                "",
            ]
        )
        if summary.estratti:
            lines.append("## Estratti selezionati per analisi dinamica")
            lines.extend(
                [
                    f"**[{estratto.documento}]**\n[p. {estratto.pagina}]\n{estratto.citazione.strip()}\n"
                    for estratto in summary.estratti
                ]
            )
    return "\n".join(lines)


def summarize_tags(
    layer: Layer,
    input_tags: list[dict[str, Any]],
    system_prompt: str,
    hierarchy: Hierarchy | None = None,
    risk_models: list[RiskModel] | None = None,
    model: str = MODEL,
    max_workers: int = DYNAMIC_SUMMARY_MAX_WORKERS,
) -> DynamicSummaries:
    """Genera le analisi per i tag passati. Nessuna scrittura su disco.

    Ritorna l'oggetto `DynamicSummaries`. Se nessun tag passato è completo
    (quadrupla valorizzata) ritorna comunque una `DynamicSummaries` vuota.
    """
    groups = group_input_tags(input_tags)

    if not groups:
        logger.info("Nessun gruppo completo dai %d tag passati: nessuna analisi generata.", len(input_tags))
        return DynamicSummaries(n_gruppi=0, n_tag_input=len(input_tags), entries=[])

    logger.info("%d gruppi (quadruple) da analizzare (workers=%d)...", len(groups), max_workers)

    t0 = time.time()
    results: dict[int, DynamicTagSummary] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_summarize_one, layer, group, system_prompt, hierarchy, risk_models, model): idx
            for idx, group in enumerate(groups)
        }
        for future in as_completed(futures):
            idx = futures[future]
            summary, elapsed = future.result()
            if summary is not None:
                results[idx] = summary
                logger.info("  [%d/%d] analisi generata (%.1fs)", idx + 1, len(groups), elapsed)
            else:
                logger.warning("  [%d/%d] analisi FALLITA (%.1fs)", idx + 1, len(groups), elapsed)

    entries: list[DynamicSummaryEntry] = []
    for idx, group in enumerate(groups):
        summary = results.get(idx)
        if summary is None:
            continue
        entries.append(_build_entry(group, summary, hierarchy))

    logger.info("Completato: %d/%d analisi in %.1fs", len(entries), len(groups), time.time() - t0)
    return DynamicSummaries(n_gruppi=len(entries), n_tag_input=len(input_tags), entries=entries)


def run(
    layer: Layer,
    input_file: Path,
    model: str = MODEL,
) -> DynamicSummaries | None:
    """Front-door da CLI: carica i tag da `input_file` (JSON) e genera le analisi.

    Ritorna `None` se l'input non è caricabile; altrimenti l'oggetto
    `DynamicSummaries` prodotto.
    """
    input_tags = _load_input_tags(input_file)
    if input_tags is None:
        return None
    if not input_tags:
        logger.error("Nessun tag presente in %s.", input_file)
        return None

    logger.info("Caricamento risorse...")
    risk_models, hierarchy, system_prompt = load_dynamic_summary_resources()

    return summarize_tags(
        layer=layer,
        input_tags=input_tags,
        system_prompt=system_prompt,
        hierarchy=hierarchy,
        risk_models=risk_models,
        model=model,
    )


# Internal helpers ------------------------------------------------------------


def _summarize_one(
    layer: Layer,
    group: GroupedTag,
    system_prompt: str,
    hierarchy: Hierarchy | None,
    risk_models: list[RiskModel] | None,
    model: str,
) -> tuple[DynamicTagSummary | None, float]:
    mo_desc, odc_desc = lookup_descriptions(hierarchy, group)
    rm_desc = lookup_rm_description(risk_models, group.risk_model) if risk_models else None
    return summarize_group(layer, group, system_prompt, model, mo_desc, odc_desc, rm_desc)


def _build_entry(
    group: GroupedTag, summary: DynamicTagSummary, hierarchy: Hierarchy | None = None
) -> DynamicSummaryEntry:
    risk_model = _rm_code_to_name(resolve_ambiente()).get(group.risk_model, group.risk_model)
    mo = group.mo
    odc = group.odc

    rm_hier = hierarchy.get_rm(risk_model) if hierarchy else None
    if rm_hier is not None:
        mo_obj = rm_hier.get_mo(extract_code(group.mo) or group.mo.strip())
        odc_obj = rm_hier.get_odc(extract_code(group.odc) or group.odc.strip())
        if mo_obj is not None:
            mo = mo_obj.label
        if odc_obj is not None:
            odc = odc_obj.label

    return DynamicSummaryEntry(
        risk_model=risk_model,
        mo=mo,
        odc=odc,
        ente=group.ente,
        n_estratti=len(group.estratti),
        estratti=list(group.estratti),
        analisi=summary,
    )


def _load_input_tags(input_file: Path) -> list[dict[str, Any]] | None:
    """Carica i tag dal file JSON. Accetta una lista o un oggetto `{"tags": [...]}`.

    Ritorna `None` (loggando l'errore) se il file manca o non è JSON valido nel
    formato atteso.
    """
    if not input_file.exists():
        logger.error("File di input non trovato: %s", input_file)
        return None
    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.exception("File di input %s non è JSON valido.", input_file)
        return None

    if isinstance(data, dict):
        data = data.get("tags", [])
    if not isinstance(data, list):
        logger.error("Formato input non valido in %s: attesa una lista di tag o {'tags': [...]}.", input_file)
        return None
    return [t for t in data if isinstance(t, dict)]
