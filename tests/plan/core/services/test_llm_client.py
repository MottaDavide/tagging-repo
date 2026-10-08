"""Test `core.services.llm_client`: retry policy + call_llm end-to-end con fake Layer."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import BaseModel
from tenacity import RetryCallState

import core.services.llm_client as client_mod
from core.services.llm_client import (
    MAX_RETRIES,
    _backoff,
    _LengthExceededError,
    _RetryableError,
    _should_retry,
    call_llm,
)

# ── Modello Pydantic di test ─────────────────────────────────────────────────


class _Response(BaseModel):
    value: int


# ── _should_retry ───────────────────────────────────────────────────────────


class TestShouldRetry:
    def test_retryable_error(self) -> None:
        assert _should_retry(_RetryableError("x")) is True

    def test_length_exceeded(self) -> None:
        assert _should_retry(_LengthExceededError()) is True

    def test_json_decode_error(self) -> None:
        assert _should_retry(json.JSONDecodeError("m", "d", 0)) is True

    def test_httpx_timeout(self) -> None:
        assert _should_retry(httpx.ReadTimeout("boom")) is True

    @pytest.mark.parametrize("msg", ["Got 401", "JWT scaduto", "unauthorized!"])
    def test_token_retryable(self, msg: str) -> None:
        assert _should_retry(Exception(msg)) is True

    @pytest.mark.parametrize("msg", ["429 too many", "rate limited"])
    def test_rate_limit_retryable(self, msg: str) -> None:
        assert _should_retry(Exception(msg)) is True

    @pytest.mark.parametrize("code", ["500", "502", "503", "504"])
    def test_server_5xx_retryable(self, code: str) -> None:
        assert _should_retry(Exception(f"got {code} from server")) is True

    @pytest.mark.parametrize("msg", ["timeout", "timed out", "socket error"])
    def test_timeout_text_retryable(self, msg: str) -> None:
        assert _should_retry(Exception(msg)) is True

    def test_unknown_error_not_retryable(self) -> None:
        assert _should_retry(Exception("something else weird")) is False

    def test_content_filter_runtime_not_retryable(self) -> None:
        """Il content filter solleva RuntimeError che NON deve essere ritentato."""
        assert _should_retry(RuntimeError("Azure content filter attivato")) is False


# ── _backoff ────────────────────────────────────────────────────────────────


class _FakeOutcome:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def exception(self) -> BaseException:
        return self._exc


def _state(exc: BaseException, attempt: int = 1) -> RetryCallState:
    """Costruisce un `RetryCallState`-like senza dover invocare tenacity."""
    s = MagicMock(spec=RetryCallState)
    s.outcome = _FakeOutcome(exc)
    s.attempt_number = attempt
    return s


class TestBackoff:
    def test_length_exceeded_short_wait(self) -> None:
        assert _backoff(_state(_LengthExceededError())) == 1

    def test_retryable_empty_response_wait_20(self) -> None:
        assert _backoff(_state(_RetryableError("empty"))) == 20

    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [(1, 15), (2, 30), (3, 60), (4, 120), (5, 240), (10, 240)],
    )
    def test_server_error_exponential_backoff(self, attempt: int, expected: float) -> None:
        assert _backoff(_state(Exception("500 Internal"), attempt=attempt)) == expected

    def test_httpx_timeout_exponential_backoff(self) -> None:
        assert _backoff(_state(httpx.ReadTimeout("x"), attempt=1)) == 15
        assert _backoff(_state(httpx.ReadTimeout("x"), attempt=3)) == 60

    @pytest.mark.parametrize("msg", ["429 too many", "rate limited"])
    def test_rate_limit_wait_20(self, msg: str) -> None:
        assert _backoff(_state(Exception(msg))) == 20

    def test_default_wait_1(self) -> None:
        """401/jwt/unauthorized e errori sconosciuti restituiscono 1s."""
        assert _backoff(_state(Exception("Got 401"))) == 1
        assert _backoff(_state(Exception("weird"))) == 1

    def test_no_outcome_returns_default(self) -> None:
        """Se outcome è None (caso teorico), fallback a 1."""
        s = MagicMock(spec=RetryCallState)
        s.outcome = None
        s.attempt_number = 1
        assert _backoff(s) == 1


# ── call_llm helpers ────────────────────────────────────────────────────────


def _gen_ok(text: str = '{"value": 42}') -> Any:
    g = MagicMock()
    g.texts = [text]
    g.error = None
    g.generation_info = None
    return g


def _gen_empty(finish_reason: str | None = None, error: str | None = None) -> Any:
    g = MagicMock()
    g.texts = [""]
    g.error = error

    if finish_reason is not None:
        gi = MagicMock()
        choice = MagicMock()
        choice.finish_reason = finish_reason
        gi.choices = [choice]
        g.generation_info = gi
    else:
        g.generation_info = None
    return g


@pytest.fixture
def fake_llm_layer() -> MagicMock:
    """Layer mock per call_llm: default = success."""
    layer = MagicMock()
    layer.generate.return_value = _gen_ok()
    return layer


# ── call_llm: success path ──────────────────────────────────────────────────


class TestCallLlmSuccess:
    def test_first_attempt_success(self, fake_llm_layer: MagicMock) -> None:
        result = call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
        )
        assert isinstance(result, _Response)
        assert result.value == 42
        assert fake_llm_layer.generate.call_count == 1

    def test_with_reasoning_and_verbosity_options(self, fake_llm_layer: MagicMock) -> None:
        """I parametri opzionali vengono propagati al payload (non solleva)."""
        call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
            reasoning_effort="high",
            verbosity="low",
        )
        # verifico che generate sia stato chiamato (smoke check sui param keyword)
        assert fake_llm_layer.generate.called


# ── call_llm: retry path ────────────────────────────────────────────────────


class TestCallLlmRetry:
    def test_retry_on_401_then_success(self, fake_llm_layer: MagicMock, no_real_sleep: None) -> None:
        fake_llm_layer.generate.side_effect = [Exception("Got 401 unauthorized"), _gen_ok()]
        result = call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
        )
        assert result.value == 42
        assert fake_llm_layer.generate.call_count == 2

    def test_retry_on_5xx_then_success(self, fake_llm_layer: MagicMock, no_real_sleep: None) -> None:
        fake_llm_layer.generate.side_effect = [
            Exception("500 Internal Server Error"),
            Exception("502 Bad Gateway"),
            _gen_ok(),
        ]
        result = call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
        )
        assert result.value == 42
        assert fake_llm_layer.generate.call_count == MAX_RETRIES

    def test_exhausts_retries_raises_runtime_error(self, fake_llm_layer: MagicMock, no_real_sleep: None) -> None:
        fake_llm_layer.generate.side_effect = Exception("500 perma-fail")
        with pytest.raises(RuntimeError, match="LLM call fallita dopo"):
            call_llm(
                layer=fake_llm_layer,
                system_prompt="sys",
                user_message="usr",
                response_format=_Response,
                max_tokens=100,
                model="m",
            )
        assert fake_llm_layer.generate.call_count == MAX_RETRIES

    def test_retry_on_empty_response_then_success(self, fake_llm_layer: MagicMock, no_real_sleep: None) -> None:
        fake_llm_layer.generate.side_effect = [_gen_empty(finish_reason=None), _gen_ok()]
        result = call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
        )
        assert result.value == 42


# ── call_llm: length bump path ──────────────────────────────────────────────


class TestCallLlmLengthBump:
    def test_length_bump_max_tokens_then_exhausts(
        self, fake_llm_layer: MagicMock, no_real_sleep: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """3 length responses consecutive → max_tokens bumped 1.5x ad ogni retry, poi RuntimeError."""
        import logging

        fake_llm_layer.generate.return_value = _gen_empty(finish_reason="length")
        with caplog.at_level(logging.WARNING, logger="core.services.llm_client"), pytest.raises(RuntimeError):
            call_llm(
                layer=fake_llm_layer,
                system_prompt="sys",
                user_message="usr",
                response_format=_Response,
                max_tokens=100,
                model="m",
            )
        # 3 tentativi → log bump 100→150, 150→225, 225→337
        assert "100 → 150" in caplog.text
        assert "150 → 225" in caplog.text
        assert "225 → 337" in caplog.text

    def test_length_then_success(self, fake_llm_layer: MagicMock, no_real_sleep: None) -> None:
        fake_llm_layer.generate.side_effect = [_gen_empty(finish_reason="length"), _gen_ok()]
        result = call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
        )
        assert result.value == 42


# ── call_llm: content filter no-retry ───────────────────────────────────────


class TestCallLlmContentFilter:
    def test_content_filter_immediate_failure(self, fake_llm_layer: MagicMock) -> None:
        """`finish_reason=content_filter` → RuntimeError immediato, NIENTE retry."""
        fake_llm_layer.generate.return_value = _gen_empty(finish_reason="content_filter")
        with pytest.raises(RuntimeError, match="content filter"):
            call_llm(
                layer=fake_llm_layer,
                system_prompt="sys",
                user_message="usr",
                response_format=_Response,
                max_tokens=100,
                model="m",
            )
        # Solo 1 call: RuntimeError non è in _should_retry
        assert fake_llm_layer.generate.call_count == 1


# ── call_llm: unknown error no-retry ────────────────────────────────────────


class TestCallLlmUnknownError:
    def test_unknown_exception_no_retry(self, fake_llm_layer: MagicMock) -> None:
        """Eccezione con messaggio non riconoscibile → no retry."""
        fake_llm_layer.generate.side_effect = Exception("absolutely-unrelated-error-text")
        with pytest.raises(RuntimeError, match="LLM call fallita"):
            call_llm(
                layer=fake_llm_layer,
                system_prompt="sys",
                user_message="usr",
                response_format=_Response,
                max_tokens=100,
                model="m",
            )
        assert fake_llm_layer.generate.call_count == 1


# ── call_llm: payload construction smoke ───────────────────────────────────


class TestCallLlmPayload:
    def test_uses_async_mode(self, fake_llm_layer: MagicMock) -> None:
        call_llm(
            layer=fake_llm_layer,
            system_prompt="sys",
            user_message="usr",
            response_format=_Response,
            max_tokens=100,
            model="m",
        )
        # tenacity wraps it; check the actual call to layer.generate received mode='async'
        call_kwargs = fake_llm_layer.generate.call_args.kwargs
        assert call_kwargs.get("mode") == "async"

    def test_constants_exposed(self) -> None:
        """Le costanti chiave sono esposte dal modulo."""
        assert isinstance(client_mod.MAX_RETRIES, int)
        assert isinstance(client_mod._RETRYABLE_HINTS, tuple)
        assert isinstance(client_mod._SERVER_HINTS, tuple)
