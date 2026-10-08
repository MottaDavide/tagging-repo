"""Test `evaluation.services.similarity.citation_overlap`."""

from __future__ import annotations

from evaluation.services.similarity import citation_overlap


class TestCitationOverlap:
    def test_identical_is_one(self) -> None:
        assert citation_overlap("Testo identico di prova.", "Testo identico di prova.") == 1.0

    def test_case_and_whitespace_insensitive(self) -> None:
        assert citation_overlap("Testo   di  Prova", "testo di prova") == 1.0

    def test_completely_disjoint_is_zero(self) -> None:
        assert citation_overlap("abcdef", "ghijkl") == 0.0

    def test_empty_strings_are_zero(self) -> None:
        assert citation_overlap("", "qualcosa") == 0.0
        assert citation_overlap("qualcosa", "") == 0.0
        assert citation_overlap(None, "qualcosa") == 0.0

    def test_shorter_fully_contained_scores_high(self) -> None:
        """Una citazione corta interamente contenuta in una più lunga ha overlap 1.0
        rispetto alla citazione più corta (containment), a differenza di un ratio simmetrico."""
        long_text = "Premessa introduttiva molto lunga. " * 5 + "Il nocciolo della questione è questo."
        short_text = "Il nocciolo della questione è questo."
        assert citation_overlap(long_text, short_text) == 1.0
        assert citation_overlap(short_text, long_text) == 1.0

    def test_partial_overlap_between_zero_and_one(self) -> None:
        a = "Il controllo riguarda la verifica del rispetto della facoltà sulle delibere."
        b = "Il controllo riguarda la verifica del rispetto della facoltà sui bonifici."
        score = citation_overlap(a, b)
        assert 0.0 < score < 1.0
