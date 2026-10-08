"""Test `core.services.text.pages.parse_pages`."""

from __future__ import annotations

import pytest

from core.services.text.pages import parse_pages


class TestParsePages:
    def test_empty_and_none(self) -> None:
        assert parse_pages("") == []
        assert parse_pages(None) == []

    def test_single(self) -> None:
        assert parse_pages("7") == [7]

    def test_comma_list_sorted_dedup(self) -> None:
        assert parse_pages("5,3,5,1") == [1, 3, 5]

    def test_whitespace_separated(self) -> None:
        assert parse_pages("  3, 4  ") == [3, 4]

    def test_range_hyphen_expanded(self) -> None:
        assert parse_pages("3-5") == [3, 4, 5]

    def test_range_endash_expanded(self) -> None:
        assert parse_pages("3–5") == [3, 4, 5]  # noqa: RUF001

    def test_range_reversed_bounds(self) -> None:
        assert parse_pages("5-3") == [3, 4, 5]

    def test_mixed_range_and_list(self) -> None:
        assert parse_pages("1, 3-5, 8") == [1, 3, 4, 5, 8]

    def test_non_numeric_fallback_extracts_digits(self) -> None:
        assert parse_pages("pag 12") == [12]
        assert parse_pages("p.7;p.9") == [7, 9]

    @pytest.mark.parametrize("value", ["", "  ", ",", "-"])
    def test_degenerate_inputs(self, value: str) -> None:
        assert parse_pages(value) == []
