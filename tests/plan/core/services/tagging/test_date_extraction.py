"""Test `core.services.tagging.date_extraction`."""

from __future__ import annotations

from unittest.mock import MagicMock

import core.services.tagging.date_extraction as date_mod
from core.models.tagging.output import DocumentPublicationDate
from core.models.tagging.stages import DocumentDateOutput
from core.models.tagging.stats import TaggerStats


class TestExtractDocumentDate:
    def test_uses_configured_date_extraction_model_by_default(self, monkeypatch) -> None:
        layer = MagicMock()
        expected = DocumentDateOutput(
            date=DocumentPublicationDate(year=2025, quarter="Q1"),
            citazione_data="x",
            rationale="ok",
        )
        captured: dict[str, str] = {}

        monkeypatch.setattr(date_mod, "DATE_EXTRACTION_SYSTEM", "SYS")
        monkeypatch.setattr(date_mod, "extract_first_page", lambda text: "FIRST_PAGE")

        def _fake_call_llm_timed(layer, system_prompt, user_message, response_format, max_tokens, model):
            captured["model"] = model
            return expected, 0.0

        monkeypatch.setattr(date_mod, "call_llm_timed", _fake_call_llm_timed)

        result = date_mod.extract_document_date(
            layer=layer,
            doc_id="doc-default-model",
            doc_text="full document",
        )

        assert result == expected
        assert captured["model"] == date_mod.DATE_EXTRACTION_MODEL

    def test_calls_llm_and_updates_stats(self, monkeypatch) -> None:
        layer = MagicMock()
        stats = TaggerStats()
        expected = DocumentDateOutput(
            date=DocumentPublicationDate(year=2025, quarter="Q1"),
            citazione_data="15 gennaio 2025",
            rationale="meeting date in copertina",
        )

        monkeypatch.setattr(date_mod, "DATE_EXTRACTION_SYSTEM", "SYS")
        monkeypatch.setattr(date_mod, "extract_first_page", lambda text: "FIRST_PAGE")
        monkeypatch.setattr(date_mod, "call_llm_timed", lambda *args, **kwargs: (expected, 0.0))

        result = date_mod.extract_document_date(
            layer=layer,
            doc_id="doc-1",
            doc_text="full document",
            model="gpt-test",
            stats=stats,
        )

        assert result == expected
        assert stats.llm_calls == 1
        assert stats.llm_time_s >= 0.0

    def test_llm_failure_returns_none_and_updates_stats(self, monkeypatch) -> None:
        layer = MagicMock()
        stats = TaggerStats()

        monkeypatch.setattr(date_mod, "DATE_EXTRACTION_SYSTEM", "SYS")
        monkeypatch.setattr(date_mod, "extract_first_page", lambda text: "FIRST_PAGE")
        monkeypatch.setattr(date_mod, "call_llm_timed", lambda *args, **kwargs: (None, 1.5))

        result = date_mod.extract_document_date(
            layer=layer,
            doc_id="doc-fail",
            doc_text="full document",
            stats=stats,
        )

        assert result is None
        assert stats.llm_calls == 1
        assert stats.llm_time_s == 1.5

    def test_without_stats_does_not_fail(self, monkeypatch) -> None:
        layer = MagicMock()
        expected = DocumentDateOutput(
            date=DocumentPublicationDate(year=None, quarter=None),
            citazione_data=None,
            rationale="not found",
        )

        monkeypatch.setattr(date_mod, "DATE_EXTRACTION_SYSTEM", "SYS")
        monkeypatch.setattr(date_mod, "extract_first_page", lambda text: "FIRST_PAGE")
        monkeypatch.setattr(date_mod, "call_llm_timed", lambda *args, **kwargs: (expected, 0.0))

        result = date_mod.extract_document_date(
            layer=layer,
            doc_id="doc-2",
            doc_text="full document",
        )

        assert result == expected
