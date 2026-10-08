from typing import Any

from pydantic import BaseModel, ConfigDict


def force_required_recursive(schema: dict[str, Any]) -> None:
    """Forza tutte le proprietà di ogni `object` schema in `required` (in-place)."""
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object" and "properties" in schema:
        schema["required"] = list(schema["properties"].keys())
        schema.setdefault("additionalProperties", False)
    for key in ("properties", "$defs", "definitions"):
        sub = schema.get(key)
        if isinstance(sub, dict):
            for v in sub.values():
                force_required_recursive(v)
    items = schema.get("items")
    if isinstance(items, dict):
        force_required_recursive(items)
    elif isinstance(items, list):
        for v in items:
            force_required_recursive(v)
    for combinator in ("anyOf", "oneOf", "allOf"):
        sub = schema.get(combinator)
        if isinstance(sub, list):
            for v in sub:
                force_required_recursive(v)


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    """Risolve un JSON-pointer locale (`#/$defs/Nome`) contro la radice dello schema."""
    node: dict[str, Any] = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def normalize_strict_schema(schema: Any, root: dict[str, Any] | None = None) -> None:
    """Rende lo schema compatibile con lo structured output Azure (in-place).

    Azure (strict) vieta i keyword fratelli accanto a un `$ref` (es. `description`,
    `default`): è il caso dei campi tipizzati con un `type` alias di `Literal`
    (`Confidence`, `TipoCitazione`), emessi da Pydantic come `$ref` a un `$defs`.
    Qui si inlina il `$ref` quando ha fratelli e si rimuovono i `default`
    (ininfluenti: ogni campo è già forzato `required`).
    """
    if root is None:
        root = schema
    if isinstance(schema, dict):
        if "$ref" in schema and len(schema) > 1:
            target = _resolve_ref(root, schema.pop("$ref"))
            for key, value in target.items():
                schema.setdefault(key, value)
        schema.pop("default", None)
        for value in schema.values():
            normalize_strict_schema(value, root)
    elif isinstance(schema, list):
        for value in schema:
            normalize_strict_schema(value, root)


class StrictModel(BaseModel):
    """Base class per i Pydantic model usati come `response_format` in `call_llm`."""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        schema = super().model_json_schema(*args, **kwargs)
        force_required_recursive(schema)
        normalize_strict_schema(schema)
        return schema
