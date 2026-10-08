"""Test `core.orchestrators.summarize_document`."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from core.models.summary import TagSummary, UniqueTag
from core.models.tagging.output import OutputTag
from core.orchestrators.summarize_document import summarize_document, summarize_tags


def _summary(titolo: str = "T") -> TagSummary:
    return TagSummary(
        titolo=titolo,
        sintesi="S",
        aspetti_rilevanti="A",
        quadro_complessivo="Q",
    )


def _full_tag(ente: str = "E1", pagina: str = "3") -> OutputTag:
    return OutputTag(
        risk_model="Credito",
        rm_confidence="high",
        mo="2503 - MO Rating",
        mo_confidence="high",
        odc="5049 - OdC A",
        odc_confidence="high",
        ente=ente,
        pagina=pagina,
        citazione="citazione",
    )


def _write_tagged(path: Path, tags: list[OutputTag]) -> None:
    import json

    path.write_text(
        json.dumps({"filename": path.stem, "tags": [t.model_dump(by_alias=True) for t in tags]}),
        encoding="utf-8",
    )


class TestSummarizeDocument:
    def test_loads_files_and_delegates_to_summarize_tags(self, tmp_path: Path, mocker) -> None:
        tagged = tmp_path / "doc.json"
        _write_tagged(tagged, [_full_tag("E1"), _full_tag("E2")])
        doc = tmp_path / "doc.md"
        doc.write_text("[PAGE 1]\n# Titolo\nbody", encoding="utf-8")

        mocker.patch(
            "core.orchestrators.summarize_document.summarize_tag",
            return_value=(_summary(), 0.1),
        )

        result = summarize_document(
            layer=MagicMock(),
            tagged_json_path=tagged,
            doc_path=doc,
            system_prompt="sys",
            hierarchy=None,
        )

        assert len(result.summaries) == 2
        assert result.summaries[0].analisi.titolo == "T"

    def test_no_tags_returns_empty_summaries(self, tmp_path: Path, mocker) -> None:
        tagged = tmp_path / "doc.json"
        _write_tagged(tagged, [])
        doc = tmp_path / "doc.md"
        doc.write_text("x", encoding="utf-8")

        spy = mocker.patch("core.orchestrators.summarize_document.summarize_tag")

        result = summarize_document(
            layer=MagicMock(),
            tagged_json_path=tagged,
            doc_path=doc,
            system_prompt="sys",
        )
        spy.assert_not_called()
        assert result.summaries == []

    def test_failed_tag_is_skipped(self, tmp_path: Path, mocker) -> None:
        tagged = tmp_path / "doc.json"
        _write_tagged(tagged, [_full_tag("E1")])
        doc = tmp_path / "doc.md"
        doc.write_text("# T\nbody", encoding="utf-8")

        mocker.patch(
            "core.orchestrators.summarize_document.summarize_tag",
            return_value=(None, 0.2),  # fail-soft
        )

        result = summarize_document(
            layer=MagicMock(),
            tagged_json_path=tagged,
            doc_path=doc,
            system_prompt="sys",
        )
        assert result.summaries == []


class TestSummarizeTags:
    def test_entry_composes_unique_tag(self, mocker) -> None:
        mocker.patch(
            "core.orchestrators.summarize_document.summarize_tag",
            return_value=(_summary(), 0.1),
        )
        result = summarize_tags(MagicMock(), "doc", "Titolo", "testo", [_full_tag("E1")], "sys")
        entry = result.summaries[0]
        assert isinstance(entry.tag, UniqueTag)
        assert entry.tag.risk_model == "Credito"
        assert entry.analisi.titolo == "T"

    def test_empty_tags_returns_empty_summaries(self) -> None:
        result = summarize_tags(MagicMock(), "doc", "Titolo", "testo", [], "sys")
        assert result.summaries == []

    def test_logs_run_id_when_provided(self, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="core.orchestrators.summarize_document"):
            summarize_tags(MagicMock(), "doc", "Titolo", "testo", [], "sys", run_id="run-123")

        assert "run_id=run-123" in caplog.text
