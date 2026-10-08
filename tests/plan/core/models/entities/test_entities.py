"""Test dei modelli/converter API in `core.models.entities.entities`."""

from __future__ import annotations

import datetime

import pytest

from core.models.entities.entities import Scope, SummaryRequest, SummaryResponse, Tag, TaggingResult, TagToSummarize
from core.models.summary import DocumentSummaries, TagOccorrenza, TagSummary, TagSummaryEntry, UniqueTag
from core.models.tagging.output import DocumentPublicationDate, DocumentTaggingOutput, OutputTag
from core.models.tagging.stats import TaggerStats


def _output_tag(**overrides: object) -> OutputTag:
    base: dict[str, object] = {
        "pagina": "12,13",
        "risk_model": "Credito",
        "rm_confidence": "high",
        "mo": "2578 - MO Concessione",
        "mo_confidence": "medium",
        "odc": "4601 - Istruttoria",
        "odc_confidence": "low",
        "ente": "0141020 - CONTROLLI BDT",
        "citazione": "testo",
        "tipo_citazione": "table",
    }
    base.update(overrides)
    return OutputTag(**base)  # type: ignore[arg-type]


def _unique_tag(**overrides: object) -> UniqueTag:
    base: dict[str, object] = {
        "risk_model": "Credito",
        "mo": "2578 - MO Concessione",
        "odc": "4601 - Istruttoria",
        "ente": "0141020 - CONTROLLI BDT",
        "occorrenze": [
            TagOccorrenza(pagina="12,13", citazione="testo 1"),
            TagOccorrenza(pagina="15", citazione="testo 2"),
        ],
    }
    base.update(overrides)
    return UniqueTag(**base)  # type: ignore[arg-type]


def _summary(**overrides: object) -> TagSummary:
    base: dict[str, object] = {
        "titolo": "Titolo",
        "sintesi": "Sintesi",
        "aspetti_rilevanti": "Aspetti",
        "quadro_complessivo": "Quadro",
    }
    base.update(overrides)
    return TagSummary(**base)  # type: ignore[arg-type]


class TestScope:
    @pytest.mark.parametrize(
        ("raw_value", "expected_scope"),
        [("fac", Scope.fac), ("vigilanza", Scope.vigilanza)],
    )
    def test_accepts_supported_scope_values(self, raw_value: str, expected_scope: Scope) -> None:
        assert Scope(raw_value) is expected_scope


class TestTagFromOutputTag:
    def test_propagates_real_confidence(self) -> None:
        tag = Tag.from_output_tag(_output_tag(), _summary())
        assert tag.risk_model.confidence == "high"
        assert tag.macro_obiettivo.confidence == "medium"
        assert tag.obiettivo_di_controllo.confidence == "low"

    def test_propagates_tipo_citazione(self) -> None:
        assert Tag.from_output_tag(_output_tag(), _summary()).tipo_citazione == "table"

    def test_propagates_table_content(self) -> None:
        html = "<table><tr><td>x</td></tr></table>"
        tag = Tag.from_output_tag(_output_tag(citazione="Tabella a pagina 3", table_content=html), _summary())
        assert tag.table_content == html

    def test_table_content_defaults_to_none_for_text(self) -> None:
        assert Tag.from_output_tag(_output_tag(tipo_citazione="text"), _summary()).table_content is None

    def test_parses_pages_and_values(self) -> None:
        tag = Tag.from_output_tag(_output_tag(), _summary())
        assert tag.pages == [12, 13]
        assert tag.risk_model.value == "1080"
        assert tag.ente == "0141020"
        assert tag.analisi.titolo == "Titolo"

    def test_handles_missing_confidence(self) -> None:
        tag = Tag.from_output_tag(_output_tag(rm_confidence=None, mo_confidence=None, odc_confidence=None), _summary())
        assert tag.risk_model.confidence is None
        assert tag.macro_obiettivo.confidence is None
        assert tag.obiettivo_di_controllo.confidence is None


class TestTaggingResultFromOutput:
    def test_maps_output_tags_to_summary_analysis(self) -> None:
        output = DocumentTaggingOutput(
            filename="doc",
            date=DocumentPublicationDate(year=None, quarter=None),
            tags=[_output_tag()],
            stats=TaggerStats(),
        )
        summary = _summary(titolo="Analisi Credito")
        summaries = DocumentSummaries(summaries=[TagSummaryEntry(tag=_unique_tag(), analisi=summary)])
        result = TaggingResult.from_document_tagging_output(output, document_summaries=summaries)
        assert len(result.tags) == 1
        assert result.tags[0].analisi is summary

    def test_builds_empty_publication_date_when_output_date_is_none(self) -> None:
        output = DocumentTaggingOutput(
            filename="doc",
            date=None,
            tags=[_output_tag()],
            stats=TaggerStats(),
        )
        summary = _summary()
        summaries = DocumentSummaries(summaries=[TagSummaryEntry(tag=_unique_tag(), analisi=summary)])

        result = TaggingResult.from_document_tagging_output(output, document_summaries=summaries)

        assert result.date is None

    def test_skips_tags_without_matching_summary(self) -> None:
        output = DocumentTaggingOutput(
            filename="doc",
            date=DocumentPublicationDate(year=None, quarter=None),
            tags=[_output_tag()],
            stats=TaggerStats(),
        )
        summaries = DocumentSummaries(
            summaries=[TagSummaryEntry(tag=_unique_tag(risk_model="AML"), analisi=_summary())]
        )

        result = TaggingResult.from_document_tagging_output(output, document_summaries=summaries)

        assert result.tags == []


class TestTagToSummarize:
    def test_to_pipeline_dict(self) -> None:
        tag = TagToSummarize(
            entityId="ENT01",
            entity="01-79000 DIREZIONE AGRIBUSINESS",
            riskModelId="RM01",
            macroObjectiveId="MO01",
            objectiveOfControlId="OdC01",
            citation="citazione",
            document="document",
        )
        assert tag.to_pipeline_dict() == {
            "Risk Model": "RM01",
            "MO": "MO01",
            "OdC": "OdC01",
            "Ente": "DIREZIONE AGRIBUSINESS",
            "Citazione": "citazione",
            "Documento": "document",
        }


class TestSummaryRequest:
    def test_empty_tags_raises(self) -> None:
        with pytest.raises(ValueError, match="tagsToSummarize"):
            SummaryRequest(
                mail="user@example.com",
                user="user",
                userWac="WAC01",
                filters=[],
                entityRiskId="ERI01",
                tagsToSummarize=[],
            )

    def test_valid_request(self) -> None:
        tag = TagToSummarize(
            entityId="ENT01",
            entity="01-79000 DIREZIONE AGRIBUSINESS",
            riskModelId="RM01",
            macroObjectiveId="MO01",
            objectiveOfControlId="OdC01",
            citation="citazione",
            document="document",
        )
        req = SummaryRequest(
            mail="user@example.com",
            user="user",
            userWac="WAC01",
            filters=[],
            entityRiskId="ERI01",
            tagsToSummarize=[tag],
        )
        assert req.entity_risk_id == "ERI01"
        assert req.user_wac == "WAC01"


class TestSummaryResponse:
    def test_data_defaults_to_iso_datetime(self) -> None:
        resp = SummaryResponse(run_id="abc123")
        datetime.datetime.fromisoformat(resp.data)

    def test_message_and_error_default_to_none(self) -> None:
        resp = SummaryResponse(run_id="xyz")
        assert resp.message is None
        assert resp.error is None
