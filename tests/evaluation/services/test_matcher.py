"""Test `evaluation.services.matcher`."""

from __future__ import annotations

from evaluation.models.results import Candidate, Counts, DocResult
from evaluation.services.matcher import (
    aggregate_per_rm,
    aggregate_total,
    doc_rows,
    evaluate_document,
    in_rm_filter,
    in_tipo_filter,
    match_by_table_id,
    match_overlap,
    rm_rows,
)

_ENTE_A = "0100788 - TOKYO BRANCH"
_ENTE_B = "0100791 - FRANKFURT BRANCH"


def _tag(
    rm: str = "AML",
    ente: str = _ENTE_A,
    mo: str = "M1",
    odc: str = "O1",
    pagina: str = "1",
    citazione: str = "Testo di prova identico.",
    tipo: str | None = None,
    table_id: str | None = None,
) -> dict[str, str]:
    tag = {"Risk Model": rm, "Ente": ente, "MO": mo, "OdC": odc, "Pagina": pagina, "Citazione": citazione}
    if tipo is not None:
        tag["Tipo Citazione"] = tipo
    if table_id is not None:
        tag["TableId"] = table_id
    return tag


class TestInRmFilter:
    def test_accepted(self) -> None:
        tag = {"Risk Model": "AML"}
        assert in_rm_filter(tag, frozenset({"AML", "Credito"})) is True

    def test_rejected(self) -> None:
        tag = {"Risk Model": "Other"}
        assert in_rm_filter(tag, frozenset({"AML"})) is False

    def test_missing_field(self) -> None:
        assert in_rm_filter({}, frozenset({"AML"})) is False


class TestInTipoFilter:
    def test_empty_filter_accepts_all(self) -> None:
        assert in_tipo_filter({"Tipo Citazione": "image"}, frozenset()) is True

    def test_missing_field_accepted(self) -> None:
        """Tag PRED che non hanno Tipo Citazione passano sempre il filtro."""
        assert in_tipo_filter({}, frozenset({"text"})) is True

    def test_in_filter(self) -> None:
        assert in_tipo_filter({"Tipo Citazione": "table"}, frozenset({"table", "image"})) is True

    def test_not_in_filter(self) -> None:
        assert in_tipo_filter({"Tipo Citazione": "text"}, frozenset({"table"})) is False


class TestMatchOverlap:
    def test_matches_on_identical_tuple_and_citation(self) -> None:
        gt = [Candidate.from_tag(_tag())]
        pred = [Candidate.from_tag(_tag())]
        assert match_overlap(gt, pred) == [(0, 0)]

    def test_no_match_when_tuple_key_differs(self) -> None:
        gt = [Candidate.from_tag(_tag(odc="O1"))]
        pred = [Candidate.from_tag(_tag(odc="O2"))]
        assert match_overlap(gt, pred) == []

    def test_no_match_when_pages_disjoint(self) -> None:
        gt = [Candidate.from_tag(_tag(pagina="1"))]
        pred = [Candidate.from_tag(_tag(pagina="2"))]
        assert match_overlap(gt, pred) == []

    def test_match_when_pages_overlap_partially(self) -> None:
        gt = [Candidate.from_tag(_tag(pagina="5-6"))]
        pred = [Candidate.from_tag(_tag(pagina="6-7"))]
        assert match_overlap(gt, pred) == [(0, 0)]

    def test_no_match_below_threshold(self) -> None:
        gt = [Candidate.from_tag(_tag(citazione="Testo completamente diverso e non correlato."))]
        pred = [Candidate.from_tag(_tag(citazione="Altra frase senza alcun punto in comune reale."))]
        assert match_overlap(gt, pred, threshold=0.7) == []

    def test_greedy_prefers_higher_overlap(self) -> None:
        """Un solo GT, due PRED candidati ammissibili: vince quello con overlap più alto."""
        base = "Il controllo riguarda la verifica del rispetto della facoltà sulle delibere acquisite."
        gt = [Candidate.from_tag(_tag(citazione=base))]
        pred_weak = Candidate.from_tag(
            _tag(citazione="Un argomento diverso riguarda la verifica del rispetto delle norme aziendali generali.")
        )
        pred_strong = Candidate.from_tag(_tag(citazione=base))
        assert match_overlap(gt, [pred_weak, pred_strong], threshold=0.3) == [(0, 1)]

    def test_one_to_one_no_double_assignment(self) -> None:
        """Due GT identici, un solo PRED: solo un GT ottiene il match."""
        gt = [Candidate.from_tag(_tag()), Candidate.from_tag(_tag())]
        pred = [Candidate.from_tag(_tag())]
        assert len(match_overlap(gt, pred)) == 1


class TestMatchByTableId:
    def test_matches_same_tuple_and_id(self) -> None:
        gt = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1"))]
        pred = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1"))]
        assert match_by_table_id(gt, pred) == [(0, 0)]

    def test_no_match_different_id(self) -> None:
        gt = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1"))]
        pred = [Candidate.from_tag(_tag(tipo="table", table_id="p2#2"))]
        assert match_by_table_id(gt, pred) == []

    def test_no_match_different_tuple(self) -> None:
        gt = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1", odc="O1"))]
        pred = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1", odc="O2"))]
        assert match_by_table_id(gt, pred) == []

    def test_none_id_never_matches(self) -> None:
        gt = [Candidate.from_tag(_tag(tipo="table"))]
        pred = [Candidate.from_tag(_tag(tipo="table"))]
        assert match_by_table_id(gt, pred) == []

    def test_one_to_one(self) -> None:
        """Due GT stessa n-upla+id, un solo PRED: un solo match."""
        gt = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1"))] * 2
        pred = [Candidate.from_tag(_tag(tipo="table", table_id="p2#1"))]
        assert len(match_by_table_id(gt, pred)) == 1


class TestEvaluateDocument:
    def test_tp_fp_fn(self) -> None:
        gt = [_tag(pagina="1"), _tag(pagina="2")]
        pred = [_tag(pagina="1"), _tag(pagina="5")]
        result = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert result.counts.tp == 1
        assert result.counts.fp == 1
        assert result.counts.fn == 1

    def test_symmetric_dedup_of_gt_and_pred(self) -> None:
        # GT con 3 tag a contenuto identico (dup) + PRED con 2 identici: dopo dedup 1 GT, 1 PRED → 1 TP
        gt = [_tag(pagina="1"), _tag(pagina="1"), _tag(pagina="1")]
        pred = [_tag(pagina="1"), _tag(pagina="1")]
        result = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert result.counts.tp == 1
        assert result.counts.fp == 0  # le pred duplicate NON diventano FP
        assert result.counts.fn == 0  # le GT duplicate NON diventano FN

    def test_whitespace_normalized_in_labels(self) -> None:
        # GT con OdC a doppio spazio (whitespace irregolare) vs PRED a spazio singolo → match
        gt = [_tag(odc="5073 -  Ruolo  e Processi di Governo")]
        pred = [_tag(odc="5073 - Ruolo e Processi di Governo")]
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert r.counts.tp == 1
        assert r.counts.fp == 0
        assert r.counts.fn == 0

    def test_rm_filter_excludes_other_rms(self) -> None:
        gt = [_tag(rm="Other")]
        pred = [_tag(rm="AML")]
        result = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        # GT filtrato fuori, PRED resta → 0 TP, 1 FP, 0 FN
        assert result.counts.tp == 0
        assert result.counts.fp == 1
        assert result.counts.fn == 0

    def test_ignore_ente(self) -> None:
        gt = [_tag(ente=_ENTE_A)]
        pred = [_tag(ente=_ENTE_B)]
        # Con ignore_ente, X e Y collassano → 1 TP
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}), ignore_ente=True)
        assert r.counts.tp == 1
        assert r.counts.fp == 0

    def test_different_mo_or_odc_excludes_match(self) -> None:
        gt = [_tag(mo="M1", odc="O1")]
        pred = [_tag(mo="M1", odc="O2")]
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert r.counts.tp == 0
        assert r.counts.fp == 1
        assert r.counts.fn == 1

    def test_tipo_filter_applied_to_gt(self) -> None:
        gt = [
            _tag(pagina="1", tipo="text"),
            _tag(pagina="2", tipo="table", table_id="p2#1"),
        ]
        pred = [
            _tag(pagina="2", tipo="table", table_id="p2#1"),
            _tag(pagina="9", tipo="table", table_id="p9#1"),
        ]
        # Tipo=table filtra il GT di testo; le tabelle matchano per id
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}), tipo_filter=frozenset({"table"}))
        assert r.counts.tp == 1  # p2#1 ↔ p2#1
        assert r.counts.fp == 1  # p9#1 pred non matchato

    def test_table_matches_by_id_not_overlap(self) -> None:
        # Citazioni diverse (no overlap) ma stesso id-tabella → match
        gt = [_tag(pagina="2", tipo="table", table_id="p2#1", citazione="riga alfa")]
        pred = [_tag(pagina="2", tipo="table", table_id="p2#1", citazione="<tr><td>beta</td></tr>")]
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert r.counts.tp == 1

    def test_table_no_match_on_different_id(self) -> None:
        gt = [_tag(pagina="2", tipo="table", table_id="p2#1")]
        pred = [_tag(pagina="2", tipo="table", table_id="p2#2")]
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert (r.counts.tp, r.counts.fp, r.counts.fn) == (0, 1, 1)

    def test_table_without_id_never_matches(self) -> None:
        gt = [_tag(pagina="2", tipo="table")]  # nessun TableId
        pred = [_tag(pagina="2", tipo="table")]
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}))
        assert (r.counts.tp, r.counts.fp, r.counts.fn) == (0, 1, 1)

    def test_low_overlap_counts_as_fn_and_fp(self) -> None:
        gt = [_tag(citazione="Un testo con un contenuto molto specifico e dettagliato.")]
        pred = [_tag(citazione="Un altro testo su un argomento completamente diverso qui.")]
        r = evaluate_document("doc", gt, pred, frozenset({"AML"}), threshold=0.7)
        assert r.counts.tp == 0
        assert r.counts.fp == 1
        assert r.counts.fn == 1


class TestAggregatePerRm:
    def test_two_docs_two_rms(self) -> None:
        c_aml = Candidate.from_tag(_tag(rm="AML"))
        c_cr = Candidate.from_tag(_tag(rm="Credito"))
        d1 = DocResult(doc="d1", gt=[c_aml], pred=[c_aml], tp=[c_aml])
        d2 = DocResult(doc="d2", gt=[c_cr], pred=[], fn=[c_cr])
        per_rm = aggregate_per_rm([d1, d2])
        assert per_rm["AML"].tp == 1
        assert per_rm["AML"].fp == 0
        assert per_rm["Credito"].fn == 1
        assert per_rm["Credito"].tp == 0


class TestAggregateTotal:
    def test_sum(self) -> None:
        c = Candidate.from_tag(_tag())
        d1 = DocResult(doc="d1", gt=[c], pred=[c], tp=[c])
        d2 = DocResult(doc="d2", gt=[], pred=[c], fp=[c])
        total = aggregate_total([d1, d2])
        assert total.tp == 1
        assert total.fp == 1
        assert total.fn == 0


class TestDocRows:
    def test_sorted_by_recall_ascending(self) -> None:
        c = Candidate.from_tag(_tag())
        perfect = DocResult(doc="perfect", gt=[c], pred=[c], tp=[c])
        empty = DocResult(doc="zero-recall", gt=[c], pred=[], fn=[c])
        rows = doc_rows([perfect, empty])
        assert [d.doc for d, _ in rows] == ["zero-recall", "perfect"]
        assert rows[0][1].recall == 0.0
        assert rows[1][1].recall == 1.0


class TestRmRows:
    def test_alphabetical_plus_totale_last(self) -> None:
        per_rm = {"Credito": Counts(tp=1), "AML": Counts(fp=2)}
        total = Counts(tp=1, fp=2)
        rows = rm_rows(per_rm, total)
        assert [label for label, _ in rows] == ["AML", "Credito", "TOTALE"]
        assert rows[-1][1].counts == total
