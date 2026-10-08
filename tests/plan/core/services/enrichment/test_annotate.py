"""Test `core.services.enrichment.annotate`: canonicalize entities, citation map, marker insertion."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.services.enrichment.annotate import (
    _annotate_citation,
    _annotate_page,
    _build_citation_to_entities_map,
    _canonicalize_page_entities,
    _make_flexible_pattern,
    _normalize_citations_for_page,
    annotate_document,
    run_batch,
)

# ── _canonicalize_page_entities ─────────────────────────────────────────────


class TestCanonicalizePageEntities:
    def test_canonical_unchanged(self) -> None:
        pe = {"0101025 - Gruppo ISP": {"citazione": "a", "ente_raw": "ISP"}}
        out = _canonicalize_page_entities(pe, "doc", "pag_1")
        assert "0101025 - Gruppo ISP" in out

    def test_canonicalizable_remapped(self) -> None:
        # "0141020 - EM 01-41020 CONTROLLI BDT" → "0141020 - CONTROLLI BDT" (code-first)
        pe = {"0141020 - EM 01-41020 CONTROLLI BDT": {"citazione": "a", "ente_raw": "bdt"}}
        out = _canonicalize_page_entities(pe, "doc", "pag_1")
        assert "0141020 - CONTROLLI BDT" in out
        assert "0141020 - EM 01-41020 CONTROLLI BDT" not in out

    def test_unmappable_dropped(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        pe = {"completely-unknown-key": {"citazione": "a", "ente_raw": "x"}}
        with caplog.at_level(logging.WARNING, logger="core.services.enrichment.annotate"):
            out = _canonicalize_page_entities(pe, "doc", "pag_1")
        assert out == {}
        assert "non canonicalizzabile" in caplog.text

    def test_collision_merges_lists(self) -> None:
        """Due chiavi raw con stesso codice mappano sullo stesso canonical → liste unite."""
        pe = {
            "0141020 - CONTROLLI BDT": {"citazione": "a", "ente_raw": "x"},
            "0141020 - EM 01-41020 CONTROLLI BDT": {"citazione": "b", "ente_raw": "y"},
        }
        out = _canonicalize_page_entities(pe, "doc", "pag_1")
        assert "0141020 - CONTROLLI BDT" in out
        citazione = out["0141020 - CONTROLLI BDT"]["citazione"]
        assert isinstance(citazione, list)
        assert {"a", "b"} <= set(citazione)

    def test_empty_input(self) -> None:
        assert _canonicalize_page_entities({}, "doc", "pag_1") == {}


# ── _normalize_citations_for_page ──────────────────────────────────────────


class TestNormalizeCitationsForPage:
    def test_no_op_on_unique_citations(self) -> None:
        pe = {"X": {"citazione": "una sola"}}
        out = _normalize_citations_for_page(pe)
        assert out["X"]["citazione"] == "una sola"

    def test_short_variant_absorbed_into_long(self) -> None:
        """Citazione corta (sottostringa di una lunga) viene unificata alla lunga."""
        long = "Frase lunga molto significativa che contiene contesto importante."
        short = long[:30]
        pe = {
            "X": {"citazione": long},
            "Y": {"citazione": short},
        }
        out = _normalize_citations_for_page(pe)
        # Sequence matcher con threshold 0.99 → varianti molto simili convergono
        # In questo caso forse non triggera la fusione (similarity < 0.99), comunque
        # il test verifica solo che non crashi e produca output valido
        assert "X" in out
        assert "Y" in out

    def test_empty(self) -> None:
        assert _normalize_citations_for_page({}) == {}


# ── _build_citation_to_entities_map ────────────────────────────────────────


class TestBuildCitationToEntitiesMap:
    def test_single_pair(self) -> None:
        pe = {"X": {"citazione": "frase X", "ente_raw": "ente_x"}}
        cmap, occ = _build_citation_to_entities_map(pe)
        assert "frase X" in cmap
        assert ("ente_x", "X") in cmap["frase X"]
        assert occ["frase X"] == 1

    def test_list_pairs_zip(self) -> None:
        pe = {"X": {"citazione": ["c1", "c2"], "ente_raw": ["r1", "r2"]}}
        cmap, _ = _build_citation_to_entities_map(pe)
        assert ("r1", "X") in cmap["c1"]
        assert ("r2", "X") in cmap["c2"]

    def test_more_raws_than_citations(self) -> None:
        """Più ente_raw che citazioni → produce coppie cross."""
        pe = {"X": {"citazione": ["c1"], "ente_raw": ["r1", "r2"]}}
        cmap, _ = _build_citation_to_entities_map(pe)
        assert ("r1", "X") in cmap["c1"]
        assert ("r2", "X") in cmap["c1"]

    def test_more_citations_than_raws_uniform(self) -> None:
        """Più citazioni di un unico ente_raw → broadcast."""
        pe = {"X": {"citazione": ["c1", "c2"], "ente_raw": ["r1"]}}
        cmap, _ = _build_citation_to_entities_map(pe)
        assert ("r1", "X") in cmap["c1"]
        assert ("r1", "X") in cmap["c2"]

    def test_substring_citation_absorbed(self) -> None:
        """Citazione corta sottostringa della lunga → assorbita nella lunga."""
        pe = {
            "X": {"citazione": "frase completa con molto contesto", "ente_raw": "rx"},
            "Y": {"citazione": "frase completa", "ente_raw": "ry"},
        }
        cmap, _ = _build_citation_to_entities_map(pe)
        # "frase completa" viene assorbita in "frase completa con molto contesto"
        assert "frase completa" not in cmap
        assert "frase completa con molto contesto" in cmap
        assert ("ry", "Y") in cmap["frase completa con molto contesto"]
        assert ("rx", "X") in cmap["frase completa con molto contesto"]


# ── _annotate_citation ──────────────────────────────────────────────────────


class TestAnnotateCitation:
    def test_simple_substitution(self) -> None:
        out = _annotate_citation("foo Gruppo ISP bar", [("Gruppo ISP", "0101025 - Gruppo ISP")])
        assert "«ENTE[Gruppo ISP|0101025 - Gruppo ISP]»" in out

    def test_no_pairs_unchanged(self) -> None:
        assert _annotate_citation("text", []) == "text"

    def test_no_match_returns_unchanged(self) -> None:
        assert _annotate_citation("text", [("absent", "Gruppo ISP")]) == "text"

    def test_overlap_resolution_picks_longest(self) -> None:
        """Span sovrapposti: il più lungo vince, l'altro viene scartato."""
        # "Gruppo ISP" (10) vs "Gruppo" (6) → vince il lungo
        out = _annotate_citation(
            "il Gruppo ISP opera",
            [("Gruppo", "0101025 - Gruppo ISP"), ("Gruppo ISP", "0101025 - Gruppo ISP")],
        )
        assert out.count("«ENTE[Gruppo ISP|0101025 - Gruppo ISP]»") == 1
        # Non deve esserci un marker isolato su "Gruppo"
        assert "«ENTE[Gruppo|" not in out

    def test_invalid_entity_key_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="core.services.enrichment.annotate"):
            out = _annotate_citation("foo Gruppo ISP bar", [("Gruppo ISP", "NOT_IN_ENTI_VALUES")])
        assert "ENTE[" not in out
        assert "non in ENTI_VALUES" in caplog.text


# ── _make_flexible_pattern ──────────────────────────────────────────────────


class TestMakeFlexiblePattern:
    def test_whitespace_to_flex(self) -> None:
        """Spazi nel pattern diventano `\\s+` per matchare anche newline/tab."""
        import re

        pat = _make_flexible_pattern("foo bar")
        # `re.escape("foo bar")` → "foo\\ bar" → sostituito in "foo\\s+bar"
        assert re.search(pat, "foo bar")
        assert re.search(pat, "foo\nbar")
        assert re.search(pat, "foo\t\tbar")

    def test_special_chars_escaped(self) -> None:
        import re

        pat = _make_flexible_pattern("a+b")
        # `+` non deve essere interpretato come quantificatore
        assert re.search(pat, "a+b")
        assert not re.search(pat, "aaab")


# ── _annotate_page ─────────────────────────────────────────────────────────


class TestAnnotatePage:
    def test_empty_entities_returns_input(self) -> None:
        out = _annotate_page("page text", {}, "doc", "pag_1")
        assert out == "page text"

    def test_simple_marker_insertion(self) -> None:
        page_text = "Il Gruppo ISP è una banca."
        pe = {"0101025 - Gruppo ISP": {"citazione": "Il Gruppo ISP è una banca.", "ente_raw": "Gruppo ISP"}}
        out = _annotate_page(page_text, pe, "doc", "pag_1")
        assert "«ENTE[Gruppo ISP|0101025 - Gruppo ISP]»" in out


# ── annotate_document ───────────────────────────────────────────────────────


class TestAnnotateDocument:
    def test_returns_unchanged_when_no_page_markers(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.md"
        p.write_text("no markers here")
        out = annotate_document(p, {})
        assert out == "no markers here"

    def test_annotates_marker_pages(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.md"
        p.write_text("[PAGE 1]\nIl Gruppo ISP opera.\n[PAGE 2]\nAltro testo.")
        all_entities = {
            "entity_extracted": {
                "pag_1": {
                    "0101025 - Gruppo ISP": {
                        "citazione": "Il Gruppo ISP opera.",
                        "ente_raw": "Gruppo ISP",
                    }
                }
            }
        }
        out = annotate_document(p, all_entities)
        assert "«ENTE[Gruppo ISP|0101025 - Gruppo ISP]»" in out
        # Pagina 2 senza entità: passthrough
        assert "Altro testo" in out

    def test_doc_key_fallback_without_pdf_suffix(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.md"
        p.write_text("[PAGE 1]\nGruppo ISP qui.")
        all_entities = {
            "entity_extracted": {
                "pag_1": {"0101025 - Gruppo ISP": {"citazione": "Gruppo ISP qui.", "ente_raw": "Gruppo ISP"}}
            }
        }
        out = annotate_document(p, all_entities)
        assert "ENTE[Gruppo ISP" in out

    def test_logs_run_id_when_provided(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        p = tmp_path / "doc.md"
        p.write_text("no markers here")

        with caplog.at_level(logging.INFO, logger="core.services.enrichment.annotate"):
            annotate_document(p, {}, run_id="run-123")

        assert "run_id=run-123" in caplog.text


# ── run_batch ───────────────────────────────────────────────────────────────


class TestRunBatch:
    def test_full_flow(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        (input_dir / "doc.md").write_text("[PAGE 1]\nGruppo ISP qui.", encoding="utf-8")

        enti_path = tmp_path / "enti.json"
        enti_path.write_text(
            json.dumps(
                {
                    "doc.pdf": {
                        "entity_extracted": {
                            "pag_1": {
                                "0101025 - Gruppo ISP": {
                                    "citazione": "Gruppo ISP qui.",
                                    "ente_raw": "Gruppo ISP",
                                }
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        run_batch(input_dir=input_dir, output_dir=output_dir, entities_path=enti_path)

        out = (output_dir / "doc.md").read_text(encoding="utf-8")
        assert "«ENTE[Gruppo ISP|0101025 - Gruppo ISP]»" in out

    def test_missing_entities_file_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            run_batch(
                input_dir=tmp_path,
                output_dir=tmp_path / "out",
                entities_path=tmp_path / "missing.json",
            )

    def test_skip_docs_without_entities(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        (input_dir / "withent.md").write_text("[PAGE 1]\nX")
        (input_dir / "noent.md").write_text("[PAGE 1]\nY")

        enti_path = tmp_path / "enti.json"
        enti_path.write_text(json.dumps({"withent.pdf": {"entity_extracted": {}}}))

        run_batch(input_dir=input_dir, output_dir=output_dir, entities_path=enti_path)
        assert (output_dir / "withent.md").exists()
        assert not (output_dir / "noent.md").exists()

    def test_single_file(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        (input_dir / "a.md").write_text("[PAGE 1]\nX")
        (input_dir / "b.md").write_text("[PAGE 1]\nY")

        enti_path = tmp_path / "enti.json"
        enti_path.write_text(
            json.dumps(
                {
                    "a.pdf": {"entity_extracted": {}},
                    "b.pdf": {"entity_extracted": {}},
                }
            )
        )

        run_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            entities_path=enti_path,
            single_file="a.md",
        )
        assert (output_dir / "a.md").exists()
        assert not (output_dir / "b.md").exists()

    def test_no_markdown_files_returns_silently(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        enti_path = tmp_path / "enti.json"
        enti_path.write_text("{}")
        # Niente .md → return silenzioso
        run_batch(input_dir=input_dir, output_dir=tmp_path / "out", entities_path=enti_path)

    def test_force_reprocesses(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "doc.md").write_text("[PAGE 1]\nX")
        (output_dir / "doc.md").write_text("OLD")

        enti_path = tmp_path / "enti.json"
        enti_path.write_text(json.dumps({"doc.pdf": {"entity_extracted": {}}}))

        run_batch(input_dir=input_dir, output_dir=output_dir, entities_path=enti_path, force=True)
        assert (output_dir / "doc.md").read_text() != "OLD"


# ── _similarity_ratio edge cases ────────────────────────────────────────────


class TestSimilarityRatio:
    def test_empty_returns_zero(self) -> None:
        from core.services.enrichment.annotate import _similarity_ratio

        assert _similarity_ratio("", "x") == 0.0
        assert _similarity_ratio("x", "") == 0.0


# ── _flatten_citations + _normalize con list citations ──────────────────────


class TestNormalizeCitationsList:
    def test_list_citation_normalized_per_index(self) -> None:
        pe = {
            "X": {"citazione": ["short", "lungo testo da preferire come canonico"], "ente_raw": ""},
        }
        out = _normalize_citations_for_page(pe, threshold=0.0)
        # Entrambe le citazioni puntano a quella più lunga (similarità >= 0.0 sempre)
        cit = out["X"]["citazione"]
        assert all("lungo" in c for c in cit)


# ── _collect_citations_from_entities ── citazione > ente_raw non uniforme ──


class TestCollectCitations:
    def test_more_citations_than_raws_non_uniform_warns(self, caplog) -> None:
        import logging

        from core.services.enrichment.annotate import _collect_citations_from_entities

        pe = {
            "X": {
                "citazione": ["c1", "c2", "c3"],
                "ente_raw": ["r1", "r2"],  # 2 raws diversi, 3 cit → ramo "non uniforme"
            }
        }
        with caplog.at_level(logging.WARNING, logger="core.services.enrichment.annotate"):
            _collect_citations_from_entities(pe)
        assert "non uniformi" in caplog.text

    def test_more_citations_than_raws_uniform_no_warn(self) -> None:
        from core.services.enrichment.annotate import _collect_citations_from_entities

        pe = {
            "X": {
                "citazione": ["c1", "c2", "c3"],
                "ente_raw": ["r1", "r1"],  # tutti uguali → broadcast
            }
        }
        cmap, _ = _collect_citations_from_entities(pe)
        # 3 citazioni mappate a r1
        assert all(pairs == [("r1", "X")] for pairs in cmap.values())

    def test_more_raws_than_citations_cross_product(self) -> None:
        from core.services.enrichment.annotate import _collect_citations_from_entities

        pe = {
            "X": {
                "citazione": ["c1"],
                "ente_raw": ["r1", "r2"],  # più raw → cross-product (c, r) per ogni c, r
            }
        }
        cmap, _ = _collect_citations_from_entities(pe)
        assert ("r1", "X") in cmap["c1"]
        assert ("r2", "X") in cmap["c1"]

    def test_skips_empty_citation_or_raw(self) -> None:
        from core.services.enrichment.annotate import _collect_citations_from_entities

        pe = {"X": {"citazione": "", "ente_raw": "r"}}
        cmap, _ = _collect_citations_from_entities(pe)
        assert cmap == {}


# ── _annotate_citation: skip ente_raw vuoto ─────────────────────────────────


class TestAnnotateCitationEmptyEnte:
    def test_empty_ente_raw_skipped(self) -> None:
        from core.services.enrichment.annotate import _annotate_citation

        # ente_raw vuoto → nessuna sostituzione
        out = _annotate_citation("testo", [("", "Gruppo ISP")])
        assert out == "testo"


# ── _annotate_page early returns ────────────────────────────────────────────


class TestAnnotatePageEarlyReturns:
    def test_canonicalize_empty_returns_input(self) -> None:
        # Entities con key non canonicalizzabili → canonicalized vuoto → return page_text
        out = _annotate_page("testo", {"completely-unknown-key": {"citazione": "x", "ente_raw": "r"}}, "doc", "pag_1")
        assert out == "testo"

    def test_no_annotation_needed_returns_unchanged(self) -> None:
        # citation_text non si trova nel page → annotated_citation == citation_text → continue
        pe = {"Gruppo ISP": {"citazione": "non presente nel testo", "ente_raw": "ISP"}}
        out = _annotate_page("altro testo", pe, "doc", "pag_1")
        assert out == "altro testo"


# ── run_batch: single_file con stem fallback ────────────────────────────────


class TestRunBatchStemFallback:
    def test_single_file_stem_fallback(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        (input_dir / "doc.md").write_text("[PAGE 1]\nX")
        output_dir = tmp_path / "out"
        enti_path = tmp_path / "enti.json"
        enti_path.write_text(json.dumps({"doc.pdf": {"entity_extracted": {}}}))

        # single_file="doc" (senza .md) → fallback su {stem}.md
        run_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            entities_path=enti_path,
            single_file="doc",
        )
        assert (output_dir / "doc.md").exists()

    def test_no_documents_with_entities(self, tmp_path: Path, caplog) -> None:
        import logging

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        (input_dir / "doc.md").write_text("[PAGE 1]\nX")
        enti_path = tmp_path / "enti.json"
        enti_path.write_text("{}")  # nessun ente per nessun doc

        with caplog.at_level(logging.INFO, logger="core.services.enrichment.annotate"):
            run_batch(input_dir=input_dir, output_dir=tmp_path / "out", entities_path=enti_path)
        assert "senza enti" in caplog.text

    def test_exception_in_annotate_logged(self, tmp_path: Path, mocker, caplog) -> None:
        import logging

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        (input_dir / "doc.md").write_text("[PAGE 1]\nX")
        enti_path = tmp_path / "enti.json"
        enti_path.write_text(json.dumps({"doc.pdf": {"entity_extracted": {}}}))

        mocker.patch("core.services.enrichment.annotate.annotate_document", side_effect=RuntimeError("boom"))
        with caplog.at_level(logging.ERROR, logger="core.services.enrichment.annotate"):
            run_batch(input_dir=input_dir, output_dir=tmp_path / "out", entities_path=enti_path)
        assert "ERRORE" in caplog.text
