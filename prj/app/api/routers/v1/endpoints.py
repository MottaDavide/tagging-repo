import asyncio
import json
import logging
import os.path
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Protocol

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from fastapi import BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from genfactory import Layer
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_incrementing

from core.models.entities.entities import (
    DocumentInsertResponse,
    ErrorAck,
    ResponseMessage,
    Scope,
    SummaryRequest,
    SummaryResponse,
    TaggingResponse,
    TaggingResult,
    TaggingTestCaseStatusResponse,
)
from core.orchestrators.dynamic_summary import render_dynamic_summary_markdown
from core.orchestrators.dynamic_summary import summarize_tags as summarize_dynamic_tags
from core.orchestrators.summarize_document import summarize_tags
from core.orchestrators.tag_document import tag_document_units
from core.resources.tag_summary_system import TAG_SUMMARY_SYSTEM
from core.services.dynamic_summary.resources import load_dynamic_summary_resources
from core.services.enrichment.annotate import annotate_document
from core.services.enrichment.entity_extraction import extract_entities
from core.services.llm_client import DEFAULT_MODEL
from core.services.parsing.parse import process_file as process_file_parse
from core.services.parsing.prepare import clean_document
from core.services.tagging.resources import load_tagging_resources
from core.services.text.markdown import extract_title
from core.utils.ack import send_ack
from core.utils.send_email import on_error_send_email

security = HTTPBearer()
router = APIRouter(default_response_class=JSONResponse)
_CONFIG = get_obj_from_config_path("tagging.yaml")["temp_file"]
logger = logging.getLogger(__name__)


class TaggingReporter(Protocol):
    def on_step(self, run_id: str, state: str) -> None: ...

    def on_success(self, run_id: str, response: TaggingResponse) -> None: ...

    def on_error(self, run_id: str, error: ErrorAck) -> None: ...


class AckTaggingReporter:
    def on_step(self, run_id: str, state: str) -> None:
        del run_id, state

    def on_success(self, run_id: str, response: TaggingResponse) -> None:
        logger.info("[run_id=%s] Sending success ack", run_id)
        send_ack(data=response.model_dump(), run_id=run_id, mode="tagging")

    def on_error(self, run_id: str, error: ErrorAck) -> None:
        try:
            logger.info("[run_id=%s] Sending error ack for step=%s", run_id, error.step)
            send_ack(data={}, run_id=run_id, error=error, mode="tagging")
        except Exception:
            logger.exception("Sending error ack failed for run_id=%s, step=%s", run_id, error.step)
            raise


class TestCaseFileTaggingReporter:
    def __init__(self) -> None:
        self._state: str | None = None
        self._response: TaggingResponse | None = None

    def _persist_test_case_status(
        self,
        run_id: str,
        state: str,
        error: ErrorAck | None = None,
        data: TaggingResponse | None = None,
    ) -> None:
        result_file = _test_case_result_file(run_id)
        result_file.parent.mkdir(parents=True, exist_ok=True)
        payload = TaggingTestCaseStatusResponse(run_id=run_id, state=state, error=error, data=data)
        temp_file = result_file.with_name(f"{result_file.name}.{uuid.uuid4().hex}.tmp")
        temp_file.write_text(payload.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        for attempt in Retrying(
            retry=retry_if_exception_type(PermissionError),
            stop=stop_after_attempt(3),
            wait=wait_incrementing(start=0.05, increment=0.05),
            reraise=True,
        ):
            with attempt:
                temp_file.replace(result_file)

    def on_step(self, run_id: str, state: str) -> None:
        self._state = state
        self._persist_test_case_status(run_id, state, data=self._response)

    def on_success(self, run_id: str, response: TaggingResponse) -> None:
        self._response = response
        self._persist_test_case_status(run_id, self._state or "build_success_ack", data=response)

    def on_error(self, run_id: str, error: ErrorAck) -> None:
        self._persist_test_case_status(run_id, error.step, error=error)


def _test_case_result_file(run_id: str) -> Path:
    return Path(_CONFIG["test-case-result-path"]) / f"{run_id}.json"


def cleanup_temp_directory(directory: Path, run_id: str | None) -> None:
    try:
        if not directory.exists():
            logger.warning("[run_id=%s] Cleanup skipped because directory does not exist: %s", run_id, directory)
            return

        logger.info("[run_id=%s] Cleaning up temporary directory %s", run_id, directory)

        for item in directory.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                logger.info("[run_id=%s] Deleted temporary item %s", run_id, item)
            except OSError:
                logger.exception("[run_id=%s] Failed to delete temporary item %s", run_id, item)

        logger.info("[run_id=%s] Temporary directory cleanup completed: %s", run_id, directory)
    except Exception:
        logger.exception("[run_id=%s] Unexpected error during temporary directory cleanup: %s", run_id, directory)


def _raise_for_failed_parse(parse_result: tuple[str, bool, float]) -> None:
    if not parse_result[1]:
        raise RuntimeError(f"Parsing failed for {parse_result[0]} after {parse_result[2]:.1f}s")


@on_error_send_email("tagging_error_content")
def background_tagging(
    path: Path,
    layer: Layer,
    file_name: str,
    scope: Scope,
    run_id: str,
    reporter: TaggingReporter,
) -> None:
    current_step = "parsing_document"
    try:
        reporter.on_step(run_id, current_step)

        logger.info("[run_id=%s] Parsing document", run_id)
        parse_result = process_file_parse((path, path.parent), layer, raise_on_error=True, run_id=run_id)
        _raise_for_failed_parse(parse_result)

        md_path = path.with_suffix(".md")
        current_step = "read_parsed_markdown"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Reading parsed markdown from %s", run_id, md_path)
        raw = md_path.read_text(encoding="utf-8")

        current_step = "clean_document"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Cleaning document", run_id)
        cleaned = clean_document(raw)
        cleaned_path = path.with_name("cleaned.md")
        cleaned_path.write_text(cleaned, encoding="utf-8")

        current_step = "soa_detection"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Extracting entities via SOA detection", run_id)
        token_value = layer.token if isinstance(layer.token, str) else layer.token()
        all_entities = extract_entities(cleaned_md=cleaned, token=token_value, run_id=run_id)

        current_step = "annotate_document"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Annotating document", run_id)
        annotated = annotate_document(md_path=cleaned_path, all_entities=all_entities, run_id=run_id)
        annotated_path = path.with_name("annotated.md")
        annotated_path.write_text(annotated, encoding="utf-8")

        current_step = "load_tagging_resources"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Loading tagging resources", run_id)
        risk_models, hierarchy = load_tagging_resources()

        current_step = "tag_document"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Running final tagging", run_id)
        tagging_output = tag_document_units(layer, annotated_path, hierarchy, run_id=run_id)

        current_step = "document_summaries"
        reporter.on_step(run_id, current_step)
        logger.info("[run_id=%s] Generating per-tag document summaries", run_id)
        document_summaries = summarize_tags(
            layer,
            annotated_path.stem,
            extract_title(annotated),
            annotated,
            tagging_output.tags,
            TAG_SUMMARY_SYSTEM,
            hierarchy,
            risk_models,
            DEFAULT_MODEL,
            run_id=run_id,
        )

        result = TaggingResult.from_document_tagging_output(tagging_output, document_summaries=document_summaries)

        current_step = "build_success_ack"
        reporter.on_step(run_id, current_step)
        tagging_response = TaggingResponse(file_name=file_name, scope=scope, tagging_results=result)
        current_step = "send_success_ack"
        reporter.on_success(run_id, tagging_response)

        current_step = "cleanup_temp_directory"
        cleanup_temp_directory(path.parent, run_id)
        reporter.on_step(run_id, current_step)

        logger.info("Background tagging completed successfully for run_id=%s", run_id)
    except Exception as exc:
        exc.current_step = current_step  # type: ignore[attr-defined]
        logger.exception(
            "Background tagging failed for run_id=%s, file_name=%s, step=%s",
            run_id,
            file_name,
            current_step,
        )
        error_ack = ErrorAck(
            step=current_step,
            exceptionMessage=str(exc),
            errorCode=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryCall=True,
        )
        try:
            reporter.on_error(run_id, error_ack)
        except Exception:
            logger.exception("Error reporting failed for run_id=%s, step=%s", run_id, current_step)
        raise


async def write_temp_file(file: UploadFile | None, run_id: str) -> Path:
    if file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file.")

    if not run_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run_id.")

    run_id_path = os.path.join(_CONFIG["path"], run_id)

    try:
        os.makedirs(run_id_path, exist_ok=True)
        raw_document_data = await file.read()
    except OSError as exc:
        logger.exception("[run_id=%s] I/O error while preparing temp file", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare temp file.",
        ) from exc
    except Exception as exc:
        logger.exception("[run_id=%s] Unexpected error while reading uploaded file", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read uploaded file.",
        ) from exc

    if not raw_document_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    raw_document_path = os.path.join(run_id_path, _CONFIG["filename"])

    raw_document_file = Path(raw_document_path)

    try:
        await asyncio.to_thread(raw_document_file.write_bytes, raw_document_data)
    except OSError as exc:
        logger.exception("[run_id=%s] I/O error while writing temp file", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save temp file.",
        ) from exc

    return raw_document_file


@on_error_send_email("dynamic_summary_error_content")
def background_dynamic_summary(request: SummaryRequest, layer: Layer, run_id: str) -> None:
    current_step = "setup_resources"
    try:
        logger.info("[run_id=%s] Setting up input tags and resources.", run_id)
        input_tags = [tag.to_pipeline_dict() for tag in request.tags_to_summarize]
        risk_models, hierarchy, system_prompt = load_dynamic_summary_resources()

        current_step = "run_summary"
        logger.info("[run_id=%s] Running summary.", run_id)
        result = summarize_dynamic_tags(
            layer=layer,
            input_tags=input_tags,
            system_prompt=system_prompt,
            hierarchy=hierarchy,
            risk_models=risk_models,
        )

        result_md = render_dynamic_summary_markdown(summaries=result, hierarchy=hierarchy)
        current_step = "send_success_ack"
        logger.info("[run_id=%s] Sending success ack", run_id)
        response_message = ResponseMessage(
            mail=request.mail,
            user=request.user,
            userWac=request.user_wac,
            entityRiskId=request.entity_risk_id,
            summary=result_md,
        )
        send_ack(data=response_message.model_dump(by_alias=True), mode="summary", run_id=run_id)

        logger.info("[run_id=%s] Dynamic summary completed with %d groups.", run_id, result.n_gruppi)
    except Exception as exc:
        exc.current_step = current_step  # type: ignore[attr-defined]
        logger.exception(
            "Background dynamic summary failed for run_id=%s, step=%s",
            run_id,
            current_step,
        )
        error_ack = ErrorAck(
            step=current_step,
            exceptionMessage=str(exc),
            errorCode=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryCall=True,
        )
        try:
            logger.info("[run_id=%s] Sending error ack for step=%s", run_id, current_step)
            send_ack(data={}, mode="summary", run_id=run_id, error=error_ack)
        except Exception:
            logger.exception("Sending error ack failed for run_id=%s, step=%s", run_id, current_step)
        raise


async def _submit_tagging_request(
    file_name: str,
    scope: Scope,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    token: HTTPAuthorizationCredentials,
    *,
    send_ack_enabled: bool,
) -> JSONResponse:
    run_id = str(uuid.uuid4())
    reporter = AckTaggingReporter() if send_ack_enabled else TestCaseFileTaggingReporter()
    try:
        raw_document_path = await write_temp_file(file, run_id)
        if not send_ack_enabled:
            reporter.on_step(run_id, "parsing_document")
        layer = Layer(token=token.credentials)
        background_tasks.add_task(background_tagging, raw_document_path, layer, file_name, scope, run_id, reporter)
        message = f"The document has been accepted for tagging. File: {file.filename} will be processed. "
        message += f"RUN_ID: {run_id}"
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=DocumentInsertResponse(message=message, run_id=run_id).model_dump(),
        )
    except HTTPException as exc:
        logger.exception("[run_id=%s] Tagging request failed before background execution", run_id)
        message = f"Tagging request failed before background execution. Detail: {exc.detail}"
        return JSONResponse(
            status_code=exc.status_code,
            content=DocumentInsertResponse(message=message, run_id=run_id).model_dump(),
        )
    except Exception:
        logger.exception("[run_id=%s] Unexpected error in tagging endpoint before background execution", run_id)
        message = "Unexpected error in tagging endpoint before background execution."
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=DocumentInsertResponse(message=message, run_id=run_id).model_dump(),
        )


### APPLICATION ENDPOINTS (aggiungi i tuoi endpoint qui) ####


@router.post(
    path="/tagging",
    summary="Submit a document for asynchronous tagging",
    description="Upload a document and start the asynchronous parsing, annotation, tagging and summary flow.",
)
async def tagging_endpoint(
    file_name: str,
    scope: Scope,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    token: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
) -> JSONResponse:
    return await _submit_tagging_request(
        file_name=file_name,
        scope=scope,
        background_tasks=background_tasks,
        file=file,
        token=token,
        send_ack_enabled=True,
    )


@router.post(
    path="/tagging/test-case",
    summary="Submit a document for asynchronous tagging without callback",
    description="Upload a document and start the asynchronous tagging flow, then retrieve the result by polling.",
)
async def tagging_test_case_endpoint(
    file_name: str,
    scope: Scope,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    token: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
) -> JSONResponse:
    return await _submit_tagging_request(
        file_name=file_name,
        scope=scope,
        background_tasks=background_tasks,
        file=file,
        token=token,
        send_ack_enabled=False,
    )


@router.get(
    path="/tagging/test-case/retrieve/{run_id}",
    summary="Get asynchronous test-case tagging status",
    description="Returns current state and final payload for a test-case tagging run.",
)
async def tagging_test_case_status_endpoint(
    run_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
) -> JSONResponse:
    del token
    result_file = _test_case_result_file(run_id)
    if not result_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_id not found")

    payload = json.loads(result_file.read_text(encoding="utf-8"))
    response = TaggingTestCaseStatusResponse.model_validate(payload)
    is_pending = response.data is None and response.error is None
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED if is_pending else status.HTTP_200_OK,
        content=response.model_dump(by_alias=True),
    )


@router.post(
    path="/summary",
    summary="Dynamic summary of user-provided tags",
    description="Generates summary for user-provided tags based on text extracts",
    status_code=status.HTTP_202_ACCEPTED,
)
async def dynamic_summary_endpoint(
    request: SummaryRequest,
    background_tasks: BackgroundTasks,
    token: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
) -> JSONResponse:
    run_id = str(uuid.uuid4())
    try:
        layer = Layer(token=token.credentials)
        background_tasks.add_task(background_dynamic_summary, request, layer, run_id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=SummaryResponse(
                run_id=run_id,
            ).model_dump(by_alias=True),
        )
    except Exception:
        logger.exception("[run_id=%s] Unexpected error in summary endpoint before background execution", run_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=SummaryResponse(run_id=run_id).model_dump(by_alias=True),
        )
