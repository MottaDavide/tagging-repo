"""Ancoraggio della pagina GT al frame del markdown (correzione dell'offset di pagina).

La `Pagina` di un tag GT proviene dall'annotazione umana sul PDF; la numerazione `[PAGE N]` del
markdown (cio' che il modello legge e taggia, e quindi il frame delle predizioni) e' sfalsata di +-1
in alcuni documenti. Senza correzione, GT e predizione parlano di pagine diverse per lo stesso
contenuto e il criterio di sovrapposizione pagine del matcher fallisce.

Questo modulo localizza la citazione GT dentro il markdown (per ancore testuali robuste) e riporta la
`Pagina` GT nella numerazione del markdown, in modo che GT e predizioni condividano lo stesso frame.
La correzione e' CONSERVATIVA:

- si applica solo quando la citazione e' localizzata con confidenza (ancore che convergono su uno
  span contiguo, oppure due ancore sulla stessa pagina);
- si applica solo a spostamenti piccoli (fino a ``MAX_SHIFT`` pagine): una relocazione ampia non e'
  un offset ma un possibile errore GT / match ambiguo, e resta invariata (da rivedere a mano);
- non accorcia mai una pagina GT gia' corretta: se lo span localizzato e' contenuto in quello GT, il
  tag resta invariato.

Riguarda solo i tag di TESTO: i tag-tabella si matchano per id-tabella, non per pagina.
"""

import re
from collections import Counter

from core.services.text.pages import parse_pages

# Numerazione [PAGE N] del markdown.
_RE_PAGE = re.compile(r"^\[PAGE\s*(\d+)\]", re.IGNORECASE)
# Marker enti/schede: rimossi come nella segmentazione (non fanno parte del testo confrontabile).
_RE_MARKER = re.compile(r"«[^»]*»")
_RE_TABLE = re.compile(r"<table.*?</table>", re.IGNORECASE | re.DOTALL)
# Normalizzazione robusta: tiene solo lettere/cifre (anche accentate); bullet, punteggiatura e
# simboli diventano spazio, cosi' le ancore non falliscono su differenze di formattazione.
_RE_NONALNUM = re.compile(r"[^0-9a-zà-öø-ÿ]+", re.IGNORECASE)

_MIN_ANCHOR = 12  # lunghezza minima di un'ancora perche' sia distintiva
_ANCHOR_LEN = 60  # lunghezza delle ancore di inizio/fine
_SPAN_TOLERANCE = 2  # massima ampiezza (in pagine) dello span di ancore per accettarlo come contiguo
MAX_SHIFT = 2  # massimo spostamento (in pagine) tra span localizzato e pagina GT per correggere


def _norm(text: str) -> str:
    return _RE_NONALNUM.sub(" ", _RE_MARKER.sub(" ", text.lower())).strip()


def build_page_index(markdown: str) -> tuple[str, list[int]]:
    """Ritorna `(testo_normalizzato, char_page)` dal markdown.

    `char_page[i]` e' il numero di pagina `[PAGE N]` a cui appartiene il carattere `i` di
    `testo_normalizzato`. Le tabelle sono escluse (unita' a se'), come nella segmentazione.
    """
    body = _RE_TABLE.sub(" ", markdown)
    chunks: list[str] = []
    char_page: list[int] = []
    page = 0
    for raw in body.split("\n"):
        marker = _RE_PAGE.match(raw.strip())
        if marker:
            page = int(marker.group(1))
            continue
        line = _norm(raw)
        if not line:
            continue
        chunk = line + " "
        chunks.append(chunk)
        char_page.extend([page] * len(chunk))
    return "".join(chunks), char_page


def _anchors(citazione_norm: str) -> list[str]:
    """Ancore distintive (inizio / meta' / fine) per localizzare la citazione nel markdown."""
    if len(citazione_norm) < _MIN_ANCHOR:
        return []
    if len(citazione_norm) < 30:
        return [citazione_norm]
    mid = len(citazione_norm) // 2
    candidates = [
        citazione_norm[:_ANCHOR_LEN],
        citazione_norm[max(0, mid - 30) : mid + 30],
        citazione_norm[-_ANCHOR_LEN:],
    ]
    return [a for a in candidates if len(a) >= _MIN_ANCHOR]


def locate_pages(citazione: str, index_text: str, char_page: list[int]) -> frozenset[int] | None:
    """Pagine markdown coperte dalla citazione, o `None` se non localizzabile con confidenza.

    Cerca le ancore (inizio/meta'/fine) nel testo del markdown. Se le pagine trovate formano uno
    span contiguo di ampiezza <= ``_SPAN_TOLERANCE`` ritorna l'intero span; se sono disperse ma
    almeno due ancore cadono sulla stessa pagina ritorna quella; altrimenti `None`.
    """
    cit = _norm(citazione)
    found: list[int] = []
    last = len(char_page) - 1
    for anchor in _anchors(cit):
        pos = index_text.find(anchor)
        if pos < 0:
            continue
        found.append(char_page[pos])
        found.append(char_page[min(pos + len(anchor) - 1, last)])
    if not found:
        return None
    pages = sorted(set(found))
    if pages[-1] - pages[0] <= _SPAN_TOLERANCE:
        return frozenset(range(pages[0], pages[-1] + 1))
    page, count = Counter(found).most_common(1)[0]
    return frozenset({page}) if count >= 2 else None


def _format(pages: frozenset[int]) -> str:
    return ",".join(str(p) for p in sorted(pages))


def reground(current: str | None, located: frozenset[int] | None, max_shift: int = MAX_SHIFT) -> tuple[str, str]:
    """Nuova stringa-`Pagina` + esito, dato lo span localizzato.

    Esiti: ``not_found`` (citazione non localizzata), ``unchanged`` (span localizzato gia' coperto
    dalla pagina GT), ``corrected`` (offset/espansione applicati), ``rejected_far`` (relocazione
    troppo ampia: tenuta invariata, da rivedere).
    """
    current_pages = frozenset(parse_pages(current))
    if located is None:
        return _format(current_pages), "not_found"
    if located <= current_pages:
        return _format(current_pages), "unchanged"
    if not current_pages:
        return _format(located), "corrected"
    distance = min(abs(a - b) for a in located for b in current_pages)
    if distance <= max_shift:
        return _format(located), "corrected"
    return _format(current_pages), "rejected_far"
