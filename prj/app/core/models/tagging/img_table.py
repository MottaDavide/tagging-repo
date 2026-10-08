"""Modelli Pydantic per descrizione LLM di figure e tabelle (per pagina)."""

from pydantic import Field

from core.models.strict import StrictModel


class FigureDescription(StrictModel):
    figure_index_on_page: int = Field(
        description="Indice 1-based della figura nella pagina (deve combaciare con figure_index_on_page in input)."
    )
    description: str = Field(description="Descrizione della figura (≤200 parole, vedi regole nel system prompt).")
    remove_as_layout: bool = Field(description="True solo per figure di puro layout (logo, header, footer ricorrente).")
    contains_chart: bool = Field(description="True se la figura contiene una qualunque visualizzazione dati.")
    chart_type: str | None = Field(description="Tipo di chart (bar_chart, line_chart, ...) o null se non applicabile.")
    reason: str = Field(description="Motivazione breve della classificazione remove_as_layout.")


class TableDescription(StrictModel):
    table_index_on_page: int = Field(description="Indice 1-based della tabella nella pagina.")
    description: str = Field(
        description="Descrizione della tabella, preferibilmente in formato entity-keyed quando applicabile (≤200 parole)."
    )
    contains_chart: bool = Field(description="True se la tabella include una visualizzazione (es. KPI dashboard).")
    chart_type: str | None = Field(description="Tipo di chart (table_kpi, table_breakdown, ...) o null.")


class PageDescriptions(StrictModel):
    """Output strutturato di una chiamata LLM per una singola pagina."""

    figures: list[FigureDescription] = Field(default_factory=list)
    tables: list[TableDescription] = Field(default_factory=list)
