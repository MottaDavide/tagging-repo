"""Test dataclass `core.models.tagging.candidates`."""

from __future__ import annotations

from core.models.tagging.candidates import BranoCandidate, EnteAppearance


class TestBranoCandidate:
    def test_minimal_construct(self) -> None:
        c = BranoCandidate(
            risk_model="AML",
            ente="Gruppo ISP",
            brano="testo",
            pagina="1",
            rationale="r",
        )
        assert c.rm_confidence is None
        assert c.mo is None
        assert c.odc is None

    def test_full_construct(self) -> None:
        c = BranoCandidate(
            risk_model="AML",
            ente="Gruppo ISP",
            brano="testo",
            pagina="1,2",
            rationale="r",
            rm_confidence="high",
            mo="8838 - MO",
            odc="5069 - OdC",
        )
        assert c.rm_confidence == "high"
        assert c.mo == "8838 - MO"
        assert c.odc == "5069 - OdC"

    def test_mutable(self) -> None:
        c = BranoCandidate(
            risk_model="AML",
            ente=None,
            brano="",
            pagina="",
            rationale="",
        )
        c.rm_confidence = "medium"
        c.mo = "X"
        assert c.rm_confidence == "medium"
        assert c.mo == "X"


class TestEnteAppearance:
    def test_construct(self) -> None:
        a = EnteAppearance(
            canonical="Gruppo ISP",
            pages=[1, 2, 3],
            n_mentions=5,
            first_page=1,
            in_cover=True,
            h1_headings=["Titolo"],
            h2_headings=[],
        )
        assert a.canonical == "Gruppo ISP"
        assert a.first_page == 1
        assert a.in_cover is True
