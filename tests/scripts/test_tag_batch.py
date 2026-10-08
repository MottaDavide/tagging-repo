"""Test `tag_batch` (script batch runner)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

from genfactory.config.enums import Environment
from prj.scripts.tag_batch import (
    _STOP_SENTINEL,
    DEFAULT_USE_CASES,
    PARALLEL_USE_CASES,
    _env_for,
    _gt_stems,
    _resolve_doc_paths,
    _run_parallel,
    _run_serial,
    _worker_main,
    run,
)

from core.models.tagging.output import DocumentPublicationDate, DocumentTaggingOutput
from core.models.tagging.stats import TaggerStats


def _fake_output(filename: str = "x") -> DocumentTaggingOutput:
    return DocumentTaggingOutput(
        filename=filename,
        date=DocumentPublicationDate(year=2025, quarter="Q1"),
        tags=[],
        stats=TaggerStats(),
    )


# ── _resolve_doc_paths ─────────────────────────────────────────────────────


class TestResolveDocPaths:
    def test_no_files_returns_empty(self, tmp_path: Path, caplog) -> None:
        with caplog.at_level(logging.ERROR, logger="tag_batch"):
            out = _resolve_doc_paths(tmp_path, None, tmp_path / "out", force=False)
        assert out == []
        assert "Nessun documento" in caplog.text

    def test_glob_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x")
        (tmp_path / "b.md").write_text("y")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        out = _resolve_doc_paths(tmp_path, None, out_dir, force=False)
        names = sorted(p.name for p in out)
        assert names == ["a.md", "b.md"]

    def test_skip_already_processed_when_not_force(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x")
        (tmp_path / "b.md").write_text("y")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "a.json").write_text("done")

        out = _resolve_doc_paths(tmp_path, None, out_dir, force=False)
        assert [p.name for p in out] == ["b.md"]

    def test_force_keeps_all(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "a.json").write_text("done")
        out = _resolve_doc_paths(tmp_path, None, out_dir, force=True)
        assert len(out) == 1

    def test_single_file_exact_match(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("x")
        out = _resolve_doc_paths(tmp_path, "doc.md", tmp_path / "out", force=True)
        assert len(out) == 1
        assert out[0].name == "doc.md"

    def test_single_file_fallback_to_stem(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("x")
        out = _resolve_doc_paths(tmp_path, "doc", tmp_path / "out", force=True)
        assert len(out) == 1
        assert out[0].name == "doc.md"

    def test_filters_by_allowed_stems(self, tmp_path: Path) -> None:
        for name in ("a.md", "b.md", "c.md"):
            (tmp_path / name).write_text("x")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        out = _resolve_doc_paths(tmp_path, None, out_dir, force=False, allowed_stems={"a", "c"})
        assert [p.name for p in out] == ["a.md", "c.md"]


class TestGtStems:
    def test_extracts_stems(self, tmp_path: Path) -> None:
        gt = tmp_path / "gt.json"
        gt.write_text(json.dumps([{"filename": "Doc Uno.pdf", "tags": []}, {"filename": "due.md", "tags": []}]))
        assert _gt_stems(gt) == {"Doc Uno", "due"}


# ── _run_serial ────────────────────────────────────────────────────────────


class TestRunSerial:
    def test_processes_each_doc(self, tmp_path: Path, mocker) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        doc_a = tmp_path / "a.md"
        doc_a.write_text("a")

        mocker.patch("tag_batch.build_hierarchy", return_value=MagicMock())
        mocker.patch("tag_batch.init_genfactory", return_value=MagicMock())
        mocker.patch("tag_batch.tag_document_units", return_value=_fake_output("a"))
        mocker.patch("tag_batch.time.sleep")

        _run_serial([doc_a], out_dir, "m", "AUDIT")
        out_file = out_dir / "a.json"
        assert out_file.exists()
        payload = json.loads(out_file.read_text())
        assert payload["filename"] == "a"
        assert payload["date"]["year"] == 2025

    def test_handles_exception(self, tmp_path: Path, mocker, caplog) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        doc_a = tmp_path / "a.md"
        doc_a.write_text("a")

        mocker.patch("tag_batch.build_hierarchy", return_value=MagicMock())
        mocker.patch("tag_batch.init_genfactory", return_value=MagicMock())
        mocker.patch("tag_batch.tag_document_units", side_effect=RuntimeError("boom"))
        mocker.patch("tag_batch.time.sleep")

        with caplog.at_level(logging.ERROR, logger="tag_batch"):
            _run_serial([doc_a], out_dir, "m", "AUDIT")
        assert "ERRORE" in caplog.text
        assert not (out_dir / "a.json").exists()

    def test_sleeps_between_docs(self, tmp_path: Path, mocker) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        docs = [tmp_path / "a.md", tmp_path / "b.md"]
        for d in docs:
            d.write_text("x")

        mocker.patch("tag_batch.build_hierarchy", return_value=MagicMock())
        mocker.patch("tag_batch.init_genfactory", return_value=MagicMock())
        mocker.patch("tag_batch.tag_document_units", return_value=_fake_output("x"))
        sleep_mock = mocker.patch("tag_batch.time.sleep")

        _run_serial(docs, out_dir, "m", "AUDIT")
        assert sleep_mock.call_count == 1


# ── run (entry point) ──────────────────────────────────────────────────────


class TestRun:
    def test_returns_early_if_no_docs(self, tmp_path: Path, mocker) -> None:
        serial_spy = mocker.patch("tag_batch._run_serial")
        parallel_spy = mocker.patch("tag_batch._run_parallel")
        run(input_dir=tmp_path / "missing-in", output_dir=tmp_path / "out")
        serial_spy.assert_not_called()
        parallel_spy.assert_not_called()

    def test_dispatches_to_serial_with_single_use_case(self, tmp_path: Path, mocker) -> None:
        in_dir = tmp_path / "in"
        in_dir.mkdir()
        (in_dir / "doc.md").write_text("x")

        serial_spy = mocker.patch("tag_batch._run_serial")
        parallel_spy = mocker.patch("tag_batch._run_parallel")
        run(input_dir=in_dir, output_dir=tmp_path / "out", use_cases=("AUDIT",))
        serial_spy.assert_called_once()
        parallel_spy.assert_not_called()

    def test_dispatches_to_parallel_with_multi_use_case(self, tmp_path: Path, mocker) -> None:
        in_dir = tmp_path / "in"
        in_dir.mkdir()
        (in_dir / "doc.md").write_text("x")

        serial_spy = mocker.patch("tag_batch._run_serial")
        parallel_spy = mocker.patch("tag_batch._run_parallel")
        run(input_dir=in_dir, output_dir=tmp_path / "out", use_cases=("AUDIT", "AUDIT-SVIL"))
        parallel_spy.assert_called_once()
        serial_spy.assert_not_called()


# ── _run_parallel (con mock multiprocessing) ───────────────────────────────


class TestRunParallel:
    def test_uses_multiprocessing_spawn(self, tmp_path: Path, mocker) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        docs = [tmp_path / "a.md"]
        docs[0].write_text("x")

        fake_proc = MagicMock()
        fake_proc.is_alive.return_value = False
        fake_doc_queue = MagicMock()
        fake_result_queue = MagicMock()
        fake_result_queue.get.return_value = (str(docs[0]), None)

        fake_ctx = MagicMock()
        fake_ctx.Queue.side_effect = [fake_doc_queue, fake_result_queue]
        fake_ctx.Process.return_value = fake_proc

        mocker.patch("tag_batch.mp.get_context", return_value=fake_ctx)

        _run_parallel(docs, out_dir, "m", ("AUDIT", "AUDIT-SVIL"))

        assert fake_ctx.Process.call_count == 2
        assert fake_proc.start.call_count == 2
        assert fake_proc.join.call_count == 2

    def test_logs_failed_documents(self, tmp_path: Path, mocker, caplog) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        docs = [tmp_path / "doc.md"]
        docs[0].write_text("x")

        fake_proc = MagicMock()
        fake_proc.is_alive.return_value = False
        fake_result_queue = MagicMock()
        fake_result_queue.get.return_value = (str(docs[0]), "errore X")
        fake_doc_queue = MagicMock()

        fake_ctx = MagicMock()
        fake_ctx.Queue.side_effect = [fake_doc_queue, fake_result_queue]
        fake_ctx.Process.return_value = fake_proc
        mocker.patch("tag_batch.mp.get_context", return_value=fake_ctx)

        with caplog.at_level(logging.WARNING, logger="tag_batch"):
            _run_parallel(docs, out_dir, "m", ("AUDIT", "AUDIT-SVIL"))
        assert "fallito" in caplog.text

    def test_kills_workers_that_dont_terminate(self, tmp_path: Path, mocker, caplog) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        docs = [tmp_path / "doc.md"]
        docs[0].write_text("x")

        fake_proc = MagicMock()
        fake_proc.is_alive.return_value = True
        fake_proc.name = "tagger-AUDIT"
        fake_result_queue = MagicMock()
        fake_result_queue.get.return_value = (str(docs[0]), None)
        fake_doc_queue = MagicMock()

        fake_ctx = MagicMock()
        fake_ctx.Queue.side_effect = [fake_doc_queue, fake_result_queue]
        fake_ctx.Process.return_value = fake_proc
        mocker.patch("tag_batch.mp.get_context", return_value=fake_ctx)

        with caplog.at_level(logging.WARNING, logger="tag_batch"):
            _run_parallel(docs, out_dir, "m", ("AUDIT", "AUDIT-SVIL"))
        assert "non terminato" in caplog.text
        fake_proc.terminate.assert_called()


# ── costanti esposte ───────────────────────────────────────────────────────


class TestConstants:
    def test_default_use_cases_single(self) -> None:
        assert DEFAULT_USE_CASES == ("AUDIT-SVIL",)

    def test_parallel_use_cases_pair(self) -> None:
        assert PARALLEL_USE_CASES == ("AUDIT-SVIL", "AUDIT")

    def test_env_for_maps_use_case(self) -> None:
        assert _env_for("AUDIT-SVIL") == Environment.SVIL
        assert _env_for("AUDIT") == Environment.TEST
        assert _env_for("sconosciuto") == Environment.TEST


# ── _worker_main ───────────────────────────────────────────────────────────


class TestWorkerMain:
    def test_loops_until_sentinel_processes_doc(self, tmp_path: Path, mocker) -> None:
        import prj.scripts.tag_batch as runner_mod

        mocker.patch.object(runner_mod, "build_hierarchy", return_value=MagicMock())
        mocker.patch.object(runner_mod, "init_genfactory", return_value=mocker.MagicMock())
        mocker.patch.object(runner_mod, "tag_document_units", return_value=_fake_output())

        class FakeQueue:
            def __init__(self, items: list[str] | None = None) -> None:
                self._items: list = list(items or [])
                self.puts: list = []

            def get(self) -> str:  # type: ignore[override]
                return self._items.pop(0)

            def put(self, item: object) -> None:
                self.puts.append(item)

        doc_dir = tmp_path / "in"
        doc_dir.mkdir()
        (doc_dir / "doc.md").write_text("[PAGE 1]\nX")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        doc_q = FakeQueue([str(doc_dir / "doc.md"), _STOP_SENTINEL])
        res_q = FakeQueue()

        _worker_main(
            use_case_id="AUDIT",
            env_file="/dev/null",
            output_dir_str=str(out_dir),
            model="gpt-x",
            doc_queue=doc_q,  # type: ignore[arg-type]
            result_queue=res_q,  # type: ignore[arg-type]
        )

        assert (out_dir / "doc.json").exists()
        assert res_q.puts == [(str(doc_dir / "doc.md"), None)]

    def test_logs_exception_and_reports_failure(self, tmp_path: Path, mocker) -> None:
        import prj.scripts.tag_batch as runner_mod

        mocker.patch.object(runner_mod, "build_hierarchy", return_value=MagicMock())
        mocker.patch.object(runner_mod, "init_genfactory", return_value=mocker.MagicMock())
        mocker.patch.object(runner_mod, "tag_document_units", side_effect=RuntimeError("boom"))

        class FakeQueue:
            def __init__(self, items: list[str] | None = None) -> None:
                self._items: list = list(items or [])
                self.puts: list = []

            def get(self) -> str:  # type: ignore[override]
                return self._items.pop(0)

            def put(self, item: object) -> None:
                self.puts.append(item)

        doc_q = FakeQueue(["/some/doc.md", _STOP_SENTINEL])
        res_q = FakeQueue()

        _worker_main(
            use_case_id="AUDIT",
            env_file="/dev/null",
            output_dir_str=str(tmp_path),
            model="m",
            doc_queue=doc_q,  # type: ignore[arg-type]
            result_queue=res_q,  # type: ignore[arg-type]
        )
        assert res_q.puts == [("/some/doc.md", "boom")]
