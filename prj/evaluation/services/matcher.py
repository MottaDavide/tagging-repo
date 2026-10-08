"""Matching predizioni vs GT e aggregazione per Risk Model / totale.

Una predizione è un match per un tag GT se, tra i candidati con la stessa n-upla
`(RM, Ente, MO, OdC)` e almeno una pagina in comune, l'overlap testuale tra le
citazioni (`citation_overlap`) è ≥ soglia. Il matching è 1-a-1: tra le coppie
ammissibili si assegnano prima quelle con overlap più alto (greedy).
"""

from collections import defaultdict
from typing import Any

from evaluation.models.results import Candidate, Counts, DocResult, Metrics
from evaluation.services.dedup import dedup_candidates
from evaluation.services.similarity import citation_overlap

DEFAULT_THRESHOLD = 0.7


def in_rm_filter(tag: dict[str, Any], rm_filter: frozenset[str]) -> bool:
    return (tag.get("Risk Model") or "").strip() in rm_filter


def in_tipo_filter(tag: dict[str, Any], tipo_filter: frozenset[str]) -> bool:
    """Filtra per `Tipo Citazione`. Tag senza il campo passano sempre.

    Filtro vuoto → accetta tutto. Tag privi del campo (tipico per le PRED)
    sono inclusi: questo rende il filtro un no-op lato pred e produce una
    valutazione asimmetrica focalizzata sul sottoinsieme GT richiesto.
    """
    if not tipo_filter:
        return True
    tipo = tag.get("Tipo Citazione")
    if tipo is None:
        return True
    return tipo.strip().lower() in tipo_filter


def _candidates(
    tags: list[dict[str, Any]],
    rm_filter: frozenset[str],
    tipo_filter: frozenset[str],
    ignore_ente: bool,
) -> list[Candidate]:
    return [
        Candidate.from_tag(t, ignore_ente=ignore_ente)
        for t in tags
        if in_rm_filter(t, rm_filter) and in_tipo_filter(t, tipo_filter)
    ]


def match_overlap(
    gt: list[Candidate],
    pred: list[Candidate],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[tuple[int, int]]:
    """Greedy 1-a-1 sulle coppie ammissibili (n-upla uguale, pagine in comune,
    overlap ≥ soglia), assegnate in ordine di overlap decrescente.

    Ritorna le coppie `(gt_idx, pred_idx)` assegnate.
    """
    scored: list[tuple[float, int, int]] = []
    for gi, g in enumerate(gt):
        for pi, p in enumerate(pred):
            if g.tuple_key != p.tuple_key:
                continue
            if not (g.pages & p.pages):
                continue
            score = citation_overlap(g.citazione, p.citazione)
            if score >= threshold:
                scored.append((score, gi, pi))
    scored.sort(key=lambda s: s[0], reverse=True)

    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _, gi, pi in scored:
        if gi in matched_gt or pi in matched_pred:
            continue
        matched_gt.add(gi)
        matched_pred.add(pi)
        pairs.append((gi, pi))
    return pairs


def match_by_table_id(gt: list[Candidate], pred: list[Candidate]) -> list[tuple[int, int]]:
    """Match tabelle per identità: stessa n-upla `(RM, Ente, MO, OdC)` e stesso `table_id`.

    Non usa overlap testuale né pagine (l'id-tabella le implica). I candidati senza
    `table_id` non matchano. Greedy 1-a-1 (l'ordine è irrilevante: il match è esatto).
    """
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for gi, g in enumerate(gt):
        if gi in matched_gt or g.table_id is None:
            continue
        for pi, p in enumerate(pred):
            if pi in matched_pred or p.table_id is None:
                continue
            if g.tuple_key == p.tuple_key and g.table_id == p.table_id:
                matched_gt.add(gi)
                matched_pred.add(pi)
                pairs.append((gi, pi))
                break
    return pairs


def _outcome(
    gt: list[Candidate], pred: list[Candidate], pairs: list[tuple[int, int]]
) -> tuple[list[Candidate], list[Candidate], list[Candidate]]:
    """Da (candidati, coppie assegnate) ricava (tp, fp, fn)."""
    matched_gt = {gi for gi, _ in pairs}
    matched_pred = {pi for _, pi in pairs}
    tp = [gt[gi] for gi, _ in pairs]
    fn = [g for i, g in enumerate(gt) if i not in matched_gt]
    fp = [p for i, p in enumerate(pred) if i not in matched_pred]
    return tp, fp, fn


def evaluate_document(
    doc_name: str,
    gt_tags: list[dict[str, Any]],
    pred_tags: list[dict[str, Any]],
    rm_filter: frozenset[str],
    tipo_filter: frozenset[str] = frozenset(),
    ignore_ente: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
) -> DocResult:
    """Valuta un documento: gli span di testo per overlap testuale, le tabelle per id-tabella.

    GT e predizioni sono deduplicati per CONTENUTO in modo simmetrico prima del match: la GT e' un
    cartesiano appiattito con ~47% di righe a contenuto identico (vedi `dedup`), e col match 1-a-1
    queste falserebbero la recall; deduplicare anche le pred evita il gonfiaggio speculare dei FP.
    """
    gt = dedup_candidates(_candidates(gt_tags, rm_filter, tipo_filter, ignore_ente))
    pred = dedup_candidates(_candidates(pred_tags, rm_filter, tipo_filter, ignore_ente))

    gt_text = [c for c in gt if c.tipo != "table"]
    pred_text = [c for c in pred if c.tipo != "table"]
    gt_tab = [c for c in gt if c.tipo == "table"]
    pred_tab = [c for c in pred if c.tipo == "table"]

    tp_t, fp_t, fn_t = _outcome(gt_text, pred_text, match_overlap(gt_text, pred_text, threshold))
    tp_b, fp_b, fn_b = _outcome(gt_tab, pred_tab, match_by_table_id(gt_tab, pred_tab))
    return DocResult(doc=doc_name, gt=gt, pred=pred, tp=tp_t + tp_b, fp=fp_t + fp_b, fn=fn_t + fn_b)


def aggregate_per_rm(docs: list[DocResult]) -> dict[str, Counts]:
    per_rm: dict[str, Counts] = defaultdict(Counts)
    for r in docs:
        for c in r.tp:
            per_rm[c.rm].tp += 1
        for c in r.fp:
            per_rm[c.rm].fp += 1
        for c in r.fn:
            per_rm[c.rm].fn += 1
    return per_rm


def aggregate_total(docs: list[DocResult]) -> Counts:
    total = Counts()
    for r in docs:
        total.tp += len(r.tp)
        total.fp += len(r.fp)
        total.fn += len(r.fn)
    return total


def doc_rows(docs: list[DocResult]) -> list[tuple[DocResult, Metrics]]:
    """Documenti con le metriche già calcolate, ordinati per recall crescente.

    Fonte unica per l'ordinamento/formattazione condivisa da report testuale ed Excel.
    """
    pairs = [(d, Metrics.from_counts(d.counts)) for d in docs]
    return sorted(pairs, key=lambda pair: pair[1].recall)


def rm_rows(per_rm: dict[str, Counts], total: Counts) -> list[tuple[str, Metrics]]:
    """Righe `(label, metriche)` per Risk Model (ordine alfabetico) + riga finale 'TOTALE'."""
    rows = [(rm, Metrics.from_counts(per_rm[rm])) for rm in sorted(per_rm)]
    rows.append(("TOTALE", Metrics.from_counts(total)))
    return rows
