.PHONY: help \
        sync sync-check requirements \
        fix format lint types test \
        check all precommit

# `uv run --no-sync`: esegue i tool dal venv del progetto (.venv/bin) COM'È, senza
# ri-sincronizzare con uv.lock a ogni comando. Così i target di verifica e gli hook
# git (che li invocano) girano anche offline, senza contattare l'indice Artifactory,
# e usano sempre ruff/mypy/pytest del venv — mai binari globali dal PATH.
# L'ambiente si aggiorna SOLO con `make sync` (unico target che scarica dall'indice).
UV_RUN  = uv run --no-sync
PY_SRC  = prj/app prj/scripts prj/evaluation
PY_TEST = tests/plan/core tests/evaluation

# ─── dipendenze ──────────────────────────────────────────────────────────────
sync:  ## aggiorna venv e uv.lock da pyproject.toml
	uv sync

sync-check:  ## verifica che uv.lock sia coerente con pyproject.toml (no side-effect)
	uv lock --check

requirements: sync  ## esporta requirements.txt da uv.lock (no dev, no hashes, no editable)
	uv export \
		--format requirements-txt \
		--no-dev \
		--no-hashes \
		--no-editable \
		--output-file requirements.txt
	@echo "requirements.txt aggiornato"

# ─── verify (read-only, fail se non passa) ───────────────────────────────────
format:  ## verifica ruff format (no fix)
	$(UV_RUN) ruff format --check $(PY_SRC) $(PY_TEST)

lint:  ## verifica ruff check (no fix)
	$(UV_RUN) ruff check --no-fix $(PY_SRC) $(PY_TEST)

types:  ## verifica mypy (solo codice di produzione: i test usano mocker non tipato)
	$(UV_RUN) mypy $(PY_SRC)

test:  ## esegue pytest con coverage (sorgente --cov=prj/app e gate 85% definiti in pyproject)
	$(UV_RUN) pytest $(PY_TEST)

# ─── auto-fix (modifica i file) ──────────────────────────────────────────────
fix:  ## applica ruff format + ruff check --fix (modifica i file)
	$(UV_RUN) ruff format $(PY_SRC) $(PY_TEST)
	$(UV_RUN) ruff check --fix $(PY_SRC) $(PY_TEST)

# ─── orchestratori ───────────────────────────────────────────────────────────
# Sequenza fail-fast: costo crescente, fix di ognuno è progressivamente più caro.
#   sync-check (istantaneo) → format (ms) → lint (s) → types (decine di s)
check: sync-check format lint types  ## verifica statica completa, fail-fast (NO test)

all: check test  ## check + test = "sicuro per push"

precommit:  ## esegue tutti gli hook git (debug); riprova una volta per i fixer che modificano file
	$(UV_RUN) pre-commit run --all-files || $(UV_RUN) pre-commit run --all-files

# ─── help ────────────────────────────────────────────────────────────────────
help:  ## mostra questo messaggio
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
