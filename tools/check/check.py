#!/usr/bin/env python3
"""check — one command that runs the kit's checks over your project, before anything is installed anywhere.

    python3 tools/check/check.py <project dir> [--server-only]

It finds five kinds of thing under the folder and runs the kit's own checker on each:

  * manifests        every file whose name ends in ``manifest.json`` -> tools/manifest/validate.py
  * apps             every folder holding a ``hooks.py`` -> tools/selfcheck/selfcheck.py
  * sandboxed builds every ``*.wasm`` -> tools/wasm_kit/scan.py (no SIMD, atomics or unknown instruction; no floating
                     point unless ``--server-only``). The full run on both hosts is ``tools/wasm_kit/kit.py admit``.
  * answers          every ``*.contract.json`` and every JSON file under a ``contract_samples/`` folder, shaped like the
                     samples in ``contracts/extension_contracts/samples/``:
                     ``{"extension_point": "desk_action", "contract": "answer", "payload": {...}}``
                     and ``"expect_refusal": "why"`` for an answer that must be turned away (the kit's own refused
                     samples work unchanged; ``"beyond_schema": true`` marks one only a shop's stored state refuses).
                     -> tools/contracts/check.py
  * settings files   every ``app.json`` that names an ``env`` list, a ``port``, a ``health`` or ``runs`` (the hosting
                     order, chapter 14b; the App library's card, also ``app.json``, is not one): its
                     settings -> tools/app_template/validate_app.py (every setting says its ``purpose``, the line the
                     Settings screen shows; the Dockerfile is checked when you plan a deploy, tools/deploy_app/)

Folders named ``tests``, ``fixtures``, ``node_modules``, ``.git``, ``.venv``, ``venv`` and ``__pycache__`` are not
searched when this looks for things to check: a test may hold a defect on purpose. (The self-check, once it is given an
app, does read that app's own ``fixtures`` folder: a script shipped as a fixture is refused.) A folder it cannot read is a refusal, and a linked folder is not followed
(it says so). Prints one line per finding and one verdict line. Exit 0 = green, 1 = at least one refusal, 2 = nothing to
check (a folder with nothing in it is not a green project: it is not a verdict either).

What a green line is NOT: permission. It means these checkers found no refusal, and each has bounds:
  * the self-check reads an app's files and never runs them; it does not read folders named build or dist, and an app
    that ships code into a shop is still something a person reviews (rule 3, guide chapter 3);
  * the Wasm scan reads instructions and local types, not every use of a float; ``kit.py admit`` is the gate for a module;
  * ``expect_refusal`` is for testing how your service handles a refusal; marking an answer you got wrong with it hides it.
Standard library only. Read-only: it never runs your code and never touches a shop.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

KIT = pathlib.Path(__file__).resolve().parents[2]
SKIP = {"tests", "fixtures", "node_modules", ".git", ".venv", "__pycache__", "venv"}


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _files(root: pathlib.Path, notes):
    """Every file under ``root`` except in a skipped folder. A linked folder is reported, not followed; a folder that
    cannot be read is a refusal, because what is in it was not checked."""
    unreadable = []
    found = []
    for here, dirs, names in os.walk(root, onerror=lambda e: unreadable.append(e.filename)):
        here = pathlib.Path(here)
        keep = []
        for d in sorted(dirs):
            if d in SKIP:
                continue
            if (here / d).is_symlink():
                notes.append(("NOTE", f"{(here / d).relative_to(root).as_posix()}: a linked folder, not followed"))
                continue
            keep.append(d)
        dirs[:] = keep
        found.extend(here / n for n in sorted(names))
    for f in unreadable:
        notes.append(("REFUSED", f"{pathlib.Path(f).relative_to(root).as_posix()}: a folder that cannot be read, so it was not checked"))
    return sorted(found)


def _manifest(path, rel, out):
    validate = _load("kit_manifest_validate", KIT / "tools" / "manifest" / "validate.py")
    try:
        manifest = json.loads(path.read_text("utf-8"))
        refusals = validate.validate(manifest)
    except json.JSONDecodeError as e:   # the place in plain words, not the parser's own message
        return out.append(("REFUSED", f"{rel}: the file is not valid JSON: something is missing or extra at line {e.lineno}, "
                                      f"column {e.colno}"))
    except (ValueError, OSError, AttributeError, TypeError) as e:
        return out.append(("REFUSED", f"{rel}: not a readable manifest ({type(e).__name__}: {e})"))
    if not refusals:   # what the shop's install refuses that its checker passes (tools/manifest/site_rules.py)
        refusals = _load("kit_manifest_site_rules", KIT / "tools" / "manifest" / "site_rules.py").refusals(manifest)
    for r in refusals:
        out.append(("REFUSED", f"{rel}: {r['where']}: {r['reason']}"))
    for w in [] if refusals else validate.warnings(manifest):
        out.append(("NOTE", f"{rel}: {w['where']}: {w['text']}"))
    if not refusals:
        out.append(("OK", f"{rel}: manifest valid"))


def _apps(files):
    """The app packages: every folder holding a hooks.py (the self-check reads the package it is given)."""
    return sorted({p.parent for p in files if p.name == "hooks.py"})


def _app(path, rel, out):
    r = subprocess.run([sys.executable, str(KIT / "tools" / "selfcheck" / "selfcheck.py"), str(path)],
                       capture_output=True, text=True)
    lines = [ln.strip() for ln in r.stdout.splitlines()]
    fails = [ln for ln in lines if ln.startswith("FAIL")]
    for ln in fails:        # the finding lines follow their check's line: a builder needs the file and the words, not only the title
        found = []
        for nxt in lines[lines.index(ln) + 1:]:
            if not nxt.startswith("- "):
                break
            found.append(nxt)
        out.append(("REFUSED", f"{rel}: self-check {ln}" + "".join("\n           " + f for f in found[:4])
                    + ("\n           … run tools/selfcheck/selfcheck.py on the app for the rest" if len(found) > 4 else "")))
    for ln in [ln for ln in lines if ln.startswith("REVIEW")]:
        out.append(("NOTE", f"{rel}: self-check {ln} (a person looks)"))
    if r.returncode not in (0, 1) or (r.returncode == 1 and not fails):
        out.append(("REFUSED", f"{rel}: self-check did not finish ({(r.stdout + r.stderr).strip()[-200:]})"))
    elif not fails:
        out.append(("OK", f"{rel}: self-check has no FAIL"))
    out.append(("NOTE", f"{rel}: app code runs inside the shop's site. Rule 3 (guide chapter 3): inside a customer's site "
                        "you ship data, not code. A person reviews this app; a green line is not that review"))


def _wasm(path, rel, out, server_only):
    scan = _load("kit_wasm_scan", KIT / "tools" / "wasm_kit" / "scan.py")
    data = path.read_bytes() if path.is_file() else b""
    if data[:8] != b"\x00asm\x01\x00\x00\x00":
        return out.append(("REFUSED", f"{rel}: not a WebAssembly module (it does not start with the module header)"))
    try:
        found = scan.scan(data)
    except Exception as e:      # the scanner indexes a section it was told is longer than the file: refuse, don't crash
        return out.append(("REFUSED", f"{rel}: the module is cut short or malformed ({type(e).__name__})"))
    bad = []
    if found["simd"] and not server_only:
        bad.append("uses SIMD")
    if found["atomics"]:
        bad.append("uses atomics")
    if found["unsupported"]:
        bad.append(f"uses instructions outside the core set {found['unsupported']}")
    if found["float"] and not server_only:
        bad.append(f"uses floating point ({found['float'][0]}); a price or decision point may not, a server-only point may")
    for b in bad:
        out.append(("REFUSED", f"{rel}: {b}"))
    if not bad:
        out.append(("OK", f"{rel}: scan clean (the run on both hosts is tools/wasm_kit/kit.py admit)"))


def _answer(path, rel, out):
    contracts = _load("kit_contracts_check", KIT / "tools" / "contracts" / "check.py")
    try:
        s = json.loads(path.read_text("utf-8"))
        errs = contracts.errors(s["extension_point"], s["contract"], s["payload"])
    except (ValueError, OSError, KeyError, TypeError) as e:
        return out.append(("REFUSED", f"{rel}: not a usable answer file ({type(e).__name__}: {e}); it needs "
                                      "extension_point, contract and payload"))
    must_refuse = bool(s.get("expect_refusal")) and not s.get("beyond_schema")
    if must_refuse and not errs:
        out.append(("REFUSED", f"{rel}: expected to be refused, but the {s['extension_point']} contract accepts it"))
    elif not must_refuse and errs:
        for e in errs[:5]:
            out.append(("REFUSED", f"{rel}: breaks the {s['extension_point']} contract: {e}"))
    else:
        out.append(("OK", f"{rel}: {'refused as expected' if must_refuse else 'holds'} against {s['extension_point']}"))


def _is_settings(path, rel, out) -> bool:
    """An ``app.json`` that is the hosting order's settings file. Another tool's ``app.json`` (the App library's card, a
    mobile project's) is left alone; one that is not valid JSON is named, since nobody can tell what it is."""
    try:
        m = json.loads(path.read_text("utf-8"))
    except (ValueError, OSError):
        out.append(("NOTE", f"{rel}: not valid JSON, so not checked as a settings file "
                            "(tools/app_template/validate_app.py says where it breaks)"))
        return False
    return isinstance(m, dict) and any(k in m for k in ("env", "port", "health", "runs"))


def _settings(path, rel, out):
    validate_app = _load("kit_validate_app", KIT / "tools" / "app_template" / "validate_app.py")
    bad = validate_app.check_settings(json.loads(path.read_text("utf-8")))     # read once already by _is_settings
    for b in bad:
        out.append(("REFUSED", f"{rel}: {b}"))
    if not bad:
        out.append(("OK", f"{rel}: settings file valid"))


def run(root: pathlib.Path, server_only: bool = False):
    out: list[tuple[str, str]] = []
    count = {"manifests": 0, "apps": 0, "modules": 0, "answers": 0, "settings files": 0}
    files = _files(root, out)

    def rel(p):
        return p.relative_to(root).as_posix() or "."

    for p in files:
        if p.name.endswith("manifest.json"):
            count["manifests"] += 1
            _manifest(p, rel(p), out)
        elif p.suffix == ".wasm":
            count["modules"] += 1
            _wasm(p, rel(p), out, server_only)
        elif p.name.endswith(".contract.json") or ("contract_samples" in p.relative_to(root).parts[:-1] and p.suffix == ".json"):
            count["answers"] += 1
            _answer(p, rel(p), out)
        elif p.name == "app.json" and _is_settings(p, rel(p), out):
            count["settings files"] += 1
            _settings(p, rel(p), out)
    for app in _apps(files):
        count["apps"] += 1
        _app(app, rel(app), out)
    return out, count


def main(argv: list[str]) -> int:
    server_only = "--server-only" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1 or not pathlib.Path(args[0]).is_dir():
        print(__doc__)
        return 2
    out, count = run(pathlib.Path(args[0]).resolve(), server_only)
    for kind, text in out:
        print(f"{kind:8s} {text}")
    found = ", ".join(f"{n} {k[:-1] if n == 1 else k}" for k, n in count.items() if n)
    refused = sum(k == "REFUSED" for k, _ in out)
    if not found:
        print("NOTHING FOUND: no manifest, app, sandboxed build, answer file or settings file under this folder")
        return 2
    print(f"CHECK {'GREEN' if not refused else f'RED: {refused} refusal(s)'} — {found}")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
