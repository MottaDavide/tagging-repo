"""Test `core.{models,services}.registry.enti`: anagrafica + canonicalizzazione."""

from __future__ import annotations

from core.models.registry.enti import Enti
from core.services.registry.enti import (
    ENTI_VALUES,
    canonical_ente_key,
    ente_name_key,
)


class TestEntiEnum:
    def test_has_canonical_anchor_values(self) -> None:
        assert Enti.GRUPPO_ISP.value == "0101025 - Gruppo ISP"
        assert Enti.CONTROLLI_BDT.value == "0141020 - CONTROLLI BDT"

    def test_enti_values_frozenset_matches_enum(self) -> None:
        assert isinstance(ENTI_VALUES, frozenset)
        assert {e.value for e in Enti} == ENTI_VALUES


class TestCanonicalEnteKey:
    def test_none_input(self) -> None:
        assert canonical_ente_key(None) is None
        assert canonical_ente_key("") is None
        assert canonical_ente_key("   ") is None

    def test_already_canonical(self) -> None:
        assert canonical_ente_key("0141020 - CONTROLLI BDT") == "0141020 - CONTROLLI BDT"

    def test_code_first_with_em_suffix(self) -> None:
        """La chiave grezza di soa-detection: match code-first sul codice iniziale."""
        assert canonical_ente_key("0141020 - EM 01-41020 CONTROLLI BDT") == "0141020 - CONTROLLI BDT"

    def test_name_only_returns_none(self) -> None:
        assert canonical_ente_key("Gruppo ISP") is None
        assert canonical_ente_key("EM 01-09545 DIR REG LOMBARDIA NORD") is None

    def test_unknown_returns_none(self) -> None:
        assert canonical_ente_key("stringa completamente sconosciuta") is None


class TestEnteNameKey:
    def test_none_and_empty(self) -> None:
        assert ente_name_key(None) is None
        assert ente_name_key("") is None
        assert ente_name_key("   ") is None

    def test_enum_passthrough(self) -> None:
        assert ente_name_key(Enti.GRUPPO_ISP) == "0101025 - Gruppo ISP"

    def test_code_first_still_resolves(self) -> None:
        assert ente_name_key("0141020 - CONTROLLI BDT") == "0141020 - CONTROLLI BDT"
        assert ente_name_key("0141020 - EM 01-41020 CONTROLLI BDT") == "0141020 - CONTROLLI BDT"

    def test_resolves_by_name(self) -> None:
        """Il caso della ground truth: solo il NOME, senza codice, ricondotto all'enum."""
        assert ente_name_key("Divisione BdT") == "0105740 - Divisione BdT"
        assert ente_name_key("CONTROLLI BDT") == "0141020 - CONTROLLI BDT"

    def test_out_of_enum_falls_back_to_normalized_name(self) -> None:
        assert ente_name_key("Ente Fantasia Non In Enum") == "entefantasianoninenum"

    def test_soa_raw_form_with_embedded_code(self) -> None:
        """Forma grezza soa (codice non iniziale): ricondotta all'enum via codice incorporato."""
        assert ente_name_key("EM 01-09545 DIR REG LOMBARDIA NORD") == "0109545 - DIR REG LOMBARDIA NORD"

    def test_soa_raw_form_matches_by_name_suffix(self) -> None:
        assert ente_name_key("report divisione bdt") == "0105740 - Divisione BdT"

    def test_gt_name_matches_pred_code_form(self) -> None:
        """GT (nome) e PRED (codice-nome) collassano sulla stessa chiave."""
        assert ente_name_key("Divisione BdT") == ente_name_key("0105740 - Divisione BdT")
