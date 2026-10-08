"""Test `core.services.tagging.classify`: classify+extract (LLM mockato)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.models.registry.hierarchy import MO, Hierarchy, OdC, RMHierarchy
from core.models.tagging.candidates import BranoCandidate
from core.models.tagging.stages import BranoOdC, ClassifiedBrano, ClassifyOutput
from core.models.tagging.stats import TaggerStats
from core.services.tagging.classify import classify_candidates


def _hierarchy() -> Hierarchy:
    mo_a = MO(
        code="2503",
        name="MO Rating",
        description="",
        odcs=(OdC(code="5049", name="Modelli", description=""), OdC(code="5050", name="Rating", description="")),
    )
    mo_b = MO(
        code="2578", name="MO Concessione", description="", odcs=(OdC(code="4602", name="Delibera", description=""),)
    )
    return Hierarchy(rms={"Credito": RMHierarchy(risk_model="Credito", mos=(mo_a, mo_b))})


def _unit(tipo: str = "text", table_id: str | None = None, brano: str = "testo della sezione") -> BranoCandidate:
    return BranoCandidate(
        risk_model="Credito", ente=None, brano=brano, pagina="1", rationale="r", tipo_citazione=tipo, table_id=table_id
    )


def _out(*brani: ClassifiedBrano) -> ClassifyOutput:
    return ClassifyOutput(brani=list(brani))


class TestClassifyCandidates:
    def test_extracts_brano_and_derives_mo(self, mocker) -> None:
        out = _out(
            ClassifiedBrano(
                citazione="estratto verbatim del brano", odc=[BranoOdC(odc_label="5050 - Rating", confidence="high")]
            )
        )
        mocker.patch("core.services.llm_client.call_llm", return_value=out)
        stats = TaggerStats()
        cands = classify_candidates(MagicMock(), [_unit()], _hierarchy(), "m", stats)
        assert len(cands) == 1
        c = cands[0]
        assert c.brano == "estratto verbatim del brano"
        assert c.odc == "5050 - Rating"
        assert c.mo == "2503 - MO Rating"  # MO derivato dall'albero
        assert c.ente is None
        assert stats.llm_calls == 1

    def test_same_brano_multiple_odc_cross_mo(self, mocker) -> None:
        out = _out(
            ClassifiedBrano(
                citazione="brano condiviso",
                odc=[
                    BranoOdC(odc_label="5050 - Rating", confidence="high"),
                    BranoOdC(odc_label="4602 - Delibera", confidence="medium"),
                ],
            )
        )
        mocker.patch("core.services.llm_client.call_llm", return_value=out)
        cands = classify_candidates(MagicMock(), [_unit()], _hierarchy(), "m", TaggerStats())
        assert len(cands) == 2
        assert {c.odc for c in cands} == {"5050 - Rating", "4602 - Delibera"}
        assert {c.mo for c in cands} == {"2503 - MO Rating", "2578 - MO Concessione"}
        assert all(c.brano == "brano condiviso" for c in cands)  # stesso estratto, non frammentato

    def test_table_keeps_table_text_and_id(self, mocker) -> None:
        out = _out(
            ClassifiedBrano(
                citazione="estratto ignorato per le tabelle",
                odc=[BranoOdC(odc_label="5050 - Rating", confidence="high")],
            )
        )
        mocker.patch("core.services.llm_client.call_llm", return_value=out)
        cands = classify_candidates(
            MagicMock(),
            [_unit(tipo="table", table_id="p1#1", brano="testo tabella intera")],
            _hierarchy(),
            "m",
            TaggerStats(),
        )
        assert len(cands) == 1
        assert cands[0].brano == "testo tabella intera"
        assert cands[0].table_id == "p1#1"

    def test_unmapped_odc_label_skipped(self, mocker) -> None:
        """Difesa in profondità: un'etichetta non riconducibile a nessun OdC viene scartata.

        Con il `response_format` dinamico (Literal sulle etichette valide del RM) l'LLM non
        dovrebbe più poter emettere un'etichetta fuori lista, ma `_expand` resta robusto anche
        se succedesse (es. fallback statico in caso di errore nella costruzione del modello)."""
        out = _out(ClassifiedBrano(citazione="x", odc=[BranoOdC(odc_label="9999 - Non Esistente", confidence="low")]))
        mocker.patch("core.services.llm_client.call_llm", return_value=out)
        assert classify_candidates(MagicMock(), [_unit()], _hierarchy(), "m", TaggerStats()) == []

    def test_empty_brani_no_candidates(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm", return_value=_out())
        assert classify_candidates(MagicMock(), [_unit()], _hierarchy(), "m", TaggerStats()) == []

    def test_unsupported_rm_skipped(self, mocker) -> None:
        spy = mocker.patch("core.services.llm_client.call_llm")
        cand = BranoCandidate(risk_model="Governance", ente=None, brano="x", pagina="1", rationale="r")
        assert classify_candidates(MagicMock(), [cand], _hierarchy(), "m", TaggerStats()) == []
        spy.assert_not_called()
