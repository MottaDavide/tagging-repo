from pydantic import BaseModel, Field

from core.models.strict import StrictModel


class TagOccorrenza(BaseModel):
    """Una singola occorrenza (pagina + citazione) di un tag nel documento.

    Per le occorrenze di tipo tabella `citazione` è l'etichetta breve (``Tabella a pagina N``)
    e `table_content` porta l'HTML integrale della tabella, usato come evidenza al posto del
    solo riferimento nel prompt del summary.
    """

    pagina: str
    citazione: str
    table_content: str | None = None


class UniqueTag(BaseModel):
    """Tag unico: chiave `(RM, MO, OdC, Ente)` + tutte le sue occorrenze nel doc.

    `mo`, `odc` ed `ente` sono sempre valorizzati: i tag incompleti (MO/OdC/Ente
    nulli) vengono scartati a monte in `_build_output` (orchestratore `tag_document`).
    """

    risk_model: str
    mo: str
    odc: str
    ente: str
    occorrenze: list[TagOccorrenza] = Field(default_factory=list)


class TagSummary(StrictModel):
    """Analisi espositiva (template fisso) del documento per un singolo tag unico.

    Taglio descrittivo/espositivo: niente giudizi di rischio o valutazioni, solo
    ciò che il documento riporta in relazione al tag.
    """

    titolo: str
    sintesi: str
    aspetti_rilevanti: str
    quadro_complessivo: str


# Artefatto JSON su disco per documento ---------------------------------------


class TagSummaryEntry(StrictModel):
    """Un tag unico (con le sue occorrenze) + l'analisi espositiva generata."""

    tag: UniqueTag
    analisi: TagSummary


class DocumentSummaries(StrictModel):
    """Output completo dello step di summary per un singolo documento."""

    summaries: list[TagSummaryEntry]
