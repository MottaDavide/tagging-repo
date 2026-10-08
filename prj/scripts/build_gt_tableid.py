"""Assegna l'id-tabella alle citazioni-tabella della GT → produce `gt_tableid.json`.

Le citazioni-tabella della GT sono riferimenti posizionali ("Tabella pag.N"), non
confrontabili per overlap testuale. Questo script le riconduce a un id-tabella stabile
(`core.services.text.tables.enumerate_tables`) e scrive una copia della GT con il campo
`TableId` aggiunto ai soli tag-tabella; i tag di testo restano invariati.

Disambiguazione su pagine con più tabelle: si sceglie la PRIMA tabella della pagina (la
principale; le successive sono tipicamente esiti sintetici / definizioni / focus). Tutte
le scelte sono elencate in un foglio di revisione CSV per la verifica umana.
"""

import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import click

from core.config import ANNOTATED_WITH_DESC_DIR, DATA_DIR
from core.services.text.tables import Table, enumerate_tables
from core.utils.logging import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_GT = DATA_DIR / "gt.json"
DEFAULT_OUT = DATA_DIR / "gt_tableid.json"
DEFAULT_REVIEW = DATA_DIR / "gt_tableid_review.csv"


def _pages(pagina: Any) -> list[int]:
    return sorted({int(n) for n in re.findall(r"\d+", str(pagina or ""))})


def _tables_by_page(tables: list[Table]) -> dict[int | None, list[Table]]:
    by_page: dict[int | None, list[Table]] = defaultdict(list)
    for t in tables:
        by_page[t.page].append(t)
    return by_page


def choose_table_id(pages: list[int], by_page: dict[int | None, list[Table]]) -> tuple[str | None, str]:
    """Ritorna (id-tabella, stato). Su pagina multi-tabella sceglie la prima (principale)."""
    for pg in pages:
        candidates = by_page.get(pg, [])
        if not candidates:
            continue
        status = "mono" if len(candidates) == 1 else "first_of_multi"
        return candidates[0].id, status
    return None, "no_table"


def _load_docs(docs_dir: Path) -> dict[str, list[Table]]:
    docs: dict[str, list[Table]] = {}
    for md in docs_dir.glob("*.md"):
        docs[md.stem] = enumerate_tables(md.read_text(encoding="utf-8"))
    return docs


def _is_table_tag(tag: dict[str, Any]) -> bool:
    return (tag.get("Tipo Citazione") or "").strip().lower() == "table"


def build(gt_file: Path, docs_dir: Path, out_file: Path, review_file: Path) -> None:
    gt_data: list[dict[str, Any]] = json.loads(gt_file.read_text(encoding="utf-8"))
    docs = _load_docs(docs_dir)

    stats: dict[str, int] = defaultdict(int)
    # cella (doc, pagina) → info per il foglio di revisione (solo pagine multi-tabella)
    cells: dict[tuple[str, int], dict[str, Any]] = {}

    for doc in gt_data:
        stem = Path(doc["filename"]).stem
        by_page = _tables_by_page(docs.get(stem, []))
        for tag in doc["tags"]:
            if not _is_table_tag(tag):
                continue
            pages = _pages(tag.get("Pagina"))
            table_id, status = choose_table_id(pages, by_page)
            tag["TableId"] = table_id
            stats[status] += 1
            if status != "first_of_multi":
                continue
            page = next(p for p in pages if by_page.get(p))
            cell = cells.setdefault(
                (stem, page),
                {"id": table_id, "candidates": by_page[page], "odc": set()},
            )
            cell["odc"].add(tag.get("OdC", ""))

    out_file.write_text(json.dumps(gt_data, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_review(review_file, cells)

    logger.info("gt_tableid: tag-tabella per stato = %s", dict(stats))
    logger.info("Celle multi-tabella da verificare: %d", len(cells))
    logger.info("Scritti: %s  e  %s", out_file, review_file)


def _write_review(review_file: Path, cells: dict[tuple[str, int], dict[str, Any]]) -> None:
    review_file.parent.mkdir(parents=True, exist_ok=True)
    with review_file.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["documento", "pagina", "OdC", "id_scelto", "candidati"])
        writer.writeheader()
        for (stem, page), info in sorted(cells.items()):
            candidati = " ;; ".join(f"{c.id}: {c.text[:70]}" for c in info["candidates"])
            writer.writerow(
                {
                    "documento": stem,
                    "pagina": str(page),
                    "OdC": " | ".join(sorted(info["odc"])),
                    "id_scelto": info["id"] or "",
                    "candidati": candidati,
                }
            )


@click.command(help="Assegna l'id-tabella alle citazioni-tabella della GT (produce gt_tableid.json).")
@click.option("--gt", "gt_file", type=click.Path(path_type=Path, dir_okay=False), default=DEFAULT_GT, show_default=True)
@click.option(
    "--docs-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=ANNOTATED_WITH_DESC_DIR,
    show_default=True,
)
@click.option(
    "--out", "out_file", type=click.Path(path_type=Path, dir_okay=False), default=DEFAULT_OUT, show_default=True
)
@click.option(
    "--review",
    "review_file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_REVIEW,
    show_default=True,
)
def main(gt_file: Path, docs_dir: Path, out_file: Path, review_file: Path) -> None:
    setup_logging("build_gt_tableid")
    build(gt_file, docs_dir, out_file, review_file)


if __name__ == "__main__":
    main()
