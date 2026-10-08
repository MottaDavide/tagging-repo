"""Test `core.models.strict`: StrictModel + force_required_recursive."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from core.models.strict import StrictModel, force_required_recursive, normalize_strict_schema

type _Conf = Literal["high", "low"]


class TestForceRequiredRecursive:
    def test_simple_object(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        }
        force_required_recursive(schema)
        assert set(schema["required"]) == {"a", "b"}
        assert schema["additionalProperties"] is False

    def test_nested_object(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "outer": {
                    "type": "object",
                    "properties": {"inner": {"type": "string"}},
                }
            },
        }
        force_required_recursive(schema)
        assert schema["properties"]["outer"]["required"] == ["inner"]

    def test_array_of_objects(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"x": {"type": "integer"}}},
                }
            },
        }
        force_required_recursive(schema)
        assert schema["properties"]["items"]["items"]["required"] == ["x"]

    def test_defs_section(self) -> None:
        schema: dict[str, Any] = {"$defs": {"Foo": {"type": "object", "properties": {"x": {"type": "integer"}}}}}
        force_required_recursive(schema)
        assert schema["$defs"]["Foo"]["required"] == ["x"]

    def test_anyof_oneof_allof(self) -> None:
        schema: dict[str, Any] = {"anyOf": [{"type": "object", "properties": {"x": {"type": "integer"}}}]}
        force_required_recursive(schema)
        assert schema["anyOf"][0]["required"] == ["x"]

    def test_non_dict_input_no_error(self) -> None:
        force_required_recursive([])  # type: ignore[arg-type]


class TestNormalizeStrictSchema:
    def test_inlines_ref_with_siblings(self) -> None:
        schema: dict[str, Any] = {
            "$defs": {"Conf": {"enum": ["high", "low"], "type": "string"}},
            "properties": {"c": {"$ref": "#/$defs/Conf", "description": "d"}},
        }
        normalize_strict_schema(schema)
        c = schema["properties"]["c"]
        assert "$ref" not in c
        assert c["enum"] == ["high", "low"]
        assert c["description"] == "d"

    def test_leaves_bare_ref_untouched(self) -> None:
        schema: dict[str, Any] = {
            "$defs": {"Conf": {"enum": ["high"], "type": "string"}},
            "properties": {"c": {"$ref": "#/$defs/Conf"}},
        }
        normalize_strict_schema(schema)
        assert schema["properties"]["c"] == {"$ref": "#/$defs/Conf"}

    def test_strips_default(self) -> None:
        schema: dict[str, Any] = {"properties": {"c": {"type": "string", "default": "x"}}}
        normalize_strict_schema(schema)
        assert "default" not in schema["properties"]["c"]

    def test_strict_model_with_literal_alias_has_no_ref_siblings(self) -> None:
        class M(StrictModel):
            conf: _Conf = Field(default="high", description="livello")

        schema = M.model_json_schema()

        def walk(node: Any) -> bool:
            if isinstance(node, dict):
                if "$ref" in node and len(node) > 1:
                    return False
                if "default" in node:
                    return False
                return all(walk(v) for v in node.values())
            if isinstance(node, list):
                return all(walk(v) for v in node)
            return True

        assert walk(schema)


class TestStrictModel:
    def test_extra_forbidden(self) -> None:
        class M(StrictModel):
            a: int = 0

        # Pydantic v2 ConfigDict(extra="forbid") deve essere ereditato.
        assert M.model_config["extra"] == "forbid"

    def test_schema_marks_all_required(self) -> None:
        class M(StrictModel):
            a: int = 0
            b: str = ""

        schema = M.model_json_schema()
        assert set(schema.get("required", [])) == {"a", "b"}
        assert schema.get("additionalProperties") is False

    def test_nested_strict_models_in_schema(self) -> None:
        class Inner(StrictModel):
            x: int = 0

        class Outer(StrictModel):
            inner: Inner = Field(default_factory=Inner)

        schema = Outer.model_json_schema()
        # Lo schema dovrebbe richiedere `inner` come required
        assert "inner" in schema.get("required", [])
