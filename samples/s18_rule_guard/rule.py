"""S18 — *Members-only rule guard*: the pure core (no framework, no network), shared by the service and its tests.

The till asks before money is taken (the check before payment extension point, ``check/1``): one signed POST when the
cashier presses Pay, carrying the server's own priced basket:

    {"point": "check/1", "context": {"v": 1, "stage": "sale" | "return", "customer", "customer_group",
                                     "currency", "currency_exponent", "lines": [{"item_code", "item_group", ...}],
                                     "totals": {"grand_minor", ...}, ...}}

``verify`` checks the shop's signature; ``decide`` answers in the extension point's closed vocabulary:

- **refuse**, with this service's own sentence, when the basket holds a members-only item (by item code or item group)
  and the sale's customer is not in one of the shop's member groups;
- **ask** the cashier a yes/no question when the sale's total is at or above the shop's ID limit;
- **allow** otherwise.

⛔ The answer never moves money: no price, no line, no payment. A refused sale is not paid — the till goes back to the
basket, and the door before any money (the card push, a gift card, cash) refuses a sale without an allowing answer for
exactly this basket.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension point's rule)


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


def context_of(body: dict) -> dict:
    """The check's context, or ``ValueError`` — only the shape this sample reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    if not isinstance(ctx.get("lines"), list) or not isinstance(ctx.get("totals"), dict):
        raise ValueError("no lines or totals")
    if not isinstance(ctx.get("currency_exponent"), int) or not isinstance(ctx["totals"].get("grand_minor"), int):
        raise ValueError("money is whole minor units")
    if not all(isinstance(ln, dict) and isinstance(ln.get("qty_milli"), int) for ln in ctx["lines"]):
        raise ValueError("a line's quantity is a whole number")   # else sold_lines could not tell sold from taken back
    return ctx


def rules_from(env: dict) -> dict:
    """The rule from the service's settings, for a run with no shop to read (comma lists; the ID limit in whole currency
    units, blank = off). A connected shop's rule is its own records (``rules_of``)."""
    def names(key):
        return {x.strip() for x in (env.get(key) or "").split(",") if x.strip()}
    limit = (env.get("PP_ASK_ABOVE") or "").strip()
    return {"items": names("PP_MEMBERS_ONLY_ITEMS"), "groups": names("PP_MEMBERS_ONLY_GROUPS"),
            "member_groups": names("PP_MEMBER_GROUPS"), "ask_above": float(limit) if limit else None}


# A shop's own rule (many shops, the App library's app): one ``<prefix> Rule`` record per rule, read back by the service.
KINDS = {"Members-only item": ("items", "item"), "Members-only item group": ("groups", "item_group"),
         "Member customer group": ("member_groups", "customer_group")}
ASK_KIND = "Ask for ID at or above"
RULE_FIELDS = ("kind", "item", "item_group", "customer_group", "amount", "enabled")


def rules_of(records) -> dict:
    """The shop's rule, from its own Rule records: the switched-on ones, one rule each. Several ID limits: the lowest.
    A record of a kind this service does not know is left out; anything that is not a list of records is ``ValueError``."""
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("the shop's rules are not a list of records")
    out = {"items": set(), "groups": set(), "member_groups": set(), "ask_above": None}
    for r in records:
        if not r.get("enabled"):
            continue
        if r.get("kind") in KINDS:
            into, field = KINDS[r["kind"]]
            if isinstance(r.get(field), str) and r[field]:
                out[into].add(r[field])
        elif r.get("kind") == ASK_KIND and isinstance(r.get("amount"), (int, float)) and r["amount"] >= 0:
            out["ask_above"] = r["amount"] if out["ask_above"] is None else min(out["ask_above"], r["amount"])
    return out


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def sold_lines(ctx: dict) -> list:
    """The lines this check sells: those with a positive quantity, on a sale or a return. An exchange rung without its
    sale carries the items it sells that way (the contract says judge them by the sale rule), and a sale may carry an item
    handed back as a line with a negative quantity, which is taken back, not sold."""
    return [ln for ln in ctx["lines"] if isinstance(ln, dict) and isinstance(ln.get("qty_milli"), int) and ln["qty_milli"] > 0]


def decide(ctx: dict, rules: dict) -> dict:
    """The answer for one check. This rule is about who may BUY an item: what a return takes back is allowed, what it
    sells is judged as a sale is; the ID question is asked on a sale only."""
    lines = sold_lines(ctx)
    if not lines:
        return {"verdict": "allow"}
    member = (ctx.get("customer_group") or "") in rules["member_groups"]
    if not member:
        for line in lines:
            if line.get("item_code") in rules["items"] or line.get("item_group") in rules["groups"]:
                item = _cut(str(line.get("item_code") or ""), 40).replace("<", "").replace(">", "")
                return {"verdict": "refuse",
                        "reason": f"{item} is for members only. Add the member's customer to the sale first."}
    limit = rules.get("ask_above")
    if limit is not None and ctx["stage"] == "sale":
        exp = ctx["currency_exponent"]
        if ctx["totals"]["grand_minor"] >= round(limit * 10 ** exp):
            amount = f"{limit:,.{exp}f} {ctx.get('currency') or ''}".strip()
            return {"verdict": "ask", "question": f"This sale is {amount} or more. Has the customer shown ID?"}
    return {"verdict": "allow"}
