"""generate.py — builds the MCP server's tool list from the API description (``api/openapi.yaml``).

One tool per operation: its name is the operationId, its description the operation's summary, its input schema the
path and query parameters plus, for a write, the request body and a ``confirm`` flag. References are resolved inline,
so the server reads ``tools.json`` with the standard library alone. Re-run after every change to the description;
``tests/test_server.py`` fails if ``tools.json`` is stale.

    .venv/bin/python tools/mcp_server/generate.py            # needs PyYAML (the programme's .venv has it)
"""

import json
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SPEC = HERE.parents[1] / "api" / "openapi.yaml"
OUT = HERE / "tools.json"
WRITE = {"post", "put", "patch", "delete"}


def resolve(node, spec, depth=0):
    if depth > 20:
        raise ValueError("reference cycle")
    if isinstance(node, dict):
        if "$ref" in node:
            target = spec
            for part in node["$ref"].lstrip("#/").split("/"):
                target = target[part]
            return resolve(target, spec, depth + 1)
        return {k: resolve(v, spec, depth + 1) for k, v in node.items() if k not in ("example", "examples")}
    if isinstance(node, list):
        return [resolve(x, spec, depth + 1) for x in node]
    return node


def _title(op: dict, write: bool) -> str:
    """The name a client shows in its approval prompt. A write keeps its whole summary: what follows the dash says
    what the write does, and the person approving it must see that. A read keeps the part before its dash or example."""
    summary = (op.get("summary") or "").strip() or op["operationId"]
    return summary if write else summary.split(" — ")[0].split(" (e.g.")[0].strip() or op["operationId"]


def build(spec: dict) -> dict:
    tools = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            props, required, query, path_params = {}, [], [], []
            for p in resolve(op.get("parameters") or [], spec):
                schema = dict(p.get("schema") or {"type": "string"})
                if p.get("description"):
                    schema["description"] = p["description"]
                props[p["name"]] = schema
                (path_params if p["in"] == "path" else query).append(p["name"])
                if p.get("required"):
                    required.append(p["name"])
            body = op.get("requestBody")
            if body:
                schema = resolve(body["content"]["application/json"]["schema"], spec)
                props["body"] = dict(schema, description=schema.get("description") or "The record to send (JSON).")
                if body.get("required"):
                    required.append("body")
            write = method in WRITE
            if not write and "/method/" in path:
                # a GET that runs a document method is a write the verb hides (found by a deep review): never a read tool
                raise SystemExit(f"{op['operationId']}: a GET that runs a method cannot be a read-only tool")
            if write:
                props["confirm"] = {"type": "boolean", "description": "Set true only after the person has approved "
                                                                      "this exact write. Without it nothing is written "
                                                                      "and the call answers with a preview."}
            desc = op.get("summary", "")
            if op.get("description"):
                desc += "\n\n" + op["description"].strip()
            desc += ("\n\nWrites to the shop (needs confirm: true, and a server started with --writes)." if write else
                     "\n\nRead-only.")
            tools.append({
                "name": op["operationId"], "description": desc,
                "inputSchema": {"type": "object", "properties": props, "required": required,
                                "additionalProperties": False},
                "annotations": {"title": _title(op, write), "readOnlyHint": not write,
                                "destructiveHint": write, "idempotentHint": method in ("get", "put"),
                                "openWorldHint": False},
                "_http": {"method": method.upper(), "path": path, "path_params": path_params, "query": query},
            })
    return {"source": "api/openapi.yaml", "api_version": spec["info"]["version"], "tools": tools}


if __name__ == "__main__":
    out = build(yaml.safe_load(SPEC.read_text()))
    text = json.dumps(out, indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text() == text else "tools.json is stale: re-run generate.py")
    OUT.write_text(text)
    print(f"{len(out['tools'])} tools → {OUT.relative_to(HERE.parents[1])}")
