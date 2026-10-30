"""S59 — *Kitchen screen*: the pure core (no framework, no network), shared by the service and its tests.

A screen's page reads its store's board through the service; the service reads the till's station-ticket door
(``station_tickets``) as the app's own user and answers what that screen may see. This file holds what needs no shop:

    sign / code_of        a screen's link: the site, the screen record and its number, signed with the app's secret
    clean_ticket          one ticket from the door, kept to the fields the page draws and their lengths
    station_view          a station screen: its stations' tickets not yet bumped, and the recall list
    expo_view             the expo: each order's tickets together, what is still waiting, which orders may be bumped
    board_view            the Now serving board: the call numbers preparing and ready
    may_move              whether a screen may move a ticket to a state (its own station, one step, never the board)

The signing helpers (``verify``, ``records_of``, ``message``, ``num``, ``setting``, ``sign``, ``link_of``, ``code_of``)
are copied from S56 (``samples/s56_guest_ordering/gor.py``, kit ``6bf1024``); a defect here is a defect there.
⛔ Nothing here voids, comps or changes a line, or carries a price: a ticket has none.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
import urllib.parse

PREFIX = "PP KSC"
SKEW_S = 300                 # a press stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024        # a press
PAGE_BODY_MAX = 4 * 1024     # a screen's call
SIG_LEN = 22                 # 22 base64url characters: 132 bits of the HMAC
KIND_STATION, KIND_EXPO, KIND_BOARD = "Station", "Expo", "Board"
KINDS = (KIND_STATION, KIND_EXPO, KIND_BOARD)
NEXT = {"new": "started", "started": "ready", "ready": "bumped"}   # the door's one step; no step back
WARN = (1, 120, 8)           # (least, most, blank) minutes before a ticket's timer turns amber
LATE = (1, 240, 15)          # … and red
LANGS = {"English": "en", "Arabic": "ar", "Spanish": "es", "French": "fr", "German": "de", "Portuguese": "pt"}
SIZES = {"Compact": "compact", "Standard": "standard", "Large": "large", "Extra large": "xlarge"}   # the slips' size steps
TICKETS_MAX = 300            # tickets one screen's answer carries to a page (after its own filter)
BOARD_MAX = 2000             # tickets of one store's board a copy keeps (the newest, when a board is larger)
LINES_MAX = 60               # lines one ticket carries
DISHES_MAX = 100             # dishes the sold-out list offers
_ORDER = re.compile(r"[A-Za-z0-9_-]{1,140}")   # the door names an order by its record name (a hash)
_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}")


def use_prefix(prefix: str):
    """The record types under another prefix: *IVENDNEXT KSC Screen* for the library's app."""
    global PREFIX
    PREFIX = prefix


def dt(name: str) -> str:
    """The app's own record type: ``dt("Screen")`` is *PP KSC Screen*."""
    return f"{PREFIX} {name}"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the press is the shop's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def records_of(body: dict, doctype: str, most: int = 50) -> list[str]:
    """The screen records a press names (one from the form, up to ``most`` ticked in the list), or ``ValueError``."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    recs = ctx["records"]
    if not recs or len(recs) > most:
        raise ValueError(f"between 1 and {most} records a press")
    names = []
    for rec in recs:
        if not isinstance(rec, dict) or rec.get("doctype") != doctype or not isinstance(rec.get("name"), str) \
                or not rec["name"] or len(rec["name"]) > 140:
            raise ValueError("not a " + doctype)
        names.append(rec["name"])
    return list(dict.fromkeys(names))


def message(body: str, level: str = "success", refresh: bool = True, title: str = "Kitchen screen") -> dict:
    body = " ".join(str(body).split())
    return {"message": {"title": title, "body": body if len(body) <= 280 else body[:279].rstrip() + "…",
                        "level": level}, "refresh": refresh}


def num(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def setting(v, rng: tuple[int, int, int]) -> int:
    """A store row's whole number within its range, or its default when blank."""
    lo, hi, blank = rng
    n = num(v)
    return blank if not n else max(lo, min(hi, n))


# ── the screen's link ────────────────────────────────────────────────────────────────────────────────────────────────

def sign(secret: bytes, site: str, record: str, number: int) -> str:
    mac = hmac.new(secret, f"ksc1|{site}|{record}|{number}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode()[:SIG_LEN]


def link_of(page: str, site: str, record: str, number: int, secret: bytes) -> str:
    """The screen's link: the page, the retailer's site, the screen record and its number with their signature, after
    ``#`` (never sent to a server in the address, never in a log, never in another site's referrer)."""
    token = f"{record}.{number}.{sign(secret, site, record, number)}"
    return f"{page.rstrip('/')}/#s={urllib.parse.quote(site, safe='')}&t={urllib.parse.quote(token, safe='')}"


def code_of(site: str, token, secrets: list[bytes]) -> tuple[str, int] | None:
    """(the screen record, its number) a link names, when its signature is the retailer's (the current secret or the
    one before): else None, and nothing is read."""
    if not isinstance(token, str) or len(token) > 200:
        return None
    parts = token.rsplit(".", 2)
    if len(parts) != 3 or not parts[0] or not (parts[1].isascii() and parts[1].isdigit()) or len(parts[2]) != SIG_LEN:
        return None
    try:
        record, number, sig = parts[0], int(parts[1]), parts[2]
        if number < 1:
            return None
        return (record, number) if any(hmac.compare_digest(sign(s, site, record, number), sig) for s in secrets) else None
    except ValueError:                  # a digit int() refuses, a character UTF-8 refuses: not the retailer's link
        return None


def stations_of(screen: dict) -> list[str]:
    """The screen's stations, in its rows' order, each once."""
    rows = screen.get("stations") or []
    names = [r.get("station") for r in rows if isinstance(r, dict) and isinstance(r.get("station"), str) and r.get("station")]
    return list(dict.fromkeys(names))


def made_for(screen: dict) -> str:
    """What a link was made for: the screen's kind, store and stations. A link stops working when any of them changes."""
    s = "|".join([screen.get("kind") or "", screen.get("store") or "", ",".join(sorted(stations_of(screen)))])
    return hashlib.sha256(s.encode()).hexdigest()[:32]


# ── the board ────────────────────────────────────────────────────────────────────────────────────────────────────────

def _text(v, most: int) -> str:
    return v[:most] if isinstance(v, str) else ""


def _qty(v) -> float:
    try:
        q = float(v)
    except (TypeError, ValueError):
        return 0.0
    return round(q, 3) if 0 < q < 100000 else 0.0


def clean_ticket(t) -> dict | None:
    """One ticket as the page may draw it: the door's own fields, each of its kind and length; None when it is not a
    ticket (no order, no number, a state or kind the door does not use)."""
    if not isinstance(t, dict):
        return None
    order, n = t.get("kitchen_order"), t.get("ticket")
    if not (isinstance(order, str) and _ORDER.fullmatch(order)) or not isinstance(n, int) or isinstance(n, bool) \
            or not 0 < n < 100000 or t.get("state") not in ("new", "started", "ready", "bumped") \
            or t.get("kind") not in ("send", "void"):
        return None
    lines = []
    for ln in (t.get("lines") or [])[:LINES_MAX]:
        if not isinstance(ln, dict):
            continue
        under = ln.get("under")
        lines.append({"item_code": _text(ln.get("item_code"), 140), "item_name": _text(ln.get("item_name"), 140),
                      "qty": _qty(ln.get("qty")), "note": _text(ln.get("note"), 200),
                      "under": under if isinstance(under, int) and not isinstance(under, bool) and 0 <= under < LINES_MAX
                      else None,
                      "guest": _text(ln.get("guest"), 40), "course": _text(ln.get("course"), 60),
                      "allergens": _text(ln.get("allergens"), 240)})
    return {"kitchen_order": order, "ticket": n, "station": _text(t.get("station"), 140), "kind": t["kind"],
            "source": "check" if t.get("source") == "check" else "sale", "call_number": _text(t.get("call_number"), 60),
            "till": _text(t.get("till"), 140), "sent_at": _text(t.get("sent_at"), 32), "state": t["state"],
            "state_at": _text(t.get("state_at"), 32), "lines": lines}


def tickets_of(board) -> list[dict]:
    """Every ticket of a door's answer, cleaned, in the door's order (oldest first)."""
    raw = board.get("tickets") if isinstance(board, dict) else None
    return [c for c in (clean_ticket(t) for t in (raw if isinstance(raw, list) else [])[-BOARD_MAX:]) if c]


def station_view(tickets: list[dict], stations: list[str]) -> dict:
    """A station screen: its stations' tickets not yet bumped (oldest first), and those bumped in the door's last 30
    minutes, newest first, to read again."""
    mine = [t for t in tickets if t["station"] in stations]
    live = [t for t in mine if t["state"] != "bumped"][:TICKETS_MAX]
    recall = sorted((t for t in mine if t["state"] == "bumped"), key=lambda t: t["state_at"], reverse=True)[:50]
    return {"tickets": live, "recall": recall}


def _orders(tickets: list[dict]) -> dict[str, list[dict]]:
    orders: dict[str, list[dict]] = {}
    for t in tickets:
        orders.setdefault(t["kitchen_order"], []).append(t)
    return orders


def _ready(ts: list[dict]) -> bool:
    """Every send ticket of an order is ready or bumped, and at least one is ready (void tickets left out)."""
    sends = [t for t in ts if t["kind"] == "send"]
    return bool(sends) and all(t["state"] in ("ready", "bumped") for t in sends) and any(t["state"] == "ready" for t in sends)


def waiting(tickets: list[dict]) -> list[dict]:
    """What is still to make: each dish's quantity over every send ticket not yet ready, less what a void ticket of the
    same order cancels; choices (a line ``under`` another) are not counted. Most first."""
    want: dict[tuple, float] = {}
    names: dict[str, str] = {}
    for t in tickets:
        if t["kind"] == "send" and t["state"] not in ("new", "started"):
            continue
        sign_ = 1 if t["kind"] == "send" else -1
        for ln in t["lines"]:
            if ln["under"] is not None or not ln["item_code"]:
                continue
            key = (t["kitchen_order"], ln["item_code"])
            want[key] = want.get(key, 0.0) + sign_ * ln["qty"]
            names.setdefault(ln["item_code"], ln["item_name"] or ln["item_code"])
    total: dict[str, float] = {}
    for (_, code), q in want.items():
        if q > 0:
            total[code] = total.get(code, 0.0) + q
    return [{"item_code": c, "item_name": names[c], "qty": round(q, 3)}
            for c, q in sorted(total.items(), key=lambda kv: (-kv[1], names[kv[0]]))]


def expo_view(tickets: list[dict]) -> dict:
    """The expo: one card per order with a send ticket not yet bumped (oldest first), its tickets by number;
    ``bump`` when every send ticket is ready or bumped and one is ready; and what is still waiting."""
    cards = []
    for order, ts in _orders(tickets).items():
        live = [t for t in ts if t["kind"] == "send" and t["state"] != "bumped"]
        if not live:                    # every dish of it gone (a void left is the station's to bump): off the pass
            continue
        ts = sorted(ts, key=lambda t: t["ticket"])
        cards.append({"kitchen_order": order, "call_number": ts[-1]["call_number"], "source": ts[0]["source"],
                      "sent_at": min(t["sent_at"] for t in live), "bump": _ready(ts), "tickets": ts})
    cards.sort(key=lambda c: c["sent_at"])
    return {"orders": cards[:TICKETS_MAX], "waiting": waiting(tickets)}


def board_view(tickets: list[dict], tables: bool) -> dict:
    """The Now serving board: call numbers only (no dish, no till). An order is *ready* when ``_ready``; it leaves when
    every send ticket is bumped. Counter sales only unless ``tables``."""
    preparing, ready = [], []
    for ts in _orders(tickets).values():
        sends = [t for t in ts if t["kind"] == "send"]
        if all(t["state"] == "bumped" for t in sends) or not (tables or sends[0]["source"] == "sale"):
            continue
        call = sends[-1]["call_number"]
        if not call:
            continue
        (ready if _ready(ts) else preparing).append(call)
    return {"preparing": list(dict.fromkeys(preparing))[:60], "ready": list(dict.fromkeys(ready))[:60]}


def find(tickets: list[dict], order, number) -> dict | None:
    for t in tickets:
        if t["kitchen_order"] == order and t["ticket"] == number:
            return t
    return None


def may_move(kind: str, stations: list[str], ticket: dict | None, state: str) -> str:
    """``""`` when this screen may move this ticket to ``state``, else why not. A station screen moves its own
    stations' tickets one step; the expo only bumps a ready ticket; the board moves nothing."""
    if kind == KIND_BOARD:
        return "board"
    if ticket is None:
        return "gone"
    if kind == KIND_STATION and ticket["station"] not in stations:
        return "not_yours"
    if kind == KIND_EXPO and state != "bumped":
        return "not_yours"
    if NEXT.get(ticket["state"]) != state and ticket["state"] != state:
        return "step"
    return ""


def dishes(tickets: list[dict]) -> list[dict]:
    """The dishes a sold-out list offers: each item on the board's send tickets, once, by name."""
    seen: dict[str, str] = {}
    for t in tickets:
        if t["kind"] != "send":
            continue
        for ln in t["lines"]:
            if ln["item_code"] and ln["item_code"] not in seen:
                seen[ln["item_code"]] = ln["item_name"] or ln["item_code"]
    return [{"item_code": c, "item_name": n} for c, n in sorted(seen.items(), key=lambda kv: kv[1])][:DISHES_MAX]


def sold_out_of(rows) -> list[dict]:
    """The store's items sold out now, from the door's ``item_availability`` answer."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and isinstance(r.get("item_code"), str) and r.get("sold_out") and not r.get("available"):
            out.append({"item_code": r["item_code"][:140]})
    return out[:DISHES_MAX]


def look(row: dict) -> dict:
    """The store row's look for its screens: mode, an accent colour (only ``#rrggbb``), the language, the timers, and the
    slips' size (a cook's A- / A+ on one screen overrides it there, remembered on that device)."""
    accent = row.get("accent") if isinstance(row.get("accent"), str) and _COLOUR.fullmatch(row.get("accent") or "") else ""
    return {"mode": "light" if row.get("look") == "Light" else "dark", "accent": accent,
            "lang": LANGS.get(row.get("language") or "", "en"),
            "warn": setting(row.get("warn_min"), WARN), "late": max(setting(row.get("late_min"), LATE),
                                                                     setting(row.get("warn_min"), WARN) + 1),
            "size": SIZES.get(row.get("slip_size") or "", "standard")}
