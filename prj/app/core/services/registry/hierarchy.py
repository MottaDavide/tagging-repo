"""Gerarchia RM → MO → OdC: accesso, canonicalizzazione label, codice per ambiente."""

import re
from collections.abc import Callable
from functools import lru_cache

from core.config import Ambiente, resolve_ambiente
from core.models.registry.hierarchy import Hierarchy, extract_code
from core.models.registry.hierarchy_data import HIERARCHY_CODES
from core.services.registry.risk_models import canonicalize_rm

# RM per cui è disponibile la gerarchia MO/OdC completa
SUPPORTED_RMS: set[str] = {"Credito", "AML"}

_RE_LABEL_CODE = re.compile(r"\b(\d{4})\b")


def canonicalize_label(raw: str, valid_labels: list[str]) -> str:
    """Mappa una label MO/OdC emessa dall'LLM alla canonica fra le `valid_labels`.

    Strategia, in ordine:
      1. Match esatto.
      2. Codice 4-cifre estratto → label che inizia con quel codice.
      3. Sotto-stringa: una valid_label è contenuta in `raw`.
      4. Fallback: ritorna `raw` invariato (chi chiama decide se rifiutare).

    Esempi:
      "8838 - MO Gestione AML" → "8838 - MO Gestione AML"
      "MO-05 — 8834 - MO Gestione..." → "8834 - MO Gestione..."
      "blablabla 5069 e altro" → "5069 - Adeguata verifica..."
    """
    label = raw.strip()
    if label in valid_labels:
        return label
    m = _RE_LABEL_CODE.search(label)
    if m:
        code = m.group(1)
        for vl in valid_labels:
            if vl.startswith(code):
                return vl
    for vl in valid_labels:
        if vl in label:
            return vl
    return label


def mo_names(hierarchy: Hierarchy, rm_name: str) -> list[str]:
    """Lista dei label MO per un RM (es. '8838 - MO Gestione AML')."""
    rm = hierarchy.get_rm(rm_name)
    return [mo.label for mo in rm.mos] if rm else []


def odc_names(hierarchy: Hierarchy, rm_name: str, mo_code: str) -> list[str]:
    """Lista dei label OdC per un MO (es. '5069 - Adeguata verifica...')."""
    rm = hierarchy.get_rm(rm_name)
    if not rm:
        return []
    mo = rm.get_mo(mo_code)
    return [odc.label for odc in mo.odcs] if mo else []


# Codice RM/MO/OdC per ambiente (output API) -------------------------------
# RM, MO e OdC sono i tre livelli di un'unica gerarchia: condividono lo stesso
# mapping (`HIERARCHY_CODES`, chiavi "rm"/"mo"/"odc") e la stessa logica di lookup,
# differendo solo nella canonicalizzazione della chiave grezza in input.

_HIERARCHY_CODES: dict[str, dict[str, dict[str, str | None]]] = HIERARCHY_CODES


@lru_cache(maxsize=1)
def _rm_code_to_name(ambiente: Ambiente) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for rm_name, env_codes in _HIERARCHY_CODES.get("rm", {}).items():
        code = env_codes.get(ambiente)
        if not code:
            continue

        previous = mapping.get(code)
        if previous is not None and previous != rm_name:
            raise ValueError(f"Codice RM duplicato per env={ambiente}: {code} -> {previous}/{rm_name}")

        mapping[code] = rm_name

    return mapping


def _extract_mo_odc_code(raw: str) -> str:
    return extract_code(raw) or raw.strip()


def _code_for_env(kind: str, raw: str | None, ambiente: Ambiente | None, canonicalize: Callable[[str], str]) -> str:
    if not raw:
        return ""
    codes = _HIERARCHY_CODES.get(kind, {}).get(canonicalize(raw))
    if codes is None:
        return ""
    return codes.get(ambiente or resolve_ambiente()) or ""


def rm_code(name: str | None, ambiente: Ambiente | None = None) -> str:
    """Ritorna il codice RM per l'ambiente corrente (o quello passato), stringa vuota se sconosciuto."""
    return _code_for_env("rm", name, ambiente, canonicalize_rm)


def mo_code(label_or_code: str | None, ambiente: Ambiente | None = None) -> str:
    """Ritorna il codice MO per l'ambiente corrente (o quello passato), stringa vuota se sconosciuto."""
    return _code_for_env("mo", label_or_code, ambiente, _extract_mo_odc_code)


def odc_code(label_or_code: str | None, ambiente: Ambiente | None = None) -> str:
    """Ritorna il codice OdC per l'ambiente corrente (o quello passato), stringa vuota se sconosciuto."""
    return _code_for_env("odc", label_or_code, ambiente, _extract_mo_odc_code)
