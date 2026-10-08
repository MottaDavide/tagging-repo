"""Test `core.services.enrichment.entity_extraction`."""

from __future__ import annotations

import logging
from typing import Any

import pytest

import core.services.enrichment.entity_extraction as ee_mod
from core.services.enrichment.entity_extraction import (
    MAX_RETRIES,
    MAX_WORKERS,
    RETRY_DELAY_S,
    _call_single_batch,
    _is_empty_result,
    _load_entity_batches,
    _merge_results,
    extract_entities,
)

# ── Costanti di test ────────────────────────────────────────────────────────

_SAMPLE_MD = "[PAGE 1]\nTesto della prima pagina.\n\n[PAGE 2]\nTesto della seconda pagina."

_BATCH_A = [{"0101025": "Gruppo bancario Intesa SanPaolo."}]
_BATCH_B = [{"0105740": "Struttura centrale del Gruppo ISP."}]

_RESULT_A: dict[str, Any] = {
    "entity_extracted": {
        "pag_1": {"Gruppo ISP": {"citazione": "Intesa SanPaolo", "ente_raw": "Intesa SanPaolo"}},
    },
    "extra": {},
}
_RESULT_B: dict[str, Any] = {
    "entity_extracted": {
        "pag_1": {"BdT": {"citazione": "Banca dei Territori", "ente_raw": "Banca dei Territori"}},
        "pag_2": {"BdT": {"citazione": "BdT", "ente_raw": "BdT"}},
    },
    "extra": {},
}
_EMPTY_RESULT: dict[str, Any] = {"entity_extracted": {}, "extra": {}}


# ── _load_entity_batches ────────────────────────────────────────────────────


class TestLoadEntityBatches:
    def test_returns_list_of_lists(self, tmp_path, mocker) -> None:
        enti = {
            "0101025": [{"0101025": "Gruppo ISP"}],
            "0105740": [{"0105740": "Struttura BdT"}, {"0141020": "Controlli BdT"}],
        }
        fake_path = tmp_path / "enti.json"
        import json

        fake_path.write_text(json.dumps(enti), encoding="utf-8")
        mocker.patch.object(ee_mod, "ENTI_JSON", fake_path)

        batches = _load_entity_batches()

        assert isinstance(batches, list)
        assert len(batches) == 2
        assert all(isinstance(b, list) for b in batches)

    def test_preserves_batch_contents(self, tmp_path, mocker) -> None:
        enti = {"key": [{"abc1234": "Descrizione ente"}]}
        fake_path = tmp_path / "enti.json"
        import json

        fake_path.write_text(json.dumps(enti), encoding="utf-8")
        mocker.patch.object(ee_mod, "ENTI_JSON", fake_path)

        batches = _load_entity_batches()

        assert batches[0] == [{"abc1234": "Descrizione ente"}]


# ── _call_single_batch ──────────────────────────────────────────────────────


class TestCallSingleBatch:
    def test_delegates_to_soa_entity_from_text(self, mocker) -> None:
        mock_soa = mocker.patch("core.services.enrichment.entity_extraction.soa_entity_from_text")
        mock_soa.return_value = _RESULT_A

        result = _call_single_batch(
            text_file_in={"texts": {"pag_1": "testo"}, "extra": {}},
            lst_entities=_BATCH_A,
            token="tok",  # noqa: S106
            service="openai",
            language="it",
            use_case="test-uc",
            env="svil",
            params=None,
        )

        mock_soa.assert_called_once_with(
            text_file_in={"texts": {"pag_1": "testo"}, "extra": {}},
            lst_entities=_BATCH_A,
            token="tok",  # noqa: S106,
            use_case="test-uc",
            service="openai",
            language="it",
            env="svil",
            params=None,
            find_children_in_hierarchy=False,  # perché quando c'è isp_code in lst_entities, find_children_in_hierarchy = False
        )
        assert result == _RESULT_A

    def test_passes_params_through(self, mocker) -> None:
        mock_soa = mocker.patch("core.services.enrichment.entity_extraction.soa_entity_from_text")
        mock_soa.return_value = _RESULT_A
        params = {"args": {"model": {"model_id": "gpt-4", "max_completion_tokens": 1000}}}

        _call_single_batch(
            text_file_in={},
            lst_entities=_BATCH_A,
            token="tok",  # noqa: S106,
            service="openai",
            language="it",
            use_case="uc",
            env="svil",
            params=params,
        )

        _, kwargs = mock_soa.call_args
        assert kwargs["params"] == params

    def test_returns_none_when_soa_returns_none(self, mocker) -> None:
        mocker.patch("core.services.enrichment.entity_extraction.soa_entity_from_text", return_value=None)

        result = _call_single_batch(
            text_file_in={},
            lst_entities=_BATCH_A,
            token="tok",  # noqa: S106,
            service="openai",
            language="it",
            use_case="uc",
            env="svil",
            params=None,
        )

        assert result is None


# ── _merge_results ──────────────────────────────────────────────────────────


class TestMergeResults:
    def test_merge_disjoint_pages(self) -> None:
        r1: dict[str, Any] = {
            "entity_extracted": {"pag_1": {"EntA": {"citazione": "A"}}},
            "extra": {},
        }
        r2: dict[str, Any] = {
            "entity_extracted": {"pag_2": {"EntB": {"citazione": "B"}}},
            "extra": {},
        }
        merged = _merge_results([r1, r2])

        assert "pag_1" in merged["entity_extracted"]
        assert "pag_2" in merged["entity_extracted"]

    def test_merge_overlapping_page_combines_entities(self) -> None:
        r1: dict[str, Any] = {
            "entity_extracted": {"pag_1": {"EntA": {"citazione": "A"}}},
            "extra": {},
        }
        r2: dict[str, Any] = {
            "entity_extracted": {"pag_1": {"EntB": {"citazione": "B"}}},
            "extra": {},
        }
        merged = _merge_results([r1, r2])

        page = merged["entity_extracted"]["pag_1"]
        assert "EntA" in page
        assert "EntB" in page

    def test_merge_overlapping_entity_key_last_wins(self) -> None:
        r1: dict[str, Any] = {
            "entity_extracted": {"pag_1": {"Ente": {"citazione": "prima"}}},
            "extra": {},
        }
        r2: dict[str, Any] = {
            "entity_extracted": {"pag_1": {"Ente": {"citazione": "seconda"}}},
            "extra": {},
        }
        merged = _merge_results([r1, r2])

        assert merged["entity_extracted"]["pag_1"]["Ente"]["citazione"] == "seconda"

    def test_merge_empty_list(self) -> None:
        merged = _merge_results([])

        assert merged == {"entity_extracted": {}, "extra": {}}

    def test_merge_skips_missing_entity_extracted_key(self) -> None:
        r1: dict[str, Any] = {"extra": {}}
        r2: dict[str, Any] = {
            "entity_extracted": {"pag_1": {"EntA": {}}},
            "extra": {},
        }
        merged = _merge_results([r1, r2])

        assert "pag_1" in merged["entity_extracted"]


# ── _is_empty_result ────────────────────────────────────────────────────────


class TestIsEmptyResult:
    def test_empty_entity_extracted_is_empty(self) -> None:
        assert _is_empty_result({"entity_extracted": {}, "extra": {}}) is True

    def test_missing_entity_extracted_is_empty(self) -> None:
        assert _is_empty_result({"extra": {}}) is True

    def test_non_empty_is_not_empty(self) -> None:
        result = {"entity_extracted": {"pag_1": {"X": {}}}, "extra": {}}
        assert _is_empty_result(result) is False


# ── extract_entities ────────────────────────────────────────────────────────


class TestExtractEntities:
    def _patch_batches(self, mocker, batches: list) -> None:
        mocker.patch.object(ee_mod, "_load_entity_batches", return_value=batches)

    def test_builds_text_file_in_from_page_markers(self, mocker) -> None:
        """RE_PAGE_SPLIT viene usato per costruire texts per pagina."""
        self._patch_batches(mocker, [_BATCH_A])
        mock_call = mocker.patch.object(ee_mod, "_call_single_batch", return_value=_RESULT_A)
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        args, _ = mock_call.call_args
        texts = args[0]["texts"]  # text_file_in è il primo argomento posizionale
        assert "pag_1" in texts
        assert "pag_2" in texts
        assert "Testo della prima pagina." in texts["pag_1"]
        assert "Testo della seconda pagina." in texts["pag_2"]

    def test_one_call_per_batch(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mock_call = mocker.patch.object(ee_mod, "_call_single_batch", return_value=_RESULT_A)
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert mock_call.call_count == 2

    def test_results_from_all_batches_are_merged(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[_RESULT_A, _RESULT_B])
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        merged = extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert "Gruppo ISP" in merged["entity_extracted"]["pag_1"]
        assert "BdT" in merged["entity_extracted"]["pag_1"]
        assert "pag_2" in merged["entity_extracted"]

    def test_none_batch_result_is_skipped(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[None, _RESULT_B])
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        merged = extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert "pag_1" in merged["entity_extracted"]
        assert "Gruppo ISP" not in merged["entity_extracted"].get("pag_1", {})

    def test_batch_exception_is_skipped(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[RuntimeError("boom"), _RESULT_B])
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        merged = extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert "pag_1" in merged["entity_extracted"]

    def test_retry_on_empty_result(self, mocker) -> None:
        """Prima chiamata restituisce vuoto, la seconda ha entità: viene restituita la seconda."""
        self._patch_batches(mocker, [_BATCH_A])
        mock_call = mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[_EMPTY_RESULT, _RESULT_A])
        mock_sleep = mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        result = extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert not _is_empty_result(result)
        assert mock_call.call_count == 2
        mock_sleep.assert_called_once_with(RETRY_DELAY_S)

    def test_raises_after_all_retries_exhausted(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A])
        mocker.patch.object(ee_mod, "_call_single_batch", return_value=_EMPTY_RESULT)
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with pytest.raises(RuntimeError, match="empty result"):
            extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

    def test_total_call_count_on_full_retry(self, mocker) -> None:
        """Con 2 batch e MAX_RETRIES=3: (MAX_RETRIES+1) tentativi x 2 batch."""
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mock_call = mocker.patch.object(ee_mod, "_call_single_batch", return_value=_EMPTY_RESULT)
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with pytest.raises(RuntimeError):
            extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert mock_call.call_count == (MAX_RETRIES + 1) * 2

    def test_sleep_called_between_retries(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A])
        mocker.patch.object(ee_mod, "_call_single_batch", return_value=_EMPTY_RESULT)
        mock_sleep = mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with pytest.raises(RuntimeError):
            extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert mock_sleep.call_count == MAX_RETRIES
        mock_sleep.assert_called_with(RETRY_DELAY_S)

    def test_no_sleep_on_first_attempt_success(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A])
        mocker.patch.object(ee_mod, "_call_single_batch", return_value=_RESULT_A)
        mock_sleep = mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        mock_sleep.assert_not_called()

    def test_logs_warning_on_retry(self, mocker, caplog: pytest.LogCaptureFixture) -> None:
        self._patch_batches(mocker, [_BATCH_A])
        mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[_EMPTY_RESULT, _RESULT_A])
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with caplog.at_level(logging.WARNING, logger="core.services.enrichment.entity_extraction"):
            extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert "retry" in caplog.text.lower()

    def test_logs_run_id_when_provided(self, mocker, caplog: pytest.LogCaptureFixture) -> None:
        self._patch_batches(mocker, [_BATCH_A])
        mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[_EMPTY_RESULT, _RESULT_A])
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with caplog.at_level(logging.INFO, logger="core.services.enrichment.entity_extraction"):
            extract_entities(cleaned_md=_SAMPLE_MD, token="tok", run_id="run-123")  # noqa: S106

        assert "run_id=run-123" in caplog.text

    def test_logs_warning_on_none_batch(self, mocker, caplog: pytest.LogCaptureFixture) -> None:
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mocker.patch.object(ee_mod, "_call_single_batch", side_effect=[None, _RESULT_B])
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with caplog.at_level(logging.WARNING, logger="core.services.enrichment.entity_extraction"):
            extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        assert "None" in caplog.text or "restituito None" in caplog.text

    def test_parallelism_uses_max_workers(self, mocker) -> None:
        self._patch_batches(mocker, [_BATCH_A, _BATCH_B])
        mocker.patch.object(ee_mod, "_call_single_batch", return_value=_RESULT_A)
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        mock_executor_cls = mocker.patch(
            "core.services.enrichment.entity_extraction.ThreadPoolExecutor",
            wraps=ee_mod.ThreadPoolExecutor,
        )

        extract_entities(cleaned_md=_SAMPLE_MD, token="tok")  # noqa: S106

        mock_executor_cls.assert_called_once_with(max_workers=MAX_WORKERS)

    def test_md_without_page_markers_produces_empty_texts(self, mocker) -> None:
        """Markdown senza [PAGE N] → texts vuoto → entity_extracted vuoto per ogni tentativo."""
        self._patch_batches(mocker, [_BATCH_A])
        mock_call = mocker.patch.object(ee_mod, "_call_single_batch", return_value=_EMPTY_RESULT)
        mocker.patch("core.services.enrichment.entity_extraction.time.sleep")

        with pytest.raises(RuntimeError):
            extract_entities(cleaned_md="Testo senza marker di pagina.", token="tok")  # noqa: S106

        args, _ = mock_call.call_args
        assert args[0]["texts"] == {}  # text_file_in è il primo argomento posizionale
