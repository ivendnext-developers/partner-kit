#!/usr/bin/env python3
"""publish — put your app in the iVendNext App library from any machine, with or without GitHub.

    python3 tools/publish/publish.py login
    python3 tools/publish/publish.py publish <project folder> [--deliveries FILE] [--keys FILE] [--out FILE] [--dry-run]
    python3 tools/publish/publish.py publish <project folder> --partner <your code> --key FILE …   (signed, until EASY3b)
    python3 tools/publish/publish.py keygen [--key FILE] [--register --recipient library/recipient.pem]

`login` signs this computer in to My apps (`developer.ivendnext.com/apps`) by a code: it prints a code, you enter it on
My apps (signed in with GitHub), and it keeps a token of yours in `~/.ivendnext/token` (only you can read it; 30 days).
A build server uses a token made on My apps > Tokens, in its secret `IVN_TOKEN`. With a token there is no key file:
`publish` names no company (the token does), and the keys come back in the answer, with the message to send each
site's administrator, which `publish` prints.

`keygen` (kept until the signed upload goes) makes a signing key on this machine; `--register` registers it, and your
sealing key, with your token: no request to iVendNext. The private half never leaves your machine.

`publish` reads your project's `library/` folder — `app.json` (the card), `manifest.json` (your app), `library.json`
(`{"public": true|false, "preview_sites": [...]}`) and `recipient.pem` — runs the kit's checks over it
(`tools/check/check.py`, and `tools/check/licence.py` over the project), signs it and uploads it. We take only these
files: never your source code. It prints what the library did: your preview shelf, your customers' shelves, the public
list (a first listing, or a version that does more than the last, waits for one approval by iVendNext), and keys.
Keys come back sealed to your `recipient.pem` and are written to a file (`library-keys.json`, readable by you only),
never printed.

Your customers' site addresses and the keys you ask for are never in the kit or your project: they come from the
environment (`LIBRARY_DELIVERIES`, `LIBRARY_KEYS`, as JSON) or from a file you name (`--deliveries`, `--keys`). **The
library keeps where each version went**, per app and site: a publish with no list reaches every site the app is on
(a site taken off with *Remove this site* on My apps gets nothing new), and a list adds sites. Nothing is remembered on
this computer. The token is read from `IVN_TOKEN`, else `~/.ivendnext/token`. The signing key (only with `--key`, or
`--partner`) is read from `--key`, else `IVN_LIBRARY_KEY`, else `~/.ivendnext/library-signing.key`.


Exit code: 0 published (or waiting for the approval) · 1 refused (by the checks or by the library) · 2 usage.
Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
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
KIT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ed25519  # noqa: E402

URL = "https://library.ivendnext.app/v1/publish"
DOMAIN = b"ivendnext-library-upload/1\n"   # the library signs nothing else with your key: an upload is only an upload
PUBLIC_PREFIX, SECRET_PREFIX = "ivn-ed25519:", "ivn-ed25519-secret:"
DEFAULT_KEY = pathlib.Path.home() / ".ivendnext" / "library-signing.key"
TOKEN_FILE = DEFAULT_KEY.parent / "token"          # `login`'s token: only you can read it, never in a project or git
HOSTING = "https://hosting.ivendnext.app"           # where `login` asks for its code
TOKEN_RE = re.compile(r"ivn_tok_[A-Za-z0-9_-]{43}")
PARTNER_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")
FILES = ("app.json", "manifest.json", "library.json")


class Stop(Exception):
    """A refusal: printed, exit 1."""


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def key_id(public: bytes) -> str:
    """The id the library knows your key by: the first 16 hex characters of its SHA-256."""
    return hashlib.sha256(public).hexdigest()[:16]


# ── the signing key ───────────────────────────────────────────────────────────


def keygen(path: pathlib.Path) -> tuple[str, str]:
    """Make a key in `path` (never over an existing one); return (the line to send iVendNext, its key id)."""
    if path.exists():
        raise Stop(f"{path} exists already: keep it, or move it away first (a new key must be registered again)")
    secret = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(SECRET_PREFIX + b64u(secret) + "\n")
    public = ed25519.public_key(secret)
    return PUBLIC_PREFIX + b64u(public), key_id(public)


def load_key(path: str | None) -> bytes:
    line = os.environ.get("IVN_LIBRARY_KEY", "") if not path else ""
    if not line:
        p = pathlib.Path(path) if path else DEFAULT_KEY
        if not p.is_file():
            raise Stop(f"no signing key at {p}: make one with `publish.py keygen --register`, or publish with a token (`publish.py login`)")
        line = p.read_text("utf-8")
    line = line.strip()
    if not line.startswith(SECRET_PREFIX) or len(unb64u(line[len(SECRET_PREFIX):])) != 32:
        raise Stop("the signing key is not a key keygen made")
    return unb64u(line[len(SECRET_PREFIX):])


# ── reading the project ───────────────────────────────────────────────────────


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_checks(project: pathlib.Path) -> list[str]:
    """The kit's checks over what is uploaded (`library/`), and the licence check over the project. Refusals only."""
    check = _load("kit_check", KIT / "tools" / "check" / "check.py")
    licence = _load("kit_licence", KIT / "tools" / "check" / "licence.py")
    out, _ = check.run(project / "library")
    return [text for kind, text in out if kind == "REFUSED"] + licence.check(project)


def recipient_sha256(pem: str) -> str:
    """SHA-256 of the sealing key's DER bytes: the library checks it is the key it registered for you."""
    lines = pem.strip().splitlines()
    if not lines or lines[0] != "-----BEGIN PUBLIC KEY-----" or lines[-1] != "-----END PUBLIC KEY-----":
        raise Stop("library/recipient.pem is not a PEM public key (openssl rsa -pubout makes one)")
    return hashlib.sha256(base64.b64decode("".join(lines[1:-1]))).hexdigest()


def _json_from(env: str, file: str | None):
    """Customer addresses and key requests: from a file you name, else the environment, else none."""
    try:
        raw = pathlib.Path(file).read_text("utf-8") if file else os.environ.get(env, "")
        return json.loads(raw) if raw.strip() else []
    except (OSError, ValueError) as e:
        raise Stop(f"{file or env} is not readable JSON ({type(e).__name__})") from None


# ── the token: My apps' sign-in, by a code ───────────────────────────────────


def token_now() -> str | None:
    """A build server's token (`IVN_TOKEN`), else this computer's (`login`), else none."""
    t = os.environ.get("IVN_TOKEN", "").strip()
    if not t and TOKEN_FILE.is_file():
        t = TOKEN_FILE.read_text("utf-8").strip()
    if t and not TOKEN_RE.fullmatch(t):
        raise Stop("the token is not one My apps made: run login again, or make a new one on My apps > Tokens")
    return t or None


def keep_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")


def login(post=None, wait=time.sleep, out=print) -> str:
    """The device code: the hosting gives a code to type on My apps; this polls until the person has entered it."""
    post = post or (lambda path, body: send(os.environ.get("IVN_HOSTING_URL", HOSTING) + path, json.dumps(body).encode()))
    status, d = post("/v1/device", {})
    if status != 200 or "user_code" not in d:
        raise Stop(f"the sign-in could not start ({status}): {d.get('words') or d.get('refused')}")
    out(f"Open {d['verification_uri_complete']} and sign in with GitHub; the code {d['user_code']} is filled in for you "
        "(or enter it under A code from your terminal).")
    for _ in range(max(1, int(d.get("expires_in", 600)) // max(1, int(d.get("interval", 5))))):
        wait(int(d.get("interval", 5)))
        status, r = post("/v1/device/token", {"device_code": d["device_code"]})
        if status == 200 and r.get("token"):
            keep_token(r["token"])
            return r.get("company") or ""
        if r.get("refused") != "device_pending":
            raise Stop(r.get("words") or "the code was not entered in time: run login again")
    raise Stop("the code was not entered in time: run login again")


def token_payload(p: dict) -> dict:
    """The same publish, sent with a token: no company, time or nonce (the token and HTTPS stand for them), no seal."""
    return {k: v for k, v in p.items() if k not in ("partner", "at", "nonce", "recipient_sha256")}


def payload(project: pathlib.Path, partner: str, deliveries=(), keys=(), at: int | None = None, sealed: bool = True) -> dict:
    lib = project / "library"
    try:
        card, manifest, conf = (json.loads((lib / f).read_text("utf-8")) for f in FILES)
    except (OSError, ValueError) as e:
        raise Stop(f"library/ needs {', '.join(FILES)} and recipient.pem, each readable ({type(e).__name__}: {e})") from None
    if not isinstance(conf, dict) or set(conf) - {"public", "preview_sites", "desk_setup"}:
        raise Stop('library/library.json is {"public": true|false, "preview_sites": [site addresses], '
                   '"desk_setup": [{"need", "recipe"}] (optional: what the administrator sets in Desk first)}')
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
        raise Stop("library/manifest.json has no version")
    p = {"partner": partner, "at": int(time.time()) if at is None else at, "nonce": b64u(secrets.token_bytes(16)),
         "cmd": "publish", "version": manifest["version"], "card": card, "manifest": manifest,
         "public": bool(conf.get("public")), "preview_sites": conf.get("preview_sites") or [],
         "deliveries": list(deliveries), "keys": list(keys)}
    if conf.get("desk_setup"):  # the message's "Before the first sale, set up in Desk" part (J5-04)
        p["desk_setup"] = conf["desk_setup"]
    if not sealed:
        return p
    if (lib / "recipient.pem").is_file():
        p["recipient_sha256"] = recipient_sha256((lib / "recipient.pem").read_text("utf-8"))
    elif p["preview_sites"] or p["deliveries"] or p["keys"]:
        # keys come back sealed: without the file the library cannot tell you they are sealed to another key
        raise Stop("library/recipient.pem is missing: keys are sealed to it (see tools/publish/README.md)")
    return p


def envelope(p: dict, secret: bytes) -> bytes:
    """The upload: the payload's exact bytes and the signature over DOMAIN + those bytes. The library reads nothing
    else, so nothing can be changed on the way without the signature failing."""
    body = json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = ed25519.sign(secret, DOMAIN + body)
    return json.dumps({"v": 1, "key": key_id(ed25519.public_key(secret)), "body": b64u(body),
                       "sig": b64u(sig)}).encode()


def send(url: str, data: bytes, token: str | None = None) -> tuple[int, dict]:
    h = {"Content-Type": "application/json", "User-Agent": "iVendNext-kit-publish/1"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"refused": f"http_{e.code}", "words": "the library did not answer in JSON"}
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
        raise Stop(f"the library could not be reached or did not answer in JSON ({type(e).__name__}); nothing is "
                   "known to be published: run it again") from None


# ── what came back ────────────────────────────────────────────────────────────


def token_report(out: dict, keys_file: pathlib.Path) -> list[str]:
    """A token's answer: where the version went, each site's message to send (the form in force), and any keys for your
    apps in a file only you can read (never printed)."""
    lines = [f"PUBLISHED {out['app']} {out['version']} (upload {out.get('upload')})",
             f"  preview shelf: {'unchanged' if out['preview'].get('unchanged') else 'published'}"]
    for site in out.get("sites", []):
        lines.append(f"  {site['site']}: {site['version']}. Send this to the customer's administrator:")
        lines += ["    " + x for x in site["message"][site.get("send") or "shelf_key"].split("\n")]
    for h in out.get("removed", []):
        lines.append(f"  {h}: removed on My apps, nothing new sent")
    if "public" in out:
        lines.append("  public list: " + (out.get("words") or out["public"]) + (f" {out['card_url']}" if out.get("card_url") else ""))
    if out.get("keys") or out.get("preview_keys"):
        fd = os.open(keys_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({k: out.get(k, []) for k in ("preview_keys", "keys")}, f, indent=1)
        lines.append(f"  keys for your apps and your preview sites are in {keys_file} (only you can read it)")
    return lines


def report(out: dict, keys_file: pathlib.Path) -> list[str]:
    lines = [f"PUBLISHED {out['app']} {out['version']} (upload {out.get('upload')})",
             f"  preview shelf: {'unchanged' if out['preview'].get('unchanged') else 'published'}"
             f" (serial {out['preview']['serial']}), {len(out.get('preview_keys', []))} site key(s)"]
    for d in out.get("delivered", []):
        lines.append(f"  a customer's shelf: serial {d['serial']}, {len(d['keys'])} site key(s)")
    if "public" in out:
        lines.append({"listed": f"  public list: listed (catalogue serial {out.get('serial')})",
                      "unchanged": "  public list: this version is already listed",
                      "awaiting_approval": f"  public list: WAITING for iVendNext's approval, request {out.get('request')}"
                                           f" ({out.get('why')})"}.get(out["public"], f"  public list: {out['public']}"))
    sealed = {k: out.get(k, []) for k in ("preview_keys", "delivered", "keys")}
    if out.get("keys"):
        lines.append(f"  keys for your apps: {len(out['keys'])}")
    if any(sealed.values()):
        fd = os.open(keys_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        if hasattr(os, "fchmod"):  # an existing file keeps its mode on open: narrow it (not on Windows: see the README)
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(sealed, f, indent=1)
        lines.append(f"  keys are in {keys_file}, sealed to library/recipient.pem: open each with your private key "
                     "(tools/publish/README.md, Opening a key)")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="publish.py", description="Put your app in the iVendNext App library.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="sign this computer in to My apps by a code; keeps a token in ~/.ivendnext/token")
    g = sub.add_parser("keygen", help="make a signing key on this machine (kept until the signed upload goes)")
    g.add_argument("--key", default=str(DEFAULT_KEY), help=f"where to keep it (default {DEFAULT_KEY})")
    g.add_argument("--register", action="store_true", help="register it (an existing key at --key too) with your token")
    g.add_argument("--recipient", help="your sealing key's public half (library/recipient.pem), registered with it")
    g.add_argument("--replace", action="store_true", help="with --register: this key alone; every other stops at once")
    p = sub.add_parser("publish", help="check and upload your project's library/ folder")
    p.add_argument("project", help="your project folder, the one holding library/")
    p.add_argument("--partner", help="signed upload only: your company's code")
    p.add_argument("--key", help="signed upload only: your signing key file (default: IVN_LIBRARY_KEY, then the keygen default)")
    p.add_argument("--deliveries", help="a JSON file of customers and their sites to add (else LIBRARY_DELIVERIES)")
    p.add_argument("--keys", help="a JSON file of keys to issue for your apps (else LIBRARY_KEYS)")
    p.add_argument("--out", default="library-keys.json", help="where keys are written (default library-keys.json)")
    p.add_argument("--dry-run", action="store_true", help="check, print what would be sent, send nothing")
    p.add_argument("--no-remembered-deliveries", action="store_true", help=argparse.SUPPRESS)  # kept so old CI runs
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if a.cmd == "login":
            company = login()
            print(f"SIGNED IN for {company}: the token is in {TOKEN_FILE} (only you can read it; 30 days)")
            return 0
        if a.cmd == "keygen":
            kp = pathlib.Path(a.key)
            if not (a.register and kp.is_file()):
                line, kid = keygen(kp)
                print(f"KEY MADE: {a.key} (keep it private; back it up)\nits public line:\n{line}\nkey id {kid}")
            if a.register:
                tok = token_now()
                if not tok:
                    raise Stop("sign in first: publish.py login")
                public = ed25519.public_key(load_key(a.key))
                body = {"cmd": "signing-key", "signing_key": PUBLIC_PREFIX + b64u(public)}
                if a.recipient:
                    body["recipient"] = pathlib.Path(a.recipient).read_text("utf-8")
                if a.replace:
                    body["replace"] = True
                status, out = send(os.environ.get("IVN_LIBRARY_URL", URL), json.dumps(body).encode(), tok)
                if "refused" in out:
                    raise Stop(out.get("words") or out["refused"])
                print(f"REGISTERED: key {out['key']} for {out['partner']}")
            return 0
        if getattr(a, "no_remembered_deliveries", False):
            print("note: --no-remembered-deliveries does nothing now: nothing is remembered on this computer, and the "
                  "library sends each version to every site the app is on")
        project = pathlib.Path(a.project)
        if not (project / "library").is_dir():
            raise Stop(f"{project}/library is not a folder: see tools/publish/README.md")
        signed = bool(a.partner or a.key)
        if signed and not (a.partner and PARTNER_RE.fullmatch(a.partner)):
            raise Stop("--partner is your company's code: lower case, digits or -")
        tok = None if signed else token_now()
        if not signed and not tok:
            raise Stop("sign in first: publish.py login (or give a build server's token in IVN_TOKEN)")
        bad = run_checks(project)
        if bad:
            for b in bad:
                print("REFUSED: " + b)
            print(f"{len(bad)} refusal(s) from the kit's checks; nothing was sent")
            return 1
        pl = payload(project, a.partner or "-", _json_from("LIBRARY_DELIVERIES", a.deliveries),
                     _json_from("LIBRARY_KEYS", a.keys), sealed=signed)
        if signed:
            secret = load_key(a.key)
            data = envelope(pl, secret)
            how = f"key {key_id(ed25519.public_key(secret))}"
        else:
            data = json.dumps(token_payload(pl)).encode()
            how = "your token"
        if a.dry_run:
            print(f"DRY RUN: {pl['card'].get('app')} {pl['version']}, {len(data)} bytes, {how}"
                  f"; public {pl['public']}, {len(pl['preview_sites'])} preview site(s), {len(pl['deliveries'])} "
                  f"customer(s) added, {len(pl['keys'])} key request(s). Nothing was sent.")
            return 0
        status, out = send(os.environ.get("IVN_LIBRARY_URL", URL), data, tok)
        if "refused" in out:
            print(f"REFUSED by the library ({status}): {out['refused']}" + (f" — {out['words']}" if out.get("words") else ""))
            return 1
        print("\n".join((report if signed else token_report)(out, pathlib.Path(a.out))))
        return 0
    except Stop as e:
        print("REFUSED: " + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
