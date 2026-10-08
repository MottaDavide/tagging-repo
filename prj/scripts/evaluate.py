"""Entry point: calcola le metriche di tagging (precision/recall/F1) e genera l'Excel di sintesi."""

from pathlib import Path

import click

from core.config import TAGGED_DIR
from core.utils.logging import setup_logging
from evaluation.orchestrators.evaluation import (
    DEFAULT_DOCS_DIR,
    DEFAULT_GT,
    DEFAULT_OUTPUT,
    RM_FILTER,
    TIPO_VALUES,
    evaluate,
)
from evaluation.services.matcher import DEFAULT_THRESHOLD


@click.command(help="Valuta le performance del tagger (precision/recall/F1) e genera l'Excel di sintesi.")
@click.option("--tagged-dir", type=click.Path(path_type=Path, file_okay=False), default=TAGGED_DIR, show_default=True)
@click.option("--gt", type=click.Path(path_type=Path, dir_okay=False), default=DEFAULT_GT, show_default=True)
@click.option("--rm", "rm", multiple=True, default=tuple(sorted(RM_FILTER)), show_default=True, metavar="RM")
@click.option(
    "--tipo",
    "tipo",
    multiple=True,
    type=click.Choice(sorted(TIPO_VALUES)),
    metavar="TIPO",
    help="Filtra GT per 'Tipo Citazione' (text, table, image). Default: nessun filtro.",
)
@click.option(
    "--no-ente",
    "no_ente",
    is_flag=True,
    help="Disabilita il confronto sull'Ente: la n-upla diventa (Risk Model, MO, OdC).",
)
@click.option(
    "--threshold",
    "threshold",
    type=click.FloatRange(0.0, 1.0),
    default=DEFAULT_THRESHOLD,
    show_default=True,
    help="Soglia minima di overlap testuale tra citazione PRED e citazione GT per considerarle un match.",
)
@click.option(
    "--output",
    "output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_OUTPUT,
    show_default=True,
    help="Percorso dell'Excel di sintesi delle metriche.",
)
@click.option(
    "--docs-dir",
    "docs_dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DEFAULT_DOCS_DIR,
    show_default=True,
    help="Dir dei markdown, per risolvere l'id-tabella delle citazioni HTML legacy.",
)
def main(
    tagged_dir: Path,
    gt: Path,
    rm: tuple[str, ...],
    tipo: tuple[str, ...],
    no_ente: bool,
    threshold: float,
    output: Path,
    docs_dir: Path,
) -> None:
    setup_logging("evaluation.evaluator")
    evaluate(
        tagged_dir=tagged_dir,
        gt_file=gt,
        rm_filter=frozenset(rm),
        tipo_filter=frozenset(tipo),
        ignore_ente=no_ente,
        threshold=threshold,
        output=output,
        docs_dir=docs_dir,
    )


if __name__ == "__main__":
    main()
