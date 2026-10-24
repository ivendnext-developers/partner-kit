"""S50 — *Required sale details*: the pure core (no framework, no network), shared by the service and its tests.

A **check before payment** (``check/1``): when the cashier presses Pay, the retailer's server sends its own priced basket,
whose ``customer_group`` is the sale's customer's group, whose ``pos_profile`` is the till's, and whose ``sale_attributes``
are the sale's details as the cashier filled them (``[{"name": <Sale Attribute>, "value": <text>}]``). The retailer keeps
one rule record per customer group (``<prefix> Rule``, named by the group): the sale details that group's customers must
give (a table of Sale Attribute) and, optionally, the POS Profiles the rule holds on (none: every till). ``on_check`` finds
the rule that decides (the customer's own group's, else the nearest group above it that has one, by the retailer's group
tree) and answers:

- no rule for the group or above it, a till the deciding rule does not name, or every needed detail filled: ``allow``;
- a needed detail missing or blank: ``refuse``, in the retailer's words or the app's own, naming the details missing.

Only a sale is judged (``stage: "sale"``), and an exchange's new basket is one. A refund, the returned lines of an exchange
and a return without its sale (``stage: "return"``) are allowed without reading the retailer's iVendNext; so is an exchange
rung without its sale when nothing is owed, which the till sends as a return with its sold lines (a bound: the contract lets
a check judge those lines, and a partner's version may). The store's
walk-in customer is in a group like any customer: a rule on its group asks it too.

⛔ No answer moves money: no price, no line, no amount, no payment method. The cashier fills the detail on the sale and
presses Pay again; the check is asked again.

``verify``, ``plain``, ``tree_of`` and ``deciding`` are S46's (``samples/s46_payment_method_rules/payrules.py``), copied:
a defect there is a defect here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
RULE_FIELDS = ("name", "customer_group", "words", "details.sale_attribute", "profiles.pos_profile")   # a left join: one row
TREE_FIELDS = ("name", "lft", "rgt")                                                                # per detail and profile


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the retailer's, else why not. The signature is base64 HMAC-SHA256 of
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
    if not all(_text_or_none(ctx.get(k)) for k in ("customer", "customer_group", "pos_profile")):
        raise ValueError("customer, customer_group and pos_profile are text")
    attrs = ctx.get("sale_attributes")
    if attrs is None:
        ctx["sale_attributes"] = []
    elif not isinstance(attrs, list) or not all(isinstance(a, dict) and isinstance(a.get("name"), str)
                                                 and _text_or_none(a.get("value")) for a in attrs):
        raise ValueError("sale_attributes is a list of a name and a text value")
    return ctx


def rules_of(rows) -> dict:
    """The retailer's switched-on rules, from its list read (one row per detail and POS Profile, a rule with neither once
    with none): ``{group: {"details": [names, in the order read], "profiles": set, "words": str}}``. A row with no group is
    left out. Anything that is not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the retailer's rules are not a list of records")
    out = {}
    for r in rows:
        group = r.get("customer_group")
        if not isinstance(group, str) or not group:
            continue
        rule = out.setdefault(group, {"details": [], "profiles": set(), "words": ""})
        words, detail, profile = r.get("words"), r.get("sale_attribute"), r.get("pos_profile")
        if isinstance(words, str) and words.strip():
            rule["words"] = words.strip()
        if isinstance(detail, str) and detail and detail not in rule["details"]:
            rule["details"].append(detail)
        if isinstance(profile, str) and profile:
            rule["profiles"].add(profile)
    return out


def tree_of(rows) -> dict:
    """``{group: (lft, rgt)}`` from the retailer's Customer Group list. A row without whole numbers is left out (that group
    then has no group above it). Anything that is not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the retailer's customer groups are not a list of records")
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


MARKS = "‌‍‎‏؜"   # joiners and direction marks Arabic and Persian text carries: the till keeps them
ZERO_WIDTH = "\u200b\ufeff"                 # never a value: a detail holding only these, spaces and marks is empty


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable (and the marks it allows), no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable() or ch in MARKS).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def missing(ctx: dict, rule: dict) -> list:
    """The rule's details this sale has not filled (absent, empty, or only spaces, marks and zero-width characters), in
    the rule's order."""
    filled = {a["name"] for a in ctx["sale_attributes"]
              if any(not ch.isspace() and ch not in MARKS + ZERO_WIDTH for ch in a.get("value") or "")}
    return [d for d in rule["details"] if d not in filled]


def _reason(group: str, rule: dict, gaps: list) -> str:
    own = plain(rule["words"])          # words that come out empty (a mark alone) fall back to the app's own
    if own.strip(MARKS):
        return own
    names = plain(", ".join(gaps), 52)  # 58 characters of sentence + a group of 30 + the details' 52: at most 140 (asserted)
    return plain(f"Customers in {plain(group, 30)} need {names}. Fill in the sale's details, then Pay.")


def on_check(ctx: dict, rules: dict, tree: dict) -> dict:
    """The answer for one check: ``refuse`` naming the needed details the sale has not filled, else ``allow``."""
    if ctx["stage"] != "sale":
        return {"verdict": "allow"}
    found = deciding(ctx.get("customer_group") or "", rules, tree)
    if not found:
        return {"verdict": "allow"}
    group, rule = found
    if rule["profiles"] and ctx.get("pos_profile") not in rule["profiles"]:
        return {"verdict": "allow"}
    gaps = missing(ctx, rule)
    if not gaps:
        return {"verdict": "allow"}
    return {"verdict": "refuse", "reason": _reason(group, rule, gaps)}
