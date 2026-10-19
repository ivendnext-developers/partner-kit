#!/usr/bin/env bash
# Validate api/openapi.yaml (OpenAPI 3.1) and prove the validator can fail. Needs the local venv:
#   python3 -m venv .venv && .venv/bin/pip install openapi-spec-validator==0.7.1 pyyaml
set -u
cd "$(dirname "$0")/.."
V=.venv/bin/openapi-spec-validator; PY=.venv/bin/python
rc=0
echo "== validate api/openapi.yaml"; $V --schema 3.1.0 api/openapi.yaml || rc=1
echo "== no YAML null slipped in (an unquoted ', ' inside a flow map parses as a stray key)"
$PY - <<'P' || rc=1
import yaml, sys
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if v is None: sys.exit(f"null value at {path}/{k}")
            walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): walk(v, f"{path}[{i}]")
walk(yaml.safe_load(open("api/openapi.yaml"))); print("no nulls")
P
T="$(mktemp -d)"
for c in "dangling-ref" "operationId-not-a-string"; do
  $PY - "$c" "$T/$c.yaml" <<'P'
import sys, yaml
kind, out = sys.argv[1], sys.argv[2]
d = yaml.safe_load(open("api/openapi.yaml"))
op = d["paths"]["/api/resource/Sales%20Invoice"]["get"]
if kind == "dangling-ref": op["responses"]["200"] = {"$ref": "#/components/responses/NoSuchResponse"}
else: op["operationId"] = [1, 2]
yaml.safe_dump(d, open(out, "w"))
P
  if $V --schema 3.1.0 "$T/$c.yaml" > "$T/$c.out" 2>&1; then echo "CANARY $c: NOT CAUGHT"; rc=1; else echo "CANARY $c: caught — $(grep -o 'Error.\{0,80\}' "$T/$c.out" | head -1)"; fi
done
rm -rf "$T"; echo "VALIDATE rc=$rc"; exit $rc
