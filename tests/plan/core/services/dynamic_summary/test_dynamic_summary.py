"""Test `core.services.dynamic_summary.dynamic_summary`."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.models.dynamic_summary import DynamicTagSummary, GroupedTag, TagExtract
from core.models.registry.hierarchy import MO, Hierarchy, OdC, RMHierarchy
from core.models.registry.risk_models import RiskModel
from core.services.dynamic_summary.dynamic_summary import (
    _format_extract_header,
    build_dynamic_summary_user_msg,
    lookup_descriptions,
    lookup_rm_description,
    summarize_group,
)

_VALID_JSON = '{"titolo":"T","sintesi":"S","temi":[{"riferimento":"R","descrizione":"D"}],"quadro_complessivo":"Q"}'


def _group(ente: str | None = "E1", documento: str | None = "doc.pdf") -> GroupedTag:
    return GroupedTag(
        risk_model="Credito",
        mo="2503 - MO Rating",
        odc="5049 - OdC A",
        ente=ente,
        estratti=[TagExtract(documento=documento, pagina="3", citazione="citazione di prova")],
    )


def _hierarchy() -> Hierarchy:
    mo = MO(
        code="2503",
        name="MO Rating",
        description="descrizione MO",
        odcs=(OdC(code="5049", name="OdC A", description="descrizione OdC"),),
    )
    return Hierarchy(rms={"Credito": RMHierarchy(risk_model="Credito", mos=(mo,))})


def _risk_models() -> list[RiskModel]:
    return [
        RiskModel(name="Credito", criteria="Criteri risk model Credito: gestione del rischio di credito."),
        RiskModel(name="AML", criteria="Criteri risk model AML: anti-money laundering."),
    ]


# ── lookup_descriptions ──────────────────────────────────────────────────────


class TestLookupDescriptions:
    def test_none_hierarchy(self) -> None:
        assert lookup_descriptions(None, _group()) == (None, None)

    def test_resolves_descriptions(self) -> None:
        mo_desc, odc_desc = lookup_descriptions(_hierarchy(), _group())
        assert mo_desc == "descrizione MO"
        assert odc_desc == "descrizione OdC"

    def test_unknown_rm(self) -> None:
        g = _group()
        g.risk_model = "Sconosciuto"
        assert lookup_descriptions(_hierarchy(), g) == (None, None)

    def test_resolves_descriptions_from_rm_code(self, monkeypatch) -> None:
        monkeypatch.setenv("ISP_AMBIENTE", "prod")
        g = GroupedTag(
            risk_model="1080",
            mo="2503 - MO Rating",
            odc="5049 - OdC A",
            ente="E1",
            estratti=[TagExtract(documento="doc.pdf", pagina="3", citazione="citazione di prova")],
        )

        mo_desc, odc_desc = lookup_descriptions(_hierarchy(), g)

        assert mo_desc == "descrizione MO"
        assert odc_desc == "descrizione OdC"


# ── lookup_rm_description ────────────────────────────────────────────────────


class TestLookupRmDescription:
    def test_found(self) -> None:
        assert lookup_rm_description(_risk_models(), "Credito") == (
            "Criteri risk model Credito: gestione del rischio di credito."
        )

    def test_found_from_code(self, monkeypatch) -> None:
        monkeypatch.setenv("ISP_AMBIENTE", "prod")
        assert lookup_rm_description(_risk_models(), "1080") == (
            "Criteri risk model Credito: gestione del rischio di credito."
        )

    def test_not_found_returns_none(self) -> None:
        assert lookup_rm_description(_risk_models(), "Sconosciuto") is None

    def test_empty_list_returns_none(self) -> None:
        assert lookup_rm_description([], "Credito") is None


# ── _format_extract_header ───────────────────────────────────────────────────


class TestFormatExtractHeader:
    def test_documento_and_page(self) -> None:
        assert _format_extract_header("doc.pdf", "3") == "[doc.pdf — Pag. 3]"

    def test_page_only(self) -> None:
        assert _format_extract_header(None, "3") == "[Pag. 3]"

    def test_documento_only(self) -> None:
        assert _format_extract_header("doc.pdf", "") == "[doc.pdf]"

    def test_neither(self) -> None:
        assert _format_extract_header(None, "") == "[estratto]"


# ── build_dynamic_summary_user_msg ───────────────────────────────────────────


class TestBuildUserMsg:
    def test_contains_quadruple_and_extracts(self) -> None:
        msg = build_dynamic_summary_user_msg(_group(), "def MO", "def OdC")
        assert "Credito" in msg
        assert "2503 - MO Rating" in msg
        assert "def MO" in msg
        assert "def OdC" in msg
        assert "citazione di prova" in msg
        assert "doc.pdf" in msg
        assert "ESTRATTI TESTUALI DA ANALIZZARE" in msg

    def test_rm_description_included(self) -> None:
        msg = build_dynamic_summary_user_msg(_group(), rm_description="Perimetro RM Credito")
        assert "Perimetro RM Credito" in msg

    def test_ente_none_renders_placeholder(self) -> None:
        msg = build_dynamic_summary_user_msg(_group(ente=None))
        assert "non specificato" in msg

    def test_descriptions_optional(self) -> None:
        msg = build_dynamic_summary_user_msg(_group())
        assert "Definizione MO" not in msg
        assert "Perimetro e criteri" not in msg


# ── summarize_group ──────────────────────────────────────────────────────────


class TestSummarizeGroup:
    def test_success(self, fake_layer: MagicMock) -> None:
        fake_layer.generate.return_value.texts = [_VALID_JSON]
        summary, elapsed = summarize_group(fake_layer, _group(), "sys", "model")
        assert isinstance(summary, DynamicTagSummary)
        assert summary.titolo == "T"
        assert summary.temi[0].riferimento == "R"
        assert elapsed >= 0.0

    def test_llm_failure_returns_none_and_logs_cause(self, mocker, caplog) -> None:
        import logging

        mocker.patch(
            "core.services.llm_client.call_llm",
            side_effect=RuntimeError("ConnectError: connection refused"),
        )
        with caplog.at_level(logging.WARNING, logger="core.services.llm_client"):
            summary, elapsed = summarize_group(MagicMock(), _group(), "sys", "model")
        assert summary is None
        assert elapsed >= 0.0
        assert "connection refused" in caplog.text
