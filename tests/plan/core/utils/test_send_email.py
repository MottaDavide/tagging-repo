from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from core.utils.send_email import EmailHandler, on_error_send_email

_FAKE_CONFIG = {"email_recipient": ["test@example.com"]}
_FAKE_FULL_CONFIG = {
    "email_recipient": ["test@example.com"],
    "tagging_error_content": "step={step} msg={exception_message}",
}


class TestEmailHandlerInit:
    def test_reads_recipients_from_config(self) -> None:
        with patch("core.utils.send_email._CONFIG", _FAKE_CONFIG):
            handler = EmailHandler()
        assert handler.recipients == ["test@example.com"]

    def test_stores_run_id(self) -> None:
        with patch("core.utils.send_email._CONFIG", _FAKE_CONFIG):
            handler = EmailHandler(run_id="abc-123")
        assert handler.run_id == "abc-123"

    def test_environment_defaults_to_development(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ISP_AMBIENTE"}
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch.dict(os.environ, env, clear=True),
        ):
            handler = EmailHandler()
        assert handler.environment == "development"

    def test_reads_environment_from_env_var(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch.dict(os.environ, {"ISP_AMBIENTE": "staging"}, clear=False),
        ):
            handler = EmailHandler()
        assert handler.environment == "staging"


class TestSendEmailError:
    def test_returns_true_when_email_sent_successfully(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch("core.utils.send_email.send_mail") as mock_send,
        ):
            handler = EmailHandler(run_id="run-1")
            result = handler.send_email_error("something went wrong")
        assert result is True
        mock_send.assert_called_once()

    def test_passes_correct_recipients_and_subject(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch.dict(os.environ, {"ISP_AMBIENTE": "production"}),
            patch("core.utils.send_email.send_mail") as mock_send,
        ):
            handler = EmailHandler(run_id="run-1")
            handler.send_email_error("some error")
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to"] == ["test@example.com"]
        assert call_kwargs["subject"] == "CAO-FAC-TAGGING-production"

    def test_content_includes_error_message_and_run_id(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch("core.utils.send_email.send_mail") as mock_send,
        ):
            handler = EmailHandler(run_id="run-xyz")
            handler.send_email_error("critical failure")
        content = mock_send.call_args.kwargs["content"]
        assert "critical failure" in content
        assert "run-xyz" in content

    def test_content_includes_environment(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch.dict(os.environ, {"ISP_AMBIENTE": "uat"}),
            patch("core.utils.send_email.send_mail") as mock_send,
        ):
            handler = EmailHandler(run_id="run-1")
            handler.send_email_error("some error")
        content = mock_send.call_args.kwargs["content"]
        assert "uat" in content

    def test_returns_false_when_no_recipients(self) -> None:
        with patch("core.utils.send_email._CONFIG", {"email_recipient": []}):
            handler = EmailHandler(run_id="run-1")
            result = handler.send_email_error("some error")
        assert result is False

    def test_logs_warning_when_no_recipients(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch("core.utils.send_email._CONFIG", {"email_recipient": []}),
            caplog.at_level(logging.WARNING, logger="core.utils.send_email"),
        ):
            handler = EmailHandler()
            handler.send_email_error("some error")
        assert "No email recipient configured" in caplog.text

    def test_returns_false_when_send_mail_raises(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch(
                "core.utils.send_email.send_mail",
                side_effect=Exception("SMTP error"),
            ),
        ):
            handler = EmailHandler(run_id="run-1")
            result = handler.send_email_error("some error")
        assert result is False

    def test_logs_error_when_send_mail_raises(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch(
                "core.utils.send_email.send_mail",
                side_effect=Exception("SMTP error"),
            ),
            caplog.at_level(logging.ERROR, logger="core.utils.send_email"),
        ):
            handler = EmailHandler(run_id="run-1")
            handler.send_email_error("some error")
        assert "Failed to send email" in caplog.text
        assert "run-1" in caplog.text

    def test_logs_success_when_email_sent(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_CONFIG),
            patch("core.utils.send_email.send_mail"),
            caplog.at_level(logging.INFO, logger="core.utils.send_email"),
        ):
            handler = EmailHandler(run_id="run-42")
            handler.send_email_error("minor error")
        assert "Successfully sent email" in caplog.text
        assert "run-42" in caplog.text


class TestOnErrorSendEmail:
    def test_does_not_call_send_email_on_success(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_FULL_CONFIG),
            patch("core.utils.send_email.EmailHandler") as mock_cls,
        ):

            @on_error_send_email("tagging_error_content")
            def pipeline(run_id: str) -> str:
                return "ok"

            pipeline(run_id="run-1")

        mock_cls.return_value.send_email_error.assert_not_called()

    def test_calls_send_email_error_on_exception(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_FULL_CONFIG),
            patch("core.utils.send_email.EmailHandler") as mock_cls,
        ):

            @on_error_send_email("tagging_error_content")
            def pipeline(run_id: str) -> None:
                exc = RuntimeError("boom")
                exc.current_step = "my_step"  # type: ignore[attr-defined]
                raise exc

            with pytest.raises(RuntimeError):
                pipeline(run_id="run-1")

        content = mock_cls.return_value.send_email_error.call_args.args[0]
        assert "my_step" in content
        assert "boom" in content

    def test_defaults_step_to_unknown_when_not_set(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_FULL_CONFIG),
            patch("core.utils.send_email.EmailHandler") as mock_cls,
        ):

            @on_error_send_email("tagging_error_content")
            def pipeline(run_id: str) -> None:
                raise RuntimeError("no step set")

            with pytest.raises(RuntimeError):
                pipeline(run_id="run-1")

        content = mock_cls.return_value.send_email_error.call_args.args[0]
        assert "unknown" in content

    def test_re_raises_exception_after_email(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_FULL_CONFIG),
            patch("core.utils.send_email.EmailHandler"),
        ):

            @on_error_send_email("tagging_error_content")
            def pipeline(run_id: str) -> None:
                raise ValueError("original error")

            with pytest.raises(ValueError, match="original error"):
                pipeline(run_id="run-1")

    def test_re_raises_even_when_email_fails(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_FULL_CONFIG),
            patch("core.utils.send_email.EmailHandler") as mock_cls,
        ):
            mock_cls.return_value.send_email_error.side_effect = Exception("email failed")

            @on_error_send_email("tagging_error_content")
            def pipeline(run_id: str) -> None:
                raise RuntimeError("pipeline error")

            with pytest.raises(RuntimeError, match="pipeline error"):
                pipeline(run_id="run-1")

    def test_instantiates_handler_with_run_id(self) -> None:
        with (
            patch("core.utils.send_email._CONFIG", _FAKE_FULL_CONFIG),
            patch("core.utils.send_email.EmailHandler") as mock_cls,
        ):

            @on_error_send_email("tagging_error_content")
            def pipeline(run_id: str) -> None:
                raise RuntimeError("boom")

            with pytest.raises(RuntimeError):
                pipeline(run_id="run-42")

        mock_cls.assert_called_once_with(run_id="run-42")
