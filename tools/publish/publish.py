#!/usr/bin/env python3
"""publish — put your app in the iVendNext App library from any machine, with or without GitHub.

    python3 tools/publish/publish.py keygen [--key FILE]
    python3 tools/publish/publish.py publish <project folder> --partner <your code> [--key FILE]
                                     [--deliveries FILE] [--no-remembered-deliveries] [--keys FILE] [--out FILE] [--dry-run]

`keygen` makes your company's signing key on this machine and prints the line to send iVendNext once, when you join:
we register it with your sealing key (`library/recipient.pem`). The private half never leaves your machine.

`publish` reads your project's `library/` folder — `app.json` (the card), `manifest.json` (your app), `library.json`
(`{"public": true|false, "preview_sites": [...]}`) and `recipient.pem` — runs the kit's checks over it
(`tools/check/check.py`, and `tools/check/licence.py` over the project), signs it and uploads it. We take only these
files: never your source code. It prints what the library did: your preview shelf, your customers' shelves, the public
list (a first listing, or a version that does more than the last, waits for one approval by iVendNext), and keys.
Keys come back sealed to your `recipient.pem` and are written to a file (`library-keys.json`, readable by you only),
never printed.

Your customers' site addresses and the keys you ask for are never in the kit or your project: they come from the
environment (`LIBRARY_DELIVERIES`, `LIBRARY_KEYS`, as JSON) or from a file you name (`--deliveries`, `--keys`).
After a publish that names customers, this machine remembers them for that app in `~/.ivendnext/deliveries/` (a file
only you can read, outside every project), and the next publish with no list includes them, so an update cannot leave
a customer behind by omission. A list you give replaces the remembered one; `--no-remembered-deliveries` publishes to none.
The signing key is read from `--key`, else `IVN_LIBRARY_KEY` (the key's line, for a CI secret), else
`~/.ivendnext/library-signing.key`.

Exit code: 0 published (or waiting for the approval) · 1 refused (by the checks or by the library) · 2 usage.
Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
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
REMEMBER_DIR = DEFAULT_KEY.parent / "deliveries"   # beside the signing key, never in a project, never in git
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
            raise Stop(f"no signing key at {p}: make one with `publish.py keygen` and send iVendNext the line it prints")
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


def _explicit(env: str, file: str | None) -> bool:
    """True when this publish names its customers itself (a list, even an empty one), so none are remembered in its place."""
    if file:
        try:
            return bool(pathlib.Path(file).read_text("utf-8").strip())   # a blank file names no one, as a blank variable does
        except OSError:
            return True
    return bool(os.environ.get(env, "").strip())


def remembered_path(partner: str, app: str) -> pathlib.Path:
    return REMEMBER_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", partner) + "." + re.sub(r"[^A-Za-z0-9_-]", "_", app) + ".json")


def recall(path: pathlib.Path) -> list:
    """The customers remembered for this app, or none. A file that cannot be read stops the publish: skipping it would
    leave those customers on the old version without a word."""
    if not path.is_file():
        return []
    try:
        found = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        found = None
    if not isinstance(found, list):
        raise Stop(f"{path} is not a list of customers: mend or delete it, or publish with --no-remembered-deliveries")
    return found


def remember(path: pathlib.Path, deliveries: list) -> None:
    """Keep the customers just published to, as given, in a file only you can read (written whole, then moved into place)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(deliveries, f, indent=1)
    os.replace(tmp, path)


def payload(project: pathlib.Path, partner: str, deliveries=(), keys=(), at: int | None = None) -> dict:
    lib = project / "library"
    try:
        card, manifest, conf = (json.loads((lib / f).read_text("utf-8")) for f in FILES)
    except (OSError, ValueError) as e:
        raise Stop(f"library/ needs {', '.join(FILES)} and recipient.pem, each readable ({type(e).__name__}: {e})") from None
    if not isinstance(conf, dict) or set(conf) - {"public", "preview_sites"}:
        raise Stop('library/library.json is {"public": true|false, "preview_sites": [site addresses]}')
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
        raise Stop("library/manifest.json has no version")
    p = {"partner": partner, "at": int(time.time()) if at is None else at, "nonce": b64u(secrets.token_bytes(16)),
         "cmd": "publish", "version": manifest["version"], "card": card, "manifest": manifest,
         "public": bool(conf.get("public")), "preview_sites": conf.get("preview_sites") or [],
         "deliveries": list(deliveries), "keys": list(keys)}
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


def send(url: str, data: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "iVendNext-kit-publish/1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"refused": f"http_{e.code}", "words": "the library did not answer in JSON"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Stop(f"the library could not be reached or did not answer in JSON ({type(e).__name__}); nothing is "
                   "known to be published: run it again") from None


# ── what came back ────────────────────────────────────────────────────────────


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
    g = sub.add_parser("keygen", help="make your company's signing key on this machine")
    g.add_argument("--key", default=str(DEFAULT_KEY), help=f"where to keep it (default {DEFAULT_KEY})")
    p = sub.add_parser("publish", help="check, sign and upload your project's library/ folder")
    p.add_argument("project", help="your project folder, the one holding library/")
    p.add_argument("--partner", required=True, help="your company's code, as iVendNext registered it")
    p.add_argument("--key", help="your signing key file (default: IVN_LIBRARY_KEY, then the keygen default)")
    p.add_argument("--deliveries", help="a JSON file of customers' shelves (else LIBRARY_DELIVERIES)")
    p.add_argument("--no-remembered-deliveries", action="store_true",
                   help="publish to no customer unless you give a list (the ones remembered from your last publish are left out)")
    p.add_argument("--keys", help="a JSON file of keys to issue for your apps (else LIBRARY_KEYS)")
    p.add_argument("--out", default="library-keys.json", help="where sealed keys are written (default library-keys.json)")
    p.add_argument("--dry-run", action="store_true", help="check and sign, print what would be sent, send nothing")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if a.cmd == "keygen":
            line, kid = keygen(pathlib.Path(a.key))
            print(f"KEY MADE: {a.key} (keep it private; back it up)\n"
                  f"Send iVendNext this line, once, to register it (it is public):\n{line}\nkey id {kid}")
            return 0
        project = pathlib.Path(a.project)
        if not (project / "library").is_dir():
            raise Stop(f"{project}/library is not a folder: see tools/publish/README.md")
        if not PARTNER_RE.fullmatch(a.partner):
            raise Stop("--partner is your company's code: lower case, digits or -")
        bad = run_checks(project)
        if bad:
            for b in bad:
                print("REFUSED: " + b)
            print(f"{len(bad)} refusal(s) from the kit's checks; nothing was sent")
            return 1
        secret = load_key(a.key)
        given = _json_from("LIBRARY_DELIVERIES", a.deliveries)
        named = _explicit("LIBRARY_DELIVERIES", a.deliveries)
        pl = payload(project, a.partner, given, _json_from("LIBRARY_KEYS", a.keys))
        mem = remembered_path(a.partner, str(pl["card"].get("app") or pl["manifest"].get("app") or "app"))
        if not named and not a.no_remembered_deliveries:
            pl["deliveries"] = recall(mem)
            if pl["deliveries"]:
                n = len(pl["deliveries"])
                print(f"including {n} customer{'s' if n != 1 else ''} remembered from your last publish "
                      "(--no-remembered-deliveries leaves them out)")
            if pl["deliveries"] and not (project / "library" / "recipient.pem").is_file():
                raise Stop("library/recipient.pem is missing: keys are sealed to it (see tools/publish/README.md)")
        data = envelope(pl, secret)
        if a.dry_run:
            print(f"DRY RUN: {pl['card'].get('app')} {pl['version']}, {len(data)} bytes, key {key_id(ed25519.public_key(secret))}"
                  f"; public {pl['public']}, {len(pl['preview_sites'])} preview site(s), {len(pl['deliveries'])} "
                  f"customer(s), {len(pl['keys'])} key request(s). Nothing was sent.")
            return 0
        status, out = send(os.environ.get("IVN_LIBRARY_URL", URL), data)
        if "refused" in out:
            print(f"REFUSED by the library ({status}): {out['refused']}" + (f" — {out['words']}" if out.get("words") else ""))
            return 1
        print("\n".join(report(out, pathlib.Path(a.out))))
        if named:   # only a publish the library accepted changes what is remembered
            try:
                had = recall(mem)
                if had and len(had) > len(pl["deliveries"]):
                    print(f"this list replaces the {len(had)} customers remembered for this app: later updates with no "
                          f"list go to these {len(pl['deliveries'])} only")
                remember(mem, pl["deliveries"])
            except (OSError, Stop) as e:
                print(f"published; but the customers could not be remembered for next time ({type(e).__name__}): "
                      "name them again next time")
        return 0
    except Stop as e:
        print("REFUSED: " + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
