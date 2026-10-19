"""kit.py — the Wasm point kit's one command Run it in a Python environment with wasmtime==49.0.0 (here `.venv`):

    .venv/bin/python tools/wasm_kit/kit.py build   [crate]                  # cargo test + build (wasm32-unknown-unknown)
    .venv/bin/python tools/wasm_kit/kit.py publish <raw.wasm> <out.wasm> [--server-only]
    .venv/bin/python tools/wasm_kit/kit.py parity  <module.wasm> [samples.json] [--metered]
    .venv/bin/python tools/wasm_kit/kit.py admit   <raw.wasm> [samples.json] [--server-only]

publish = scan (no SIMD, atomics or unknown instruction; no float unless --server-only) → the STACK meter (bound
10 000 units) → the FUEL meter (meter/) → the memory maximum (vendor/package.py, 160 pages) → the size cap
(256 KB; none with --server-only) → the load checks (vendor/host.py inspect, metered). admit takes the partner's RAW build: it refuses one that
already carries a meter, publishes it itself, then runs every sample on BOTH hosts — the server's (wasmtime) and the
browser's (the Worker host in hosts/, in Node): a trap, a refusal or an answer that differs from the expected one is a refusal.

What this kit's checks are NOT: our certificate. At intake, OUR CI runs the same harness and signs the module's sha256
(P-WASM §4); a partner never vouches for its own module.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

KIT = pathlib.Path(__file__).resolve().parent
PP = KIT.parents[1]
sys.path[:0] = [str(KIT), str(KIT / "vendor")]
import host as H  # noqa: E402  the server host, vendored unchanged
from scan import scan  # noqa: E402

SIZE_CAP = 256 * 1024          # a point that runs on the TILL (downloaded, cold-started there)
SERVER_ONLY_SIZE_CAP = None    # no size cap for a server-only function
STACK_BOUND = 10_000
CARGO = os.path.expanduser("~/.cargo/bin/cargo")
FUEL_METER = KIT / "meter" / "target" / "release" / "pp_meter"
STACK_METER = KIT / "stackmeter" / "target" / "release" / "pp_stackmeter"
SAMPLES = KIT / "template" / "samples" / "samples.json"


class Refused(Exception):
    pass


def _run(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise Refused(f"{pathlib.Path(str(cmd[0])).name} failed: {(r.stderr or r.stdout)[-400:]}")
    return r


def static_checks(b: bytes, metered: bool, server_only: bool, size_cap: int = SIZE_CAP) -> dict:
    """Everything decided from the bytes alone. Raises Refused with the first reason. A server-only point (it never
    runs on a till and touches no price or decision) may use floating point and SIMD; atomics never."""
    if size_cap is not None and len(b) > size_cap:
        raise Refused(f"too_large {len(b)} bytes (cap {size_cap})")
    try:
        profile = H.inspect(b, metered)
    except H.Refused as e:
        raise Refused(e.reason) from None
    try:
        s = scan(b)
    except (ValueError, IndexError) as e:
        raise Refused(f"invalid_module code: {e}") from None
    if s["simd"] and not server_only:
        raise Refused("simd")
    if s["atomics"]:
        raise Refused("atomics")
    if s["unsupported"]:
        raise Refused(f"unsupported_instruction {s['unsupported'][0]}")
    if s["float"] and not server_only:
        raise Refused(f"float {s['float'][0]} (a point that touches a price or a decision may not use floating point)")
    if not server_only and not metered:
        raise Refused("not_metered (a point that runs on the till must be published through the kit's meters)")
    return {"profile": profile, "functions": s["functions"]}


def build(crate=KIT / "template"):
    crate = pathlib.Path(crate).resolve()      # a relative path, or one outside the kit, is fine
    _run([CARGO, "test", "--release", "-q"], cwd=crate)
    _run([CARGO, "build", "--release", "-q", "--target", "wasm32-unknown-unknown"], cwd=crate)
    name = next(l.split("=")[1].strip().strip('"') for l in open(crate / "Cargo.toml") if l.startswith("name"))
    out = crate / "target" / "wasm32-unknown-unknown" / "release" / f"{name}.wasm"
    print(json.dumps({"built": str(out.relative_to(PP) if out.is_relative_to(PP) else out), "bytes": out.stat().st_size}))
    return out


def publish(raw: str, out: str, server_only=False) -> dict:
    src = open(raw, "rb").read()
    pre = _meter_exports(src)
    if pre:
        raise Refused(f"already_metered ({', '.join(pre)}): publish the raw build")
    # the hosts' own load checks first, on a copy with the memory cap written (the one thing publishing adds that they
    # check), so a module is refused with the hosts' precise reason before any tool rewrites it
    pdir = tempfile.mkdtemp()                 # the packager writes a MANIFEST.json beside its output: keep it out of `out`'s
    try:
        try:
            _run([sys.executable, KIT / "vendor" / "package.py", raw, os.path.join(pdir, "probe.wasm")])
        except Refused as e:                  # the packager's own refusal: the module's memory is not one plain memory
            raise Refused("no_memory (" + str(e).split("REFUSED: ")[-1].strip() + ")") from None
        H.inspect(open(os.path.join(pdir, "probe.wasm"), "rb").read(), metered=False)
    except H.Refused as e:
        raise Refused(e.reason) from None
    finally:
        shutil.rmtree(pdir, ignore_errors=True)
    try:
        s = scan(src)
    except (ValueError, IndexError) as e:
        raise Refused(f"invalid_module code: {e}") from None
    if s["atomics"] or (s["simd"] and not server_only):
        raise Refused("atomics" if s["atomics"] else "simd")
    if s["unsupported"]:
        raise Refused(f"unsupported_instruction {s['unsupported'][0]}")
    if s["float"] and not server_only:
        raise Refused(f"float {s['float'][0]}")
    tmp1, tmp2 = out + ".stack", out + ".fuel"
    _run([STACK_METER, raw, tmp1, STACK_BOUND])
    _run([FUEL_METER, tmp1, tmp2])
    _run([sys.executable, KIT / "vendor" / "package.py", tmp2, out, "--metered"])
    for t in (tmp1, tmp2):
        os.remove(t)
    b = open(out, "rb").read()
    facts = static_checks(b, metered=True, server_only=server_only,
                          size_cap=SERVER_ONLY_SIZE_CAP if server_only else SIZE_CAP)
    rec = {"module": os.path.basename(out), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "metered": True,
           "stack_bound_units": STACK_BOUND, "fuel_bound": H.LIMITS["fuel"], "server_only": server_only, **facts}
    json.dump(rec, open(out + ".publish.json", "w"), indent=1)
    print(json.dumps(rec))
    return rec


def _server(b: bytes, samples, metered: bool) -> list[dict]:
    try:
        loaded = H.load(H.engine(), b, metered)
    except H.Refused as e:
        raise Refused(e.reason) from None
    rows = []
    for smp in samples:
        data = smp["input"].encode() if "input" in smp else __import__("base64").b64decode(smp["input_b64"])
        r = H.run_once(loaded, data)
        rows.append({"id": smp["id"], "status": r["status"], "reason": r["reason"],
                     "out": r["output"].decode() if r["output"] is not None else None})
    return rows


def _browser(path: str, samples_path: str, metered: bool) -> list[dict]:
    r = subprocess.run(["node", str(KIT / "harness" / "run_node.mjs"), path, samples_path] +
                       (["--metered"] if metered else []), capture_output=True, text=True, timeout=600)
    rows = [json.loads(x) for x in r.stdout.split("\n") if x.startswith("{")]   # not splitlines(): U+2028 is raw in an answer
    if rows and "load" in rows[0]:
        raise Refused(rows[0]["reason"])
    return rows


def parity(path: str, samples_path: str = str(SAMPLES), metered=False) -> dict:
    """PARITY: the server host and the browser host give the IDENTICAL result on every sample — the same answer, or
    the same trap with the same reason; every answer given equals the sample's expected one (the spike's reference answers); and every
    sample marked must_answer is answered."""
    samples = json.load(open(samples_path))["samples"]
    b = open(path, "rb").read()
    srv, brw = _server(b, samples, metered), _browser(path, samples_path, metered)
    split, wrong, unanswered = [], [], []
    for smp, a, c in zip(samples, srv, brw):
        if (a["status"], a["reason"], a["out"]) != (c["status"], c["reason"], c["out"]):
            split.append(smp["id"])
        elif a["status"] == "ok" and a["out"] != smp["expected"]:
            wrong.append(smp["id"])
        elif a["status"] != "ok" and smp.get("must_answer"):
            unanswered.append((smp["id"], a["reason"]))
    traps = sorted({(a["reason"]) for a in srv if a["status"] != "ok"})
    rep = {"samples": len(samples), "browser_rows": len(brw), "hosts_identical": len(samples) - len(split),
           "answered_and_expected": sum(a["status"] == "ok" for a in srv) - len(wrong),
           "identical_traps": sum(a["status"] != "ok" for a in srv) - len([i for i in split]),
           "trap_reasons": traps, "split": split[:10], "wrong": wrong[:10], "must_answer_failed": unanswered[:10],
           "parity": not split and not wrong and not unanswered and len(brw) == len(samples)}
    print(json.dumps(rep))
    return rep


def _meter_exports(b: bytes) -> list[str]:
    try:
        exports = H.shape(b)["exports"]
    except H.Refused:
        return []
    return [e["name"] for e in exports if e["name"] in ("pp_fuel", "pp_stack")]


def admit(path: str, samples_path: str = str(SAMPLES), server_only=False, size_cap="default") -> dict:
    """The kit's local admission — what intake runs. ``path`` is the partner's RAW build.

    A till point: a module that already carries a meter is refused (a module's own counter is never trusted — review
    finding); the kit publishes it ITSELF (stack meter, fuel meter, memory cap), checks the result, then runs every
    sample — the server host first (its fuel stops a loop in milliseconds), the browser host only when the server side
    has answered every sample it must. A server-only point is checked as given and run on the server host only."""
    if size_cap == "default":
        size_cap = SERVER_ONLY_SIZE_CAP if server_only else SIZE_CAP
    b = open(path, "rb").read()
    samples = json.load(open(samples_path))["samples"]
    tmp = None
    try:
        pre = _meter_exports(b)
        if pre:                   # never trusted, on either path: the server host's own fuel is the bound here
            raise Refused(f"already_metered ({', '.join(pre)}): send the raw build — the kit meters it itself")
        if server_only:
            facts = static_checks(b, metered=False, server_only=True, size_cap=size_cap)
            run_path, metered = path, False
        else:
            tmp = tempfile.mkdtemp()
            run_path, metered = os.path.join(tmp, "published.wasm"), True
            facts = {k: v for k, v in _quiet_publish(path, run_path, size_cap).items()
                     if k in ("profile", "functions", "bytes", "sha256")}
        rb = open(run_path, "rb").read()
        for smp, r in zip(samples, _server(rb, samples, metered)):
            if smp.get("must_answer") and r["status"] != "ok":
                raise Refused(f"trial run (server): sample {smp['id']} not answered — {r['reason']}")
            if r["status"] == "ok" and r["out"] != smp["expected"]:
                raise Refused(f"trial run (server): sample {smp['id']} answered, but not the expected answer")
        rep = {"parity": True} if server_only else parity(run_path, samples_path, metered)
        if not rep["parity"]:
            raise Refused(f"trial run (both hosts): no parity — split {rep['split'][:3]}, wrong {rep['wrong'][:3]}, "
                          f"unanswered {rep['must_answer_failed'][:3]}")
    except Refused as e:
        out = {"module": os.path.basename(path), "admitted": False, "reason": str(e)}
    else:
        out = {"module": os.path.basename(path), "admitted": True, **facts}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(out))
    return out


def _quiet_publish(raw, out, size_cap):
    """publish() without its printout; the size cap applied to the PUBLISHED module, as at intake."""
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        rec = publish(raw, out)
    if rec["bytes"] > size_cap:
        raise Refused(f"too_large {rec['bytes']} bytes after metering (cap {size_cap})")
    return rec


if __name__ == "__main__":
    a = sys.argv[1:]
    flags = {x for x in a if x.startswith("--")}
    pos = [x for x in a if not x.startswith("--")]
    try:
        {"build": lambda: build(*(map(pathlib.Path, pos[1:2]))),
         "publish": lambda: publish(pos[1], pos[2], "--server-only" in flags),
         "parity": lambda: parity(pos[1], *(pos[2:3]), metered="--metered" in flags),
         "admit": lambda: admit(pos[1], *(pos[2:3]), server_only="--server-only" in flags)}[pos[0]]()
    except Refused as e:
        sys.exit(f"REFUSED {e}")
