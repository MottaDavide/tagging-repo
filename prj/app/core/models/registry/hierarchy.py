"""Strutture dati gerarchia RM → MO → OdC + label formatting (dato)."""

from dataclasses import dataclass


def format_label(code: str, name: str) -> str:
    """Formatta codice e nome come label canonica: `'XXXX - Nome'`."""
    return f"{code} - {name}"


def extract_code(label: str) -> str:
    """Estrae il codice numerico iniziale da una label `'XXXX - Nome'`.

    Restituisce stringa vuota se il formato non è riconoscibile.
    """
    return label.split(" - ", 1)[0].strip() if " - " in label else ""


@dataclass(frozen=True)
class OdC:
    """Obiettivo di Controllo."""

    code: str
    name: str
    description: str

    @property
    def label(self) -> str:
        return format_label(self.code, self.name)


@dataclass(frozen=True)
class MO:
    """Macro Obiettivo con i suoi OdC."""

    code: str
    name: str
    description: str
    odcs: tuple[OdC, ...]

    @property
    def label(self) -> str:
        return format_label(self.code, self.name)


@dataclass(frozen=True)
class RMHierarchy:
    """Gerarchia completa per un Risk Model."""

    risk_model: str
    mos: tuple[MO, ...]

    def get_mo(self, mo_code: str) -> MO | None:
        return next((m for m in self.mos if m.code == mo_code), None)

    def get_odc(self, odc_code: str) -> OdC | None:
        for mo in self.mos:
            for odc in mo.odcs:
                if odc.code == odc_code:
                    return odc
        return None


@dataclass(frozen=True)
class Hierarchy:
    """Gerarchia completa RM → MO → OdC."""

    rms: dict[str, RMHierarchy]

    def get_rm(self, rm_name: str) -> RMHierarchy | None:
        return self.rms.get(rm_name)

    def is_supported(self, rm_name: str) -> bool:
        return rm_name in self.rms

    @property
    def supported_rms(self) -> list[str]:
        return sorted(self.rms.keys())
