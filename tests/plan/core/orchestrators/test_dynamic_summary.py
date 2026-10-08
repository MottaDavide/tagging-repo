"""Test `core.orchestrators.dynamic_summary`."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.models.dynamic_summary import DynamicTagSummary, TemaEstratti
from core.orchestrators.dynamic_summary import (
    _load_input_tags,
    run,
    summarize_tags,
)


def _summary(titolo: str = "T") -> DynamicTagSummary:
    return DynamicTagSummary(
        titolo=titolo,
        sintesi="S",
        temi=[TemaEstratti(riferimento="R", descrizione="D")],
        quadro_complessivo="Q",
    )


def _full_tag(ente: str = "E1", documento: str | None = None) -> dict:
    tag = {
        "Risk Model": "Credito",
        "MO": "2503 - MO Rating",
        "OdC": "5049 - OdC A",
        "Ente": ente,
        "Pagina": "3",
        "Citazione": "citazione",
    }
    if documento is not None:
        tag["documento"] = documento
    return tag


# ── summarize_tags ───────────────────────────────────────────────────────────


class TestSummarizeTags:
    def test_generates_summaries(self, mocker) -> None:
        mocker.patch(
            "core.orchestrators.dynamic_summary.summarize_group",
            return_value=(_summary(), 0.1),
        )

        result = summarize_tags(
            layer=MagicMock(),
            input_tags=[_full_tag("E1"), _full_tag("E2")],
            system_prompt="sys",
            hierarchy=None,
        )

        assert result.n_gruppi == 2
        assert result.n_tag_input == 2
        assert len(result.entries) == 2
        assert result.entries[0].analisi.titolo == "T"
        assert result.entries[0].n_estratti == 1

    def test_no_complete_groups_returns_empty(self, mocker) -> None:
        spy = mocker.patch("core.orchestrators.dynamic_summary.summarize_group")

        result = summarize_tags(
            layer=MagicMock(),
            input_tags=[{"Risk Model": "AML", "MO": None, "OdC": None, "Ente": "E", "Pagina": "1", "Citazione": "c"}],
            system_prompt="sys",
        )
        assert result.n_gruppi == 0
        assert result.n_tag_input == 1
        spy.assert_not_called()

    def test_failed_group_is_skipped(self, mocker) -> None:
        mocker.patch(
            "core.orchestrators.dynamic_summary.summarize_group",
            return_value=(None, 0.2),  # fail-soft
        )

        result = summarize_tags(
            layer=MagicMock(),
            input_tags=[_full_tag("E1")],
            system_prompt="sys",
        )
        assert result.n_gruppi == 0
        assert result.entries == []

    def test_extracts_serialized_with_documento(self, mocker) -> None:
        mocker.patch(
            "core.orchestrators.dynamic_summary.summarize_group",
            return_value=(_summary(), 0.1),
        )

        result = summarize_tags(
            layer=MagicMock(),
            input_tags=[_full_tag("E1", documento="rel.pdf")],
            system_prompt="sys",
        )
        assert result.entries[0].estratti[0].documento == "rel.pdf"

    def test_output_is_canonicalized_when_codes_are_provided(self, mocker) -> None:
        mocker.patch(
            "core.orchestrators.dynamic_summary.summarize_group",
            return_value=(_summary(), 0.1),
        )

        hierarchy = MagicMock()
        rm_hier = MagicMock()
        rm_hier.risk_model = "Credito"
        rm_hier.get_mo.return_value = MagicMock(label="2503 - MO Rating")
        rm_hier.get_odc.return_value = MagicMock(label="5049 - OdC A")
        hierarchy.get_rm.return_value = rm_hier

        result = summarize_tags(
            layer=MagicMock(),
            input_tags=[
                {
                    "Risk Model": "1080",
                    "MO": "2503",
                    "OdC": "5049",
                    "Ente": "E1",
                    "Pagina": "3",
                    "Citazione": "citazione",
                }
            ],
            system_prompt="sys",
            hierarchy=hierarchy,
        )

        assert result.entries[0].risk_model == "Credito"
        assert result.entries[0].mo == "2503 - MO Rating"
        assert result.entries[0].odc == "5049 - OdC A"


# ── _load_input_tags ──────────────────────────────────────────────────────────


class TestLoadInputTags:
    def test_missing_file_returns_none(self, tmp_path: Path, caplog) -> None:
        with caplog.at_level(logging.ERROR, logger="core.orchestrators.dynamic_summary"):
            out = _load_input_tags(tmp_path / "missing.json")
        assert out is None
        assert "non trovato" in caplog.text

    def test_invalid_json_returns_none(self, tmp_path: Path, caplog) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{not json", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="core.orchestrators.dynamic_summary"):
            out = _load_input_tags(f)
        assert out is None
        assert "non è JSON valido" in caplog.text

    def test_list_format(self, tmp_path: Path) -> None:
        f = tmp_path / "tags.json"
        f.write_text(json.dumps([_full_tag("E1")]), encoding="utf-8")
        out = _load_input_tags(f)
        assert out is not None
        assert len(out) == 1

    def test_tags_wrapper_format(self, tmp_path: Path) -> None:
        f = tmp_path / "tags.json"
        f.write_text(json.dumps({"tags": [_full_tag("E1"), _full_tag("E2")]}), encoding="utf-8")
        out = _load_input_tags(f)
        assert out is not None
        assert len(out) == 2

    def test_dict_without_tags_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "tags.json"
        f.write_text(json.dumps({"foo": 1}), encoding="utf-8")
        assert _load_input_tags(f) == []

    def test_filters_non_dict_entries(self, tmp_path: Path) -> None:
        f = tmp_path / "tags.json"
        f.write_text(json.dumps([_full_tag("E1"), "garbage", 42]), encoding="utf-8")
        out = _load_input_tags(f)
        assert out is not None
        assert len(out) == 1

    def test_non_list_non_dict_returns_none(self, tmp_path: Path, caplog) -> None:
        f = tmp_path / "tags.json"
        f.write_text("42", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="core.orchestrators.dynamic_summary"):
            out = _load_input_tags(f)
        assert out is None
        assert "Formato input non valido" in caplog.text


# ── run ─────────────────────────────────────────────────────────────────────


class TestRun:
    def test_returns_none_if_input_missing(self, tmp_path: Path) -> None:
        assert run(layer=MagicMock(), input_file=tmp_path / "missing.json") is None

    def test_returns_none_if_empty_tags(self, tmp_path: Path, caplog) -> None:
        f = tmp_path / "tags.json"
        f.write_text("[]", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="core.orchestrators.dynamic_summary"):
            result = run(layer=MagicMock(), input_file=f)
        assert result is None
        assert "Nessun tag" in caplog.text

    def test_invokes_summarize_tags(self, tmp_path: Path, mocker) -> None:
        f = tmp_path / "tags.json"
        f.write_text(json.dumps([_full_tag("E1")]), encoding="utf-8")

        mocker.patch(
            "core.orchestrators.dynamic_summary.load_dynamic_summary_resources",
            return_value=([], MagicMock(), "sys"),
        )
        st = mocker.patch(
            "core.orchestrators.dynamic_summary.summarize_tags",
            return_value=MagicMock(),
        )

        run(layer=MagicMock(), input_file=f)
        st.assert_called_once()

    def test_propagates_missing_hierarchy(self, tmp_path: Path, mocker) -> None:
        f = tmp_path / "tags.json"
        f.write_text(json.dumps([_full_tag("E1")]), encoding="utf-8")

        mocker.patch(
            "core.orchestrators.dynamic_summary.load_dynamic_summary_resources",
            side_effect=FileNotFoundError("no hierarchy"),
        )

        with pytest.raises(FileNotFoundError):
            run(layer=MagicMock(), input_file=f)
