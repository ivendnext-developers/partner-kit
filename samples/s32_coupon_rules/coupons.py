"""S32 — *Coupon rules*: the pure core (no framework, no network), shared by the service and its tests.

A **check before payment** (``check/1``): when the cashier presses Pay, the shop's server sends its own priced basket,
whose ``coupon_codes`` names each coupon on the sale (the Coupon record's name, its ``id``). The shop keeps one rule
record per coupon (``<prefix> Rule``, named by the coupon). ``on_check`` refuses a coupon whose rule says:

- **only for one customer group**, when the sale's customer is not in that group (exactly that group: a parent group
  does not reach its children, as the product's own item groups);
- **first purchase only**, when the customer has bought before (``prior_sales``: the service counts the customer's
  submitted sales in the shop), or when the sale names no customer. The till always names one (its walk-in customer
  when the cashier has added none, who has usually bought before), so the refusal says to add the new customer.

A coupon with no rule record, or with its rule switched off, is never refused; a sale with no coupon is allowed without
reading the shop. The rules apply on every stage: an exchange rung without its sale carries the coupons of what it sells.

⛔ No answer moves money: no price, no line, no payment. A refused sale is not paid: the till goes back to the basket,
the cashier removes the coupon and presses Pay again. The door before any money refuses a sale without an allowing answer
for exactly this basket, so an allowed coupon cannot be followed by another line or coupon without asking again.

``verify`` and ``plain`` are S23's (``samples/s23_till_guard/guard.py``), copied: a defect there is a defect here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
RULE_FIELDS = ("name", "coupon", "enabled", "first_purchase_only", "customer_group")


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


def _text_or_none(value) -> bool:
    return value is None or isinstance(value, str)


def check_context(body: dict) -> dict:
    """The check's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    codes = ctx.get("coupon_codes")
    if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
        raise ValueError("coupon_codes is a list of text")
    if not (_text_or_none(ctx.get("customer")) and _text_or_none(ctx.get("customer_group"))):
        raise ValueError("customer and customer_group are text")
    return ctx


def rules_of(records) -> dict:
    """The shop's rules, from its own Rule records: ``{coupon: {"first": bool, "group": str}}`` for each switched-on record
    that names a coupon. A record with neither rule set refuses nothing. Anything that is not a list of records is
    ``ValueError`` (the service then answers 503: nothing was judged)."""
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("the shop's rules are not a list of records")
    out = {}
    for r in records:
        coupon = r.get("coupon")
        if not r.get("enabled") or not isinstance(coupon, str) or not coupon:
            continue
        group = r.get("customer_group")
        out[coupon] = {"first": bool(r.get("first_purchase_only")), "group": group if isinstance(group, str) else ""}
    return out


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable, no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def on_check(ctx: dict, rules: dict, prior_sales) -> dict:
    """The answer for one check. Every group rule first (they read nothing), then every first-purchase rule, which asks
    ``prior_sales(customer)`` at most once; the first refusal is the answer, else allow."""
    mine = [c for c in ctx["coupon_codes"] if c in rules]     # in the sale's order (sorted, by the contract)
    for c in mine:
        group = rules[c]["group"]
        if group and (ctx.get("customer_group") or "") != group:
            return {"verdict": "refuse", "reason": plain(
                f"Coupon {plain(c, 30)} is only for customers in {plain(group, 30)}. "
                "Remove it, or add a customer in that group.")}
    firsts = [c for c in mine if rules[c]["first"]]
    if firsts:
        c, customer = firsts[0], ctx.get("customer") or ""
        if not customer:
            return {"verdict": "refuse", "reason": plain(
                f"Coupon {plain(c, 40)} is for a first purchase only. Add the customer to the sale first.")}
        if prior_sales(customer) > 0:
            return {"verdict": "refuse", "reason": plain(
                f"Coupon {plain(c, 30)} is for a first purchase only; this customer has bought before. "
                "Remove it, or add the new customer.")}
    return {"verdict": "allow"}
