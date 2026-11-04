"""S17 — a partner page framed by the shop: the pure core (no framework, no network), shared by the service and its tests.

When a cashier presses the page's till key, or a Desk user opens the page, the shop opens our page with a signed
context in the address's FRAGMENT (``…/board/#ctx=<payload>.<signature>``), so it never reaches a server log or a
``Referer``. The page's own script reads it and sends it here; ``read_context`` checks it:

* the SIGNATURE — base64url HMAC-SHA256 of the payload's bytes with the subscription's secret (the installer handed it
  back once, as ``pp_pge:sub:board``);
* the EXPIRY — ``exp``, five minutes after ``iat``.

On the till the page answers server to server, and the shop takes one answer: ``submit_body`` + ``sign`` make the signed POST to the shop's
``ivendnext_mpos.api.page.submit`` (``X-iVendNext-Timestamp`` and ``X-iVendNext-Signature``: base64 HMAC-SHA256 of
``<timestamp>.<body>``). The till takes ``message`` and ``sale_attributes`` from a page — nothing that carries money.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time

ATTRIBUTE = "PP PGE Delivery Order"     # the sale detail this app's manifest installs
CLOCK_SKEW_S = 60


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def read_context(ctx, secret: str, now: float | None = None) -> tuple[dict | None, str]:
    """``(payload, "")`` for a context the shop signed that has not run out, else ``(None, why)``. ⛔ The HMAC is
    checked BEFORE the payload is parsed, and over the bytes as they came."""
    if not isinstance(ctx, str) or ctx.count(".") != 1 or len(ctx) > 16384:
        return None, "the context is not one the shop made"
    body, sig = ctx.split(".")
    try:
        raw, got = _unb64(body), _unb64(sig)
    except (binascii.Error, ValueError):
        return None, "the context is not one the shop made"
    if not hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).digest(), got):
        return None, "the context's signature does not match"
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, "the context is not one the shop made"
    now = now or time.time()
    if not isinstance(payload, dict) or payload.get("v") != 1 or not isinstance(payload.get("nonce"), str):
        return None, "the context is not one the shop made"
    if not isinstance(payload.get("exp"), int) or now > payload["exp"] or payload.get("iat", 0) > now + CLOCK_SKEW_S:
        return None, "the context has run out; open the page again"
    return payload, ""


def where(payload: dict) -> dict:
    """What the page shows about where it was opened: the till (store, POS Profile, the sale's lines) or Desk (a record)."""
    if payload.get("doctype"):
        return {"on": "desk", "doctype": payload["doctype"], "name": payload.get("name")}
    sale = payload.get("sale") or {}
    return {"on": "till", "store": payload.get("store"), "pos_profile": payload.get("pos_profile"),
            "sale_ref": sale.get("sale_ref"), "lines": len(sale.get("lines") or [])}


def delivery_order(nonce: str) -> str:
    """The partner's delivery order number for this opening — its own numbering (here derived from the nonce)."""
    return "TB-" + str(int(hashlib.sha256(nonce.encode()).hexdigest()[:8], 16) % 100000).zfill(5)


def submit_body(nonce: str, order: str, note: str | None = None) -> bytes:
    result = {"sale_attributes": [{"sale_attribute": ATTRIBUTE, "attribute_value": order}]}
    if note:
        result["message"] = {"title": "Delivery booked", "body": note[:280], "level": "success"}
    return json.dumps({"ctx_nonce": nonce, "result": result}, sort_keys=True, separators=(",", ":")).encode()


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).digest()).decode()
