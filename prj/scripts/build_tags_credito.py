"""Costruisce `data/tags_credito.json` dall'Excel di validazione.

Replica la struttura di `data/tags.json` (lista di documenti con `filename` e
`tags`). Filtra i soli tag Credito con flag di validazione `Y` (colonna 13) e
canonicalizza il campo Ente tramite `core.services.registry.enti.canonical_ente_key`.

Script one-shot (non parte della pipeline runtime): si appoggia ai moduli
condivisi di `core` (config, registry, logging) ma contiene qui la propria logica.
"""

import json
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import click
import openpyxl
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.config import TAGGING_CREDITO_XLSX, TAGS_CREDITO_JSON
from core.services.registry.enti import canonical_ente_key
from core.utils.logging import setup_logging

logger = logging.getLogger(__name__)

_CONFIG = get_obj_from_config_path("tagging.yaml")["tools"]["build_tags"]

SHEET: str = _CONFIG["sheet_name"]
COLS: dict[str, int] = _CONFIG["cols"]
_MIN_ROW: int = _CONFIG["min_row"]
_FILENAME_COL: int = _CONFIG["filename_col"]
_VALIDATION_COL: int = _CONFIG["validation_col"]
_VALIDATION_VALUE: str = _CONFIG["validation_value"]


def _format_pagina(p: object) -> str:
    if p is None:
        return ""
    if isinstance(p, float):
        # Excel converte "2,3" → 2.3: preserva la forma testuale senza zeri inutili.
        if p.is_integer():
            return str(int(p))
        return f"{p:g}"
    return str(p).strip()


def _clean(s: object) -> str | None:
    if s is None:
        return None
    s = str(s).strip()
    return s or None


def build(xlsx: Path = TAGGING_CREDITO_XLSX, out: Path = TAGS_CREDITO_JSON) -> None:
    """Esegue il build leggendo l'Excel e scrivendo `tags_credito.json`."""
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb[SHEET]

    by_doc: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    unmapped_enti: dict[str, int] = {}

    for row in ws.iter_rows(min_row=_MIN_ROW, values_only=True):
        if row[0] is None:
            continue
        rm = _clean(row[COLS["Risk Model"]])
        if not rm or rm.upper() != "CREDITO":
            continue

        if row[_VALIDATION_COL] != _VALIDATION_VALUE:
            continue

        filename = _clean(row[_FILENAME_COL])
        if not filename:
            continue

        ente_raw = _clean(row[COLS["Ente"]])
        ente_canon = canonical_ente_key(ente_raw) if ente_raw else None
        if ente_raw and ente_canon is None:
            unmapped_enti[ente_raw] = unmapped_enti.get(ente_raw, 0) + 1
            # Fallback: rimuove eventuale codice numerico iniziale.
            ente_canon = re.sub(r"^[A-Z0-9]{5,9}\s*-\s*", "", ente_raw).strip() or ente_raw

        tag = {
            "Pagina": _format_pagina(row[COLS["Pagina"]]),
            "Risk Model": "Credito",
            "OdC": _clean(row[COLS["OdC"]]) or "",
            "MO": _clean(row[COLS["MO"]]) or "",
            "Ente": ente_canon or "",
            "Periodo": _clean(row[COLS["Periodo"]]) or "",
            "Citazione": _clean(row[COLS["Estratto"]]) or "",
        }
        by_doc.setdefault(filename, []).append(tag)

    output = [{"filename": fn, "tags": tags} for fn, tags in by_doc.items()]
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    total_tags = sum(len(d["tags"]) for d in output)
    logger.info("Salvati %d documenti / %d tag in %s", len(output), total_tags, out)

    if unmapped_enti:
        logger.warning(
            "Enti non canonicalizzabili (fallback applicato): %d valori distinti",
            len(unmapped_enti),
        )
        for ente, n in sorted(unmapped_enti.items(), key=lambda x: -x[1])[:20]:
            logger.warning("  %r (%d occorrenze)", ente, n)


# CLI ---------------------------------------------------------------------


@click.command(help="Costruisce tags_credito.json dall'Excel di validazione.")
@click.option(
    "--xlsx", type=click.Path(path_type=Path, dir_okay=False), default=TAGGING_CREDITO_XLSX, show_default=True
)
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=TAGS_CREDITO_JSON, show_default=True)
def main(xlsx: Path, out: Path) -> None:
    setup_logging(__name__)
    build(xlsx=xlsx, out=out)


if __name__ == "__main__":
    main()
