"""Test dataclass `core.models.tagging.stats`."""

from __future__ import annotations

from core.models.tagging.stats import TaggerStats


class TestTaggerStats:
    def test_defaults_zero(self) -> None:
        s = TaggerStats()
        assert s.input_chars == 0
        assert s.llm_calls == 0
        assert s.llm_time_s == 0.0

    def test_incremental_update(self) -> None:
        s = TaggerStats()
        s.llm_calls += 1
        s.llm_time_s += 2.5
        assert s.llm_calls == 1
        assert s.llm_time_s == 2.5
