# cao-fac-tagging

Server API FastAPI per il tagging di contenuti tramite modelli LLM, sviluppato all'interno del BIG DATA LAB (BDL).

---

## Indice

- [Struttura del progetto](#struttura-del-progetto)
- [Gestione del virtual environment e delle dipendenze con UV](#gestione-del-virtual-environment-e-delle-dipendenze-con-uv)
- [Avvio in locale](#avvio-in-locale)
- [Sviluppo dell'applicazione](#sviluppo-dellapplicazione)
- [Code quality](#code-quality)
- [Makefile](#makefile)
- [Pre-commit hooks](#pre-commit-hooks)

---

## Struttura del progetto

```text
.
├── isp-config-env/                  # configurazioni per ambiente PAAS (svil, svis, test, ptes, prod)
│
├── prj/
│   ├── app/                         # applicazione FastAPI (import come `core.*` e `api.*`)
│   │   ├── main.py                  # entry point FastAPI + init genfactory
│   │   ├── api/
│   │   │   ├── exceptionhandlers/   # gestione centralizzata degli errori HTTP
│   │   │   └── routers/v1/
│   │   │       └── endpoints.py     # endpoint applicativi (POST /tagging)
│   │   ├── config/                  # .yaml applicativi (llm.yaml, tagging.yaml, app.yaml) + JSON dati statici
│   │   └── core/
│   │       ├── config.py            # unica fonte di verità per i path (derivati da DATA_DIR)
│   │       ├── models/              # modelli Pydantic (registry, tagging, entities, summary)
│   │       ├── services/            # building block: parsing, enrichment, tagging, text, registry, llm_client
│   │       ├── resources/           # system prompt LLM + builder di prompt
│   │       ├── orchestrators/       # composizione dei service in flussi (tag_document, summarize_document, ...)
│   │       └── utils/               # logging, ack
│   ├── evaluation/                  # package offline di valutazione (import come `evaluation.*`)
│   ├── scripts/                     # CLI click (pipeline.py orchestratore, optimize_odc.py, ...)
│   ├── config/
│   │   ├── gunicorn_conf.py         # config gunicorn (produzione)
│   │   └── uvicorn_conf.yaml        # config logging uvicorn
│   ├── static/                      # asset Swagger UI
│   ├── start.sh                     # avvio in produzione (gunicorn)
│   └── start_dev.sh                 # avvio in sviluppo (uvicorn con hot-reload)
│
├── tests/
│   ├── plan/core/                   # test del package app (coverage-gated: ≥ 85%)
│   └── evaluation/                  # test del package evaluation
│
├── data/                            # dati locali (default di DATA_DIR, override con TAGGING_DATA_DIR)
├── docs/                            # documentazione aggiuntiva
├── tools/                           # script di supporto
├── pyproject.toml                   # sorgente di verità per dipendenze e configurazione tool
├── uv.lock                          # lock file generato da UV (versionato)
├── requirements.txt                 # generato da uv.lock per gli ambienti di deploy
├── Makefile                         # shortcut per i comandi di sviluppo
└── .pre-commit-config.yaml          # hook di qualità automatici su commit e push
```

---

## Gestione del virtual environment e delle dipendenze con UV

Il progetto usa [**UV**](https://docs.astral.sh/uv/) come gestore di pacchetti e virtual environment.
UV è un sostituto veloce di `pip` + `venv` + `pip-tools`, scritto in Rust.

### Installazione di UV

Fare riferimento alla [documentazione ufficiale di UV](https://docs.astral.sh/uv/getting-started/installation/) per l'installazione.

Il metodo consigliato è tramite lo script ufficiale:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verificare l'installazione:

```bash
uv --version
```

### Variabili d'ambiente per l'indice privato

Il progetto scarica le dipendenze da un registro Artifactory privato (configurato in `pyproject.toml` sotto `[[tool.uv.index]]`).
UV legge le credenziali tramite variabili d'ambiente con il nome dell'indice come suffisso:

```bash
export UV_INDEX_ARTIFACTORY_USERNAME=snapshot-deployer
export UV_INDEX_ARTIFACTORY_PASSWORD=snapshot
```

Senza queste variabili, `uv sync` e `uv add` falliscono quindi è necessario settarle nel proprio file `.env`.

### Configurazione del virtual environment

UV gestisce automaticamente il virtual environment leggendo `pyproject.toml`.
Per creare il venv e installare tutte le dipendenze (produzione + sviluppo):

```bash
uv sync
```

Il venv viene creato in `.venv/` nella root del progetto. Non è necessario attivarlo esplicitamente: tutti i comandi si eseguono tramite `uv run <comando>` oppure attivando il venv manualmente:

```bash
source .venv/bin/activate   # macOS / Linux
.venv\Scripts\activate      # Windows
```

### Gestione delle dipendenze

Le dipendenze sono definite in `pyproject.toml` in due sezioni:

| Sezione | Scopo |
| --- | --- |
| `[project].dependencies` | dipendenze di produzione (gunicorn, uvicorn, bdlpkg-core, …) |
| `[dependency-groups].dev` | dipendenze di sviluppo (pytest, ruff, mypy, pre-commit, …) |

**Aggiungere una dipendenza di produzione:**

```bash
uv add <pacchetto>
```

**Aggiungere una dipendenza di sviluppo:**

```bash
uv add --group dev <pacchetto>
```

**Rimuovere una dipendenza:**

```bash
uv remove <pacchetto>
```

Questi comandi aggiornano automaticamente `pyproject.toml` e rigenerano `uv.lock`.

> Per la documentazione completa sui comandi UV: [Managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/)

### Flusso di lavoro con le dipendenze

```text
pyproject.toml  ──(uv sync)──▶  uv.lock  ──(make requirements)──▶  requirements.txt
  [modificato                   [versionato,                         [usato dal deploy,
   dal dev]                      fonte di verità]                     non modificare a mano]
```

1. Modifica le dipendenze in `pyproject.toml` (direttamente o con `uv add`/`uv remove`)
2. Esegui `uv sync` per aggiornare il venv e rigenera `uv.lock`
3. Esegui `make requirements` per rigenerare `requirements.txt` con le versioni pinnate da `uv.lock`
4. Committa sia `pyproject.toml` che `uv.lock` (e `requirements.txt` se aggiornato)

### Generazione di requirements.txt

Il file `requirements.txt` è **generato automaticamente** da `uv.lock` e non va mai modificato a mano.
Contiene le versioni pinnate di tutte le dipendenze transitive, pronte per il deploy:

```bash
make requirements
# oppure direttamente:
uv export --format requirements-txt --no-dev --no-hashes --no-editable --output-file requirements.txt
```

---

## Avvio in locale

```bash
# sviluppo — uvicorn (imposta APP_CONF_DIR, DS_CONF_DIR, MY_HOME)
PORT=9999 ./prj/start_dev.sh
```

`start_dev.sh` deriva la porta dallo username (`PORT=${PORT:-...}`): per una porta fissa passala esplicitamente come sopra.

> `prj/start.sh` (gunicorn) è pensato per l'**ambiente PAAS**: si aspetta la struttura di `VIRTUAL_ENV` del deploy e le env var `ARTIFACT_URL`/`BDL_APP_NAME`, quindi non gira così com'è in locale.

Una volta avviata (con `PORT=9999`), l'applicazione è disponibile su:

- **Swagger UI**: [http://localhost:9999/docs](http://localhost:9999/docs)
- **OpenAPI JSON**: [http://localhost:9999/openapi.json](http://localhost:9999/openapi.json)

---

## Sviluppo dell'applicazione

### Aggiungere un endpoint

Il router principale è `prj/app/api/routers/v1/endpoints.py`. Per aggiungere endpoint:

```python
from fastapi.routing import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(default_response_class=JSONResponse)

@router.get("/esempio")
async def esempio() -> dict:
    return {"messaggio": "ok"}
```

Per organizzare gli endpoint in più router, creare un nuovo file in `api/routers/v1/` e registrarlo in `api/routers/v1/__init__.py`:

```python
from . import nuovo_router

def _build_router() -> APIRouter:
    ...
    rt.include_router(nuovo_router.router, prefix="/prefisso")
    ...
    return rt
```

### Configurazione applicativa

I parametri applicativi sono definiti in file `.yaml` nella cartella `prj/app/config/`.
Per leggerli nel codice:

```python
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

app_configs = get_obj_from_config_path("app.yaml")
```

---

## Code quality

Il progetto usa tre strumenti complementari per garantire la qualità del codice.
Tutti e tre sono configurati in `pyproject.toml` (sezioni `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`).

### ruff — formattazione e analisi statica

[Ruff](https://docs.astral.sh/ruff/) svolge due ruoli distinti:

> Il modo consigliato di eseguire questi controlli è tramite i target `make` (vedi [Makefile](#makefile)):
> `make fix` per correggere, `make check` per verificare in sola lettura. I comandi `uv run` qui sotto sono l'equivalente diretto.

**Formattazione** — garantisce uno stile uniforme (equivalente a `black`):

```bash
uv run ruff format prj/app prj/scripts prj/evaluation tests/plan/core tests/evaluation          # formatta i file (make fix)
uv run ruff format --check prj/app prj/scripts prj/evaluation tests/plan/core tests/evaluation   # solo verifica (make format)
```

**Linting** — analisi statica con oltre 800 regole (pyflakes, pycodestyle, bugbear, bandit, isort, …):

```bash
uv run ruff check --fix prj/app prj/scripts prj/evaluation tests/plan/core tests/evaluation      # analizza e auto-corregge (make fix)
uv run ruff check --no-fix prj/app prj/scripts prj/evaluation tests/plan/core tests/evaluation   # solo verifica (make lint)
```

Le regole attive sono configurate in `[tool.ruff.lint].select` nel `pyproject.toml` e coprono:

- correttezza logica (pyflakes, bugbear)
- stile PEP8 (pycodestyle)
- ordinamento import (isort)
- naming convention (pep8-naming)
- sicurezza (bandit)
- best practice async per FastAPI
- logging corretto
- type annotation complete
- gestione eccezioni
- datetime timezone-aware

### mypy — type checking

[mypy](https://mypy.readthedocs.io/) verifica la correttezza dei tipi statici sul codice di produzione (i test usano mocker non tipato):

```bash
uv run mypy prj/app prj/scripts prj/evaluation   # make types
```

La configurazione in `[tool.mypy]` impone annotazioni complete su tutte le funzioni, vieta generici non parametrizzati (`List` → `List[str]`) e usa il plugin Pydantic per l'inferenza corretta sui modelli.

### pytest — test con coverage

[pytest](https://docs.pytest.org/) esegue la suite di test e misura la coverage:

```bash
uv run pytest        # oppure: make test
```

Per eseguire un **singolo test/file** durante lo sviluppo, disabilita la coverage con `--no-cov`: la gate `--cov-fail-under=85` è in `addopts`, quindi un run parziale fallirebbe (coverage sotto soglia) anche se il test passa:

```bash
uv run pytest tests/plan/core/services/tagging/test_tag_rm.py --no-cov
uv run pytest "tests/plan/core/services/tagging/test_tag_rm.py::TestTagRm::test_x" --no-cov
```

La configurazione in `[tool.pytest.ini_options]` imposta automaticamente:

- misurazione della coverage su `prj/app`
- report a terminale e in HTML (`htmlcov/`)
- fallimento della suite se la coverage scende sotto l'**85%**

Per visualizzare il report HTML dopo l'esecuzione:

```bash
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## Makefile

Il `Makefile` nella root è l'**interfaccia primaria** per lavorare sul progetto: ogni target incapsula il comando `uv` corretto (con i path sorgente/test giusti) e gli hook git corrispondono 1:1 ai target. Non serve ricordare i comandi `uv run ...` a mano.

I target di verifica e auto-fix usano `uv run --no-sync`: eseguono i tool del venv (`.venv/bin`, versioni da `uv.lock`) **senza** ri-sincronizzare l'ambiente a ogni comando, quindi girano anche **offline** e senza contattare Artifactory. L'ambiente si aggiorna solo con `make sync`, l'unico target che scarica dall'indice — eseguilo dopo aver modificato le dipendenze.

```bash
make          # mostra l'elenco dei target disponibili (default)
```

I target sono divisi in tre gruppi:

**Dipendenze**

| Target | Fa | Descrizione |
| --- | --- | --- |
| `make sync` | `uv sync` | crea/aggiorna il venv e rigenera `uv.lock` da `pyproject.toml` |
| `make sync-check` | `uv lock --check` | verifica che `uv.lock` sia coerente con `pyproject.toml` (no side-effect) |
| `make requirements` | `uv sync` + `uv export …` | rigenera `requirements.txt` da `uv.lock` (no dev, no hashes) |

**Verifica (sola lettura — falliscono se il codice non è a posto, non modificano nulla)**

| Target | Fa | Descrizione |
| --- | --- | --- |
| `make format` | `ruff format --check` | verifica la formattazione |
| `make lint` | `ruff check --no-fix` | analisi statica (~800 regole) |
| `make types` | `mypy` | type checking (solo codice di produzione) |
| `make test` | `pytest` | test con coverage (gate ≥ 85%) |

**Auto-fix e orchestratori**

| Target | Fa | Descrizione |
| --- | --- | --- |
| `make fix` | `ruff format` + `ruff check --fix` | **unico target che MODIFICA i file** — riformatta e auto-corregge |
| `make check` | `sync-check` → `format` → `lint` → `types` | verifica statica completa **fail-fast**, senza test |
| `make all` | `check` + `test` | verifica completa: "sicuro per push" |
| `make precommit` | `pre-commit run --all-files` | esegue tutti gli hook git (utile per debug) |

`make check` esegue i controlli in ordine di costo crescente (`sync-check` istantaneo → `format` ms → `lint` s → `types` decine di s) e si ferma al primo fallimento, così ottieni il feedback più economico per primo.

**Flusso tipico durante lo sviluppo:**

```bash
make fix      # riformatta e auto-corregge (l'unico che scrive)
make check    # verifica statica rapida prima di committare
make all      # verifica completa (check + test) prima di aprire una PR
```

> `make fix && make all` in locale garantisce che gli hook di `pre-commit` e `pre-push` passeranno: gli hook eseguono esattamente gli stessi controlli.

---

## Pre-commit hooks

Il progetto usa [pre-commit](https://pre-commit.com/) per eseguire automaticamente i controlli di qualità in due momenti distinti del flusso git.

Ogni hook locale **invoca il target `make` corrispondente** (`ruff-format` → `make format`, `mypy` → `make types`, ecc.): il Makefile è l'unica fonte di verità per path e comandi, quindi gli hook eseguono esattamente gli stessi controlli di `make check`/`make all`, usano i tool del venv via `uv run --no-sync` e girano anche offline.

### Installazione

Grazie a `default_install_hook_types` nel `.pre-commit-config.yaml`, un solo comando installa **entrambi** gli stage (`pre-commit` e `pre-push`):

```bash
uv run pre-commit install
```

### Hook configurati

#### Stage `pre-commit` — eseguito a ogni `git commit`

Controlli veloci (< 1s) che danno feedback immediato:

| Hook | Descrizione |
| --- | --- |
| `check-yaml` | valida la sintassi di tutti i file YAML |
| `check-toml` | valida la sintassi di `pyproject.toml` e altri TOML |
| `check-merge-conflict` | blocca commit con marker `<<<<<<<` rimasti nel codice |
| `end-of-file-fixer` | assicura che ogni file termini con un newline |
| `trailing-whitespace` | rimuove spazi bianchi a fine riga |
| `uv-lock-check` | verifica che `uv.lock` sia coerente con `pyproject.toml` (`make sync-check`) |
| `ruff-format --check` | verifica che il codice sia formattato (fallisce se non lo è — eseguire `make fix`) |

#### Stage `pre-push` — eseguito a ogni `git push`

Controlli più pesanti che validano l'intero codebase prima che il codice raggiunga il repository remoto:

| Hook | Descrizione |
| --- | --- |
| `ruff-lint --no-fix` | analisi statica completa (fallisce se ci sono violazioni — eseguire `make lint`) |
| `mypy` | type checking completo su `prj/app` |
| `pytest` | intera suite di test con coverage |

### Flusso completo

```bash
git commit  ──▶  check-yaml, check-toml, check-merge-conflict,
                 end-of-file-fixer, trailing-whitespace,
                 uv-lock-check, ruff-format --check

git push    ──▶  ruff-lint --no-fix
                 mypy
                 pytest
```

### Eseguire gli hook manualmente

```bash
uv run pre-commit run --all-files                        # tutti gli hook pre-commit
uv run pre-commit run --all-files --hook-stage pre-push  # tutti gli hook pre-push
```
