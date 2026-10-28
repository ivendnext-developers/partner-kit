"""S32 — *Coupon rules*: the pure core (no framework, no network), shared by the service and its tests.

A **check before payment** (``check/1``): when the cashier presses Pay, the shop's server sends its own priced basket,
whose ``coupon_codes`` names each coupon on the sale (the Coupon record's name, its ``id``). The shop keeps one rule
record per coupon (``<prefix> Rule``, named by the coupon). ``on_check`` refuses a coupon whose rule says:

- **only for one customer group**, when the sale's customer is not in that group (exactly that group: a parent group
  does not reach its children, as the product's own item groups);
- **first purchase only**, when the customer has bought before (``prior_sales``: the service counts the customer's
  submitted sales in the shop), or when the sale names no customer. The till always names one (its walk-in customer
  when the cashier has added none, who has usually bought before), so the refusal says to add the new customer;
- **a sale needed for each use** (1.1.0): on a sale (``stage`` ``sale``), every coupon whose rule names an amount takes
  that much of the sale's total (``totals.grand_minor``: as rounded for payment, after its discounts, the coupons' own
  included, tax included; an exchange's is the difference the customer pays); when their sum is more than the total, the
  coupons are refused. The amount is read in the sale's own currency, rounded up to its minor unit. The check sees each coupon once (``coupon_codes`` is a
  set of names) and never a coupon's own amount, so the cap is per coupon: a coupon of 100 for each 1,000 spent is a rule
  of 1,000 on each such coupon, and two of them need a sale of 2,000.

A coupon with no rule record, or with its rule switched off, is never refused; a sale with no coupon is allowed without
reading the shop. The group and first-purchase rules apply on every stage: an exchange rung without its sale carries the
coupons of what it sells. A coupon that needs a sale is refused on the ``return`` stage (a no-receipt exchange the customer
is paid back on: its sold lines would carry the coupon's discount into the money paid out); a return against its sale
carries no coupon (the till clears them).

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
from decimal import ROUND_CEILING, Decimal, InvalidOperation

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
RULE_FIELDS = ("name", "coupon", "enabled", "first_purchase_only", "customer_group", "spend_per_use")   # the manifest's fields (test_manifest pins them); the read takes every field


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
    exp, totals = ctx.get("currency_exponent"), ctx.get("totals")
    if not _whole(exp) or not 0 <= exp <= 4 or not isinstance(totals, dict) or not _whole(totals.get("grand_minor")):
        raise ValueError("currency_exponent and totals.grand_minor are whole numbers")
    return ctx


def _whole(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool)


def _amount(value) -> Decimal:
    """A rule's *Sale needed for each use*, in the sale's currency: 0 when blank, absent (a retailer on 1.0.1, whose
    record has no such field), not a number or not above 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return Decimal(0)
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return Decimal(0)
    return d if d.is_finite() and d > 0 else Decimal(0)


def rules_of(records) -> dict:
    """The shop's rules, from its own Rule records: ``{coupon: {"first": bool, "group": str, "spend": Decimal}}`` for each
    switched-on record that names a coupon. A record with no rule set refuses nothing. Anything that is not a list of
    records is ``ValueError`` (the service then answers 503: nothing was judged)."""
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("the shop's rules are not a list of records")
    out = {}
    for r in records:
        coupon = r.get("coupon")
        if not r.get("enabled") or not isinstance(coupon, str) or not coupon:
            continue
        group = r.get("customer_group")
        out[coupon] = {"first": bool(r.get("first_purchase_only")), "group": group if isinstance(group, str) else "",
                       "spend": _amount(r.get("spend_per_use"))}
    return out


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable, no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def money(minor: int, exponent: int, currency: str = "") -> str:
    """``minor`` units as the till shows an amount: ``AED 1,450.00``."""
    whole, frac = divmod(abs(minor), 10 ** exponent)
    text = ("-" if minor < 0 else "") + f"{whole:,}" + (f".{frac:0{exponent}d}" if exponent else "")
    return f"{plain(currency, 3)} {text}".strip()


def over_cap(ctx: dict, rules: dict, mine: list) -> dict | None:
    """The refusal when the sale's capped coupons need more of its total than it has, else ``None``. On the ``return``
    stage a capped coupon is always refused: only a no-receipt exchange that sells reaches it with a coupon, and its total
    is what the customer is paid back, never a sale."""
    capped = [c for c in mine if rules[c].get("spend")]
    if not capped:
        return None
    exp = ctx["currency_exponent"]
    need = sum(int((rules[c]["spend"] * 10 ** exp).to_integral_value(ROUND_CEILING)) for c in capped)   # a minimum: up
    total = ctx["totals"]["grand_minor"]
    refund = ctx["stage"] != "sale"
    if not refund and need <= total:
        return None
    cur = ctx.get("currency") or ""
    one = len(capped) == 1
    if refund:
        tail = f" a sale of {money(need, exp, cur)} and cannot be used on a refund. Remove {'it' if one else 'them'}."
    else:
        tail = f" a sale of {money(need, exp, cur)}; this sale is {money(total, exp, cur)}. Remove a coupon, or add to the sale."
    names = ", ".join(plain(c, 20) for c in capped)
    lead = f"Coupon {names} needs" if one else f"Coupons {names} need"
    if len(lead + tail) > TEXT_MAX:     # long names: the amounts and the instruction stay whole
        lead = "This coupon needs" if one else f"These {len(capped)} coupons need"
    return {"verdict": "refuse", "reason": plain(lead + tail)}


def on_check(ctx: dict, rules: dict, prior_sales) -> dict:
    """The answer for one check. Every group rule first, then the sale-needed cap (neither reads anything), then every
    first-purchase rule, which asks ``prior_sales(customer)`` at most once; the first refusal is the answer, else allow."""
    mine = [c for c in ctx["coupon_codes"] if c in rules]     # in the sale's order (sorted, by the contract)
    for c in mine:
        group = rules[c]["group"]
        if group and (ctx.get("customer_group") or "") != group:
            return {"verdict": "refuse", "reason": plain(
                f"Coupon {plain(c, 30)} is only for customers in {plain(group, 30)}. "
                "Remove it, or add a customer in that group.")}
    capped = over_cap(ctx, rules, mine)
    if capped:
        return capped
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
