"""Smoke test: `core.config` espone Path attesi e radicati in `PROJECT_DIR`."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from core import config


def test_project_dir_is_absolute_path() -> None:
    assert isinstance(config.PROJECT_DIR, Path)
    assert config.PROJECT_DIR.is_absolute()


def test_data_dir_defaults_under_project_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Senza `TAGGING_DATA_DIR`, `DATA_DIR` ricade su `PROJECT_DIR/"data"`."""
    monkeypatch.delenv("TAGGING_DATA_DIR", raising=False)
    reloaded = importlib.reload(config)
    try:
        assert reloaded.DATA_DIR == reloaded.PROJECT_DIR / "data"
    finally:
        importlib.reload(config)


def test_data_dir_honors_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Con `TAGGING_DATA_DIR` settata, la casa dati vive fuori dal repo."""
    monkeypatch.setenv("TAGGING_DATA_DIR", str(tmp_path))
    reloaded = importlib.reload(config)
    try:
        assert tmp_path == reloaded.DATA_DIR
    finally:
        monkeypatch.delenv("TAGGING_DATA_DIR", raising=False)
        importlib.reload(config)


def test_env_file_under_project_dir() -> None:
    assert config.ENV_FILE == config.PROJECT_DIR / ".env"


def test_pipeline_dirs_are_under_data_dir() -> None:
    """Tutti i path delle directory pipeline ricadono in `DATA_DIR`."""
    pipeline_dirs = [
        config.DOCUMENTS_DIR,
        config.PARSED_DIR,
        config.CLEAN_DIR,
        config.CLEAN_WITH_DESC_DIR,
        config.ANNOTATED_DIR,
        config.ANNOTATED_WITH_DESC_DIR,
        config.TAGGED_DIR,
    ]
    for p in pipeline_dirs:
        assert config.DATA_DIR in p.parents or p.parent == config.DATA_DIR


class TestResolveAmbiente:
    def test_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ISP_AMBIENTE", "prod")
        assert config.resolve_ambiente() == "prod"

    @pytest.mark.parametrize("raw_value", ["test", "svil", "local"])
    def test_non_prod_values(self, monkeypatch: pytest.MonkeyPatch, raw_value: str) -> None:
        monkeypatch.setenv("ISP_AMBIENTE", raw_value)
        assert config.resolve_ambiente() == "non_prod"

    def test_missing_env_is_non_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ISP_AMBIENTE", raising=False)
        assert config.resolve_ambiente() == "non_prod"


def test_data_files_are_under_data_dir() -> None:
    """Tutti i file dati canonici puntano dentro `DATA_DIR`."""
    data_files = [
        config.ENTI_ESTRATTI_JSON,
        config.ENTI_FULL_NAME_JSON,
        config.TAGS_JSON,
        config.ENTI_CODE_NAME_JSON,
        config.MAPPING_ENTI_FTZ_JSON,
        config.ODC_CREDITO_XLSX,
        config.ODC_AML_XLSX,
        config.ODC_DESCRIPTIONS_JSON,
        config.MO_DESCRIPTIONS_JSON,
        config.TAGGING_CREDITO_XLSX,
        config.TAGS_CREDITO_JSON,
    ]
    for f in data_files:
        assert f.parent == config.DATA_DIR
