"""S34 — *Purchase orders checked by your ERP*: the pure core (no framework, no network), shared by the service and its tests.

One extension point, the **document check** (``doccheck/1``): when a buyer submits a Purchase Order, from Desk, an import
or the API, the shop's server sends the fields the subscription names and waits for one answer. ``on_check`` asks the ERP
(here a stand-in, ``erp.py``) three things, in this order:

1. **Is the supplier on hold?** → ``refuse`` with the ERP's reason. The order stays a draft and the buyer reads why.
2. **Is the order over what the company has left of its monthly purchasing budget?** → ``approve`` by the role
   *Purchase Manager*, whoever submits: a user without the role is refused, and one who holds it is asked to approve.
   (The budget is the company's, never the submitting user's, so a colleague with budget left cannot skip the approval.)
3. **All clear** → ``fill`` the ERP's own order number into ``<app>_erp_number``, the field the manifest adds to
   Purchase Order. The order is submitted carrying it.

⛔ The answer never writes money: ``fill`` names only the field the subscription lets it fill. A draft's save is never
asked (the manifest's ``on_validate`` is false); if a shop turns it on, a draft is allowed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the user reads: plain text, 1 to 140 characters
APPROVER = "Purchase Manager"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def check_context(body: dict) -> dict:
    """The document check's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "doccheck/1":
        raise ValueError("not a doccheck/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("event") not in ("submit", "validate"):
        raise ValueError("no context")
    if ctx.get("doctype") != "Purchase Order":
        raise ValueError("this app checks purchase orders only")
    f = ctx.get("fields")
    if not isinstance(f, dict) or not isinstance(f.get("supplier"), str) or not f["supplier"]:
        raise ValueError("no supplier")
    total = f.get("grand_total")
    if not (isinstance(total, dict) and isinstance(total.get("minor"), int) and isinstance(total.get("currency"), str)
            and isinstance(total.get("currency_exponent"), int)):
        raise ValueError("the total is whole minor units with its currency")
    return ctx


def money(minor: int, currency: str, exponent: int) -> str:
    return f"{minor / 10 ** exponent:,.{exponent}f} {currency}"


def text(s: str) -> str:
    """One plain-text sentence the user reads: no markup, at most TEXT_MAX characters."""
    s = " ".join(str(s).replace("<", "").replace(">", "").split())
    return s if len(s) <= TEXT_MAX else s[: TEXT_MAX - 1] + "…"


def on_check(ctx: dict, erp, field: str) -> dict:
    """The answer for one purchase order. ``erp`` is the ERP client (``erp.StandIn`` here); ``field`` the fill field."""
    if ctx["event"] != "submit":
        return {"verdict": "allow"}
    f = ctx["fields"]
    hold = erp.supplier_hold(f["supplier"])
    if hold:
        return {"verdict": "refuse", "reason": text(f"The ERP holds this supplier: {hold}")}
    total = f["grand_total"]
    left = erp.budget_left(ctx["company"], total["currency"])
    if left is not None and total["minor"] > left:
        return {"verdict": "approve", "role": APPROVER,
                "reason": text(f"Over the monthly budget: {money(max(left, 0), total['currency'], total['currency_exponent'])} left.")}
    return {"verdict": "fill", "fields": {field: erp.order_number(ctx["name"])}}
