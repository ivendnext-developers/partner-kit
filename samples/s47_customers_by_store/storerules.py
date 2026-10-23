"""S47 — *Customers by store*: the pure core (no framework, no network), shared by the service and its tests.

A **capture on customer select** (``capture/1``, event ``customer_select``): when the cashier puts an existing customer on
a sale, the shop's server sends the customer (with their customer group), the till's store and its POS Profile. The shop
keeps one rule record per customer group (``<prefix> Rule``, named by the group) with a table of the places its customers
may buy at: each row a store, a POS Profile, or both (that POS Profile at that store). ``on_select`` finds the rule that
decides (the customer's own group's, else the nearest group above it that has one, by the shop's group tree) and answers
``allow`` when a row names this till, else ``refuse`` with the rule's words: the till takes the customer off the sale, and
the server refuses every door that charges or books the sale for that customer until a later pick is allowed.

- no rule for the group or above it: ``allow``, the customer buys anywhere;
- a rule with no usable row (every row blank): ``refuse`` everywhere, never let through.

⛔ No answer moves money or changes the sale: an answer lets a customer on, or takes them off.

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
RULE_FIELDS = ("name", "customer_group", "words", "places.store", "places.pos_profile")   # one row per place (a left join)
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


def select_context(body: dict) -> dict:
    """The select's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "capture/1":
        raise ValueError("not a capture/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("event") != "customer_select":
        raise ValueError("not a customer select")
    if not (isinstance(ctx.get("store"), str) and isinstance(ctx.get("pos_profile"), str)):
        raise ValueError("store and pos_profile are text")
    who = ctx.get("customer")
    if not isinstance(who, dict) or not isinstance(who.get("customer_group"), str):
        raise ValueError("the customer and their customer_group")
    return ctx


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def rules_of(rows) -> dict:
    """The shop's switched-on rules, from its list read (one row per place, a rule with no place once with none):
    ``{group: {"places": {(store, pos_profile)}, "words": str}}``, a blank side of a place as ``""``. A row with no group
    is left out (that group then takes the rule above it); a place with both sides blank is no place. Anything that is
    not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the shop's rules are not a list of records")
    out = {}
    for r in rows:
        group = r.get("customer_group")
        if not isinstance(group, str) or not group:
            continue
        rule = out.setdefault(group, {"places": set(), "words": ""})
        if _text(r.get("words")):
            rule["words"] = _text(r["words"])
        place = (_text(r.get("store")), _text(r.get("pos_profile")))
        if any(place):
            rule["places"].add(place)
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


MARKS = "‌‍‎‏؜"   # joiners and direction marks Arabic and Persian text carries: the till keeps them


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable (and the marks it allows), no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable() or ch in MARKS).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def allowed_here(places: set, store: str, pos_profile: str) -> bool:
    """A place names this till when each side it fills is the till's own: a store alone, a POS Profile alone, or both."""
    return any((not s or s == store) and (not p or p == pos_profile) for s, p in places)


def _place(store: str, pos_profile: str) -> str:
    if store and pos_profile:
        return f"{pos_profile} at {store}"
    return store or pos_profile


def _reason(group: str, rule: dict) -> str:
    own = plain(rule["words"])          # words that come out empty (a mark alone) fall back to the app's own
    if own.strip(MARKS):
        return own
    if not rule["places"]:
        return plain(f"Customers in {plain(group, 40)} can't buy at this store.")
    where = ", ".join(sorted(_place(*p) for p in rule["places"]))
    return plain(f"Customers in {plain(group, 40)} buy only at {plain(where, 73)}.")   # 13 + 40 + 13 + 73 + 1: at most 140


def on_select(ctx: dict, rules: dict, tree: dict) -> dict:
    """The answer for one pick: on the sale when the deciding rule names this till (or no rule decides), else off it."""
    found = deciding(ctx["customer"]["customer_group"], rules, tree)
    if not found:
        return {"verdict": "allow"}
    group, rule = found
    if allowed_here(rule["places"], ctx["store"], ctx["pos_profile"]):
        return {"verdict": "allow"}
    return {"verdict": "refuse", "reason": _reason(group, rule)}
