"""Test `core.services.dynamic_summary.grouping`."""

from __future__ import annotations

from typing import Any

from core.models.dynamic_summary import DynamicSummaryEntry, DynamicTagSummary, TagExtract, TemaEstratti
from core.services.dynamic_summary.grouping import group_input_tags


def _tag(
    rm: str,
    mo: str | None,
    odc: str | None,
    ente: str | None,
    pagina: str,
    citazione: str,
    documento: str | None = None,
    doc_key: str = "documento",
) -> dict[str, Any]:
    tag: dict[str, Any] = {
        "Risk Model": rm,
        "MO": mo,
        "OdC": odc,
        "Ente": ente,
        "Pagina": pagina,
        "Citazione": citazione,
    }
    if documento is not None:
        tag[doc_key] = documento
    return tag


class TestGroupInputTags:
    def test_empty(self) -> None:
        assert group_input_tags([]) == []

    def test_skips_incomplete_tags(self) -> None:
        tags = [
            _tag("Credito", None, None, "E1", "1", "c"),  # solo RM
            _tag("AML", None, None, "E2", "2", "c"),  # MO/OdC nulli
            _tag("Credito", "2503 - MO", None, "E1", "3", "c"),  # OdC nullo
        ]
        assert group_input_tags(tags) == []

    def test_groups_by_quadruple(self) -> None:
        tags = [
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "c1"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "2", "c2"),  # stessa quadrupla
            _tag("Credito", "2503 - MO", "5049 - OdC", "E2", "3", "c3"),  # ente diverso
        ]
        result = group_input_tags(tags)
        assert len(result) == 2
        first = result[0]
        assert (first.risk_model, first.mo, first.odc, first.ente) == ("Credito", "2503 - MO", "5049 - OdC", "E1")
        assert len(first.estratti) == 2
        assert result[1].ente == "E2"

    def test_preserves_first_appearance_order(self) -> None:
        tags = [
            _tag("AML", "8838 - MO", "1 - O", "Z", "1", "c"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "A", "1", "c"),
        ]
        result = group_input_tags(tags)
        assert [r.risk_model for r in result] == ["AML", "Credito"]

    def test_dedup_identical_extracts(self) -> None:
        tags = [
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "stessa", documento="doc.pdf"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "stessa", documento="doc.pdf"),  # duplicato esatto
        ]
        result = group_input_tags(tags)
        assert len(result) == 1
        assert len(result[0].estratti) == 1

    def test_same_citation_different_document_kept(self) -> None:
        tags = [
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "stessa", documento="a.pdf"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "stessa", documento="b.pdf"),  # doc diverso
        ]
        result = group_input_tags(tags)
        assert len(result) == 1
        assert len(result[0].estratti) == 2

    def test_ente_none_is_valid_group(self) -> None:
        tags = [_tag("Credito", "2503 - MO", "5049 - OdC", None, "1", "c")]
        result = group_input_tags(tags)
        assert len(result) == 1
        assert result[0].ente is None

    def test_documento_key_variants(self) -> None:
        tags = [
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "a", documento="x.pdf", doc_key="Documento"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "E2", "2", "b", documento="y.pdf", doc_key="fonte"),
        ]
        result = group_input_tags(tags)
        assert result[0].estratti[0].documento == "x.pdf"
        assert result[1].estratti[0].documento == "y.pdf"


def _make_entry(estratti: list[TagExtract]) -> DynamicSummaryEntry:
    return DynamicSummaryEntry(
        risk_model="Credito",
        mo="2503",
        odc="5049",
        ente="E1",
        n_estratti=len(estratti),
        estratti=estratti,
        analisi=DynamicTagSummary(
            titolo="T",
            sintesi="S",
            temi=[TemaEstratti(riferimento="R", descrizione="D")],
            quadro_complessivo="Q",
        ),
    )


class TestDynamicSummaryEntryDocumenti:
    def test_documenti_distinct_and_ordered(self) -> None:
        estratti = [
            TagExtract(documento="b.pdf", pagina="1", citazione="a"),
            TagExtract(documento="a.pdf", pagina="2", citazione="b"),
            TagExtract(documento="b.pdf", pagina="3", citazione="c"),  # ripetuto
            TagExtract(documento=None, pagina="4", citazione="d"),  # senza documento
        ]
        entry = _make_entry(estratti)
        assert entry.documenti == ["b.pdf", "a.pdf"]

    def test_documenti_empty_when_no_documento(self) -> None:
        estratti = [TagExtract(documento=None, pagina="1", citazione="c")]
        entry = _make_entry(estratti)
        assert entry.documenti == []

    def test_documenti_single(self) -> None:
        estratti = [TagExtract(documento="x.pdf", pagina="1", citazione="c")]
        entry = _make_entry(estratti)
        assert entry.documenti == ["x.pdf"]
