"""Test `core.services.llm_client` (init_genfactory + _gf_log_handler)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import core.services.llm_client as llm_mod
from core.services.llm_client import init_genfactory
from core.utils.logging import GENFACTORY_LOGGER_NAME


class TestInitGenfactory:
    def test_returns_layer_instance(self, mocker) -> None:
        """Smoke: init costruisce Layer con token-callable e timeout di default."""
        mocker.patch("core.services.llm_client.GenfactoryConfig")
        mocker.patch("core.services.llm_client.Credentials.from_dotenv")
        mocker.patch("core.services.llm_client.set_configuration")
        token_cache = mocker.patch("core.services.llm_client.TokenCache")
        token_cache.with_minutes.return_value.get = lambda: "fake-token"
        layer_mock = mocker.patch("core.services.llm_client.Layer")

        result = init_genfactory(env_file="/path/.env")

        assert result == layer_mock.return_value
        # Layer è stato chiamato con token callable + timeout
        kwargs = layer_mock.call_args.kwargs
        assert callable(kwargs["token"])
        assert kwargs["timeout"] is not None

    def test_with_custom_timeout(self, mocker) -> None:
        mocker.patch("core.services.llm_client.GenfactoryConfig")
        mocker.patch("core.services.llm_client.Credentials.from_dotenv")
        mocker.patch("core.services.llm_client.set_configuration")
        mocker.patch("core.services.llm_client.TokenCache").with_minutes.return_value.get = lambda: "t"
        layer_mock = mocker.patch("core.services.llm_client.Layer")

        import httpx

        custom = httpx.Timeout(5.0)
        init_genfactory(env_file="/p", timeout=custom)
        assert layer_mock.call_args.kwargs["timeout"] == custom

    def test_registers_log_handler(self, mocker) -> None:
        mocker.patch("core.services.llm_client.GenfactoryConfig")
        mocker.patch("core.services.llm_client.Credentials.from_dotenv")
        mocker.patch("core.services.llm_client.set_configuration")
        mocker.patch("core.services.llm_client.TokenCache").with_minutes.return_value.get = lambda: "t"
        mocker.patch("core.services.llm_client.Layer")

        init_genfactory(env_file="/p")
        # Logger.handlers contiene il nostro handler
        assert llm_mod._gf_log_handler in llm_mod.Logger.handlers


class TestGfLogHandler:
    def test_forwards_to_genfactory_logger(
        self,
        mocker,
        caplog: logging.LogCaptureHandler,
    ) -> None:
        log = MagicMock()
        log.uid = "uid-1"
        log.key = "key"
        log.action = "act"
        log.response_status_code = 200
        log.response_content = "ok"

        mocker.patch.object(llm_mod.Logger, "_handle_log_level", return_value="INFO")
        mocker.patch.object(llm_mod.Logger, "_format_response_message", return_value="msg")

        with caplog.at_level(logging.INFO, logger=GENFACTORY_LOGGER_NAME):
            llm_mod._gf_log_handler(log)
        assert "uid-1" in caplog.text
        assert "key act" in caplog.text
        assert "200 msg" in caplog.text

    def test_logs_error_details_when_status_4xx(
        self,
        mocker,
        caplog,
    ) -> None:
        log = MagicMock()
        log.uid = None
        log.key = "k"
        log.action = "a"
        log.response_status_code = 500
        log.response_content = "boom"

        mocker.patch.object(llm_mod.Logger, "_handle_log_level", return_value="ERROR")
        mocker.patch.object(llm_mod.Logger, "_format_response_message", return_value="m")

        with caplog.at_level(logging.ERROR, logger=GENFACTORY_LOGGER_NAME):
            llm_mod._gf_log_handler(log)
        assert "Error details" in caplog.text
        assert "boom" in caplog.text

    def test_handles_int_level(self, mocker, caplog) -> None:
        """Ramo: _handle_log_level può restituire un int direttamente."""
        log = MagicMock()
        log.uid = None
        log.key = ""
        log.action = ""
        log.response_status_code = 200
        log.response_content = ""

        mocker.patch.object(llm_mod.Logger, "_handle_log_level", return_value=logging.INFO)
        mocker.patch.object(llm_mod.Logger, "_format_response_message", return_value="m")

        with caplog.at_level(logging.INFO, logger=GENFACTORY_LOGGER_NAME):
            llm_mod._gf_log_handler(log)
        # Non solleva: ha gestito correttamente l'int level
        assert "200 m" in caplog.text
