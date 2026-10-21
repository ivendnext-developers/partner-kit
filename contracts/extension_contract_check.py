# Source: ivendnext/iVendNext_PWA apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contract_check.py @ 7d47d331a203, copied unchanged: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board.
# Copyright (c) 2026, CitiXsys Technologies and contributors
# For license information, please see license.txt
"""The extension-point library's schema checker (lane ``lib1``), kept free of fixtures so any suite
that captures a real press's body can check it against the published contract
(``request_errors``) without importing another suite.

⚠ ``jsonschema`` is not installed on the bench and is no dependency of the app, so this checks the
draft 2020-12 keywords the contracts use. ``test_extension_contracts`` refuses a contract that uses
any other keyword, so none is silently skipped."""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent / "extension_contracts"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
KEYWORDS = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "const", "enum"}
KEYWORDS |= {"minLength", "maxLength", "pattern", "minimum", "maximum", "items", "minItems"}
KEYWORDS |= {"maxItems", "properties", "required", "additionalProperties", "minProperties"}
KEYWORDS |= {"allOf", "anyOf", "oneOf", "not"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _load(path) -> dict:
    return json.loads(pathlib.Path(path).read_text())


def _schema(point: str) -> dict:
    return _load(ROOT / f"{point}.v1.schema.json")


# ── the checker: the draft 2020-12 subset the contracts use ────────────────


def _resolve(ref: str, root: dict) -> tuple[dict, dict]:
    file, _, pointer = ref.partition("#")
    doc = _load(ROOT / file) if file else root
    node = doc
    for part in filter(None, pointer.split("/")):
        node = node[part]
    return node, doc


def _is(value, kind: str) -> bool:
    if kind in ("integer", "number") and isinstance(value, bool):
        return False
    if kind == "integer":
        return isinstance(value, int)
    if kind == "number":
        return isinstance(value, (int, float))
    return isinstance(value, TYPES[kind])


def _eq(a, b) -> bool:
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _errors(schema: dict, value, root: dict, at: str = "$") -> list[str]:
    out = []
    if "$ref" in schema:
        node, doc = _resolve(schema["$ref"], root)
        out += _errors(node, value, doc, at)
    if "type" in schema and not _is(value, schema["type"]):
        return [*out, f"{at}: not {schema['type']}"]
    if "const" in schema and not _eq(value, schema["const"]):
        out.append(f"{at}: not {schema['const']!r}")
    if "enum" in schema and not any(_eq(value, e) for e in schema["enum"]):
        out.append(f"{at}: not one of {schema['enum']}")
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", len(value)):
            out.append(f"{at}: {len(value)} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{at}: does not match {schema['pattern']}")
    if _is(value, "number") and not schema.get("minimum", value) <= value <= schema.get(
        "maximum", value
    ):
        out.append(f"{at}: {value} is out of range")
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", len(value)):
            out.append(f"{at}: {len(value)} items")
        for i, item in enumerate(value if "items" in schema else []):
            out += _errors(schema["items"], item, root, f"{at}[{i}]")
    if isinstance(value, dict):
        out += [f"{at}.{k}: missing" for k in schema.get("required", []) if k not in value]
        if len(value) < schema.get("minProperties", 0):
            out.append(f"{at}: too few properties")
        props, extra = schema.get("properties", {}), schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                out += _errors(props[k], v, root, f"{at}.{k}")
            elif extra is False:
                out.append(f"{at}.{k}: not allowed")
            elif isinstance(extra, dict):
                out += _errors(extra, v, root, f"{at}.{k}")
    for sub in schema.get("allOf", []):
        out += _errors(sub, value, root, at)
    if "anyOf" in schema and all(_errors(s, value, root, at) for s in schema["anyOf"]):
        out.append(f"{at}: matches no anyOf branch")
    if "oneOf" in schema and sum(not _errors(s, value, root, at) for s in schema["oneOf"]) != 1:
        out.append(f"{at}: does not match exactly one oneOf branch")
    if "not" in schema and not _errors(schema["not"], value, root, at):
        out.append(f"{at}: matches what it must not")
    return out


def request_errors(point: str, body: dict) -> list[str]:
    """A real press's body against the published request — for the suites that capture one
    (``test_desk_action``, ``test_app_button_remote``)."""
    schema = _schema(point)
    return _errors(schema["$defs"]["request"], body, schema)
