"""Entry-point `evaluate()`: carica GT + pred, valuta, stampa il report e salva l'Excel di sintesi."""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from core.config import ANNOTATED_WITH_DESC_DIR, DATA_DIR, TAGGED_DIR
from core.services.text.tables import enumerate_tables, resolve_table_id
from evaluation.models.results import Counts, DocResult
from evaluation.services.diagnostics import diagnostics_lines
from evaluation.services.matcher import (
    DEFAULT_THRESHOLD,
    aggregate_per_rm,
    aggregate_total,
    doc_rows,
    evaluate_document,
    rm_rows,
)
from evaluation.services.report import write_summary

logger = logging.getLogger(__name__)

RM_FILTER: frozenset[str] = frozenset({"Credito", "AML"})
TIPO_VALUES: frozenset[str] = frozenset({"text", "table", "image"})
DEFAULT_OUTPUT: Path = DATA_DIR / "metriche_tagging.xlsx"
DEFAULT_DOCS_DIR: Path = ANNOTATED_WITH_DESC_DIR
# Riferimento di default: GT deduplicata per contenuto (vedi scripts/build_gt_dedup.py).
DEFAULT_GT: Path = DATA_DIR / "gt_dedup.json"
_RE_TABLE_MARKUP = re.compile(r"<t[rdh]", re.IGNORECASE)

_LINE_WIDTH = 92
_RM_COL = 32
_DOC_COL = 43


def _per_doc_table_lines(docs: list[DocResult]) -> list[str]:
    sep = "-" * _LINE_WIDTH
    out = [
        f"\n{'DOCUMENTO':<{_DOC_COL}} {'GT':>4} {'PRED':>5} {'TP':>4} {'FP':>4} {'FN':>4}  {'REC':>6}  {'PREC':>6}",
        sep,
    ]
    for d, m in doc_rows(docs):
        out.append(
            f"{d.doc[: _DOC_COL - 1]:<{_DOC_COL}} {len(d.gt):>4} {len(d.pred):>5} "
            f"{m.counts.tp:>4} {m.counts.fp:>4} {m.counts.fn:>4}  "
            f"{m.recall:>6.1%}  {m.precision:>6.1%}"
        )
    return out


def _per_rm_table_lines(per_rm: dict[str, Counts], total: Counts) -> list[str]:
    line = "=" * _LINE_WIDTH
    sep = "-" * _LINE_WIDTH
    out = [
        f"\n{line}\n  PER RISK MODEL\n{line}",
        f"{'Risk Model':<{_RM_COL}} {'TP':>5} {'FP':>5} {'FN':>5}  {'Prec':>7}  {'Rec':>7}  {'F1':>7}",
        sep,
    ]
    rows = rm_rows(per_rm, total)
    for i, (label, m) in enumerate(rows):
        if i == len(rows) - 1:
            out.append(sep)
        out.append(
            f"{label:<{_RM_COL}} {m.counts.tp:>5} {m.counts.fp:>5} {m.counts.fn:>5}  "
            f"{m.precision:>7.1%}  {m.recall:>7.1%}  {m.f1:>7.1%}"
        )
    return out


def print_report(
    docs: list[DocResult],
    per_rm: dict[str, Counts],
    total: Counts,
    rm_filter: frozenset[str],
    tipo_filter: frozenset[str] = frozenset(),
    ignore_ente: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
) -> None:
    line = "=" * _LINE_WIDTH
    tuple_label = "(RM, MO, OdC)" if ignore_ente else "(RM, Ente, MO, OdC)"
    tipo_label = ", ".join(sorted(tipo_filter)) if tipo_filter else "tutti"
    out: list[str] = [
        f"\n{line}",
        f"  EVALUATION tag_rm — {len(docs)} documenti",
        f"  Filtro RM: {', '.join(sorted(rm_filter))}",
        f"  Filtro Tipo Citazione: {tipo_label}",
        f"  Matching: n-upla {tuple_label} esatta  ·  pagine sovrapposte  ·  overlap citazione ≥ {threshold:.0%}",
        line,
    ]
    out.extend(_per_doc_table_lines(docs))
    out.extend(_per_rm_table_lines(per_rm, total))
    out.append("")
    logger.info("\n".join(out))


def _build_gt_by_name(gt_data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Costruisce `stem → tags` dalla GT, warning se più entry hanno lo stesso stem."""
    gt_by_name: dict[str, list[dict[str, Any]]] = {}
    for d in gt_data:
        key = Path(d["filename"]).stem
        if key in gt_by_name:
            logger.warning("GT duplicato: '%s' — sovrascrittura con seconda entry", key)
        gt_by_name[key] = d["tags"]
    return gt_by_name


def _enrich_pred_table_ids(tags: list[dict[str, Any]], docs_dir: Path, doc_name: str) -> None:
    """Marca come tabella i pred con citazione HTML e ne risolve il `TableId` dal documento.

    Necessario per gli output legacy privi di `Tipo Citazione`/`TableId`: le citazioni-tabella
    (righe HTML copiate) vengono ricondotte all'id-tabella così da poter matchare la GT. I pred
    che hanno già un `TableId` non vengono toccati (output del nuovo algoritmo).
    """
    to_resolve = [t for t in tags if not t.get("TableId") and _RE_TABLE_MARKUP.search(t.get("Citazione") or "")]
    if not to_resolve:
        return
    md = docs_dir / f"{doc_name}.md"
    tables = enumerate_tables(md.read_text(encoding="utf-8")) if md.exists() else []
    for tag in to_resolve:
        tag["Tipo Citazione"] = "table"
        tag["TableId"] = resolve_table_id(tag.get("Citazione") or "", tables)


def evaluate(
    tagged_dir: Path = TAGGED_DIR,
    gt_file: Path = DEFAULT_GT,
    rm_filter: frozenset[str] = RM_FILTER,
    tipo_filter: frozenset[str] = frozenset(),
    ignore_ente: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    output: Path = DEFAULT_OUTPUT,
    docs_dir: Path = DEFAULT_DOCS_DIR,
) -> None:
    """Carica GT + pred, valuta i documenti taggati, stampa il report e salva l'Excel di sintesi."""
    gt_data = json.loads(gt_file.read_text(encoding="utf-8"))
    gt_by_name = _build_gt_by_name(gt_data)

    pred_by_name: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(tagged_dir.glob("*.json")):
        pred_doc = json.loads(path.read_text(encoding="utf-8"))
        doc_name = path.stem
        if doc_name not in gt_by_name:
            logger.warning("File taggato '%s' non presente in GT — escluso dal calcolo", doc_name)
            continue
        tags = pred_doc.get("tags", [])
        _enrich_pred_table_ids(tags, docs_dir, doc_name)
        pred_by_name[doc_name] = tags

    if not pred_by_name:
        logger.error("Nessun file taggato trovato in %s", tagged_dir)
        sys.exit(1)

    for doc_name in sorted(gt_by_name.keys() - pred_by_name.keys()):
        logger.warning("Nessun file taggato per '%s' — escluso dal calcolo", doc_name)

    docs: list[DocResult] = [
        evaluate_document(
            doc_name,
            gt_by_name[doc_name],
            pred_tags,
            rm_filter,
            tipo_filter=tipo_filter,
            ignore_ente=ignore_ente,
            threshold=threshold,
        )
        for doc_name, pred_tags in sorted(pred_by_name.items())
    ]

    per_rm = aggregate_per_rm(docs)
    total = aggregate_total(docs)
    print_report(docs, per_rm, total, rm_filter, tipo_filter=tipo_filter, ignore_ente=ignore_ente, threshold=threshold)
    logger.info("\n".join(diagnostics_lines(docs, threshold, ignore_ente=ignore_ente)))
    write_summary(
        docs,
        per_rm,
        total,
        rm_filter=rm_filter,
        tipo_filter=tipo_filter,
        ignore_ente=ignore_ente,
        threshold=threshold,
        output=output,
    )
