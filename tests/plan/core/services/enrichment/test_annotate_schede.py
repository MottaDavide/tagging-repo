"""Test `core.services.enrichment.annotate_schede`."""

import json
from pathlib import Path

import pytest

from core.services.enrichment.annotate_schede import (
    annotate_document,
    enrich_md,
    load_mapping,
    run_batch,
)

_ENTRY = {"Risk Model": "Credito", "mo": "2578 MO Concessione", "odc": "4601 Istruttoria"}
_MARKER = "«RM[Credito] | MO[2578 MO Concessione] | ODC[4601 Istruttoria]»"


class TestEnrichMd:
    def test_short_key_annotation(self) -> None:
        mapping = {"B11.1acc - Controllo": _ENTRY}
        out = enrich_md("Verifica B11 e B11.1acc nel testo.", mapping)
        assert f"B11 {_MARKER}" in out
        assert f"B11.1acc {_MARKER}" in out

    def test_no_double_annotation(self) -> None:
        mapping = {"B11 - Controllo": _ENTRY}
        once = enrich_md("Riferimento B11 nel testo.", mapping)
        twice = enrich_md(once, mapping)
        assert once.count(_MARKER) == 1
        assert twice.count(_MARKER) == 1

    def test_long_key_whitespace_flexible(self) -> None:
        entry = {"Risk Model": "AML", "mo": "MO-A", "odc": "ODC-AML"}
        mapping = {"Controllo antiriciclaggio periodico": entry}
        out = enrich_md("Controllo\nantiriciclaggio\tperiodico eseguito.", mapping)
        assert "«RM[AML] | MO[MO-A] | ODC[ODC-AML]»" in out


class TestLoadMapping:
    def test_filters_non_dict_and_empty_entries(self, tmp_path: Path) -> None:
        schede = tmp_path / "schede.json"
        schede.write_text(
            json.dumps(
                {
                    "K1": _ENTRY,
                    "K2": "valore-stringa-ignorato",
                    "K3": {"Risk Model": "", "mo": "", "odc": ""},
                }
            ),
            encoding="utf-8",
        )
        mapping = load_mapping(schede)
        assert set(mapping) == {"K1"}
        assert mapping["K1"]["Risk Model"] == "Credito"

    def test_raises_on_non_object_json(self, tmp_path: Path) -> None:
        schede = tmp_path / "schede.json"
        schede.write_text(json.dumps(["non", "un", "oggetto"]), encoding="utf-8")
        with pytest.raises(TypeError):
            load_mapping(schede)

    # def test_default_resource_is_versioned_and_loads(self) -> None:
    #     """La risorsa schede_tagged.json è versionata nel repo e ben formata."""
    #     assert SCHEDE_TAGGED_JSON.exists()
    #     mapping = load_mapping(SCHEDE_TAGGED_JSON)
    #     assert mapping, "mapping schede vuoto"
    #     sample = next(iter(mapping.values()))
    #     assert set(sample) == {"Risk Model", "mo", "odc"}


class TestAnnotateDocument:
    def test_annotate_document(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("Testo B01 da annotare.", encoding="utf-8")
        out = annotate_document(md, {"B01 - voce": _ENTRY})
        assert f"B01 {_MARKER}" in out


class TestRunBatch:
    def test_single_file_stem_fallback(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        (input_dir / "doc.md").write_text("B01 qui.", encoding="utf-8")

        schede = tmp_path / "schede.json"
        schede.write_text(json.dumps({"B01 - voce": _ENTRY}), encoding="utf-8")

        run_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            schede_path=schede,
            single_file="doc",
        )

        assert (output_dir / "doc.md").exists()
        assert _MARKER in (output_dir / "doc.md").read_text(encoding="utf-8")

    def test_in_place_processes_even_without_force(self, tmp_path: Path) -> None:
        in_out = tmp_path / "docs"
        in_out.mkdir()
        md_path = in_out / "doc.md"
        md_path.write_text("B01 qui.", encoding="utf-8")

        schede = tmp_path / "schede.json"
        schede.write_text(json.dumps({"B01 - voce": _ENTRY}), encoding="utf-8")

        run_batch(
            input_dir=in_out,
            output_dir=in_out,
            schede_path=schede,
            force=False,
        )

        assert _MARKER in md_path.read_text(encoding="utf-8")
