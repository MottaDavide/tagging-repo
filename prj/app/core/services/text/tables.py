"""Enumerazione delle tabelle di un documento markdown con id stabile.

Ogni tabella HTML (``<table>…</table>``) riceve un id ``p{pagina}#{k}`` dove ``pagina`` è
il marker ``[PAGE N]`` che la precede e ``k`` l'indice 1-based tra le tabelle che iniziano
su quella pagina. L'ordine è quello di comparsa nel markdown (lettura top-down), quindi
deterministico e condiviso tra ground truth e output dell'algoritmo.

Riusabile sia a runtime (segmentazione: la tabella è un'unità candidata) sia offline per
assegnare l'id-tabella alle citazioni della GT / mappare citazioni HTML legacy a un id.
"""

import bisect
import re
from dataclasses import dataclass

from core.services.text.markdown import normalize_whitespace_lower

_RE_PAGE = re.compile(r"\[PAGE\s*(\d+)\]", re.IGNORECASE)
_RE_TABLE = re.compile(r"<table.*?</table>", re.IGNORECASE | re.DOTALL)
_RE_MARKER = re.compile(r"«[^»]*»")
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_ID = re.compile(r"^p\d+#\d+$")


def table_text(html: str) -> str:
    """Testo normalizzato di una tabella: senza marker ``«…»`` né tag HTML, whitespace collassato."""
    without_markers = _RE_MARKER.sub(" ", html)
    without_tags = _RE_HTML_TAG.sub(" ", without_markers)
    return normalize_whitespace_lower(without_tags)


def table_html_clean(html: str) -> str:
    """HTML della tabella ripulito dai marker di annotazione ``«…»``.

    Mantiene la struttura HTML (``<table>``/``<tr>``/``<td>``…) rimuovendo solo i marker
    ``«ENTE[…]»`` iniettati in fase di annotazione, così da esporre un ``<table>`` leggibile
    come contenuto integrale della tabella.
    """
    return _RE_MARKER.sub("", html).strip()


@dataclass(frozen=True)
class Table:
    """Una tabella del documento con id stabile e pagina di appartenenza."""

    id: str
    page: int | None
    html: str

    @property
    def text(self) -> str:
        return table_text(self.html)


def enumerate_tables(markdown: str) -> list[Table]:
    """Elenca le tabelle del markdown, in ordine di comparsa, con id ``p{pagina}#{k}``."""
    page_marks = [(m.start(), int(m.group(1))) for m in _RE_PAGE.finditer(markdown)]
    _starts = [s for s, _ in page_marks]

    def page_at(pos: int) -> int | None:
        i = bisect.bisect_right(_starts, pos) - 1
        return page_marks[i][1] if i >= 0 else None

    counter: dict[int | None, int] = {}
    tables: list[Table] = []
    for m in _RE_TABLE.finditer(markdown):
        page = page_at(m.start())
        counter[page] = counter.get(page, 0) + 1
        tables.append(Table(id=f"p{page if page is not None else 0}#{counter[page]}", page=page, html=m.group(0)))
    return tables


def resolve_table_id(citation: str | None, tables: list[Table]) -> str | None:
    """Riconduce una citazione a un id-tabella.

    Se `citation` è già un id (``p9#2``) lo ritorna. Altrimenti, se è una porzione di tabella
    (es. righe HTML copiate), individua la tabella il cui testo contiene un prefisso distintivo
    della citazione. Ritorna None se non riconducibile.
    """
    if not citation:
        return None
    stripped = citation.strip()
    if _RE_ID.match(stripped):
        return stripped
    probe = table_text(stripped)[:60]
    if not probe:
        return None
    for t in tables:
        if probe in t.text:
            return t.id
    return None
