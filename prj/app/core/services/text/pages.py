"""Parsing della stringa-pagina (formato GT) in lista di interi.

Util condiviso: la `pagina` di un tag è una stringa libera (es. `"7"`, `"22,23,24"`,
talvolta un range `"3-5"`). Questo modulo la normalizza in `list[int]` ordinata e
deduplicata, riusato sia dal tagger (`tag_rm`) sia dalla risposta API.
"""

import re

# Trattino o en-dash (U+2013) come separatore di range pagine.
_RANGE_SEP = re.compile(r"[-–]")  # noqa: RUF001
_CHUNK_SEP = re.compile(r"[,\s]+")


def parse_pages(pagina: str | None) -> list[int]:
    """Converte la stringa-pagina in `list[int]` ordinata e senza duplicati.

    Gestisce: liste separate da virgola/spazio (`"22,23"`), range espansi
    (`"3-5"` → `[3, 4, 5]`) e, come fallback, estrazione di tutte le cifre da un
    chunk non riconosciuto. Stringa vuota o `None` → `[]`.
    """
    pages: set[int] = set()
    for chunk in _CHUNK_SEP.split(pagina or ""):
        if not chunk:
            continue
        bounds = _RANGE_SEP.split(chunk)
        if len(bounds) == 2 and all(bound.isdigit() for bound in bounds):
            lo, hi = sorted(map(int, bounds))
            pages.update(range(lo, hi + 1))
        else:
            pages.update(int(match) for match in re.findall(r"\d+", chunk))
    return sorted(pages)
