"""Utility testuali per la pipeline di tagging.

API pubblica del sub-package, raggruppata per scopo:

  - Markdown parsing (pagine, heading, figure, tabelle).
  - Estrazione marker entità (`ENTE[…]`).
  - Normalizzazione testo per matching (`normalize_for_matching`).
  - Anchor resolution (`find_anchor_in_text`).
  - Conteggio token (`count_tokens`).
"""

from core.services.text.anchor import (
    compute_page_range_from_position,
    find_anchor_in_text,
    page_hint_to_pos,
    preprocess_anchor,
)
from core.services.text.markdown import (
    RE_ENTE_CANONICAL,
    RE_PAGE_MARKER,
    RE_PAGE_SPLIT,
    extract_enti_from_text,
    extract_title,
    find_figures_and_tables_by_page,
    is_chart_only_figure,
    iter_page_numbers,
    normalize_for_matching,
    normalize_whitespace_lower,
    remove_chart_figures,
    split_by_pages,
    strip_figure_tags,
)
from core.services.text.pages import parse_pages
from core.services.text.tokens import count_tokens

__all__ = [
    # markdown
    "RE_ENTE_CANONICAL",
    "RE_PAGE_MARKER",
    "RE_PAGE_SPLIT",
    "compute_page_range_from_position",
    "count_tokens",
    "extract_enti_from_text",
    "extract_title",
    "find_anchor_in_text",
    "find_figures_and_tables_by_page",
    "is_chart_only_figure",
    "iter_page_numbers",
    "normalize_for_matching",
    "normalize_whitespace_lower",
    "page_hint_to_pos",
    "parse_pages",
    "preprocess_anchor",
    "remove_chart_figures",
    "split_by_pages",
    "strip_figure_tags",
]
