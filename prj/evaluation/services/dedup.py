"""Deduplica i tag a CONTENUTO identico (stessa n-upla + tipo + id-tabella + pagine + citazione).

La ground truth e' un prodotto cartesiano appiattito `(estratto x OdC x Ente)`: il fan-out
span->multi-ente / span->multi-OdC e' LEGITTIMO (tuple distinte, da preservare), ma lo stesso testo
fisico compare sotto piu' record-estratto rifanoutati in modo identico -> ~47% di righe a contenuto
identico che differiscono solo per ID tecnici. Con matching 1-a-1 queste righe gonfiano il
denominatore e abbattono artificialmente la recall.

La dedup collassa SOLO i contenuti identici: due tag con ente diverso, OdC diverso o citazione
diversa hanno chiavi diverse e restano distinti. Va applicata in modo SIMMETRICO a GT e predizioni,
cosi' un finding vale 1 su entrambi i lati (ne' recall ne' precision vengono falsate).
"""

from typing import Any

from evaluation.models.results import Candidate

# Chiave di contenuto: n-upla di match + tipo/id-tabella + pagine esatte + citazione esatta.
_Key = tuple[str, str | None, str, str, str, str | None, frozenset[int], str]


def candidate_key(c: Candidate) -> _Key:
    """Chiave di contenuto di un candidato (identica ⇒ stesso tag, a meno di ID tecnici)."""
    return (c.rm, c.ente, c.mo, c.odc, c.tipo, c.table_id, c.pages, c.citazione.strip())


def dedup_candidates(cands: list[Candidate]) -> list[Candidate]:
    """Rimuove i candidati a contenuto identico mantenendo la prima occorrenza (ordine preservato)."""
    seen: set[_Key] = set()
    out: list[Candidate] = []
    for c in cands:
        key = candidate_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def dedup_raw_tags(tags: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Deduplica una lista di tag grezzi (dict) per contenuto. Ritorna `(tag_unici, n_rimossi)`.

    La chiave e' calcolata via `Candidate.from_tag` per usare la stessa normalizzazione della
    valutazione (ente per nome, pagine come set, tipo lowercase).
    """
    seen: set[_Key] = set()
    out: list[dict[str, Any]] = []
    for tag in tags:
        key = candidate_key(Candidate.from_tag(tag))
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out, len(tags) - len(out)
