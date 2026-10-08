"""Test `core.{models,services}.registry.risk_models`: dataclass + loader + canonicalize."""

from __future__ import annotations

from pathlib import Path

import pytest

import core.services.registry.risk_models as rm_mod
from core.models.registry.risk_models import RiskModel
from core.services.registry.risk_models import canonicalize_rm, load_risk_models_from_resources


class TestRiskModelDataclass:
    def test_frozen_dataclass(self) -> None:
        rm = RiskModel(name="X", criteria="Y")
        assert rm.name == "X"
        assert rm.criteria == "Y"
        with pytest.raises(AttributeError):
            rm.name = "Z"  # type: ignore[misc]


class TestCanonicalizeRm:
    def test_aml_lowercase(self) -> None:
        assert canonicalize_rm("aml") == "AML"

    def test_aml_capitalized(self) -> None:
        assert canonicalize_rm("AML") == "AML"

    def test_anti_financial_crime_to_aml(self) -> None:
        assert canonicalize_rm("Anti Financial Crime") == "AML"
        assert canonicalize_rm("anti financial crime") == "AML"

    def test_credito_lowercase(self) -> None:
        assert canonicalize_rm("credito") == "Credito"

    def test_unknown_returns_stripped_input(self) -> None:
        assert canonicalize_rm("  Operational Risk  ") == "Operational Risk"


class TestLoadRiskModelsFromMarkdown:
    def test_loads_from_fixture(self, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rm_mod, "RM_CRITERIA", (fixtures_dir / "tiny_rm_criteria.md").read_text(encoding="utf-8"))
        models = load_risk_models_from_resources()
        names = [m.name for m in models]
        assert "Credito" in names
        assert "AML" in names

    def test_empty_or_invalid_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rm_mod, "RM_CRITERIA", "nessun heading qui")
        with pytest.raises(ValueError, match="Nessun risk model trovato in RM_CRITERIA"):
            load_risk_models_from_resources()

    def test_criteria_text_preserved(self, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rm_mod, "RM_CRITERIA", (fixtures_dir / "tiny_rm_criteria.md").read_text(encoding="utf-8"))
        models = load_risk_models_from_resources()
        credito = next(m for m in models if m.name == "Credito")
        assert "concessione" in credito.criteria.lower()
