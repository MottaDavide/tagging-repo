"""Tipi condivisi dei tag (confidence, tipo citazione, chiave identità)."""

from dataclasses import dataclass
from typing import Literal

type Confidence = Literal["high", "medium", "low"]
type TipoCitazione = Literal["text", "table", "image"]


@dataclass(frozen=True)
class TagKey:
    """Chiave identità di un tag `(Risk Model, MO, OdC, Ente)`, per dedup/lookup nei raggruppamenti."""

    risk_model: str
    mo: str
    odc: str
    ente: str | None
