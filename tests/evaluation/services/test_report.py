"""Test `evaluation.services.report.write_summary`."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from evaluation.models.results import Candidate, DocResult
from evaluation.services.matcher import DEFAULT_THRESHOLD, aggregate_per_rm, aggregate_total
from evaluation.services.report import write_summary


def _candidate(rm: str, pagina: str) -> Candidate:
    return Candidate.from_tag({"Risk Model": rm, "Ente": "X", "MO": "M1", "OdC": "O1", "Pagina": pagina})


def _docs() -> list[DocResult]:
    ok = _candidate("AML", "1")
    fn = _candidate("AML", "2")
    fp = _candidate("Credito", "3")
    d1 = DocResult(doc="doc1", gt=[ok, fn], pred=[ok], tp=[ok], fn=[fn])
    d2 = DocResult(doc="doc2", gt=[], pred=[fp], fp=[fp])
    return [d1, d2]


def _write(docs: list[DocResult], output: Path) -> None:
    write_summary(
        docs,
        aggregate_per_rm(docs),
        aggregate_total(docs),
        rm_filter=frozenset({"AML", "Credito"}),
        tipo_filter=frozenset(),
        ignore_ente=False,
        threshold=DEFAULT_THRESHOLD,
        output=output,
    )


class TestWriteSummary:
    def test_creates_file_with_two_sheets(self, tmp_path: Path) -> None:
        output = tmp_path / "metriche.xlsx"
        _write(_docs(), output)

        assert output.exists()
        wb = openpyxl.load_workbook(output)
        assert wb.sheetnames == ["Per documento", "Per Risk Model"]

    def test_per_doc_sheet_has_header_and_rows(self, tmp_path: Path) -> None:
        output = tmp_path / "metriche.xlsx"
        _write(_docs(), output)

        ws = openpyxl.load_workbook(output)["Per documento"]
        header_row = [c.value for c in ws[4]]
        assert header_row == ["Documento", "GT", "PRED", "TP", "FP", "FN", "Recall", "Precisione"]
        doc_names = {ws.cell(row=r, column=1).value for r in (5, 6)}
        assert doc_names == {"doc1", "doc2"}

    def test_per_rm_sheet_has_totals_row(self, tmp_path: Path) -> None:
        docs = _docs()
        per_rm = aggregate_per_rm(docs)
        total = aggregate_total(docs)
        output = tmp_path / "metriche.xlsx"
        _write(docs, output)

        ws = openpyxl.load_workbook(output)["Per Risk Model"]
        header_row = [c.value for c in ws[4]]
        assert header_row == ["Risk Model", "TP", "FP", "FN", "Precisione", "Recall", "F1"]
        # 2 Risk Model (AML, Credito) + riga totale
        last_row = 4 + len(per_rm) + 1
        assert ws.cell(row=last_row, column=1).value == "TOTALE"
        assert ws.cell(row=last_row, column=2).value == total.tp

    def test_number_formats_applied(self, tmp_path: Path) -> None:
        output = tmp_path / "metriche.xlsx"
        _write(_docs(), output)

        ws = openpyxl.load_workbook(output)["Per documento"]
        assert ws.cell(row=5, column=7).number_format == "0.0%"
        assert ws.cell(row=5, column=4).number_format == "#,##0"

    def test_empty_docs_still_writes_valid_workbook(self, tmp_path: Path) -> None:
        output = tmp_path / "metriche.xlsx"
        _write([], output)

        wb = openpyxl.load_workbook(output)
        ws_rm = wb["Per Risk Model"]
        assert ws_rm.cell(row=5, column=1).value == "TOTALE"

    def test_per_doc_last_row_is_not_styled_as_total(self, tmp_path: Path) -> None:
        """Il foglio 'Per documento' non ha una riga di totale: l'ultimo documento
        (quello con recall più basso) deve restare in grassetto normale, non bold/evidenziato
        come se fosse un aggregato."""
        docs = [DocResult(doc="unico", gt=[_candidate("AML", "1")], pred=[], fn=[_candidate("AML", "1")])]
        output = tmp_path / "metriche.xlsx"
        _write(docs, output)

        ws = openpyxl.load_workbook(output)["Per documento"]
        last_cell = ws.cell(row=5, column=1)
        assert last_cell.font.bold is False
