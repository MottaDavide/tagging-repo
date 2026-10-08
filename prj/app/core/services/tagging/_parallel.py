"""Utility condivise dagli stage paralleli del tagging (discover, classify).

`TAGGING_MAX_WORKERS` è il grado di parallelismo condiviso; `parallel_llm_map` esegue i task
LLM in un thread pool accumulando le statistiche di call/tempo su `TaggerStats`.
"""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

from core.models.tagging.stats import TaggerStats

# Numero di worker condiviso dagli stage paralleli (discovery, classify, ente).
TAGGING_MAX_WORKERS: int = get_obj_from_config_path("tagging.yaml")["classify"]["max_workers"]


def parallel_llm_map[K, V](
    tasks: Iterable[Callable[[], tuple[K, V, float]]],
    stats: TaggerStats,
    max_workers: int = TAGGING_MAX_WORKERS,
) -> dict[K, V]:
    """Esegue i `tasks` in parallelo e ritorna `{chiave: valore}` (ordine di completamento).

    Ogni task è un thunk che ritorna `(chiave, valore, elapsed)`: la chiave indicizza il
    risultato, `elapsed` alimenta `stats.llm_time_s` e ogni task completato incrementa
    `stats.llm_calls`. Nessun filtro sui valori: è il chiamante a decidere a valle cosa scartare.
    """
    results: dict[K, V] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(task) for task in tasks]
        for future in as_completed(futures):
            key, value, elapsed = future.result()
            stats.llm_calls += 1
            stats.llm_time_s += elapsed
            results[key] = value
    return results
