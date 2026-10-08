"""Stage 1: parsing PDF → markdown via Azure Document Intelligence.

Espone i building block (`init_worker`, `process_file`) usabili da:
  - lo script `prj/scripts/pipeline.py` per l'orchestratore batch
  - future API che processano un singolo PDF
"""

import logging
import time
from pathlib import Path

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from genfactory.layer.dtypes.document_analysis import DocumentIntelligencePayload

from core.config import ENV_FILE
from core.services.llm_client import Layer, init_genfactory

logger = logging.getLogger(__name__)

_CONFIG = get_obj_from_config_path("tagging.yaml")["parse"]

NUM_WORKERS: int = _CONFIG["num_workers"]
USE_CASE_ID: str = get_obj_from_config_path("llm.yaml")["calls"]["parse"]["use_case_id"]
PROCESSOR: str = _CONFIG["processor"]
SUPPORTED_EXTENSIONS = {".pdf"}


def init_genfactory_for_parsing() -> Layer:
    """Inizializza il `Layer` nel processo worker (chiamato una volta)."""
    _layer = init_genfactory(env_file=str(ENV_FILE), use_case_id=USE_CASE_ID)
    logger.info("Layer inizializzato con token fresco.")
    return _layer


def process_file(
    args: tuple[Path, Path], layer: Layer | None = None, *, raise_on_error: bool = False, run_id: str | None = None
) -> tuple[str, bool, float]:
    """Parsea un singolo PDF. Ritorna (nome_file, ok, durata_secondi)."""
    file_path, output_dir = args
    file_name = file_path.name
    output_path = output_dir / (file_path.stem + ".md")
    t_start = time.time()

    if output_path.exists():
        logger.info("[run_id=%s][%s] già processato, saltato.", run_id, file_name)
        return file_name, True, 0.0

    try:
        content = file_path.read_bytes()
        assert layer is not None, "Worker non inizializzato: _init_worker non è stato chiamato"
        result = layer.analyze_document(
            document=content,
            payload=DocumentIntelligencePayload(
                processor=PROCESSOR,
                output_content_format="markdown",
            ),
            mode="async",
            filename=file_name,
        )
        markdown_content = result.content or ""
        if not markdown_content.strip():
            logger.warning("[run_id=%s][%s] contenuto markdown vuoto, saltato.", run_id, file_name)
            return file_name, False, time.time() - t_start
        output_path.write_text(markdown_content, encoding="utf-8")
    except Exception:
        elapsed = time.time() - t_start
        logger.exception("[run_id=%s][%s] errore (%.1fs)", run_id, file_name, elapsed)
        if raise_on_error:
            raise
        return file_name, False, elapsed
    else:
        elapsed = time.time() - t_start
        logger.info("[run_id=%s][%s] salvato in %s (%.1fs)", run_id, file_name, output_path.name, elapsed)
        return file_name, True, elapsed
