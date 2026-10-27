"""Order CitiXsys App Hosting online, and run it: `deploy_app.py order | status | secret | cancel`.

    python3 tools/deploy_app/deploy_app.py order <app folder> --plan starter --partner <you> --github <owner>/<repo>
                                           [--branch main] [--env prod] [--customer <name>] [--set NAME=VALUE …]
                                           [--invoice --email <address>] --accept-schedule [--root <folder>] [--dry-run]
    python3 tools/deploy_app/deploy_app.py status --partner <you> [--order <id>]
    python3 tools/deploy_app/deploy_app.py secret --partner <you> --order <id> --name <NAME>   (the value from stdin)
    python3 tools/deploy_app/deploy_app.py cancel --partner <you> --order <id>

`order` runs the same checks as planning (`deploy_app.check`), then sends one request signed with the key you publish
with (`tools/publish`, `keygen`): the app's settings, the plan, the copy, your GitHub repository and branch, the plain
settings you give with `--set`, and the App Hosting Schedule's version you accept. It prints a Stripe checkout address
to pay monthly by card, or, with `--invoice`, says an invoice with payment terms goes to `--email`. An app that only
answers presses and is listed in the App library needs no payment. Once paid, CitiXsys's hosting builds the app with no
person, and each version your GitHub workflow pushes (`hosting-workflow.yml`) is put live the same way.

`secret` puts one secret's value (a container's `"secret": true` settings), read from standard input and never shown.
The signed request is sent over HTTPS; the value is kept only in the app's own secret store.

Exit code: 0 done · 1 refused · 2 usage. Standard library only.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import re
import secrets
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "publish"))
import ed25519  # noqa: E402
import publish  # noqa: E402  (the signing key: keygen, load_key, key_id)

URL = "https://hosting.ivendnext.app/v1/order"
DOMAIN = b"ivendnext-hosting-order/1\n"   # never the library upload's: an order cannot be replayed as an upload
SCHEDULE_VERSION = "2026-10-27"            # the App Hosting Schedule you accept by ordering (guide 14b)
SETTING = re.compile(r"([A-Z][A-Z0-9_]{0,63})=(.*)", re.S)
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
SUBJECT = re.compile(r"repo:([A-Za-z0-9][A-Za-z0-9-]{0,38})@[0-9]{1,15}/([A-Za-z0-9._-]{1,100})@[0-9]{1,15}")


class Stop(Exception):
    pass


def payload(cmd: str, partner: str, at: int | None = None, **fields) -> dict:
    return {"partner": partner, "at": int(time.time()) if at is None else at,
            "nonce": publish.b64u(secrets.token_bytes(16)), "cmd": cmd, **fields}


def envelope(p: dict, secret: bytes) -> bytes:
    body = json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return json.dumps({"v": 1, "key": publish.key_id(ed25519.public_key(secret)), "body": publish.b64u(body),
                       "sig": publish.b64u(ed25519.sign(secret, DOMAIN + body))}).encode()


def send(data: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(os.environ.get("IVN_HOSTING_URL", URL), data=data, method="POST",
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
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Stop(f"the hosting could not be reached ({type(e).__name__}); nothing is known to be done: run it again") from None


def app_settings(m: dict) -> dict:
    """What of app.json the order sends: names and shapes, never a value."""
    keep = ("app", "version", "runs", "size", "port", "health", "handler", "region", "shops")
    out = {k: m[k] for k in keep if k in m}
    out["env"] = [{k: e[k] for k in ("name", "secret", "required") if k in e} for e in m.get("env") or [] if isinstance(e, dict)]
    return out


def order_payload(folder, partner: str, plan: str, env: str, github: str, branch: str, customer: str = "",
                  settings=(), invoice: bool = False, email: str = "", root=None, subject: str = "") -> dict:
    import deploy_app  # the planning tool's checks, reused
    m = json.loads((pathlib.Path(folder) / "app.json").read_text("utf-8"))
    image = "" if deploy_app.is_function(m) else f"hosting.ivendnext.app/partner-apps/{m.get('app')}:{m.get('version')}"
    bad, m = deploy_app.check(folder, image, plan, partner, env, customer, root)
    if m.get("schedule") or "timeout" in m:      # the order carries neither: the app would run with no schedule
        bad.append("schedule: an app that runs on a schedule is put live by CitiXsys, not ordered online yet: "
                   "ask through your partner contact (guide 14b, A function on a schedule)")
    if not REPO.fullmatch(github or ""):
        bad.append("github: your repository as owner/name (the one your workflow pushes from)")
    sm = SUBJECT.fullmatch(subject or "") if subject else None
    if subject and (not sm or f"{sm[1]}/{sm[2]}".lower() != (github or "").lower()):
        bad.append("--github-subject: your repository's sign-in subject prefix, repo:<owner>@<id>/<name>@<id> (see guide 14b)")
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
    gh = {"repo": github, "branch": branch, **({"subject": subject} if subject else {})}
    return {"app": app_settings(m), "plan": plan, "env": env, "customer": customer, "github": gh,
            "plain_env": plain, "invoice": invoice, "email": email, "schedule_version": SCHEDULE_VERSION}


def show(out: dict) -> list[str]:
    lines = [f"ORDER {out['order']}: {out['id']} on {out['plan']}, {out['status']} ({out['kind']})", f"  address  {out['address']}"]
    if out.get("checkout_url"):
        lines.append(f"  pay      {out['checkout_url']}  (monthly by card; the hosting starts building once it is paid)")
    elif out.get("kind") == "invoice" and out.get("status") == "pending":
        lines.append("  pay      an invoice with payment terms is sent to your e-mail; the hosting builds the app once it is paid")
    up = out.get("upload") or {}
    lines.append(f"  upload   {up.get('image') or up.get('package')}  from GitHub, role {up.get('github_role')}")
    if out.get("secrets"):
        lines.append(f"  secrets  {', '.join(out['secrets'])}: put each with `deploy_app.py secret`")
    return lines


def main(argv) -> int:
    ap = argparse.ArgumentParser(prog="deploy_app.py", description="Order CitiXsys App Hosting online, and run it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("order", help="check, sign and send a hosting order")
    o.add_argument("folder")
    o.add_argument("--plan", required=True)
    o.add_argument("--env", default="prod")
    o.add_argument("--customer", default="")
    o.add_argument("--github", required=True, help="the repository your workflow pushes from: owner/name")
    o.add_argument("--branch", default="main")
    o.add_argument("--github-subject", default="", metavar="PREFIX",
                   help="your repository's sign-in subject prefix (repo:<owner>@<id>/<name>@<id>): gh api "
                        "repos/<owner>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix")
    o.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="a plain (not secret) setting")
    o.add_argument("--invoice", action="store_true", help="pay by invoice with payment terms instead of by card")
    o.add_argument("--email", default="", help="where the invoices go")
    o.add_argument("--accept-schedule", action="store_true",
                   help=f"you accept the App Hosting Schedule, version {SCHEDULE_VERSION} (guide 14b)")
    o.add_argument("--root", default="", help="a function: the folder its package paths start from")
    o.add_argument("--dry-run", action="store_true", help="check and sign, send nothing")
    for name, helptext in (("status", "your orders and apps"), ("secret", "put one secret's value (read from stdin)"),
                           ("cancel", "stop an app at the end of its paid month")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--order", default="" if name == "status" else None, required=name != "status")
        if name == "secret":
            p.add_argument("--name", required=True)
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
                raise Stop(f"read the App Hosting Schedule (version {SCHEDULE_VERSION}, guide 14b) and add --accept-schedule")
            fields = order_payload(a.folder, a.partner, a.plan, a.env, a.github, a.branch, a.customer, a.set,
                                   a.invoice, a.email, a.root or None, a.github_subject)
        elif a.cmd == "secret":
            value = getpass.getpass(f"{a.name}: ") if sys.stdin.isatty() else sys.stdin.read().rstrip("\n")
            fields = {"order": a.order, "name": a.name, "value": value}
        else:
            fields = {"order": a.order} if a.order else {}
        data = envelope(payload(a.cmd, a.partner, **fields), publish.load_key(a.key))
        if getattr(a, "dry_run", False):
            print(f"DRY RUN: {fields['app']['app']} {fields['app']['version']} on {a.plan}, {len(data)} bytes. Nothing was sent.")
            return 0
        status, out = send(data)
        if "refused" in out:
            print(f"REFUSED by the hosting ({status}): {out['refused']}" + (f" — {out['words']}" if out.get("words") else ""))
            return 1
        if a.cmd == "secret":
            print(f"{out['secret']} set on order {out['order']} (the value is not shown)")
        elif a.cmd == "cancel":
            print(f"order {out['order']}: stops at the end of the paid month" if out.get("stops_at") else
                  f"order {out['order']}: {out['status']}")
        else:
            for o_ in out.get("orders") or [out]:
                print("\n".join(show(o_)))
        return 0
    except (Stop, publish.Stop) as e:
        print(str(e) if str(e).startswith("REFUSED") else "REFUSED: " + str(e))
        return 1
