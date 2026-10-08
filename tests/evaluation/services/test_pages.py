"""Test `evaluation.services.pages`."""

from __future__ import annotations

from evaluation.services.pages import normalize_pages, pages_set


class TestNormalizePages:
    def test_none_or_empty(self) -> None:
        assert normalize_pages(None) == ""
        assert normalize_pages("") == ""

    def test_single_number(self) -> None:
        assert normalize_pages("5") == "5"

    def test_comma_separated_sorted_deduplicated(self) -> None:
        assert normalize_pages("5,3,5,1") == "1,3,5"

    def test_range_expanded(self) -> None:
        assert normalize_pages("3-6") == "3,4,5,6"

    def test_en_dash_range(self) -> None:
        # EN DASH (U+2013) accepted come separatore di range
        assert normalize_pages("3–6") == "3,4,5,6"  # noqa: RUF001 (EN DASH intenzionale)

    def test_range_too_wide_preserved(self) -> None:
        """Se range > 20, non espande (limite difensivo)."""
        out = normalize_pages("1-100")
        # Non espande, ma estrae i 2 numeri 1 e 100
        nums = [int(p) for p in out.split(",")]
        assert nums == [1, 100]

    def test_mixed_ranges_and_singles(self) -> None:
        assert normalize_pages("3-5, 7") == "3,4,5,7"


class TestPagesSet:
    def test_returns_frozenset(self) -> None:
        out = pages_set("1,3,5")
        assert isinstance(out, frozenset)
        assert out == frozenset({1, 3, 5})

    def test_range_in_set(self) -> None:
        assert pages_set("1-3") == frozenset({1, 2, 3})

    def test_empty(self) -> None:
        assert pages_set("") == frozenset()
        assert pages_set(None) == frozenset()
