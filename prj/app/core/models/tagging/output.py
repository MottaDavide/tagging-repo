"""Modello Pydantic dell'output di `tag_document` (formato identico alla ground truth)."""

from typing import Literal

from pydantic import ConfigDict, Field

from core.models.strict import StrictModel
from core.models.tagging.stats import TaggerStats
from core.models.tagging.types import Confidence, TipoCitazione


class OutputTag(StrictModel):
    """Tag in formato GT (chiavi PascalCase italiane su disco).

    Gli alias sono bidirezionali (`alias` + `populate_by_name`): la serializzazione su
    disco usa le chiavi GT (`model_dump(by_alias=True)`), mentre la costruzione in-memory
    resta per nome campo e il reload del JSON GT (summarize_document) valida per alias.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pagina: str = Field(alias="Pagina")
    risk_model: str = Field(alias="Risk Model")
    rm_confidence: Confidence | None = Field(alias="Risk Model Confidence")
    mo: str = Field(alias="MO")
    mo_confidence: Confidence | None = Field(alias="MO Confidence")
    odc: str = Field(alias="OdC")
    odc_confidence: Confidence | None = Field(alias="OdC Confidence")
    ente: str = Field(alias="Ente")
    citazione: str = Field(alias="Citazione")
    tipo_citazione: TipoCitazione = Field(default="text", alias="Tipo Citazione")
    table_id: str | None = Field(default=None, alias="TableId")
    table_content: str | None = Field(default=None, alias="TableContent")


class DocumentPublicationDate(StrictModel):
    year: int | None = Field(
        None, description="Anno normalizzato nel formato YYYY (es. 2024). Null se non determinabile."
    )
    quarter: Literal["Q1", "Q2", "Q3", "Q4"] | None = Field(
        None,
        description="Trimestre/quarter normalizzato nel formato QN (es. Q3). Null se il trimestre/quarter non è determinabile.",
    )


class DocumentTaggingOutput(StrictModel):
    """Output completo di `tag_document` per un singolo documento."""

    filename: str
    date: DocumentPublicationDate | None
    tags: list[OutputTag]
    stats: TaggerStats
