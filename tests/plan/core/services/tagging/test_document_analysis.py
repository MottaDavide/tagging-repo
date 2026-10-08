"""Test `core.services.tagging.document_analysis`."""

from __future__ import annotations

from core.services.tagging.document_analysis import (
    build_ente_metadata,
    parse_doc_structure,
)

# ── parse_doc_structure ─────────────────────────────────────────────────────


class TestParseDocStructure:
    def test_empty_returns_empty(self) -> None:
        page_enti, sections = parse_doc_structure("")
        assert page_enti == {}
        assert sections == []

    def test_extracts_enti_per_page(self) -> None:
        doc = "[PAGE 1]\nciao «ENTE[Gruppo ISP]» bla bla\n[PAGE 2]\n«ENTE[CONTROLLI BDT]» altro testo\n"
        page_enti, _ = parse_doc_structure(doc)
        assert page_enti[1] == ["Gruppo ISP"]
        assert page_enti[2] == ["CONTROLLI BDT"]

    def test_ente_dedup_within_page(self) -> None:
        doc = "[PAGE 1]\n«ENTE[X]» «ENTE[X]» «ENTE[Y]»"
        page_enti, _ = parse_doc_structure(doc)
        # Order preserved (X first appearance), no dup
        assert page_enti[1] == ["X", "Y"]

    def test_sections_with_enti(self) -> None:
        doc = "[PAGE 1]\n# H1 Titolo\n«ENTE[Gruppo ISP]»\n## H2 Sotto\n«ENTE[CONTROLLI BDT]»\n"
        _, sections = parse_doc_structure(doc)
        # Sections: (level, heading_text, page, enti_in_section)
        assert any(level == 1 and "Gruppo ISP" in enti for level, _h, _p, enti in sections)
        assert any(level == 2 and "CONTROLLI BDT" in enti for level, _h, _p, enti in sections)

    def test_section_boundary_uses_heading_level(self) -> None:
        """Una sezione H1 termina solo all'arrivo di un altro H1 (non H2)."""
        doc = "# H1 A\n«ENTE[X]»\n## H2 sotto\n«ENTE[Y]»\n# H1 B\n«ENTE[Z]»\n"
        _, sections = parse_doc_structure(doc)
        h1_a = next(s for s in sections if s[0] == 1 and "A" in s[1])
        # H1 A contiene X e Y (la H2 e i suoi enti sono dentro la sezione H1)
        assert "X" in h1_a[3]
        assert "Y" in h1_a[3]


# ── build_ente_metadata ─────────────────────────────────────────────────────


class TestBuildEnteMetadata:
    def test_metadata_pages_and_count(self) -> None:
        doc = "[PAGE 1]\n«ENTE[X]»\n[PAGE 2]\n«ENTE[X]» «ENTE[Y]»"
        page_enti, sections = parse_doc_structure(doc)
        meta = build_ente_metadata(doc, page_enti, sections)
        x = meta["X"]
        assert x.pages == [1, 2]
        assert x.n_mentions == 2
        assert x.first_page == 1
        assert x.in_cover is True

    def test_y_not_in_cover(self) -> None:
        doc = "[PAGE 1]\n«ENTE[X]»\n[PAGE 2]\n«ENTE[Y]»"
        page_enti, sections = parse_doc_structure(doc)
        meta = build_ente_metadata(doc, page_enti, sections)
        assert meta["Y"].in_cover is False

    def test_h1_h2_associated_with_ente(self) -> None:
        doc = "# Titolo principale\n«ENTE[X]»\n## Sotto\n«ENTE[X]»\n"
        page_enti, sections = parse_doc_structure(doc)
        meta = build_ente_metadata(doc, page_enti, sections)
        x = meta["X"]
        assert "Titolo principale" in x.h1_headings
        assert "Sotto" in x.h2_headings
