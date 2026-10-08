"""Ottimizza le descrizioni OdC e genera quelle MO per il tagging.

Legge le descrizioni OdC da `odc_credito.xlsx` e `odc_aml.xlsx` (colonna D
"Nuova proposta di riscrittura"), le riformula via LLM per renderle più
efficaci nel task di tagging, e genera descrizioni sintetiche per i MO
aggregando gli OdC contenuti.

Output:
  - `data/odc_descriptions_optimized.json`
  - `data/mo_descriptions.json`
  - `data/hierarchy.json`  (gerarchia completa RM → MO → OdC, usata dal tagger)

Script one-shot (non parte della pipeline runtime): si appoggia ai moduli
condivisi di `core` (config, llm, models, logging) ma contiene qui la propria logica.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import click
import httpx
import openpyxl
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from pydantic import Field

from core.config import (
    DATA_DIR,
    ENV_FILE,
    MO_DESCRIPTIONS_JSON,
    ODC_AML_XLSX,
    ODC_CREDITO_XLSX,
    ODC_DESCRIPTIONS_JSON,
)
from core.models.strict import StrictModel
from core.services.llm_client import DEFAULT_MODEL, Layer, call_llm, init_genfactory
from core.utils.logging import setup_logging

logger = logging.getLogger(__name__)

_CONFIG = get_obj_from_config_path("llm.yaml")["calls"]["optimize_odc"]

USE_CASE_ID: str = _CONFIG["use_case_id"]
MODEL: str = _CONFIG.get("model", DEFAULT_MODEL)
MAX_COMPLETION_TOKENS: int = _CONFIG["max_completion_tokens"]
_HTTP_TIMEOUT_S: float = _CONFIG["http_timeout_s"]

# Output intermedio: gerarchia ottimizzata da riportare in hierarchy_data.py
_HIERARCHY_OUT = DATA_DIR / "hierarchy.json"


# Gerarchia RM → MO → OdC (struttura fissa, codici allineati alla GT) ------

HIERARCHY: dict[str, dict[str, dict[str, str | list[str]]]] = {
    "Credito": {
        "2503": {
            "name": "MO Rating",
            "odcs": [
                "Modelli di gestione del credito",
                "Attribuzione del rating",
                "Stress test",
            ],
        },
        "2576": {
            "name": "MO Gestione e controllo del rischio di credito",
            "odcs": [
                "Requisiti patrimoniali",
                "Rettifica di valore da valutazione analitico-statistica e da valutazione collettiva dei crediti in bonis",
            ],
        },
        "2578": {
            "name": "MO Concessione del credito",
            "odcs": [
                "Istruttoria e proposta",
                "Delibera",
                "Perfezionamento",
                "Fattori ESG nel processo di concessione",
            ],
        },
        "8833": {
            "name": "MO Credit Risk Mitigation (Garanzie e Covenant)",
            "odcs": [
                "Gestione e monitoraggio delle mitigazioni del rischio di credito",
                "Gestione delle perizie",
            ],
        },
        "8834": {
            "name": "MO Gestione e monitoraggio del credito performing",
            "odcs": [
                "Monitoraggio del credito",
                "Intercettamento e gestione del credito anomalo",
            ],
        },
        "8835": {
            "name": "MO Credito non performing",
            "odcs": [
                "Past due",
                "Unlikely to Pay",
                "Sofferenze",
                "Cessione e gestione portafogli / crediti",
            ],
        },
    },
    "AML": {
        "8838": {
            "name": "MO Gestione AML",
            "odcs": [
                "Adeguata verifica della clientela",
                "Conservazione e messa a disposizione dei documenti, dei dati e delle informazioni per il contrasto del riciclaggio e del finanziamento del terrorismo",
                "Obblighi di segnalazione e comunicazione",
                "Monitoraggio della movimentazione - Transaction Monitoring",
                "Limitazioni in materia di contante, titoli al portatore, intestazione prodotti di conto, moneta elettronica e libretti",
                "Gestione Antiterrorismo e embarghi",
                "Ruolo e Processi di Governo assegnati alla Funzione Antiriciclaggio",
                "Gestione del Management Information System",
            ],
        },
    },
}

ODC_CODES: dict[str, str] = {
    "Istruttoria e proposta": "4601",
    "Delibera": "4602",
    "Perfezionamento": "4603",
    "Fattori ESG nel processo di concessione": "5088",
    "Gestione e monitoraggio delle mitigazioni del rischio di credito": "4604",
    "Gestione delle perizie": "4604b",
    "Past due": "4612",
    "Unlikely to Pay": "5053",
    "Sofferenze": "5054",
    "Monitoraggio del credito": "5051",
    "Intercettamento e gestione del credito anomalo": "5052",
    "Modelli di gestione del credito": "5049",
    "Attribuzione del rating": "5050",
    "Stress test": "5050b",
    "Requisiti patrimoniali": "4598",
    "Rettifica di valore da valutazione analitico-statistica e da valutazione collettiva dei crediti in bonis": "5047",
    "Cessione e gestione portafogli / crediti": "5054b",
    "Adeguata verifica della clientela": "5069",
    "Conservazione e messa a disposizione dei documenti, dei dati e delle informazioni per il contrasto del riciclaggio e del finanziamento del terrorismo": "5070",
    "Obblighi di segnalazione e comunicazione": "4712",
    "Monitoraggio della movimentazione - Transaction Monitoring": "5071",
    "Limitazioni in materia di contante, titoli al portatore, intestazione prodotti di conto, moneta elettronica e libretti": "5072",
    "Gestione Antiterrorismo e embarghi": "4714",
    "Ruolo e Processi di Governo assegnati alla Funzione Antiriciclaggio": "5073",
    "Gestione del Management Information System": "5074",
}


# Dataclass ---------------------------------------------------------------


@dataclass
class OdCDescription:
    """Descrizione di un Obiettivo di Controllo."""

    code: str
    name: str
    rm: str
    mo_code: str
    mo_name: str
    original_description: str
    optimized_description: str = ""


@dataclass
class MODescription:
    """Descrizione di un Macro Obiettivo."""

    code: str
    name: str
    rm: str
    description: str = ""
    odc_codes: list[str] = field(default_factory=list)


# Pydantic models per LLM output ------------------------------------------


class OptimizedDescription(StrictModel):
    """Output LLM: descrizione OdC riformulata per il tagging."""

    optimized_description: str = Field(
        description=(
            "La descrizione riformulata dell'Obiettivo di Controllo, ottimizzata per il "
            "task di tagging documentale. Stesse informazioni dell'originale, organizzate "
            "in modo più efficace per il matching semantico."
        )
    )


class MOSyntheticDescription(StrictModel):
    """Output LLM: descrizione sintetica del Macro Obiettivo."""

    description: str = Field(
        description=(
            "Descrizione sintetica del MO che cattura l'ambito complessivo coperto dagli "
            "OdC contenuti, ottimizzata per il task di tagging documentale."
        )
    )


# Prompt -------------------------------------------------------------------


SYSTEM_PROMPT_ODC = """\
Sei un esperto di risk management bancario e di ottimizzazione di prompt per sistemi di \
classificazione automatica. Il tuo compito è riformulare la descrizione di un Obiettivo di \
Controllo (OdC) bancario in modo che sia più efficace per un sistema di tagging \
documentale automatizzato.

## Contesto

Il sistema di tagging analizza documenti di audit bancario per identificare quali porzioni \
di testo trattano temi legati a specifici Obiettivi di Controllo. Per fare questo, confronta \
il contenuto del documento con la descrizione dell'OdC.

## Regole di riformulazione

1. **NON aggiungere informazioni** non presenti nell'originale
2. **NON rimuovere informazioni** presenti nell'originale
3. **NON inventare** esempi, scenari o dettagli
4. **Riorganizza** il testo in modo strutturato:
   - Inizia con una frase definitoria chiara che delimiti l'ambito dell'OdC
   - Poi elenca i criteri/verifiche specifiche raggruppati per tema
   - Evidenzia le parole chiave e i concetti discriminanti che distinguono questo OdC \
     da OdC simili dello stesso Macro Obiettivo
5. **Rimuovi ridondanze**: molte descrizioni ripetono "L'obiettivo di controllo verifica..." \
   — condensale senza perdere specificità
6. **Mantieni i termini tecnici** bancari invariati (non parafrasare)
7. **Disambigua**: se l'OdC originale specifica "non riguarda X", mantieni questa esclusione \
   perché è fondamentale per il matching corretto
8. Scrivi in **italiano**
"""

USER_PROMPT_ODC_TEMPLATE = """\
## OdC da riformulare

**Nome**: {odc_name}
**Risk Model**: {rm}
**Macro Obiettivo**: {mo_code} - {mo_name}

### Descrizione originale

{original_description}

### OdC fratelli nello stesso MO (per contesto — NON riformulare questi)

{sibling_odcs}

---

Riformula la descrizione dell'OdC "{odc_name}" seguendo le regole indicate.
"""

SYSTEM_PROMPT_MO = """\
Sei un esperto di risk management bancario. Il tuo compito è generare una descrizione \
sintetica di un Macro Obiettivo (MO) a partire dalle descrizioni degli Obiettivi di \
Controllo (OdC) che contiene.

## Regole

1. La descrizione deve catturare l'ambito complessivo del MO, non essere un elenco degli OdC
2. Deve essere utile per un sistema di tagging documentale che deve decidere se una porzione \
   di testo rientra nell'ambito di questo MO
3. Lunghezza: 150-300 parole
4. **NON inventare** informazioni non desumibili dagli OdC
5. Evidenzia i confini del MO: cosa copre e cosa NON copre (in relazione ad altri MO dello \
   stesso RM, se indicati)
6. Scrivi in **italiano**
"""

USER_PROMPT_MO_TEMPLATE = """\
## Macro Obiettivo da descrivere

**Codice**: {mo_code}
**Nome**: {mo_name}
**Risk Model**: {rm}

### OdC contenuti in questo MO

{odc_descriptions}

### Altri MO dello stesso RM (per contesto — NON descrivere questi)

{sibling_mos}

---

Genera una descrizione sintetica del MO "{mo_name}" che ne catturi l'ambito complessivo.
"""


# Caricamento OdC da Excel ------------------------------------------------


def _find_mo_for_odc(rm: str, odc_name: str) -> tuple[str, str]:
    rm_hierarchy = HIERARCHY.get(rm, {})
    for mo_code, mo_data in rm_hierarchy.items():
        odcs = mo_data["odcs"]
        if isinstance(odcs, list) and odc_name in odcs:
            return mo_code, str(mo_data["name"])
    return "????", "Sconosciuto"


def load_odc_from_xlsx(xlsx_path: Path, rm: str) -> list[OdCDescription]:
    """Carica le descrizioni OdC da un file Excel (colonna D = riscrittura, fallback C)."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["Sheet1"]
    odcs: list[OdCDescription] = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        name = str(row[0]).strip() if row[0] else ""
        if not name:
            continue

        desc = str(row[3]).strip() if row[3] else ""
        if not desc:
            desc = str(row[2]).strip() if row[2] else ""

        mo_code, mo_name = _find_mo_for_odc(rm, name)
        odcs.append(
            OdCDescription(
                code=ODC_CODES.get(name, "????"),
                name=name,
                rm=rm,
                mo_code=mo_code,
                mo_name=mo_name,
                original_description=desc,
            )
        )

    wb.close()
    return odcs


# LLM passes --------------------------------------------------------------


def optimize_odc_descriptions(
    odcs: list[OdCDescription],
    layer: Layer,
    model: str,
) -> list[OdCDescription]:
    """Riformula le descrizioni OdC via LLM."""
    logger.info("Ottimizzazione %d OdC con modello=%s...", len(odcs), model)

    for i, odc in enumerate(odcs, 1):
        siblings = [o for o in odcs if o.mo_code == odc.mo_code and o.name != odc.name]
        sibling_text = (
            "\n".join(f"- **{s.name}**: {s.original_description[:200]}..." for s in siblings)
            if siblings
            else "(nessun altro OdC nello stesso MO)"
        )
        user_msg = USER_PROMPT_ODC_TEMPLATE.format(
            odc_name=odc.name,
            rm=odc.rm,
            mo_code=odc.mo_code,
            mo_name=odc.mo_name,
            original_description=odc.original_description,
            sibling_odcs=sibling_text,
        )

        logger.info("  [%d/%d] Ottimizzando: %s...", i, len(odcs), odc.name)
        try:
            result = call_llm(
                layer=layer,
                system_prompt=SYSTEM_PROMPT_ODC,
                user_message=user_msg,
                response_format=OptimizedDescription,
                max_tokens=MAX_COMPLETION_TOKENS,
                model=model,
            )
            odc.optimized_description = result.optimized_description
            logger.info("    OK: %d → %d chars", len(odc.original_description), len(odc.optimized_description))
        except RuntimeError:
            odc.optimized_description = odc.original_description
            logger.warning("    FALLITO: uso descrizione originale")

    return odcs


def generate_mo_descriptions(
    odcs: list[OdCDescription],
    layer: Layer,
    model: str,
) -> list[MODescription]:
    """Genera descrizioni sintetiche per i MO a partire dagli OdC."""
    mos: list[MODescription] = []
    for rm, rm_mos in HIERARCHY.items():
        for mo_code, mo_data in rm_mos.items():
            mo_odcs = [o for o in odcs if o.mo_code == mo_code and o.rm == rm]
            mos.append(
                MODescription(
                    code=mo_code,
                    name=str(mo_data["name"]),
                    rm=rm,
                    odc_codes=[o.code for o in mo_odcs],
                )
            )

    logger.info("Generazione descrizioni per %d MO...", len(mos))

    for i, mo in enumerate(mos, 1):
        mo_odcs = [o for o in odcs if o.mo_code == mo.code and o.rm == mo.rm]
        odc_desc_text = "\n\n".join(
            f"#### {o.name} ({o.code})\n{o.optimized_description or o.original_description}" for o in mo_odcs
        )
        sibling_mos = [m for m in mos if m.rm == mo.rm and m.code != mo.code]
        sibling_text = (
            "\n".join(f"- **{s.code} - {s.name}**" for s in sibling_mos) if sibling_mos else "(unico MO in questo RM)"
        )
        user_msg = USER_PROMPT_MO_TEMPLATE.format(
            mo_code=mo.code,
            mo_name=mo.name,
            rm=mo.rm,
            odc_descriptions=odc_desc_text,
            sibling_mos=sibling_text,
        )

        logger.info("  [%d/%d] Generando: %s...", i, len(mos), mo.name)
        try:
            result = call_llm(
                layer=layer,
                system_prompt=SYSTEM_PROMPT_MO,
                user_message=user_msg,
                response_format=MOSyntheticDescription,
                max_tokens=MAX_COMPLETION_TOKENS,
                model=model,
            )
            mo.description = result.description
            logger.info("    OK: %d chars", len(mo.description))
        except RuntimeError:
            mo.description = f"Il {mo.name} copre i seguenti ambiti: " + ", ".join(o.name for o in mo_odcs) + "."
            logger.warning("    FALLITO: uso descrizione fallback")

    return mos


# Salvataggio -------------------------------------------------------------


def save_odc_descriptions(odcs: list[OdCDescription], path: Path = ODC_DESCRIPTIONS_JSON) -> None:
    path.write_text(json.dumps([asdict(o) for o in odcs], ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Salvato %d OdC in %s", len(odcs), path)


def save_mo_descriptions(mos: list[MODescription], path: Path = MO_DESCRIPTIONS_JSON) -> None:
    path.write_text(json.dumps([asdict(m) for m in mos], ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Salvato %d MO in %s", len(mos), path)


def save_hierarchy(
    odcs: list[OdCDescription],
    mos: list[MODescription],
    path: Path = _HIERARCHY_OUT,
) -> None:
    """Salva la gerarchia completa RM → MO → OdC in un unico JSON strutturato."""
    hierarchy: dict[str, dict[str, dict[str, object]]] = {}
    for rm, rm_mos in HIERARCHY.items():
        rm_data: dict[str, dict[str, object]] = {"mos": {}}
        for mo_code, mo_info in rm_mos.items():
            mo_obj = next((m for m in mos if m.code == mo_code and m.rm == rm), None)
            mo_odcs = [o for o in odcs if o.mo_code == mo_code and o.rm == rm]
            rm_data["mos"][mo_code] = {
                "name": mo_info["name"],
                "description": mo_obj.description if mo_obj else "",
                "odcs": {
                    o.code: {
                        "name": o.name,
                        "description": o.optimized_description or o.original_description,
                    }
                    for o in mo_odcs
                },
            }
        hierarchy[rm] = rm_data

    path.write_text(json.dumps(hierarchy, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Salvata gerarchia completa in %s", path)


# Orchestrator + CLI ------------------------------------------------------


def run(model: str = MODEL) -> None:
    """Carica → ottimizza → genera → salva."""
    logger.info("Caricamento OdC da Excel...")
    odcs_credito = load_odc_from_xlsx(ODC_CREDITO_XLSX, "Credito")
    odcs_aml = load_odc_from_xlsx(ODC_AML_XLSX, "AML")
    all_odcs = odcs_credito + odcs_aml
    logger.info("  Caricati %d Credito + %d AML = %d totali", len(odcs_credito), len(odcs_aml), len(all_odcs))

    unmapped = [o for o in all_odcs if o.mo_code == "????"]
    if unmapped:
        logger.error("OdC senza MO assegnato: %s", [o.name for o in unmapped])
        return

    layer = init_genfactory(
        env_file=str(ENV_FILE),
        use_case_id=USE_CASE_ID,
        timeout=httpx.Timeout(_HTTP_TIMEOUT_S),
    )

    all_odcs = optimize_odc_descriptions(all_odcs, layer, model)
    mos = generate_mo_descriptions(all_odcs, layer, model)

    save_odc_descriptions(all_odcs)
    save_mo_descriptions(mos)
    save_hierarchy(all_odcs, mos)
    logger.info("\nProcesso completato.")


@click.command(help="Ottimizza descrizioni OdC e genera MO per il tagging.")
@click.option("--model", type=str, default=MODEL, show_default=True)
def main(model: str) -> None:
    setup_logging(__name__)
    run(model=model)


if __name__ == "__main__":
    main()
