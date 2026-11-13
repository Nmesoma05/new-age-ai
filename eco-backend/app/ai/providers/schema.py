"""Turn Pydantic models into JSON schemas both vendors accept in strict mode.

Both vendors' strict modes expect every object to set ``additionalProperties: false`` and list every property
in ``required``; optional values are expressed as a union with null. Validation keywords such as length or
range limits are not reliably supported in strict schemas, so they are moved into the description and
enforced afterwards by Pydantic, which always re-validates the model's output.

Anthropic documents explicit limits for strict schemas (checked 2026-11-10, platform.claude.com structured
outputs page): at most 20 strict tools per request, 24 optional parameters, 16 parameters using anyOf or type
arrays. ``schema_stats`` lets tests hold every agent and tool schema to those limits.
"""
from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

_DROP = {"minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "pattern",
         "minItems", "maxItems", "uniqueItems", "format", "default", "title", "examples", "multipleOf"}
_DESCRIBE = {"minLength": "min length", "maxLength": "max length", "minimum": "min", "maximum": "max",
             "minItems": "min items", "maxItems": "max items", "pattern": "pattern"}


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, list):
            return [resolve(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            target.update(extra)
            return resolve(target)
        out: dict[str, Any] = {}
        notes = [f"{_DESCRIBE[k]} {node[k]}" for k in _DESCRIBE if k in node]
        for k, v in node.items():
            if k in _DROP:
                continue
            if k in ("properties",):
                out[k] = {name: resolve(sub) for name, sub in v.items()}
            elif k in ("items", "anyOf", "allOf", "oneOf"):
                out[k] = resolve(v)
            else:
                out[k] = v
        if notes:
            out["description"] = (out.get("description", "") + f" ({'; '.join(notes)})").strip()
        if out.get("type") == "object" or "properties" in out:
            out["type"] = "object"
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}).keys())
        if "oneOf" in out:  # strict modes support anyOf; discriminated unions arrive as oneOf
            out["anyOf"] = out.pop("oneOf")
        if "anyOf" in out:
            # collapse Optional[scalar] to a type array, the form both vendors document
            opts = out["anyOf"]
            if len(opts) == 2 and {"type": "null"} in opts:
                other = next(o for o in opts if o != {"type": "null"})
                if set(other) <= {"type", "description", "enum"} and isinstance(other.get("type"), str):
                    out.pop("anyOf")
                    out["type"] = [other["type"], "null"]
                    if "enum" in other:
                        out["enum"] = [*other["enum"], None]
        return out

    return resolve(raw)


def schema_stats(schema: dict[str, Any]) -> dict[str, int]:
    """Count the constructs vendors limit: nullable/union parameters and total properties."""
    unions = props = 0

    def walk(node: Any) -> None:
        nonlocal unions, props
        if isinstance(node, list):
            for n in node:
                walk(n)
            return
        if not isinstance(node, dict):
            return
        if "anyOf" in node or isinstance(node.get("type"), list):
            unions += 1
        for sub in node.get("properties", {}).values():
            props += 1
            walk(sub)
        for k in ("items", "anyOf"):
            if k in node:
                walk(node[k])

    walk(schema)
    return {"unions": unions, "properties": props}
