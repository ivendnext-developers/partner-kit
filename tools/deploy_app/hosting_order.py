"""Order CitiXsys App Hosting online, and run it: `deploy_app.py order | push | back | status | secret | cancel`.

    python3 tools/deploy_app/deploy_app.py order <app folder> --plan starter --partner <you>
                                           [--copies prod,sandbox] [--customer <name>] [--set NAME=VALUE …]
                                           [--invoice --email <address>] --accept-schedule [--root <folder>] [--dry-run]
    python3 tools/deploy_app/deploy_app.py push <app folder> --partner <you> --order <id> [--root <folder>] [--save <zip>]
    python3 tools/deploy_app/deploy_app.py back --partner <you> --order <id> --to <earlier version> [--version <new>]
    python3 tools/deploy_app/deploy_app.py status --partner <you> [--order <id>]
    python3 tools/deploy_app/deploy_app.py secret --partner <you> --order <id> [--env sandbox] --name <NAME>   (stdin)
    python3 tools/deploy_app/deploy_app.py cancel --partner <you> --order <id>

`order` runs the same checks as planning (`deploy_app.check`), then sends one request signed with the key you publish
with (`tools/publish`, `keygen`): the app's settings, the plan, its copies, the plain settings you give with `--set`,
and the App Hosting Schedule's version you accept. It prints a Stripe checkout address to pay monthly by card, or, with
`--invoice`, says an invoice with payment terms goes to `--email`. An app that only answers presses and is listed in the
App library needs no payment. Once paid, CitiXsys's hosting builds the app's copies with no person.

`push` sends a version: it zips the app's folder (never `.git`, an `.env…` file, `.samples` or `__pycache__`) and
uploads it, signed with the same key. A function's zip is its `app.json` and its package, read from `--root` as
`deploy_app.py --zip` reads it (an app made with `tools/manifest/start.py` names paths from the kit's folder: `--root .`).
`--save <zip>` writes the zip and sends nothing: the zip the hosting page's *Upload a version* takes. The hosting builds it on its side for every copy of the order (a container's
image for ARM, or a function's package) and puts it live; `status` says *Building 1.0.1…*, then *Built.*, or, when it
did not build, the last 50 lines of the build. You need no GitHub repository, no workflow and no AWS sign-in. Raise
app.json's `"version"` for each upload: a version is never built twice.

`back` goes back to an earlier version: the hosting copies that version's image or package under a new, higher number
(the next one after your newest, or `--version`), and puts it live. Nothing is built.

One order runs the plan's copies (production and its sandbox, and staging on the plans that have it) at the plan's one
price; `--copies` names fewer. Each copy has its own address and its own secrets; a version goes to every copy.

`secret` puts one secret's value (a container's `"secret": true` settings) on one copy, read from standard input and
never shown.
The signed request is sent over HTTPS; the value is kept only in the app's own secret store.

Exit code: 0 done · 1 refused · 2 usage. Standard library only.
"""
from __future__ import annotations

import argparse
import getpass
import http.client
import json
import os
import pathlib
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "publish"))
import ed25519  # noqa: E402
import publish  # noqa: E402  (the signing key: keygen, load_key, key_id)

URL = "https://hosting.ivendnext.app/v1/order"
UPLOAD_PATH = "/v1/upload"                 # the same signed door's upload address (the hosting's own name)
MB = 1024 * 1024
LIMITS = {"function": 50 * MB, "container": 1024 * MB}   # a function's package, a container's image (plans.json's hosting)
DOMAIN = b"ivendnext-hosting-order/1\n"   # never the library upload's: an order cannot be replayed as an upload
SCHEDULE_VERSION = "2026-10-21"            # the App Hosting Schedule you accept by ordering: Schedule 1 of the iVendNext Developer Terms, version 1.0 (guide 14b)
SETTING = re.compile(r"([A-Z][A-Z0-9_]{0,63})=(.*)", re.S)
SEMVER = re.compile(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}")
ORDER = re.compile(r"[0-9a-f]{16}")
# what a container's upload leaves out: the repository's own history, local settings with secrets, kept sample copies, caches
CONTAINER_SKIP = re.compile(r"(^|/)(\.git|\.env[^/]*|\.samples|__pycache__)(/|$)|\.pyc$")


class Stop(Exception):
    pass


def payload(cmd: str, partner: str, at: int | None = None, **fields) -> dict:
    return {"partner": partner, "at": int(time.time()) if at is None else at,
            "nonce": publish.b64u(secrets.token_bytes(16)), "cmd": cmd, **fields}


def envelope(p: dict, secret: bytes) -> bytes:
    body = json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return json.dumps({"v": 1, "key": publish.key_id(ed25519.public_key(secret)), "body": publish.b64u(body),
                       "sig": publish.b64u(ed25519.sign(secret, DOMAIN + body))}).encode()


def send(data: bytes, path: str = "") -> tuple[int, dict]:
    url = os.environ.get("IVN_HOSTING_URL", URL)
    if path:
        url = url.rsplit("/v1/", 1)[0] + path
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "iVendNext-kit-hosting/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"refused": f"http_{e.code}", "words": "the hosting did not answer in JSON"}
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
        raise Stop(f"the hosting could not be reached ({type(e).__name__}); nothing is known to be done: run it again") from None


def app_settings(m: dict) -> dict:
    """What of app.json the order sends: names and shapes, never a value."""
    keep = ("app", "version", "runs", "size", "port", "health", "handler", "region", "shops", "scratch")
    out = {k: m[k] for k in keep if k in m}
    out["env"] = [{k: e[k] for k in ("name", "secret", "required") if k in e} for e in m.get("env") or [] if isinstance(e, dict)]
    return out


def plan_copies(plan: str) -> list[str]:
    """The copies a plan runs, production first (plans.json `enforced.envs`)."""
    import deploy_app
    p = deploy_app.PLANS["plans"].get(plan)
    return [e for e in deploy_app.PLANS["envs"] if p and e in p["enforced"]["envs"]]


def order_payload(folder, partner: str, plan: str, copies, customer: str = "",
                  settings=(), invoice: bool = False, email: str = "", root=None) -> dict:
    import deploy_app  # the planning tool's checks, reused
    m = json.loads((pathlib.Path(folder) / "app.json").read_text("utf-8"))
    image = "" if deploy_app.is_function(m) else f"hosting.ivendnext.app/partner-apps/{m.get('app')}:{m.get('version')}"
    copies = list(copies) or plan_copies(plan)
    bad = [f"--copies: {e} is named twice" for e in sorted({e for e in copies if copies.count(e) > 1})]
    for env in dict.fromkeys(copies) or ["prod"]:  # each copy as planning checks it; a problem shared by all, once
        b, m = deploy_app.check(folder, image, plan, partner, env, customer, root)
        bad += [x for x in b if x not in bad]
    if m.get("schedule") or "timeout" in m:      # the order carries neither: the app would run with no schedule
        bad.append("schedule: an app that runs on a schedule is put live by CitiXsys, not ordered online yet: "
                   "ask through your partner contact (guide 14b, A function on a schedule)")
    plain_names = {e.get("name") for e in m.get("env") or [] if isinstance(e, dict) and not e.get("secret")}
    plain = {}
    for s in settings:
        mm = SETTING.fullmatch(s)
        if not mm or mm[1] not in plain_names:
            bad.append(f"--set {s.split('=', 1)[0]}: a plain (not secret) setting your app.json names")
        else:
            plain[mm[1]] = mm[2]
    if invoice and not email:
        bad.append("--invoice needs --email: where the invoices go")
    if bad:
        raise Stop("\n".join("REFUSED: " + b for b in bad))
    return {"app": app_settings(m), "plan": plan, "copies": copies, "customer": customer,
            "plain_env": plain, "invoice": invoice, "email": email, "schedule_version": SCHEDULE_VERSION}


# ── push: one version, uploaded and built on the hosting's side ──

def megabytes(size: int) -> str:
    """A size as the hosting says it: in MB, rounded up to one decimal."""
    tenths = -(-int(size) * 10 // MB)
    return f"{tenths // 10:,}" if tenths % 10 == 0 else f"{tenths // 10:,}.{tenths % 10}"


def too_big(size: int) -> str:
    return (f"Not kept: this upload is {megabytes(size)} MB; a function's package can be at most 50 MB, a container's "
            "image at most 1,024 MB. Nothing was built.")


def folder_zip(folder, root=None) -> bytes:
    """What `push` uploads, the same bytes for the same files: a container's folder (every file but `.git`, `.env…`
    files, the kept sample copies `.samples` and caches, so `.dockerignore` and any dot-file its Dockerfile copies go
    too; its executable bit kept for its scripts); a function's `app.json` and its package, read from `root` (default:
    the folder) exactly as `deploy_app.py --zip` reads it."""
    import deploy_app
    import io
    import zipfile
    folder, buf = pathlib.Path(folder), io.BytesIO()
    m = json.loads((folder / "app.json").read_text("utf-8"))
    if deploy_app.is_function(m):
        pairs = [("app.json", folder / "app.json")] + [p for p in deploy_app.package_files(m, root or folder) if p[0] != "app.json"]
    else:
        pairs = [(f.relative_to(folder).as_posix(), f) for f in sorted(folder.rglob("*")) if f.is_file() and not f.is_symlink()]
    skip = deploy_app.SKIP if deploy_app.is_function(m) else CONTAINER_SKIP
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, f in pairs:
            if skip.search(name):
                continue
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            mode = 0o755 if f.stat().st_mode & 0o111 else 0o644
            info.external_attr, info.compress_type, info.create_system = (0o100000 | mode) << 16, zipfile.ZIP_DEFLATED, 3
            z.writestr(info, f.read_bytes())
    return buf.getvalue()


def push_checks(folder, root=None) -> tuple[dict, list[str]]:
    """What the hosting's build would refuse, checked here first: the template's checker and the hosted licence rule,
    and a function's package and handler, from `root` as `--zip` reads them (the hosting builds from the zip alone)."""
    import deploy_app
    try:
        m = json.loads((pathlib.Path(folder) / "app.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}, ["app.json: the folder has no app.json the hosting can read"]
    if not isinstance(m, dict):
        return {}, ["app.json: the folder has no app.json the hosting can read"]
    bad = deploy_app.validate_app.check_folder(folder) + deploy_app.licence.check(folder, hosted=True)
    if not SEMVER.fullmatch(str(m.get("version", ""))):
        bad.append('version: app.json\'s "version", three numbers like 1.0.1')
    if deploy_app.is_function(m):
        base = pathlib.Path(root or folder)
        for part in m.get("package") or []:
            if not isinstance(part, str) or part.startswith("/") or ".." in pathlib.PurePosixPath(part).parts \
                    or not (base / part).exists():
                bad.append(f"package: {part} is not in {base} (give --root: the folder the package paths start from)")
        handler = m.get("handler") if isinstance(m.get("handler"), str) else ""
        if not bad and "/" + handler.rsplit(".", 1)[0] + ".py" not in ["/" + n for n, _ in deploy_app.package_files(m, base)]:
            bad.append(f"handler: {handler.rsplit('.', 1)[0]}.py is not in the package")
    return m, bad


def put(url: str, headers: dict, data: bytes) -> int:
    if not url.startswith("https://") or not urllib.parse.urlsplit(url).hostname.endswith(".amazonaws.com"):
        raise Stop("the hosting answered an upload address that is not ours; nothing was sent")
    req = urllib.request.Request(url, data=data, method="PUT", headers={**headers, "Content-Length": str(len(data))})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status
    except urllib.error.HTTPError as e:
        with e:
            return e.code
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        raise Stop(f"the upload did not finish ({type(e).__name__}); nothing was built: run push again") from None


REASONS = (("held", "held: {}"), ("waiting_for", "waiting for its secrets: {}"), ("roll_failed", "version {} did not start"),
           ("push_refused", "version {} was refused (its size, or not a version)"),
           ("push_not_sent", "version {} reached it from outside an upload and is not put live: upload it"),
           ("stopped", "stopped: {}"))


def _state(c: dict) -> str:
    st = f"building ({c['building']})" if c.get("status") == "building" else c.get("status", "")
    if c.get("live_version"):
        st += f", running {c['live_version']}"
    return "; ".join([st] + [w.format(", ".join(c[k]) if isinstance(c[k], list) else c[k]) for k, w in REASONS if c.get(k)])


def show(out: dict) -> list[str]:
    copies = out.get("copies") or [out]  # a hosting from before copies answers with one
    name = copies[0]["id"] if len(copies) == 1 else out["id"]
    lines = [f"ORDER {out['order']}: {name} on {out['plan']} ({out['kind']}), {len(copies)} cop{'y' if len(copies) == 1 else 'ies'}"
             + (f" for {out['customer']}" if out.get("customer") else "")]
    if out.get("checkout_url"):
        lines.append(f"  pay      {out['checkout_url']}  (monthly by card, one price for every copy; the hosting starts "
                     "building once it is paid)")
    elif out.get("kind") == "invoice" and out.get("status") == "pending":
        lines.append("  pay      an invoice with payment terms is sent to your e-mail; the hosting builds the app once it is paid")
    if out.get("stops_at"):
        lines.append(f"  stops    at the end of the paid month ({time.strftime('%Y-%m-%d', time.gmtime(out['stops_at']))})")
    for c in copies:
        lines.append(f"  {c.get('env', 'prod'):<8} {c['address']}  {_state(c)}")
    if out.get("versions"):
        lines.append(f"  versions {', '.join(out['versions'])}")
    b = out.get("build")
    if b and b.get("words"):
        lines.append(f"  build    {b['words']}")
        lines += [f"           | {ln}" for ln in b.get("lines") or []]
    if out.get("secrets"):
        lines.append(f"  secrets  {', '.join(out['secrets'])}: put each on each copy with `deploy_app.py secret --env <copy>`")
    return lines


def main(argv) -> int:
    ap = argparse.ArgumentParser(prog="deploy_app.py", description="Order CitiXsys App Hosting online, and run it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("order", help="check, sign and send a hosting order")
    o.add_argument("folder")
    o.add_argument("--plan", required=True)
    o.add_argument("--copies", default="", metavar="ENV,ENV",
                   help="the copies to run, from the plan's (default: all of them): prod, staging, sandbox")
    o.add_argument("--env", default="", help=argparse.SUPPRESS)  # an older form: one copy
    o.add_argument("--customer", default="")
    o.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="a plain (not secret) setting")
    o.add_argument("--invoice", action="store_true", help="pay by invoice with payment terms instead of by card")
    o.add_argument("--email", default="", help="where the invoices go")
    o.add_argument("--accept-schedule", action="store_true",
                   help=f"you accept the App Hosting Schedule, version {SCHEDULE_VERSION} (guide 14b)")
    o.add_argument("--root", default="", help="a function: the folder its package paths start from")
    o.add_argument("--dry-run", action="store_true", help="check and sign, send nothing")
    u = sub.add_parser("push", help="upload a new version: the hosting builds it for every copy and puts it live")
    u.add_argument("folder")
    u.add_argument("--order", default="", help="the order's id (not needed with --save)")
    u.add_argument("--root", default="", help="a function: the folder its package paths start from (default: the app's)")
    u.add_argument("--save", default="", metavar="ZIP", help="write the zip here and send nothing (for the hosting page)")
    b = sub.add_parser("back", help="go back to an earlier version, put live again under a new number (nothing is built)")
    b.add_argument("--order", required=True)
    b.add_argument("--to", required=True, metavar="VERSION", help="the earlier version")
    b.add_argument("--version", default="", help="the new number (default: the next one after your newest)")
    for name, helptext in (("status", "your orders and apps"), ("secret", "put one secret's value (read from stdin)"),
                           ("cancel", "stop an app at the end of its paid month")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--order", default="" if name == "status" else None, required=name != "status")
        if name == "secret":
            p.add_argument("--name", required=True)
            p.add_argument("--env", default="", help="the copy: prod, staging or sandbox (needed when the order has several)")
    for p in sub.choices.values():
        p.add_argument("--partner", required=True, help="your company's code, as iVendNext registered it")
        p.add_argument("--key", help="your signing key file (default: IVN_LIBRARY_KEY, then the keygen default)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if a.cmd == "order":
            if not a.accept_schedule:
                raise Stop(f"read the App Hosting Schedule (dated {SCHEDULE_VERSION}, guide 14b) and add --accept-schedule")
            copies = [e.strip() for e in (a.copies or a.env).split(",") if e.strip()]
            fields = order_payload(a.folder, a.partner, a.plan, copies, a.customer, a.set,
                                   a.invoice, a.email, a.root or None)
        elif a.cmd == "push":
            return push(a)
        elif a.cmd == "back":
            if not ORDER.fullmatch(a.order or "") or not SEMVER.fullmatch(a.to) or (a.version and not SEMVER.fullmatch(a.version)):
                raise Stop("--order is the order's id (16 letters and digits), --to and --version are versions like 1.0.1")
            fields = {"order": a.order, "to": a.to, **({"version": a.version} if a.version else {})}
        elif a.cmd == "secret":
            value = getpass.getpass(f"{a.name}: ") if sys.stdin.isatty() else sys.stdin.read().rstrip("\n")
            fields = {"order": a.order, "name": a.name, "value": value, **({"env": a.env} if a.env else {})}
        else:
            fields = {"order": a.order} if a.order else {}
        data = envelope(payload(a.cmd, a.partner, **fields), publish.load_key(a.key))
        if getattr(a, "dry_run", False):
            print(f"DRY RUN: {fields['app']['app']} {fields['app']['version']} on {a.plan}, copies {', '.join(fields['copies'])}, "
                  f"{len(data)} bytes. Nothing was sent.")
            return 0
        status, out = send(data)
        if "refused" in out:
            print(f"REFUSED by the hosting ({status}): {out['refused']}" + (f" — {out['words']}" if out.get("words") else ""))
            return 1
        if a.cmd == "secret":
            print(f"{out['secret']} set on order {out['order']} (the value is not shown)")
        elif a.cmd == "back":
            print(f"BACK: {out['version']} holds {out['from']}'s content on every copy of order {out['order']}; nothing was "
                  "built. It is put live now: `deploy_app.py status` follows it.")
        elif a.cmd == "cancel":
            print(f"order {out['order']}: stops at the end of the paid month" if out.get("stops_at") else
                  f"order {out['order']}: {out['status']}")
        else:
            orders = out["orders"] if "orders" in out else [out]
            for o_ in orders:
                print("\n".join(show(o_)))
            if not orders:
                print("no hosting orders yet")
        return 0
    except (Stop, publish.Stop) as e:
        print(str(e) if str(e).startswith("REFUSED") else "REFUSED: " + str(e))
        return 1


def push(a) -> int:
    """`push <folder> --order <id>`: check, zip, ask the hosting for the upload's address (signed), and upload."""
    if not a.save and not ORDER.fullmatch(a.order or ""):
        raise Stop("--order: the order's id, 16 letters and digits (deploy_app.py status lists them)")
    m, bad = push_checks(a.folder, a.root or None)
    if bad:
        raise Stop("\n".join("REFUSED: " + b for b in bad))
    data = folder_zip(a.folder, a.root or None)
    import deploy_app
    limit = LIMITS["function" if deploy_app.is_function(m) else "container"]
    if len(data) > limit:
        raise Stop(too_big(len(data)))
    version = m["version"]
    if a.save:
        pathlib.Path(a.save).write_bytes(data)
        print(f"SAVED {version} as {a.save} ({megabytes(len(data))} MB). Nothing was sent: choose it under Upload a version "
              "on the hosting page, or run push without --save.")
        return 0
    env = envelope(payload("upload", a.partner, order=a.order, version=version, size=len(data)), publish.load_key(a.key))
    status, out = send(env, UPLOAD_PATH)
    if "refused" in out:
        print(f"REFUSED by the hosting ({status}): {out['refused']}" + (f" — {out['words']}" if out.get("words") else ""))
        return 1
    up = out["upload"]
    code = put(up["url"], up.get("headers") or {}, data)
    if code == 412:
        print(f"REFUSED: {version} was uploaded already: raise app.json's \"version\" and push again")
        return 1
    if code not in (200, 201):
        print(f"REFUSED: the upload was not kept ({code}); nothing was built: run push again")
        return 1
    print(f"UPLOADED {version} ({megabytes(len(data))} MB) for order {out['order']}: it is built on our side now, for "
          f"every copy. `deploy_app.py status --partner {a.partner} --order {out['order']}` follows it.")
    return 0
