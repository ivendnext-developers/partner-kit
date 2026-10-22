"""S37 — *Age-restricted sale check*: the pure core (no framework, no network), shared by the service and its tests.

Two extension points, one app:

- **a capture on scan** (``capture/1``): the product calls it only for an item its filter names (the item's own
  *Customers must be at least this old* holds a value, or its group is one the shop named on the service). ``on_scan``
  answers ``notice`` with the date of birth the customer must be born on or before, and a sale detail,
  ``<prefix> ID Checked``, holding *"18 or over"*. The till shows the sentence and the value on one sheet: **Add with
  these details** puts the item on the sale and records the check; **Don't add it** leaves both off.
- **a check before payment** (``check/1``): when the cashier presses Pay, ``on_check`` refuses the sale when a line it
  sells needs an age the sale's recorded check does not cover: no check recorded (an item picked from a list, or a
  *Don't add it* earlier), or a lower age than the line needs. The cashier can type the age in *Sale details*.

An item's age is its own *Customers must be at least this old* when above 0, else the nearest item group above it (itself
included) that has one (``age_of``). A return is judged only for what it sells (an exchange's new lines).

⛔ No answer moves money: no price, no line, no payment. No date of birth or ID number is asked or kept: the record is
the age band the cashier confirmed.

``verify`` and ``plain`` are S23's (``samples/s23_till_guard/guard.py``), copied: a defect there is a defect here.
``groups_of`` reads the group tree as S36's does (``samples/s36_duty_free/dutyfree.py``).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import re
import threading
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
CHECKED = "ID Checked"                      # the sale detail is "<prefix> ID Checked"
ASKED_TTL = 4 * 3600  # how long a sale's asked ages are remembered (a sale stays open on a till for hours at most)
ASKED_MAX = 20000     # sales remembered per running copy; the oldest go first


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


def _age(v) -> int:
    """A whole age from 1 to 120, else 0 (no limit)."""
    return int(v) if _number(v) and v == int(v) and 0 < v <= 120 else 0


def check_context(body: dict) -> dict:
    """The check's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    lines, attrs = ctx.get("lines"), ctx.get("sale_attributes")
    if not isinstance(lines, list) or not all(
            isinstance(x, dict) and isinstance(x.get("item_code"), str) and isinstance(x.get("item_group"), str)
            and _number(x.get("qty_milli")) for x in lines):
        raise ValueError("lines are rows of item_code, item_group and qty_milli")
    if not isinstance(attrs, list) or not all(
            isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("value"), str) for a in attrs):
        raise ValueError("sale_attributes are rows of name and value")
    return ctx


def scan_context(body: dict) -> dict:
    """The capture's scan context, or ``ValueError``. This app answers the scan event only."""
    if not isinstance(body, dict) or body.get("point") != "capture/1":
        raise ValueError("not a capture/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("event") != "scan":
        raise ValueError("not a scan")
    line = ctx.get("line")
    if not isinstance(line, dict) or not isinstance(line.get("item_code"), str) or not line["item_code"]:
        raise ValueError("no line")
    if not isinstance(line.get("item_group", ""), str) or not isinstance(ctx.get("sale_ref") or "", str):
        raise ValueError("the line's group and the sale's reference are text")
    return ctx


def sells(ctx: dict) -> bool:
    """Whether the sale hands anything over: a line with a positive quantity (a refund's lines are all negative)."""
    return any(x["qty_milli"] > 0 for x in ctx["lines"])


def settings_of(record) -> dict:
    """The shop's settings, from its record *Default* (``None``: not made yet, so UTC and *see their ID*). Hours from
    UTC past ±14 read 0; *ask for ID if they look under* is a whole age, 0 when blank or not one."""
    r = record if isinstance(record, dict) else {}
    hours = r.get("hours_from_utc")
    return {"hours": float(hours) if _number(hours) and -14 <= hours <= 14 else 0.0,
            "look_under": _age(r.get("look_under"))}


def groups_of(records, prefix: str) -> dict:
    """The shop's item groups: ``{name: (lft, rgt, age)}``. Anything that is not a list of records with whole ``lft`` and
    ``rgt`` is ``ValueError`` (the service then answers 503: nothing was judged)."""
    field = prefix.lower().replace(" ", "_") + "_min_age"
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and isinstance(r.get("name"), str) and isinstance(r.get("lft"), int)
            and isinstance(r.get("rgt"), int) for r in records):
        raise ValueError("the shop's item groups are not a list of records")
    return {r["name"]: (r["lft"], r["rgt"], _age(r.get(field))) for r in records}


def items_of(records, prefix: str) -> dict:
    """The items' own ages and templates: ``{item_code: (age, template or "")}`` (age 0: the group's age applies). A variant
    does not inherit a field its template gained later (the shop copies only the fields its Item Variant Settings list),
    so ``age_of`` falls back to the template's own age."""
    field = prefix.lower().replace(" ", "_") + "_min_age"
    if not isinstance(records, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):
        raise ValueError("the shop's items are not a list of records")
    return {r["name"]: (_age(r.get(field)), r.get("variant_of") if isinstance(r.get("variant_of"), str) else "")
            for r in records}


def age_of(item_code: str, item_group: str, items: dict, groups: dict) -> int:
    """The age a customer must be to buy this item: its own when above 0, else its template's own (a variant), else the
    nearest group with one (the group itself, then each group above it), else 0."""
    own, template = items.get(item_code) or (0, "")
    own = own or (items.get(template) or (0, ""))[0]
    if own:
        return own
    g = groups.get(item_group)
    if not g:
        return 0
    above = [(lft, age) for lft, rgt, age in groups.values() if age and lft <= g[0] and g[1] <= rgt]
    return max(above)[1] if above else 0          # the largest lft is the nearest: the tree nests by lft/rgt


def today_at(hours: float, now: float | None = None) -> datetime.date:
    """The shop's own date: UTC plus the shop's hours from UTC."""
    t = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t + datetime.timedelta(hours=hours)).date()


def born_by(today: datetime.date, age: int) -> datetime.date:
    """The latest date of birth of a customer who is ``age`` today. 29 February, in a year without one, is the 28th."""
    try:
        return today.replace(year=today.year - age)
    except ValueError:
        return today.replace(year=today.year - age, day=28)


def checked_value(age: int) -> str:
    return f"{age} or over"


def checked_age(ctx: dict, prefix: str) -> int:
    """The age the sale's *ID Checked* detail records: a whole age alone, as the scan writes it (*"18 or over"*) or the
    cashier types it (*18*, *18+*), else 0. Anything else, such as a date of birth typed in, is no check."""
    want = f"{prefix} {CHECKED}"
    value = next((a["value"] for a in ctx["sale_attributes"] if a["name"] == want), "")
    m = re.fullmatch(r"\s*(\d{1,3})\s*(\+|or over)?\s*", value, re.IGNORECASE)
    return _age(int(m.group(1))) if m else 0


def on_scan(ctx: dict, age: int, settings: dict, today: datetime.date, prefix: str) -> dict:
    """A restricted item: the date to compare and the record of the check, on one sheet. An age of 0 (a group the shop
    named on the service with no age set): allow, nothing shown."""
    if not age:
        return {"verdict": "allow"}
    item, d = plain(ctx["line"]["item_code"], 40), born_by(today, age)
    look = settings["look_under"]
    ask = f"Ask for ID if they look under {look}." if look > age else "See their ID."
    return {"verdict": "notice",
            "message": plain(f"{item}: customers {age} or over. Born on or before {d.day} {d:%b %Y}. {ask}"),
            "sale_attributes": [{"sale_attribute": f"{prefix} {CHECKED}", "attribute_value": checked_value(age)}]}


def on_check(ctx: dict, ages: list, checked: int) -> dict:
    """``ages`` is each line's age, in the order of ``ctx["lines"]``. The highest age a sold line needs above the recorded
    check is refused, naming its first line; otherwise allow."""
    short = [(age, i) for i, (line, age) in enumerate(zip(ctx["lines"], ages)) if line["qty_milli"] > 0 and age > checked]
    if not short:
        return {"verdict": "allow"}
    age = max(a for a, _ in short)
    i = next(i for a, i in short if a == age)
    line = ctx["lines"][i]
    n, item = line.get("line_no") or i + 1, plain(line["item_code"], 24)   # 24: the whole sentence fits the till's 140
    if checked:
        text = (f"Line {n}: {item} is for customers {age} or over; the sale's ID check says {checked}. "
                f"See their ID, then enter {age} in Sale details.")
    else:
        text = (f"Line {n}: {item} is for customers {age} or over. "
                f"See their ID, then enter {age} in Sale details, or take it off.")
    return {"verdict": "refuse", "reason": plain(text)}


class Asked:
    """Which ages this running copy has asked about on each sale (by the shop and the sale's reference), so a basket of
    wine is asked about once, not per bottle. Remembered ``ASKED_TTL`` seconds; the oldest go past ``ASKED_MAX``. The
    till does not say whether the cashier added the item: a sale asked about and then refused at the scan is caught by
    the check at Pay."""

    def __init__(self, clock=time.monotonic):
        self.clock, self.seen, self.lock = clock, {}, threading.Lock()

    def covered(self, shop: str, sale_ref: str, age: int) -> bool:
        if not sale_ref:
            return False                         # a sale's first scan has no reference yet
        with self.lock:
            hit = self.seen.get((shop, sale_ref))
        return bool(hit and self.clock() - hit[0] < ASKED_TTL and hit[1] >= age)

    def remember(self, shop: str, sale_ref: str, age: int) -> None:
        if not sale_ref:
            return
        with self.lock:
            now, old = self.clock(), self.seen.pop((shop, sale_ref), None)
            kept = old[1] if old and now - old[0] < ASKED_TTL else 0
            self.seen[(shop, sale_ref)] = (now, max(age, kept))
            while len(self.seen) > ASKED_MAX:
                self.seen.pop(next(iter(self.seen)))
