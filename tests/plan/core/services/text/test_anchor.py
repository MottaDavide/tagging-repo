"""Test `core.services.text.anchor`: anchor resolution, page-range computation."""

from __future__ import annotations

from core.services.text.anchor import (
    compute_page_range_from_position,
    find_anchor_in_text,
    page_hint_to_pos,
    preprocess_anchor,
)


class TestPreprocessAnchor:
    def test_strip_heading_markers(self) -> None:
        assert preprocess_anchor("## Titolo") == "Titolo"
        assert preprocess_anchor("###### H6") == "H6"

    def test_strip_ente_marker(self) -> None:
        assert preprocess_anchor("foo ENTE[Gruppo ISP] bar") == "foo Gruppo ISP bar"

    def test_whitespace_trimmed(self) -> None:
        assert preprocess_anchor("   spaced   ") == "spaced"


class TestFindAnchorInText:
    def test_exact_match(self) -> None:
        text = "abcXYZdef"
        assert find_anchor_in_text(text, "XYZ") == 3

    def test_case_insensitive_match(self) -> None:
        text = "abcXYZdef"
        assert find_anchor_in_text(text, "xyz") == 3

    def test_returns_none_when_not_found(self) -> None:
        assert find_anchor_in_text("nothing here", "missing-anchor-needle") is None

    def test_empty_anchor_returns_none(self) -> None:
        assert find_anchor_in_text("text", "") is None
        assert find_anchor_in_text("text", "   ") is None

    def test_picks_closest_to_hint(self) -> None:
        """Tra due occorrenze identiche sceglie la più vicina all'hint."""
        text = "needle...filler...needle"
        pos_far = find_anchor_in_text(text, "needle", page_hint_pos=0)
        pos_near = find_anchor_in_text(text, "needle", page_hint_pos=len(text))
        assert pos_far == 0
        assert pos_near == text.rfind("needle")

    def test_normalized_unicode_match(self) -> None:
        """Trova ancora anche dopo NFKC + whitespace + dash normalization."""
        text = "L’analisi del rischio"  # noqa: RUF001 (smart quote intenzionale)
        # smart quote nel testo, anchor con apostrofo dritto → dopo normalize matcha
        assert find_anchor_in_text(text, "L'analisi") is not None

    def test_preprocessed_anchor_fallback(self) -> None:
        """Ancora con prefisso heading `## ` viene strippata e poi matcha."""
        text = "Titolo della sezione importante nel documento"
        anchor = "## Titolo della sezione importante"
        # Direct match fallisce (## solo in anchor), preprocess strippa e matcha.
        assert find_anchor_in_text(text, anchor) is not None

    def test_short_prefix_match(self) -> None:
        """Prefisso fallback su finestra attorno all'hint."""
        prefix = "x" * 70
        text = "prologo " + prefix + " resto del documento"
        anchor = prefix + " resto del documento diverso che NON sta nel testo"
        pos = find_anchor_in_text(text, anchor, page_hint_pos=10)
        assert pos is not None


class TestComputePageRangeFromPosition:
    def test_negative_position_returns_fallback(self) -> None:
        assert compute_page_range_from_position("[PAGE 1]\nA", -1, "A", "fallback") == "fallback"

    def test_single_page(self) -> None:
        doc = "[PAGE 1]\nciao\n[PAGE 2]\nmondo"
        pos = doc.index("ciao")
        assert compute_page_range_from_position(doc, pos, "ciao", "0") == "1"

    def test_brano_spans_multiple_pages(self) -> None:
        doc = "[PAGE 1]\nstart\n[PAGE 2]\nmiddle\n[PAGE 3]\nend"
        brano = "start\n[PAGE 2]\nmiddle\n[PAGE 3]\nend"
        pos = doc.index("start")
        assert compute_page_range_from_position(doc, pos, brano, "0") == "1,2,3"

    def test_no_page_marker_before_position_returns_fallback(self) -> None:
        doc = "preambolo\n[PAGE 1]\nfoo"
        # pos prima del primo marker
        assert compute_page_range_from_position(doc, 0, "preambolo", "fallback") == "fallback"


class TestPageHintToPos:
    def test_empty_pagina_returns_zero(self) -> None:
        assert page_hint_to_pos("any text", "") == 0

    def test_finds_existing_page_marker(self) -> None:
        doc = "preambolo\n[PAGE 1]\nA\n[PAGE 2]\nB\n[PAGE 5]\nC"
        pos = page_hint_to_pos(doc, "2")
        assert pos == doc.index("[PAGE 2]")

    def test_falls_back_to_adjacent_page(self) -> None:
        """Se la pagina richiesta non esiste come marker, prova ±1."""
        doc = "[PAGE 1]\nA\n[PAGE 3]\nC"
        # cerco pagina 2: non esiste, fallback su 1 o 3
        pos = page_hint_to_pos(doc, "2")
        assert pos in (doc.index("[PAGE 1]"), doc.index("[PAGE 3]"))

    def test_range_uses_first_part(self) -> None:
        doc = "[PAGE 1]\nA\n[PAGE 2]\nB"
        assert page_hint_to_pos(doc, "1,2") == doc.index("[PAGE 1]")

    def test_non_numeric_returns_zero(self) -> None:
        doc = "[PAGE 1]\nA"
        assert page_hint_to_pos(doc, "abc") == 0
