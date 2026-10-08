"""Ricerca robusta di citazioni LLM nel documento sorgente.

Strategia in 6 livelli decrescenti di forza per tollerare discrepanze OCR /
unicode / whitespace / heading marker tra il testo del documento e l'ancora
emessa dall'LLM. La funzione preferisce sempre l'occorrenza più vicina alla
posizione dell'hint di pagina, per evitare di "saltare" sulla stessa stringa
ripetuta altrove (indici, header, slide copiate).
"""

import re

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.services.text.markdown import RE_PAGE_MARKER, normalize_for_matching

_CONFIG = get_obj_from_config_path("tagging.yaml")["text"]["anchor"]

_ANCHOR_WINDOW_CHARS: int = _CONFIG["window_chars"]  # ~2-3 pagine attorno all'hint
_PREFIX_LENGTHS: tuple[int, ...] = tuple(_CONFIG["prefix_lengths"])


def preprocess_anchor(anchor: str) -> str:
    """Rimuove artefatti LLM (heading `##`, marker `ENTE[...]`) prima della ricerca."""
    anchor = anchor.strip()
    anchor = re.sub(r"^#{1,6}\s+", "", anchor)
    anchor = re.sub(r"ENTE\[([^\]]+)\]", r"\1", anchor)
    return anchor.strip()


def _find_all_occurrences(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    out: list[int] = []
    start = 0
    while True:
        pos = text.find(needle, start)
        if pos == -1:
            break
        out.append(pos)
        start = pos + 1
    return out


def find_anchor_in_text(text: str, anchor: str, page_hint_pos: int = 0) -> int | None:
    """Cerca l'ancora nel testo scegliendo l'occorrenza più vicina all'hint di pagina.

    Strategie in ordine di forza decrescente:
      1. Match esatto.
      2. Case-insensitive.
      3. NFKC + whitespace + dash/virgolette normalizzati.
      4. Normalizzazione + case-insensitive.
      5. Prefisso `_PREFIX_LENGTHS` char, ristretto a una finestra attorno all'hint.
      6. Ancora pre-processata (strip heading, ENTE markers) → riapplica 1-5.
    """
    if not anchor or not anchor.strip():
        return None

    anchor = anchor.strip()

    def _pick_closest(positions: list[int]) -> int | None:
        if not positions:
            return None
        return min(positions, key=lambda p: abs(p - page_hint_pos))

    def _try_short_prefix(a: str) -> int | None:
        if page_hint_pos > 0:
            win_start = max(0, page_hint_pos - _ANCHOR_WINDOW_CHARS)
            win_end = min(len(text), page_hint_pos + _ANCHOR_WINDOW_CHARS)
            window = text[win_start:win_end]
            window_lower = window.lower()
            offset = win_start
        else:
            window, window_lower, offset = text, text.lower(), 0
        for length in _PREFIX_LENGTHS:
            if len(a) <= length:
                continue
            short = a[:length].strip()
            if not short:
                continue
            candidates = [offset + p for p in _find_all_occurrences(window, short)]
            candidates += [offset + p for p in _find_all_occurrences(window_lower, short.lower())]
            pos = _pick_closest(candidates)
            if pos is not None:
                return pos
        return None

    def _try_match(a: str) -> int | None:
        pos = _pick_closest(_find_all_occurrences(text, a))
        if pos is not None:
            return pos
        pos = _pick_closest(_find_all_occurrences(text.lower(), a.lower()))
        if pos is not None:
            return pos
        text_norm = normalize_for_matching(text)
        a_norm = normalize_for_matching(a)
        if a_norm:
            pos = _pick_closest(_find_all_occurrences(text_norm, a_norm))
            if pos is not None:
                return pos
            pos = _pick_closest(_find_all_occurrences(text_norm.lower(), a_norm.lower()))
            if pos is not None:
                return pos
        return _try_short_prefix(a)

    pos = _try_match(anchor)
    if pos is not None:
        return pos

    anchor_clean = preprocess_anchor(anchor)
    if anchor_clean and anchor_clean != anchor:
        pos = _try_match(anchor_clean)
        if pos is not None:
            return pos

    return None


def compute_page_range_from_position(
    doc_text: str,
    pos_start: int,
    brano: str,
    fallback_pagina: str,
) -> str:
    """Calcola il range pagine del brano dalla sua posizione assoluta nel documento."""
    if pos_start < 0:
        return fallback_pagina

    start_page: int | None = None
    for m in RE_PAGE_MARKER.finditer(doc_text):
        if m.start() <= pos_start:
            start_page = int(m.group(1))
        else:
            break

    if start_page is None:
        return fallback_pagina

    inner_pages = [int(m.group(1)) for m in RE_PAGE_MARKER.finditer(brano)]
    end_page = max(inner_pages) if inner_pages else start_page

    if start_page == end_page:
        return str(start_page)
    return ",".join(str(p) for p in range(start_page, end_page + 1))


def page_hint_to_pos(doc_text: str, pagina: str) -> int:
    """Converte la stringa pagina LLM in una posizione di riferimento nel documento.

    Ritorna la posizione del marker `[PAGE N]` corrispondente (o pagine adiacenti
    se la N indicata non esiste come marker). Usata da `find_anchor_in_text` per
    scegliere l'occorrenza più vicina.
    """
    if not pagina:
        return 0
    parts = re.split(r"[,\-–.;]", pagina)  # noqa: RUF001
    for part in parts:
        part = part.strip()
        if part.isdigit():
            page_n = int(part)
            for p in (page_n, page_n - 1, page_n + 1):
                if p < 1:
                    continue
                marker = f"[PAGE {p}]"
                pos = doc_text.find(marker)
                if pos != -1:
                    return pos
            break
    return 0
