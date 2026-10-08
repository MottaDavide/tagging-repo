"""Caricamento dei criteri Risk Model dalla risorsa Python `rm_criteria.py` + canonicalizzazione nome RM."""

import re

from core.models.registry.risk_models import RiskModel
from core.resources.rm_criteria import RM_CRITERIA

_RM_SECTION_RE = re.compile(
    r"^##\s+(?P<name>.+?)\n(?P<criteria>[\s\S]*?)(?=^---$|\Z)",
    re.MULTILINE,
)


def load_risk_models_from_resources() -> list[RiskModel]:
    """Carica i risk model dalla risorsa embedded `RM_CRITERIA`."""
    models = []
    for match in _RM_SECTION_RE.finditer(RM_CRITERIA):
        name = match.group("name").strip()
        criteria = match.group("criteria").strip()
        if name and criteria:
            models.append(RiskModel(name=name, criteria=criteria))
    if not models:
        raise ValueError("Nessun risk model trovato in RM_CRITERIA.")
    return models


# Canonicalizzazione del nome RM emesso dall'LLM ---------------------------

_RM_ALIASES: dict[str, str] = {
    "anti financial crime": "AML",
    "aml": "AML",
    "credito": "Credito",
}


def canonicalize_rm(raw: str) -> str:
    """Mappa varianti comuni del nome RM al canonico.

    Esempi:
      "AML" -> "AML"
      "aml" -> "AML"
      "Anti Financial Crime" -> "AML"
      "credito" -> "Credito"
      "X sconosciuto" -> "X sconosciuto"  (passthrough invariato)
    """
    return _RM_ALIASES.get(raw.strip().lower(), raw.strip())
