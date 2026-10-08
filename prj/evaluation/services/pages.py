"""Normalizzazione delle stringhe pagina usata dal matching delle metriche."""

import re


def normalize_pages(pagina: str | None) -> str:
    """Estrae i numeri da `pagina` e ritorna `'p1,p2,...'` (ordinato, dedupato).

    Espande range del tipo `'22-24'` → `'22,23,24'` (max 20 numeri di salto).
    """
    if not pagina:
        return ""
    s = str(pagina)

    def _expand_range(m: re.Match[str]) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < b - a <= 20:
            return ",".join(str(p) for p in range(a, b + 1))
        return m.group(0)

    s = re.sub(r"(\d+)\s*[-–]\s*(\d+)", _expand_range, s)  # noqa: RUF001
    nums = sorted({int(n) for n in re.findall(r"\d+", s)})
    return ",".join(str(p) for p in nums)


def pages_set(pagina: str | None) -> frozenset[int]:
    """Insieme di numeri di pagina parsato da `pagina`."""
    norm = normalize_pages(pagina)
    return frozenset(int(p) for p in norm.split(",") if p)
