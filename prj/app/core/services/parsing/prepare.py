"""Stage 2: pulizia statica dei markdown parsati.

Pipeline deterministica di regex `text → text` applicata in ordine.

Espone i building block (`clean_document`, `process_file`, le singole step) usabili da:
  - lo script `prj/scripts/pipeline.py` per l'orchestratore batch
  - future API che processano un singolo markdown
"""

import html
import logging
import re
from pathlib import Path

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.services.text.markdown import RE_PAGE_MARKER

logger = logging.getLogger(__name__)

NUM_WORKERS: int = get_obj_from_config_path("tagging.yaml")["prepare"]["num_workers"]


# Pattern compilati -------------------------------------------------------

_RE_PAGE_HEADER_FOOTER = re.compile(
    r"<!--\s*Page(?:Footer|Header)(?:=\"[^\"]*?\")?\s*-->\n?",
    re.IGNORECASE,
)
# PageBreak + zero o più PageNumber successivi (ordine DRTU: PageBreak→PageNumber).
# Per documenti con PageNumber PRIMA del PageBreak (ordine AML), i PageNumber
# vengono trattati come orfani e rimossi dall'handler successivo.
_RE_PAGE_BREAK_WITH_NUM = re.compile(
    r"<!--\s*PageBreak\s*-->\s*(?:<!--\s*PageNumber=\"(\d+)\"\s*-->\s*)*",
    re.IGNORECASE,
)
_RE_PAGE_NUMBER_ORPHAN = re.compile(
    r"<!--\s*PageNumber=\"[^\"]*\"\s*-->\n?",
    re.IGNORECASE,
)

# Alternative non vuote: `m+n*|n+m*` evita match dell'empty string dentro `(?:...)*`
# (ReDoS-prone). `\n` rimosso perché già coperto da `\s`. `re.DOTALL` rimosso (no `.`).
_RE_LOGO_FIGURE = re.compile(
    r"<figure>\s*(?:<figcaption>[^<]*</figcaption>\s*)??"
    r"(?:INTESA|SANPAOLO|m+n*|n+m*|\[m\]|CONFIDENZIALE|RISERVATO|\s)*"
    r"\s*</figure>",
    re.IGNORECASE,
)
_RE_EMPTY_FIGURE = re.compile(r"<figure>\s*</figure>", re.IGNORECASE | re.DOTALL)

# Tabelle indice/sommario (2 colonne: titolo | pagina). NO re.DOTALL +
# primo cell `[^<]*` per evitare backtracking che attraversa `[PAGE N]`.
# `\u002d` = HYPHEN-MINUS, `\u2013` = EN DASH (entrambi usati nei PDF come separatori di pagina)
_RE_TOC_TABLE = re.compile(
    r"<table>\s*"
    r"(?:"
    r"<tr>\s*"
    r"<td[^>]*>[^<]*</td>\s*"
    r"<td[^>]*>\s*\d{1,3}(?:\s*[\u002d\u2013]\s*\d{1,3})?\s*</td>\s*"
    r"</tr>\s*"
    r")+"
    r"</table>",
    re.IGNORECASE,
)

_RE_CLASSIFICATION_LABEL = re.compile(
    r"^(?:RISERVATO|CONFIDENZIALE|CLASSIFICATO|INTERNO|STRETTAMENTE RISERVATO)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Frammenti logo ISP/IMI CIB come righe isolate fuori <figure>.
# NON IGNORECASE: preserva "Intesa Sanpaolo" minuscolo nel testo normale.
_RE_LOGO_FRAGMENTS = re.compile(
    r"^(?:"
    r"INTESA(?:\s+(?:[mno]{1,4}|\[[^\]]{1,6}\]|[A-Z]{1,3}))*\s+SAN(?:PAOLO|PAOL[UO]|PA\w{0,4})"
    r"|INTESA|SANPAOLO"
    r"|[mno]{2,4}|\[m+\]|\[n[^\]]*\]"
    r"|IMI|CORPORATE\s*&?|INVESTMENT|BANKING"
    r")\s*$",
    re.MULTILINE,
)

_RE_DEEP_HEADING = re.compile(r"^(#{5,})\s+(.+)$", re.MULTILINE)
_RE_ESCAPED_MARKDOWN = re.compile(r"^(\d+)\\(\.\s)", re.MULTILINE)  # 1\. → 1.
_RE_ESCAPED_BULLET = re.compile(r"^\\([-*>])\s", re.MULTILINE)  # \- / \> / \*

# Checkbox standalone da diapositive (☐ ☒ ❑ ❏ □).
_RE_STANDALONE_CHECKBOX = re.compile(r"^\s*[☐☑☒❑❏□]\s*$", re.MULTILINE)
_RE_MULTI_BLANK = re.compile(r"\n{4,}")

_UNICODE_OCR_MAP = {"¿": "?", "¡": "!"}

_RE_CAPTION_TAG = re.compile(r"</?caption>", re.IGNORECASE)
_RE_ISOLATED_NOISE = re.compile(r"^\s*(?:[A-Z]\s*|\\?[+!])\s*$", re.MULTILINE)


# Cleaning steps ----------------------------------------------------------

# Regex ausiliaria per contare le entità HTML decodificate da `html.unescape`
# (`&amp;`, `&#160;`, `&#xA0;`, ...): serve solo al conteggio, non alla pulizia.
_RE_HTML_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|\w+);")


def _log_removed(step: str, count: int) -> None:
    """Logga a livello DEBUG quanti elementi uno step ha rimosso/trasformato.

    Pensata per il monitoraggio della pulizia: silenziosa quando non c'è nulla
    da segnalare (`count == 0`) per non sporcare il log.
    """
    if count:
        logger.debug("  prepare/%s: %d", step, count)


def convert_page_markers(text: str) -> str:
    """Converte commenti HTML di paginazione in marker `[PAGE N]` espliciti."""
    text, n_header_footer = _RE_PAGE_HEADER_FOOTER.subn("", text)

    page_counter = 1

    def _replace_break(m: re.Match[str]) -> str:
        nonlocal page_counter
        post_num = m.group(1)
        if post_num is not None:
            page_counter = int(post_num)
        else:
            page_counter += 1
        return f"\n\n[PAGE {page_counter}]\n\n"

    text, n_breaks = _RE_PAGE_BREAK_WITH_NUM.subn(_replace_break, text)
    text, n_orphan = _RE_PAGE_NUMBER_ORPHAN.subn("", text)

    _log_removed("header/footer di pagina rimossi", n_header_footer)
    _log_removed("page break convertiti in [PAGE N]", n_breaks)
    _log_removed("page number orfani rimossi", n_orphan)

    if not re.match(r"\s*\[PAGE \d+\]", text):
        text = f"[PAGE 1]\n\n{text}"
    return text


def remove_logo_figures(text: str) -> str:
    text, count = _RE_LOGO_FIGURE.subn("", text)
    _log_removed("figure-logo rimosse", count)
    return text


def remove_empty_figures(text: str) -> str:
    text, count = _RE_EMPTY_FIGURE.subn("", text)
    _log_removed("figure vuote rimosse", count)
    return text


def remove_toc_tables(text: str) -> str:
    text, count = _RE_TOC_TABLE.subn("", text)
    _log_removed("tabelle indice/sommario rimosse", count)
    return text


def remove_classification_labels(text: str) -> str:
    text, count = _RE_CLASSIFICATION_LABEL.subn("", text)
    _log_removed("etichette di classificazione rimosse", count)
    return text


def remove_logo_fragments(text: str) -> str:
    text, count = _RE_LOGO_FRAGMENTS.subn("", text)
    _log_removed("frammenti-logo rimossi", count)
    return text


def normalize_deep_headings(text: str) -> str:
    """Riduce a H4 i heading più profondi di H4 (artefatti OCR PPT)."""
    text, count = _RE_DEEP_HEADING.subn(r"#### \2", text)
    _log_removed("heading profondi normalizzati a H4", count)
    return text


def fix_escaped_markdown(text: str) -> str:
    """Rimuove backslash OCR davanti a `.`, `-`, `>`, `*` a inizio riga/lista."""
    text, n_num = _RE_ESCAPED_MARKDOWN.subn(r"\1\2", text)
    text, n_bullet = _RE_ESCAPED_BULLET.subn(r"\1 ", text)
    _log_removed("escape markdown corretti", n_num + n_bullet)
    return text


def remove_standalone_checkboxes(text: str) -> str:
    text, count = _RE_STANDALONE_CHECKBOX.subn("", text)
    _log_removed("checkbox isolate rimosse", count)
    return text


def decode_html_entities(text: str) -> str:
    """Decodifica `&amp;`, `&lt;`, `&gt;`, `&nbsp;`, ecc."""
    count = len(_RE_HTML_ENTITY.findall(text))
    _log_removed("entità HTML decodificate", count)
    return html.unescape(text)


def strip_caption_tags(text: str) -> str:
    text, count = _RE_CAPTION_TAG.subn("", text)
    _log_removed("tag <caption> rimossi", count)
    return text


def fix_unicode_ocr_artifacts(text: str) -> str:
    count = 0
    for old, new in _UNICODE_OCR_MAP.items():
        count += text.count(old)
        text = text.replace(old, new)
    _log_removed("artefatti unicode OCR corretti", count)
    return text


def remove_isolated_noise(text: str) -> str:
    """Rimuove lettere/punteggiatura isolate fuori dai blocchi `<table>`."""
    parts = re.split(r"(<table[\s\S]*?</table>)", text, flags=re.IGNORECASE)
    count = 0
    for i, part in enumerate(parts):
        if i % 2 == 0:
            parts[i], n = _RE_ISOLATED_NOISE.subn("", part)
            count += n
    _log_removed("rumore isolato rimosso", count)
    return "".join(parts)


def normalize_page_sequence(text: str) -> str:
    """Rinumera i `[PAGE N]` in sequenza 1..N nell'ordine di apparizione.

    Gestisce numeri fuori ordine, duplicati e documenti con allegati che
    reimpostano il counter da 1. No-op se la sequenza è già 1..N.
    """
    if not RE_PAGE_MARKER.search(text):
        return text

    first_match = RE_PAGE_MARKER.search(text)
    preamble = text[: first_match.start()] if first_match else ""

    segments: list[tuple[int, str]] = []
    matches = list(RE_PAGE_MARKER.finditer(text))
    for i, m in enumerate(matches):
        page_num = int(m.group(1))
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segments.append((page_num, text[content_start:content_end]))

    original_nums = [n for n, _ in segments]
    if original_nums == list(range(1, len(segments) + 1)):
        return text

    ellipsis = "..." if len(original_nums) > 20 else ""
    logger.warning(
        "  Sequenza pagine Azure DI anomala (originale: %s%s) → rinumerata 1..%d",
        original_nums[:20],
        ellipsis,
        len(segments),
    )

    parts = [preamble] if preamble.strip() else []
    for new_num, (_, content) in enumerate(segments, start=1):
        parts.append(f"[PAGE {new_num}]")
        parts.append(content)
    return "".join(parts)


def collapse_blank_lines(text: str) -> str:
    text, count = _RE_MULTI_BLANK.subn("\n\n\n", text)
    _log_removed("sequenze di righe vuote compattate", count)
    return text.strip() + "\n"


# Pipeline + batch --------------------------------------------------------


CLEANING_PIPELINE = [
    convert_page_markers,
    remove_logo_figures,
    remove_empty_figures,
    remove_toc_tables,
    remove_classification_labels,
    remove_logo_fragments,
    normalize_deep_headings,
    fix_escaped_markdown,
    remove_standalone_checkboxes,
    decode_html_entities,
    fix_unicode_ocr_artifacts,
    strip_caption_tags,
    remove_isolated_noise,
    normalize_page_sequence,
    collapse_blank_lines,
]


def clean_document(text: str) -> str:
    """Applica l'intera pipeline di cleaning a un documento markdown."""
    for step in CLEANING_PIPELINE:
        text = step(text)
    return text


def process_file(args: tuple[Path, Path]) -> tuple[str, bool, str]:
    """Pulisce un singolo `.md` e lo scrive in `output_dir`.

    Firma a tupla per compatibilità con `multiprocessing.Pool.map` lato script.
    """
    input_path, output_dir = args
    file_name = input_path.name
    try:
        raw = input_path.read_text(encoding="utf-8")
        cleaned = clean_document(raw)
        (output_dir / file_name).write_text(cleaned, encoding="utf-8")
        reduction = (1 - len(cleaned) / len(raw)) * 100 if raw else 0
        detail = f"riduzione {reduction:.0f}%"
        logger.info("[%s] OK %s", file_name, detail)
    except Exception as exc:
        logger.exception("[%s] ERRORE", file_name)
        return file_name, False, str(exc)
    else:
        return file_name, True, detail
