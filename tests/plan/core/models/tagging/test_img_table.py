"""Test modelli Pydantic `core.models.tagging.img_table`."""

from __future__ import annotations

from core.models.tagging.img_table import FigureDescription, PageDescriptions, TableDescription


class TestFigureDescription:
    def test_construct(self) -> None:
        f = FigureDescription(
            figure_index_on_page=1,
            description="d",
            remove_as_layout=False,
            contains_chart=True,
            chart_type="bar_chart",
            reason="r",
        )
        assert f.figure_index_on_page == 1
        assert f.chart_type == "bar_chart"

    def test_chart_type_nullable(self) -> None:
        f = FigureDescription(
            figure_index_on_page=1,
            description="d",
            remove_as_layout=False,
            contains_chart=False,
            chart_type=None,
            reason="r",
        )
        assert f.chart_type is None


class TestTableDescription:
    def test_construct(self) -> None:
        t = TableDescription(
            table_index_on_page=1,
            description="d",
            contains_chart=False,
            chart_type=None,
        )
        assert t.table_index_on_page == 1


class TestPageDescriptions:
    def test_empty(self) -> None:
        p = PageDescriptions(figures=[], tables=[])
        assert p.figures == []
        assert p.tables == []

    def test_round_trip_json(self) -> None:
        p = PageDescriptions(
            figures=[
                FigureDescription(
                    figure_index_on_page=1,
                    description="d",
                    remove_as_layout=False,
                    contains_chart=True,
                    chart_type="bar_chart",
                    reason="r",
                )
            ],
            tables=[TableDescription(table_index_on_page=1, description="t", contains_chart=False, chart_type=None)],
        )
        s = p.model_dump_json()
        roundtrip = PageDescriptions.model_validate_json(s)
        assert len(roundtrip.figures) == 1
        assert len(roundtrip.tables) == 1
