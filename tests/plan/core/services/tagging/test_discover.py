"""Test `core.services.tagging.discover`: discovery per unità + gate RM (LLM mockato)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.models.tagging.stages import RMGateAssignment, RMGateOutput
from core.models.tagging.stats import TaggerStats
from core.services.tagging.discover import discover_candidates

_MD = (
    "[PAGE 1]\n# Sez A\ntesto su credito e sconfini\n"
    "<table><tr><td>«ENTE[a|Divisione BdT]» dati</td></tr>"
    "<tr><td>«ENTE[b|Divisione CIB]» dati</td></tr></table>\n"
)


def _out(*rms: str) -> RMGateOutput:
    return RMGateOutput(
        assignments=[RMGateAssignment(risk_model=rm, confidence="high", reasoning="r") for rm in rms]  # type: ignore[arg-type]
    )


class TestDiscoverCandidates:
    def test_candidate_per_unit_and_rm(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm", return_value=_out("Credito"))
        stats = TaggerStats()
        cands = discover_candidates(MagicMock(), _MD, "m", stats)
        # 2 unita' (sezione + tabella) x 1 RM = 2 candidati
        assert len(cands) == 2
        assert {c.risk_model for c in cands} == {"Credito"}
        assert stats.n_tag_rm_tags == 2
        assert stats.llm_calls == 2

    def test_table_unit_carries_id_and_tipo(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm", return_value=_out("Credito"))
        cands = discover_candidates(MagicMock(), _MD, "m", TaggerStats())
        table = next(c for c in cands if c.tipo_citazione == "table")
        assert table.table_id == "p1#1"
        section = next(c for c in cands if c.tipo_citazione == "text")
        assert section.table_id is None
        assert section.pagina == "1"
        assert "credito" in section.brano.lower()

    def test_multi_rm_expands(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm", return_value=_out("Credito", "AML"))
        cands = discover_candidates(MagicMock(), _MD, "m", TaggerStats())
        assert len(cands) == 4  # 2 unita' x 2 RM

    def test_empty_assignments_no_candidates(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm", return_value=_out())
        stats = TaggerStats()
        cands = discover_candidates(MagicMock(), _MD, "m", stats)
        assert cands == []
        assert stats.llm_calls == 2  # ogni unità è comunque interrogata

    def test_llm_failure_skips_unit(self, mocker) -> None:
        mocker.patch("core.services.llm_client.call_llm", side_effect=RuntimeError("boom"))
        cands = discover_candidates(MagicMock(), _MD, "m", TaggerStats())
        assert cands == []

    def test_low_entity_table_is_gated_out(self, mocker) -> None:
        """Una tabella con < 2 enti-riga non diventa candidato (gate tabelle)."""
        md = "[PAGE 1]\n# Sez\ntesto\n<table><tr><td>tabella generica senza enti</td></tr></table>\n"
        mocker.patch("core.services.llm_client.call_llm", return_value=_out("Credito"))
        cands = discover_candidates(MagicMock(), md, "m", TaggerStats())
        # solo la sezione di testo diventa candidato; la tabella è scartata
        assert all(c.tipo_citazione != "table" for c in cands)
        assert len(cands) == 1
