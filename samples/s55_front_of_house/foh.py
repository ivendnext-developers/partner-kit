"""S55 — *Front of house*: the pure core (no framework, no network), shared by the service and its tests.

Four Desk buttons send one signed POST per press each (the Desk action extension point, ``desk_action/1``):

    Book      on a reservation        → /press/book     the table is held: no other booking overlaps it
    Seat      on a reservation or a   → /press/seat     the table's check opens through the till's open-check
              waiting party                             door (``check_open``), with the party's size
    No-show   on a reservation        → /press/noshow   the booking is a no-show, the store's deposit rule written on it
    Cancel    on a reservation        → /press/cancel   the booking is cancelled and its table freed

``verify`` checks the signature the shop puts on every call; ``records_of`` takes a press's record; ``span`` and
``clashes`` are the double-booking guard; ``seat_request`` builds the one call that opens a check; ``place_busy`` reads
the floor. ⛔ No answer writes anything: the service writes through its own API key and its own rights, BEFORE it
answers. ⛔ The guest's name, phone, customer and notes are never read here: the app's user cannot read them.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time

PREFIX = "PP FOH"
SKEW_S = 300                # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140              # the door keeps 140 characters of a label and a reference
BODY_WORDS = 280            # a Desk answer's body
SOURCE = "front_of_house"   # the door's own name for a front-of-house app (20 characters at most)
LENGTH = 90                 # a booking's length in minutes when neither the booking nor its store's row says
HOLDING = ("Booked", "Seated")      # the bookings that hold their table
OPEN_STATES = ("Requested", "Booked")   # a booking that may still be booked, seated, marked a no-show or cancelled


def use_prefix(prefix: str):
    """The record types under another prefix: *IVENDNEXT FOH Reservation* for the library's app."""
    global PREFIX
    PREFIX = prefix


def dt(name: str) -> str:
    """The app's own record type: ``dt("Reservation")`` is *PP FOH Reservation*."""
    return f"{PREFIX} {name}"


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


def records_of(body: dict, doctypes: tuple) -> tuple[str, str]:
    """The one record a press names, ``(doctype, name)``, or ``ValueError``: checked before anything is read."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    recs = ctx["records"]
    if len(recs) != 1:
        raise ValueError("one record a press")
    rec = recs[0]
    if not isinstance(rec, dict) or rec.get("doctype") not in doctypes or not isinstance(rec.get("name"), str) \
            or not rec["name"]:
        raise ValueError("not a " + " or ".join(doctypes))
    return rec["doctype"], rec["name"]


def fit(text: str, most: int = BODY_WORDS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


def message(title: str, body: str, level: str = "success", refresh: bool = True) -> dict:
    out = {"message": {"title": title[:60], "body": fit(body or "Nothing to do."), "level": level}}
    if refresh:
        out["refresh"] = True
    return out


def num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def moment(date_text, time_text) -> datetime.datetime | None:
    """The shop's own date and time (its site's clock, as it stores them) as one moment, or None."""
    try:
        d = datetime.date.fromisoformat(str(date_text)[:10])
        h, m, *s = (str(time_text or "").split(".")[0].split(":") + ["0"])[:3]
        return datetime.datetime(d.year, d.month, d.day, int(h), int(m), int(float(s[0] or 0)))
    except (TypeError, ValueError):
        return None


def stamp(text) -> datetime.datetime | None:
    """A record's ``modified`` (the site's clock) as a moment, or None."""
    try:
        return datetime.datetime.fromisoformat(str(text).split(".")[0])
    except (TypeError, ValueError):
        return None


def minutes_of(record: dict, row: dict) -> int:
    """A booking's length: its own, else its store's usual, else 90 minutes; at most 24 hours."""
    m = num(record.get("minutes")) or num((row or {}).get("minutes")) or LENGTH
    return max(15, min(m, 24 * 60))


def span(start: datetime.datetime, minutes: int) -> tuple[datetime.datetime, datetime.datetime]:
    return start, start + datetime.timedelta(minutes=minutes)


def clashes(mine: tuple, others: list[dict], rows_by_store: dict, exclude: str = "") -> list[dict]:
    """The bookings that hold the same table at an overlapping time, earliest first.

    ``mine`` is ``(start, end)``; each other booking holds its table from its start for its length (its own, or its
    store's usual). Only *Booked* and *Seated* bookings hold a table; a *Requested* one holds nothing yet."""
    start, end = mine
    out = []
    for o in others:
        if o.get("name") == exclude or o.get("status") not in HOLDING:
            continue
        s = moment(o.get("booking_date"), o.get("booking_time"))
        if s is None:
            continue
        s, e = span(s, minutes_of(o, rows_by_store.get(o.get("store")) or {}))
        if s < end and start < e:
            out.append(dict(o, _start=s, _end=e))
    return sorted(out, key=lambda o: (o["_start"], o.get("name") or ""))


def clash_words(o: dict, place_label: str) -> str:
    when = f"{o['_start']:%H:%M} to {o['_end']:%H:%M}"
    day = "" if o["_start"].date() == o["_end"].date() else f" on {o['_start']:%d %b}"
    return f"{place_label} is booked from {when}{day} ({o['name']}, {num(o.get('party'))} guests)."


def days_around(start: datetime.datetime) -> list[str]:
    """The booking dates a clash can come from: the day before (a booking running past midnight), the day, the next."""
    d = start.date()
    return [(d + datetime.timedelta(days=k)).isoformat() for k in (-1, 0, 1)]


def label_of(name: str, party: int, deposit) -> str:
    """The check's label: the booking's number and its size, and its deposit when it took one. Never a name."""
    text = f"{name} · {party}"
    try:
        amount = float(deposit or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount > 0:
        text += f" · deposit {amount:.2f}"
    return text[:TEXT_MAX]


def seat_request(store: str, register: str, key: str, place: str, name: str, party: int, deposit=None) -> dict:
    """The one call that opens the party's check, sent exactly so again on a retry (the door returns its first answer
    for the same key and arguments; other arguments are refused). No server (the first till to write serves it), no
    customer (the guest's details stay in the shop)."""
    return {"store": store, "pos_profile": register, "key": key, "place": place, "covers": party,
            "label": label_of(name, party, deposit), "source": SOURCE, "source_ref": name[:TEXT_MAX]}


def place_busy(floor: dict, place: str) -> bool:
    """True when the floor shows an open check at the place (any status but *free*)."""
    for p in (floor or {}).get("places") or []:
        if isinstance(p, dict) and p.get("place") == place:
            return p.get("status") not in (None, "", "free") or bool(p.get("checks"))
    return False


def deposit_note(rule: str, deposit_sale: str, amount, cancelled: bool = False) -> str:
    """What the store's rule says to do with a no-show's (or a cancellation's) deposit. The app moves no money."""
    if not deposit_sale:
        return ""
    try:
        sum_ = f"{float(amount or 0):.2f}"
    except (TypeError, ValueError):
        sum_ = str(amount)
    on_file = f"The deposit ({deposit_sale}, {sum_}) is on the guest's money on file."
    if cancelled:
        return on_file + " Return it or keep it as your booking terms say."
    if (rule or "").startswith("Return"):
        return on_file + " Your store's rule is to return it: pay it back to the guest from there."
    return on_file + " Your store's rule is to keep it: your accountant books it to income from there."
