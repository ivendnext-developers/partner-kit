"""Receiving iVendNext webhooks safely — the reference implementation of recipes/webhook_receiver.md.

1. VERIFY: header ``X-Frappe-Webhook-Signature`` = base64(HMAC-SHA256(secret, body)). The sender signs
   and lays out the body in its own way, which differs between releases (on one line, or indented with its keys
   sorted). So we verify over the RAW BODY (any language can), before anything is parsed, and never rebuild it first:
   a body that does not verify as received is refused.
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
    """``(data, "raw-body")`` when the signature holds over the bytes received, else ``(None, why)``."""
    if not signature:
        return None, "no signature header"
    if not hmac.compare_digest(_sign(secret, body), signature.strip().encode()):   # HMAC first, parse after
        return None, "the signature does not match"
    try:
        data = json.loads(body)
    except ValueError:
        return None, "the body is not JSON"
    if not isinstance(data, dict):
        return None, "the body is not a JSON object"
    return data, "raw-body"


def replay_key(data: dict) -> str | None:
    """The seen-set key: record type + name + event + modified. None if the payload lacks one of them."""
    parts = [data.get(k) for k in ("doctype", "name", "event", "modified")]
    return "|".join(str(p) for p in parts) if all(parts) else None
