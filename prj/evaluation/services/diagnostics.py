"""Decomposizione diagnostica delle cause di FN (recall) e FP (precision).

Trasversale al matching 1-a-1: serve a capire DOVE si perde recall/precision.

- Recall (span di testo GT): per ogni span si individua la PRIMA divergenza lungo la
  catena pagina → RM → confine dello span → Ente → MO → OdC. Le categorie sono mutuamente
  esclusive (una per span), quindi sommano al totale degli span di testo GT.
- Precision (predizioni non matchate): distingue la sovra-generazione (predizione su una
  zona pagina+RM priva di GT) dal disaccordo su una zona con GT.
"""

from collections import Counter

from evaluation.models.results import Candidate, DocResult
from evaluation.services.matcher import DEFAULT_THRESHOLD
from evaluation.services.similarity import citation_overlap

# Etichette ordinate per la stampa (chiave → descrizione leggibile).
RECALL_LABELS: dict[str, str] = {
    "1_no_pred_in_pagina": "nessuna predizione sulla pagina",
    "2_rm_diverso": "predizione in pagina ma RM diverso",
    "3_confine_span": "stesso RM+pagina, span non sovrapposto",
    "4_ente_errato": "span trovato, Ente errato",
    "5_mo_errato": "Ente ok, MO errato",
    "6_odc_errato": "MO ok, OdC errato",
    "7_match_completo": "match completo",
}
PRECISION_LABELS: dict[str, str] = {
    "A_zona_senza_gt": "zona (pagina+RM) senza alcun GT → sovra-generazione",
    "B_zona_con_gt_no_match": "zona con GT ma nessun match completo",
    "C_pred_tabella": "predizione-tabella non matchata",
}


def _is_text(c: Candidate) -> bool:
    return c.tipo != "table"


def _recall_cause(g: Candidate, pred: list[Candidate], threshold: float, *, ignore_ente: bool) -> str:
    same_page = [p for p in pred if g.pages & p.pages]
    if not same_page:
        return "1_no_pred_in_pagina"
    if not any(p.rm == g.rm for p in same_page):
        return "2_rm_diverso"
    in_zone = [p for p in pred if _is_text(p) and p.rm == g.rm and (g.pages & p.pages)]
    scored = [(citation_overlap(g.citazione, p.citazione), p) for p in in_zone]
    over = [(s, p) for s, p in scored if s >= threshold]
    if not over:
        return "3_confine_span"
    best = max(over, key=lambda sp: sp[0])[1]
    if not ignore_ente and best.ente != g.ente:
        return "4_ente_errato"
    if best.mo != g.mo:
        return "5_mo_errato"
    if best.odc != g.odc:
        return "6_odc_errato"
    return "7_match_completo"


def recall_causes(
    docs: list[DocResult],
    threshold: float = DEFAULT_THRESHOLD,
    *,
    ignore_ente: bool = False,
) -> Counter[str]:
    """Conta, sugli span di testo GT, la prima divergenza lungo la catena di match."""
    causes: Counter[str] = Counter()
    for d in docs:
        for g in d.gt:
            if not _is_text(g):
                continue
            causes[_recall_cause(g, d.pred, threshold, ignore_ente=ignore_ente)] += 1
    return causes


def precision_causes(docs: list[DocResult]) -> Counter[str]:
    """Classifica le predizioni non matchate (FP) per origine dell'errore di precision."""
    causes: Counter[str] = Counter()
    for d in docs:
        for p in d.fp:
            if not _is_text(p):
                causes["C_pred_tabella"] += 1
            elif any(g.rm == p.rm and (g.pages & p.pages) for g in d.gt):
                causes["B_zona_con_gt_no_match"] += 1
            else:
                causes["A_zona_senza_gt"] += 1
    return causes


def _cause_lines(title: str, causes: Counter[str], labels: dict[str, str]) -> list[str]:
    total = sum(causes.values())
    out = [title]
    if total == 0:
        return [*out, "  (nessun caso)"]
    for key, desc in labels.items():
        n = causes.get(key, 0)
        out.append(f"  {desc:<44} {n:>5}  ({n / total:>5.1%})")
    out.append(f"  {'TOTALE':<44} {total:>5}")
    return out


def diagnostics_lines(
    docs: list[DocResult],
    threshold: float = DEFAULT_THRESHOLD,
    *,
    ignore_ente: bool = False,
) -> list[str]:
    """Righe di report per la decomposizione delle cause di recall e precision."""
    return [
        *_cause_lines(
            "\nCAUSE FN — recall span di testo (prima divergenza)",
            recall_causes(docs, threshold, ignore_ente=ignore_ente),
            RECALL_LABELS,
        ),
        *_cause_lines(
            "\nCAUSE FP — precision (predizioni non matchate)",
            precision_causes(docs),
            PRECISION_LABELS,
        ),
    ]
