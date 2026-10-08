from dataclasses import dataclass

from core.models.tagging.types import Confidence, TipoCitazione


@dataclass
class BranoCandidate:
    """Rappresentazione interna di un brano durante il processing del tagger."""

    risk_model: str
    ente: str | None
    brano: str
    pagina: str
    rationale: str
    rm_confidence: Confidence | None = None
    mo: str | None = None
    mo_confidence: Confidence | None = None
    odc: str | None = None
    odc_confidence: Confidence | None = None
    tipo_citazione: TipoCitazione = "text"
    table_id: str | None = None
    table_entities: tuple[str, ...] = ()


@dataclass
class EnteAppearance:
    """Metadata strutturali di un ente nel documento (Strato 1 — deterministico).

    Tutti i campi sono derivati dai marker `ENTE[…]` e dalla struttura di
    pagine/heading del documento, senza coinvolgere il modello LLM. Servono a
    fornire allo Stage 1 una vista globale dell'ente, utile a scegliere il
    soggetto contestuale del brano anche quando non è annotato sulla pagina della
    citazione.
    """

    canonical: str
    pages: list[int]
    n_mentions: int
    first_page: int
    in_cover: bool
    h1_headings: list[str]
    h2_headings: list[str]
