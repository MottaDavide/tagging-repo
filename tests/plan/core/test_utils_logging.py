"""Test di `core.utils.logging`: formatter compatto + setup_logging."""

from __future__ import annotations

import logging

import pytest

from core.utils.logging import GENFACTORY_LOGGER_NAME, _CompactFormatter, setup_logging


def _make_record(name: str, message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )


class TestCompactFormatter:
    def test_basic_format_contains_level_and_message(self) -> None:
        formatter = _CompactFormatter()
        record = _make_record("core.test", "ciao")
        out = formatter.format(record)
        assert "INFO" in out
        assert "ciao" in out

    def test_indent_applied_for_genfactory_logger(self) -> None:
        """Il logger `tagging.genfactory` riceve 4 spazi di indent."""
        formatter = _CompactFormatter()
        record = _make_record(GENFACTORY_LOGGER_NAME, "subevent")
        out = formatter.format(record)
        # Cerco la presenza di "    subevent" (4 spazi + messaggio).
        assert "    subevent" in out

    def test_no_indent_for_other_loggers(self) -> None:
        formatter = _CompactFormatter()
        record = _make_record("core.something", "plain")
        out = formatter.format(record)
        assert "    plain" not in out
        assert "plain" in out

    def test_exc_info_appended(self) -> None:
        formatter = _CompactFormatter()
        try:
            raise ValueError("boom")  # noqa: TRY301 (serve a generare exc_info per il test del formatter)
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="core.test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="errore",
                args=None,
                exc_info=sys.exc_info(),
            )
        out = formatter.format(record)
        assert "errore" in out
        assert "ValueError" in out


class TestSetupLogging:
    @pytest.fixture(autouse=True)
    def _reset_root(self) -> None:
        """Salva e ripristina lo stato del root logger per non inquinare altri test."""
        root = logging.getLogger()
        old_level = root.level
        old_handlers = list(root.handlers)
        yield
        root.setLevel(old_level)
        root.handlers = old_handlers

    def test_returns_named_logger(self) -> None:
        log = setup_logging("core.test.foo")
        assert log.name == "core.test.foo"

    def test_root_logger_has_compact_formatter(self) -> None:
        setup_logging("core.test.bar")
        root = logging.getLogger()
        assert any(isinstance(h.formatter, _CompactFormatter) for h in root.handlers)

    def test_root_level_is_info(self) -> None:
        setup_logging("core.test.baz")
        assert logging.getLogger().level == logging.INFO

    def test_httpx_logger_silenced_to_warning(self) -> None:
        setup_logging("core.test.qux")
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
