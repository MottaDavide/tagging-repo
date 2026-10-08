"""Generazione dell'analisi espositiva LLM per un singolo tag unico (Stage 7).

Una call LLM per tag unico: riceve il documento completo + le evidenze del tag e
restituisce un'analisi espositiva strutturata (`TagSummary`, template fisso).
L'estrazione delle descrizioni MO/OdC/RM dalla gerarchia e dai risk models vive
qui per essere riusata dall'orchestratore e dall'API.
"""

import logging
import unicodedata

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.models.registry.hierarchy import Hierarchy, extract_code
from core.models.registry.risk_models import RiskModel
from core.models.summary import TagSummary, UniqueTag
from core.services.llm_client import Layer, call_llm_timed

logger = logging.getLogger(__name__)

TAG_SUMMARY_MAX_TOKENS: int = get_obj_from_config_path("llm.yaml")["calls"]["tag_summary"]["max_tokens"]

_CONTEXT_CHARS: int = 400


def lookup_descriptions(
    hierarchy: Hierarchy | None,
    unique_tag: UniqueTag,
) -> tuple[str | None, str | None]:
    """Recupera le descrizioni di MO e OdC dalla gerarchia (best-effort).

    Le label dei tag hanno formato `'CODICE - Nome'`: si estrae il codice e si
    interroga la gerarchia. Ritorna `(None, None)` se la gerarchia non è
    disponibile o il RM/MO/OdC non vi è presente.
    """
    if hierarchy is None:
        return None, None
    rm_hier = hierarchy.get_rm(unique_tag.risk_model)
    if rm_hier is None:
        return None, None
    mo = rm_hier.get_mo(extract_code(unique_tag.mo))
    odc = rm_hier.get_odc(extract_code(unique_tag.odc))
    return (mo.description if mo else None), (odc.description if odc else None)


def lookup_rm_description(risk_models: list[RiskModel], rm_name: str) -> str | None:
    """Recupera i criteri completi del Risk Model per nome (match esatto).

    Restituisce il campo `criteria` del `RiskModel` trovato (testo completo,
    non troncato) da usare come contesto nel user message. Restituisce `None`
    se il RM non è presente nella lista.
    """
    for rm in risk_models:
        if rm.name == rm_name:
            return rm.criteria
    return None


def extract_citation_context(doc_text: str, citation: str, context_chars: int = _CONTEXT_CHARS) -> str | None:
    """Trova la citazione nel testo del documento e restituisce il contesto circostante.

    Prova in ordine: match esatto, case-insensitive, NFKC normalizzato, prefisso
    dei primi 50 caratteri. Restituisce `±context_chars` attorno alla citazione
    trovata, con marcatori `…` se il testo è stato tagliato. Restituisce `None`
    se la citazione non viene localizzata nel documento.
    """
    citation = citation.strip()
    if not citation or not doc_text:
        return None

    def _normalize(s: str) -> str:
        return unicodedata.normalize("NFKC", " ".join(s.split()))

    idx = doc_text.find(citation)
    if idx == -1:
        idx = doc_text.lower().find(citation.lower())
    if idx == -1:
        norm_doc = _normalize(doc_text)
        norm_cit = _normalize(citation)
        idx = norm_doc.lower().find(norm_cit.lower())
    if idx == -1:
        prefix = citation[:50].lower()
        idx = doc_text.lower().find(prefix)
    if idx == -1:
        return None

    start = max(0, idx - context_chars)
    end = min(len(doc_text), idx + len(citation) + context_chars)
    snippet = doc_text[start:end].strip()
    return f"{'…' if start > 0 else ''}{snippet}{'…' if end < len(doc_text) else ''}"


def build_summary_user_msg(
    unique_tag: UniqueTag,
    doc_title: str,
    doc_text: str,
    mo_description: str | None = None,
    odc_description: str | None = None,
    rm_description: str | None = None,
) -> str:
    """Costruisce il messaggio utente: descrizione tag contestualizzata + evidenze espanse + documento."""
    tag_lines = [
        "## TAG IN ESAME",
        "",
        f"Risk Model: **{unique_tag.risk_model}**",
    ]
    if rm_description:
        tag_lines.extend(["  Perimetro e criteri del RM:", rm_description.strip(), ""])
    tag_lines.append(f"Macro Obiettivo (MO): **{unique_tag.mo}**")
    if mo_description:
        tag_lines.append(f"  Definizione MO: {mo_description.strip()}")
    tag_lines.append(f"Obiettivo di Controllo (OdC): **{unique_tag.odc}**")
    if odc_description:
        tag_lines.append(f"  Definizione OdC: {odc_description.strip()}")
    tag_lines.append(f"Ente di riferimento: {unique_tag.ente or 'non specificato'}")

    evidenze_lines = ["## EVIDENZE NEL DOCUMENTO CHE HANNO GENERATO QUESTO TAG", ""]
    for occ in unique_tag.occorrenze:
        if occ.table_content:
            # Tabella: la citazione è un'etichetta breve, l'evidenza è il contenuto integrale
            # della tabella (l'etichetta non è ritrovabile nel documento, niente lookup di contesto).
            evidenze_lines.append(f"[Pag. {occ.pagina}] {occ.citazione}")
            evidenze_lines.extend(["Contenuto della tabella:", occ.table_content])
        else:
            evidenze_lines.append(f'[Pag. {occ.pagina}] "{occ.citazione}"')
            ctx = extract_citation_context(doc_text, occ.citazione)
            if ctx:
                evidenze_lines.extend(["Contesto nel documento:", ctx])
        evidenze_lines.append("")

    return (
        f"{chr(10).join(tag_lines)}\n\n"
        f"---\n\n"
        f"{chr(10).join(evidenze_lines)}\n\n"
        f"---\n\n"
        f"## DOCUMENTO COMPLETO\n\n"
        f"Titolo: {doc_title}\n\n"
        f"{doc_text}"
    )


def summarize_tag(
    layer: Layer,
    unique_tag: UniqueTag,
    doc_title: str,
    doc_text: str,
    system_prompt: str,
    model: str,
    mo_description: str | None = None,
    odc_description: str | None = None,
    rm_description: str | None = None,
) -> tuple[TagSummary | None, float]:
    """Una call LLM: analisi espositiva del documento per `unique_tag`.

    Ritorna `(TagSummary, elapsed_s)`; `(None, elapsed_s)` se la call fallisce
    (fail-soft per non bloccare il batch sugli altri tag).
    """
    user_msg = build_summary_user_msg(unique_tag, doc_title, doc_text, mo_description, odc_description, rm_description)
    return call_llm_timed(layer, system_prompt, user_msg, TagSummary, TAG_SUMMARY_MAX_TOKENS, model)
