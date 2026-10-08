"""Unico path autorizzato per chiamare LLM tramite genfactory.

`init_genfactory(...)` configura il singleton globale di genfactory e ritorna
un'istanza `Layer` pronta. Il token JWT è gestito da `genfactory.auth.TokenCache`:
viene passato come callable al `Layer` e rinnovato in automatico quando scade.
Nessun altro modulo deve istanziare `Layer` o chiamare `request_access_token`
direttamente.

`call_llm(...)` esegue la chiamata vera e propria con retry tenacity e structured
output. Il refresh del token non vive qui: `Layer` chiama il `TokenCache.get`
passato come token-callable in `init_genfactory`.

Retry policy:
  - 5xx / timeout / socket    → backoff esponenziale 15, 30, 60, 120, 240 s
  - 429 / rate-limit          → fisso 20 s
  - 401 / JWT                 → 1 s (TokenCache rinnova prima del prossimo retry)
  - empty response (sconosc.) → fisso 20 s
  - finish_reason="length"    → 1 s; `max_tokens` viene aumentato 1.5x via closure
  - finish_reason="content_filter" → fallisce immediatamente (Azure non cede su retry)
"""

import json
import logging
import time
from typing import Any, Literal

import httpx
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from genfactory import Layer
from genfactory.auth import TokenCache
from genfactory.config import GenfactoryConfig, set_configuration
from genfactory.config.credentials import Credentials
from genfactory.config.enums import Environment
from genfactory.layer.dtypes.common import Provider
from genfactory.layer.dtypes.text_generation import (
    AzureDeveloperMessage,
    AzureUserMessage,
    GenerationParams,
    TextGenerationPayload,
)
from genfactory.utils.logging import Logger, LogRequest
from pydantic import BaseModel
from tenacity import (
    RetryCallState,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from core.utils.logging import GENFACTORY_LOGGER_NAME

__all__ = ["DEFAULT_MODEL", "Layer", "call_llm", "call_llm_timed", "init_genfactory"]

# Logger dedicato per i sub-eventi HTTP genfactory. Il `_CompactFormatter`
# indenta questo logger di 4 spazi per nestarlo visivamente sotto le call di stage.
_gf_logger = logging.getLogger(GENFACTORY_LOGGER_NAME)

logger = logging.getLogger(__name__)


_CONFIG = get_obj_from_config_path("llm.yaml")
_LAYER_CONFIG = _CONFIG["layer"]
_HTTP_TIMEOUT_CONFIG = _LAYER_CONFIG["http_timeout"]

DEFAULT_MODEL: str = _CONFIG["default_model"]
DEFAULT_HTTP_TIMEOUT = httpx.Timeout(
    connect=_HTTP_TIMEOUT_CONFIG["connect"],
    read=_HTTP_TIMEOUT_CONFIG["read"],
    write=_HTTP_TIMEOUT_CONFIG["write"],
    pool=_HTTP_TIMEOUT_CONFIG["pool"],
)
DEFAULT_TOKEN_LIFETIME_MIN: int = _LAYER_CONFIG["token_lifetime_min"]
DEFAULT_USE_CASE_ID: str = _LAYER_CONFIG["use_case_id"]

MAX_RETRIES: int = _CONFIG["client"]["max_retries"]

# Substring di errori transitori. Classificazione fragile ma necessaria:
# genfactory solleva `Exception` generiche con messaggi distinti.
_RETRYABLE_HINTS: tuple[str, ...] = (
    "401",
    "jwt",
    "unauthorized",
    "429",
    "rate",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "socket",
)
_SERVER_HINTS: tuple[str, ...] = ("500", "502", "503", "504", "timeout", "timed out", "socket")


def _gf_log_handler(log: LogRequest) -> None:
    """Inoltra i log strutturati di genfactory al logger Python centrale."""
    level_name = Logger._handle_log_level(log)
    level = logging.getLevelName(level_name) if isinstance(level_name, str) else level_name

    uid_str = f"[{log.uid}]" if log.uid else ""
    call_str = " ".join(p for p in [log.key, log.action] if p)
    message = Logger._format_response_message(log)
    result_str = f"{log.response_status_code} {message}"
    body = "  ".join(p for p in [uid_str, call_str, result_str] if p)

    _gf_logger.log(level, body)
    if log.response_status_code >= 400:
        _gf_logger.log(level, "  Error details: %s", log.response_content)


def init_genfactory(
    env_file: str,
    use_case_id: str = DEFAULT_USE_CASE_ID,
    env: Environment = Environment.TEST,
    timeout: httpx.Timeout | None = None,
    token_lifetime_min: int = DEFAULT_TOKEN_LIFETIME_MIN,
) -> Layer:
    """Configura genfactory e ritorna un `Layer` con token auto-refresh.

    Il token è gestito da `TokenCache`: viene passato come callable al `Layer`,
    che lo richiede ad ogni call HTTP. La cache lo rinnova in autonomia quando
    supera il TTL (`token_lifetime_min` minuti).

    Per scenari multi-`use_case_id` (es. AUDIT + AUDIT-SVIL), chiamare questa
    funzione in processi separati: il singleton `GenfactoryConfig` non è
    sicuro tra Layer diversi nello stesso processo.
    """
    set_configuration(
        GenfactoryConfig(
            credentials=Credentials.from_dotenv(env_file),
            use_case_id=use_case_id,
            env=env,
        )
    )
    Logger.handlers = [_gf_log_handler]

    token_cache = TokenCache.with_minutes(token_lifetime_min)
    return Layer(token=token_cache.get, timeout=timeout or DEFAULT_HTTP_TIMEOUT)


class _RetryableError(Exception):
    """Segnale: ritenta (es. risposta vuota senza finish_reason riconoscibile)."""


class _LengthExceededError(_RetryableError):
    """`finish_reason='length'`: aumentare `max_tokens` prima del retry."""


def _should_retry(e: BaseException) -> bool:
    """Tenacity predicate: True se l'errore è transitorio."""
    if isinstance(e, (_RetryableError, json.JSONDecodeError, httpx.TimeoutException)):
        return True
    err = str(e).lower()
    return any(h in err for h in _RETRYABLE_HINTS)


def _backoff(retry_state: RetryCallState) -> float:
    """Wait in secondi in base al tipo di errore corrente."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _LengthExceededError):
        return 1
    if isinstance(exc, _RetryableError):
        return 20  # empty response senza finish_reason chiaro
    # tenacity non tipizza `attempt_number`, cast esplicito per mypy.
    attempt = int(retry_state.attempt_number)
    if isinstance(exc, httpx.TimeoutException):
        return float(min(15 * 2 ** (attempt - 1), 240))
    err = str(exc).lower() if exc else ""
    if any(c in err for c in _SERVER_HINTS):
        return float(min(15 * 2 ** (attempt - 1), 240))
    if "429" in err or "rate" in err:
        return 20
    return 1


def call_llm[T: BaseModel](
    layer: Layer,
    system_prompt: str,
    user_message: str,
    response_format: type[T],
    max_tokens: int,
    model: str,
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = "low",
    verbosity: Literal["low", "medium", "high"] | None = None,
) -> T:
    """LLM call con retry tenacity e structured output.

    `max_tokens` viene aumentato 1.5x via closure-state se l'output viene
    troncato (`finish_reason='length'`). Solleva `RuntimeError` dopo
    `MAX_RETRIES` tentativi falliti o su content filter (no retry).
    """
    state = {"max_tokens": max_tokens}

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=_backoff,
        retry=retry_if_exception(_should_retry),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _attempt() -> T:
        gen: Any = layer.generate(
            payload=TextGenerationPayload(
                provider=Provider.AZURE,
                generation_params=GenerationParams(
                    messages=[
                        AzureDeveloperMessage(content=system_prompt),
                        AzureUserMessage(content=user_message),
                    ],
                    model=model,
                    response_format=response_format,
                    max_completion_tokens=state["max_tokens"],
                    reasoning_effort=reasoning_effort,
                    verbosity=verbosity,
                ),
            ),
            mode="async",
        )
        if gen.texts and gen.texts[0].strip():
            return response_format.model_validate_json(gen.texts[0])

        # Risposta vuota: differenzia su finish_reason.
        gi = gen.generation_info
        finish = getattr(gi.choices[0], "finish_reason", None) if gi and gi.choices else None
        if finish == "length":
            new_max = int(state["max_tokens"] * 1.5)
            logger.warning("finish_reason=length: aumento max_tokens %d → %d", state["max_tokens"], new_max)
            state["max_tokens"] = new_max
            raise _LengthExceededError
        if finish == "content_filter":
            # Azure non cede su retry: fallisci subito (RuntimeError non è retryable).
            raise RuntimeError(f"Azure content filter attivato (error={gen.error})")
        raise _RetryableError(f"empty response (finish_reason={finish}, error={gen.error})")

    try:
        return _attempt()
    except Exception as e:
        raise RuntimeError(f"LLM call fallita dopo {MAX_RETRIES} tentativi: {type(e).__name__}: {e}") from e


def call_llm_timed[T: BaseModel](
    layer: Layer,
    system_prompt: str,
    user_message: str,
    response_format: type[T],
    max_tokens: int,
    model: str,
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = "low",
) -> tuple[T | None, float]:
    """`call_llm` con timing e cattura di `RuntimeError` (fail-soft). Ritorna `(result, elapsed)`."""
    t0 = time.time()
    try:
        result = call_llm(
            layer, system_prompt, user_message, response_format, max_tokens, model, reasoning_effort=reasoning_effort
        )
    except RuntimeError as e:
        logger.warning("call_llm fallita (fail-soft): %s", e)
        return None, time.time() - t0
    return result, time.time() - t0
