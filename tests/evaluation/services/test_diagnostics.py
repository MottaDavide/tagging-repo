"""Test `evaluation.services.diagnostics`: decomposizione cause FN (recall) e FP (precision)."""

from __future__ import annotations

from evaluation.models.results import Candidate, DocResult
from evaluation.services.diagnostics import diagnostics_lines, precision_causes, recall_causes

_ENTE_A = "0100788 - TOKYO BRANCH"
_ENTE_B = "0100791 - FRANKFURT BRANCH"
_CIT = "Testo di prova sufficientemente lungo e identico."


def _tag(
    rm: str = "AML",
    ente: str = _ENTE_A,
    mo: str = "M1",
    odc: str = "O1",
    pagina: str = "1",
    citazione: str = _CIT,
    tipo: str = "text",
) -> dict[str, str]:
    return {
        "Risk Model": rm,
        "Ente": ente,
        "MO": mo,
        "OdC": odc,
        "Pagina": pagina,
        "Citazione": citazione,
        "Tipo Citazione": tipo,
    }


def _c(**kw: str) -> Candidate:
    return Candidate.from_tag(_tag(**kw))


class TestRecallCauses:
    def test_one_per_category(self) -> None:
        gt = [
            _c(pagina="1"),  # 7: pred identico
            _c(pagina="2"),  # 1: nessuna pred in pagina
            _c(pagina="3"),  # 2: pred in pagina con RM diverso
            _c(pagina="4", citazione="aaaa bbbb cccc dddd eeee ffff"),  # 3: nessun overlap
            _c(pagina="5"),  # 4: ente errato
            _c(pagina="6"),  # 5: MO errato
            _c(pagina="7"),  # 6: OdC errato
            _c(pagina="8", tipo="table"),  # ignorato (non-testo)
        ]
        pred = [
            _c(pagina="1"),
            _c(pagina="3", rm="Credito"),
            _c(pagina="4", citazione="zzzz yyyy xxxx wwww vvvv uuuu"),
            _c(pagina="5", ente=_ENTE_B),
            _c(pagina="6", mo="M2"),
            _c(pagina="7", odc="O2"),
        ]
        causes = recall_causes([DocResult(doc="d", gt=gt, pred=pred)])
        assert causes["7_match_completo"] == 1
        assert causes["1_no_pred_in_pagina"] == 1
        assert causes["2_rm_diverso"] == 1
        assert causes["3_confine_span"] == 1
        assert causes["4_ente_errato"] == 1
        assert causes["5_mo_errato"] == 1
        assert causes["6_odc_errato"] == 1
        assert sum(causes.values()) == 7  # il GT tabella non è conteggiato

    def test_ignore_ente_skips_ente_cause(self) -> None:
        gt = [Candidate.from_tag(_tag(pagina="5"), ignore_ente=True)]
        pred = [Candidate.from_tag(_tag(pagina="5", ente=_ENTE_B), ignore_ente=True)]
        causes = recall_causes([DocResult(doc="d", gt=gt, pred=pred)], ignore_ente=True)
        assert causes["4_ente_errato"] == 0
        assert causes["7_match_completo"] == 1


class TestPrecisionCauses:
    def test_categories(self) -> None:
        gt = [_c(pagina="11")]  # GT su AML pag 11 → zona con GT
        fp = [
            _c(pagina="10"),  # A: zona senza GT
            _c(pagina="11", odc="O9"),  # B: zona con GT ma non matchato
            _c(pagina="12", tipo="table"),  # C: predizione-tabella
        ]
        causes = precision_causes([DocResult(doc="d", gt=gt, pred=fp, fp=fp)])
        assert causes["A_zona_senza_gt"] == 1
        assert causes["B_zona_con_gt_no_match"] == 1
        assert causes["C_pred_tabella"] == 1


class TestDiagnosticsLines:
    def test_returns_readable_lines(self) -> None:
        lines = diagnostics_lines([DocResult(doc="d", gt=[_c()], pred=[_c()])])
        text = "\n".join(lines)
        assert "CAUSE FN" in text
        assert "CAUSE FP" in text
