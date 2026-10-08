"""Test `core.services.dynamic_summary.resources.load_dynamic_summary_resources`."""

from __future__ import annotations

from pathlib import Path

import pytest

import core.services.dynamic_summary.resources as resources_mod
import core.services.registry.risk_models as rm_mod
from core.models.registry.hierarchy import Hierarchy
from core.resources.dynamic_summary_system import DYNAMIC_SUMMARY_SYSTEM


class TestLoadDynamicSummaryResources:
    def test_uses_default_loaders(self, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rm_mod, "RM_CRITERIA", (fixtures_dir / "tiny_rm_criteria.md").read_text(encoding="utf-8"))

        risk_models, hierarchy, system_prompt = resources_mod.load_dynamic_summary_resources()

        names = [rm.name for rm in risk_models]
        assert "Credito" in names
        assert "AML" in names

        assert isinstance(hierarchy, Hierarchy)
        assert hierarchy.is_supported("Credito")

        assert system_prompt == DYNAMIC_SUMMARY_SYSTEM
