from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import requests

from core.models.entities.entities import ErrorAck
from core.utils.ack import send_ack


class TestSendAck:
    def test_sends_ack_when_callback_is_configured(self) -> None:
        response = MagicMock(status_code=200, text="ok")

        with (
            patch.dict(os.environ, {"CALLBACK_TAGGING": "https://callback.test"}, clear=False),
            patch("core.utils.ack.requests.post", return_value=response) as post_mock,
        ):
            send_ack(data={"hello": "world"}, mode="tagging", run_id="run-1")

        post_mock.assert_called_once()
        assert post_mock.call_args.args[0] == "https://callback.test"
        assert post_mock.call_args.kwargs["data"]
        assert '"run_id":"run-1"' in post_mock.call_args.kwargs["data"]
        assert '"data":{"hello":"world"}' in post_mock.call_args.kwargs["data"]

    def test_uses_summary_callback_when_mode_is_summary(self) -> None:
        response = MagicMock(status_code=200, text="ok")

        with (
            patch.dict(
                os.environ,
                {
                    "CALLBACK_TAGGING": "https://tagging-callback.test",
                    "CALLBACK_SUMMARY": "https://summary-callback.test",
                },
                clear=False,
            ),
            patch("core.utils.ack.requests.post", return_value=response) as post_mock,
        ):
            send_ack(data={"hello": "world"}, mode="summary", run_id="run-1")

        post_mock.assert_called_once()
        assert post_mock.call_args.args[0] == "https://summary-callback.test"

    def test_includes_error_payload_when_present(self) -> None:
        response = MagicMock(status_code=200, text="ok")
        error = ErrorAck(
            step="tag_document",
            exceptionMessage="boom",
            errorCode=500,
            retryCall=True,
        )

        with (
            patch.dict(os.environ, {"CALLBACK_TAGGING": "https://callback.test"}, clear=False),
            patch("core.utils.ack.requests.post", return_value=response) as post_mock,
        ):
            send_ack(data={}, mode="tagging", run_id="run-1", error=error)

        payload = post_mock.call_args.kwargs["data"]
        assert '"error":{"step":"tag_document","exceptionMessage":"boom","errorCode":500,"retryCall":true}' in payload

    def test_logs_exception_when_request_fails(self, caplog) -> None:
        with (
            patch.dict(os.environ, {"CALLBACK_TAGGING": "https://callback.test"}, clear=False),
            patch("core.utils.ack.requests.post", side_effect=requests.RequestException("boom")),
            caplog.at_level(logging.ERROR, logger="core.utils.ack"),
        ):
            send_ack(data={}, mode="tagging", run_id="run-1")

        assert "Error while sending ack to CALLBACK" in caplog.text

    def test_logs_error_when_callback_returns_non_200(self, caplog) -> None:
        response = MagicMock(status_code=500, text="nope")

        with (
            patch.dict(os.environ, {"CALLBACK_TAGGING": "https://callback.test"}, clear=False),
            patch("core.utils.ack.requests.post", return_value=response),
            caplog.at_level(logging.ERROR, logger="core.utils.ack"),
        ):
            send_ack(data={}, mode="tagging", run_id="run-1")

        assert "Ack delivery to ITTools failed" in caplog.text

    def test_logs_warning_when_callback_is_missing(self, caplog) -> None:
        env = dict(os.environ)
        env.pop("CALLBACK_TAGGING", None)

        with patch.dict(os.environ, env, clear=True), caplog.at_level(logging.WARNING, logger="core.utils.ack"):
            send_ack(data={}, mode="tagging", run_id="run-1")

        assert "CALLBACK_TAGGING is not configured" in caplog.text
