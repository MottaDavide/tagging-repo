"""Struttura dati di un Risk Model (solo dato)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskModel:
    """Un singolo modello di rischio con il suo nome e i criteri di assegnazione."""

    name: str
    criteria: str
