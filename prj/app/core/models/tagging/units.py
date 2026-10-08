from dataclasses import dataclass


@dataclass(frozen=True)
class Unit:
    """Unità candidata: sezione di testo o tabella, con pagina e heading di contesto.

    `entities` (solo tabelle) = enti-riga distinti (marker soa), in ordine di comparsa. Discrimina
    le tabelle "di risultati per ente" (audit-rilevanti) da quelle generiche e, a valle, alimenta il
    fan-out deterministico dell'ente sui candidati-tabella (un tag per ente-riga, senza LLM).
    `n_entities` è la cardinalità di `entities`, usata dal gate tabelle.
    """

    kind: str  # "section" | "table"
    text: str
    page: int | None
    heading: str
    table_id: str | None = None
    entities: tuple[str, ...] = ()

    @property
    def n_entities(self) -> int:
        return len(self.entities)
