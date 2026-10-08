"""Test `core.services.summary.grouping`."""

from __future__ import annotations

from core.models.tagging.output import OutputTag
from core.services.summary.grouping import group_unique_tags


def _tag(
    rm: str,
    mo: str,
    odc: str,
    ente: str,
    pagina: str,
    citazione: str,
    table_content: str | None = None,
) -> OutputTag:
    return OutputTag(
        risk_model=rm,
        rm_confidence="high",
        mo=mo,
        mo_confidence="high",
        odc=odc,
        odc_confidence="high",
        ente=ente,
        pagina=pagina,
        citazione=citazione,
        tipo_citazione="table" if table_content else "text",
        table_content=table_content,
    )


class TestGroupUniqueTags:
    def test_empty(self) -> None:
        assert group_unique_tags([]) == []

    def test_groups_by_full_key(self) -> None:
        tags = [
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "c1"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "2", "c2"),  # stessa chiave
            _tag("Credito", "2503 - MO", "5049 - OdC", "E2", "3", "c3"),  # ente diverso
        ]
        result = group_unique_tags(tags)
        assert len(result) == 2
        first = result[0]
        assert (first.risk_model, first.mo, first.odc, first.ente) == ("Credito", "2503 - MO", "5049 - OdC", "E1")
        assert len(first.occorrenze) == 2
        assert result[1].ente == "E2"

    def test_preserves_first_appearance_order(self) -> None:
        tags = [
            _tag("AML", "8838 - MO", "1 - O", "Z", "1", "c"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "A", "1", "c"),
        ]
        result = group_unique_tags(tags)
        assert [r.risk_model for r in result] == ["AML", "Credito"]

    def test_dedup_identical_occorrenze(self) -> None:
        tags = [
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "stessa"),
            _tag("Credito", "2503 - MO", "5049 - OdC", "E1", "1", "stessa"),  # duplicato esatto
        ]
        result = group_unique_tags(tags)
        assert len(result) == 1
        assert len(result[0].occorrenze) == 1

    def test_carries_table_content_into_occorrenza(self) -> None:
        html = "<table><tr><td>x</td></tr></table>"
        tags = [_tag("Credito", "2503 - MO", "5049 - OdC", "E1", "3", "Tabella a pagina 3", table_content=html)]
        result = group_unique_tags(tags)
        assert result[0].occorrenze[0].table_content == html

    def test_distinct_tables_same_page_and_label_not_merged(self) -> None:
        # Due tabelle diverse sulla stessa pagina condividono l'etichetta breve ma non il contenuto.
        tags = [
            _tag(
                "Credito", "2503 - MO", "5049 - OdC", "E1", "3", "Tabella a pagina 3", table_content="<table>A</table>"
            ),
            _tag(
                "Credito", "2503 - MO", "5049 - OdC", "E1", "3", "Tabella a pagina 3", table_content="<table>B</table>"
            ),
        ]
        result = group_unique_tags(tags)
        assert len(result) == 1
        assert len(result[0].occorrenze) == 2
