"""Stage opzionale: annotazione marker `«RM[...] | MO[...] | ODC[...]»` nei documenti.

Pipeline deterministica (no LLM): legge il dizionario delle schede di controllo
(file statico) e inserisce nei markdown i marker `«RM[...] | MO[...] | ODC[...]»`.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.config import ANNOTATED_WITH_DESC_DIR, SCHEDE_TAGGED_JSON

logger = logging.getLogger(__name__)
_CODE_PREFIX_RE = re.compile(r"^([A-Z]{1,6}\s*\d+(?:[.\-]\d+)?(?:[A-Z]+)?)", re.IGNORECASE)
_ALREADY_ANNOTATED_RE = re.compile(r"\s*«RM\[[^\]]*\]\s*\|\s*MO\[[^\]]*\]\s*\|\s*ODC\[[^\]]*\]»")


def _format_marker(entry: dict[str, Any]) -> str:
    """Restituisce il marker standard."""
    rm = str(entry.get("Risk Model", "")).strip()
    mo = str(entry.get("mo", "")).strip()
    odc = str(entry.get("odc", "")).strip()
    return f"«RM[{rm}] | MO[{mo}] | ODC[{odc}]»"


def load_mapping(json_path: Path) -> dict[str, dict[str, str]]:
    """Carica il mapping `{chiave: {Risk Model, mo, odc}}` dal file JSON."""
    with json_path.open(encoding="utf-8") as file_obj:
        raw = json.load(file_obj)

    if not isinstance(raw, dict):
        raise TypeError(f"Formato mapping non valido in {json_path}: atteso oggetto JSON")

    out: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, dict):
            key_clean = key.strip()
            rm = str(value.get("Risk Model", "")).strip()
            mo = str(value.get("mo", "")).strip()
            odc = str(value.get("odc", "")).strip()
            if key_clean and (rm or mo or odc):
                out[key_clean] = {
                    "Risk Model": rm,
                    "mo": mo,
                    "odc": odc,
                }
    return out


def _build_code_base_map(mapping: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Estrae i prefissi codice (es. `B11` da `B11.1acc`) con relativa entry scheda."""
    base_to_entry: dict[str, dict[str, str]] = {}
    for key, entry in mapping.items():
        match = _CODE_PREFIX_RE.match(key)
        if not match:
            continue

        # usa solo il prefisso codice all'inizio della chiave, rimuovendo spazi e suffisso "acc"
        compact = re.sub(r"\s+", "", match.group(1))
        compact = re.sub(r"acc$", "", compact, flags=re.IGNORECASE)
        base = re.split(r"[.\-]", compact)[0]
        base_to_entry[base.upper()] = entry
    return base_to_entry


def _annotate_short_codes(md_text: str, base_to_entry: dict[str, dict[str, str]]) -> str:
    """Annota codici brevi nel testo evitando doppie annotazioni."""
    if not base_to_entry:
        return md_text

    bases = sorted(base_to_entry.keys(), key=len, reverse=True)
    pattern_str = r"\b(" + "|".join(re.escape(base) for base in bases) + r")(?:[.\-]\d+)?(?:acc)?\b"
    pattern = re.compile(pattern_str, re.IGNORECASE)

    def _replacer(match: re.Match[str]) -> str:
        entry = base_to_entry.get(match.group(1).upper())
        if not entry:
            return match.group(0)

        tail = md_text[match.end() :]
        if _ALREADY_ANNOTATED_RE.match(tail):
            return match.group(0)
        return f"{match.group(0)} {_format_marker(entry)}"

    return pattern.sub(_replacer, md_text)


def _annotate_long_keys(md_text: str, mapping: dict[str, dict[str, str]]) -> str:
    """Annota chiavi lunghe (multi-parola) (tolleranza sul whitespace)."""
    result = md_text
    for key, entry in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if _CODE_PREFIX_RE.match(key):
            continue

        words = key.strip().split()
        if len(words) <= 1:
            continue

        pattern = re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE | re.MULTILINE)

        def _replacer(match: re.Match[str], current_entry: dict[str, str] = entry) -> str:
            tail = match.string[match.end() :]
            if _ALREADY_ANNOTATED_RE.match(tail):
                return match.group(0)
            return f"{match.group(0)} {_format_marker(current_entry)}"

        result = pattern.sub(_replacer, result)

    return result


def enrich_md(md_text: str, mapping: dict[str, dict[str, str]]) -> str:
    """Arricchisce un markdown con marker `«RM[...] | MO[...] | ODC[...]»` in base al mapping."""
    with_short = _annotate_short_codes(md_text, _build_code_base_map(mapping))
    return _annotate_long_keys(with_short, mapping)


def annotate_document(md_path: Path, mapping: dict[str, dict[str, str]]) -> str:
    """Annota un documento markdown e ritorna il contenuto annotato."""
    return enrich_md(md_path.read_text(encoding="utf-8"), mapping)


def run_batch(
    input_dir: Path = ANNOTATED_WITH_DESC_DIR,
    output_dir: Path = ANNOTATED_WITH_DESC_DIR,
    schede_path: Path = SCHEDE_TAGGED_JSON,
    single_file: str | None = None,
    force: bool = False,
) -> None:
    """Annota i `.md` in `input_dir` con marker RM/MO/ODC e salva in `output_dir`."""
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = load_mapping(schede_path)

    if single_file:
        md_paths = [input_dir / single_file]
        if not md_paths[0].exists():
            md_paths = [input_dir / f"{Path(single_file).stem}.md"]
    else:
        md_paths = sorted(input_dir.glob("*.md"))

    if not md_paths:
        logger.error("Nessun documento trovato in %s.", input_dir)
        return

    in_place = input_dir.resolve() == output_dir.resolve()
    if not force and not in_place:
        md_paths = [path for path in md_paths if not (output_dir / path.name).exists()]

    logger.info("Documenti da annotare con schede: %d", len(md_paths))

    for md_path in md_paths:
        try:
            out_path = output_dir / md_path.name
            out_path.write_text(annotate_document(md_path, mapping), encoding="utf-8")
            logger.info("Salvato: %s", out_path.name)
        except Exception:
            logger.exception("[%s] ERRORE", md_path.name)

    logger.info("Completata annotazione-schede: %d/%d", len(md_paths), len(list(input_dir.glob("*.md"))))
