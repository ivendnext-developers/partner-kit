"""S42 — *Optical prescriptions and lab orders*: the pure core of its check before payment (no framework, no network),
shared by the service and its tests.

The shop keeps prescriptions and lab orders as its own records (the manifest). One extension point needs a service:

- **a check before payment** (``check/1``): when the cashier presses Pay, ``on_check`` refuses the sale when a line it
  sells is marked *Spectacles* or *Contact lenses* and the sale's customer has no prescription of that kind in date
  (its test date on or before the shop's today, its *Valid until* on or after it). A walk-in customer has none, so the
  cashier adds the customer.

An item's mark is its own *Sold against a prescription* when set, else its template's (a variant), else the nearest item
group above it (itself included) that has one (``need_of``). *Not needed* frees an item or a group below a marked one. A
return is judged only for what it sells (an exchange's new lines).

⛔ No answer moves money: no price, no line, no payment. The service reads three fields of a prescription (its kind, test
date and *Valid until*), never a lens value, a note or a scan, and keeps none of them.

``verify`` and ``plain`` are S23's (``samples/s23_till_guard/guard.py``), copied: a defect there is a defect here.
``groups_of``, ``items_of`` and the nearest-group rule are S37's (``samples/s37_age_check/agecheck.py``), copied the same way.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
KINDS = ("Spectacles", "Contact lenses")    # a prescription's kind, and the marks that need one
NOT_NEEDED = "Not needed"
WORDS = {"Spectacles": "spectacle", "Contact lenses": "contact lens"}


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


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable, no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _mark(v) -> str:
    """A mark the app reads: one of the two kinds, *Not needed*, or ``""`` (none of its own)."""
    return v if v in KINDS or v == NOT_NEEDED else ""


def field_of(prefix: str) -> str:
    return prefix.lower().replace(" ", "_") + "_needs"


def check_context(body: dict) -> dict:
    """The check's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    lines = ctx.get("lines")
    if not isinstance(lines, list) or not all(
            isinstance(x, dict) and isinstance(x.get("item_code"), str) and isinstance(x.get("item_group"), str)
            and _number(x.get("qty_milli")) for x in lines):
        raise ValueError("lines are rows of item_code, item_group and qty_milli")
    if not isinstance(ctx.get("customer"), str):
        raise ValueError("the customer is text")
    return ctx


def sells(ctx: dict) -> bool:
    """Whether the sale hands anything over: a line with a positive quantity (a refund's lines are all negative)."""
    return any(x["qty_milli"] > 0 for x in ctx["lines"])


def settings_of(record) -> dict:
    """The shop's settings, from its record *Default* (``None``: not made yet, so UTC). Hours from UTC past ±14 read 0."""
    r = record if isinstance(record, dict) else {}
    hours = r.get("hours_from_utc")
    return {"hours": float(hours) if _number(hours) and -14 <= hours <= 14 else 0.0}


def groups_of(records, prefix: str) -> dict:
    """The shop's item groups: ``{name: (lft, rgt, mark)}``. Anything that is not a list of records with whole ``lft`` and
    ``rgt`` is ``ValueError`` (the service then answers 503: nothing was judged)."""
    field = field_of(prefix)
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and isinstance(r.get("name"), str) and isinstance(r.get("lft"), int)
            and isinstance(r.get("rgt"), int) for r in records):
        raise ValueError("the shop's item groups are not a list of records")
    return {r["name"]: (r["lft"], r["rgt"], _mark(r.get(field))) for r in records}


def items_of(records, prefix: str) -> dict:
    """The items' own marks and templates: ``{item_code: (mark, template or "")}``. A variant does not inherit a field
    its template gained later (the shop copies only the fields its Item Variant Settings list), so ``need_of`` falls back
    to the template's own mark."""
    field = field_of(prefix)
    if not isinstance(records, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):
        raise ValueError("the shop's items are not a list of records")
    return {r["name"]: (_mark(r.get(field)), r.get("variant_of") if isinstance(r.get("variant_of"), str) else "")
            for r in records}


def need_of(item_code: str, item_group: str, items: dict, groups: dict) -> str:
    """The kind of prescription this item needs, or ``""``: its own mark, else its template's (a variant), else the
    nearest group with one (the group itself, then each group above it). *Not needed* anywhere on that path is ``""``."""
    own, template = items.get(item_code) or ("", "")
    own = own or (items.get(template) or ("", ""))[0]
    if not own:
        g = groups.get(item_group)
        above = [(lft, mark) for lft, rgt, mark in groups.values() if g and mark and lft <= g[0] and g[1] <= rgt]
        own = max(above)[1] if above else ""      # the largest lft is the nearest: the tree nests by lft/rgt
    return own if own in KINDS else ""


def _date(v) -> datetime.date | None:
    if not isinstance(v, str):
        return None
    try:
        return datetime.date.fromisoformat(v[:10])
    except ValueError:
        return None


def prescriptions_of(records) -> list:
    """The customer's prescriptions as ``[(kind, test_date, valid_until)]``. The shop answers each with the three fields
    asked for; a record without them (an app user with a bare SELECT right gets names only) is ``ValueError``, so a
    missing right is a 503, never a refusal. A record with an unreadable date counts as none."""
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and {"kind", "test_date", "valid_until"} <= set(r) for r in records):
        raise ValueError("the customer's prescriptions are not records with their kind and dates")
    return [(r["kind"], _date(r["test_date"]), _date(r["valid_until"])) for r in records if r["kind"] in KINDS]


def today_at(hours: float, now: float | None = None) -> datetime.date:
    """The shop's own date: UTC plus the shop's hours from UTC."""
    t = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t + datetime.timedelta(hours=hours)).date()


def in_date(rx: tuple, kind: str, today: datetime.date) -> bool:
    k, tested, until = rx
    return k == kind and tested is not None and until is not None and tested <= today <= until


def on_check(ctx: dict, needs: list, rxs: list, today: datetime.date) -> dict:
    """``needs`` is each line's kind (or ``""``), in the order of ``ctx["lines"]``; ``rxs`` the customer's prescriptions.
    The first sold line whose kind has no prescription in date is refused, saying when the customer's last one of that
    kind ran out if it has one; otherwise allow."""
    for i, (line, kind) in enumerate(zip(ctx["lines"], needs)):
        if line["qty_milli"] <= 0 or not kind or any(in_date(rx, kind, today) for rx in rxs):
            continue
        # 20: the whole sentence fits the till's 140 on line 500
        n, item, word = line.get("line_no") or i + 1, plain(line["item_code"], 20), WORDS[kind]
        ended = [u for k, _t, u in rxs if k == kind and u is not None and u < today]
        if ended:
            d = max(ended)
            text = (f"Line {n}: {item}: the customer's {word} prescription ran out on {d.day} {d:%b %Y}. "
                    f"Enter the new one in Desk, then Pay again.")
        else:
            text = (f"Line {n}: {item} needs a {word} prescription for this customer. "
                    f"Add the customer, or enter it in Desk, then Pay again.")
        return {"verdict": "refuse", "reason": plain(text)}
    return {"verdict": "allow"}
