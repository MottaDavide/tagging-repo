import os
from pathlib import Path
from typing import Literal

Ambiente = Literal["prod", "non_prod"]


def resolve_ambiente() -> Ambiente:
    """Deduce l'ambiente di deploy da `ISP_AMBIENTE`: 'prod' oppure 'non_prod' (test/local/svil/assente)."""
    return "prod" if os.environ.get("ISP_AMBIENTE") == "prod" else "non_prod"


# Override la root del progetto via env var per portabilità (CI, deploy, altre macchine).
# Default: percorso assoluto dell'attuale checkout (core/config.py → core → app → prj → repo root).
_DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[3]
PROJECT_DIR = Path(os.environ.get("TAGGING_PROJECT_DIR", _DEFAULT_PROJECT_DIR))

RESOURCES_DIR = PROJECT_DIR / "prj" / "app" / "core" / "resources"
APP_CONFIG_DIR = Path(os.environ.get("APP_CONF_DIR", PROJECT_DIR / "prj" / "app" / "config"))

DATA_DIR = Path(os.environ.get("TAGGING_DATA_DIR", PROJECT_DIR / "data"))
ENV_FILE = PROJECT_DIR / ".env"

# Directory pipeline -------------------------------------------------------
# Nota: questo layout `data/` non usa lo stage descrizioni (img-table), quindi le dir
# "*-with-description" coincidono con le rispettive dir base (clean/annotated).
DOCUMENTS_DIR = DATA_DIR / "original-documents"
PARSED_DIR = DATA_DIR / "parsed-documents"
CLEAN_DIR = DATA_DIR / "clean-documents"
CLEAN_WITH_DESC_DIR = DATA_DIR / "clean-documents"
ANNOTATED_DIR = DATA_DIR / "annotated-documents"
ANNOTATED_WITH_DESC_DIR = DATA_DIR / "annotated-documents"
TAGGED_DIR = DATA_DIR / "tagged-documents"
SUMMARY_DIR = DATA_DIR / "dynamic-tag-summaries"

# Script one-shot build_dynamic_summary_inputs.py / run_dynamic_summaries.py: bag di tag
# costruiti dall'Excel statistiche DAIO, uno per "richiesta" di summary dinamica.
DYNAMIC_SUMMARY_STATS_XLSX = DATA_DIR / "statistiche_tagging_DAIO_per_sintesi_dinamica.xlsx"
DYNAMIC_SUMMARY_DIR = DATA_DIR / "dynamic-summaries"
DYNAMIC_SUMMARY_INPUT_DIR = DYNAMIC_SUMMARY_DIR / "input"
DYNAMIC_SUMMARY_OUTPUT_DIR = DYNAMIC_SUMMARY_DIR / "output"


# File dati ----------------------------------------------------------------
ENTI_ESTRATTI_JSON = DATA_DIR / "enti_estratti.json"
ENTI_FULL_NAME_JSON = DATA_DIR / "enti_full_name.json"
TAGS_JSON = DATA_DIR / "tags.json"

# Mapping per entity_extraction (legacy smartocr)
ENTI_CODE_NAME_JSON = DATA_DIR / "enti_code_name.json"
MAPPING_ENTI_FTZ_JSON = DATA_DIR / "mapping_enti_FTZ.json"

ODC_CREDITO_XLSX = DATA_DIR / "odc_credito.xlsx"
ODC_AML_XLSX = DATA_DIR / "odc_aml.xlsx"
ODC_DESCRIPTIONS_JSON = DATA_DIR / "odc_descriptions_optimized.json"
MO_DESCRIPTIONS_JSON = DATA_DIR / "mo_descriptions.json"

# Build di tags_credito.json a partire da Excel di validazione
TAGGING_CREDITO_XLSX = DATA_DIR / "Taggatura fonti Credito - update validazione.xlsx"
TAGS_CREDITO_JSON = DATA_DIR / "tags_credito.json"

# JSON per SOA
# Mapping schede di controllo `{chiave: {Risk Model, mo, odc}}` versionato nel repo.
SCHEDE_TAGGED_JSON = APP_CONFIG_DIR / "schede_tagged.json"
ENTI_JSON = APP_CONFIG_DIR / "enti.json"
