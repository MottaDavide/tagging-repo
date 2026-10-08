"""Stage 3: descrizione LLM di figure e tabelle, una call per pagina.

Combina describe + classify in una singola chiamata per pagina con structured
output Pydantic (`PageDescriptions`). Pre-filtering deterministico per layout
ricorrenti e figure chart-only (sostituiscono call LLM con euristiche).

Parallelizzazione delle pagine via `ThreadPoolExecutor` (`PAGES_MAX_WORKERS`).
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from pypdf import PdfReader

from core.config import CLEAN_DIR, CLEAN_WITH_DESC_DIR, DOCUMENTS_DIR, ENV_FILE
from core.models.tagging.img_table import PageDescriptions
from core.resources.builders import build_img_table_user_prompt
from core.resources.img_table_system import IMG_TABLE_SYSTEM
from core.services.llm_client import DEFAULT_MODEL, Layer, call_llm_timed, init_genfactory
from core.services.parsing.prepare import collapse_blank_lines, remove_empty_figures, remove_logo_figures
from core.services.text.markdown import (
    find_figures_and_tables_by_page,
    is_chart_only_figure,
    normalize_whitespace_lower,
    remove_chart_figures,
    strip_figure_tags,
)

logger = logging.getLogger(__name__)

_CONFIG = get_obj_from_config_path("tagging.yaml")["img_table"]
_LLM_CONFIG = get_obj_from_config_path("llm.yaml")["calls"]["img_table"]
_HTTP_TIMEOUT_CONFIG = _LLM_CONFIG["http_timeout"]

USE_CASE_ID: str = _LLM_CONFIG["use_case_id"]
MODEL: str = _LLM_CONFIG.get("model", DEFAULT_MODEL)
MAX_COMPLETION_TOKENS: int = _LLM_CONFIG["max_completion_tokens"]
PAGES_MAX_WORKERS: int = _CONFIG["pages_max_workers"]
LAYOUT_RECURRENCE_MIN: int = _CONFIG["layout_recurrence_min"]
LAYOUT_TEXT_MAX_CHARS: int = _CONFIG["layout_text_max_chars"]

_HTTP_TIMEOUT = httpx.Timeout(
    connect=_HTTP_TIMEOUT_CONFIG["connect"],
    read=_HTTP_TIMEOUT_CONFIG["read"],
    write=_HTTP_TIMEOUT_CONFIG["write"],
    pool=_HTTP_TIMEOUT_CONFIG["pool"],
)


# Figure-specific helpers --------------------------------------------------


def _figure_signature(md_text: str, pdf_meta: dict[str, Any] | None) -> str:
    """Fingerprint stabile per riconoscere figure layout ricorrenti."""
    image_name = normalize_whitespace_lower(str((pdf_meta or {}).get("name", "")))
    size_bytes = str((pdf_meta or {}).get("size_bytes", ""))
    if image_name:
        return f"img:{image_name}|size:{size_bytes}"
    return f"md:{normalize_whitespace_lower(md_text)[:120]}"


def _clean_markdown(md_text: str) -> str:
    """Riusa le 3 regole di cleaning di `prepare.py` rilevanti per questo stage."""
    cleaned = md_text
    for step in (remove_logo_figures, remove_empty_figures, collapse_blank_lines):
        cleaned = step(cleaned)
    return cleaned


# PDF image extraction ----------------------------------------------------


def _extract_pdf_images_by_page(pdf_path: Path) -> dict[int, list[dict[str, Any]]]:
    reader = PdfReader(str(pdf_path))
    images_by_page: dict[int, list[dict[str, Any]]] = {}
    for page_idx, page in enumerate(reader.pages, start=1):
        page_images: list[dict[str, Any]] = []
        for img_idx, image_obj in enumerate(page.images, start=1):
            page_images.append(
                {
                    "image_index_on_page": img_idx,
                    "name": getattr(image_obj, "name", None),
                    "width": getattr(image_obj, "width", None),
                    "height": getattr(image_obj, "height", None),
                    "color_space": getattr(image_obj, "color_space", None),
                    "bits_per_component": getattr(image_obj, "bits_per_component", None),
                    "size_bytes": len(getattr(image_obj, "data", b"")),
                }
            )
        images_by_page[page_idx] = page_images
    return images_by_page


# Cross-page occurrence (no LLM) ------------------------------------------


def _compute_signature_occurrences(
    md_pages: dict[int, dict[str, list[Any]]],
    pdf_images_by_page: dict[int, list[dict[str, Any]]],
) -> dict[str, int]:
    """Mapping `signature → numero di pagine distinte` in cui la figura compare."""
    signature_pages: dict[str, set[int]] = {}

    all_pages = sorted(set(md_pages.keys()) | set(pdf_images_by_page.keys()))
    for page_number in all_pages:
        page_md = md_pages.get(page_number, {"figures": [], "tables": []})
        page_pdf_images = pdf_images_by_page.get(page_number, [])

        for idx, fig in enumerate(page_md["figures"]):
            pdf_meta = page_pdf_images[idx] if idx < len(page_pdf_images) else None
            sig = _figure_signature(fig.get("md_text", ""), pdf_meta)
            signature_pages.setdefault(sig, set()).add(page_number)

    return {sig: len(pages) for sig, pages in signature_pages.items()}


# Pre-filtering deterministico --------------------------------------------


def _is_layout_figure_heuristic(item: dict[str, Any]) -> bool:
    occurrence = item.get("occurrence_count", 1)
    md_text = item.get("md_text", "") or ""
    return occurrence >= LAYOUT_RECURRENCE_MIN and len(md_text.strip()) < LAYOUT_TEXT_MAX_CHARS


def _is_chart_only_input(item: dict[str, Any]) -> bool:
    raw_text = item.get("raw_text") or item.get("md_text") or ""
    return is_chart_only_figure(raw_text)


# Per-page LLM call --------------------------------------------------------


def _build_user_prompt(
    page_number: int,
    figures_input: list[dict[str, Any]],
    tables_input: list[dict[str, Any]],
) -> str:
    compact_figures = [
        {
            "figure_index_on_page": item["figure_index_on_page"],
            "md_text": item.get("md_text", ""),
            "pdf_image": item.get("pdf_image"),
            "occurrence_count": item.get("occurrence_count", 1),
        }
        for item in figures_input
    ]
    compact_tables = [
        {
            "table_index_on_page": item["table_index_on_page"],
            "row_count": item.get("row_count", 0),
            "column_count": item.get("column_count", 0),
            "rows": item.get("rows", []),
        }
        for item in tables_input
    ]
    return build_img_table_user_prompt(
        page_number=page_number,
        figures_json=json.dumps(compact_figures, ensure_ascii=False),
        tables_json=json.dumps(compact_tables, ensure_ascii=False),
    )


def _describe_and_classify_page(
    layer: Layer,
    page_number: int,
    figures_input: list[dict[str, Any]],
    tables_input: list[dict[str, Any]],
    model: str,
    system_prompt: str,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Singola LLM call per la pagina con output Pydantic strutturato."""
    if not figures_input and not tables_input:
        return {}, {}

    user_msg = _build_user_prompt(page_number, figures_input, tables_input)
    result, elapsed = call_llm_timed(layer, system_prompt, user_msg, PageDescriptions, MAX_COMPLETION_TOKENS, model)
    if result is None:
        logger.warning("  Pagina %s: LLM fallito dopo retry, fallback applicato (%.1fs)", page_number, elapsed)
        return {}, {}

    figure_results: dict[int, dict[str, Any]] = {
        f.figure_index_on_page: {
            "description": f.description.strip(),
            "remove_as_layout": bool(f.remove_as_layout),
            "contains_chart": bool(f.contains_chart),
            "chart_type": f.chart_type,
            "reason": f.reason.strip(),
        }
        for f in result.figures
    }
    table_results: dict[int, dict[str, Any]] = {
        t.table_index_on_page: {
            "description": t.description.strip(),
            "contains_chart": bool(t.contains_chart),
            "chart_type": t.chart_type,
        }
        for t in result.tables
    }
    return figure_results, table_results


# Page processing (parallel) ----------------------------------------------


def _build_page_inputs(
    page_number: int,
    page_md: dict[str, list[Any]],
    page_pdf_images: list[dict[str, Any]],
    signature_occurrences: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Prepara figures_to_call / figures_skipped / tables_input applicando pre-filter."""
    figures_to_call: list[dict[str, Any]] = []
    figures_skipped: list[dict[str, Any]] = []

    for idx, fig in enumerate(page_md["figures"], start=1):
        pdf_meta = page_pdf_images[idx - 1] if idx - 1 < len(page_pdf_images) else None
        sig = _figure_signature(fig.get("md_text", ""), pdf_meta)
        item = {
            "figure_index_on_page": idx,
            "md_text": fig.get("md_text", ""),
            "raw_text": fig.get("raw_text", ""),
            "pdf_image": pdf_meta,
            "occurrence_count": signature_occurrences.get(sig, 1),
            "start_line": fig.get("start_line"),
            "end_line": fig.get("end_line"),
        }
        if _is_layout_figure_heuristic(item):
            figures_skipped.append({**item, "skip_reason": "layout-recurrent"})
            continue
        if _is_chart_only_input(item):
            figures_skipped.append({**item, "skip_reason": "chart-only-ocr"})
            continue
        figures_to_call.append(item)

    tables_input: list[dict[str, Any]] = [
        {
            "table_index_on_page": idx,
            "row_count": int(table.get("row_count", 0)),
            "column_count": int(table.get("column_count", 0)),
            "rows": table.get("rows", []),
            "start_line": table.get("start_line"),
            "end_line": table.get("end_line"),
        }
        for idx, table in enumerate(page_md["tables"], start=1)
    ]
    return figures_to_call, figures_skipped, tables_input


def _process_page(
    layer: Layer,
    page_number: int,
    figures_to_call: list[dict[str, Any]],
    figures_skipped: list[dict[str, Any]],
    tables_input: list[dict[str, Any]],
    model: str,
    system_prompt: str,
) -> dict[str, Any] | None:
    figure_results: dict[int, dict[str, Any]] = {}
    table_results: dict[int, dict[str, Any]] = {}

    if figures_to_call or tables_input:
        figure_results, table_results = _describe_and_classify_page(
            layer=layer,
            page_number=page_number,
            figures_input=figures_to_call,
            tables_input=tables_input,
            model=model,
            system_prompt=system_prompt,
        )

    figures_kept: list[dict[str, Any]] = []
    for item in figures_to_call:
        idx = item["figure_index_on_page"]
        res = figure_results.get(idx) or {
            "description": f"Figura rilevata in pagina {page_number}; descrizione non disponibile.",
            "remove_as_layout": False,
            "contains_chart": False,
            "chart_type": None,
            "reason": "AI response unavailable; kept by default.",
        }
        if res.get("remove_as_layout"):
            continue
        figures_kept.append(
            {
                "page_number": page_number,
                "figure_index_on_page": idx,
                "description": res["description"],
                "contains_chart": bool(res.get("contains_chart", False)),
                "chart_type": res.get("chart_type"),
            }
        )

    tables_kept: list[dict[str, Any]] = []
    for item in tables_input:
        idx = item["table_index_on_page"]
        res = table_results.get(idx) or {
            "description": (
                f"Tabella in pagina {page_number} con struttura "
                f"{item['row_count']} righe x {item['column_count']} colonne."
            ),
            "contains_chart": False,
            "chart_type": None,
        }
        tables_kept.append(
            {
                "page_number": page_number,
                "table_index_on_page": idx,
                "description": res["description"],
                "contains_chart": bool(res.get("contains_chart", False)),
                "chart_type": res.get("chart_type"),
            }
        )

    if not figures_kept and not tables_kept:
        return None
    return {
        "page_number": page_number,
        "figures": figures_kept,
        "tables": tables_kept,
        "figures_skipped_count": len(figures_skipped),
    }


def _generate_descriptions(
    layer: Layer,
    md_pages: dict[int, dict[str, list[Any]]],
    pdf_images_by_page: dict[int, list[dict[str, Any]]],
    signature_occurrences: dict[str, int],
    model: str,
    system_prompt: str,
    target_page: int | None = None,
) -> dict[int, dict[str, Any]]:
    """Itera le pagine in parallelo. Ritorna `page_number → page_descriptions`."""
    all_pages = sorted(set(md_pages.keys()) | set(pdf_images_by_page.keys()))
    if target_page is not None:
        all_pages = [p for p in all_pages if p == target_page]
        logger.info("Single-page mode: pagina %d.", target_page)

    page_jobs: list[tuple[int, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]] = []
    total_skipped_layout = total_skipped_chart = 0
    for page_number in all_pages:
        page_md = md_pages.get(page_number, {"figures": [], "tables": []})
        page_pdf_images = pdf_images_by_page.get(page_number, [])
        figures_to_call, figures_skipped, tables_input = _build_page_inputs(
            page_number, page_md, page_pdf_images, signature_occurrences
        )
        for s in figures_skipped:
            if s["skip_reason"] == "layout-recurrent":
                total_skipped_layout += 1
            elif s["skip_reason"] == "chart-only-ocr":
                total_skipped_chart += 1
        if not figures_to_call and not tables_input:
            continue
        page_jobs.append((page_number, figures_to_call, figures_skipped, tables_input))

    logger.info(
        "Pagine con contenuto da descrivere: %d (pre-filtered: %d layout, %d chart-only)",
        len(page_jobs),
        total_skipped_layout,
        total_skipped_chart,
    )

    output_by_page: dict[int, dict[str, Any]] = {}
    if not page_jobs:
        return output_by_page

    with ThreadPoolExecutor(max_workers=PAGES_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_process_page, layer, pn, fc, fs, tbl, model, system_prompt): pn
            for (pn, fc, fs, tbl) in page_jobs
        }
        for future in as_completed(futures):
            page_number = futures[future]
            try:
                page_out = future.result()
            except Exception:
                logger.exception("  Pagina %s: errore inatteso, skip", page_number)
                continue
            if page_out is not None:
                output_by_page[page_number] = page_out

    return output_by_page


# Markdown enrichment -----------------------------------------------------


def inject_descriptions_into_markdown(
    cleaned_md_text: str,
    images_and_tables_by_page: dict[int, dict[str, list[Any]]],
    descriptions_by_page: dict[int, dict[str, Any]],
) -> str:
    """Inserisce le descrizioni dopo i blocchi `<figure>`/`<table>`.

    Procede dal basso per non invalidare gli indici di riga. Indicizza per
    `figure_index_on_page` esplicito (più robusto se l'LLM skippa un indice).
    """
    lines = cleaned_md_text.splitlines()

    for page_number, page_content in sorted(images_and_tables_by_page.items(), key=lambda x: x[0], reverse=True):
        page_info = descriptions_by_page.get(page_number)
        if not page_info:
            continue

        fig_desc_by_idx: dict[int, str] = {
            f["figure_index_on_page"]: f["description"] for f in page_info.get("figures", [])
        }
        tbl_desc_by_idx: dict[int, str] = {
            t["table_index_on_page"]: t["description"] for t in page_info.get("tables", [])
        }

        inserts: list[tuple[int, str]] = []
        for idx, fig in enumerate(page_content["figures"], start=1):
            desc = fig_desc_by_idx.get(idx)
            if not desc:
                continue
            end_line = fig.get("end_line")
            if end_line is None:
                continue
            inserts.append((end_line + 1, f"\n> Descrizione figura: {desc}"))

        for idx, table in enumerate(page_content["tables"], start=1):
            desc = tbl_desc_by_idx.get(idx)
            if not desc:
                continue
            end_line = table.get("end_line")
            if end_line is None:
                continue
            inserts.append((end_line + 1, f"\n> Descrizione tabella: {desc}"))

        for pos, text in sorted(inserts, key=lambda x: x[0], reverse=True):
            if 0 <= pos <= len(lines):
                lines.insert(pos, text)

    return "\n".join(lines)


# Document + batch --------------------------------------------------------


def _read_inputs(input_dir: Path, target_name: str) -> tuple[Path, Path, str]:
    md_path = input_dir / f"{target_name}.md"
    pdf_path = DOCUMENTS_DIR / f"{target_name}.pdf"
    if not md_path.exists():
        raise FileNotFoundError(f"File markdown non trovato: {md_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"File PDF non trovato: {pdf_path}")
    return md_path, pdf_path, md_path.read_text(encoding="utf-8")


def process_document(
    layer: Layer,
    target_name: str,
    input_dir: Path,
    output_dir: Path,
    model: str,
    system_prompt: str,
    target_page: int | None = None,
) -> Path:
    """Pipeline completa per un singolo documento. Ritorna il path dell'output scritto."""
    _md_path, pdf_path, md_text = _read_inputs(input_dir, target_name)

    logger.info("[%s] Cleaning markdown…", target_name)
    cleaned_md_text = _clean_markdown(md_text)

    logger.info("[%s] Parsing markdown by page…", target_name)
    tables_and_images_position = find_figures_and_tables_by_page(cleaned_md_text)

    logger.info("[%s] Extracting PDF images by page…", target_name)
    pdf_images_by_page = _extract_pdf_images_by_page(pdf_path)

    logger.info("[%s] Computing figure signature occurrences (no AI)…", target_name)
    signature_occurrences = _compute_signature_occurrences(tables_and_images_position, pdf_images_by_page)

    descriptions_by_page = _generate_descriptions(
        layer=layer,
        md_pages=tables_and_images_position,
        pdf_images_by_page=pdf_images_by_page,
        signature_occurrences=signature_occurrences,
        model=model,
        system_prompt=system_prompt,
        target_page=target_page,
    )

    logger.info("[%s] Injecting descriptions into markdown…", target_name)
    enriched_md_text = inject_descriptions_into_markdown(
        cleaned_md_text=cleaned_md_text,
        images_and_tables_by_page=tables_and_images_position,
        descriptions_by_page=descriptions_by_page,
    )

    output_text = remove_chart_figures(enriched_md_text)
    output_text = strip_figure_tags(output_text)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_md_path = output_dir / f"{target_name}.md"
    output_md_path.write_text(output_text, encoding="utf-8")

    logger.info("[%s] Completed → %s", target_name, output_md_path)
    return output_md_path


def run_batch(
    input_dir: Path = CLEAN_DIR,
    output_dir: Path = CLEAN_WITH_DESC_DIR,
    model: str = MODEL,
    single_file: str | None = None,
    target_page: int | None = None,
    force: bool = False,
) -> None:
    """Esegue il batch di descrizione su tutti i documenti in `input_dir`."""
    targets = [Path(single_file).stem] if single_file else [p.stem for p in sorted(input_dir.glob("*.md"))]

    if not targets:
        logger.error("Nessun documento trovato in %s", input_dir)
        return

    if not force:
        targets = [t for t in targets if not (output_dir / f"{t}.md").exists()]

    if not targets:
        logger.info("Tutti i documenti già processati. Usa --force per riprocessare.")
        return

    logger.info("Documenti da processare: %d", len(targets))

    layer = init_genfactory(env_file=str(ENV_FILE), use_case_id=USE_CASE_ID, timeout=_HTTP_TIMEOUT)
    system_prompt = IMG_TABLE_SYSTEM

    t_global = time.time()
    n_ok = 0
    for target_name in targets:
        try:
            process_document(
                layer=layer,
                target_name=target_name,
                input_dir=input_dir,
                output_dir=output_dir,
                model=model,
                system_prompt=system_prompt,
                target_page=target_page,
            )
            n_ok += 1
        except FileNotFoundError:
            logger.exception("Skipping %s", target_name)
        except Exception:
            logger.exception("Errore inatteso processando %s", target_name)

    logger.info("Completato: %d/%d in %.1fs", n_ok, len(targets), time.time() - t_global)
