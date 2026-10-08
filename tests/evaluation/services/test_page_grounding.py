"""Test `evaluation.services.page_grounding`: ancoraggio pagina GT al frame del markdown."""

from __future__ import annotations

from evaluation.services.page_grounding import build_page_index, locate_pages, reground

# Markdown fittizio con 3 pagine numerate [PAGE N] e una tabella (esclusa dall'indice).
_MD = """[PAGE 1]
# Intestazione
La Direzione Impact evidenzia carenze nei controlli di primo livello sulle istanze aperte.
[PAGE 2]
Sono stati riscontrati sconfinamenti persistenti sulle posizioni in watch-list del portafoglio.
<table><tr><td>0105740 - Divisione BdT</td></tr></table>
[PAGE 3]
Il monitoraggio andamentale mostra un utilizzo elevato delle linee accordate alla clientela.
"""


def _index() -> tuple[str, list[int]]:
    return build_page_index(_MD)


def test_build_index_mappa_char_su_pagina() -> None:
    text, char_page = _index()
    assert "direzione impact evidenzia" in text
    # il testo tabella non entra nell'indice
    assert "divisione bdt" not in text
    # ogni carattere ha una pagina fra 1 e 3
    assert set(char_page) <= {1, 2, 3}
    assert len(text) == len(char_page)


def test_locate_su_pagina_corretta() -> None:
    text, char_page = _index()
    pages = locate_pages("La Direzione Impact evidenzia carenze nei controlli di primo livello", text, char_page)
    assert pages == frozenset({1})
    pages2 = locate_pages("sconfinamenti persistenti sulle posizioni in watch-list del portafoglio", text, char_page)
    assert pages2 == frozenset({2})


def test_locate_ignora_bullet_e_punteggiatura() -> None:
    text, char_page = _index()
    # citazione con bullet/maiuscole/punteggiatura diversi: la norm robusta la localizza comunque
    pages = locate_pages("▪ MONITORAGGIO andamentale — mostra un UTILIZZO elevato, delle linee", text, char_page)
    assert pages == frozenset({3})


def test_locate_non_trovata_ritorna_none() -> None:
    text, char_page = _index()
    assert locate_pages("Testo che non compare da nessuna parte nel documento", text, char_page) is None


def test_reground_corregge_offset_di_uno() -> None:
    # GT dice pagina 1, ma il contenuto sta a pagina 2 nel markdown -> correzione
    new, outcome = reground("1", frozenset({2}))
    assert outcome == "corrected"
    assert new == "2"


def test_reground_invariato_se_gia_allineato() -> None:
    new, outcome = reground("2", frozenset({2}))
    assert outcome == "unchanged"
    assert new == "2"


def test_reground_non_accorcia_range_gia_coperto() -> None:
    # lo span localizzato e' contenuto nel range GT -> nessuna modifica (niente shrink)
    new, outcome = reground("22,23,24", frozenset({23}))
    assert outcome == "unchanged"
    assert new == "22,23,24"


def test_reground_espande_a_span_multipagina() -> None:
    new, outcome = reground("12", frozenset({11, 12}))
    assert outcome == "corrected"
    assert new == "11,12"


def test_reground_rifiuta_relocazione_ampia() -> None:
    # salto di molte pagine: non e' un offset, si tiene la pagina GT e si segnala
    new, outcome = reground("95", frozenset({31}))
    assert outcome == "rejected_far"
    assert new == "95"


def test_reground_non_localizzata_tiene_pagina() -> None:
    new, outcome = reground("7", None)
    assert outcome == "not_found"
    assert new == "7"
