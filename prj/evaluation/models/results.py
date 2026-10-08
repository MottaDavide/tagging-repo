"""Dataclass condivisi dal flusso di valutazione (candidato di matching, conteggi, metriche)."""

import re
from dataclasses import dataclass, field
from typing import Any, Self

from core.services.registry.enti import ente_name_key
from evaluation.services.pages import pages_set

_RE_WS = re.compile(r"\s+")


def _norm_label(value: str | None) -> str:
    """Normalizza una label (RM/MO/OdC): collassa gli spazi multipli e rifila.

    La GT ha etichette con whitespace irregolare (es. ``'5073 -  Ruolo  e Processi...'`` con doppi
    spazi) mentre modello e gerarchia usano spazi singoli: senza normalizzare, l'uguaglianza esatta
    della n-upla fallirebbe su tag altrimenti identici.
    """
    return _RE_WS.sub(" ", (value or "")).strip()


@dataclass
class Candidate:
    """Tag (GT o PRED) ridotto ai campi rilevanti per il matching.

    `pages`/`citazione` alimentano il criterio di sovrapposizione (pagine in comune +
    overlap testuale); `tuple_key` è la n-upla su cui vale l'uguaglianza esatta.
    L'ente è canonicalizzato per NOME (`ente_name_key`): GT e predizione usano i nomi,
    non i codici. `tipo` (text/table/…) serve alla diagnostica per-tipo.
    """

    rm: str
    ente: str | None
    mo: str
    odc: str
    pages: frozenset[int]
    citazione: str
    tipo: str = ""
    table_id: str | None = None

    @classmethod
    def from_tag(cls, tag: dict[str, Any], ignore_ente: bool = False) -> Self:
        return cls(
            rm=_norm_label(tag.get("Risk Model")),
            ente=None if ignore_ente else ente_name_key(tag.get("Ente")),
            mo=_norm_label(tag.get("MO")),
            odc=_norm_label(tag.get("OdC")),
            pages=pages_set(tag.get("Pagina")),
            citazione=tag.get("Citazione") or "",
            tipo=(tag.get("Tipo Citazione") or "").strip().lower(),
            table_id=(tag.get("TableId") or None),
        )

    @property
    def tuple_key(self) -> tuple[str, str | None, str, str]:
        """N-upla (RM, Ente, MO, OdC) su cui vale l'uguaglianza esatta."""
        return (self.rm, self.ente, self.mo, self.odc)


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0


@dataclass
class Metrics:
    counts: Counts
    precision: float
    recall: float
    f1: float

    @classmethod
    def from_counts(cls, c: Counts) -> Self:
        p = c.tp / (c.tp + c.fp) if (c.tp + c.fp) > 0 else 0.0
        r = c.tp / (c.tp + c.fn) if (c.tp + c.fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return cls(counts=c, precision=p, recall=r, f1=f1)


@dataclass
class DocResult:
    """Esito della valutazione di un singolo documento."""

    doc: str
    gt: list[Candidate]
    pred: list[Candidate]
    tp: list[Candidate] = field(default_factory=list)
    fp: list[Candidate] = field(default_factory=list)
    fn: list[Candidate] = field(default_factory=list)

    @property
    def counts(self) -> Counts:
        return Counts(tp=len(self.tp), fp=len(self.fp), fn=len(self.fn))
