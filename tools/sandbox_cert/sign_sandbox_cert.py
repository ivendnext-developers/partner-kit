#!/usr/bin/env python3
"""Sign your payment connector's SANDBOX certificate: the paper a shop's Remote Connector record needs before it calls
your connector on a CitiXsys sandbox.

    python3 tools/sandbox_cert/sign_sandbox_cert.py --declaration declaration.json --partner acme --connector cash \
        > sandbox_certificate.json        # paste the file's text into the Remote Connector record

``--declaration`` is your connector's declaration as JSON (``-`` reads it from standard input); S22 prints its own with
``python3 samples/s22_customer_loyalty/service/wallet.py --declaration``. The partner and connector names are lower-case
letters and digits, 2 to 24 characters, starting with a letter.

The certificate is ``{"v": 1, "kid": "test-1", "payload": P, "signature": S}``: ``P`` holds the provider key
``remote_<partner>_<connector>``, the partner, the connector, the declaration and the time it was issued, and ``S`` is
the base64 Ed25519 signature over ``P``'s canonical JSON (sorted keys, no spaces, ASCII). It is signed with the
**published sandbox key** ``test-1``: public on purpose, accepted only on a CitiXsys sandbox, and refused by name on
every production site. ⛔ A production certificate is CitiXsys's alone: it is issued from your sealed conformance report,
and you never sign one yourself.

Source, in words: adapted from CitiXsys's private reference implementation's certificate tool @ 74c99d5 (a defect here
may be a defect there); its canonical form and the certificate's shape are copied from the iVendNext Payments code
repository's remote-connector app, its certificate module (``signing.py``: ``canonical``, and the envelope ``sign``
builds) @ 7f2201d, and the key from CitiXsys Payments' partner sandbox runbook, §4. The signing itself is done by the
``openssl`` command, not by that module's library; the known-answer test holds the two equal. Report a defect on the
Partner feedback forms. Needs OpenSSL 3.x (Ed25519) and no Python package; macOS's own ``openssl`` is LibreSSL, which
cannot sign Ed25519 this way: install OpenSSL 3 (for example with Homebrew) and put it first on your PATH.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

SANDBOX_KID = "test-1"
SANDBOX_PRIVATE_KEY = "PgljfQXjS4PprEn4F+5JXa0Htv6e5tpsPIdCBQ0xuuw="     # published: a CitiXsys sandbox key
SLUG = re.compile(r"^[a-z][a-z0-9]{1,23}$")
PKCS8_ED25519 = bytes.fromhex("302e020100300506032b657004220420")     # the DER prefix of a raw 32-byte Ed25519 key


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def ed25519_sign(message: bytes, private_key_b64: str) -> bytes:
    der = PKCS8_ED25519 + base64.b64decode(private_key_b64, validate=True)
    with tempfile.TemporaryDirectory() as d:
        key, msg = os.path.join(d, "k.der"), os.path.join(d, "m.bin")
        fd = os.open(key, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(der)
        with open(msg, "wb") as f:
            f.write(message)
        r = subprocess.run(["openssl", "pkeyutl", "-sign", "-keyform", "DER", "-inkey", key, "-rawin", "-in", msg],
                           capture_output=True)
        if r.returncode:
            raise ValueError("openssl could not sign (it needs OpenSSL 3.x, not LibreSSL): "
                             + r.stderr.decode(errors="replace").strip()[:300])
        return r.stdout


def certificate(declaration: dict, partner: str, connector: str, issued: str) -> dict:
    for what, v in (("partner", partner), ("connector", connector)):
        if not SLUG.match(v):
            raise ValueError(f"the {what} name must be 2-24 lower-case letters and digits, starting with a letter: {v!r}")
    payload = {"provider_key": f"remote_{partner}_{connector}", "partner": partner, "connector": connector,
               "declaration": declaration, "issued": issued}
    return {"v": 1, "kid": SANDBOX_KID, "payload": payload,
            "signature": base64.b64encode(ed25519_sign(canonical(payload), SANDBOX_PRIVATE_KEY)).decode()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="sign a payment connector's SANDBOX certificate with the published key")
    p.add_argument("--declaration", required=True, help="the declaration as a JSON file, or - for standard input")
    p.add_argument("--partner", required=True, help="your partner name: lower-case letters and digits")
    p.add_argument("--connector", required=True, help="the connector's name: lower-case letters and digits")
    a = p.parse_args(argv)
    raw = sys.stdin.read() if a.declaration == "-" else open(a.declaration).read()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        print(json.dumps(certificate(json.loads(raw), a.partner, a.connector, now), indent=1))
    except ValueError as e:
        sys.exit(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
