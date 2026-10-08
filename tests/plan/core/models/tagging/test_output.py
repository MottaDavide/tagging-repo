"""Test modelli output `core.models.tagging.output`."""

from __future__ import annotations

from core.models.tagging.output import DocumentPublicationDate, DocumentTaggingOutput
from core.models.tagging.stats import TaggerStats


class TestDocumentTaggingOutput:
    def test_supports_single_date_field(self) -> None:
        out = DocumentTaggingOutput(
            filename="doc1",
            date=DocumentPublicationDate(year=2025, quarter="Q1"),
            tags=[],
            stats=TaggerStats(),
        )

        dumped = out.model_dump(by_alias=True)
        assert dumped["date"]["year"] == 2025
        assert dumped["date"]["quarter"] == "Q1"
        assert "date_extraction" not in dumped
