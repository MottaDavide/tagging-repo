from __future__ import annotations

import asyncio
import functools
import importlib
import inspect
import json
import re
import sys
import types
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials

from core.models.entities.entities import Scope, SummaryRequest, TaggingResponse, TaggingResult
from core.models.summary import DocumentSummaries
from core.models.tagging.output import DocumentPublicationDate, DocumentTaggingOutput
from core.models.tagging.stats import TaggerStats


def _fake_output(filename: str = "doc") -> DocumentTaggingOutput:
    return DocumentTaggingOutput(
        filename=filename,
        date=DocumentPublicationDate(year=None, quarter=None),
        tags=[],
        stats=TaggerStats(),
    )


def _fake_summaries() -> DocumentSummaries:
    return DocumentSummaries(summaries=[])


def _make_upload_file(content: bytes, filename: str = "doc.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def _make_package(name: str, path: Path | None = None) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = [str(path)] if path is not None else []  # type: ignore[attr-defined]
    return module


def _make_module(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _one_tag(entity_id: str = "E1") -> dict:
    return {
        "entityId": entity_id,
        "entity": entity_id + " NOME ENTE",
        "riskModelId": "RM1",
        "macroObjectiveId": "MO1",
        "objectiveOfControlId": "OdC1",
        "citation": "short citation",
        "document": "document",
    }


def _make_request(n_tags: int = 1) -> SummaryRequest:
    tags = [_one_tag(f"E{i}") for i in range(n_tags)]
    return SummaryRequest.model_validate(
        {
            "mail": "user@example.com",
            "user": "Alice",
            "userWac": "WAC001",
            "filters": [],
            "entityRiskId": "ERI-1",
            "tagsToSummarize": tags,
        }
    )


def _build_fake_on_error_send_email(email_notifications: list[dict[str, object]]):
    def _fake_on_error_send_email(content_key: str):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    bound = inspect.signature(func).bind(*args, **kwargs)
                    bound.apply_defaults()
                    email_notifications.append(
                        {
                            "content_key": content_key,
                            "run_id": bound.arguments.get("run_id"),
                            "step": getattr(exc, "current_step", "unknown"),
                            "exception_message": str(exc),
                        }
                    )

                return None

            return wrapper

        return decorator

    return _fake_on_error_send_email


@pytest.fixture
def endpoints_mod(tmp_path: Path):
    for module_name in ("api.routers.v1.endpoints", "api.routers.v1", "api.routers", "api"):
        sys.modules.pop(module_name, None)

    api_module = _make_package("api", Path("prj/app/api").resolve())
    api_routers_module = _make_package("api.routers", Path("prj/app/api/routers").resolve())
    api_routers_v1_module = _make_package("api.routers.v1", Path("prj/app/api/routers/v1").resolve())
    api_module.routers = api_routers_module  # type: ignore[attr-defined]
    api_routers_module.v1 = api_routers_v1_module  # type: ignore[attr-defined]

    bdlpkg_module = _make_package("bdlpkg")
    bdlpkg_routers_module = _make_package("bdlpkg.routers")
    bdlpkg_utils_module = _make_package("bdlpkg.utils")
    bdlpkg_bdlfile_module = _make_package("bdlpkg.utils.bdlfile")
    bdlpkg_bdlfile_services_module = _make_package("bdlpkg.utils.bdlfile.services")
    bdlpkg_module.routers = bdlpkg_routers_module  # type: ignore[attr-defined]
    bdlpkg_module.utils = bdlpkg_utils_module  # type: ignore[attr-defined]
    bdlpkg_utils_module.bdlfile = bdlpkg_bdlfile_module  # type: ignore[attr-defined]
    bdlpkg_bdlfile_module.services = bdlpkg_bdlfile_services_module  # type: ignore[attr-defined]

    internal_module = _make_module("bdlpkg.routers.internal", router=MagicMock())
    bdlpkg_routers_module.internal = internal_module  # type: ignore[attr-defined]

    def _fake_config(name: str) -> dict:
        if name == "tagging.yaml":
            return {
                "temp_file": {
                    "path": str(tmp_path),
                    "filename": "raw.pdf",
                    "test-case-result-path": str(tmp_path / "results"),
                }
            }
        if name == "entity_extraction.yaml":
            return {"soa_detection": {"env": "local", "max_workers": 1, "max_retries": 0, "retry_delay_s": 0.0}}
        if name == "mail.yaml":
            return {
                "email_recipient": ["dev@example.com"],
                "tagging_error_content": "step={step} msg={exception_message} tb={traceback}",
                "dynamic_summary_error_content": "step={step} msg={exception_message} tb={traceback}",
            }
        return {"application": {"name": "test-app"}}

    bdlfile_module = _make_module(
        "bdlpkg.utils.bdlfile.services.bdlfile",
        get_obj_from_config_path=_fake_config,
    )
    bdlpkg_bdlfile_services_module.bdlfile = bdlfile_module  # type: ignore[attr-defined]

    class FakeLayer:
        def __init__(self, token: str) -> None:
            self.token = token

    email_notifications: list[dict[str, object]] = []

    modules = {
        "api": api_module,
        "api.routers": api_routers_module,
        "api.routers.v1": api_routers_v1_module,
        "bdlpkg": bdlpkg_module,
        "bdlpkg.routers": bdlpkg_routers_module,
        "bdlpkg.routers.internal": internal_module,
        "bdlpkg.utils": bdlpkg_utils_module,
        "bdlpkg.utils.bdlfile": bdlpkg_bdlfile_module,
        "bdlpkg.utils.bdlfile.services": bdlpkg_bdlfile_services_module,
        "bdlpkg.utils.bdlfile.services.bdlfile": bdlfile_module,
        "genfactory": _make_module("genfactory", Layer=FakeLayer),
        "core.services.llm_client": _make_module("core.services.llm_client", DEFAULT_MODEL="fake-model"),
        "core.services.text.markdown": _make_module(
            "core.services.text.markdown",
            extract_title=lambda text: "title",
            RE_PAGE_SPLIT=re.compile(r"\[PAGE (\d+)\](.*?)(?=\[PAGE \d+\]|\Z)", re.DOTALL),
        ),
        "core.orchestrators.summarize_document": _make_module(
            "core.orchestrators.summarize_document",
            summarize_tags=lambda *args, **kwargs: _fake_summaries(),
        ),
        "core.orchestrators.tag_document": _make_module(
            "core.orchestrators.tag_document",
            tag_document_units=lambda *args, **kwargs: _fake_output(),
        ),
        "core.services.enrichment.annotate": _make_module(
            "core.services.enrichment.annotate",
            annotate_document=lambda *args, **kwargs: "annotated-md",
        ),
        "core.services.parsing.parse": _make_module(
            "core.services.parsing.parse",
            process_file=lambda *args, **kwargs: None,
        ),
        "core.services.parsing.prepare": _make_module(
            "core.services.parsing.prepare",
            clean_document=lambda raw: raw,
        ),
        "core.services.tagging.resources": _make_module(
            "core.services.tagging.resources",
            load_tagging_resources=lambda: ([], MagicMock(name="hierarchy")),
        ),
        "core.utils.ack": _make_module(
            "core.utils.ack",
            send_ack=lambda *args, **kwargs: None,
        ),
        "core.utils.send_email": _make_module(
            "core.utils.send_email",
            on_error_send_email=_build_fake_on_error_send_email(email_notifications),
        ),
        "core.orchestrators.dynamic_summary": _make_module(
            "core.orchestrators.dynamic_summary",
            summarize_tags=lambda *args, **kwargs: None,
            render_dynamic_summary_markdown=lambda *args, **kwargs: "",
        ),
        "core.services.dynamic_summary": _make_package("core.services.dynamic_summary"),
        "core.services.dynamic_summary.resources": _make_module(
            "core.services.dynamic_summary.resources",
            load_dynamic_summary_resources=lambda: ([], MagicMock(), "prompt"),
        ),
    }

    with patch.dict(sys.modules, modules):
        module = importlib.import_module("api.routers.v1.endpoints")
        module._CONFIG = {"path": str(tmp_path), "filename": "raw.pdf"}
        module._test_email_notifications = email_notifications
        yield module


class TestCleanupTempDirectory:
    def test_deletes_all_items(self, endpoints_mod, tmp_path: Path) -> None:
        temp_dir = tmp_path / "run"
        nested_dir = temp_dir / "nested"
        nested_dir.mkdir(parents=True)
        (temp_dir / "a.txt").write_text("a", encoding="utf-8")
        (nested_dir / "b.txt").write_text("b", encoding="utf-8")

        endpoints_mod.cleanup_temp_directory(temp_dir, "run-1")

        assert temp_dir.exists()
        assert list(temp_dir.iterdir()) == []

    def test_logs_warning_when_directory_is_missing(self, endpoints_mod, tmp_path: Path, caplog) -> None:
        missing_dir = tmp_path / "missing"

        endpoints_mod.cleanup_temp_directory(missing_dir, "run-1")

        assert "Cleanup skipped because directory does not exist" in caplog.text

    def test_continues_when_single_item_deletion_fails(self, endpoints_mod, tmp_path: Path, caplog) -> None:
        temp_dir = tmp_path / "run"
        nested_dir = temp_dir / "nested"
        nested_dir.mkdir(parents=True)
        file_path = temp_dir / "a.txt"
        file_path.write_text("a", encoding="utf-8")

        def fail_rmtree(path: Path) -> None:
            raise OSError(f"cannot delete {path}")

        with patch.object(endpoints_mod.shutil, "rmtree", side_effect=fail_rmtree):
            endpoints_mod.cleanup_temp_directory(temp_dir, "run-1")

        assert not file_path.exists()
        assert nested_dir.exists()
        assert "Failed to delete temporary item" in caplog.text


class TestBackgroundTagging:
    @pytest.mark.parametrize("scope", [Scope.fac, Scope.vigilanza])
    def test_sends_success_ack_and_cleans_up(self, endpoints_mod, tmp_path: Path, scope: Scope) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)

        def fake_parse(
            args: list[Path], layer: object, run_id: str | None = None, **kwargs: object
        ) -> tuple[str, bool, float]:
            del args, layer, run_id, kwargs
            raw_path.with_suffix(".md").write_text("raw markdown", encoding="utf-8")
            raw_path.with_name("entities.json").write_text("{}", encoding="utf-8")
            return raw_path.name, True, 0.0

        send_ack_mock = MagicMock()
        cleanup_mock = MagicMock()
        output = _fake_output("raw")
        parse_mock = MagicMock(side_effect=fake_parse)

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "process_file_parse", parse_mock))
            stack.enter_context(patch.object(endpoints_mod, "clean_document", side_effect=lambda raw: f"clean::{raw}"))
            stack.enter_context(
                patch.object(endpoints_mod, "extract_entities", side_effect=lambda cleaned_md, token, run_id=None: {})
            )
            annotate_mock = stack.enter_context(
                patch.object(endpoints_mod, "annotate_document", side_effect=lambda **kwargs: "annotated")
            )
            stack.enter_context(patch.object(endpoints_mod, "load_tagging_resources", return_value=([], MagicMock())))
            tag_document_mock = stack.enter_context(
                patch.object(endpoints_mod, "tag_document_units", return_value=output)
            )
            summaries = _fake_summaries()
            summarize_mock = stack.enter_context(patch.object(endpoints_mod, "summarize_tags", return_value=summaries))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))
            stack.enter_context(patch.object(endpoints_mod, "cleanup_temp_directory", cleanup_mock))

            endpoints_mod.background_tagging(
                raw_path, MagicMock(), "doc.pdf", scope, "run-1", endpoints_mod.AckTaggingReporter()
            )

        expected_data = TaggingResponse(
            file_name="doc.pdf",
            scope=scope,
            tagging_results=TaggingResult.from_document_tagging_output(output, document_summaries=summaries),
        ).model_dump()
        assert parse_mock.call_args.kwargs["raise_on_error"] is True
        send_ack_mock.assert_called_once_with(data=expected_data, mode="tagging", run_id="run-1")
        cleanup_mock.assert_called_once_with(raw_path.parent, "run-1")
        assert parse_mock.call_args.kwargs["run_id"] == "run-1"
        assert annotate_mock.call_args.kwargs["run_id"] == "run-1"
        assert tag_document_mock.call_args.kwargs["run_id"] == "run-1"
        assert summarize_mock.call_args.kwargs["run_id"] == "run-1"

    def test_sends_error_ack_and_skips_cleanup_on_failure(self, endpoints_mod, tmp_path: Path) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)
        send_ack_mock = MagicMock()
        cleanup_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "process_file_parse", side_effect=RuntimeError("boom")))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))
            stack.enter_context(patch.object(endpoints_mod, "cleanup_temp_directory", cleanup_mock))

            endpoints_mod.background_tagging(
                raw_path, MagicMock(), "doc.pdf", Scope.fac, "run-1", endpoints_mod.AckTaggingReporter()
            )

        send_ack_mock.assert_called_once()
        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["data"] == {}
        assert kwargs["mode"] == "tagging"
        assert kwargs["run_id"] == "run-1"
        assert kwargs["error"].step == "parsing_document"
        assert kwargs["error"].exception_message == "boom"
        cleanup_mock.assert_not_called()

    def test_sends_error_ack_with_soa_empty_result_message(self, endpoints_mod, tmp_path: Path) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)
        send_ack_mock = MagicMock()

        def fake_parse(
            args: list[Path], layer: object, run_id: str | None = None, **kwargs: object
        ) -> tuple[str, bool, float]:
            del args, layer, run_id, kwargs
            raw_path.with_suffix(".md").write_text("raw markdown", encoding="utf-8")
            return raw_path.name, True, 0.0

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "process_file_parse", side_effect=fake_parse))
            stack.enter_context(patch.object(endpoints_mod, "clean_document", side_effect=lambda raw: f"clean::{raw}"))
            stack.enter_context(
                patch.object(
                    endpoints_mod,
                    "extract_entities",
                    side_effect=RuntimeError("SOA entity extraction returned empty result after 3 retries."),
                )
            )
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))

            endpoints_mod.background_tagging(
                raw_path, MagicMock(), "doc.pdf", Scope.fac, "run-1", endpoints_mod.AckTaggingReporter()
            )

        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["run_id"] == "run-1"
        assert kwargs["error"].step == "soa_detection"
        assert kwargs["error"].exception_message == "SOA entity extraction returned empty result after 3 retries."

    def test_uses_parsing_step_when_parser_returns_failed_status(self, endpoints_mod, tmp_path: Path) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)
        send_ack_mock = MagicMock()
        cleanup_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(endpoints_mod, "process_file_parse", return_value=("raw.pdf", False, 1.23))
            )
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))
            stack.enter_context(patch.object(endpoints_mod, "cleanup_temp_directory", cleanup_mock))

            endpoints_mod.background_tagging(
                raw_path, MagicMock(), "doc.pdf", Scope.fac, "run-1", endpoints_mod.AckTaggingReporter()
            )

        send_ack_mock.assert_called_once()
        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["error"].step == "parsing_document"
        assert "read_parsed_markdown" not in kwargs["error"].exception_message
        cleanup_mock.assert_not_called()

    def test_sends_error_email_with_run_id_when_parser_returns_failed_status(
        self, endpoints_mod, tmp_path: Path
    ) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)
        send_ack_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(endpoints_mod, "process_file_parse", return_value=("raw.pdf", False, 1.23))
            )
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))

            endpoints_mod.background_tagging(
                raw_path, MagicMock(), "doc.pdf", Scope.fac, "run-1", endpoints_mod.AckTaggingReporter()
            )

        send_ack_mock.assert_called_once()
        assert endpoints_mod._test_email_notifications == [
            {
                "content_key": "tagging_error_content",
                "run_id": "run-1",
                "step": "parsing_document",
                "exception_message": "Parsing failed for raw.pdf after 1.2s",
            }
        ]

    def test_logs_when_error_ack_fails(self, endpoints_mod, tmp_path: Path, caplog) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "process_file_parse", side_effect=RuntimeError("boom")))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", side_effect=RuntimeError("ack boom")))

            endpoints_mod.background_tagging(
                raw_path, MagicMock(), "doc.pdf", Scope.fac, "run-1", endpoints_mod.AckTaggingReporter()
            )

        assert "Sending error ack failed" in caplog.text

    def test_persists_success_status_and_skips_ack_when_disabled(self, endpoints_mod, tmp_path: Path) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)
        result_dir = tmp_path / "results"
        endpoints_mod._CONFIG = {
            "path": str(tmp_path),
            "filename": "raw.pdf",
            "test-case-result-path": str(result_dir),
        }

        def fake_parse(
            args: list[Path], layer: object, run_id: str | None = None, **kwargs: object
        ) -> tuple[str, bool, float]:
            del args, layer, kwargs, run_id
            raw_path.with_suffix(".md").write_text("raw markdown", encoding="utf-8")
            return raw_path.name, True, 0.0

        send_ack_mock = MagicMock()
        cleanup_mock = MagicMock()
        output = _fake_output("raw")
        parse_mock = MagicMock(side_effect=fake_parse)

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "process_file_parse", parse_mock))
            stack.enter_context(patch.object(endpoints_mod, "clean_document", side_effect=lambda raw: f"clean::{raw}"))
            stack.enter_context(
                patch.object(endpoints_mod, "extract_entities", side_effect=lambda cleaned_md, token, run_id=None: {})
            )
            annotate_mock = stack.enter_context(
                patch.object(endpoints_mod, "annotate_document", side_effect=lambda **kwargs: "annotated")
            )
            stack.enter_context(patch.object(endpoints_mod, "load_tagging_resources", return_value=([], MagicMock())))
            tag_document_mock = stack.enter_context(
                patch.object(endpoints_mod, "tag_document_units", return_value=output)
            )
            summaries = _fake_summaries()
            summarize_mock = stack.enter_context(patch.object(endpoints_mod, "summarize_tags", return_value=summaries))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))
            stack.enter_context(patch.object(endpoints_mod, "cleanup_temp_directory", cleanup_mock))

            endpoints_mod.background_tagging(
                raw_path,
                MagicMock(),
                "doc.pdf",
                Scope.fac,
                "run-1",
                endpoints_mod.TestCaseFileTaggingReporter(),
            )

        send_ack_mock.assert_not_called()
        cleanup_mock.assert_called_once_with(raw_path.parent, "run-1")
        payload = json.loads((result_dir / "run-1.json").read_text(encoding="utf-8"))
        assert payload["run_id"] == "run-1"
        assert payload["state"] == "cleanup_temp_directory"
        assert payload["error"] is None
        assert payload["data"]["file_name"] == "doc.pdf"
        assert parse_mock.call_args.kwargs["run_id"] == "run-1"
        assert annotate_mock.call_args.kwargs["run_id"] == "run-1"
        assert tag_document_mock.call_args.kwargs["run_id"] == "run-1"
        assert summarize_mock.call_args.kwargs["run_id"] == "run-1"

    def test_persists_error_status_when_ack_disabled(self, endpoints_mod, tmp_path: Path) -> None:
        raw_path = tmp_path / "run-1" / "raw.pdf"
        raw_path.parent.mkdir(parents=True)
        result_dir = tmp_path / "results"
        endpoints_mod._CONFIG = {
            "path": str(tmp_path),
            "filename": "raw.pdf",
            "test-case-result-path": str(result_dir),
        }
        send_ack_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "process_file_parse", side_effect=RuntimeError("boom")))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))

            endpoints_mod.background_tagging(
                raw_path,
                MagicMock(),
                "doc.pdf",
                Scope.fac,
                "run-1",
                endpoints_mod.TestCaseFileTaggingReporter(),
            )

        send_ack_mock.assert_not_called()
        payload = json.loads((result_dir / "run-1.json").read_text(encoding="utf-8"))
        assert payload["run_id"] == "run-1"
        assert payload["state"] == "parsing_document"
        assert payload["data"] is None
        assert payload["error"]["step"] == "parsing_document"


class TestWriteTempFile:
    def test_writes_uploaded_file(self, endpoints_mod, tmp_path: Path) -> None:
        upload = _make_upload_file(b"hello")

        out = asyncio.run(endpoints_mod.write_temp_file(upload, "run-1"))

        assert out == tmp_path / "run-1" / "raw.pdf"
        assert out.read_bytes() == b"hello"

    def test_raises_on_missing_file(self, endpoints_mod) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoints_mod.write_temp_file(None, "run-1"))

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Missing file."

    def test_raises_on_invalid_run_id(self, endpoints_mod) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoints_mod.write_temp_file(_make_upload_file(b"x"), ""))

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid run_id."

    def test_raises_on_empty_upload(self, endpoints_mod) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoints_mod.write_temp_file(_make_upload_file(b""), "run-1"))

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Uploaded file is empty."

    def test_raises_on_prepare_io_error(self, endpoints_mod) -> None:
        with (
            patch.object(endpoints_mod.os, "makedirs", side_effect=OSError("disk")),
            pytest.raises(HTTPException) as exc_info,
        ):
            asyncio.run(endpoints_mod.write_temp_file(_make_upload_file(b"x"), "run-1"))

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Failed to prepare temp file."

    def test_raises_on_unexpected_read_error(self, endpoints_mod) -> None:
        upload = _make_upload_file(b"x")

        async def fail_read() -> bytes:
            raise RuntimeError("boom")

        upload.read = fail_read

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoints_mod.write_temp_file(upload, "run-1"))

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Failed to read uploaded file."

    def test_raises_on_write_io_error(self, endpoints_mod) -> None:
        upload = _make_upload_file(b"x")

        with (
            patch.object(endpoints_mod.asyncio, "to_thread", new=AsyncMock(side_effect=OSError("disk"))),
            pytest.raises(HTTPException) as exc_info,
        ):
            asyncio.run(endpoints_mod.write_temp_file(upload, "run-1"))

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Failed to save temp file."


class TestTaggingEndpoint:
    def test_returns_accepted_response_and_schedules_background_task(self, endpoints_mod, tmp_path) -> None:
        raw_path = tmp_path / "raw.pdf"
        background_tasks = BackgroundTasks()
        add_task_spy = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(background_tasks, "add_task", add_task_spy))
            stack.enter_context(patch.object(endpoints_mod, "write_temp_file", new=AsyncMock(return_value=raw_path)))

            response = asyncio.run(
                endpoints_mod.tagging_endpoint(
                    file_name="doc.pdf",
                    scope=Scope.fac,
                    background_tasks=background_tasks,
                    file=_make_upload_file(b"hello"),
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
                )
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert add_task_spy.call_count == 1
        assert json.loads(response.body)["run_id"]

    def test_returns_document_insert_response_on_http_exception(self, endpoints_mod) -> None:
        with patch.object(
            endpoints_mod,
            "write_temp_file",
            new=AsyncMock(side_effect=HTTPException(status_code=400, detail="Missing file.")),
        ):
            response = asyncio.run(
                endpoints_mod.tagging_endpoint(
                    file_name="doc.pdf",
                    scope=Scope.fac,
                    background_tasks=BackgroundTasks(),
                    file=None,
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
                )
            )

        payload = json.loads(response.body)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert payload["message"] == "Tagging request failed before background execution. Detail: Missing file."
        assert payload["run_id"]

    def test_returns_document_insert_response_on_unexpected_exception(self, endpoints_mod) -> None:
        with patch.object(
            endpoints_mod,
            "write_temp_file",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = asyncio.run(
                endpoints_mod.tagging_endpoint(
                    file_name="doc.pdf",
                    scope=Scope.fac,
                    background_tasks=BackgroundTasks(),
                    file=_make_upload_file(b"hello"),
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
                )
            )

        payload = json.loads(response.body)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert payload["message"] == "Unexpected error in tagging endpoint before background execution."
        assert payload["run_id"]


class TestTaggingTestCaseEndpoint:
    def test_returns_accepted_response_and_schedules_background_task(self, endpoints_mod, tmp_path) -> None:
        raw_path = tmp_path / "raw.pdf"
        background_tasks = BackgroundTasks()
        add_task_spy = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(background_tasks, "add_task", add_task_spy))
            stack.enter_context(patch.object(endpoints_mod, "write_temp_file", new=AsyncMock(return_value=raw_path)))
            reporter_spy = stack.enter_context(patch.object(endpoints_mod.TestCaseFileTaggingReporter, "on_step"))

            response = asyncio.run(
                endpoints_mod.tagging_test_case_endpoint(
                    file_name="doc.pdf",
                    scope=Scope.fac,
                    background_tasks=background_tasks,
                    file=_make_upload_file(b"hello"),
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
                )
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        reporter_spy.assert_called_once()
        assert add_task_spy.call_count == 1
        assert isinstance(add_task_spy.call_args.args[-1], endpoints_mod.TestCaseFileTaggingReporter)
        assert json.loads(response.body)["run_id"]

    def test_returns_document_insert_response_on_http_exception(self, endpoints_mod) -> None:
        with patch.object(
            endpoints_mod,
            "write_temp_file",
            new=AsyncMock(side_effect=HTTPException(status_code=400, detail="Missing file.")),
        ):
            response = asyncio.run(
                endpoints_mod.tagging_test_case_endpoint(
                    file_name="doc.pdf",
                    scope=Scope.fac,
                    background_tasks=BackgroundTasks(),
                    file=None,
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
                )
            )

        payload = json.loads(response.body)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert payload["message"] == "Tagging request failed before background execution. Detail: Missing file."
        assert payload["run_id"]


class TestTaggingTestCaseStatusEndpoint:
    def test_returns_404_when_run_id_is_missing(self, endpoints_mod, tmp_path: Path) -> None:
        endpoints_mod._CONFIG = {
            "path": str(tmp_path),
            "filename": "raw.pdf",
            "test-case-result-path": str(tmp_path / "results"),
        }

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                endpoints_mod.tagging_test_case_status_endpoint(
                    "run-missing",
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
                )
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_202_when_run_is_pending(self, endpoints_mod, tmp_path: Path) -> None:
        result_dir = tmp_path / "results"
        result_dir.mkdir(parents=True)
        (result_dir / "run-1.json").write_text(
            json.dumps({"run_id": "run-1", "state": "tag_document", "error": None, "data": None}),
            encoding="utf-8",
        )
        endpoints_mod._CONFIG = {
            "path": str(tmp_path),
            "filename": "raw.pdf",
            "test-case-result-path": str(result_dir),
        }

        response = asyncio.run(
            endpoints_mod.tagging_test_case_status_endpoint(
                "run-1",
                token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            )
        )

        payload = json.loads(response.body)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert payload["state"] == "tag_document"
        assert payload["error"] is None
        assert payload["data"] is None

    def test_returns_200_when_run_is_completed(self, endpoints_mod, tmp_path: Path) -> None:
        result_dir = tmp_path / "results"
        result_dir.mkdir(parents=True)
        payload = {
            "run_id": "run-1",
            "state": "cleanup_temp_directory",
            "error": None,
            "data": {
                "file_name": "doc.pdf",
                "scope": "fac",
                "tagging_results": {"date": {"year": None, "quarter": None}, "tags": []},
            },
        }
        (result_dir / "run-1.json").write_text(json.dumps(payload), encoding="utf-8")
        endpoints_mod._CONFIG = {
            "path": str(tmp_path),
            "filename": "raw.pdf",
            "test-case-result-path": str(result_dir),
        }

        response = asyncio.run(
            endpoints_mod.tagging_test_case_status_endpoint(
                "run-1",
                token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            )
        )

        body = json.loads(response.body)
        assert response.status_code == status.HTTP_200_OK
        assert body["state"] == "cleanup_temp_directory"
        assert body["data"]["file_name"] == "doc.pdf"


class TestBackgroundDynamicSummary:
    def test_sends_success_ack_on_happy_path(self, endpoints_mod) -> None:
        request = _make_request()
        fake_result = MagicMock()
        fake_result.n_gruppi = 2
        fake_result.model_dump.return_value = {"entries": []}
        send_ack_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "summarize_dynamic_tags", return_value=fake_result))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))

            endpoints_mod.background_dynamic_summary(request, MagicMock(), "run-1")

        send_ack_mock.assert_called_once()
        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["mode"] == "summary"
        assert kwargs["run_id"] == "run-1"
        assert "error" not in kwargs

    def test_sends_success_ack_with_correct_response_message(self, endpoints_mod) -> None:
        request = _make_request()
        fake_result = MagicMock()
        fake_result.n_gruppi = 1
        send_ack_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "summarize_dynamic_tags", return_value=fake_result))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))
            stack.enter_context(
                patch.object(endpoints_mod, "render_dynamic_summary_markdown", return_value="## markdown")
            )

            endpoints_mod.background_dynamic_summary(request, MagicMock(), "run-2")

        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["mode"] == "summary"
        data = kwargs["data"]
        assert data["mail"] == "user@example.com"
        assert data["user"] == "Alice"
        assert data["userWac"] == "WAC001"
        assert data["entityRiskId"] == "ERI-1"
        assert data["summary"] == "## markdown"

    def test_sends_error_ack_on_summary_failure(self, endpoints_mod) -> None:
        request = _make_request()
        send_ack_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(endpoints_mod, "summarize_dynamic_tags", side_effect=ValueError("bad input"))
            )
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))

            endpoints_mod.background_dynamic_summary(request, MagicMock(), "run-err")

        send_ack_mock.assert_called_once()
        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["data"] == {}
        assert kwargs["mode"] == "summary"
        assert kwargs["run_id"] == "run-err"
        assert kwargs["error"].step == "run_summary"
        assert "bad input" in kwargs["error"].exception_message

    def test_sends_error_ack_on_resource_loading_failure(self, endpoints_mod) -> None:
        request = _make_request()
        send_ack_mock = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(endpoints_mod, "load_dynamic_summary_resources", side_effect=RuntimeError("no resources"))
            )
            stack.enter_context(patch.object(endpoints_mod, "send_ack", send_ack_mock))

            endpoints_mod.background_dynamic_summary(request, MagicMock(), "run-res-err")

        kwargs = send_ack_mock.call_args.kwargs
        assert kwargs["mode"] == "summary"
        assert kwargs["error"].step == "setup_resources"
        assert "no resources" in kwargs["error"].exception_message

    def test_logs_when_error_ack_send_fails(self, endpoints_mod, caplog) -> None:
        import logging

        request = _make_request()

        with ExitStack() as stack:
            stack.enter_context(patch.object(endpoints_mod, "summarize_dynamic_tags", side_effect=RuntimeError("boom")))
            stack.enter_context(patch.object(endpoints_mod, "send_ack", side_effect=RuntimeError("ack boom")))

            with caplog.at_level(logging.ERROR):
                endpoints_mod.background_dynamic_summary(request, MagicMock(), "run-ack-fail")

        assert "Sending error ack failed" in caplog.text


class TestDynamicSummaryEndpoint:
    def test_returns_202_and_schedules_background_task(self, endpoints_mod) -> None:
        request = _make_request()
        background_tasks = BackgroundTasks()
        add_task_spy = MagicMock()

        with patch.object(background_tasks, "add_task", add_task_spy):
            response = asyncio.run(
                endpoints_mod.dynamic_summary_endpoint(
                    request=request,
                    background_tasks=background_tasks,
                    token=HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok"),
                )
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        add_task_spy.assert_called_once()
        payload = json.loads(response.body)
        assert "run_id" in payload
        assert payload["error"] is None
        assert payload["message"] is None
