"""Metrica di sovrapposizione testuale tra due citazioni."""

from difflib import SequenceMatcher

from core.services.text.markdown import normalize_whitespace_lower


def citation_overlap(a: str | None, b: str | None) -> float:
    """Quota della citazione più corta coperta da testo in comune con l'altra.

    Containment sui blocchi comuni di `SequenceMatcher`, normalizzato sulla
    citazione più corta — a differenza di `SequenceMatcher.ratio()` (simmetrico
    sulla lunghezza totale), una citazione troncata o che ne cita solo una
    porzione dell'altra ottiene comunque un punteggio alto se quella porzione
    coincide integralmente.
    """
    na, nb = normalize_whitespace_lower(a or ""), normalize_whitespace_lower(b or "")
    if not na or not nb:
        return 0.0
    matcher = SequenceMatcher(None, na, nb, autojunk=False)
    common = sum(block.size for block in matcher.get_matching_blocks())
    return common / min(len(na), len(nb))
