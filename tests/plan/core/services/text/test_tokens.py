"""Test `core.services.text.tokens.count_tokens`."""

from __future__ import annotations

from core.services.text.tokens import count_tokens


class TestCountTokens:
    def test_empty_string_returns_zero(self) -> None:
        assert count_tokens("") == 0

    def test_short_text_returns_positive(self) -> None:
        assert count_tokens("hello world") > 0

    def test_longer_text_returns_more_tokens(self) -> None:
        short = count_tokens("foo")
        long = count_tokens("foo bar baz qux quux corge grault garply")
        assert long > short
