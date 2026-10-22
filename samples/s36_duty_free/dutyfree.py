"""S36 — *Duty-free allowance and boarding pass*: the pure core (no framework, no network), shared by the service and its
tests.

A **check before payment** (``check/1``) for an airport shop. The cashier scans the customer's boarding pass into the sale
detail ``<prefix> Boarding Pass`` (the basket's *Sale details* row). When the cashier presses Pay, the shop's server sends
its own priced basket, and ``judge`` answers:

- **no pass** on the sale: refused, *scan it into Sale details*;
- **not a boarding pass** (IATA's bar-coded boarding pass, format ``M``: ``legs``): refused, *scan it again*;
- **another airport:** no leg of the pass leaves from (an arrivals shop: lands at) one of the shop's airports;
- **another day:** no such leg is dated today or tomorrow (an arrivals shop: today or the two days before, since a pass
  carries the day its flight leaves and a long flight can arrive two days later), by the airport's own day;
- **over an allowance:** an item group with a *Duty-free allowance per passenger* holds more, counting this sale and the
  passenger's earlier sales on the same pass (returns take theirs back), than its allowance. Each line counts its
  quantity in the item's stock unit times the item's *Counts toward the duty-free allowance as* (blank: 1), so a group can be
  limited in litres or in cigarettes. A group's allowance covers every group below it.

A sale that sells nothing (a refund) is allowed without reading the shop. ⛔ No answer moves money: no price, no line,
no payment. A refused sale is not paid: the till goes back to the basket.

The till keeps at most 140 characters of a sale detail, so a long pass is cut: every leg that fits whole is read, and a
pass whose first leg is whole is always readable (a pass's first leg ends at its 60th character).

``verify`` and ``plain`` are S23's (``samples/s23_till_guard/guard.py``), copied: a defect there is a defect here.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import re
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
PASS = "Boarding Pass"                      # the sale detail is "<prefix> Boarding Pass"
PASS_KEY = 60         # a pass's first 60 characters (its first leg) name the passenger and the flight: the key of
                      # their earlier sales
LEG = 37              # each leg's fixed part, from its booking reference to its variable-size field
SETTINGS_FIELDS = ("airports", "direction", "hours_from_utc", "count_earlier_sales")

NO_PASS = "Scan the customer's boarding pass into Sale details, then press Pay again."
UNREADABLE = "The boarding pass could not be read. Scan it again into Sale details."
OTHER_DAY = "This boarding pass is for a flight on another day. Ask for the pass for today's flight."
OTHER_DAY_ARRIVING = "This boarding pass is for a flight on another day. Ask for the pass of the flight the customer just arrived on."


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
            and isinstance(x.get("uom"), str) and _number(x.get("qty_milli")) for x in lines):
        raise ValueError("lines are rows of item_code, item_group, uom and qty_milli")
    if not isinstance(attrs, list) or not all(
            isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("value"), str) for a in attrs):
        raise ValueError("sale_attributes are rows of name and value")
    return ctx


def sells(ctx: dict) -> bool:
    """Whether the sale hands anything over: a line with a positive quantity (a refund's lines are all negative)."""
    return any(x["qty_milli"] > 0 for x in ctx["lines"])


def pass_of(ctx: dict, prefix: str) -> str:
    """The boarding pass the cashier scanned (the sale detail ``<prefix> Boarding Pass``), or ``""``."""
    want = f"{prefix} {PASS}"
    return next((a["value"] for a in ctx["sale_attributes"] if a["name"] == want), "")


def settings_of(record) -> dict:
    """The shop's settings, from its record *Default* (``None``: not made yet, so any airport, departures, UTC, earlier
    sales counted). Airports are words of letters (three-letter codes), separated by anything else; a mistyped one is
    kept, so it matches no pass and the cashier sees it named, never read as any airport. Hours from UTC past ±14
    read 0."""
    r = record if isinstance(record, dict) else {}
    codes = re.findall(r"[A-Za-z]+", str(r.get("airports") or ""))
    hours = r.get("hours_from_utc")
    hours = float(hours) if _number(hours) and -14 <= hours <= 14 else 0.0
    earlier = r.get("count_earlier_sales")
    return {"airports": sorted({c.upper() for c in codes}),
            "arriving": r.get("direction") == "arriving", "hours": hours,
            "earlier": True if earlier is None else bool(earlier)}


def groups_of(records, prefix: str) -> dict:
    """The shop's item groups: ``{name: (lft, rgt, allowance, unit)}``. Anything that is not a list of records with whole
    ``lft`` and ``rgt`` is ``ValueError`` (the service then answers 503: nothing was judged)."""
    p = prefix.lower().replace(" ", "_")
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and isinstance(r.get("name"), str) and isinstance(r.get("lft"), int)
            and isinstance(r.get("rgt"), int) for r in records):
        raise ValueError("the shop's item groups are not a list of records")
    out = {}
    for r in records:
        allowance = r.get(f"{p}_allowance")
        out[r["name"]] = (r["lft"], r["rgt"], float(allowance) if _number(allowance) and allowance > 0 else 0.0,
                          str(r.get(f"{p}_unit") or "").strip())
    return out


def legs(text: str) -> list[dict]:
    """Each whole leg of an IATA bar-coded boarding pass (format ``M``, 1 to 4 legs): ``from``, ``to``, ``flight`` and
    ``day`` (the day of the year, 1 to 366). ``[]`` when the first leg cannot be read. A leg cut short (the till keeps 140
    characters) or malformed ends the reading, keeping the legs before it."""
    t = text or ""
    if len(t) < 23 + LEG or t[0] != "M" or t[1] not in "1234":
        return []
    out, pos = [], 23
    for _ in range(int(t[1])):
        seg = t[pos:pos + LEG]
        if len(seg) < LEG:
            break
        frm, to, day, size = seg[7:10], seg[10:13], seg[21:24], seg[35:37]
        try:
            n = int(size, 16)
        except ValueError:
            break
        if not (frm.isalpha() and to.isalpha() and day.isdigit() and 1 <= int(day) <= 366):
            break
        out.append({"from": frm.upper(), "to": to.upper(), "flight": (seg[13:16] + seg[16:21]).replace(" ", ""),
                    "day": int(day)})
        pos += LEG + n
    return out


def today_at(hours: float, now: float | None = None) -> datetime.date:
    """The airport's own date: UTC plus the shop's hours from UTC."""
    t = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t + datetime.timedelta(hours=hours)).date()


def pass_problem(text: str, settings: dict, today: datetime.date) -> str:
    """Why this pass cannot buy here, or ``""``: unreadable, another airport, another day."""
    found = legs(text)
    if not found:
        return UNREADABLE
    side, airports = ("to" if settings["arriving"] else "from"), settings["airports"]
    here = [x for x in found if not airports or x[side] in airports]
    if not here:
        where = ", ".join(airports)
        return plain(f"This boarding pass is for a flight to {found[-1]['to']}. This shop sells to passengers arriving at {where}."
                     if settings["arriving"] else
                     f"This boarding pass is for a flight from {found[0]['from']}. This shop sells to passengers departing {where}.")
    steps = (0, -1, -2) if settings["arriving"] else (0, 1)
    days = {(today + datetime.timedelta(days=n)).timetuple().tm_yday for n in steps}
    if any(x["day"] in days for x in here):
        return ""
    return OTHER_DAY_ARRIVING if settings["arriving"] else OTHER_DAY


def limited_groups(item_group: str, groups: dict) -> list[str]:
    """The groups with an allowance that ``item_group`` falls under (itself included), by the tree's ``lft``/``rgt``."""
    g = groups.get(item_group)
    if not g:
        return []
    return [name for name, (lft, rgt, allowance, _unit) in groups.items() if allowance and lft <= g[0] and g[1] <= rgt]


def _fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def over_allowance(rows, groups: dict, touched) -> str:
    """The first allowance broken, in words, or ``""``. ``rows`` are ``(item_group, amount)`` for this sale's lines and the
    earlier sales' (an amount already in the allowance's own measure; a return's is negative); only the groups in
    ``touched`` (those this sale's own lines fall under) are judged, so an earlier sale alone never refuses this one."""
    totals: dict[str, float] = {}
    for item_group, amount in rows:
        for g in limited_groups(item_group, groups):
            totals[g] = totals.get(g, 0.0) + amount
    for g in sorted(set(touched)):
        allowance, unit = groups[g][2], groups[g][3]
        total = round(totals.get(g, 0.0), 6)
        if total > allowance + 1e-9:
            amount = f"{_fmt(total)} {plain(unit, 20)}".strip()
            return plain(f"{plain(g, 40)}: {amount} on this boarding pass; the allowance is {_fmt(allowance)}. "
                         "Take some off the sale.")
    return ""
