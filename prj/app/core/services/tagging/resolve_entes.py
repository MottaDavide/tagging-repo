"""Stadio ente: assegna a ogni brano la/le struttura/e ANALIZZATA/CONTROLLATA.

Due regimi:
- **Span-tabella "di risultati per ente"** (≥2 enti-riga) → fan-out deterministico, un tag per
  ente-riga senza LLM (la tabella attribuisce il dato a ciascuna sotto-unità elencata).
- **Span-testo** → scelta ancorata al POOL LOCALE (marker ENTE della pagina + enti di sezione +
  titolare), non all'intero catalogo: offrirlo tutto faceva driftare l'LLM su default ad alto
  livello (Divisione BdT / Gruppo ISP) assenti dalla pagina. Pool vuoto → nessun ente; singolo →
  deterministico; multiplo → l'LLM sceglie tra i soli candidati (fallback titolare).

L'ente è emesso in forma canonica (enum) quando possibile. Selezione LLM parallela per gruppo.
"""

import copy
import logging
import re
from collections import OrderedDict
from functools import lru_cache, partial
from typing import Literal

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from pydantic import Field, create_model

from core.models.tagging.candidates import BranoCandidate, EnteAppearance
from core.models.tagging.stages import EnteSelection
from core.models.tagging.stats import TaggerStats
from core.resources.ente_system import ENTE_SYSTEM
from core.services.llm_client import Layer, call_llm_timed
from core.services.registry.enti import ENTI_VALUES, ente_name_key
from core.services.tagging._parallel import parallel_llm_map
from core.services.tagging.discover import TABLE_MIN_ENTITIES
from core.services.tagging.document_analysis import build_ente_metadata, parse_doc_structure

logger = logging.getLogger(__name__)

ENTE_MAX_TOKENS: int = get_obj_from_config_path("llm.yaml")["calls"]["resolve_entes"]["max_tokens"]


@lru_cache(maxsize=256)
def _dynamic_ente_selection(pool: tuple[str, ...]) -> type[EnteSelection]:
    return create_model(
        "DynamicEnteSelection",
        __base__=EnteSelection,
        enti=(
            list[Literal[pool]],  # type: ignore[valid-type]  # Literal da tupla nota solo a runtime
            Field(default_factory=list, description=EnteSelection.model_fields["enti"].description),
        ),
    )


TABLE_ROSTER_MIN_ENTITIES = TABLE_MIN_ENTITIES
ENTE_REASONING: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "medium"

_GENERIC_UNLESS_LOCAL = frozenset({ente_name_key("Gruppo ISP")})
_CONTROLLER_TERMS: list[str] = get_obj_from_config_path("tagging.yaml")["resolve_entes"]["disfavored_controller_terms"]
_RE_CONTROLLER = re.compile("|".join(_CONTROLLER_TERMS), re.IGNORECASE)


def _is_disfavored(ente: str) -> bool:
    """Ente da emettere solo se ancorato localmente: generico di comodo o funzione di controllo."""
    return ente_name_key(ente) in _GENERIC_UNLESS_LOCAL or bool(_RE_CONTROLLER.search(ente))


_GroupKey = tuple[str, tuple[int, ...]]
_SectionIndex = list[tuple[int, list[str]]]


def _table_roster_entities(cand: BranoCandidate) -> list[str] | None:
    """Enti-riga per il fan-out deterministico di un candidato-tabella, o `None` se non applicabile.

    Applicabile solo agli span-tabella con ≥ `TABLE_ROSTER_MIN_ENTITIES` enti-riga distinti; ritorna
    i nomi deduplicati per chiave canonica (preservando l'ordine), così che l'emissione a valle non
    generi tag doppi per varianti dello stesso ente. Sotto soglia / non-tabella → `None` (pool LLM).
    """
    if cand.tipo_citazione != "table" or len(cand.table_entities) < TABLE_ROSTER_MIN_ENTITIES:
        return None
    seen: set[str | None] = set()
    roster: list[str] = []
    for ente in cand.table_entities:
        canonical = ente_name_key(ente)
        if canonical not in seen:
            seen.add(canonical)
            roster.append(ente)
    return roster if len(roster) >= TABLE_ROSTER_MIN_ENTITIES else None


def _drop_ungrounded_disfavored(cands: list[BranoCandidate], page_enti: dict[int, list[str]]) -> list[BranoCandidate]:
    """Rimuove i tag con ente sfavorito (generico o controllore) NON marcato sulle pagine del brano.

    Ancoraggio via marker: la citazione salvata è ripulita dai nomi canonici, quindi si verifica la
    presenza locale dell'ente tra i marker `ENTE` delle pagine dello span (non una sottostringa)."""
    page_keys_cache: dict[int, set[str | None]] = {
        pg: {ente_name_key(e) for e in enti} for pg, enti in page_enti.items()
    }
    out: list[BranoCandidate] = []
    for cand in cands:
        if cand.ente and _is_disfavored(cand.ente):
            local_keys = {k for pg in _pages(cand.pagina) for k in page_keys_cache.get(pg, set())}
            if ente_name_key(cand.ente) not in local_keys:
                continue
        out.append(cand)
    return out


def _pages(pagina: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", pagina or ""))


def _emit_ente(raw: str) -> str:
    """Forma canonica (valore enum) se riconducibile, altrimenti la stringa grezza."""
    canonical = ente_name_key(raw)
    return canonical if canonical in ENTI_VALUES else raw


def _titular(ente_metadata: dict[str, EnteAppearance]) -> str | None:
    """Ente titolare del documento: preferisci la copertina, poi la frequenza."""
    cover = [a for a in ente_metadata.values() if a.in_cover]
    pool = cover or list(ente_metadata.values())
    if not pool:
        return None
    return max(pool, key=lambda a: (a.in_cover, a.n_mentions, -a.first_page)).canonical


def _section_index(section_enti_list: list[tuple[int, str, int, list[str]]]) -> _SectionIndex:
    """Sezioni (con enti) ordinate per pagina d'inizio, per l'ereditarietà dei brani su pagine senza marker."""
    return sorted(((pg, enti) for _lvl, _ht, pg, enti in section_enti_list if enti), key=lambda x: x[0])


def _inherited_enti(page: int, sections: _SectionIndex) -> list[str]:
    """Enti della sezione più vicina che precede (o inizia su) la pagina del brano."""
    best: list[str] = []
    for start_page, enti in sections:
        if start_page <= page:
            best = enti
        else:
            break
    return best


def _local_pool(
    pages: tuple[int, ...],
    page_enti: dict[int, list[str]],
    sections: _SectionIndex,
    titular: str | None,
) -> list[str]:
    """Candidati per il brano: marker di pagina, poi ereditarietà di sezione se la pagina è muta, poi titolare."""
    pool: list[str] = []
    for pg in pages:
        for ente in page_enti.get(pg, []):
            if ente not in pool:
                pool.append(ente)
    if not pool and pages:
        for ente in _inherited_enti(min(pages), sections):
            if ente not in pool:
                pool.append(ente)
    if titular and titular not in pool:
        pool.append(titular)
    return pool


def _candidate_block(
    pool: list[str],
    on_page_keys: set[str | None],
    titular: str | None,
    ente_metadata: dict[str, EnteAppearance],
) -> str:
    """Righe delle strutture candidate, con contesto (pagina, titolare, copertina, sezione)."""
    lines: list[str] = []
    for ente in pool:
        flags: list[str] = []
        if ente_name_key(ente) in on_page_keys:
            flags.append("citata su questa pagina")
        if ente == titular:
            flags.append("struttura titolare del documento")
        app = ente_metadata.get(ente)
        if app:
            if app.in_cover:
                flags.append("copertina")
            heads = app.h1_headings or app.h2_headings
            if heads:
                flags.append(f"sezione «{heads[0][:50]}»")
        suffix = ("  [" + " · ".join(flags) + "]") if flags else ""
        lines.append(f"- «{ente}»{suffix}")
    return "\n".join(lines)


def _select_for_group(
    layer: Layer,
    key: _GroupKey,
    pool: list[str],
    page_enti: dict[int, list[str]],
    ente_metadata: dict[str, EnteAppearance],
    titular: str | None,
    model: str,
) -> tuple[_GroupKey, list[str], float]:
    """Pool multiplo (≥2 candidati): l'LLM sceglie tra i soli candidati locali.

    Selezione vuota/fallita → fallback titolare. Ritorna `(key, enti_selezionati, elapsed)`.
    """
    brano, pages = key
    on_page_keys: set[str | None] = {ente_name_key(e) for pg in pages for e in page_enti.get(pg, [])}
    pages_str = ",".join(str(p) for p in pages) or "n/d"
    user_msg = (
        f"## BRANO (pagina/e {pages_str})\n\n{brano}\n\n"
        f"## STRUTTURE CANDIDATE\n{_candidate_block(pool, on_page_keys, titular, ente_metadata)}"
    )
    response_format = _dynamic_ente_selection(tuple(pool))
    result, elapsed = call_llm_timed(
        layer, ENTE_SYSTEM, user_msg, response_format, ENTE_MAX_TOKENS, model, reasoning_effort=ENTE_REASONING
    )
    if result is None:
        return key, ([titular] if titular else []), elapsed

    pool_keys: dict[str | None, str] = {ente_name_key(e): e for e in pool}
    selected: list[str] = []
    for raw in result.enti:
        canonical = pool_keys.get(ente_name_key(raw))
        if canonical is not None and canonical not in selected:
            selected.append(canonical)
    if not selected:
        selected = [titular] if titular else []
    return key, selected, elapsed


def resolve_entes(
    layer: Layer,
    candidates: list[BranoCandidate],
    doc_text: str,
    model: str,
    stats: TaggerStats,
) -> list[BranoCandidate]:
    """Assegna l'ente (fan-out) scegliendo dal pool locale del brano (pagina/sezione + titolare)."""
    if not candidates:
        return candidates

    page_enti, section_enti_list = parse_doc_structure(doc_text)
    ente_metadata = build_ente_metadata(doc_text, page_enti, section_enti_list)
    if not ente_metadata:
        stats.n_tags_no_ente = len(candidates)
        return candidates

    sections = _section_index(section_enti_list)
    titular = _titular(ente_metadata)

    groups: OrderedDict[_GroupKey, list[BranoCandidate]] = OrderedDict()
    for cand in candidates:
        groups.setdefault((cand.brano, _pages(cand.pagina)), []).append(cand)

    selections: dict[_GroupKey, list[str]] = {}
    llm_pools: list[tuple[_GroupKey, list[str]]] = []
    for key, group in groups.items():
        roster = _table_roster_entities(group[0])
        if roster is not None:
            selections[key] = roster
            continue
        _brano, pages = key
        pool = _local_pool(pages, page_enti, sections, titular)
        if len(pool) <= 1:
            selections[key] = pool
        else:
            llm_pools.append((key, pool))

    tasks = [
        partial(_select_for_group, layer, key, pool, page_enti, ente_metadata, titular, model)
        for key, pool in llm_pools
    ]
    selections.update(parallel_llm_map(tasks, stats))

    final: list[BranoCandidate] = []
    for key, group in groups.items():
        selected = selections.get(key) or ([titular] if titular else [])
        for cand in group:
            if not selected:
                final.append(cand)
                continue
            for raw in selected:
                copied = copy.copy(cand)
                copied.ente = _emit_ente(raw)
                final.append(copied)

    n_before = len(final)
    final = _drop_ungrounded_disfavored(final, page_enti)
    if len(final) < n_before:
        logger.info(
            "  ente: rimossi %d tag con ente sfavorito non ancorato (generico/controllore)", n_before - len(final)
        )
    stats.n_tags_no_ente = sum(1 for c in final if c.ente is None)
    logger.info("  ente: %d tag dopo fan-out (%d senza ente)", len(final), stats.n_tags_no_ente)
    return final
