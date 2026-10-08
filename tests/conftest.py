"""Fixture condivise per tutti i test del package `core`.

Convenzioni:
  - Fixture "fake" (es. `fake_layer`) sono mock leggeri usati al posto di
    risorse esterne (LLM, smartocr, multiprocessing).
  - Fixture "sample" (es. `sample_md`) costruiscono dati di test minimali ma
    realistici, usabili da più test.
  - Per dati grandi (ground truth, hierarchy) usiamo i file in `fixtures/`
    caricati via fixture pytest.
"""

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

if "JENKINS_HOME" in os.environ:
    python_version = f"python{'.'.join(os.getenv('PYTHON_VERSION', '').split('.')[:2])}"
    virtual_env = os.getenv("VIRTUAL_ENV", "")
    repository_name = os.getenv("repository", "")  # noqa: SIM112

    sys.path.insert(0, os.path.join(virtual_env, "lib", python_version, "site-packages", repository_name))

FIXTURES_DIR = Path(__file__).resolve().parent / "plan" / "core" / "fixtures"


# ── fake genfactory `Layer` ──────────────────────────────────────────────────


class _FakeGenerationInfo:
    """Stub di `gen.generation_info` per test del retry-loop di `call_llm`."""

    def __init__(
        self,
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        finish_reason: str | None = "stop",
        refusal: str | None = None,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

        class _Choice:
            pass

        choice = _Choice()
        choice.finish_reason = finish_reason  # type: ignore[attr-defined]
        choice.refusal = refusal  # type: ignore[attr-defined]
        self.choices = [choice]


class FakeGen:
    """Stub di `gen` (return value di `layer.generate(...)`)."""

    def __init__(
        self,
        text: str = '{"value": 42}',
        finish_reason: str | None = "stop",
        error: str | None = None,
    ) -> None:
        self.texts = [text] if text else [""]
        self.error = error
        self.generation_info = _FakeGenerationInfo(finish_reason=finish_reason)


@pytest.fixture
def make_fake_gen() -> Any:
    """Factory di `FakeGen` per build-test di `gen` con configurazione custom.

    Uso:
        gen_ok = make_fake_gen(text='{"ok":true}')
        gen_length = make_fake_gen(text="", finish_reason="length")
    """
    return FakeGen


@pytest.fixture
def fake_layer() -> MagicMock:
    """Mock di `genfactory.Layer` con `generate()` che ritorna `FakeGen()` di default.

    Sovrascrivibile per test:
        fake_layer.generate.side_effect = [FakeGen("x"), Exception("boom")]
    """
    layer = MagicMock()
    layer.generate.return_value = FakeGen()
    return layer


# ── fixture file ─────────────────────────────────────────────────────────────


@pytest.fixture
def fixtures_dir() -> Path:
    """Path alla directory delle fixture statiche."""
    return FIXTURES_DIR


# ── tenacity ─────────────────────────────────────────────────────────────────


@pytest.fixture
def no_real_sleep(mocker) -> None:
    """Disabilita `time.sleep` di tenacity per evitare 15-30-60s reali nei retry.

    `tenacity.nap.time.sleep` è il punto in cui tenacity addormenta tra retry.
    Patchato a no-op, le politiche di backoff vengono comunque calcolate ma il
    test corre in millisecondi.
    """
    mocker.patch("tenacity.nap.time.sleep", return_value=None)
