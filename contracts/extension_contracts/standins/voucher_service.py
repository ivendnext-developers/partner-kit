# Source: ivendnext/iVendNext_PWA apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contracts/standins/voucher_service.py @ 7d47d331a203, copied unchanged: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board.
# Copyright (c) 2026, CitiXsys Technologies and contributors
# For license information, please see license.txt
"""A stand-in voucher service for extension point ``fulfil`` (P-FULFIL) — the two promises
a partner's service keeps, in the fewest lines (``docs/extending/partner_fulfil.md`` §4):

1. the same ``idempotency_key`` always returns the same code;
2. a ``void`` on a key wins over any later ``issue`` on it.

``VoucherService.answer(raw_body, headers)`` takes the POST iVendNext sends and returns the
JSON answer (bytes). It checks the signature (``X-iVendNext-Signature``: base64 HMAC-SHA256
of ``<timestamp>.<body>`` with the shared secret) and refuses a call more than five minutes
old. ``serve(port)`` puts it behind a plain HTTP server for a local try-out (put HTTPS in
front of it for a shop). No framework, no database: a real service keeps ``codes`` and
``voided`` in its own store. Its conformance test: ``tests/test_partner_fulfil_standin.py``."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

SIGNATURE_HEADER = "X-iVendNext-Signature"
TIMESTAMP_HEADER = "X-iVendNext-Timestamp"
SKEW_S = 300


class VoucherService:
    def __init__(self, secret: str, denomination_left: int = 1000):
        self.secret = secret
        self.codes: dict[str, str] = {}  # idempotency_key -> ref
        self.voided: set[str] = set()  # keys a void has reached, and refs it cancelled
        self.left = denomination_left
        self.lock = threading.Lock()

    def _signed(self, raw: bytes, headers: dict) -> bool:
        stamp = headers.get(TIMESTAMP_HEADER, "")
        given = headers.get(SIGNATURE_HEADER, "")
        if not stamp.isdigit() or abs(time.time() - int(stamp)) > SKEW_S:
            return False
        mac = hmac.new(self.secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256)
        return hmac.compare_digest(base64.b64encode(mac.digest()).decode(), given)

    def answer(self, raw: bytes, headers: dict) -> tuple[int, bytes]:
        if not self._signed(raw, headers):
            return 401, b'{"error":"bad signature"}'
        context = json.loads(raw)["context"]
        key = context["idempotency_key"]
        with self.lock:
            if context["call"] == "void":
                self.voided.add(key)
                if context.get("ref"):
                    self.voided.add(context["ref"])
                return 200, json.dumps({"verdict": "voided"}).encode()
            if key in self.voided:  # promise 2: a voided key is never issued on
                return (
                    200,
                    json.dumps(
                        {"verdict": "refuse", "reason": "This code was cancelled."}
                    ).encode(),
                )
            if key not in self.codes:  # promise 1: one code per key, however often asked
                if self.left <= 0:
                    return (
                        200,
                        json.dumps(
                            {"verdict": "refuse", "reason": "None left in this denomination."}
                        ).encode(),
                    )
                self.left -= 1
                self.codes[key] = "GZ-" + secrets.token_hex(4).upper()
            ref = self.codes[key]
        pin = " ".join(str(int(ref[3:], 16) % 10**12).zfill(12)[i : i + 4] for i in (0, 4, 8))
        return (
            200,
            json.dumps(
                {"verdict": "issued", "ref": ref, "lines": [f"PIN {pin}", "Valid for one year"]}
            ).encode(),
        )


def serve(port: int, secret: str) -> None:  # pragma: no cover - a local try-out
    from http.server import BaseHTTPRequestHandler, HTTPServer

    service = VoucherService(secret)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            status, body = service.answer(raw, dict(self.headers))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
