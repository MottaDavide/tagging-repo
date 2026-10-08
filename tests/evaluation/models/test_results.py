"""Test dataclass `evaluation.models.results`: Candidate, Counts, Metrics, DocResult."""

from __future__ import annotations

from evaluation.models.results import Candidate, Counts, DocResult, Metrics


class TestCandidate:
    def test_from_tag_basic(self) -> None:
        tag = {
            "Risk Model": "AML",
            "Ente": "0101025 - Gruppo ISP",
            "MO": "8838 - MO Gestione AML",
            "OdC": "5069 - Adeguata verifica della clientela",
            "Pagina": "5",
            "Citazione": "testo",
        }
        c = Candidate.from_tag(tag)
        assert c.rm == "AML"
        assert c.ente == "0101025 - Gruppo ISP"
        assert c.mo == "8838 - MO Gestione AML"
        assert c.odc == "5069 - Adeguata verifica della clientela"
        assert c.citazione == "testo"

    def test_from_tag_pages_as_set(self) -> None:
        tag = {"Risk Model": "AML", "Pagina": "3-5"}
        c = Candidate.from_tag(tag)
        assert c.pages == frozenset({3, 4, 5})

    def test_from_tag_ignore_ente(self) -> None:
        tag = {"Risk Model": "AML", "Ente": "0101025 - Gruppo ISP", "Pagina": "5"}
        c = Candidate.from_tag(tag, ignore_ente=True)
        assert c.ente is None

    def test_from_tag_ente_canonicalized(self) -> None:
        tag = {"Risk Model": "AML", "Ente": "0141020 - CONTROLLI BDT", "Pagina": "1"}
        c = Candidate.from_tag(tag)
        assert c.ente == "0141020 - CONTROLLI BDT"

    def test_from_tag_ente_resolved_by_name(self) -> None:
        """La GT riporta l'ente per NOME: va ricondotto al valore canonico dell'enum."""
        tag = {"Risk Model": "Credito", "Ente": "Divisione BdT", "Pagina": "1"}
        c = Candidate.from_tag(tag)
        assert c.ente == "0105740 - Divisione BdT"

    def test_from_tag_tipo(self) -> None:
        assert Candidate.from_tag({"Tipo Citazione": "Table"}).tipo == "table"
        assert Candidate.from_tag({}).tipo == ""

    def test_from_tag_table_id(self) -> None:
        assert Candidate.from_tag({"TableId": "p9#2"}).table_id == "p9#2"
        assert Candidate.from_tag({}).table_id is None

    def test_tuple_key(self) -> None:
        tag = {"Risk Model": "AML", "Ente": "0141020 - CONTROLLI BDT", "MO": "M1", "OdC": "O1", "Pagina": "1"}
        c = Candidate.from_tag(tag)
        assert c.tuple_key == ("AML", "0141020 - CONTROLLI BDT", "M1", "O1")

    def test_tuple_key_ignore_ente(self) -> None:
        tag = {"Risk Model": "AML", "Ente": "0141020 - CONTROLLI BDT", "MO": "M1", "OdC": "O1", "Pagina": "1"}
        c = Candidate.from_tag(tag, ignore_ente=True)
        assert c.tuple_key == ("AML", None, "M1", "O1")

    def test_missing_fields_default_to_empty_string(self) -> None:
        c = Candidate.from_tag({})
        assert c.rm == ""
        assert c.mo == ""
        assert c.odc == ""
        assert c.citazione == ""
        assert c.pages == frozenset()


class TestCounts:
    def test_defaults_zero(self) -> None:
        c = Counts()
        assert (c.tp, c.fp, c.fn) == (0, 0, 0)

    def test_with_values(self) -> None:
        c = Counts(tp=3, fp=2, fn=1)
        assert c.tp == 3
        assert c.fp == 2
        assert c.fn == 1


class TestMetrics:
    def test_perfect_match(self) -> None:
        m = Metrics.from_counts(Counts(tp=10, fp=0, fn=0))
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0

    def test_zero_division_safe(self) -> None:
        m = Metrics.from_counts(Counts())
        assert m.precision == 0.0
        assert m.recall == 0.0
        assert m.f1 == 0.0

    def test_only_fp(self) -> None:
        m = Metrics.from_counts(Counts(tp=0, fp=5, fn=0))
        assert m.precision == 0.0
        assert m.recall == 0.0

    def test_balanced(self) -> None:
        m = Metrics.from_counts(Counts(tp=2, fp=1, fn=1))
        assert m.precision == 2 / 3
        assert m.recall == 2 / 3
        assert abs(m.f1 - 2 / 3) < 1e-9


class TestDocResult:
    def test_counts_from_list_lengths(self) -> None:
        g1 = Candidate.from_tag({"Risk Model": "X", "Pagina": "1"})
        g2 = Candidate.from_tag({"Risk Model": "X", "Pagina": "2"})
        p1 = Candidate.from_tag({"Risk Model": "X", "Pagina": "1"})
        p3 = Candidate.from_tag({"Risk Model": "X", "Pagina": "3"})
        r = DocResult(doc="d", gt=[g1, g2], pred=[p1, p3], tp=[g1], fp=[p3], fn=[g2])
        assert r.counts.tp == 1
        assert r.counts.fp == 1
        assert r.counts.fn == 1

    def test_empty_doc(self) -> None:
        r = DocResult(doc="empty", gt=[], pred=[])
        assert r.counts.tp == 0
        assert r.counts.fp == 0
        assert r.counts.fn == 0
