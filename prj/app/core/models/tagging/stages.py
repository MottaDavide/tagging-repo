"""Modelli Pydantic per gli stage della pipeline di tagging v2."""

from typing import Literal

from pydantic import ConfigDict, Field

from core.models.registry.odc_labels import AMLOdC, CreditoOdC
from core.models.strict import StrictModel
from core.models.tagging.output import DocumentPublicationDate
from core.models.tagging.types import Confidence


class RMGateAssignment(StrictModel):
    """Un Risk Model in scope a cui l'unità è pertinente."""

    risk_model: Literal["Credito", "AML"] = Field(description="Il risk model in scope pertinente all'unità.")
    confidence: Confidence = Field(description="Uno tra 'high', 'medium', 'low'.")
    reasoning: str = Field(description="Motivazione in 1-2 frasi.")


class RMGateOutput(StrictModel):
    """Esito del gate RM su una singola unità (multi-label; vuoto se non pertinente)."""

    assignments: list[RMGateAssignment] = Field(
        default_factory=list,
        description="Risk model in scope (Credito e/o AML) pertinenti all'unità; lista vuota se nessuno.",
    )


class EnteSelection(StrictModel):
    """Enti (struttura analizzata/controllata) selezionati dal pool locale del brano.

    `enti` è `list[str]` solo come base: a runtime `resolve_entes.py` genera per ogni pool una
    variante `list[Literal[pool]]` via `create_model` (non il generico degli OdC, che qui
    perderebbe memoria: vedi `_dynamic_ente_selection`).
    """

    enti: list[str] = Field(
        default_factory=list,
        description=(
            "Enti che sono la struttura ANALIZZATA/CONTROLLATA nel brano (l'oggetto dell'evidenza), "
            "non chi esegue il controllo. Lista vuota se nessun ente candidato è la struttura analizzata."
        ),
    )


class BranoOdC[T](StrictModel):
    """Un Obiettivo di Controllo assegnato a un brano (il MO è derivato dall'albero)."""

    odc_label: T = Field(description="Etichetta OdC ESATTA dalla lista fornita.")
    confidence: Confidence = Field(description="Uno tra 'high', 'medium', 'low'.")


class ClassifiedBrano[T](StrictModel):
    """Un brano estratto dall'unità con l'insieme degli OdC che tratta."""

    citazione: str = Field(
        description=(
            "Estratto VERBATIM copiato ESATTAMENTE dal testo dell'unità: il passaggio pertinente COMPLETO, "
            "che contiene l'evidenza integrale del/dei controllo/i. NON accorciarlo a un frammento — meglio più "
            "lungo che più corto; se l'intera unità è un unico finding coerente, copia l'intera unità. "
            "NON parafrasare."
        )
    )
    odc: list[BranoOdC[T]] = Field(
        min_length=1,
        description=(
            "Uno o più OdC che QUESTO STESSO brano tratta. Se il passaggio riguarda più temi/OdC, elencali tutti "
            "qui sotto lo stesso brano; NON duplicare il testo in brani separati."
        ),
    )


class ClassifyOutput[T](StrictModel):
    """Brani pertinenti estratti da un'unità (vuoto se l'unità non copre alcun OdC)."""

    brani: list[ClassifiedBrano[T]] = Field(
        default_factory=list,
        description="Brani distinti trovati nell'unità; lista vuota se l'unità non copre alcun OdC in scope.",
    )


# Sottoclassi nominate (non alias) per `response_format` in classify.
# Il titolo JSON schema deve rispettare '^[a-zA-Z0-9_-]+$' (vincolo Azure OpenAI):
# i semplici alias `ClassifyOutput[X]` producono nomi con '[' e ']' che vengono rifiutati.
class CreditoClassifyOutput(ClassifyOutput[CreditoOdC]):
    model_config = ConfigDict(title="CreditoClassifyOutput")


class AmlClassifyOutput(ClassifyOutput[AMLOdC]):
    model_config = ConfigDict(title="AmlClassifyOutput")


class DocumentDateOutput(StrictModel):
    """Output strutturato dell'estrazione della data documento."""

    date: DocumentPublicationDate
    citazione_data: str | None = Field(
        default=None,
        description="Citazione verbatim esatta del testo da cui è stata ricavata la data.",
    )
    rationale: str = Field(
        default="",
        description="Breve spiegazione del motivo per cui quella data è stata scelta.",
    )
