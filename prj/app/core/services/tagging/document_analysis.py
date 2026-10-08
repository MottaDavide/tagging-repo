"""Analisi strutturale del documento annotato (deterministica, no LLM).

Estrae da un markdown annotato (con marker `[PAGE N]` e `«ENTE[mention|canonical]»`):
  - `page_enti`: ente → pagine in cui appare il marker
  - `section_enti_list`: enti contenuti nelle sezioni (per ereditarietà heading)
  - `ente_metadata`: catalogo globale (pagine, frequenza, copertina, H1/H2)
"""

from typing import Any

from core.models.tagging.candidates import EnteAppearance
from core.services.text.markdown import RE_ENTE_CANONICAL, RE_HEADING, RE_PAGE_MARKER


def parse_doc_structure(
    doc_text: str,
) -> tuple[dict[int, list[str]], list[tuple[int, str, int, list[str]]]]:
    """Analizza la struttura enti del documento.

    Returns:
        (page_enti, section_enti_list) dove:
        - `page_enti`: pagina → lista di nomi canonici enti (ordine di apparizione)
        - `section_enti_list`: (heading_level, heading_text, page, enti_in_section)
    """
    current_page = 1
    tokens: list[tuple[str, object]] = []

    for line in doc_text.split("\n"):
        m_page = RE_PAGE_MARKER.match(line)
        if m_page:
            current_page = int(m_page.group(1))
            tokens.append(("page", current_page))
            continue

        m_heading = RE_HEADING.match(line)
        if m_heading:
            level = len(m_heading.group(1))
            heading_text = m_heading.group(2).strip()
            tokens.append(("heading", (level, heading_text, current_page)))
            continue

        for m_ente in RE_ENTE_CANONICAL.finditer(line):
            canonical = m_ente.group(1).strip()
            tokens.append(("ente", (canonical, current_page)))

    page_enti: dict[int, list[str]] = {}
    for kind, value in tokens:
        if kind == "ente":
            ente_val: Any = value
            canonical, page = str(ente_val[0]), int(ente_val[1])
            page_enti.setdefault(page, [])
            if canonical not in page_enti[page]:
                page_enti[page].append(canonical)

    section_enti_list: list[tuple[int, str, int, list[str]]] = []
    heading_indices = [i for i, (kind, _) in enumerate(tokens) if kind == "heading"]

    for pos, idx in enumerate(heading_indices):
        level, heading_text, page = tokens[idx][1]  # type: ignore[misc]
        level = int(level)
        page = int(page)
        next_boundary = len(tokens)
        for j in heading_indices[pos + 1 :]:
            next_level = tokens[j][1][0]  # type: ignore[index]
            if next_level <= level:
                next_boundary = j
                break
        enti_in_section: list[str] = []
        for kind, value in tokens[idx + 1 : next_boundary]:
            if kind == "ente":
                canonical = value[0]  # type: ignore[index]
                if canonical not in enti_in_section:
                    enti_in_section.append(canonical)
        section_enti_list.append((level, heading_text, page, enti_in_section))

    return page_enti, section_enti_list


def build_ente_metadata(
    doc_text: str,
    page_enti: dict[int, list[str]],
    section_enti_list: list[tuple[int, str, int, list[str]]],
) -> dict[str, EnteAppearance]:
    """Catalogo deterministico degli enti del documento.

    Per ogni ente annotato calcola: pagine in cui appare, frequenza totale,
    presenza in copertina (pag. 1), heading H1/H2 la cui sezione lo contiene.
    """
    mention_counts: dict[str, int] = {}
    for m in RE_ENTE_CANONICAL.finditer(doc_text):
        canonical = m.group(1).strip()
        mention_counts[canonical] = mention_counts.get(canonical, 0) + 1

    h1_per_ente: dict[str, list[str]] = {}
    h2_per_ente: dict[str, list[str]] = {}
    for level, heading_text, _page, enti in section_enti_list:
        if level == 1:
            target = h1_per_ente
        elif level == 2:
            target = h2_per_ente
        else:
            continue
        for ente in enti:
            bucket = target.setdefault(ente, [])
            if heading_text not in bucket:
                bucket.append(heading_text)

    all_enti = {e for enti in page_enti.values() for e in enti}

    out: dict[str, EnteAppearance] = {}
    for ente in all_enti:
        pages = sorted({p for p, enti in page_enti.items() if ente in enti})
        if not pages:
            continue
        out[ente] = EnteAppearance(
            canonical=ente,
            pages=pages,
            n_mentions=mention_counts.get(ente, 0),
            first_page=pages[0],
            in_cover=(1 in pages),
            h1_headings=h1_per_ente.get(ente, []),
            h2_headings=h2_per_ente.get(ente, []),
        )
    return out
