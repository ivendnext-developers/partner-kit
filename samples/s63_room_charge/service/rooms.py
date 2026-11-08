"""S63 — the rules: what the check answers at Pay, and what one sale owes the folio. Standard library only, no calls: the
service (``app.py``) and the worker (``worker.py``) do the talking, so every rule here runs in a test with no shop.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

MODE = "Room Charge"             # the tile's name when a store's row names none
ROOM, GUEST, FOLIO, TIP = "Room", "Guest", "Folio", "Tip"          # the sale details the manifest declares
DETAILS_TABLE = "custom_pos_invoice_sale_attribute"                # a sale's details, as POS Invoice holds them
_NOT_PLAIN = re.compile(r"[<>\x00-\x1f\x7f  ‪-‮⁦-⁩-]")
_BOUND = re.compile(r"^(\S+) \((.*)\)$", re.S)


def plain(text, limit: int = 140) -> str:
    """Text the till accepts: no markup or control characters, at most ``limit`` characters."""
    return _NOT_PLAIN.sub(" ", str(text or "")).strip()[:limit].strip()


def settings_of(doc: dict | None) -> dict:
    """{store: its row}, from the app's one settings record."""
    out = {}
    for row in (doc or {}).get("stores") or []:
        if row.get("store"):
            out[row["store"]] = {"store": row["store"], "system": row.get("hotel_system") or "",
                                 "connection": row.get("connection") or "", "charge_code": (row.get("charge_code") or "").strip(),
                                 "tip_code": (row.get("tip_code") or "").strip(),
                                 "mode": (row.get("mode_of_payment") or "").strip() or MODE}
    return out


def details_of_ctx(ctx: dict) -> dict:
    return {str(r.get("name")): str(r.get("value") or "").strip() for r in ctx.get("sale_attributes") or []}


def details_of_sale(inv: dict) -> dict:
    return {str(r.get("sale_attribute")): str(r.get("attribute_value") or "").strip() for r in inv.get(DETAILS_TABLE) or []}


def tip_of(text: str, decimals: int = 2) -> Decimal | None:
    """The tip typed on the sale: 0 when none, None when it is not an amount. A separator may only start the currency's own
    decimals, so "50,000" is never read as fifty where a currency has two."""
    if not text:
        return Decimal(0)
    whole, sep, frac = text.replace(",", ".").partition(".")
    if not whole.isascii() or not whole.isdigit() or (sep and not (frac.isascii() and frac.isdigit() and len(frac) <= decimals)):
        return None
    try:
        return Decimal(f"{whole}.{frac or 0}")
    except InvalidOperation:
        return None


# ---- the Folio on the sale ------------------------------------------------------------------------------------------
# The Folio detail carries the room and guest it was found for, so a room corrected after the check is looked up again
# and never posted to the first room's guest: "R-1001 (412 Smith)".

def folio_text(folio: str, room: str, guest: str) -> str:
    return plain(f"{folio} ({room} {guest})")


def folio_id(text: str) -> str:
    m = _BOUND.match(text or "")
    return m.group(1) if m else ""


def folio_fits(text: str, room: str, guest: str) -> bool:
    fid = folio_id(text)
    return bool(fid) and text == folio_text(fid, room, guest)


# ---- the check at Pay -----------------------------------------------------------------------------------------------

def _dim(mode: str, reason: str) -> dict:
    return {"verdict": "allow", "exclude_tenders": [mode], "reason": plain(reason)}


def check_return(ctx: dict, mode: str) -> dict:
    """A room charge goes back to the room, and a split's card gets its share: every other offered tender is dimmed. Store
    credit is dimmed with them, which is what refuses an exchange of such a sale."""
    paid_by = set((ctx.get("return_of") or {}).get("paid_by") or [])
    if mode not in paid_by:
        return {"verdict": "allow"}
    off = [t for t in ctx.get("offered_tenders") or [] if t not in paid_by][:20]
    if not off:
        return {"verdict": "allow"}
    return {"verdict": "allow", "exclude_tenders": off, "reason": "This went on a room. Return it and ring it again."}


def check_sale(ctx: dict, mode: str) -> tuple[dict | None, str, str]:
    """(the answer, "", "") when the details settle it, or (None, room, guest) when the hotel system must be asked."""
    if mode not in (ctx.get("offered_tenders") or []):
        return {"verdict": "allow"}, "", ""
    d = details_of_ctx(ctx)
    room, guest = d.get(ROOM, ""), d.get(GUEST, "")
    if not room:
        return _dim(mode, "Type the room and the guest's surname on Sale details."), "", ""
    if not guest:
        return _dim(mode, f"Type the guest's surname for room {room} on Sale details."), "", ""
    if tip_of(d.get(TIP, ""), int(ctx.get("currency_exponent") or 0)) is None:
        return _dim(mode, "The tip on Sale details is not an amount."), "", ""
    if folio_fits(d.get(FOLIO, ""), room, guest):       # asked again on the filled sale: the same answer, no second call
        return {"verdict": "allow", "fill": {FOLIO: d[FOLIO]}}, "", ""
    return None, room, guest


def found(folio: str, room: str, guest: str) -> dict:
    return {"verdict": "allow", "fill": {FOLIO: folio_text(folio, room, guest)}}


def not_confirmed(mode: str, reason: str) -> dict:
    return _dim(mode, reason)


def hotel_down(room: str) -> dict:
    return {"verdict": "ask", "question": plain(f"The hotel system isn't answering. Charge room {room} anyway?")}


# ---- what one sale owes the folio -----------------------------------------------------------------------------------

def share_of(inv: dict, mode: str) -> float:
    """The sale's own Room Charge rows: on a split, only this share reaches the folio. A return's rows are negative."""
    return round(sum(float(p.get("amount") or 0) for p in inv.get("payments") or [] if p.get("mode_of_payment") == mode), 6)


def work_of(inv: dict, s: dict) -> dict | None:
    """The row a Room Charge sale or return writes, or None when it has no Room Charge row. A return posts no tip: the tip
    stays posted, as the till's own tips do."""
    amount = share_of(inv, s["mode"])
    if not amount:
        return None
    d, is_return = details_of_sale(inv), bool(inv.get("is_return"))
    room, guest = d.get(ROOM, ""), d.get(GUEST, "")
    tip = 0.0 if is_return else float(tip_of(d.get(TIP, ""), 3) or 0)
    fits = folio_fits(d.get(FOLIO, ""), room, guest)
    return {"sale": inv["name"], "status": "Sending", "day": inv.get("posting_date"), "store": s["store"], "room": room,
            "guest": guest, "folio": folio_id(d[FOLIO]) if fits else "", "currency": inv.get("currency"), "amount": amount,
            "tip": tip, "return_of": inv.get("return_against") if is_return else None}


def lines_of(row: dict, s: dict) -> list[dict]:
    """The folio's lines: the charge, and the tip when the store names a tip code."""
    lines = [{"kind": "charge", "code": s["charge_code"], "amount": float(row["amount"]), "label": "Restaurant charge"}]
    if float(row.get("tip") or 0) and s["tip_code"]:
        lines.append({"kind": "tip", "code": s["tip_code"], "amount": float(row["tip"]), "label": "Tip"})
    return lines


def return_gate(original: dict | None) -> tuple[str, str]:
    """What a return may do while its sale's own post stands as it does: ("go", "") · ("Waiting", why) · ("Refused", why)."""
    status = (original or {}).get("status")
    if status in ("Waiting", "Sending"):
        return "Waiting", "Waiting for its sale to reach the folio first."
    if status == "Refused":
        return "Refused", "Its sale is on the auditor's list. If it is on the folio, take this amount off there."
    return "go", ""
