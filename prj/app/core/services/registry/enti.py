"""Canonicalizzazione delle stringhe ente verso l'enum `Enti`.

I valori dell'enum hanno formato ``"CODICE - NOME"`` (es. ``"0141020 - CONTROLLI BDT"``).

La canonicalizzazione è code-first: il match avviene sul codice iniziale della stringa
(soa-detection restituisce sempre codici, es. ``"0141020 - EM 01-41020 CONTROLLI BDT"``).
"""

import re

from core.models.registry.enti import Enti

ENTI_VALUES: frozenset[str] = frozenset(e.value for e in Enti)

_RE_CODE = re.compile(r"^([A-Za-z0-9]{5,9})\s*-\s*")


def _split_code_label(value: str) -> tuple[str | None, str]:
    """Da un valore enum ``"CODICE - NOME"`` ritorna ``(codice, nome)``."""
    m = _RE_CODE.match(value)
    if m:
        return m.group(1), value[m.end() :]
    return None, value


# Indice codice → valore canonico, costruito una sola volta dall'enum.
_CODE_TO_ENTE: dict[str, str] = {}
for _e in Enti:
    _code, _ = _split_code_label(_e.value)
    if _code:
        _CODE_TO_ENTE[_code.upper()] = _e.value


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _extract_code(s: str) -> str | None:
    """Estrae il codice iniziale da una stringa grezza, o None."""
    m = _RE_CODE.match(s.strip())
    return m.group(1) if m else None


def entity_label(value: str | None) -> str:
    """Ritorna il nome dell'ente ignorando il codice iniziale (split sul primo spazio).

    entity_label("01-79000 DIREZIONE AGRIBUSINESS") -> "DIREZIONE AGRIBUSINESS"
    entity_label(None) -> ""
    """
    if not value:
        return ""
    parts = value.strip().split(" ", 1)
    return parts[1].strip() if len(parts) > 1 else parts[0]


def ente_code(value: "str | Enti | None") -> str:
    """Ritorna il codice di un ente canonico, stringa vuota se vuoto/nullo/sconosciuto."""
    if value is None:
        return ""
    v = (value.value if isinstance(value, Enti) else str(value)).strip()
    if not v:
        return ""
    code, _ = _split_code_label(v)
    return code or ""


def ente_name(code: str | None) -> str:
    """Ritorna il valore canonico ente a partire dal codice, o il valore in input se sconosciuto."""
    if not code:
        return ""
    return _CODE_TO_ENTE.get(str(code).strip().upper(), str(code).strip())


def canonical_ente_key(s: str | None) -> str | None:
    """Mappa una stringa grezza al valore canonico dell'enum `Enti`, o None.

    Il match avviene sul codice iniziale della stringa.

    Esempi:
        "0141020 - EM 01-41020 CONTROLLI BDT" → "0141020 - CONTROLLI BDT"
        "0141020 - CONTROLLI BDT"             → "0141020 - CONTROLLI BDT"
        "stringa senza codice"                 → None
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None

    if s in ENTI_VALUES:
        return s

    code = _extract_code(s)
    if code:
        return _CODE_TO_ENTE.get(code.upper())

    return None


# Indice nome-normalizzato → valore canonico, per risolvere gli ente riportati
# per NOME (senza codice, es. "Divisione BdT") — formato tipico della ground truth.
_NAME_TO_ENTE: dict[str, str] = {}
_CODENORM_TO_ENTE: dict[str, str] = {}
for _e in Enti:
    _code_part, _name_part = _split_code_label(_e.value)
    _name_key = _norm_key(_name_part)
    if _name_key:
        _NAME_TO_ENTE[_name_key] = _e.value
    if _code_part:
        _CODENORM_TO_ENTE[_norm_key(_code_part)] = _e.value
# Nomi enum ordinati per lunghezza decrescente: match del suffisso preferendo il più lungo.
_NAME_TO_ENTE_BY_LEN: list[tuple[str, str]] = sorted(_NAME_TO_ENTE.items(), key=lambda kv: -len(kv[0]))


def ente_name_key(value: "str | Enti | None") -> str | None:
    """Chiave di confronto ente basata sul NOME, per il matching di valutazione.

    A differenza di `canonical_ente_key` (code-first), risolve anche le stringhe che
    riportano solo il NOME dell'ente — formato tipico della ground truth, es.
    ``"Divisione BdT"`` — riconducendole al valore canonico dell'enum. Gli ente non
    presenti nell'enum ricadono su una chiave nome normalizzata, così che GT e
    predizione con lo stesso nome coincidano comunque.

    Esempi:
        "0105740 - Divisione BdT" → "0105740 - Divisione BdT"  (code-first)
        "Divisione BdT"           → "0105740 - Divisione BdT"  (per nome)
        "Chief Lending Officer"   → "chieflendingofficer"      (fuori enum, normalizzato)
    """
    if value is None:
        return None
    if isinstance(value, Enti):
        return value.value
    raw = str(value).strip()
    if not raw:
        return None

    canonical = canonical_ente_key(raw)
    if canonical is not None:
        return canonical

    _, label = _split_code_label(raw)
    key = _norm_key(label)
    hit = _NAME_TO_ENTE.get(key)
    if hit is not None:
        return hit

    # Forme grezze soa senza codice iniziale canonico (es. "EM 01-09545 DIR REG LOMBARDIA NORD"):
    # riconosci il codice enum incorporato o il nome enum come suffisso della stringa normalizzata.
    kfull = _norm_key(raw)
    for code_norm, canonical_value in _CODENORM_TO_ENTE.items():
        if code_norm and code_norm in kfull:
            return canonical_value
    for name_norm, canonical_value in _NAME_TO_ENTE_BY_LEN:
        if name_norm and kfull.endswith(name_norm):
            return canonical_value
    return key or None
