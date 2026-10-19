"""Receiving iVendNext webhooks safely — the reference implementation of recipes/webhook_receiver.md.

1. VERIFY: header ``X-Frappe-Webhook-Signature`` = base64(HMAC-SHA256(secret, body)). The sender signs
   ``json.dumps(data)`` and sends ``json.dumps(data, default=str)``; for a payload of plain JSON values the
   two are the same bytes, so we verify over the RAW BODY (any language can). If that fails we also try the
   sender's own form, ``json.dumps(json.loads(body))``, and record which one matched (measured on our test bench).
2. REPLAY: nothing in the payload is signed with a time, so a captured request stays valid for ever. We keep
   a seen-set keyed on record type + name + event + ``modified``.
3. IDEMPOTENCY and MISSED DELIVERIES are the caller's (app.py): every handler is safe to run twice, and a
   reconciliation pull finds what no webhook delivered.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

HEADER = "X-Frappe-Webhook-Signature"


def _sign(secret: str, payload: bytes) -> bytes:
    return base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest())


def verify(body: bytes, signature: str | None, secret: str) -> tuple[dict | None, str]:
    """``(data, how)`` when the signature holds — ``how`` is "raw-body" or "re-serialised" — else ``(None, why)``."""
    if not signature:
        return None, "no signature header"
    sig = signature.strip().encode()
    how = "raw-body" if hmac.compare_digest(_sign(secret, body), sig) else None   # HMAC first, parse after
    try:
        data = json.loads(body)
    except ValueError:
        return None, "the signature does not match" if how is None else "the body is not JSON"
    if not isinstance(data, dict):
        return None, "the body is not a JSON object"
    if how is None and hmac.compare_digest(_sign(secret, json.dumps(data).encode()), sig):
        how = "re-serialised"
    return (data, how) if how else (None, "the signature does not match")


def replay_key(data: dict) -> str | None:
    """The seen-set key: record type + name + event + modified. None if the payload lacks one of them."""
    parts = [data.get(k) for k in ("doctype", "name", "event", "modified")]
    return "|".join(str(p) for p in parts) if all(parts) else None
