"""Test `evaluation.orchestrators.evaluation`: evaluate(), print_report(), _build_gt_by_name()."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from evaluation.models.results import Candidate, Counts, DocResult
from evaluation.orchestrators.evaluation import (
    _build_gt_by_name,
    _enrich_pred_table_ids,
    _per_doc_table_lines,
    _per_rm_table_lines,
    evaluate,
    print_report,
)
from evaluation.services.matcher import aggregate_per_rm, aggregate_total

# Fixture helper ------------------------------------------------------------


@pytest.fixture
def tagged_and_gt(tmp_path: Path) -> tuple[Path, Path]:
    """Crea una dir taggata + un file GT minimali per testare evaluate()."""
    tagged = tmp_path / "tagged"
    tagged.mkdir()

    # Documento "doc1": GT ha 1 tag AML, PRED matcha (stessa n-upla, pagina, citazione)
    doc1_tag = {
        "Risk Model": "AML",
        "Ente": "Gruppo ISP",
        "MO": "M1",
        "OdC": "O1",
        "Pagina": "1",
        "Citazione": "Testo di prova per il match.",
    }
    (tagged / "doc1.json").write_text(json.dumps({"tags": [doc1_tag]}))
    # Documento "doc2": GT ha 1 tag Credito, PRED ha 1 tag su pagina diversa → FP+FN
    (tagged / "doc2.json").write_text(
        json.dumps(
            {
                "tags": [
                    {"Risk Model": "Credito", "Ente": "Gruppo ISP", "MO": "M2", "OdC": "O2", "Pagina": "5"},
                ]
            }
        )
    )

    gt_file = tmp_path / "gt.json"
    gt_file.write_text(
        json.dumps(
            [
                {"filename": "doc1.md", "tags": [doc1_tag]},
                {
                    "filename": "doc2.md",
                    "tags": [{"Risk Model": "Credito", "Ente": "Gruppo ISP", "MO": "M2", "OdC": "O2", "Pagina": "2"}],
                },
            ]
        )
    )

    return tagged, gt_file


# Tests ---------------------------------------------------------------------


class TestBuildGtByName:
    def test_strips_extension(self) -> None:
        out = _build_gt_by_name([{"filename": "doc1.md", "tags": ["t1"]}])
        assert "doc1" in out

    def test_warns_on_duplicate(self, caplog: pytest.LogCaptureFixture) -> None:
        data = [
            {"filename": "doc.md", "tags": ["a"]},
            {"filename": "doc.md", "tags": ["b"]},  # duplicato
        ]
        with caplog.at_level(logging.WARNING, logger="evaluation.orchestrators.evaluation"):
            out = _build_gt_by_name(data)
        assert "GT duplicato" in caplog.text
        assert out["doc"] == ["b"]


class TestPerDocTableLines:
    def test_header_present(self) -> None:
        lines = _per_doc_table_lines([])
        assert any("DOCUMENTO" in line for line in lines)


class TestPerRmTableLines:
    def test_total_row_present(self) -> None:
        out = _per_rm_table_lines({}, Counts())
        assert any("TOTALE" in line for line in out)


class TestPrintReport:
    def test_logs_section_headers(self, caplog: pytest.LogCaptureFixture) -> None:
        # docs vuoto, ma il report si genera comunque
        with caplog.at_level(logging.INFO, logger="evaluation.orchestrators.evaluation"):
            print_report([], {}, Counts(), frozenset({"AML"}))
        assert "EVALUATION tag_rm" in caplog.text
        assert "PER RISK MODEL" in caplog.text

    def test_with_docs(self, caplog: pytest.LogCaptureFixture) -> None:
        c = Candidate.from_tag({"Risk Model": "AML", "Ente": "X", "MO": "M1", "OdC": "O1", "Pagina": "1"})
        d = DocResult(doc="my-doc", gt=[c], pred=[c], tp=[c])
        per_rm = aggregate_per_rm([d])
        total = aggregate_total([d])
        with caplog.at_level(logging.INFO, logger="evaluation.orchestrators.evaluation"):
            print_report([d], per_rm, total, frozenset({"AML"}))
        assert "my-doc" in caplog.text


class TestEnrichPredTableIds:
    def test_resolves_html_citation_to_id(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "doc1.md").write_text(
            "[PAGE 3]\n<table><tr><td>beta due tre quattro cinque sei sette</td></tr></table>\n"
        )
        tags = [{"Citazione": "<tr><td>beta due tre quattro cinque sei sette</td></tr>"}]
        _enrich_pred_table_ids(tags, docs, "doc1")
        assert tags[0]["Tipo Citazione"] == "table"
        assert tags[0]["TableId"] == "p3#1"

    def test_leaves_text_and_existing_id_untouched(self, tmp_path: Path) -> None:
        tags = [
            {"Citazione": "solo testo, nessun markup"},
            {"Citazione": "<tr><td>x</td></tr>", "TableId": "p1#1"},
        ]
        _enrich_pred_table_ids(tags, tmp_path, "assente")  # nessun .md: to_resolve è vuoto
        assert "TableId" not in tags[0]
        assert tags[1]["TableId"] == "p1#1"


class TestEvaluate:
    def test_full_flow(
        self, tagged_and_gt: tuple[Path, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        tagged_dir, gt_file = tagged_and_gt
        output = tmp_path / "metriche.xlsx"
        with caplog.at_level(logging.INFO, logger="evaluation.orchestrators.evaluation"):
            evaluate(
                tagged_dir=tagged_dir,
                gt_file=gt_file,
                rm_filter=frozenset({"AML", "Credito"}),
                output=output,
            )
        # Devono comparire i nomi dei documenti
        assert "doc1" in caplog.text
        assert "doc2" in caplog.text
        # L'Excel di sintesi deve essere stato salvato
        assert output.exists()

    def test_warns_on_tagged_without_gt(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        tagged = tmp_path / "tagged"
        tagged.mkdir()
        (tagged / "orphan.json").write_text(json.dumps({"tags": []}))
        gt = tmp_path / "gt.json"
        # GT ha doc_real ma tagged ha solo orphan + doc_real
        (tagged / "doc_real.json").write_text(json.dumps({"tags": []}))
        gt.write_text(json.dumps([{"filename": "doc_real.md", "tags": []}]))

        with caplog.at_level(logging.WARNING, logger="evaluation.orchestrators.evaluation"):
            evaluate(tagged_dir=tagged, gt_file=gt, rm_filter=frozenset({"AML"}), output=tmp_path / "out.xlsx")
        assert "orphan" in caplog.text
        assert "non presente in GT" in caplog.text

    def test_warns_on_gt_without_tagged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        tagged = tmp_path / "tagged"
        tagged.mkdir()
        (tagged / "present.json").write_text(json.dumps({"tags": []}))
        gt = tmp_path / "gt.json"
        gt.write_text(
            json.dumps(
                [
                    {"filename": "present.md", "tags": []},
                    {"filename": "missing.md", "tags": []},
                ]
            )
        )
        with caplog.at_level(logging.WARNING, logger="evaluation.orchestrators.evaluation"):
            evaluate(tagged_dir=tagged, gt_file=gt, rm_filter=frozenset({"AML"}), output=tmp_path / "out.xlsx")
        assert "missing" in caplog.text
        assert "Nessun file taggato" in caplog.text

    def test_exits_when_no_tagged_files(self, tmp_path: Path) -> None:
        tagged = tmp_path / "tagged"
        tagged.mkdir()
        gt = tmp_path / "gt.json"
        gt.write_text(json.dumps([{"filename": "doc.md", "tags": []}]))
        with pytest.raises(SystemExit):
            evaluate(tagged_dir=tagged, gt_file=gt, rm_filter=frozenset({"AML"}), output=tmp_path / "out.xlsx")
