"""Test `core.resources.builders`."""

from __future__ import annotations

from core.resources.builders import (
    build_img_table_user_prompt,
)


class TestBuildImgTableUserPrompt:
    def test_substitutes_placeholders(self) -> None:
        out = build_img_table_user_prompt(page_number=42, figures_json='[{"x":1}]', tables_json="[]")
        assert "42" in out
        assert '{"x":1}' in out
