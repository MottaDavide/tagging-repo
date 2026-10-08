"""Modelli per la summary dinamica: analisi espositiva su estratti passati dall'utente.

Document-agnostica: aggrega tag arbitrari per quadrupla `(RM, MO, OdC, Ente)` e ne
produce un'analisi.

Famiglie: `TagExtract` (estratto, aggregazione + JSON), `GroupedTag` (aggregazione, no LLM),
`TemaEstratti`/`DynamicTagSummary` (output LLM), `DynamicSummaryEntry`/`DynamicSummaries` (JSON).
"""

from dataclasses import dataclass, field

from core.models.strict import StrictModel


class TagExtract(StrictModel):
    """Un estratto associato a un tag: provenienza (opzionale) + pagina + citazione."""

    documento: str | None
    pagina: str
    citazione: str


@dataclass
class GroupedTag:
    """Gruppo di tag con la stessa quadrupla `(RM, MO, OdC, Ente)` + i suoi estratti."""

    risk_model: str
    mo: str
    odc: str
    ente: str | None
    estratti: list[TagExtract] = field(default_factory=list)


class TemaEstratti(StrictModel):
    """Un tema/aspetto che ricorre negli estratti del gruppo."""

    riferimento: str
    descrizione: str


class DynamicTagSummary(StrictModel):
    """Analisi espositiva (template fisso) degli estratti di un gruppo `(RM, MO, OdC, Ente)`.

    Taglio descrittivo/espositivo: niente giudizi di rischio o valutazioni, solo
    ciò che gli estratti riportano in relazione alla quadrupla in esame.
    """

    titolo: str
    sintesi: str
    temi: list[TemaEstratti]
    quadro_complessivo: str


class DynamicSummaryEntry(StrictModel):
    """Un gruppo (quadrupla) + i suoi estratti + l'analisi espositiva generata."""

    risk_model: str
    mo: str
    odc: str
    ente: str | None
    n_estratti: int
    estratti: list[TagExtract]
    analisi: DynamicTagSummary

    @property
    def documenti(self) -> list[str]:
        """Documenti distinti di provenienza degli estratti, in ordine di apparizione."""
        seen: set[str] = set()
        out: list[str] = []
        for e in self.estratti:
            if e.documento and e.documento not in seen:
                seen.add(e.documento)
                out.append(e.documento)
        return out


class DynamicSummaries(StrictModel):
    """Output completo di una run di summary dinamica (un bag di tag in input)."""

    n_gruppi: int
    n_tag_input: int
    entries: list[DynamicSummaryEntry]
