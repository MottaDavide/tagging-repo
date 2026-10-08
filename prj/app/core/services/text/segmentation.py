"""Segmentazione del documento in unità candidate per il tagging.

Un'unità è la porzione minima che il classificatore valuta contro la gerarchia RM→MO→OdC.
Due tipi:

- ``section``: blocco di testo delimitato da heading e da salto pagina (``[PAGE N]``), con
  la pagina e il titolo di heading di contesto. Granularità scelta empiricamente sulla GT:
  copre il ~93% degli span di testo (containment ≥0.7), contro il ~39% della granularità a
  paragrafo (gli span attraversano più paragrafi ma restano dentro una sezione).
- ``table``: una tabella intera (via ``enumerate_tables``), con il suo id-tabella.

Il testo delle unità è ripulito dai marker ``«…»`` (enti/schede) e dai blocchi tabella
(gestiti come unità a sé), pronto per la classificazione e per essere emesso come citazione.
"""

import re

from core.models.tagging.units import Unit
from core.services.text.markdown import RE_ENTE_CANONICAL
from core.services.text.tables import enumerate_tables

_RE_PAGE = re.compile(r"^\[PAGE\s*(\d+)\]", re.IGNORECASE)
_RE_HEAD = re.compile(r"^#{1,6}\s+(.*)$")
_RE_MARKER = re.compile(r"«[^»]*»")
_RE_TABLE = re.compile(r"<table.*?</table>", re.IGNORECASE | re.DOTALL)


def _clean(lines: list[str]) -> str:
    joined = _RE_MARKER.sub(" ", " ".join(lines))
    return re.sub(r"\s+", " ", joined).strip()


def segment_document(markdown: str) -> list[Unit]:
    """Divide il markdown in unità: sezioni di testo (heading/pagina) + tabelle."""
    units: list[Unit] = []
    page: int | None = None
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        text = _clean(buf)
        if text:
            units.append(Unit(kind="section", text=text, page=page, heading=heading))
        buf = []

    for raw in _RE_TABLE.sub(" ", markdown).split("\n"):
        line = raw.strip()
        page_marker = _RE_PAGE.match(line)
        if page_marker:
            flush()
            page = int(page_marker.group(1))
            continue
        head = _RE_HEAD.match(line)
        if head:
            flush()
            heading = head.group(1).strip()
            continue
        if line:
            buf.append(line)
    flush()

    for table in enumerate_tables(markdown):
        entities = _distinct_entities(table.html)
        units.append(
            Unit(kind="table", text=table.text, page=table.page, heading="", table_id=table.id, entities=entities)
        )
    return units


def _distinct_entities(html: str) -> tuple[str, ...]:
    """Enti-riga canonici distinti in una tabella, in ordine di comparsa (dal marker soa)."""
    out: list[str] = []
    for m in RE_ENTE_CANONICAL.finditer(html):
        ente = m.group(1).strip()
        if ente not in out:
            out.append(ente)
    return tuple(out)
