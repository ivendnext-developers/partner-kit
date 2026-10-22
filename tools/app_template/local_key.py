#!/usr/bin/env python3
"""Library keys for a shop on your own machine, so the many-shops handshake runs on your laptop (local mode).

The App library signs a real key for a real site, and its signing keys never leave AWS. For a shop on this machine
(a local bench at http://shop.localhost:8000, say) you make your own key pair and sign the key yourself; the app
accepts it in local mode only (`IVN_LOCAL=1`), and only for a shop on this machine. Standard library only.

    python3 tools/app_template/local_key.py keygen --out .local-keys
        # writes .local-keys/library.secret (yours alone) and .local-keys/library_keys.json (the public half)
    python3 tools/app_template/local_key.py sign --secret .local-keys/library.secret \\
        --app ivendnext_hello --site shop.localhost:8000
        # prints the key line the shop hands over at connect ("IVN1-…")

Then run the app with IVN_LOCAL=1, IVN_SHOPS_FILE and IVN_LOCAL_LIBRARY_KEYS=.local-keys/library_keys.json.
Never commit the secret, and never use these keys for a real shop: they prove nothing but that you made them.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "service"))
import ed25519  # noqa: E402
import shops  # noqa: E402

KID = "LOCAL"       # never one of the pinned kids (L1, F1)


def keygen(out: pathlib.Path, force: bool = False) -> tuple[pathlib.Path, pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    seed, secret_file, keys_file = secrets.token_bytes(32), out / "library.secret", out / "library_keys.json"
    if secret_file.exists() and not force:     # a new pair stops every key the old one signed: said out loud
        raise SystemExit(f"{secret_file} exists: keys you signed with it stop working if you replace it (--force)")
    fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(secret_file, 0o600)               # readable by this user alone, an older file's mode included
    with os.fdopen(fd, "w") as f:
        f.write(base64.b64encode(seed).decode() + "\n")
    public = base64.b64encode(ed25519.public_key(seed)).decode()
    keys_file.write_text(json.dumps({KID: [public, ["paid", "free"]]}, indent=1) + "\n", "utf-8")
    return secret_file, keys_file


def sign(seed: bytes, app: str, site: str, kind: str = "paid") -> str:
    if not shops.is_local(site):
        raise SystemExit(f"{site!r} is not a shop on this machine (localhost, <name>.localhost, 127.0.0.1 or [::1])")
    payload = {"typ": "applib-key", "v": 1, "kid": KID, "id": "LOCAL" + secrets.token_hex(4).upper(), "app": app,
               "host": site, "to": "free" if kind == "free" else "customer:local", "kind": kind, "exp": None}
    pb = json.dumps(payload, separators=(",", ":")).encode()

    def b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    return f"IVN1-{b64u(pb)}.{b64u(ed25519.sign(seed, pb))}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("keygen", help="make a key pair for local mode")
    g.add_argument("--out", default=".local-keys", help="the folder to write it to (default .local-keys)")
    g.add_argument("--force", action="store_true", help="replace a key pair made before (its keys stop working)")
    s = sub.add_parser("sign", help="sign a library key for a shop on this machine")
    s.add_argument("--secret", required=True, help="the library.secret keygen wrote")
    s.add_argument("--app", required=True, help="your app's id in the App library (IVN_LIBRARY_APP)")
    s.add_argument("--site", required=True, help="the shop's name with its port, e.g. shop.localhost:8000")
    s.add_argument("--kind", choices=("paid", "free"), default="paid")
    a = ap.parse_args(argv)
    if a.command == "keygen":
        secret_file, keys_file = keygen(pathlib.Path(a.out), a.force)
        print(f"secret: {secret_file}  (never commit it)\npublic: {keys_file}  (IVN_LOCAL_LIBRARY_KEYS)")
        return 0
    seed = base64.b64decode(pathlib.Path(a.secret).read_text().strip())
    print(sign(seed, a.app, a.site.strip().lower(), a.kind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
