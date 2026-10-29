"""S56 — *Guest ordering*: the pure core (no framework, no network), shared by the service and its tests.

A guest scans a table's code (or uses the store's kiosk), reads the register's menu and sends an order; the service adds
it to the table's check (or a kiosk tab) through the till's open-check door. This file holds what needs no shop:

    sign / code_of        the code's link: the site, the code record and its number, signed with the app's secret
    menu_of               the menu the page shows, from the register, its items, their choice rows and prices
    order_lines           a guest's order checked against that menu and the store's limits, as the door's lines
    door_key / kiosk_code the door's keys and the kiosk's order code, made from the page's own key

⛔ Nothing here prices a line the door keeps: a line carries no price, and the bill is priced when it is paid.
⛔ A guest's order is never sent to the kitchen: every line waits unsent for a person at the till.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
import unicodedata
import urllib.parse

PREFIX = "PP GOR"
SKEW_S = 300                 # a press stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024        # a press
PAGE_BODY_MAX = 16 * 1024    # a guest's call
SIG_LEN = 22                 # 22 base64url characters: 132 bits of the HMAC
SOURCE = "guest_ordering"    # the door's own name for the app (20 characters at most)
NOTE_MAX = 80                # a guest's note for the kitchen
LINES = (1, 50, 10)          # (least, most, blank) lines in one order: the store row's setting, at most the door's 50
QTY = (1, 99, 10)            # (least, most, blank) of one dish in one order
COURSE = "Guest order"       # the course a guest's lines carry when the store row names none
MENU_MAX = 300               # dishes on one menu
SPACING_S = 15               # one order per code this often
KIOSK_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 31: no 0/O, 1/I/L
KIOSK_LEN = 5
KIND_TABLE, KIND_KIOSK = "Table", "Kiosk"
_KEY = re.compile(r"[A-Za-z0-9-]{16,64}")


def use_prefix(prefix: str):
    """The record types under another prefix: *IVENDNEXT GOR Code* for the library's app."""
    global PREFIX
    PREFIX = prefix


def dt(name: str) -> str:
    """The app's own record type: ``dt("Code")`` is *PP GOR Code*."""
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


def records_of(body: dict, doctype: str, most: int = 100) -> list[str]:
    """The code records a press names (one from the form, up to ``most`` ticked in the list), or ``ValueError``."""
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


def message(body: str, level: str = "success", refresh: bool = True, title: str = "Guest ordering") -> dict:
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


# ── the code's link ──────────────────────────────────────────────────────────────────────────────────────────────────

def sign(secret: bytes, site: str, record: str, number: int) -> str:
    mac = hmac.new(secret, f"gor1|{site}|{record}|{number}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode()[:SIG_LEN]


def link_of(page: str, site: str, record: str, number: int, secret: bytes) -> str:
    """The code's link: the page, the retailer's site, the code record and its number with their signature, after
    ``#`` (never sent to a server in the address, never in a log, never in another site's referrer)."""
    token = f"{record}.{number}.{sign(secret, site, record, number)}"
    return f"{page.rstrip('/')}/#s={urllib.parse.quote(site, safe='')}&t={urllib.parse.quote(token, safe='')}"


def code_of(site: str, token, secrets: list[bytes]) -> tuple[str, int] | None:
    """(the code record, its number) a link names, when its signature is the retailer's (the current secret or the one
    before): else None, and nothing is read."""
    if not isinstance(token, str) or len(token) > 200:
        return None
    parts = token.rsplit(".", 2)
    if len(parts) != 3 or not parts[0] or not parts[1].isdigit() or len(parts[2]) != SIG_LEN:
        return None
    try:
        record, number, sig = parts[0], int(parts[1]), parts[2]
        if number < 1:
            return None
        return (record, number) if any(hmac.compare_digest(sign(s, site, record, number), sig) for s in secrets) else None
    except ValueError:                  # a digit int() refuses, a character UTF-8 refuses: not the retailer's link
        return None


# ── the menu ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def money(v) -> float | None:
    try:
        return round(float(v), 6) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def choice_price(row: dict, list_rate) -> float | None:
    """A choice's price under its dish, as the till books it (``cross_selling._preview_rates``): the row's own price
    when its price type is *Amount*, else the choice's list price, less the row's discount."""
    base = money(row.get("price")) if row.get("price_type") == "Amount" else money(list_rate)
    if base is None:
        return None
    off = money(row.get("discount")) or 0
    if row.get("discount_type") == "Amount" and off:
        return round(base - off, 6)
    if row.get("discount_type") == "Percentage" and off:
        return round(base * (1 - off / 100.0), 6)
    return base


def menu_of(items: list[dict], rows: list[dict], groups: dict, prices: dict, order: list[str] | None = None) -> list[dict]:
    """The page's menu, by item group: each dish with its price and its choice groups, each choice with its price.

    ``items`` are the dishes' Item rows (read without the items sold only as a choice); ``rows`` their *Cross Selling Product Detail* rows (``parent`` the dish); a
    row is a choice when it names a *Retail Option Group* (``custom_mpos_option_group``) found, switched on, in
    ``groups`` (``display_name``, ``min_picks``, ``max_picks``, ``enabled``); any other row is an ordinary offer and is
    not shown. ``prices`` holds an item's list price by code."""
    dishes: dict[str, dict] = {}
    for r in items:
        code = r.get("name")
        if not isinstance(code, str) or not code or code in dishes:
            continue
        if len(dishes) >= MENU_MAX:
            break
        dishes[code] = {"code": code, "name": r.get("item_name") or code, "group": r.get("item_group") or "",
                        "price": money(prices.get(code)), "groups": {}}
    for r in sorted(rows, key=lambda r: num(r.get("idx"))):
        d, g, choice = dishes.get(r.get("parent")), r.get("custom_mpos_option_group"), r.get("item_code")
        meta = groups.get(g) if g else None
        if d is None or not choice or not meta or not num(meta.get("enabled", 1)):
            continue
        grp = d["groups"].setdefault(g, {"group": g, "label": meta.get("display_name") or g,
                                         "min": num(meta.get("min_picks")), "max": num(meta.get("max_picks")),
                                         "choices": []})
        if all(c["code"] != choice for c in grp["choices"]):
            grp["choices"].append({"code": choice, "name": r.get("item_name") or choice,
                                   "price": choice_price(r, prices.get(choice))})
    sections: dict[str, list] = {}
    for d in dishes.values():
        d["groups"] = list(d["groups"].values())
        sections.setdefault(d["group"], []).append(d)
    names = [g for g in (order or []) if g in sections] + sorted(g for g in sections if g not in (order or []))
    return [{"group": g, "dishes": sorted(sections[g], key=lambda d: d["name"].lower())} for g in names]


def dishes_of(menu: list[dict]) -> dict[str, dict]:
    return {d["code"]: d for s in menu for d in s["dishes"]}


# ── an order ─────────────────────────────────────────────────────────────────────────────────────────────────────────

class Refused(Exception):
    """An order the service will not send: the words go to the guest; nothing was written."""

    def __init__(self, words: str):
        super().__init__(words)
        self.words = words


def clean_note(v) -> str:
    """A guest's note for the kitchen: one line of printable text, at most ``NOTE_MAX`` characters."""
    if not isinstance(v, str):
        return ""
    text = "".join(c if unicodedata.category(c)[0] not in ("C", "Z") or c == " " else " " for c in v)
    text = " ".join(text.split())
    return text[:NOTE_MAX]


def order_lines(raw, menu: list[dict], most_lines: int, most_qty: int, course: str) -> list[dict]:
    """The guest's order as the door's lines, or ``Refused``: each dish on the menu, a whole quantity within the
    store's limit, each choice one of the dish's own, each group between its least and most picks (checked here
    whatever the register's *Item options* switch says), and the store's course word on every line."""
    if not isinstance(raw, list) or not raw:
        raise Refused("Your order is empty.")
    if len(raw) > most_lines:
        raise Refused(f"An order holds at most {most_lines} lines. Send the rest as a second order.")
    dishes = dishes_of(menu)
    out = []
    for ln in raw:
        if not isinstance(ln, dict):
            raise Refused("Your order could not be read. Open the menu again.")
        d = dishes.get(ln.get("item_code")) if isinstance(ln.get("item_code"), str) else None
        if d is None:
            raise Refused("Something in your order is no longer on the menu. Open the menu again.")
        qty = ln.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= most_qty:
            raise Refused(f"{d['name']}: order between 1 and {most_qty}.")
        picked = ln.get("options") or []
        if not isinstance(picked, list) or len(picked) > 20 or not all(isinstance(p, str) for p in picked):
            raise Refused(f"{d['name']}: your choices could not be read.")
        own = {c["code"]: g for g in d["groups"] for c in g["choices"]}
        if len(set(picked)) != len(picked):
            raise Refused(f"{d['name']}: pick each choice once.")
        for code in picked:
            if code not in own:
                raise Refused(f"{d['name']}: a choice is no longer offered. Open the menu again.")
        for g in d["groups"]:
            n = sum(1 for code in picked if own[code] is g)
            if n < g["min"]:
                raise Refused(f"{d['name']}: choose {g['min']} from {g['label']}.")
            if g["max"] and n > g["max"]:
                raise Refused(f"{d['name']}: choose up to {g['max']} from {g['label']}.")
        line = {"item_code": d["code"], "qty": qty, "course": course}
        if picked:
            line["options"] = [{"item_code": code, "option_group": own[code]["group"]} for code in picked]
        note = clean_note(ln.get("note"))
        if note:
            line["note"] = note
        out.append(line)
    return out


def page_key(v) -> str | None:
    """The page's own key for one press of *Send order* (a fresh random value), or None."""
    return v if isinstance(v, str) and _KEY.fullmatch(v) else None


def door_key(key: str, step: str) -> str:
    """The door's key for one step of one order (``open`` or ``add``), made from the page's key: a retry of the order
    sends the same keys, a new order new ones. Shaped as a UUID, from 122 bits of a hash of a random value."""
    h = hashlib.sha256(f"gor1|{step}|{key}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def kiosk_code(key: str, secret: bytes) -> str:
    """The kiosk order's five-character code, made from the page's key (the same on a retry) with the retailer's secret,
    so a guest cannot choose a key that gives another guest's code (31^5: two open tabs share one about once in
    tens of millions of orders)."""
    n = int.from_bytes(hmac.new(secret, f"gor1|kiosk|{key}".encode(), hashlib.sha256).digest()[:8], "big")
    out = ""
    for _ in range(KIOSK_LEN):
        n, r = divmod(n, len(KIOSK_LETTERS))
        out += KIOSK_LETTERS[r]
    return out


def made_for(code: dict) -> str:
    """What a code was made for: its kind, store and table (or kiosk name). Written by *Make code*; a guest's call
    refuses a code whose record no longer matches, so a card printed for Table 12 never orders for another table."""
    where = code.get("place") if code.get("kind") == KIND_TABLE else (code.get("kiosk_name") or "").strip()
    return "|".join(str(v or "") for v in (code.get("kind"), code.get("store"), where))[:140]


def place_of(floor: dict, place: str) -> dict | None:
    """The place on the store's floor, or None when it is not an active place of an active section."""
    for p in (floor or {}).get("places") or []:
        if isinstance(p, dict) and p.get("place") == place:
            return p
    return None
