"""Test `core.services.text.segmentation`: unità sezione/tabella con pagina e heading."""

from __future__ import annotations

from core.models.tagging.units import Unit
from core.services.text.segmentation import segment_document

_MD = (
    "[PAGE 1]\n"
    "intro prima di ogni heading\n"
    "# Titolo A\n"
    "riga uno di A\n"
    "riga due con «ENTE[x|Divisione BdT]»Divisione BdT dentro\n"
    "## Sotto B\n"
    "contenuto di B\n"
    "[PAGE 2]\n"
    "contenuto di B su pagina 2\n"
    "<table><tr><td>cella tabella</td></tr></table>\n"
)


def _sections(units: list[Unit]) -> list[Unit]:
    return [u for u in units if u.kind == "section"]


class TestSegmentDocument:
    def test_splits_on_heading_and_page(self) -> None:
        secs = _sections(segment_document(_MD))
        # intro / Titolo A / Sotto B (pag1) / Sotto B (pag2)
        assert [(s.page, s.heading) for s in secs] == [
            (1, ""),
            (1, "Titolo A"),
            (1, "Sotto B"),
            (2, "Sotto B"),
        ]

    def test_strips_markers_keeps_visible_text(self) -> None:
        sec_a = next(s for s in _sections(segment_document(_MD)) if s.heading == "Titolo A")
        assert "«" not in sec_a.text
        assert "Divisione BdT dentro" in sec_a.text

    def test_page_break_starts_new_section_same_heading(self) -> None:
        secs = [s for s in _sections(segment_document(_MD)) if s.heading == "Sotto B"]
        assert {s.page for s in secs} == {1, 2}

    def test_tables_become_units_with_id(self) -> None:
        tables = [u for u in segment_document(_MD) if u.kind == "table"]
        assert len(tables) == 1
        assert tables[0].table_id == "p2#1"
        assert tables[0].page == 2
        assert "cella tabella" in tables[0].text
        assert tables[0].n_entities == 0  # nessun marker ente nella tabella

    def test_table_counts_row_entities(self) -> None:
        md = (
            "[PAGE 1]\n<table><tr><td>«ENTE[a|Divisione BdT]» 9,4%</td></tr>"
            "<tr><td>«ENTE[b|Divisione CIB]» 3,1%</td></tr></table>\n"
        )
        tables = [u for u in segment_document(md) if u.kind == "table"]
        assert tables[0].n_entities == 2
        # gli enti-riga distinti sono conservati (ordine di comparsa) per il fan-out deterministico
        assert tables[0].entities == ("Divisione BdT", "Divisione CIB")

    def test_table_entities_dedup_preserves_order(self) -> None:
        md = (
            "[PAGE 1]\n<table>"
            "<tr><td>«ENTE[a|Divisione CIB]» x</td></tr>"
            "<tr><td>«ENTE[b|Divisione BdT]» y</td></tr>"
            "<tr><td>«ENTE[c|Divisione CIB]» z</td></tr></table>\n"
        )
        tables = [u for u in segment_document(md) if u.kind == "table"]
        assert tables[0].entities == ("Divisione CIB", "Divisione BdT")

    def test_content_before_first_heading(self) -> None:
        first = _sections(segment_document(_MD))[0]
        assert first.heading == ""
        assert "intro" in first.text

    def test_empty_document(self) -> None:
        assert segment_document("") == []
