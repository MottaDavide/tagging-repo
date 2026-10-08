"""Test modelli Pydantic `core.models.tagging.stages`."""

from __future__ import annotations

from core.models.tagging.output import DocumentPublicationDate
from core.models.tagging.stages import (
    DocumentDateOutput,
)


class TestDocumentDateOutput:
    def test_construct(self) -> None:
        out = DocumentDateOutput(
            date=DocumentPublicationDate(year=2025, quarter="Q1"),
            citazione_data="15 gennaio 2025",
            rationale="copertina",
        )
        assert out.date.year == 2025
        assert out.date.quarter == "Q1"
