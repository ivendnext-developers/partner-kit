"""S64 — *Production station*: the pure core (no framework, no network), shared by the service and its tests.

A processing room's station screen opens by a signed link. A worker taps their name, a category and a price point; the
service makes the tag (the engine's own barcode with the price inside, in this week's colour) and counts it. *Cart full*
posts the cart into stock at no value and moves it to a store. A Desk button, *Work out*, writes who tagged how much and
what each colour week sold. This file holds what needs no shop:

    verify / records_of / message     the signed Desk presses (``desk_action/1``) and their answers
    sign / link_of / code_of          a station's link: the site, the station record and its number, signed
    colour_of / weeks_between         the colour of a day from the rotation (the lead's one-day colour wins on its day)
    price_points / price_of           a category's price points, and the one a tap names (never the page's own figure)
    read_back                         whether the engine read a tag's barcode back as its item and its price
    cart_lines / receipt / transfer   a cart's stock entries: lines by item at no value, the receipt, then the move
    worker_rows / colour_rows         the production report's rows

The signing helpers (``verify``, ``records_of``, ``message``, ``num``, ``sign``, ``link_of``, ``code_of``) are S59's
(``samples/s59_kitchen_screen/ksc.py``); a defect here is a defect there.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time
import urllib.parse

PREFIX = "PP PST"
SKEW_S = 300                 # a press stamped further than this from our clock is refused (a replay window)
SIG_LEN = 22                 # 22 base64url characters: 132 bits of the HMAC
DAYS_MAX = 92                # a production report covers at most this many days (one press reads them)
PRICE_MAX = 99999.99         # the largest price point a tag carries
TAG_MM = ((20, 150, 50), (10, 100, 30))   # (least, most, blank) millimetres: the tag's width, then its height
NAME_MAX = 140
FIELD_COLOUR = "pp_pst_tag_colour"     # the field on Item the manifest adds (its lower-case prefix)
FIELD_CART = "pp_pst_cart"             # the field on Stock Entry the manifest adds


def use_prefix(prefix: str):
    """The record types under another prefix: *IVENDNEXT PST Station* for the library's app."""
    global PREFIX, FIELD_COLOUR, FIELD_CART
    PREFIX = prefix
    low = prefix.lower().replace(" ", "_")
    FIELD_COLOUR, FIELD_CART = f"{low}_tag_colour", f"{low}_cart"


def dt(name: str) -> str:
    """The app's own record type: ``dt("Station")`` is *PP PST Station*."""
    return f"{PREFIX} {name}"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the press is the shop's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or len(ts) > 12 or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def records_of(body: dict, doctype: str, most: int = 50) -> list[str]:
    """The records a press names (one from the form, up to ``most`` ticked in the list), or ``ValueError``."""
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
                or not rec["name"] or len(rec["name"]) > NAME_MAX:
            raise ValueError("not a " + doctype)
        names.append(rec["name"])
    return list(dict.fromkeys(names))


def message(body: str, level: str = "success", refresh: bool = True, title: str = "Production station") -> dict:
    body = " ".join(str(body).split())
    return {"message": {"title": title, "body": body if len(body) <= 280 else body[:279].rstrip() + "…",
                        "level": level}, "refresh": refresh}


def num(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def money(v) -> float | None:
    """A price to the cent, or None when it is not one a tag can carry (blank, below a cent, too large)."""
    if isinstance(v, bool):
        return None
    try:
        p = round(float(v), 2)
    except (TypeError, ValueError):
        return None
    return p if 0.01 <= p <= PRICE_MAX else None


def text(v, most: int = NAME_MAX) -> str:
    return v.strip()[:most] if isinstance(v, str) else ""


# ── the station's link ───────────────────────────────────────────────────────────────────────────────────────────────

def sign(secret: bytes, site: str, record: str, number: int) -> str:
    mac = hmac.new(secret, f"pst1|{site}|{record}|{number}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode()[:SIG_LEN]


def link_of(page: str, site: str, record: str, number: int, secret: bytes) -> str:
    """The station's link: the page, the retailer's site, the station record and its number with their signature, after
    ``#`` (never sent to a server in the address, never in a log, never in another site's referrer)."""
    token = f"{record}.{number}.{sign(secret, site, record, number)}"
    return f"{page.rstrip('/')}/#s={urllib.parse.quote(site, safe='')}&t={urllib.parse.quote(token, safe='')}"


def code_of(site: str, token, secrets: list[bytes]) -> tuple[str, int] | None:
    """(the station record, its number) a link names, when its signature is the retailer's (the current secret or the
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


def made_for(station: dict) -> str:
    """What a link was made for: the station's settings. A link stops working when the station moves to other settings."""
    return hashlib.sha256((station.get("settings") or "").encode()).hexdigest()[:32]


# ── the settings: colours, workers, price points, places ─────────────────────────────────────────────────────────────

def _rows(settings: dict, table: str) -> list[dict]:
    rows = [r for r in settings.get(table) or [] if isinstance(r, dict)]
    return sorted(rows, key=lambda r: r.get("idx") if isinstance(r.get("idx"), int) else 0)


def day_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text(v)[:10])
    except ValueError:
        return None


def colours(settings: dict) -> list[str]:
    """The rotation's colours, in the lead's order, each once."""
    return list(dict.fromkeys(c for c in (text(r.get("colour"), 40) for r in _rows(settings, "colours")) if c))


def colour_of(settings: dict, day: datetime.date) -> tuple[str, datetime.date] | None:
    """(the colour of ``day``, the first day of that colour's week), or None when the rotation is not set. The colours
    turn each week from *First colour week starts*: colours[(whole weeks since then) mod n]. The lead's *Colour for one
    day* wins on its *On* date alone, and its week starts that day."""
    one, on = text(settings.get("day_colour"), 40), day_of(settings.get("day_colour_on"))
    if one and on == day:
        return one, day
    cs, first = colours(settings), day_of(settings.get("first_week"))
    if not cs or first is None:
        return None
    weeks = (day - first).days // 7
    return cs[weeks % len(cs)], first + datetime.timedelta(days=7 * weeks)


def weeks_between(settings: dict, frm: datetime.date, to: datetime.date) -> list[tuple[str, datetime.date]]:
    """Every colour week of the rotation that overlaps ``frm``..``to``, oldest first, and the lead's one-day colour when
    its day is in the range: [(colour, first day)]."""
    out = []
    cs, first = colours(settings), day_of(settings.get("first_week"))
    if cs and first is not None:
        start = first + datetime.timedelta(days=7 * ((frm - first).days // 7))
        while start <= to:
            out.append((cs[((start - first).days // 7) % len(cs)], start))
            start += datetime.timedelta(days=7)
    one, on = text(settings.get("day_colour"), 40), day_of(settings.get("day_colour_on"))
    if one and on is not None and frm <= on <= to and (one, on) not in out:
        out.append((one, on))
    return sorted(out, key=lambda w: (w[1], w[0]))


def sold_window(week_start: datetime.date, n_colours: int, today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """The days a colour week's pieces are counted as sold: from its first day until the colour's next turn (first day +
    7 x the number of colours - 1), or today, whichever is earlier."""
    end = week_start + datetime.timedelta(days=7 * max(n_colours, 1) - 1)
    return week_start, min(end, today)


def workers(settings: dict) -> list[str]:
    """The active workers' names, in the lead's order, each once."""
    names = (text(r.get("worker_name"), 80) for r in _rows(settings, "workers") if num(r.get("active")))
    return list(dict.fromkeys(n for n in names if n))


def price_points(settings: dict) -> dict:
    """{category: [prices]} in the lead's order: each category once, each of its prices once, to the cent."""
    out: dict = {}
    for r in _rows(settings, "price_points"):
        cat, p = text(r.get("category")), money(r.get("price"))
        if cat and p is not None:
            prices = out.setdefault(cat, [])
            if p not in prices:
                prices.append(p)
    return out


def price_of(points: dict, category, sent) -> float | None:
    """The settings' own price point a tap names, or None. The page's figure only picks one: the price written on the
    tag is the settings'."""
    p = money(sent)
    if p is None or not isinstance(category, str) or category not in points:
        return None
    return next((q for q in points[category] if abs(q - p) < 0.005), None)


def places(settings: dict) -> list[dict]:
    """The places a cart can go: [{"warehouse", "label"}], each warehouse once."""
    out, seen = [], set()
    for r in _rows(settings, "places"):
        wh = text(r.get("warehouse"))
        if wh and wh not in seen:
            seen.add(wh)
            out.append({"warehouse": wh, "label": text(r.get("label"), 60) or wh})
    return out


def tag_size(settings: dict) -> dict:
    out = {}
    for key, field, (lo, hi, blank) in (("width_mm", "tag_width_mm", TAG_MM[0]), ("height_mm", "tag_height_mm", TAG_MM[1])):
        n = num(settings.get(field))
        out[key] = blank if not n else max(lo, min(hi, n))
    return out


# ── a tag ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def item_for(rows: list, colour: str) -> dict | None:
    """The category's item whose *Tag colour* is ``colour`` (rows of Item with ``name``, the tag colour field,
    ``custom_barcode_mask`` and ``barcode``, one row per barcode): the first by item code, with all its barcodes."""
    found: dict = {}
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("name"), str) or not r["name"] \
                or text(r.get(FIELD_COLOUR), 40).lower() != colour.lower():
            continue
        it = found.setdefault(r["name"], {"name": r["name"], "mask": text(r.get("custom_barcode_mask")), "barcodes": []})
        bar = text(r.get("barcode"))
        if bar and bar not in it["barcodes"]:
            it["barcodes"].append(bar)
    return found[min(found)] if found else None


def read_back(resolved, item: dict, price: float) -> bool:
    """Whether the engine's barcode reader read a tag's barcode as its item and its price to the cent: what the till
    will charge. A site whose labels carry a price their scan does not read back (before the engine's label fix of
    12 October 2026) answers another price, and the tag is refused."""
    if not isinstance(resolved, dict) or not resolved.get("barcode_masked") or resolved.get("error"):
        return False
    code, bar = text(resolved.get("item_code")), text(resolved.get("item_barcode"))
    same = (code and code == item["name"]) or (bar and bar in item["barcodes"])
    try:
        got = round(float(resolved.get("scanned_price") or 0), 2)
    except (TypeError, ValueError):
        return False
    return bool(same) and abs(got - price) < 0.005


# ── a cart ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def cart_lines(tags: list) -> list[tuple[str, int]]:
    """[(item, quantity)] of a cart's tags, one line per item, by item code: a voided tag is never received."""
    out: dict = {}
    for t in tags:
        if not isinstance(t, dict) or num(t.get("void")) or not isinstance(t.get("item"), str) or not t["item"]:
            continue
        q = num(t.get("quantity"))
        if q > 0:
            out[t["item"]] = out.get(t["item"], 0) + q
    return sorted(out.items())


def receipt(company: str, room: str, cart: str, lines: list, uoms: dict) -> dict:
    """The cart's Material Receipt into the processing room, at no value, naming the cart; submitted as it is made."""
    return {"stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
            "to_warehouse": room, FIELD_CART: cart, "docstatus": 1, "remarks": f"Production cart {cart}",
            "items": [{"item_code": i, "qty": q, "uom": uoms[i], "stock_uom": uoms[i], "conversion_factor": 1,
                       "t_warehouse": room, "basic_rate": 0, "allow_zero_valuation_rate": 1} for i, q in lines]}


def transfer(company: str, room: str, to: str, cart: str, lines: list, uoms: dict) -> dict:
    """The same lines moved from the processing room to the place chosen, naming the cart; submitted as it is made."""
    return {"stock_entry_type": "Material Transfer", "purpose": "Material Transfer", "company": company,
            "from_warehouse": room, "to_warehouse": to, FIELD_CART: cart, "docstatus": 1,
            "remarks": f"Production cart {cart}",
            "items": [{"item_code": i, "qty": q, "uom": uoms[i], "stock_uom": uoms[i], "conversion_factor": 1,
                       "s_warehouse": room, "t_warehouse": to, "allow_zero_valuation_rate": 1} for i, q in lines]}


def finished(cart: dict) -> bool:
    """A cart is done when it was sent, or received and kept where it was received (its *Open for* cleared). It never
    reads today's settings, so a room changed later never moves a kept cart."""
    state = cart.get("state")
    return state == "Sent" or (state == "Received" and not cart.get("open_for"))


def req_of(v) -> str | None:
    """A tap's own request id (the page makes one per tap and sends the same one again after a lost answer), or None."""
    return v if isinstance(v, str) and 8 <= len(v) <= 40 and all(c.isalnum() or c == "-" for c in v) else None


# ── the production report ────────────────────────────────────────────────────────────────────────────────────────────

def worker_rows(groups: list) -> list[dict]:
    """One row per day, station and worker: pieces (the non-void tags' quantity), hours (the clock hours in which the
    worker tagged) and pieces per hour. ``groups`` are rows of (tagged_on, station, worker, hour, pieces)."""
    acc: dict = {}
    for g in groups:
        if not isinstance(g, dict):
            continue
        key = (text(g.get("tagged_on"))[:10], text(g.get("station")), text(g.get("worker"), 80))
        if not all(key) or num(g.get("pieces")) <= 0:
            continue
        a = acc.setdefault(key, {"pieces": 0, "hours": set()})
        a["pieces"] += num(g.get("pieces"))
        a["hours"].add(num(g.get("hour")))
    rows = []
    for (day, station, worker), a in sorted(acc.items()):
        hours = len(a["hours"])
        rows.append({"day": day, "station": station, "worker": worker, "pieces": a["pieces"], "hours": hours,
                     "per_hour": round(a["pieces"] / hours, 1) if hours else 0.0})
    return rows


def colour_rows(weeks: list, tagged: dict, sold: dict) -> list[dict]:
    """One row per colour week: tagged (non-void pieces of that week), sold (that colour's units the till sold in the
    week's window) and sell-through (sold ÷ tagged, as a percent to one place; blank when nothing was tagged)."""
    rows = []
    for colour, start in weeks:
        key = (colour, start.isoformat())
        t, s = tagged.get(key, 0), sold.get(key, 0.0)
        rows.append({"colour": colour, "week_start": start.isoformat(), "tagged": t, "sold": round(s, 3),
                     "sell_through": round(100.0 * s / t, 1) if t > 0 else None})
    return rows


def summary_of(rows: list, crows: list, frm: datetime.date, to: datetime.date) -> str:
    pieces = sum(r["pieces"] for r in rows)
    people = len({r["worker"] for r in rows})
    s = (f"{frm.isoformat()} to {to.isoformat()}: {pieces} piece{'' if pieces == 1 else 's'} tagged by {people} "
         f"worker{'' if people == 1 else 's'}.")
    if crows:
        tagged, sold = sum(r["tagged"] for r in crows), sum(r["sold"] for r in crows)
        s += f" Colour weeks: {tagged} tagged, {sold:g} sold."
    return s
