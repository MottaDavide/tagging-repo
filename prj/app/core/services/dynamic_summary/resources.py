"""Caricamento delle risorse per la summary dinamica.

Centralizza il bootstrap (risk models, hierarchy, system prompt) per
`orchestrators.dynamic_summary.run`, sullo stesso modello di
`core.services.tagging.resources.load_tagging_resources`.
"""

from core.models.registry.hierarchy import Hierarchy
from core.models.registry.hierarchy_data import build_hierarchy
from core.models.registry.risk_models import RiskModel
from core.resources.dynamic_summary_system import DYNAMIC_SUMMARY_SYSTEM
from core.services.registry.risk_models import load_risk_models_from_resources


def load_dynamic_summary_resources() -> tuple[list[RiskModel], Hierarchy, str]:
    """Carica risk models, hierarchy e il system prompt della summary dinamica.

    Singola fonte di verità per il bootstrap del front-door CLI (`run`).
    """
    risk_models = load_risk_models_from_resources()
    hierarchy = build_hierarchy()
    return risk_models, hierarchy, DYNAMIC_SUMMARY_SYSTEM
