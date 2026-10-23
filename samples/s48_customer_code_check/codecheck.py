"""S48 — *Customer code check*: the pure core (no framework, no network), shared by the service and its tests.

A **capture on customer select** (``capture/1``, event ``customer_select``) that answers **challenge**: when the cashier
puts an existing customer on a sale, the shop's server sends the customer (with their phone and customer group, read by
the server from the customer record), the store, the POS Profile, the cashier and a ``challenge_id``. The shop keeps one
rule record per customer group (``<prefix> Rule``, named by the group): *Ask for a code* or *Never ask*, and what to do
when the customer has no mobile number. ``on_select`` finds the rule that decides (the customer's own group's, else the
nearest group above it that has one, by the shop's group tree) and answers:

- ``allow``: no rule decides, the rule says *Never ask*, or the record has no mobile number and the rule lets them on.
  Every other pick asks again: the till spends a right code's pass at the booking, so the next sale asks anew;
- ``refuse``: the rule asks, the record has no mobile number, and the rule takes them off the sale;
- ``challenge``: the rule asks. The service first writes a code record (``code_record``) in the shop; the shop's own
  Notification on that record texts the code to the number it holds. The till then shows a code field, and what the
  customer reads out comes back as ``verify``.

``on_verify`` checks the code against the record named by the ``challenge_id``: right, unused and younger than
``CODE_TTL_S``: ``ok``; else ``refuse`` in words. The shop's server counts the tries (three wrong codes end the check).

⛔ No answer moves money: an answer lets a customer on, asks for a code, or takes them off. The code never leaves the
shop through the service: it is made here, written to the shop's own record, and sent by the shop's own SMS gateway.

``verify``, ``plain``, ``tree_of`` and ``deciding`` are S47's (``samples/s47_customers_by_store/storerules.py``, from
S46's ``payrules.py``), copied: a defect there is a defect here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
LENGTH = 6            # the code's digits (the contract allows 4 to 8)
CODE_TTL_S = 600      # a code is good for ten minutes, as the shop's own challenge is
MOBILE_MIN = 6        # fewer digits than this on the record is no mobile number
MOBILE_MAX = 20       # the shop's Phone field holds at most 20 characters
LEAD = re.compile(r"\+?[0-9][0-9 ()\-.]*")   # the number a record's phone starts with (a second number, an extension: dropped)
ASK, NEVER = "Ask for a code", "Never ask"
TAKE_OFF, LET_ON = "Take them off the sale", "Let them on"
SENT, USED = "Sent", "Used"
RULE_FIELDS = ("name", "customer_group", "ask", "without_mobile", "words")
TREE_FIELDS = ("name", "lft", "rgt")
CODE_FIELDS = ("name", "code", "status", "sent_at")
WRONG = "That code is not right."
ENDED = "This code has ended. Pick the customer again."


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


def _hex32(value) -> bool:
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def capture_context(body: dict) -> dict:
    """The call's context, or ``ValueError``: a customer select or a verify, only the shape this app reads, checked
    before any decision."""
    if not isinstance(body, dict) or body.get("point") != "capture/1":
        raise ValueError("not a capture/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not _hex32(ctx.get("challenge_id")):
        raise ValueError("a capture call with its challenge_id")
    if ctx.get("event") == "verify":
        code = ctx.get("code")
        if not (isinstance(code, str) and code.isascii() and code.isalnum() and 4 <= len(code) <= 8):
            raise ValueError("a verify carries the code: 4 to 8 letters and digits")
        return ctx
    if ctx.get("event") != "customer_select":
        raise ValueError("not a customer select or a verify")
    if not all(isinstance(ctx.get(k), str) for k in ("store", "pos_profile", "operator")):
        raise ValueError("store, pos_profile and operator are text")
    who = ctx.get("customer")
    if not isinstance(who, dict) or not all(isinstance(who.get(k), str) for k in ("customer", "customer_group", "phone")):
        raise ValueError("the customer, their customer_group and their phone")
    if not who["customer"]:
        raise ValueError("the customer is named")
    return ctx


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def rules_of(rows) -> dict:
    """The shop's switched-on rules, from its list read: ``{group: {"ask": bool, "let_on": bool, "words": str}}``. A row
    with no group is left out (that group then takes the rule above it). Anything but *Never ask* asks, and anything but
    *Let them on* takes a customer with no mobile number off the sale: a value the shop's form never writes errs on the
    side of the code. Anything that is not a list of records is ``ValueError``."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("the shop's rules are not a list of records")
    out = {}
    for r in rows:
        group = r.get("customer_group")
        if isinstance(group, str) and group:
            out[group] = {"ask": _text(r.get("ask")) != NEVER, "let_on": _text(r.get("without_mobile")) == LET_ON,
                          "words": _text(r.get("words"))}
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


def digits(phone: str) -> str:
    return "".join(c for c in phone if c.isascii() and c.isdigit())


def mobile_of(phone: str) -> str:
    """The number the code goes to: the first number the record's phone holds (``+971 50 123 4567 / …`` and
    ``0100 555 0147 ext 2`` keep their first number), in the characters the shop's Phone field accepts, at most
    ``MOBILE_MAX``; ``""`` when fewer than ``MOBILE_MIN`` digits are left (no mobile number)."""
    m = LEAD.match((phone or "").strip())
    number = m.group(0).strip() if m else ""
    if len(number) > MOBILE_MAX:
        number = number.replace(" ", "")
    if len(number) > MOBILE_MAX or len(digits(number)) < MOBILE_MIN:
        return ""
    return number


def prompt(rule: dict, phone: str) -> str:
    """The words with the code field: the rule's own, else the app's, which name the last two digits of the number the
    code went to, so the customer can say *that is not my number*."""
    own = plain(rule["words"])
    if own.strip(MARKS):
        return own
    return f"Ask the customer for the {LENGTH}-digit code we sent to their phone ending {digits(phone)[-2:]}."


def on_select(ctx: dict, rules: dict, tree: dict) -> dict:
    """The answer for one pick, before any code is made: ``allow``, ``refuse``, or ``challenge`` (the service then writes
    the code record before it answers)."""
    who = ctx["customer"]
    group = who["customer_group"]
    if group and group not in tree and group not in rules and rules:
        raise ValueError("the customer's group is not in the shop's group tree")
    found = deciding(group, rules, tree)
    if not found or not found[1]["ask"]:
        return {"verdict": "allow"}
    name, rule = found
    if not mobile_of(who["phone"]):
        if rule["let_on"]:
            return {"verdict": "allow"}
        return {"verdict": "refuse",
                "reason": plain(f"Customers in {plain(name, 40)} need a code, and this customer has no mobile number.")}
    return {"verdict": "challenge", "prompt": prompt(rule, mobile_of(who["phone"])), "length": LENGTH}


def new_code() -> str:
    """A code from a secure source: ``LENGTH`` digits, any of them."""
    return f"{secrets.randbelow(10 ** LENGTH):0{LENGTH}d}"


def code_record(ctx: dict, code: str, now: float) -> dict:
    """The shop's code record for one challenge, named by the till's ``challenge_id``: what the shop's Notification texts
    (``code`` to ``mobile``), and what ``on_verify`` and the next pick read back."""
    who = ctx["customer"]
    return {"challenge": ctx["challenge_id"], "customer": who["customer"], "customer_name": plain(who.get("customer_name") or "", 140),
            "mobile": mobile_of(who["phone"]), "code": code, "store": ctx["store"][:140], "pos_profile": ctx["pos_profile"][:140],
            "operator": ctx["operator"][:140], "status": SENT, "sent_at": int(now)}


def on_verify(ctx: dict, record: dict | None, now: float) -> dict:
    """The answer to a code the customer read out, from the record its ``challenge_id`` names (``None``: no such record):
    right, unused and younger than ``CODE_TTL_S``: ``ok``; a wrong code: ``refuse`` (the till counts it); anything else
    has ended."""
    if not isinstance(record, dict) or record.get("status") != SENT or not isinstance(record.get("code"), str) \
            or not record["code"] or not isinstance(record.get("sent_at"), int) or isinstance(record.get("sent_at"), bool) \
            or not 0 <= now - record["sent_at"] <= CODE_TTL_S:
        return {"verdict": "refuse", "reason": ENDED}
    if not hmac.compare_digest(record["code"].encode(), ctx["code"].encode()):
        return {"verdict": "refuse", "reason": WRONG}
    return {"verdict": "ok"}
