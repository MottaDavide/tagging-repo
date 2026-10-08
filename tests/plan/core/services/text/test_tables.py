"""Test `core.services.text.tables`: enumerazione tabelle con id + risoluzione citazione→id."""

from __future__ import annotations

from core.services.text.tables import enumerate_tables, resolve_table_id, table_html_clean, table_text

_MD = (
    "[PAGE 1]\n"
    "<table><tr><td>Divisione BdT</td><td>9,4%</td></tr></table>\n"
    "testo tra le tabelle\n"
    "[PAGE 2]\n"
    "<table><tr><td>alpha uno</td></tr></table>\n"
    "<table><tr><td>beta due tre quattro cinque sei</td></tr></table>\n"
)


class TestEnumerateTables:
    def test_ids_and_pages(self) -> None:
        tables = enumerate_tables(_MD)
        assert [t.id for t in tables] == ["p1#1", "p2#1", "p2#2"]
        assert [t.page for t in tables] == [1, 2, 2]

    def test_ordinal_resets_per_page(self) -> None:
        tables = enumerate_tables(_MD)
        page2 = [t for t in tables if t.page == 2]
        assert [t.id for t in page2] == ["p2#1", "p2#2"]

    def test_no_tables(self) -> None:
        assert enumerate_tables("[PAGE 1]\nsolo testo, nessuna tabella") == []

    def test_table_before_any_page_marker(self) -> None:
        tables = enumerate_tables("<table><tr><td>x</td></tr></table>")
        assert tables[0].page is None
        assert tables[0].id == "p0#1"


class TestTableText:
    def test_strips_tags_and_markers(self) -> None:
        html = "<table><tr><td>«ENTE[BdT|Divisione BdT]»Divisione BdT</td></tr></table>"
        text = table_text(html)
        assert "divisione bdt" in text
        assert "«" not in text
        assert "<td>" not in text


class TestTableHtmlClean:
    def test_strips_markers_but_keeps_html(self) -> None:
        html = "<table><tr><td>«ENTE[BdT|Divisione BdT]»Divisione BdT</td><td>9,4%</td></tr></table>"
        clean = table_html_clean(html)
        assert clean == "<table><tr><td>Divisione BdT</td><td>9,4%</td></tr></table>"
        assert "«" not in clean
        assert "<table>" in clean

    def test_no_markers_unchanged(self) -> None:
        html = "<table><tr><td>x</td></tr></table>"
        assert table_html_clean(html) == html


class TestResolveTableId:
    def test_passthrough_when_already_id(self) -> None:
        assert resolve_table_id("p9#2", enumerate_tables(_MD)) == "p9#2"

    def test_resolves_html_row_to_table(self) -> None:
        tables = enumerate_tables(_MD)
        assert resolve_table_id("<tr><td>beta due tre quattro cinque sei</td></tr>", tables) == "p2#2"

    def test_unresolvable_returns_none(self) -> None:
        assert resolve_table_id("contenuto non presente in nessuna tabella", enumerate_tables(_MD)) is None

    def test_none_or_empty(self) -> None:
        tables = enumerate_tables(_MD)
        assert resolve_table_id(None, tables) is None
        assert resolve_table_id("", tables) is None
