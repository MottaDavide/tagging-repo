"""Parsing e manipolazione del markdown della pipeline.

Raccoglie:
  - Pattern di pagina (`[PAGE N]`) e heading.
  - Estrazione enti dai marker `«ENTE[mention|canonical]»`.
  - Normalizzazione testo per matching (NFKC, whitespace, dash/virgolette).
  - Helpers HTML-in-markdown (`<figure>`, `<table>`, `<tr>`, `<td>`): parsing,
    pulizia, rimozione figure chart-only.
  - Parser strutturale di figure e tabelle per pagina (output di Azure DI).

Tutto ciò che riguarda il testo grezzo del documento sta qui. La controparte
per le entità canoniche (anagrafica) sta in `core.models.registry.enti`.
"""

import re
import unicodedata
from collections import defaultdict
from typing import Any

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

_CONFIG = get_obj_from_config_path("tagging.yaml")["text"]["markdown"]

# Soglie chart-detection (vedi is_chart_only_figure, remove_chart_figures).
_CHART_ALPHA_RATIO_THRESHOLD: float = _CONFIG["chart_alpha_ratio_threshold"]
_CHART_MIN_SENTENCES: int = _CONFIG["chart_min_sentences"]
_CHART_CAPTION_MIN_CHARS: int = _CONFIG["chart_caption_min_chars"]


# Page markers + heading --------------------------------------------------

# Marker di pagina prodotto da `prepare`: una riga `[PAGE N]` da sola.
RE_PAGE_MARKER = re.compile(r"^\[PAGE (\d+)\]$", re.MULTILINE)
# Splitta un documento per pagina: gruppo 1 = numero, gruppo 2 = contenuto fino al
# prossimo `[PAGE N]` o EOF.
RE_PAGE_SPLIT = re.compile(r"\[PAGE (\d+)\](.*?)(?=\[PAGE \d+\]|\Z)", re.DOTALL)
RE_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


def extract_title(text: str) -> str:
    """Restituisce il titolo H1 del documento o `'(senza titolo)'`."""
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else "(senza titolo)"


def extract_first_page(text: str, max_chars: int = 4000) -> str:
    """Estrae la prima pagina del documento, anche senza marker iniziale `[PAGE 1]`."""
    first_marker = re.search(
        r"^\[PAGE\s+\d+\]$",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    if not first_marker:
        return text[:max_chars].strip()

    if first_marker.start() > 0:
        first_page = text[: first_marker.start()].strip()
        if first_page:
            return first_page[:max_chars]

    page1_match = re.search(
        r"^\[PAGE\s+1\]$(.*?)(?=^\[PAGE\s+2\]$|\Z)",
        text,
        flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )

    if page1_match:
        return ("[PAGE 1]\n" + page1_match.group(1).strip())[:max_chars]

    next_marker = re.search(
        r"^\[PAGE\s+\d+\]$",
        text[first_marker.end() :],
        flags=re.MULTILINE | re.IGNORECASE,
    )

    if next_marker:
        end_pos = first_marker.end() + next_marker.start()
        return text[first_marker.start() : end_pos].strip()[:max_chars]

    return text[first_marker.start() :].strip()[:max_chars]


def split_by_pages(md_text: str) -> list[tuple[int, str]]:
    """Splitta il markdown per pagina. Ritorna `[(numero_pagina, contenuto), ...]`."""
    return [(int(pn), content) for pn, content in RE_PAGE_SPLIT.findall(md_text)]


def iter_page_numbers(md_text: str) -> list[int]:
    """Numeri di pagina in ordine di apparizione."""
    return [int(m.group(1)) for m in RE_PAGE_MARKER.finditer(md_text)]


# Marker entità nel testo --------------------------------------------------

# Estrae il nome canonico dal formato `«ENTE[display|canonical]»` o `«ENTE[canonical]»`.
RE_ENTE_CANONICAL = re.compile(r"ENTE\[(?:[^\]|]*\|)?([^\]|]+)\]")


def extract_enti_from_text(text: str) -> list[str]:
    """Nomi canonici (univoci, ordinati) presenti nei marker `ENTE[...]`."""
    enti: set[str] = set()
    for m in RE_ENTE_CANONICAL.finditer(text):
        enti.add(m.group(1).strip())
    return sorted(enti)


# Normalizzazione testo per matching --------------------------------------


def normalize_for_matching(text: str) -> str:
    """Normalizza il testo per il matching delle ancore.

    Gestisce le principali fonti di discrepanza tra il documento (output OCR
    di Azure Document Intelligence) e le ancore generate dall'LLM:
      - Unicode (accenti, simboli, punteggiatura tipografica)
      - Spaziatura interna alle celle di tabelle markdown
      - Trattini/dash e virgolette tipografiche
      - Newline multipli
      - Spazi attorno ai newline (multi-colonna copiato dall'LLM)
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    # Caratteri tipografici -> ASCII. Le sorgenti SONO intenzionalmente non-ASCII
    # (è ciò che vogliamo matchare e sostituire): `noqa: RUF001` per linea.
    text = text.replace("–", "-").replace("—", "-")  # noqa: RUF001  en-dash, em-dash
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")  # noqa: RUF001  smart single quotes
    return text.replace("«", '"').replace("»", '"')


def normalize_whitespace_lower(value: str) -> str:
    """Lowercase + collassa runs di whitespace. Usato per signature/fingerprinting."""
    return re.sub(r"\s+", " ", value.lower().strip())


# HTML in markdown: figure, table -----------------------------------------

RE_TR = re.compile(r"<tr>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
RE_TCELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
RE_TAGS = re.compile(r"<[^>]+>")
RE_CHART_FIGURE = re.compile(
    r"<figure>\s*(?:<figcaption>[^<]*</figcaption>\s*)?([\s\S]*?)\s*</figure>",
    re.IGNORECASE | re.DOTALL,
)
RE_FIGURE_TAGS = re.compile(r"</?(?:figure|figcaption)[^>]*>", re.IGNORECASE)


def clean_html_cell(value: str) -> str:
    """Strip dei tag HTML e collasso whitespace: `'<b>foo</b>  bar'` → `'foo bar'`."""
    value = RE_TAGS.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def is_chart_only_figure(content: str) -> bool:
    """True se la `<figure>` contiene solo dati numerici/grafici OCR (no prosa)."""
    text = re.sub(r"<figcaption>.*?</figcaption>", "", content, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    alpha = len(re.findall(r"[a-zA-ZàèéìòùÀÈÉÌÒÙ]", text))
    total = len(text.strip())
    if total == 0:
        return True
    sentences = re.findall(r"[a-zA-ZàèéìòùÀÈÉÌÒÙ]{3,}(?:\s+[a-zA-ZàèéìòùÀÈÉÌÒÙ]{3,}){2,}", text)
    return alpha / total < _CHART_ALPHA_RATIO_THRESHOLD or len(sentences) < _CHART_MIN_SENTENCES


def remove_chart_figures(text: str) -> str:
    """Rimuove `<figure>` chart-only preservando una figcaption significativa."""

    def _replace(m: re.Match[str]) -> str:
        full, inner = m.group(0), m.group(1)
        if not is_chart_only_figure(inner):
            return full
        cap = re.search(r"<figcaption>(.*?)</figcaption>", full, re.DOTALL)
        if cap and len(cap.group(1).strip()) > _CHART_CAPTION_MIN_CHARS:
            return f"\n> *[Grafico: {cap.group(1).strip()}]*\n"
        return ""

    return RE_CHART_FIGURE.sub(_replace, text)


def strip_figure_tags(text: str) -> str:
    """Rimuove i tag `<figure>`/`<figcaption>` residui preservando il contenuto."""
    text = re.sub(r"<figcaption>(.*?)</figcaption>", r"**\1**", text, flags=re.DOTALL)
    text, _ = RE_FIGURE_TAGS.subn("", text)
    return text


def find_figures_and_tables_by_page(md_text: str) -> dict[int, dict[str, list[Any]]]:
    """Parsa figure (`<figure>`) e tabelle (`<table>`) per pagina.

    Ritorna `{pagina_n: {"figures": [...], "tables": [...]}}` dove ogni figura
    contiene `md_text`/`raw_text`/`start_line`/`end_line` e ogni tabella
    `rows`/`row_count`/`column_count`/`start_line`/`end_line`.
    """
    pages: dict[int, dict[str, list[Any]]] = defaultdict(lambda: {"figures": [], "tables": []})
    current_page = 1

    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        page_match = RE_PAGE_MARKER.search(line)
        if page_match:
            current_page = int(page_match.group(1))
            i += 1
            continue

        stripped = line.strip().lower()
        if stripped == "<figure>":
            start_idx = i
            i += 1
            figure_lines: list[str] = []
            while i < len(lines) and lines[i].strip().lower() != "</figure>":
                figure_lines.append(lines[i])
                i += 1
            end_idx = i
            pages[current_page]["figures"].append(
                {
                    "md_text": clean_html_cell("\n".join(figure_lines)),
                    "raw_text": "\n".join(figure_lines),
                    "start_line": start_idx,
                    "end_line": end_idx,
                }
            )
            i += 1
            continue

        if stripped == "<table>":
            start_idx = i
            i += 1
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().lower() != "</table>":
                table_lines.append(lines[i])
                i += 1
            end_idx = i
            table_html = "\n".join(table_lines)
            rows: list[list[str]] = []
            for row_html in RE_TR.findall(table_html):
                cells = [clean_html_cell(cell) for cell in RE_TCELL.findall(row_html)]
                if cells:
                    rows.append(cells)
            pages[current_page]["tables"].append(
                {
                    "rows": rows,
                    "row_count": len(rows),
                    "column_count": max((len(r) for r in rows), default=0),
                    "start_line": start_idx,
                    "end_line": end_idx,
                }
            )
            i += 1
            continue

        i += 1

    return dict(sorted(pages.items(), key=lambda item: item[0]))
