"""Test `core.services.parsing.prepare`: cleaning functions + pipeline."""

from __future__ import annotations

from core.services.parsing.prepare import (
    CLEANING_PIPELINE,
    clean_document,
    collapse_blank_lines,
    convert_page_markers,
    decode_html_entities,
    fix_escaped_markdown,
    fix_unicode_ocr_artifacts,
    normalize_deep_headings,
    normalize_page_sequence,
    remove_classification_labels,
    remove_empty_figures,
    remove_isolated_noise,
    remove_logo_figures,
    remove_logo_fragments,
    remove_standalone_checkboxes,
    remove_toc_tables,
    strip_caption_tags,
)

# ── convert_page_markers ────────────────────────────────────────────────────


class TestConvertPageMarkers:
    def test_pagebreak_with_explicit_number(self) -> None:
        text = '<!-- PageBreak --><!-- PageNumber="5" -->\nContent'
        out = convert_page_markers(text)
        assert "[PAGE 5]" in out

    def test_pagebreak_without_number_counter(self) -> None:
        text = "<!-- PageBreak -->\nFirst<!-- PageBreak -->\nSecond"
        out = convert_page_markers(text)
        assert "[PAGE 2]" in out
        assert "[PAGE 3]" in out

    def test_inserts_page1_at_start(self) -> None:
        out = convert_page_markers("plain text no markers")
        assert out.startswith("[PAGE 1]")

    def test_strips_page_header(self) -> None:
        text = '<!-- PageHeader="title" -->\nbody'
        out = convert_page_markers(text)
        assert "PageHeader" not in out

    def test_orphan_page_number_removed(self) -> None:
        text = '<!-- PageNumber="x" -->\nbody'
        out = convert_page_markers(text)
        assert "PageNumber" not in out


# ── remove_logo_figures + remove_empty_figures ──────────────────────────────


class TestRemoveLogoFigures:
    def test_logo_figure_removed(self) -> None:
        out = remove_logo_figures("<figure>INTESA SANPAOLO</figure>")
        assert "INTESA" not in out

    def test_non_logo_preserved(self) -> None:
        text = "<figure>Una descrizione che non contiene il logo aziendale.</figure>"
        out = remove_logo_figures(text)
        assert "descrizione" in out


class TestRemoveEmptyFigures:
    def test_empty_figure_removed(self) -> None:
        out = remove_empty_figures("<figure></figure>")
        assert "figure" not in out


# ── remove_toc_tables ───────────────────────────────────────────────────────


class TestRemoveTocTables:
    def test_toc_table_removed(self) -> None:
        text = "<table><tr><td>Capitolo 1</td><td>3</td></tr><tr><td>Capitolo 2</td><td>5</td></tr></table>"
        out = remove_toc_tables(text)
        assert "table" not in out

    def test_data_table_preserved(self) -> None:
        """Tabella con celle non-puramente-numeriche nella seconda colonna è preservata."""
        text = "<table><tr><td>Foo</td><td>Bar</td></tr></table>"
        out = remove_toc_tables(text)
        assert "Foo" in out


# ── remove_classification_labels ────────────────────────────────────────────


class TestRemoveClassificationLabels:
    def test_riservato_label_removed(self) -> None:
        out = remove_classification_labels("body\nRISERVATO\nmore")
        assert "RISERVATO" not in out


# ── remove_logo_fragments ───────────────────────────────────────────────────


class TestRemoveLogoFragments:
    def test_isolated_intesa_line_removed(self) -> None:
        # NB: la regex è MULTILINE, riga isolata
        out = remove_logo_fragments("body\nINTESA\nmore")
        assert "INTESA" not in out


# ── normalize_deep_headings ─────────────────────────────────────────────────


class TestNormalizeDeepHeadings:
    def test_h5_becomes_h4(self) -> None:
        out = normalize_deep_headings("##### Titolo profondo")
        assert "#### Titolo profondo" in out
        assert "#####" not in out

    def test_h4_unchanged(self) -> None:
        out = normalize_deep_headings("#### Already h4")
        assert "#### Already h4" in out


# ── fix_escaped_markdown ────────────────────────────────────────────────────


class TestFixEscapedMarkdown:
    def test_escaped_dot_in_numbered_list(self) -> None:
        out = fix_escaped_markdown(r"1\. Primo")
        assert "1. Primo" in out

    def test_escaped_dash(self) -> None:
        out = fix_escaped_markdown(r"\- bullet")
        assert "- bullet" in out


# ── remove_standalone_checkboxes ────────────────────────────────────────────


class TestRemoveStandaloneCheckboxes:
    def test_checkbox_line_removed(self) -> None:
        out = remove_standalone_checkboxes("body\n☐\nmore")
        assert "☐" not in out


# ── decode_html_entities ────────────────────────────────────────────────────


class TestDecodeHtmlEntities:
    def test_amp_decoded(self) -> None:
        out = decode_html_entities("foo &amp; bar")
        assert "foo & bar" in out

    def test_no_entities_no_op(self) -> None:
        out = decode_html_entities("plain")
        assert out == "plain"


# ── strip_caption_tags ──────────────────────────────────────────────────────


class TestStripCaptionTags:
    def test_caption_tags_stripped(self) -> None:
        out = strip_caption_tags("<caption>Titolo</caption>")
        assert "<caption>" not in out
        assert "Titolo" in out


# ── fix_unicode_ocr_artifacts ───────────────────────────────────────────────


class TestFixUnicodeOcrArtifacts:
    def test_inverted_question_mark(self) -> None:
        out = fix_unicode_ocr_artifacts("foo ¿ bar")
        assert "?" in out
        assert "¿" not in out


# ── remove_isolated_noise ───────────────────────────────────────────────────


class TestRemoveIsolatedNoise:
    def test_single_uppercase_letter_line_removed(self) -> None:
        out = remove_isolated_noise("body\nA\nmore")
        assert "\nA\n" not in out

    def test_table_content_preserved(self) -> None:
        """Le sequenze dentro <table> NON vengono toccate (potrebbero essere codici)."""
        text = "<table>\nA\n</table>"
        out = remove_isolated_noise(text)
        # 'A' interno alla tabella resta
        assert "A" in out


# ── normalize_page_sequence ─────────────────────────────────────────────────


class TestNormalizePageSequence:
    def test_no_markers_no_op(self) -> None:
        out = normalize_page_sequence("plain text")
        assert out == "plain text"

    def test_in_order_no_op(self) -> None:
        text = "[PAGE 1]\nA\n[PAGE 2]\nB"
        assert normalize_page_sequence(text) == text

    def test_out_of_order_renumbered(self) -> None:
        text = "[PAGE 5]\nA\n[PAGE 7]\nB"
        out = normalize_page_sequence(text)
        assert "[PAGE 1]" in out
        assert "[PAGE 2]" in out


# ── collapse_blank_lines ────────────────────────────────────────────────────


class TestCollapseBlankLines:
    def test_collapses_4plus_newlines(self) -> None:
        out = collapse_blank_lines("A\n\n\n\n\nB")
        assert "\n\n\n\n" not in out


# ── pipeline + clean_document ──────────────────────────────────────────────


class TestCleaningPipeline:
    def test_pipeline_is_nonempty_list(self) -> None:
        assert isinstance(CLEANING_PIPELINE, list)
        assert len(CLEANING_PIPELINE) > 5

    def test_all_callable(self) -> None:
        for step in CLEANING_PIPELINE:
            assert callable(step)


class TestCleanDocument:
    def test_returns_text(self) -> None:
        text = "<!-- PageBreak -->\nA\n\n\n\n\nB"
        out = clean_document(text)
        assert isinstance(out, str)

    def test_idempotent_on_already_clean(self) -> None:
        """Una run pulita non deve modificare il risultato di una run successiva."""
        text = "[PAGE 1]\nA\n\nB\n"
        out1 = clean_document(text)
        out2 = clean_document(out1)
        assert out1 == out2
