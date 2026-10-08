"""Test `core.{models,services}.registry.hierarchy`: dataclass, loader, canonicalizzazione label."""

from __future__ import annotations

import pytest

import core.services.registry.hierarchy as hierarchy_mod
from core.models.registry.hierarchy import (
    MO,
    Hierarchy,
    OdC,
    RMHierarchy,
    extract_code,
    format_label,
)
from core.models.registry.hierarchy_data import build_hierarchy
from core.services.registry.hierarchy import (
    SUPPORTED_RMS,
    canonicalize_label,
    mo_code,
    mo_names,
    odc_code,
    odc_names,
    rm_code,
)


class TestFormatLabel:
    def test_format(self) -> None:
        assert format_label("4601", "Istruttoria") == "4601 - Istruttoria"


class TestExtractCode:
    def test_extracts_from_canonical_form(self) -> None:
        assert extract_code("4601 - Istruttoria e proposta") == "4601"

    def test_returns_empty_when_no_separator(self) -> None:
        assert extract_code("NoCodeHere") == ""

    def test_strips_whitespace(self) -> None:
        assert extract_code("  4601   - Foo") == "4601"


class TestCanonicalizeLabel:
    def test_exact_match(self) -> None:
        valid = ["8838 - MO AML", "2578 - MO Concessione"]
        assert canonicalize_label("8838 - MO AML", valid) == "8838 - MO AML"

    def test_code_match(self) -> None:
        """Estraendo il codice 4-cifre, mappa alla canonica che inizia con quello."""
        valid = ["8838 - MO Gestione AML"]
        assert canonicalize_label("MO-05 — 8838 - MO Gestione AML", valid) == "8838 - MO Gestione AML"

    def test_substring_match(self) -> None:
        """La label canonica è sottostringa della raw."""
        valid = ["MO Concessione"]
        assert canonicalize_label("prefix MO Concessione suffix", valid) == "MO Concessione"

    def test_fallback_passthrough(self) -> None:
        assert canonicalize_label("Sconosciuto", ["X", "Y"]) == "Sconosciuto"


class TestDataclasses:
    def test_odc_label_property(self) -> None:
        odc = OdC(code="4601", name="Istruttoria", description="d")
        assert odc.label == "4601 - Istruttoria"

    def test_mo_label_property(self) -> None:
        mo = MO(code="2578", name="MO Concessione", description="d", odcs=())
        assert mo.label == "2578 - MO Concessione"

    def test_rm_hierarchy_get_mo(self) -> None:
        mo = MO(code="2578", name="MO C", description="", odcs=())
        rm = RMHierarchy(risk_model="Credito", mos=(mo,))
        assert rm.get_mo("2578") is mo
        assert rm.get_mo("9999") is None

    def test_rm_hierarchy_get_odc(self) -> None:
        odc = OdC(code="4601", name="X", description="")
        mo = MO(code="2578", name="MO C", description="", odcs=(odc,))
        rm = RMHierarchy(risk_model="Credito", mos=(mo,))
        assert rm.get_odc("4601") is odc
        assert rm.get_odc("9999") is None

    def test_hierarchy_get_rm(self) -> None:
        h = Hierarchy(rms={"Credito": RMHierarchy(risk_model="Credito", mos=())})
        assert h.get_rm("Credito") is not None
        assert h.get_rm("Other") is None

    def test_hierarchy_is_supported(self) -> None:
        h = Hierarchy(rms={"AML": RMHierarchy(risk_model="AML", mos=())})
        assert h.is_supported("AML")
        assert not h.is_supported("Other")

    def test_hierarchy_supported_rms_sorted(self) -> None:
        h = Hierarchy(
            rms={
                "Credito": RMHierarchy(risk_model="Credito", mos=()),
                "AML": RMHierarchy(risk_model="AML", mos=()),
            }
        )
        assert h.supported_rms == ["AML", "Credito"]


class TestBuildHierarchy:
    def test_returns_credito_and_aml(self) -> None:
        h = build_hierarchy()
        assert "Credito" in h.rms
        assert "AML" in h.rms

    def test_credito_has_expected_mo_and_odc(self) -> None:
        h = build_hierarchy()
        credito = h.get_rm("Credito")
        assert credito is not None
        assert any(mo.code == "2578" for mo in credito.mos)
        odc = credito.get_odc("4601")
        assert odc is not None
        assert odc.label == "4601 - Istruttoria e proposta"


class TestModuleHelpers:
    def test_mo_names_returns_labels(self) -> None:
        h = build_hierarchy()
        labels = mo_names(h, "Credito")
        assert "2578 - MO Concessione del credito" in labels

    def test_mo_names_unknown_rm(self) -> None:
        h = build_hierarchy()
        assert mo_names(h, "Sconosciuto") == []

    def test_odc_names_returns_labels(self) -> None:
        h = build_hierarchy()
        labels = odc_names(h, "Credito", "2578")
        assert "4601 - Istruttoria e proposta" in labels

    def test_odc_names_unknown_rm_or_mo(self) -> None:
        h = build_hierarchy()
        assert odc_names(h, "Sconosciuto", "2578") == []
        assert odc_names(h, "Credito", "9999") == []


class TestSupportedRmsConstant:
    def test_contains_credito_and_aml(self) -> None:
        assert "Credito" in SUPPORTED_RMS
        assert "AML" in SUPPORTED_RMS


class TestMoOdcRmCode:
    """RM, MO e OdC condividono lo stesso mapping/lookup: un'unica gerarchia di codici."""

    @pytest.fixture(autouse=True)
    def _fake_codes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hierarchy_mod._rm_code_to_name.cache_clear()
        monkeypatch.setattr(
            hierarchy_mod,
            "_HIERARCHY_CODES",
            {
                "rm": {"Credito": {"prod": "RM-CRED-P", "non_prod": "RM-CRED-T"}},
                "mo": {"2578": {"prod": "MO-P", "non_prod": "MO-T"}},
                "odc": {"4601": {"prod": "ODC-P", "non_prod": "ODC-T"}},
            },
        )

    def test_rm_code_none_input(self) -> None:
        assert rm_code(None) == ""

    def test_rm_code_unknown_returns_empty(self) -> None:
        assert rm_code("Operational Risk") == ""

    def test_rm_code_prod(self) -> None:
        assert rm_code("Credito", ambiente="prod") == "RM-CRED-P"

    def test_rm_code_non_prod(self) -> None:
        assert rm_code("Credito", ambiente="non_prod") == "RM-CRED-T"

    def test_rm_code_canonicalizes_before_lookup(self) -> None:
        assert rm_code("credito", ambiente="prod") == "RM-CRED-P"

    def test_mo_code_none_input(self) -> None:
        assert mo_code(None) == ""

    def test_mo_code_unknown_returns_empty(self) -> None:
        assert mo_code("9999 - Sconosciuto") == ""

    def test_mo_code_from_label_prod(self) -> None:
        assert mo_code("2578 - MO Concessione", ambiente="prod") == "MO-P"

    def test_mo_code_from_bare_code_non_prod(self) -> None:
        assert mo_code("2578", ambiente="non_prod") == "MO-T"

    def test_odc_code_from_label_prod(self) -> None:
        assert odc_code("4601 - Istruttoria", ambiente="prod") == "ODC-P"

    def test_odc_code_from_bare_code_non_prod(self) -> None:
        assert odc_code("4601", ambiente="non_prod") == "ODC-T"

    def test_defaults_to_resolved_ambiente(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ISP_AMBIENTE", "prod")
        assert mo_code("2578 - MO Concessione") == "MO-P"
        assert rm_code("Credito") == "RM-CRED-P"
        monkeypatch.setenv("ISP_AMBIENTE", "test")
        assert mo_code("2578 - MO Concessione") == "MO-T"
        assert rm_code("Credito") == "RM-CRED-T"

    def test_rm_code_to_name_uses_current_env_mapping(self) -> None:
        assert hierarchy_mod._rm_code_to_name("prod") == {"RM-CRED-P": "Credito"}
        hierarchy_mod._rm_code_to_name.cache_clear()
        assert hierarchy_mod._rm_code_to_name("non_prod") == {"RM-CRED-T": "Credito"}


class TestRmCodeToName:
    @pytest.fixture(autouse=True)
    def _fake_codes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            hierarchy_mod,
            "_HIERARCHY_CODES",
            {
                "rm": {
                    "Credito": {"prod": "RM-CRED-P", "non_prod": "RM-CRED-T"},
                    "AML": {"prod": "RM-AML-P", "non_prod": "RM-AML-T"},
                },
                "mo": {},
                "odc": {},
            },
        )
        hierarchy_mod._rm_code_to_name.cache_clear()

    def test_prod_mapping(self) -> None:
        assert hierarchy_mod._rm_code_to_name("prod") == {
            "RM-CRED-P": "Credito",
            "RM-AML-P": "AML",
        }

    def test_non_prod_mapping(self) -> None:
        assert hierarchy_mod._rm_code_to_name("non_prod") == {
            "RM-CRED-T": "Credito",
            "RM-AML-T": "AML",
        }

    def test_duplicate_code_raises(self) -> None:
        hierarchy_mod._rm_code_to_name.cache_clear()
        original_codes = hierarchy_mod._HIERARCHY_CODES
        hierarchy_mod._HIERARCHY_CODES = {
            "rm": {
                "Credito": {"prod": "RM-DUP", "non_prod": "RM-CRED-T"},
                "AML": {"prod": "RM-DUP", "non_prod": "RM-AML-T"},
            },
            "mo": {},
            "odc": {},
        }

        try:
            with pytest.raises(ValueError, match="Codice RM duplicato"):
                hierarchy_mod._rm_code_to_name("prod")
        finally:
            hierarchy_mod._HIERARCHY_CODES = original_codes
            hierarchy_mod._rm_code_to_name.cache_clear()


class TestRealHierarchyCodes:
    """Verifica sui dati reali di `HIERARCHY_CODES` (non mockati)."""

    def test_rm_credito_and_aml(self) -> None:
        assert rm_code("Credito", ambiente="prod") == "1080"
        assert rm_code("AML", ambiente="prod") == "1086"

    def test_odc_absent_in_non_prod_returns_empty(self) -> None:
        """L'OdC 5088 ('Fattori ESG nel processo di concessione') non esiste in svil/test/local."""
        assert odc_code("5088 - Fattori ESG nel processo di concessione", ambiente="prod") == "5088"
        assert odc_code("5088 - Fattori ESG nel processo di concessione", ambiente="non_prod") == ""
