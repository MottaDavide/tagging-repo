"""Test `core.orchestrators.tag_document` (orchestratore)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from core.models.registry.hierarchy import Hierarchy
from core.models.tagging.candidates import BranoCandidate
from core.models.tagging.output import DocumentPublicationDate
from core.models.tagging.stages import DocumentDateOutput
from core.models.tagging.stats import TaggerStats
from core.orchestrators.tag_document import _build_output, tag_document_units


def _hierarchy_empty() -> Hierarchy:
    return Hierarchy(rms={})


# ── tag_document_units ────────────────────────────────────────────────────


class TestTagDocumentUnits:
    def test_full_flow_uses_discovery_and_classify(self, tmp_path: Path, mocker) -> None:
        doc = tmp_path / "doc1.md"
        doc.write_text("[PAGE 1]\n# T\ntesto")

        unit_cand = BranoCandidate(
            risk_model="Credito", ente=None, brano="sezione", pagina="1", rationale="r", tipo_citazione="table"
        )
        final_cand = BranoCandidate(
            risk_model="Credito",
            ente=None,
            brano="estratto",
            pagina="1",
            rationale="r",
            mo="2578 - MO",
            odc="4602 - OdC",
            tipo_citazione="table",
            table_id="p1#1",
        )
        mocker.patch(
            "core.orchestrators.tag_document.extract_document_date",
            return_value=DocumentDateOutput(
                date=DocumentPublicationDate(year=2025, quarter="Q2"), citazione_data="x", rationale="ok"
            ),
        )
        ente_cand = BranoCandidate(
            risk_model="Credito",
            ente="Divisione BdT",
            brano="estratto",
            pagina="1",
            rationale="r",
            mo="2578 - MO",
            odc="4602 - OdC",
            tipo_citazione="table",
            table_id="p1#1",
        )
        mocker.patch("core.orchestrators.tag_document.discover_candidates", return_value=[unit_cand])
        mocker.patch("core.orchestrators.tag_document.classify_candidates", return_value=[final_cand])
        mocker.patch("core.orchestrators.tag_document.resolve_entes", return_value=[ente_cand])

        out = tag_document_units(MagicMock(), doc, _hierarchy_empty())
        assert len(out.tags) == 1
        assert out.tags[0].ente == "Divisione BdT"
        assert out.tags[0].mo == "2578 - MO"
        assert out.tags[0].odc == "4602 - OdC"
        assert out.tags[0].tipo_citazione == "table"
        assert out.tags[0].table_id == "p1#1"

    def test_no_candidates_returns_empty(self, tmp_path: Path, mocker) -> None:
        doc = tmp_path / "doc1.md"
        doc.write_text("x")
        mocker.patch(
            "core.orchestrators.tag_document.extract_document_date",
            return_value=DocumentDateOutput(
                date=DocumentPublicationDate(year=None, quarter=None), citazione_data=None, rationale="n"
            ),
        )
        mocker.patch("core.orchestrators.tag_document.discover_candidates", return_value=[])
        classify_spy = mocker.patch("core.orchestrators.tag_document.classify_candidates")
        ente_spy = mocker.patch("core.orchestrators.tag_document.resolve_entes")

        out = tag_document_units(MagicMock(), doc, _hierarchy_empty())
        assert out.tags == []
        assert out.stats.n_tags_final == 0
        classify_spy.assert_not_called()
        ente_spy.assert_not_called()

    def test_logs_run_id_when_provided(self, tmp_path: Path, mocker, caplog) -> None:
        doc = tmp_path / "doc1.md"
        doc.write_text("x")
        mocker.patch(
            "core.orchestrators.tag_document.extract_document_date",
            return_value=DocumentDateOutput(
                date=DocumentPublicationDate(year=None, quarter=None), citazione_data=None, rationale="n"
            ),
        )
        mocker.patch("core.orchestrators.tag_document.discover_candidates", return_value=[])

        with caplog.at_level(logging.INFO, logger="core.orchestrators.tag_document"):
            tag_document_units(MagicMock(), doc, _hierarchy_empty(), run_id="run-123")

        assert "run_id=run-123" in caplog.text


# ── _build_output ──────────────────────────────────────────────────────────


class TestBuildOutput:
    def test_empty_candidates(self) -> None:
        out = _build_output("doc1", [], TaggerStats())
        assert out.filename == "doc1"
        assert out.date is None
        assert out.tags == []
        assert out.stats.n_tags_final == 0
        assert out.stats.llm_calls == 0

    def test_includes_date_string(self) -> None:
        date_result = DocumentDateOutput(
            date=DocumentPublicationDate(year=2025, quarter="Q1"),
            citazione_data="15 gennaio 2025",
            rationale="copertina",
        )
        out = _build_output("doc1", [], TaggerStats(), date_result)
        assert out.date.year == 2025
        assert out.date.quarter == "Q1"

    def test_candidate_to_tag_dict(self) -> None:
        cand = BranoCandidate(
            risk_model="AML",
            ente="Gruppo ISP",
            brano="testo",
            pagina="3,4",
            rationale="r",
            rm_confidence="high",
            mo="8838 - MO",
            odc="5069 - OdC",
        )
        out = _build_output("doc1", [cand], TaggerStats())
        assert out.tags[0].model_dump(by_alias=True, exclude_none=True, exclude_unset=True) == {
            "Pagina": "3,4",
            "Risk Model": "AML",
            "Risk Model Confidence": "high",
            "MO": "8838 - MO",
            "OdC": "5069 - OdC",
            "Ente": "Gruppo ISP",
            "Citazione": "testo",
            "Tipo Citazione": "text",
        }

    def test_table_candidate_uses_label_and_table_content(self) -> None:
        doc_text = (
            "[PAGE 1]\ntesto\n"
            "[PAGE 3]\n"
            "<table><tr><td>«ENTE[BdT|Divisione BdT]»Divisione BdT</td><td>9,4%</td></tr></table>\n"
        )
        cand = BranoCandidate(
            risk_model="Credito",
            ente="Divisione BdT",
            brano="testo normalizzato tabella",
            pagina="3",
            rationale="r",
            mo="2578 - MO",
            odc="4602 - OdC",
            tipo_citazione="table",
            table_id="p3#1",
        )
        out = _build_output("doc1", [cand], TaggerStats(), None, doc_text)
        tag = out.tags[0]
        assert tag.citazione == "Tabella a pagina 3"
        assert tag.table_id == "p3#1"
        assert tag.table_content == "<table><tr><td>Divisione BdT</td><td>9,4%</td></tr></table>"

    def test_table_candidate_without_resolvable_id_has_no_content(self) -> None:
        cand = BranoCandidate(
            risk_model="Credito",
            ente="E1",
            brano="x",
            pagina="9",
            rationale="r",
            mo="2578 - MO",
            odc="4602 - OdC",
            tipo_citazione="table",
            table_id="p9#2",
        )
        out = _build_output("doc1", [cand], TaggerStats(), None, "nessuna tabella qui")
        assert out.tags[0].citazione == "Tabella a pagina 9"
        assert out.tags[0].table_content is None

    def test_candidates_without_mo_odc_or_ente_are_excluded(self) -> None:
        stats = TaggerStats()
        complete = BranoCandidate(
            risk_model="AML",
            ente="Gruppo ISP",
            brano="testo completo",
            pagina="3,4",
            rationale="r",
            rm_confidence="high",
            mo="8838 - MO",
            odc="5069 - OdC",
        )
        missing_mo = BranoCandidate(risk_model="AML", ente="Gruppo ISP", brano="s", pagina="5", rationale="r")
        missing_odc = BranoCandidate(
            risk_model="AML", ente="Gruppo ISP", brano="s", pagina="6", rationale="r", mo="8838 - MO"
        )
        missing_ente = BranoCandidate(
            risk_model="AML", ente=None, brano="s", pagina="7", rationale="r", mo="8838 - MO", odc="5069 - OdC"
        )
        out = _build_output("doc1", [complete, missing_mo, missing_odc, missing_ente], stats)
        assert len(out.tags) == 1
        assert out.tags[0].citazione == "testo completo"
        assert out.stats.n_tags_final == 1

    def test_stats_rounded(self) -> None:
        stats = TaggerStats()
        stats.llm_time_s = 1.23456
        out = _build_output("d", [], stats)
        # In memoria il valore resta pieno; l'arrotondamento a 1 decimale avviene in serializzazione.
        assert out.stats.llm_time_s == 1.23456
        assert out.stats.model_dump()["llm_time_s"] == 1.2
