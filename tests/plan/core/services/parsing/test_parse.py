"""Test `core.services.parsing.parse`."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.services.parsing.parse import init_genfactory_for_parsing, process_file

# ── init_worker ─────────────────────────────────────────────────────────────


class TestInitWorker:
    def test_initializes_layer(self, mocker) -> None:
        fake = MagicMock()
        mocker.patch("core.services.parsing.parse.init_genfactory", return_value=fake)
        result = init_genfactory_for_parsing()
        assert result is fake


# ── process_file ────────────────────────────────────────────────────────────


class TestProcessFile:
    def test_skips_when_output_exists(self, tmp_path: Path, mocker) -> None:
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-1.4 ...")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "a.md").write_text("already")

        # _layer non deve essere chiamato
        name, ok, elapsed = process_file((pdf, out_dir))
        assert ok is True
        assert name == "a.pdf"
        assert elapsed == 0.0

    def test_success_writes_markdown(self, tmp_path: Path, mocker) -> None:
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"PDF bytes")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        fake_layer = MagicMock()
        fake_result = MagicMock()
        fake_result.content = "# Titolo\nbody"
        fake_layer.analyze_document.return_value = fake_result

        _name, ok, _elapsed = process_file((pdf, out_dir), fake_layer)
        assert ok is True
        assert (out_dir / "a.md").read_text() == "# Titolo\nbody"

    def test_empty_content_returns_false(self, tmp_path: Path, mocker, caplog) -> None:
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"x")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        fake_layer = MagicMock()
        fake_layer.analyze_document.return_value = MagicMock(content="")

        with caplog.at_level(logging.WARNING, logger="core.services.parsing.parse"):
            _name, ok, _elapsed = process_file((pdf, out_dir), fake_layer)
        assert ok is False
        assert "contenuto markdown vuoto" in caplog.text

    def test_exception_returns_false(self, tmp_path: Path, mocker, caplog) -> None:
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"x")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        fake_layer = MagicMock()
        fake_layer.analyze_document.side_effect = Exception("boom")

        with caplog.at_level(logging.ERROR, logger="core.services.parsing.parse"):
            _name, ok, _elapsed = process_file((pdf, out_dir), fake_layer)
        assert ok is False
        assert "errore" in caplog.text

    def test_logs_run_id_when_provided(self, tmp_path: Path, caplog) -> None:
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"PDF bytes")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        fake_layer = MagicMock()
        fake_layer.analyze_document.return_value = MagicMock(content="# Titolo\nbody")

        with caplog.at_level(logging.INFO, logger="core.services.parsing.parse"):
            process_file((pdf, out_dir), fake_layer, run_id="run-123")

        assert "run_id=run-123" in caplog.text

    def test_exception_raises_when_requested(self, tmp_path: Path, mocker, caplog) -> None:
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"x")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        fake_layer = MagicMock()
        fake_layer.analyze_document.side_effect = Exception("boom")

        with (
            caplog.at_level(logging.ERROR, logger="core.services.parsing.parse"),
            pytest.raises(Exception, match="boom"),
        ):
            process_file((pdf, out_dir), fake_layer, raise_on_error=True)

        assert "errore" in caplog.text
