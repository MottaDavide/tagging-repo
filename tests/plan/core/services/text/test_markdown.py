"""Test `core.services.text.markdown`: parsing, normalizzazione, helpers HTML."""

from __future__ import annotations

from core.services.text.markdown import (
    RE_PAGE_MARKER,
    RE_PAGE_SPLIT,
    clean_html_cell,
    extract_enti_from_text,
    extract_first_page,
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


class TestExtractTitle:
    def test_returns_h1_when_present(self) -> None:
        assert extract_title("# Titolo principale\nresto") == "Titolo principale"

    def test_returns_placeholder_when_missing(self) -> None:
        assert extract_title("nessun heading") == "(senza titolo)"

    def test_returns_first_h1(self) -> None:
        assert extract_title("# Primo\n# Secondo") == "Primo"


class TestExtractFirstPage:
    def test_without_page_markers_returns_initial_chunk(self) -> None:
        assert extract_first_page("Prima pagina\nSeconda riga") == "Prima pagina\nSeconda riga"

    def test_text_before_first_marker_is_treated_as_first_page(self) -> None:
        md = "Copertina\nData\n[PAGE 2]\nCorpo"
        assert extract_first_page(md) == "Copertina\nData"

    def test_extracts_page_1_until_page_2(self) -> None:
        md = "[PAGE 1]\nPrima\n[PAGE 2]\nSeconda"
        assert extract_first_page(md) == "[PAGE 1]\nPrima"

    def test_fallback_uses_first_marker_until_next_marker(self) -> None:
        md = "[PAGE 7]\nPrima logica\n[PAGE 8]\nSeconda"
        assert extract_first_page(md) == "[PAGE 7]\nPrima logica"


class TestSplitByPages:
    def test_no_pages(self) -> None:
        assert split_by_pages("plain text") == []

    def test_single_page(self) -> None:
        assert split_by_pages("[PAGE 1]\nA") == [(1, "\nA")]

    def test_multiple_pages(self) -> None:
        md = "[PAGE 1]\nAlfa\n[PAGE 2]\nBeta\n[PAGE 5]\nGamma"
        pages = split_by_pages(md)
        nums = [n for n, _ in pages]
        assert nums == [1, 2, 5]
        assert pages[1][1] == "\nBeta\n"


class TestIterPageNumbers:
    def test_in_order(self) -> None:
        md = "[PAGE 1]\n[PAGE 2]\n[PAGE 7]"
        assert iter_page_numbers(md) == [1, 2, 7]

    def test_empty(self) -> None:
        assert iter_page_numbers("nothing") == []


class TestExtractEntiFromText:
    def test_simple_marker(self) -> None:
        assert extract_enti_from_text("foo ENTE[Gruppo ISP] bar") == ["Gruppo ISP"]

    def test_marker_with_pipe(self) -> None:
        assert extract_enti_from_text("foo ENTE[display text|Gruppo ISP] bar") == ["Gruppo ISP"]

    def test_multiple_markers_deduplicated_and_sorted(self) -> None:
        text = "ENTE[Banca X] ENTE[Banca A] ENTE[Banca X] ENTE[Banca M]"
        assert extract_enti_from_text(text) == ["Banca A", "Banca M", "Banca X"]

    def test_no_marker(self) -> None:
        assert extract_enti_from_text("plain text") == []


class TestNormaliseForMatching:
    def test_unicode_nfkc(self) -> None:
        # smart quotes U+2019 / U+2018 → apostrofo dritto
        out = normalize_for_matching("L’analisi")  # noqa: RUF001
        assert "'" in out
        assert "’" not in out  # noqa: RUF001

    def test_collapse_horizontal_whitespace(self) -> None:
        assert normalize_for_matching("foo    bar") == "foo bar"

    def test_dash_normalization(self) -> None:
        # EN DASH e EM DASH → -
        out = normalize_for_matching("foo – bar — baz")  # noqa: RUF001
        assert "–" not in out  # noqa: RUF001
        assert "—" not in out
        assert out.count("-") == 2

    def test_smart_quotes_normalized(self) -> None:
        out = normalize_for_matching("“foo” «bar»")
        assert '"foo"' in out
        assert '"bar"' in out


class TestNormalizeWhitespaceLower:
    def test_lowercase_and_collapse(self) -> None:
        assert normalize_whitespace_lower("FOO   Bar\tBAZ") == "foo bar baz"


class TestCleanHtmlCell:
    def test_strip_tags_collapse_whitespace(self) -> None:
        assert clean_html_cell("<b>foo</b>  <i>bar</i>") == "foo bar"

    def test_empty(self) -> None:
        assert clean_html_cell("") == ""


class TestIsChartOnlyFigure:
    def test_empty_is_chart_only(self) -> None:
        assert is_chart_only_figure("") is True

    def test_numeric_only_is_chart(self) -> None:
        assert is_chart_only_figure("12 34 56 78 1.2% 3.4%") is True

    def test_prose_is_not_chart(self) -> None:
        prose = "Questa figura mostra il flusso del processo. Le fasi sono descritte dettagliatamente."
        assert is_chart_only_figure(prose) is False

    def test_figcaption_stripped_before_decision(self) -> None:
        # La figcaption non deve "salvare" una figura altrimenti chart-only
        assert is_chart_only_figure("<figcaption>Grafico A</figcaption>12 34 56") is True


class TestRemoveChartFigures:
    def test_chart_only_figure_removed(self) -> None:
        md = "before <figure>12 34 56 78</figure> after"
        assert "12 34" not in remove_chart_figures(md)

    def test_prose_figure_preserved(self) -> None:
        # 2 "frasi" (sequenze di ≥3 parole >=3 lettere) separate da punto:
        # la regex sentence-detector richiede len(sentences) >= 2.
        md = (
            "<figure>"
            "Questa figura mostra il flusso completo dei processi aziendali principali. "
            "Inoltre dettaglia ulteriori aspetti operativi rilevanti."
            "</figure>"
        )
        assert "figura mostra il flusso" in remove_chart_figures(md)

    def test_chart_figure_with_significant_caption_replaced_with_marker(self) -> None:
        md = "<figure><figcaption>Titolo importante del grafico</figcaption>12 34</figure>"
        out = remove_chart_figures(md)
        assert "[Grafico:" in out
        assert "Titolo importante del grafico" in out


class TestStripFigureTags:
    def test_strips_figure_tags(self) -> None:
        md = "<figure>X</figure>"
        out = strip_figure_tags(md)
        assert "<figure>" not in out
        assert "</figure>" not in out
        assert "X" in out

    def test_figcaption_becomes_bold(self) -> None:
        md = "<figure><figcaption>Titolo</figcaption>Y</figure>"
        out = strip_figure_tags(md)
        assert "**Titolo**" in out


class TestFindFiguresAndTablesByPage:
    def test_empty_markdown(self) -> None:
        assert find_figures_and_tables_by_page("plain text") == {}

    def test_figure_in_one_page(self) -> None:
        md = "[PAGE 1]\n<figure>\nUna figura\n</figure>"
        out = find_figures_and_tables_by_page(md)
        assert 1 in out
        assert len(out[1]["figures"]) == 1
        assert "figura" in out[1]["figures"][0]["md_text"]

    def test_table_in_one_page(self) -> None:
        md = "[PAGE 1]\n<table>\n<tr><td>A</td><td>B</td></tr>\n<tr><td>C</td><td>D</td></tr>\n</table>"
        out = find_figures_and_tables_by_page(md)
        assert len(out[1]["tables"]) == 1
        tbl = out[1]["tables"][0]
        assert tbl["row_count"] == 2
        assert tbl["column_count"] == 2
        assert tbl["rows"] == [["A", "B"], ["C", "D"]]

    def test_multiple_pages(self) -> None:
        md = "[PAGE 1]\n<figure>\nA\n</figure>\n[PAGE 2]\n<figure>\nB\n</figure>"
        out = find_figures_and_tables_by_page(md)
        assert sorted(out.keys()) == [1, 2]
        assert len(out[1]["figures"]) == 1
        assert len(out[2]["figures"]) == 1


class TestRegexConstantsAreUsable:
    def test_re_page_marker_matches(self) -> None:
        m = list(RE_PAGE_MARKER.finditer("[PAGE 42]"))
        assert len(m) == 1
        assert m[0].group(1) == "42"

    def test_re_page_split_captures_content(self) -> None:
        out = RE_PAGE_SPLIT.findall("[PAGE 1]A[PAGE 2]B")
        assert out == [("1", "A"), ("2", "B")]
