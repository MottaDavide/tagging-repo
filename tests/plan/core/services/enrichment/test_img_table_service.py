"""Test `core.services.enrichment.img_table`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import core.services.enrichment.img_table as img_mod
from core.models.tagging.img_table import FigureDescription, PageDescriptions, TableDescription
from core.services.enrichment.img_table import (
    LAYOUT_RECURRENCE_MIN,
    LAYOUT_TEXT_MAX_CHARS,
    _build_page_inputs,
    _build_user_prompt,
    _clean_markdown,
    _compute_signature_occurrences,
    _describe_and_classify_page,
    _figure_signature,
    _generate_descriptions,
    _is_chart_only_input,
    _is_layout_figure_heuristic,
    _process_page,
    _read_inputs,
    inject_descriptions_into_markdown,
    process_document,
    run_batch,
)

# ── _figure_signature ──────────────────────────────────────────────────────


class TestFigureSignature:
    def test_with_pdf_meta_name(self) -> None:
        sig = _figure_signature("md text", {"name": "logo.png", "size_bytes": 1024})
        assert sig.startswith("img:logo.png")
        assert "1024" in sig

    def test_without_pdf_meta_falls_back_to_md(self) -> None:
        sig = _figure_signature("Some markdown text", None)
        assert sig.startswith("md:")
        assert "some markdown text" in sig

    def test_md_signature_truncated(self) -> None:
        long_md = "x" * 200
        sig = _figure_signature(long_md, None)
        # 120 chars max nel signature
        assert len(sig.split("md:", 1)[1]) <= 120


# ── _is_chart_only_input ───────────────────────────────────────────────────


class TestIsChartOnlyInput:
    def test_uses_raw_text(self) -> None:
        item = {"raw_text": "12 34 56", "md_text": ""}
        assert _is_chart_only_input(item) is True

    def test_prose_not_chart(self) -> None:
        item = {
            "raw_text": (
                "Questa figura mostra il flusso completo dei processi aziendali principali. "
                "Inoltre dettaglia ulteriori aspetti operativi rilevanti."
            )
        }
        assert _is_chart_only_input(item) is False


# ── _is_layout_figure_heuristic ────────────────────────────────────────────


class TestIsLayoutFigureHeuristic:
    def test_recurring_and_short_text(self) -> None:
        item = {"occurrence_count": LAYOUT_RECURRENCE_MIN, "md_text": "x" * 5}
        assert _is_layout_figure_heuristic(item) is True

    def test_recurring_but_long_text(self) -> None:
        item = {
            "occurrence_count": LAYOUT_RECURRENCE_MIN,
            "md_text": "x" * (LAYOUT_TEXT_MAX_CHARS + 10),
        }
        assert _is_layout_figure_heuristic(item) is False

    def test_short_text_but_not_recurring(self) -> None:
        item = {"occurrence_count": 1, "md_text": "x"}
        assert _is_layout_figure_heuristic(item) is False


# ── _clean_markdown ────────────────────────────────────────────────────────


class TestCleanMarkdown:
    def test_applies_cleaning_chain(self) -> None:
        # Mette logo, figura vuota, e linee vuote → tutti rimossi
        md = "<figure>INTESA SANPAOLO</figure>\n\n\n\n<figure></figure>\n\n\n\nReal text"
        out = _clean_markdown(md)
        assert "INTESA" not in out
        assert "Real text" in out


# ── _extract_pdf_images_by_page ────────────────────────────────────────────


class TestExtractPdfImagesByPage:
    def test_returns_dict_by_page(self, mocker) -> None:
        # Mock di PdfReader: 2 pagine, ognuna con 1 immagine
        fake_image = MagicMock()
        fake_image.name = "img.png"
        fake_image.width = 100
        fake_image.height = 50
        fake_image.color_space = "RGB"
        fake_image.bits_per_component = 8
        fake_image.data = b"x" * 256

        fake_page = MagicMock()
        fake_page.images = [fake_image]

        fake_reader = MagicMock()
        fake_reader.pages = [fake_page, fake_page]

        mocker.patch("core.services.enrichment.img_table.PdfReader", return_value=fake_reader)

        from core.services.enrichment.img_table import _extract_pdf_images_by_page

        out = _extract_pdf_images_by_page(Path("/dummy.pdf"))
        assert 1 in out
        assert 2 in out
        assert out[1][0]["name"] == "img.png"
        assert out[1][0]["size_bytes"] == 256


# ── _compute_signature_occurrences ─────────────────────────────────────────


class TestComputeSignatureOccurrences:
    def test_signature_counted_across_pages(self) -> None:
        md_pages = {
            1: {"figures": [{"md_text": "logo"}], "tables": []},
            2: {"figures": [{"md_text": "logo"}], "tables": []},
        }
        pdf_images = {1: [], 2: []}
        occ = _compute_signature_occurrences(md_pages, pdf_images)
        # Stessa md_text "logo" appare in 2 pagine → signature ricorrente
        sig = next(iter(occ))
        assert occ[sig] == 2


# ── _build_user_prompt ─────────────────────────────────────────────────────


class TestBuildUserPrompt:
    def test_renders_page_and_jsons(self) -> None:
        out = _build_user_prompt(
            page_number=42,
            figures_input=[
                {
                    "figure_index_on_page": 1,
                    "md_text": "fig text",
                    "pdf_image": None,
                    "occurrence_count": 1,
                }
            ],
            tables_input=[{"table_index_on_page": 1, "row_count": 2, "column_count": 3, "rows": [["a"]]}],
        )
        assert "42" in out
        assert "fig text" in out


# ── _describe_and_classify_page ────────────────────────────────────────────


class TestDescribeAndClassifyPage:
    def test_empty_inputs_returns_empty(self) -> None:
        f, t = _describe_and_classify_page(MagicMock(), 1, [], [], "m", "sys")
        assert f == {}
        assert t == {}

    def test_success_returns_dicts(self, mocker) -> None:
        mocker.patch(
            "core.services.enrichment.img_table.call_llm_timed",
            return_value=(
                PageDescriptions(
                    figures=[
                        FigureDescription(
                            figure_index_on_page=1,
                            description="d",
                            remove_as_layout=False,
                            contains_chart=True,
                            chart_type="bar_chart",
                            reason="r",
                        )
                    ],
                    tables=[
                        TableDescription(
                            table_index_on_page=1,
                            description="t",
                            contains_chart=False,
                            chart_type=None,
                        )
                    ],
                ),
                0.0,
            ),
        )
        figs_in = [{"figure_index_on_page": 1, "md_text": "x"}]
        tabs_in = [{"table_index_on_page": 1, "row_count": 1, "column_count": 1, "rows": []}]
        f, t = _describe_and_classify_page(MagicMock(), 1, figs_in, tabs_in, "m", "sys")
        assert f[1]["description"] == "d"
        assert t[1]["contains_chart"] is False

    def test_llm_failure_returns_empty(self, mocker) -> None:
        mocker.patch("core.services.enrichment.img_table.call_llm_timed", return_value=(None, 1.2))
        figs_in = [{"figure_index_on_page": 1, "md_text": "x"}]
        f, t = _describe_and_classify_page(MagicMock(), 1, figs_in, [], "m", "sys")
        assert f == {}
        assert t == {}


# ── _build_page_inputs ──────────────────────────────────────────────────────


class TestBuildPageInputs:
    def test_simple_figure_and_table(self) -> None:
        page_md: dict[str, list[Any]] = {
            "figures": [{"md_text": "a real figure with lots of textual content", "raw_text": "real text"}],
            "tables": [{"row_count": 2, "column_count": 3, "rows": [["x"]]}],
        }
        figs_call, figs_skip, tables = _build_page_inputs(1, page_md, [], {})
        # Una figura non layout/chart-only → entra in figs_call
        # (la fig "a real figure ..." è prose, non chart)
        assert len(figs_call) + len(figs_skip) == 1
        assert len(tables) == 1

    def test_layout_figure_skipped(self) -> None:
        sig_text = "logo"
        page_md: dict[str, list[Any]] = {
            "figures": [{"md_text": sig_text, "raw_text": sig_text}],
            "tables": [],
        }
        # Forza ricorrenza alta per la signature corrispondente
        from core.services.enrichment.img_table import _figure_signature

        sig = _figure_signature(sig_text, None)
        figs_call, figs_skip, _ = _build_page_inputs(1, page_md, [], {sig: LAYOUT_RECURRENCE_MIN})
        # Stripped come layout
        assert figs_call == []
        assert len(figs_skip) == 1
        assert figs_skip[0]["skip_reason"] == "layout-recurrent"

    def test_chart_only_figure_skipped(self) -> None:
        page_md: dict[str, list[Any]] = {
            "figures": [{"md_text": "12 34 56", "raw_text": "12 34 56"}],
            "tables": [],
        }
        figs_call, figs_skip, _ = _build_page_inputs(1, page_md, [], {})
        assert figs_call == []
        assert figs_skip[0]["skip_reason"] == "chart-only-ocr"


# ── _process_page ──────────────────────────────────────────────────────────


class TestProcessPage:
    def test_with_figures_and_tables(self, mocker) -> None:
        mocker.patch(
            "core.services.enrichment.img_table._describe_and_classify_page",
            return_value=(
                {
                    1: {
                        "description": "fig-desc",
                        "remove_as_layout": False,
                        "contains_chart": False,
                        "chart_type": None,
                        "reason": "",
                    }
                },
                {1: {"description": "tbl-desc", "contains_chart": False, "chart_type": None}},
            ),
        )
        figs_call = [{"figure_index_on_page": 1}]
        tabs = [{"table_index_on_page": 1, "row_count": 1, "column_count": 1, "rows": []}]
        out = _process_page(MagicMock(), 1, figs_call, [], tabs, "m", "sys")
        assert out is not None
        assert len(out["figures"]) == 1
        assert len(out["tables"]) == 1

    def test_remove_as_layout_excludes_figure(self, mocker) -> None:
        mocker.patch(
            "core.services.enrichment.img_table._describe_and_classify_page",
            return_value=(
                {
                    1: {
                        "description": "",
                        "remove_as_layout": True,
                        "contains_chart": False,
                        "chart_type": None,
                        "reason": "",
                    }
                },
                {},
            ),
        )
        figs_call = [{"figure_index_on_page": 1}]
        out = _process_page(MagicMock(), 1, figs_call, [], [], "m", "sys")
        # Figure rimossa, nessuna tabella → output None
        assert out is None

    def test_fallback_when_llm_fails(self, mocker) -> None:
        """Se _describe_and_classify_page ritorna dict vuoti, descrizione fallback usata."""
        mocker.patch(
            "core.services.enrichment.img_table._describe_and_classify_page",
            return_value=({}, {}),
        )
        figs_call = [{"figure_index_on_page": 1}]
        tabs = [{"table_index_on_page": 1, "row_count": 2, "column_count": 3, "rows": []}]
        out = _process_page(MagicMock(), 1, figs_call, [], tabs, "m", "sys")
        assert out is not None
        # Fallback descriptions sono presenti
        assert "non disponibile" in out["figures"][0]["description"]
        assert "righe x" in out["tables"][0]["description"]


# ── _generate_descriptions ─────────────────────────────────────────────────


class TestGenerateDescriptions:
    def test_runs_per_page_in_parallel(self, mocker) -> None:
        """Smoke: passa 2 pagine con tabelle (no pre-filter), verifica chiamate."""
        process_page_spy = mocker.patch(
            "core.services.enrichment.img_table._process_page",
            return_value={"page_number": 1, "figures": [], "tables": [], "figures_skipped_count": 0},
        )
        # Le tabelle non sono soggette al pre-filtering chart/layout → sempre processate
        md_pages = {
            1: {"figures": [], "tables": [{"row_count": 1, "column_count": 1, "rows": [["x"]]}]},
            2: {"figures": [], "tables": [{"row_count": 1, "column_count": 1, "rows": [["y"]]}]},
        }
        pdf_imgs: dict[int, list[Any]] = {1: [], 2: []}
        _generate_descriptions(MagicMock(), md_pages, pdf_imgs, {}, "m", "sys")
        assert process_page_spy.call_count == 2

    def test_target_page_filter(self, mocker) -> None:
        process_page_spy = mocker.patch(
            "core.services.enrichment.img_table._process_page",
            return_value={"page_number": 2, "figures": [], "tables": [], "figures_skipped_count": 0},
        )
        md_pages = {
            1: {"figures": [], "tables": [{"row_count": 1, "column_count": 1, "rows": [["x"]]}]},
            2: {"figures": [], "tables": [{"row_count": 1, "column_count": 1, "rows": [["y"]]}]},
        }
        pdf_imgs: dict[int, list[Any]] = {1: [], 2: []}
        _generate_descriptions(MagicMock(), md_pages, pdf_imgs, {}, "m", "sys", target_page=2)
        # Solo pagina 2 viene processata
        assert process_page_spy.call_count == 1
        call_args = process_page_spy.call_args_list[0]
        # Il page_number è il 2° positional arg
        assert call_args.args[1] == 2


# ── inject_descriptions_into_markdown ──────────────────────────────────────


class TestInjectDescriptionsIntoMarkdown:
    def test_injects_figure_description(self) -> None:
        md = "<figure>\nA\n</figure>"
        images_and_tables = {
            1: {
                "figures": [{"start_line": 0, "end_line": 2}],
                "tables": [],
            }
        }
        descriptions = {1: {"figures": [{"figure_index_on_page": 1, "description": "Descrizione X"}], "tables": []}}
        out = inject_descriptions_into_markdown(md, images_and_tables, descriptions)
        assert "Descrizione X" in out

    def test_no_descriptions_no_op(self) -> None:
        md = "<figure>\nA\n</figure>"
        out = inject_descriptions_into_markdown(md, {1: {"figures": [], "tables": []}}, {})
        assert out == md


# ── _read_inputs ───────────────────────────────────────────────────────────


class TestReadInputs:
    def test_missing_md_raises(self, tmp_path: Path, mocker) -> None:
        mocker.patch.object(img_mod, "DOCUMENTS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError, match="markdown"):
            _read_inputs(tmp_path, "missing-doc")

    def test_missing_pdf_raises(self, tmp_path: Path, mocker) -> None:
        (tmp_path / "doc.md").write_text("x")
        mocker.patch.object(img_mod, "DOCUMENTS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError, match="PDF"):
            _read_inputs(tmp_path, "doc")

    def test_returns_paths_and_text(self, tmp_path: Path, mocker) -> None:
        (tmp_path / "doc.md").write_text("contenuto")
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        mocker.patch.object(img_mod, "DOCUMENTS_DIR", tmp_path)
        md_path, pdf_path, text = _read_inputs(tmp_path, "doc")
        assert md_path.name == "doc.md"
        assert pdf_path.name == "doc.pdf"
        assert text == "contenuto"


# ── process_document ──────────────────────────────────────────────────────


class TestProcessDocument:
    def test_full_flow(self, tmp_path: Path, mocker) -> None:
        md_dir = tmp_path / "md"
        md_dir.mkdir()
        (md_dir / "doc.md").write_text("[PAGE 1]\n<figure>\nA\n</figure>")
        (tmp_path / "doc.pdf").write_bytes(b"PDF")

        mocker.patch.object(img_mod, "DOCUMENTS_DIR", tmp_path)
        mocker.patch("core.services.enrichment.img_table._extract_pdf_images_by_page", return_value={1: []})
        mocker.patch(
            "core.services.enrichment.img_table._generate_descriptions",
            return_value={
                1: {
                    "figures": [{"figure_index_on_page": 1, "description": "DESC"}],
                    "tables": [],
                }
            },
        )

        out_dir = tmp_path / "out"
        out_path = process_document(MagicMock(), "doc", md_dir, out_dir, "m", "sysprompt")
        assert out_path.exists()
        assert "DESC" in out_path.read_text()


# ── run_batch ──────────────────────────────────────────────────────────────


class TestRunBatch:
    def test_no_files_returns(self, tmp_path: Path, caplog) -> None:
        with caplog.at_level(logging.ERROR, logger="core.services.enrichment.img_table"):
            run_batch(input_dir=tmp_path / "in", output_dir=tmp_path / "out")
        assert "Nessun documento trovato" in caplog.text

    def test_all_already_processed(self, tmp_path: Path, caplog) -> None:
        in_dir = tmp_path / "in"
        out_dir = tmp_path / "out"
        in_dir.mkdir()
        out_dir.mkdir()
        (in_dir / "doc.md").write_text("x")
        (out_dir / "doc.md").write_text("already")

        with caplog.at_level(logging.INFO, logger="core.services.enrichment.img_table"):
            run_batch(input_dir=in_dir, output_dir=out_dir)
        assert "già processati" in caplog.text

    def test_processes_targets(self, tmp_path: Path, mocker) -> None:
        in_dir = tmp_path / "in"
        out_dir = tmp_path / "out"
        in_dir.mkdir()
        (in_dir / "doc.md").write_text("x")

        mocker.patch("core.services.enrichment.img_table.init_genfactory", return_value=MagicMock())
        mocker.patch("core.services.enrichment.img_table.IMG_TABLE_SYSTEM", "sys")
        process_spy = mocker.patch(
            "core.services.enrichment.img_table.process_document",
            return_value=tmp_path / "out" / "doc.md",
        )
        run_batch(input_dir=in_dir, output_dir=out_dir)
        process_spy.assert_called_once()

    def test_skips_on_filenotfound(self, tmp_path: Path, mocker, caplog) -> None:
        in_dir = tmp_path / "in"
        out_dir = tmp_path / "out"
        in_dir.mkdir()
        (in_dir / "doc.md").write_text("x")

        mocker.patch("core.services.enrichment.img_table.init_genfactory", return_value=MagicMock())
        mocker.patch("core.services.enrichment.img_table.IMG_TABLE_SYSTEM", "sys")
        mocker.patch(
            "core.services.enrichment.img_table.process_document",
            side_effect=FileNotFoundError("pdf missing"),
        )
        with caplog.at_level(logging.ERROR, logger="core.services.enrichment.img_table"):
            run_batch(input_dir=in_dir, output_dir=out_dir)
        assert "Skipping" in caplog.text

    def test_force_reprocesses(self, tmp_path: Path, mocker) -> None:
        in_dir = tmp_path / "in"
        out_dir = tmp_path / "out"
        in_dir.mkdir()
        out_dir.mkdir()
        (in_dir / "doc.md").write_text("x")
        (out_dir / "doc.md").write_text("pre")

        mocker.patch("core.services.enrichment.img_table.init_genfactory", return_value=MagicMock())
        mocker.patch("core.services.enrichment.img_table.IMG_TABLE_SYSTEM", "sys")
        process_spy = mocker.patch(
            "core.services.enrichment.img_table.process_document",
            return_value=out_dir / "doc.md",
        )
        run_batch(input_dir=in_dir, output_dir=out_dir, force=True)
        process_spy.assert_called_once()
