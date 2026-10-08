import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, Field

from core.models.summary import DocumentSummaries, TagSummary
from core.models.tagging.output import DocumentPublicationDate, DocumentTaggingOutput, OutputTag
from core.models.tagging.types import Confidence, TagKey, TipoCitazione
from core.services.registry.enti import ente_code, entity_label
from core.services.registry.hierarchy import mo_code, odc_code, rm_code
from core.services.text.pages import parse_pages


class Scope(StrEnum):
    fac = "fac"
    vigilanza = "vigilanza"


class DocumentInsertResponse(BaseModel):
    message: str
    run_id: str


class ClassifiedField(BaseModel):
    """Esito di una classificazione (RM / MO / OdC): valore + confidence."""

    value: str
    confidence: Confidence | None


class Tag(BaseModel):
    ente: str
    pages: list[int]
    risk_model: ClassifiedField
    macro_obiettivo: ClassifiedField
    obiettivo_di_controllo: ClassifiedField
    citazione: str
    tipo_citazione: TipoCitazione
    table_content: str | None = None
    analisi: TagSummary

    @classmethod
    def from_output_tag(cls, output_tag: OutputTag, analisi: TagSummary) -> "Tag":
        return cls(
            ente=ente_code(output_tag.ente),
            pages=parse_pages(output_tag.pagina),
            risk_model=ClassifiedField(value=rm_code(output_tag.risk_model), confidence=output_tag.rm_confidence),
            macro_obiettivo=ClassifiedField(value=mo_code(output_tag.mo), confidence=output_tag.mo_confidence),
            obiettivo_di_controllo=ClassifiedField(
                value=odc_code(output_tag.odc), confidence=output_tag.odc_confidence
            ),
            citazione=output_tag.citazione,
            tipo_citazione=output_tag.tipo_citazione,
            table_content=output_tag.table_content,
            analisi=analisi,
        )


class TaggingResult(BaseModel):
    date: DocumentPublicationDate | None
    tags: list[Tag]

    @classmethod
    def from_document_tagging_output(
        cls,
        output: DocumentTaggingOutput,
        document_summaries: DocumentSummaries,
    ) -> "TaggingResult":
        analisi_by_tag = {
            TagKey(
                risk_model=entry.tag.risk_model, mo=entry.tag.mo, odc=entry.tag.odc, ente=entry.tag.ente
            ): entry.analisi
            for entry in document_summaries.summaries
        }

        tags: list[Tag] = []
        for output_tag in output.tags:
            if output_tag.mo is None or output_tag.odc is None:
                continue

            analisi = analisi_by_tag.get(
                TagKey(risk_model=output_tag.risk_model, mo=output_tag.mo, odc=output_tag.odc, ente=output_tag.ente)
            )
            if analisi is None:
                continue

            tags.append(Tag.from_output_tag(output_tag, analisi))

        return cls(
            date=output.date,
            tags=tags,
        )


class TaggingResponse(BaseModel):
    file_name: str
    scope: Scope
    tagging_results: TaggingResult


class ErrorAck(BaseModel):
    step: str
    exception_message: str = Field(alias="exceptionMessage")
    error_code: int = Field(alias="errorCode")
    retry_call: bool = Field(alias="retryCall")


class ClassificationAck(BaseModel):
    """
    A model used for both the results of the classification process
    and for error handling. This model contains the following fields:
    """

    run_id: str
    error: ErrorAck | None = None
    data: dict[str, Any]
    message: str | None = None


class TaggingTestCaseStatusResponse(BaseModel):
    run_id: str
    state: str = Field(...)
    error: ErrorAck | None = None
    data: TaggingResponse | None = None


Filter = list[Any]


class TagToSummarize(BaseModel):
    entity_id: str = Field(alias="entityId")
    entity: str
    risk_model_id: str = Field(alias="riskModelId")
    macro_objective_id: str = Field(alias="macroObjectiveId")
    objective_of_control_id: str = Field(alias="objectiveOfControlId")
    citation: str
    document: str

    def to_pipeline_dict(self) -> dict[str, str]:
        return {
            "Risk Model": self.risk_model_id,
            "MO": self.macro_objective_id,
            "OdC": self.objective_of_control_id,
            "Ente": entity_label(self.entity),
            "Citazione": self.citation,
            "Documento": self.document,
        }


class SummaryRequest(BaseModel):
    mail: EmailStr
    user: str
    user_wac: str = Field(alias="userWac")
    filters: list[Filter]
    entity_risk_id: str = Field(alias="entityRiskId")
    tags_to_summarize: Annotated[
        list[TagToSummarize],
        Field(alias="tagsToSummarize", min_length=1, max_length=200),
    ]


class ResponseMessage(BaseModel):
    mail: EmailStr
    user: str
    user_wac: str = Field(alias="userWac")
    entity_risk_id: str = Field(alias="entityRiskId")
    summary: str


class SummaryResponse(BaseModel):
    data: str = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    run_id: str
    message: ResponseMessage | None = None
    error: ErrorAck | None = None
