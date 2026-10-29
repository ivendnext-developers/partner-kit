"""S46 — *Payment method rules*: the pure core (no framework, no network), shared by the service and its tests.

A **check before payment** (``check/1``): when the cashier presses Pay, the shop's server sends its own priced basket,
whose ``customer_group`` is the sale's customer's group and whose ``offered_tenders`` are the payment methods this till
offers. The shop keeps one rule record per customer group (``<prefix> Rule``, named by the group): *Only these payment
methods* or *Every payment method but these*, with a table of methods. ``on_check`` finds the rule that decides (the
customer's own group's, else the nearest group above it that has one, by the shop's group tree) and answers ``allow``
with ``exclude_tenders``: the till draws those methods dimmed with the rule's words, and the cashier takes another.

- no rule for the group or above it: ``allow``, every method stays;
- a rule that leaves out none of the offered methods: ``allow``;
- a rule that leaves out every offered method: ``refuse`` (the payment screen would have nothing to take);
- more than the contract's 20 methods to leave out: ``refuse`` too, never a partial list that lets one through.

**From a sale of** (1.1.0, NETT's minimum sale before loyalty points pay): a method row may carry an amount
(``min_sale``). Under either kind of rule that method pays only for a sale of at least that amount: below it, it is left
out with the rule's words, or the app's naming the amount; from it, it is offered. A row without an amount keeps 1.0's
meaning, and a method on several rows takes the strictest (below). The amount is read in the sale's own currency, rounded up to
its minor unit (a minimum), against ``totals.grand_minor``: the sale's total as rounded for payment, after its
discounts, tax included, before any payment method's own discount. Equal is enough. A method on several rows takes the
strictest: the largest amount, and under *Every payment method but these* a row with no amount keeps it out. The till draws an excluded method's tile dimmed, but its loyalty form shows whenever the customer has points:
a redemption below the amount is refused when the payment completes, and once a card on the bank's own machine, a wallet
or a split's earlier leg has taken money it books and is flagged for review (the till's own doors, ``partner_check.Door.verify``). Loyalty points pay through the method named *Loyalty Points*, so a rule on the
top customer group, *Every payment method but these*, *Loyalty Points* from 2,000, is NETT's rule for every customer.

Only a sale is judged (``stage: "sale"``), and an exchange's replacement basket is one (the check page, section 1): it pays
by store credit, so an *Only these* rule that does not list the store-credit method stops that group's exchanges. A refund,
the returned lines of an exchange and a return without its sale (``stage: "return"``) are allowed without reading the shop.

⛔ No answer moves money: no price, no line, no amount. A method left out is not taken for this basket at any door that
moves money (the till holds the answer to the basket); another line asks again.

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
EXCLUDE_MAX = 20      # the contract's most methods one answer leaves out
ONLY, BUT = "Only these payment methods", "Every payment method but these"
# one row per method (a left join). A retailer still on 1.0.x has no ``min_sale``: a read naming it answers 417, and the
# service reads again with the listed version's fields (``RULE_FIELDS_LISTED``), whose rows carry no amount
RULE_FIELDS = ("name", "customer_group", "kind", "words", "methods.mode_of_payment", "methods.min_sale")
RULE_FIELDS_LISTED = RULE_FIELDS[:-1]
TREE_FIELDS = ("name", "lft", "rgt")


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit() and len(ts) <= 12) or abs((now or time.time()) - int(ts)) > SKEW_S:
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
    offered = ctx.get("offered_tenders")
    if not isinstance(offered, list) or not all(isinstance(t, str) for t in offered):
        raise ValueError("offered_tenders is a list of text")
    if not (_text_or_none(ctx.get("customer")) and _text_or_none(ctx.get("customer_group"))):
        raise ValueError("customer and customer_group are text")
    exp, totals = ctx.get("currency_exponent"), ctx.get("totals")
    if not _whole(exp) or not 0 <= exp <= 4 or not isinstance(totals, dict) or not _whole(totals.get("grand_minor")):
        raise ValueError("currency_exponent and totals.grand_minor are whole numbers")
    return ctx


def _whole(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool)


def _amount(value) -> Decimal:
    """A method row's *From a sale of*: 0 when blank, absent (a retailer on 1.0.x), not a number or not above 0.
    S32's ``_amount`` (``samples/s32_coupon_rules/coupons.py``), copied: a defect there is a defect here."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return Decimal(0)
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return Decimal(0)
    return d if d.is_finite() and d > 0 else Decimal(0)


def rules_of(rows) -> dict:
    """The shop's switched-on rules, from its list read (one row per method, a rule with no method once with none):
    ``{group: {"kind": ONLY | BUT, "methods": set, "from": {method: amount}, "words": str}}``. ``from`` holds the methods
    with an amount, a method on several rows taking the strictest: the largest amount, and under *Every payment method but
    these* a row with no amount keeps the method out at any total (a blank row is never loosened by another). A row with no group, or a kind this app does not know,
    is left out (that group then takes the rule above it). Anything that is not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the shop's rules are not a list of records")
    out, bare = {}, set()
    for r in rows:
        group, kind = r.get("customer_group"), r.get("kind")
        if not isinstance(group, str) or not group or kind not in (ONLY, BUT):
            continue
        rule = out.setdefault(group, {"kind": kind, "methods": set(), "from": {}, "words": ""})
        words, method = r.get("words"), r.get("mode_of_payment")
        if isinstance(words, str) and words.strip():
            rule["words"] = words.strip()
        if isinstance(method, str) and method:
            rule["methods"].add(method)
            amount = _amount(r.get("min_sale"))
            if not amount:
                bare.add((group, method))
            elif amount > rule["from"].get(method, 0):
                rule["from"][method] = amount
    for group, method in bare:
        if out[group]["kind"] == BUT:       # always out: an amount on another row never lets it through
            out[group]["from"].pop(method, None)
    return out


def tree_of(rows) -> dict:
    """``{group: (lft, rgt)}`` from the shop's Customer Group list. A row without whole numbers is left out (that group
    then has no group above it). Anything that is not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the shop's customer groups are not a list of records")
    out = {}
    for r in rows:
        name, lft, rgt = r.get("name"), r.get("lft"), r.get("rgt")
        if isinstance(name, str) and all(isinstance(n, int) and not isinstance(n, bool) for n in (lft, rgt)):
            out[name] = (lft, rgt)
    return out


def deciding(group: str, rules: dict, tree: dict) -> tuple[str, dict] | None:
    """The rule that decides for a customer in ``group``: its own, else the nearest group above it with a rule (the
    groups whose span holds the group's, the innermost first). One rule decides, whole: a group's own rule replaces the
    rules above it. A customer with no group takes the rule of a root group (one no other group holds), if it has one.
    ``None``: no rule decides."""
    if group in rules:
        return group, rules[group]
    if group:
        if group not in tree:
            return None
        lft, rgt = tree[group]
        above = [g for g, (l, r) in tree.items() if l < lft and rgt < r]
    else:
        above = [g for g, (l, r) in tree.items() if not any(l2 < l and r < r2 for l2, r2 in tree.values())]
    for g in sorted(above, key=lambda g: tree[g][0], reverse=True):     # the innermost (largest lft) first
        if g in rules:
            return g, rules[g]
    return None


MARKS = "\u200c\u200d\u200e\u200f\u061c"   # joiners and direction marks Arabic and Persian text carries: the till keeps them


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable (and the marks it allows), no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable() or ch in MARKS).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def money(minor: int, exponent: int, currency: str = "") -> str:
    """``minor`` units as the till shows an amount: ``NGN 2,000.00``. S32's (``coupons.py``), copied."""
    whole, frac = divmod(abs(minor), 10 ** exponent)
    text = ("-" if minor < 0 else "") + f"{whole:,}" + (f".{frac:0{exponent}d}" if exponent else "")
    return f"{plain(currency, 3)} {text}".strip()


def _short_words(short: list, need: dict, ctx: dict, tail: str = ".") -> str:
    """The sale's total first (a cut sentence keeps it), then each method left out by its amount, then ``tail``."""
    exp, cur = ctx["currency_exponent"], ctx.get("currency") or ""
    head = f"This sale is {money(ctx['totals']['grand_minor'], exp, cur)}; "
    if len(short) == 1:
        return plain(head + f"{plain(short[0], 40)} needs a sale of {money(need[short[0]], exp, cur)}{tail}")
    return plain(head + "these need a larger sale: " + ", ".join(
        f"{plain(t, 30)} {money(need[t], exp, cur)}" for t in short) + tail)


def _reason(group: str, rule: dict) -> str:
    own = plain(rule["words"])          # words that come out empty (a mark alone) fall back to the app's own
    if own.strip(MARKS):
        return own
    if rule["kind"] == ONLY:
        return plain(f"Customers in {plain(group, 40)} pay with {', '.join(sorted(rule['methods'])) or 'no method'}.")
    return plain(f"Not for customers in {plain(group, 60)}.")


def on_check(ctx: dict, rules: dict, tree: dict) -> dict:
    """The answer for one check: the methods the deciding rule leaves out of the offered ones, in the till's order."""
    if ctx["stage"] != "sale":
        return {"verdict": "allow"}
    found = deciding(ctx.get("customer_group") or "", rules, tree)
    if not found:
        return {"verdict": "allow"}
    group, rule = found
    offered = list(dict.fromkeys(ctx["offered_tenders"]))
    exp, total = ctx["currency_exponent"], ctx["totals"]["grand_minor"]
    need = {t: int((a * 10 ** exp).to_integral_value(ROUND_CEILING)) for t, a in rule["from"].items()}   # a minimum: up
    short = [t for t in offered if t in need and total < need[t]]        # left out by the sale's size
    if rule["kind"] == ONLY:
        out = [t for t in offered if t not in rule["methods"] or t in short]
    else:
        out = [t for t in offered if (t in rule["methods"] and t not in need) or t in short]
    if not out:
        return {"verdict": "allow"}
    if len(out) == len(offered) and short:
        return {"verdict": "refuse", "reason": _short_words(short, need, ctx, ": add to the sale; the rule allows no other method here.")}
    if len(out) == len(offered):
        takes = ", ".join(sorted(rule["methods"])) if rule["kind"] == ONLY and rule["methods"] else "another payment method"
        return {"verdict": "refuse", "reason": plain(       # 52 characters + a group of 30 + a list of 58: at most 140
            f"Customers in {plain(group, 30)} can't pay at this till: use one with {plain(takes, 58)}.")}
    if len(out) > EXCLUDE_MAX:
        return {"verdict": "refuse", "reason": plain(
            f"This till offers more payment methods than the rule for customers in {plain(group, 40)} can switch off. "
            "Ask your administrator.")}
    own = plain(rule["words"])
    if short and not own.strip(MARKS):   # the amount first (the contract carries one reason for every method left out)
        tail = "." if out == short else f". {_reason(group, rule)}"
        return {"verdict": "allow", "exclude_tenders": out, "reason": _short_words(short, need, ctx, tail)}
    return {"verdict": "allow", "exclude_tenders": out, "reason": _reason(group, rule)}
