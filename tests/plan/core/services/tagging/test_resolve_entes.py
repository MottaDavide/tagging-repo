"""Test `core.services.tagging.resolve_entes`: fan-out ente ancorato al pool locale (LLM mockato)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.models.tagging.candidates import BranoCandidate
from core.models.tagging.stages import EnteSelection
from core.models.tagging.stats import TaggerStats
from core.services.registry.enti import ente_name_key
from core.services.tagging.resolve_entes import (
    _drop_ungrounded_disfavored,
    _is_disfavored,
    _table_roster_entities,
    resolve_entes,
)

_GRUPPO = ente_name_key("Gruppo ISP")

# pag 1: Divisione BdT + Divisione CIB ; pag 2: solo Divisione BdT
_DOC = (
    "[PAGE 1]\n"
    "«ENTE[BdT|Divisione BdT]» controlli e «ENTE[CIB|Divisione CIB]»\n"
    "[PAGE 2]\n"
    "testo pag 2 «ENTE[BdT|Divisione BdT]»\n"
)
_DOC_NO_ENTI = "[PAGE 1]\ntesto senza alcun ente annotato\n"
_BDT = "0105740 - Divisione BdT"
_CIB = "0105741 - Divisione CIB"


def _cand(pagina: str = "1", brano: str = "brano di prova") -> BranoCandidate:
    return BranoCandidate(risk_model="Credito", ente=None, brano=brano, pagina=pagina, rationale="r", mo="M", odc="O")


def _table_cand(entities: tuple[str, ...], pagina: str = "1", brano: str = "tabella") -> BranoCandidate:
    return BranoCandidate(
        risk_model="Credito",
        ente=None,
        brano=brano,
        pagina=pagina,
        rationale="r",
        mo="M",
        odc="O",
        tipo_citazione="table",
        table_id="p1#1",
        table_entities=entities,
    )


class TestResolveEntes:
    def test_selects_and_emits_canonical(self, mocker) -> None:
        # pag 1 ha 2 candidati (BdT, CIB) → l'LLM sceglie tra i candidati locali
        mocker.patch("core.services.llm_client.call_llm", return_value=EnteSelection(enti=["Divisione BdT"]))
        out = resolve_entes(MagicMock(), [_cand("1")], _DOC, "m", TaggerStats())
        assert len(out) == 1
        assert out[0].ente == _BDT  # forma canonica (enum), non la grezza

    def test_single_local_candidate_skips_llm(self, mocker) -> None:
        # pag 2 ha un solo candidato locale (BdT) → assegnazione deterministica, nessuna call LLM
        call = mocker.patch("core.services.llm_client.call_llm")
        stats = TaggerStats()
        out = resolve_entes(MagicMock(), [_cand("2")], _DOC, "m", stats)
        assert [c.ente for c in out] == [_BDT]
        call.assert_not_called()
        assert stats.llm_calls == 0

    def test_selection_restricted_to_local_pool(self, mocker) -> None:
        # su pag 2 il pool è {BdT}: anche se l'LLM proponesse CIB, resta fuori pool → BdT deterministico
        mocker.patch("core.services.llm_client.call_llm", return_value=EnteSelection(enti=["Divisione CIB"]))
        out = resolve_entes(MagicMock(), [_cand("2")], _DOC, "m", TaggerStats())
        assert [c.ente for c in out] == [_BDT]

    def test_multi_ente_fanout(self, mocker) -> None:
        mocker.patch(
            "core.services.llm_client.call_llm",
            return_value=EnteSelection(enti=["Divisione BdT", "Divisione CIB"]),
        )
        out = resolve_entes(MagicMock(), [_cand("1")], _DOC, "m", TaggerStats())
        assert {c.ente for c in out} == {_BDT, _CIB}

    def test_filters_out_of_pool(self, mocker) -> None:
        mocker.patch(
            "core.services.llm_client.call_llm",
            return_value=EnteSelection(enti=["Divisione BdT", "Ente Inventato Non Nel Documento"]),
        )
        out = resolve_entes(MagicMock(), [_cand("1")], _DOC, "m", TaggerStats())
        assert [c.ente for c in out] == [_BDT]

    def test_titular_fallback_when_selection_empty(self, mocker) -> None:
        # pool multiplo su pag 1, ma l'LLM non seleziona nulla → fallback titolare (copertina, più frequente)
        mocker.patch("core.services.llm_client.call_llm", return_value=EnteSelection(enti=[]))
        out = resolve_entes(MagicMock(), [_cand("1")], _DOC, "m", TaggerStats())
        assert out[0].ente == _BDT

    def test_no_ente_when_document_has_none(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm")
        stats = TaggerStats()
        out = resolve_entes(MagicMock(), [_cand("1")], _DOC_NO_ENTI, "m", stats)
        assert out[0].ente is None
        assert stats.n_tags_no_ente == 1


class TestTableRosterFanout:
    def test_table_fans_out_to_all_row_entities_without_llm(self, mocker) -> None:
        # tabella "di risultati per ente" (≥2 enti-riga) → un tag per riga, nessuna call LLM
        call = mocker.patch("core.services.llm_client.call_llm")
        stats = TaggerStats()
        cand = _table_cand(("Divisione BdT", "Divisione CIB"))
        out = resolve_entes(MagicMock(), [cand], _DOC, "m", stats)
        assert {c.ente for c in out} == {_BDT, _CIB}
        call.assert_not_called()
        assert stats.llm_calls == 0

    def test_table_roster_dedups_by_canonical(self, mocker) -> None:
        # varianti dello stesso ente (nome/casing) collassano in un solo tag
        mocker.patch("core.services.llm_client.call_llm")
        cand = _table_cand(("Divisione BdT", "DIVISIONE BDT", "Divisione CIB"))
        out = resolve_entes(MagicMock(), [cand], _DOC, "m", TaggerStats())
        assert sorted(c.ente for c in out) == sorted({_BDT, _CIB})

    def test_helper_none_below_threshold_or_non_table(self) -> None:
        assert _table_roster_entities(_table_cand(("Divisione BdT",))) is None  # 1 sola riga
        assert _table_roster_entities(_cand()) is None  # span-testo
        assert _table_roster_entities(_table_cand(("Divisione BdT", "Divisione CIB"))) == [
            "Divisione BdT",
            "Divisione CIB",
        ]


_AFC = "0101167 - DC DIREZIONE ANTI FINANCIAL CRIME"


class TestDisfavored:
    def test_is_disfavored(self) -> None:
        assert _is_disfavored(_GRUPPO)  # generico
        assert _is_disfavored(_AFC)  # controllore: Anti Financial Crime
        assert _is_disfavored("0139665 - SECOND LEVEL CONTROLS & DATA GOVERNANC V")
        assert _is_disfavored("0113788 - Chief Compliance Officer")
        assert not _is_disfavored("0105740 - Divisione BdT")
        assert not _is_disfavored("0105738 - Chief Lending Officer")  # business, non controllo


class TestDropUngroundedDisfavored:
    def _cand_ente(self, ente: str, pagina: str = "1") -> BranoCandidate:
        c = _cand(pagina)
        c.ente = ente
        return c

    def test_drops_gruppo_isp_not_on_page(self) -> None:
        cands = [self._cand_ente(_GRUPPO, "1")]
        out = _drop_ungrounded_disfavored(cands, {1: ["Divisione BdT"]})  # Gruppo ISP non marcato in pag 1
        assert out == []

    def test_drops_anti_financial_crime_not_on_page(self) -> None:
        cands = [self._cand_ente(_AFC, "1")]
        out = _drop_ungrounded_disfavored(cands, {1: ["Divisione BdT"]})  # controllore non ancorato → rimosso
        assert out == []

    def test_keeps_controller_when_on_page(self) -> None:
        cands = [self._cand_ente(_AFC, "1")]
        out = _drop_ungrounded_disfavored(cands, {1: ["DC DIREZIONE ANTI FINANCIAL CRIME"]})  # ancorato
        assert len(out) == 1

    def test_keeps_specific_ente_even_if_not_on_page(self) -> None:
        cands = [self._cand_ente(_BDT, "1")]  # non sfavorito → mai rimosso
        assert _drop_ungrounded_disfavored(cands, {1: ["Divisione CIB"]}) == cands

    def test_via_resolve_entes_titular_gruppo_dropped(self, mocker) -> None:
        # doc con solo Gruppo ISP in copertina (titolare); brano su pag 2 senza marker → pool = {Gruppo ISP}
        # deterministico, ma non ancorato alla pagina del brano → rimosso
        doc = "[PAGE 1]\ncopertina «ENTE[ISP|Gruppo ISP]»\n[PAGE 2]\nfinding senza ente\n"
        mocker.patch("core.services.llm_client.call_llm")
        out = resolve_entes(MagicMock(), [_cand("2")], doc, "m", TaggerStats())
        assert out == []
