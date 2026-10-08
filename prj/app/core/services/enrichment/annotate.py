"""Stage 4: annotazione marker `«ENTE[ente_raw|canonical]»` nei documenti.

Pipeline deterministica (no LLM): legge il dizionario degli enti estratti per
documento (output del modulo entity_extraction) e inserisce nei file markdown
i marker `«ENTE[…]»` in corrispondenza delle menzioni testuali.

Per ogni pagina:
  1. Canonicalizzazione delle entity_key contro l'enum `Enti`.
  2. Normalizzazione delle citazioni (assorbimento di varianti più corte).
  3. Mappa citazione → enti (con merge di citazioni che sono sottostringhe).
  4. Inserimento marker risolvendo overlap (preferenza al match più lungo).
"""

import json
import logging
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.config import ANNOTATED_WITH_DESC_DIR, CLEAN_WITH_DESC_DIR, ENTI_ESTRATTI_JSON
from core.services.registry.enti import ENTI_VALUES, canonical_ente_key
from core.services.text.markdown import RE_PAGE_SPLIT

logger = logging.getLogger(__name__)


_CITATION_SIMILARITY_THRESHOLD: float = get_obj_from_config_path("tagging.yaml")["annotate"][
    "citation_similarity_threshold"
]


# Canonicalizzazione entity_key (resilienza a JSON sporchi) ----------------


def _canonicalize_page_entities(page_entities: dict[str, Any], doc_name: str, page_key: str) -> dict[str, Any]:
    """Normalizza le `entity_key` contro l'enum `Enti`.

    - chiave già canonica → invariata
    - chiave canonicalizzabile (strip codice + EM → match enum) → rimpiazzata
    - chiave non riconducibile → entry scartata con WARNING

    Collisioni (più chiavi raw che mappano sullo stesso canonical) → entries
    unite concatenando `citazione` e `ente_raw` come liste.
    """
    if not page_entities:
        return page_entities

    canonical_entities: dict[str, Any] = {}
    for raw_key, data in page_entities.items():
        canonical = canonical_ente_key(raw_key)
        if canonical is None:
            logger.warning(
                "[%s][%s] entity_key non canonicalizzabile, skip: %r",
                doc_name,
                page_key,
                raw_key,
            )
            continue

        if canonical not in canonical_entities:
            canonical_entities[canonical] = dict(data)
            continue

        existing = canonical_entities[canonical]
        for field_name in ("citazione", "ente_raw"):
            ev = existing.get(field_name, "")
            nv = data.get(field_name, "")
            el = ev if isinstance(ev, list) else [ev]
            nl = nv if isinstance(nv, list) else [nv]
            existing[field_name] = [v for v in (el + nl) if v]

    return canonical_entities


# Normalizzazione citazioni (assorbimento varianti più corte) -------------


def _similarity_ratio(text_a: str, text_b: str) -> float:
    if not text_a or not text_b:
        return 0.0
    norm_a = " ".join(text_a.split())
    norm_b = " ".join(text_b.split())
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _flatten_citations(page_entities: dict[str, Any]) -> list[tuple[str, int | None, str]]:
    flat: list[tuple[str, int | None, str]] = []
    for entity_key, data in page_entities.items():
        citation = data.get("citazione", "")
        if isinstance(citation, list):
            for i, t in enumerate(citation):
                flat.append((entity_key, i, t))
        else:
            flat.append((entity_key, None, citation))
    return flat


def _group_similar_citations(flat: list[Any], threshold: float) -> dict[int, str]:
    """Per ogni citazione, sceglie la versione canonica (la più lunga fra le simili)."""
    texts = [t for _, _, t in flat]
    canonical: dict[int, str] = {}
    for i, ti in enumerate(texts):
        canonical[i] = max(
            (tj for j, tj in enumerate(texts) if _similarity_ratio(ti, tj) >= threshold),
            key=lambda t: len(t.strip()),
            default=ti,
        )
    return canonical


def _normalize_citations_for_page(
    page_entities: dict[str, Any], threshold: float = _CITATION_SIMILARITY_THRESHOLD
) -> dict[str, Any]:
    """Sostituisce citazioni parziali con la versione canonica più lunga."""
    flat = _flatten_citations(page_entities)
    if not flat:
        return page_entities

    canonical_per_idx = _group_similar_citations(flat, threshold)
    lookup: dict[tuple[str, int | None], str] = {
        (entity_key, idx): canonical_per_idx[i] for i, (entity_key, idx, _) in enumerate(flat)
    }

    out: dict[str, Any] = {}
    for entity_key, data in page_entities.items():
        new_data = dict(data)
        citation = data.get("citazione", "")
        if isinstance(citation, list):
            new_data["citazione"] = [lookup.get((entity_key, idx), t) for idx, t in enumerate(citation)]
        else:
            new_data["citazione"] = lookup.get((entity_key, None), citation)
        out[entity_key] = new_data
    return out


# Mappa citazione → enti ---------------------------------------------------


def _collect_citations_from_entities(
    page_entities: dict[str, Any],
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, int]]:
    citation_map: dict[str, list[tuple[str, str]]] = {}
    occurrence: dict[str, int] = {}

    for entity_key, data in page_entities.items():
        citation = data.get("citazione", "")
        ente_raw = data.get("ente_raw", "")
        cit_list = citation if isinstance(citation, list) else [citation]
        raw_list = ente_raw if isinstance(ente_raw, list) else [ente_raw]

        if len(cit_list) == len(raw_list):
            pairs: list[tuple[str, str]] = list(zip(cit_list, raw_list, strict=False))
        elif len(raw_list) > len(cit_list):
            unique_raws = list(dict.fromkeys(r for r in raw_list if r))
            pairs = [(c, r) for c in cit_list if c for r in unique_raws if r]
        else:
            unique_raws = list(dict.fromkeys(r for r in raw_list if r))
            if len(unique_raws) == 1:
                pairs = [(c, unique_raws[0]) for c in cit_list if c]
            else:
                logger.warning(
                    "entity_key %r: citazione (%d) > ente_raw (%d) con valori non uniformi, truncato.",
                    entity_key,
                    len(cit_list),
                    len(raw_list),
                )
                pairs = list(zip(cit_list, raw_list, strict=False))

        for c, r in pairs:
            if not c or not r:
                continue
            citation_map.setdefault(c, [])
            occurrence[c] = occurrence.get(c, 0) + 1
            if (r, entity_key) not in citation_map[c]:
                citation_map[c].append((r, entity_key))
    return citation_map, occurrence


def _merge_shorter_citations_into_longer(
    citation_map: dict[str, list[tuple[str, str]]],
    occurrence: dict[str, int],
) -> None:
    """In-place merge: citazioni corte (sottostringa di una più lunga) assorbite."""
    longest_first = sorted(citation_map.keys(), key=len, reverse=True)
    merged: set[str] = set()

    for i, long_c in enumerate(longest_first):
        long_norm = " ".join(long_c.split())
        for short_c in longest_first[i + 1 :]:
            if short_c in merged:
                continue
            if " ".join(short_c.split()) in long_norm:
                for pair in citation_map[short_c]:
                    if pair not in citation_map[long_c]:
                        citation_map[long_c].append(pair)
                merged.add(short_c)

    for c in merged:
        citation_map.pop(c, None)
        occurrence.pop(c, None)


def _build_citation_to_entities_map(
    page_entities: dict[str, Any],
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, int]]:
    citation_map, occurrence = _collect_citations_from_entities(page_entities)
    _merge_shorter_citations_into_longer(citation_map, occurrence)
    return citation_map, occurrence


# Inserimento marker -------------------------------------------------------


def _annotate_citation(citation_text: str, entity_pairs: list[tuple[str, str]]) -> str:
    """Sostituisce ogni occorrenza di `ente_raw` con `«ENTE[ente_raw|entity_key]»`.

    Span overlapping risolti a favore del più lungo (a parità di lunghezza,
    il più a sinistra). Span con `entity_key` non in `ENTI_VALUES` vengono
    saltati con WARNING (invariante garantita da `_canonicalize_page_entities`).
    """
    if not entity_pairs:
        return citation_text

    candidates: list[tuple[int, int, str, str]] = []
    for ente_raw, entity_key in entity_pairs:
        if not ente_raw:
            continue
        for m in re.finditer(re.escape(ente_raw), citation_text):
            candidates.append((m.start(), m.end(), ente_raw, entity_key))

    if not candidates:
        return citation_text

    candidates.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    selected: list[tuple[int, int, str, str]] = []
    for start, end, ente_raw, entity_key in candidates:
        if not any(not (end <= ss or start >= se) for ss, se, _, _ in selected):
            selected.append((start, end, ente_raw, entity_key))

    selected.sort(key=lambda s: s[0])
    parts: list[str] = []
    cursor = 0
    for start, end, ente_raw, entity_key in selected:
        if entity_key not in ENTI_VALUES:
            logger.warning("entity_key %r non in ENTI_VALUES, skip span", entity_key)
            continue
        parts.append(citation_text[cursor:start])
        parts.append(f"«ENTE[{ente_raw}|{entity_key}]»")
        cursor = end
    parts.append(citation_text[cursor:])
    return "".join(parts)


def _make_flexible_pattern(text: str) -> str:
    """Pattern regex che tollera differenze di whitespace.

    Le citazioni nel JSON sono spesso su una riga sola, mentre nel markdown
    possono essere multi-riga. Convertiamo ogni run di whitespace escapato
    in `\\s+` per renderle equivalenti.
    """
    escaped = re.escape(text)
    return re.sub(r"((?:\\ |\\\n|\\\t|\\\r)+)", r"\\s+", escaped)


def _annotate_page(
    page_text: str,
    page_entities: dict[str, Any],
    doc_name: str,
    page_key: str,
) -> str:
    """Annota tutte le menzioni di ente in una pagina markdown."""
    if not page_entities:
        return page_text

    canonicalized = _canonicalize_page_entities(page_entities, doc_name, page_key)
    if not canonicalized:
        return page_text

    normalized = _normalize_citations_for_page(canonicalized)
    citation_map, occurrence = _build_citation_to_entities_map(normalized)

    annotated = page_text
    for citation_text, pairs in sorted(citation_map.items(), key=lambda x: len(x[0]), reverse=True):
        annotated_citation = _annotate_citation(citation_text, pairs)
        if annotated_citation == citation_text:
            continue

        flexible = _make_flexible_pattern(citation_text)
        n = occurrence.get(citation_text, 1)
        try:
            annotated = re.sub(flexible, annotated_citation, annotated, count=n)
        except re.error:
            for _ in range(n):
                annotated = annotated.replace(citation_text, annotated_citation, 1)

    return annotated


# Document + batch --------------------------------------------------------


def annotate_document(md_path: Path, all_entities: dict[str, Any], run_id: str | None = None) -> str:
    """Annota un singolo documento markdown. Ritorna il contenuto annotato."""
    doc_name = md_path.stem
    md_content = md_path.read_text(encoding="utf-8")

    page_matches = RE_PAGE_SPLIT.findall(md_content)
    if not page_matches:
        logger.info("[run_id=%s][%s] Nessun marker [PAGE N] trovato; restituisco invariato.", run_id, doc_name)
        return md_content

    doc_entities = all_entities.get("entity_extracted", {})

    annotated_pages: list[str] = []
    for page_n, page_text in page_matches:
        page_key = f"pag_{int(page_n)}"
        page_entities = doc_entities.get(page_key, {})
        annotated = _annotate_page(page_text.strip(), page_entities, doc_name, page_key)
        annotated_pages.append(f"[PAGE {page_n}]\n{annotated}")
        logger.debug("[run_id=%s][%s][%s] annotato.", run_id, doc_name, page_key)

    return "\n\n".join(annotated_pages)


def run_batch(
    input_dir: Path = CLEAN_WITH_DESC_DIR,
    output_dir: Path = ANNOTATED_WITH_DESC_DIR,
    entities_path: Path = ENTI_ESTRATTI_JSON,
    single_file: str | None = None,
    force: bool = False,
) -> None:
    """Annota tutti i `.md` in `input_dir`."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if not entities_path.exists():
        logger.error("File enti estratti non trovato: %s", entities_path)
        sys.exit(1)
    all_entities = json.loads(entities_path.read_text(encoding="utf-8"))
    logger.info("Caricati enti per %d documenti.", len(all_entities))

    if single_file:
        md_paths = [input_dir / single_file]
        if not md_paths[0].exists():
            md_paths = [input_dir / f"{Path(single_file).stem}.md"]
    else:
        md_paths = sorted(input_dir.glob("*.md"))

    if not md_paths:
        logger.error(
            "Nessun documento trovato in %s. Esegui prima `pipeline.img_table` "
            "per produrre i file in clean-with-description-documents/.",
            input_dir,
        )
        return

    def _has_entities(p: Path) -> bool:
        stem = p.stem
        return bool(all_entities.get(f"{stem}.pdf") or all_entities.get(stem))

    before = len(md_paths)
    md_paths = [p for p in md_paths if _has_entities(p)]
    skipped = before - len(md_paths)
    if skipped:
        logger.info("Saltati %d documenti senza enti estratti.", skipped)

    if not md_paths:
        logger.info("Nessun documento con enti estratti da annotare.")
        return

    if not force:
        md_paths = [p for p in md_paths if not (output_dir / p.name).exists()]

    logger.info("Documenti da annotare: %d", len(md_paths))

    t0 = time.time()
    n_ok = 0
    for md_path in md_paths:
        try:
            doc_entities = all_entities.get(f"{md_path.stem}.pdf") or all_entities.get(md_path.stem, {})
            result = annotate_document(md_path, doc_entities)
            out_path = output_dir / md_path.name
            out_path.write_text(result, encoding="utf-8")
            logger.info("  Salvato: %s", out_path.name)
            n_ok += 1
        except Exception:
            logger.exception("[%s] ERRORE", md_path.name)

    logger.info("\nCompletato: %d/%d in %.1fs", n_ok, len(md_paths), time.time() - t0)
