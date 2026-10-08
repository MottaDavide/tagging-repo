"""Test `evaluation.services.dedup`: dedup per contenuto (fan-out preservato)."""

from __future__ import annotations

from evaluation.models.results import Candidate
from evaluation.services.dedup import candidate_key, dedup_candidates, dedup_raw_tags

_ENTE_A = "0105740 - Divisione BdT"
_ENTE_B = "0105741 - Divisione CIB"


def _tag(
    rm: str = "Credito",
    ente: str = _ENTE_A,
    mo: str = "M1",
    odc: str = "O1",
    pagina: str = "17",
    citazione: str = "Lo stock scaduto complessivo aumenta.",
    id_estratto: str | None = None,
) -> dict[str, str]:
    tag = {"Risk Model": rm, "Ente": ente, "MO": mo, "OdC": odc, "Pagina": pagina, "Citazione": citazione}
    if id_estratto is not None:
        tag["id_estratto"] = id_estratto  # ID tecnico: NON deve entrare nella chiave
    return tag


class TestDedupRawTags:
    def test_collapses_content_identical_differing_only_by_technical_id(self) -> None:
        tags = [_tag(id_estratto="e0121"), _tag(id_estratto="e0122"), _tag(id_estratto="e0123")]
        out, removed = dedup_raw_tags(tags)
        assert len(out) == 1
        assert removed == 2
        assert out[0]["id_estratto"] == "e0121"  # tiene la prima occorrenza

    def test_preserves_fanout_on_different_ente(self) -> None:
        tags = [_tag(ente=_ENTE_A), _tag(ente=_ENTE_B)]
        out, removed = dedup_raw_tags(tags)
        assert len(out) == 2
        assert removed == 0

    def test_preserves_fanout_on_different_odc(self) -> None:
        out, removed = dedup_raw_tags([_tag(odc="O1"), _tag(odc="O2")])
        assert len(out) == 2
        assert removed == 0

    def test_different_citation_kept(self) -> None:
        out, removed = dedup_raw_tags([_tag(citazione="testo A"), _tag(citazione="testo B")])
        assert len(out) == 2
        assert removed == 0

    def test_empty(self) -> None:
        assert dedup_raw_tags([]) == ([], 0)


class TestDedupCandidates:
    def test_collapses_identical_candidates(self) -> None:
        c = Candidate.from_tag(_tag())
        assert len(dedup_candidates([c, c, c])) == 1

    def test_ente_name_normalized_in_key(self) -> None:
        # stesso ente per NOME (senza codice) vs canonico → stessa chiave → collassa
        by_code = Candidate.from_tag(_tag(ente="0105740 - Divisione BdT"))
        by_name = Candidate.from_tag(_tag(ente="Divisione BdT"))
        assert candidate_key(by_code) == candidate_key(by_name)
        assert len(dedup_candidates([by_code, by_name])) == 1
