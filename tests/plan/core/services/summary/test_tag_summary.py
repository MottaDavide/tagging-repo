"""Test `core.services.summary.tag_summary`."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.models.registry.hierarchy import MO, Hierarchy, OdC, RMHierarchy
from core.models.registry.risk_models import RiskModel
from core.models.summary import TagOccorrenza, TagSummary, UniqueTag
from core.services.summary.tag_summary import (
    build_summary_user_msg,
    extract_citation_context,
    lookup_descriptions,
    lookup_rm_description,
    summarize_tag,
)

_VALID_JSON = '{"titolo":"T","sintesi":"S","aspetti_rilevanti":"A","quadro_complessivo":"Q"}'


def _unique_tag(ente: str = "E1") -> UniqueTag:
    return UniqueTag(
        risk_model="Credito",
        mo="2503 - MO Rating",
        odc="5049 - OdC A",
        ente=ente,
        occorrenze=[TagOccorrenza(pagina="3", citazione="citazione di prova")],
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
        assert lookup_descriptions(None, _unique_tag()) == (None, None)

    def test_resolves_descriptions(self) -> None:
        mo_desc, odc_desc = lookup_descriptions(_hierarchy(), _unique_tag())
        assert mo_desc == "descrizione MO"
        assert odc_desc == "descrizione OdC"

    def test_unknown_rm(self) -> None:
        ut = _unique_tag()
        ut.risk_model = "Sconosciuto"
        assert lookup_descriptions(_hierarchy(), ut) == (None, None)


# ── lookup_rm_description ────────────────────────────────────────────────────


class TestLookupRmDescription:
    def test_found(self) -> None:
        desc = lookup_rm_description(_risk_models(), "Credito")
        assert desc == "Criteri risk model Credito: gestione del rischio di credito."

    def test_not_found_returns_none(self) -> None:
        assert lookup_rm_description(_risk_models(), "Sconosciuto") is None

    def test_empty_list_returns_none(self) -> None:
        assert lookup_rm_description([], "Credito") is None

    def test_case_sensitive(self) -> None:
        assert lookup_rm_description(_risk_models(), "credito") is None


# ── extract_citation_context ─────────────────────────────────────────────────


class TestExtractCitationContext:
    _DOC = "Inizio documento. " + "A" * 100 + " citazione di prova " + "B" * 100 + " fine documento."

    def test_exact_match_returns_context(self) -> None:
        ctx = extract_citation_context(self._DOC, "citazione di prova")
        assert ctx is not None
        assert "citazione di prova" in ctx

    def test_case_insensitive_fallback(self) -> None:
        ctx = extract_citation_context(self._DOC, "CITAZIONE DI PROVA")
        assert ctx is not None

    def test_not_found_returns_none(self) -> None:
        assert extract_citation_context(self._DOC, "testo assente nel documento") is None

    def test_empty_citation_returns_none(self) -> None:
        assert extract_citation_context(self._DOC, "") is None

    def test_empty_doc_returns_none(self) -> None:
        assert extract_citation_context("", "citazione") is None

    def test_ellipsis_when_truncated(self) -> None:
        ctx = extract_citation_context(self._DOC, "citazione di prova", context_chars=10)
        assert ctx is not None
        assert "…" in ctx


# ── build_summary_user_msg ───────────────────────────────────────────────────


class TestBuildUserMsg:
    def test_contains_tag_evidenze_and_document(self) -> None:
        msg = build_summary_user_msg(_unique_tag(), "Titolo Doc", "TESTO COMPLETO", "def MO", "def OdC")
        assert "Credito" in msg
        assert "2503 - MO Rating" in msg
        assert "def MO" in msg
        assert "def OdC" in msg
        assert "citazione di prova" in msg
        assert "TESTO COMPLETO" in msg
        assert "Titolo Doc" in msg

    def test_rm_description_included(self) -> None:
        msg = build_summary_user_msg(_unique_tag(), "T", "doc", rm_description="Perimetro RM Credito")
        assert "Perimetro RM Credito" in msg

    def test_ente_empty_renders_placeholder(self) -> None:
        msg = build_summary_user_msg(_unique_tag(ente=""), "T", "doc")
        assert "non specificato" in msg

    def test_descriptions_optional(self) -> None:
        msg = build_summary_user_msg(_unique_tag(), "T", "doc")
        assert "Definizione MO" not in msg
        assert "Perimetro e criteri" not in msg

    def test_context_extracted_when_citation_in_doc(self) -> None:
        doc = "Paragrafo iniziale. citazione di prova Paragrafo finale."
        msg = build_summary_user_msg(_unique_tag(), "T", doc)
        assert "Contesto nel documento" in msg

    def test_no_context_when_citation_absent(self) -> None:
        msg = build_summary_user_msg(_unique_tag(), "T", "doc senza la citazione cercata")
        assert "Contesto nel documento" not in msg

    def test_table_occorrenza_uses_table_content(self) -> None:
        html = "<table><tr><td>Divisione BdT</td><td>9,4%</td></tr></table>"
        ut = UniqueTag(
            risk_model="Credito",
            mo="2503 - MO Rating",
            odc="5049 - OdC A",
            ente="E1",
            occorrenze=[TagOccorrenza(pagina="3", citazione="Tabella a pagina 3", table_content=html)],
        )
        msg = build_summary_user_msg(ut, "T", "documento senza l'etichetta della tabella")
        assert "Contenuto della tabella:" in msg
        assert html in msg
        # L'etichetta breve non deve innescare il lookup del contesto testuale.
        assert "Contesto nel documento" not in msg


# ── summarize_tag ─────────────────────────────────────────────────────────────


class TestSummarizeTag:
    def test_success(self, fake_layer: MagicMock) -> None:
        fake_layer.generate.return_value.texts = [_VALID_JSON]
        summary, elapsed = summarize_tag(fake_layer, _unique_tag(), "T", "doc", "sys", "model")
        assert isinstance(summary, TagSummary)
        assert summary.titolo == "T"
        assert elapsed >= 0.0

    def test_rm_description_forwarded(self, fake_layer: MagicMock, mocker) -> None:
        build_spy = mocker.spy(
            __import__("core.services.summary.tag_summary", fromlist=["build_summary_user_msg"]),
            "build_summary_user_msg",
        )
        fake_layer.generate.return_value.texts = [_VALID_JSON]
        summarize_tag(fake_layer, _unique_tag(), "T", "doc", "sys", "model", rm_description="desc RM")
        _, kwargs = build_spy.call_args
        assert kwargs.get("rm_description") == "desc RM" or "desc RM" in build_spy.call_args.args

    def test_llm_failure_returns_none_and_logs_cause(self, mocker, caplog) -> None:
        import logging

        mocker.patch(
            "core.services.llm_client.call_llm",
            side_effect=RuntimeError("ConnectError: connection refused"),
        )
        with caplog.at_level(logging.WARNING, logger="core.services.llm_client"):
            summary, elapsed = summarize_tag(MagicMock(), _unique_tag(), "T", "doc", "sys", "model")
        assert summary is None
        assert elapsed >= 0.0
        # La causa reale non viene più inghiottita in silenzio.
        assert "connection refused" in caplog.text
