"""Caricamento delle risorse condivise dalla pipeline di tagging."""

from core.models.registry.hierarchy import Hierarchy
from core.models.registry.hierarchy_data import build_hierarchy
from core.models.registry.risk_models import RiskModel
from core.services.registry.risk_models import load_risk_models_from_resources


def load_tagging_resources() -> tuple[list[RiskModel], Hierarchy]:
    """Carica RM e hierarchy. Singola fonte di verità per il bootstrap del tagger."""
    return load_risk_models_from_resources(), build_hierarchy()
