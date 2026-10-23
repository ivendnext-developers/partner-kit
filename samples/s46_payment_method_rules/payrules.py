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

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
EXCLUDE_MAX = 20      # the contract's most methods one answer leaves out
ONLY, BUT = "Only these payment methods", "Every payment method but these"
RULE_FIELDS = ("name", "customer_group", "kind", "words", "methods.mode_of_payment")   # one row per method (a left join)
TREE_FIELDS = ("name", "lft", "rgt")


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
    offered = ctx.get("offered_tenders")
    if not isinstance(offered, list) or not all(isinstance(t, str) for t in offered):
        raise ValueError("offered_tenders is a list of text")
    if not (_text_or_none(ctx.get("customer")) and _text_or_none(ctx.get("customer_group"))):
        raise ValueError("customer and customer_group are text")
    return ctx


def rules_of(rows) -> dict:
    """The shop's switched-on rules, from its list read (one row per method, a rule with no method once with none):
    ``{group: {"kind": ONLY | BUT, "methods": set, "words": str}}``. A row with no group, or a kind this app does not know,
    is left out (that group then takes the rule above it). Anything that is not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the shop's rules are not a list of records")
    out = {}
    for r in rows:
        group, kind = r.get("customer_group"), r.get("kind")
        if not isinstance(group, str) or not group or kind not in (ONLY, BUT):
            continue
        rule = out.setdefault(group, {"kind": kind, "methods": set(), "words": ""})
        words, method = r.get("words"), r.get("mode_of_payment")
        if isinstance(words, str) and words.strip():
            rule["words"] = words.strip()
        if isinstance(method, str) and method:
            rule["methods"].add(method)
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
    if rule["kind"] == ONLY:
        out = [t for t in offered if t not in rule["methods"]]
    else:
        out = [t for t in offered if t in rule["methods"]]
    if not out:
        return {"verdict": "allow"}
    if len(out) == len(offered):
        takes = ", ".join(sorted(rule["methods"])) if rule["kind"] == ONLY and rule["methods"] else "another payment method"
        return {"verdict": "refuse", "reason": plain(       # 52 characters + a group of 30 + a list of 58: at most 140
            f"Customers in {plain(group, 30)} can't pay at this till: use one with {plain(takes, 58)}.")}
    if len(out) > EXCLUDE_MAX:
        return {"verdict": "refuse", "reason": plain(
            f"This till offers more payment methods than the rule for customers in {plain(group, 40)} can switch off. "
            "Ask your administrator.")}
    return {"verdict": "allow", "exclude_tenders": out, "reason": _reason(group, rule)}
