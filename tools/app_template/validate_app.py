#!/usr/bin/env python3
"""Check an app's settings file (`app.json`) and its Dockerfile before you deploy. Standard library only.

    python3 validate_app.py [<app folder>]        # default: the folder this file is in; exit 0 = ready, 1 = refused

The settings file says what the app is and what it needs, and holds **no value**: names only. A host (your own, or ours) reads it to
know the port, the health address, the size, the region, which environment variables to supply and whether the app
keeps a shops table (`shops`: many shops, each connecting itself), and whether it runs as an always-on container or as a
function paid per call (`runs`; a function also names its `handler` and the `package` it is zipped from). Refused, with the reason:
an unknown key, a bad name or port, a size or region not on the list, an environment variable with a value in the file, a variable
whose name looks like a secret but is not marked secret; and a Dockerfile that runs as root, has no health check, exposes a
different port from the file, or sets a secret-looking variable with ENV. A function needs no Dockerfile (one present is
still checked), serves many shops and keeps no secret of its own: each shop hands over its own at connect.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

KEYS = {"app", "version", "port", "health", "size", "region", "env", "shops", "runs", "handler", "package"}
ENV_KEYS = {"name", "secret", "required"}
SIZES = ("small", "medium", "large")
RUNS = ("container", "function")
HANDLER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_/]*\.[A-Za-z_][A-Za-z0-9_]*")     # service/app.lambda_handler
PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")                              # one piece of a package path
SECRETISH = re.compile(r"(SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|PRIVATE|CREDENTIAL)", re.I)


def check_settings(m) -> list[str]:
    bad = []
    if not isinstance(m, dict):
        return ["app.json is not a JSON object"]
    bad += [f"unknown key {k!r}" for k in sorted(set(m) - KEYS)]
    if not isinstance(m.get("app"), str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,39}", m.get("app") or ""):
        bad.append("app: a lower-case name of 3 to 40 letters, digits and hyphens, starting with a letter")
    if not isinstance(m.get("version"), str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", m.get("version") or ""):
        bad.append("version: three numbers, like 1.0.0")
    port = m.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        bad.append("port: a whole number from 1024 to 65535")
    if not isinstance(m.get("health"), str) or not re.fullmatch(r"/[A-Za-z0-9/_-]*", m.get("health") or ""):
        bad.append("health: an address starting with /, like /health")
    if m.get("size") not in SIZES:
        bad.append(f"size: one of {', '.join(SIZES)}")
    if not isinstance(m.get("region"), str) or not re.fullmatch(r"[a-z]{2}", m.get("region") or ""):
        bad.append("region: a two-letter lower-case country code, like us")
    if "shops" in m and not isinstance(m["shops"], bool):
        bad.append("shops: true or false (true: the app serves many shops, each connecting itself; chapter 14b)")
    bad += check_form(m)
    env = m.get("env", [])
    if not isinstance(env, list):
        return bad + ["env: a list"]
    seen = set()
    for i, e in enumerate(env):
        w = f"env[{i}]"
        if not isinstance(e, dict):
            bad.append(f"{w}: an object")
            continue
        bad += [f"{w}: unknown key {k!r}" + (" (the file holds names, never values)" if k in ("value", "default") else "") for k in sorted(set(e) - ENV_KEYS)]
        name = e.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name or ""):
            bad.append(f"{w}: name in capitals, digits and underscores")
            continue
        if name in seen:
            bad.append(f"{w}: {name} twice")
        if name in ("IVN_LOCAL", "IVN_LOCAL_LIBRARY_KEYS"):
            bad.append(f"{w}: {name} is for your laptop (local mode), never for hosting")
        seen.add(name)
        for flag in ("secret", "required"):
            if flag in e and not isinstance(e[flag], bool):
                bad.append(f"{w}: {flag} is true or false")
        if SECRETISH.search(name) and e.get("secret") is not True:
            bad.append(f"{w}: {name} looks like a secret: mark it \"secret\": true")
    return bad


def check_form(m: dict) -> list[str]:
    """``runs``: a container (the default: what an app that says nothing gets) or a function (chapter 14b)."""
    runs = m.get("runs", "container")
    if runs not in RUNS:
        return [f"runs: one of {', '.join(RUNS)} (leave it out for a container)"]
    if runs == "container":
        return [f"{k}: only a function has one (\"runs\": \"function\")" for k in ("handler", "package") if k in m]
    bad = []
    if not isinstance(m.get("handler"), str) or not HANDLER.fullmatch(m["handler"]) or ".." in m["handler"]:
        bad.append("handler: the file and its function, like service/app.lambda_handler")
    pkg = m.get("package")
    if not isinstance(pkg, list) or not pkg or not all(
            isinstance(x, str) and all(PART.fullmatch(part) and part != ".." for part in x.split("/")) for x in pkg):
        bad.append("package: a list of the files and folders the function is zipped from, relative paths like service")
    if m.get("shops") is not True:
        bad.append("shops: a function serves many shops, each connecting itself (\"shops\": true; chapter 14b)")
    env = m.get("env", [])
    if isinstance(env, list) and any(isinstance(e, dict) and e.get("secret") for e in env):
        bad.append("env: a function keeps no secret of its own: each shop hands over its own at connect "
                   "(an app that needs its own secret runs as a container)")
    return bad


def check_dockerfile(text: str, port) -> list[str]:
    bad, lines = [], [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    users = [l.split(None, 1)[1].strip() for l in lines if l.upper().startswith("USER ") and len(l.split(None, 1)) == 2]
    if not users or users[-1].split(":")[0] in ("root", "0"):
        bad.append("Dockerfile: the app must run as a user that is not root (add a USER line)")
    if not any(l.upper().startswith("HEALTHCHECK ") for l in lines):
        bad.append("Dockerfile: no HEALTHCHECK, so a platform cannot tell a stuck app from a healthy one")
    exposed = {int(p) for l in lines if l.upper().startswith("EXPOSE ") for p in re.findall(r"\d+", l)}
    if exposed and port not in exposed:
        bad.append(f"Dockerfile: EXPOSE {sorted(exposed)} but app.json says port {port}")
    for l in lines:
        if re.match(r"(ENV|ARG)\s", l, re.I) and SECRETISH.search(l.split("=")[0]) and "=" in l and l.split("=", 1)[1].strip():
            bad.append("Dockerfile: a secret-looking variable is set in the image (secrets come from the platform's secret store)")
    return bad


def check_folder(folder) -> list[str]:
    folder = pathlib.Path(folder)
    try:
        m = json.loads((folder / "app.json").read_text("utf-8"))
    except FileNotFoundError:
        return ["app.json is missing"]
    except ValueError as e:
        return [f"app.json is not valid JSON: {e}"]
    bad = check_settings(m)
    d = folder / "Dockerfile"
    if not d.is_file():
        function = isinstance(m, dict) and m.get("runs") == "function"
        return bad + ([] if function else ["Dockerfile is missing"])
    return bad + check_dockerfile(d.read_text("utf-8"), m.get("port") if isinstance(m, dict) else None)


def main() -> int:
    folder = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent
    bad = check_folder(folder)
    for b in bad:
        print("REFUSED: " + b)
    print("READY: the settings file (and the Dockerfile, if any) are fine" if not bad else f"{len(bad)} refusal(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
