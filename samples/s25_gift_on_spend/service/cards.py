"""S25 — issue, release and void the shop's own gift cards. The rules are ``gcs.py``'s; this module only talks to the shop.

A card's life, every step a record in the shop:

1. **Issuing** — the app's ``Card`` record is written FIRST, named by the sale and the card's position (``gcs.card_key``),
   holding the card's number, value, item, threshold and hold. The shop refuses a second record with that name, so a
   replayed event or a crash never earns a second card.
2. **Held** — the engine's own **Gift Card** is made with that number at a balance of **0**: the till and the engine
   refuse a card with nothing on it, so the customer cannot spend it during the hold.
3. **Released** — after the hold, the sale is READ AGAIN (cancelled? returned below what earned this card?) and only then
   does the engine's own **Gift Card Balance** (``GC-BAL-…``, submitted) set the card to its value. ⚠ A Gift Card
   Balance SETS the balance; it does not add. So a card is released only when it has NO submitted Gift Card Balance yet
   and its balance is exactly 0; anything else is ``Review`` (the shop decides), never a second balance.
4. **Voided** — the sale was cancelled, or its returns took its spend below what earned the card: a held card is simply
   never released; a released card still at its full value and never used at the till (the engine's own *redeemed*
   test) is set to 0 by a Gift Card Balance. A card already used is ``Review``: nothing is taken from it.

Every decision reads the sale's NET spend (its spend less every return booked against it), whichever event arrives
first, so a sale handled after its return (a failed event retried) earns only what the net still earns.

Handlers take ``t`` (the shop: ``get``, ``list``, ``insert``, ``update``, ``method``), ``s`` (``gcs.Settings``) and
``now`` (an aware UTC datetime, so the tests own the clock).
"""

from __future__ import annotations

import datetime as _dt
import secrets

import gcs
from gcs import D
from shop import Duplicate, ShopError

CARD, SETTINGS = "PP GCS Card", "PP GCS Settings"      # use_prefix() renames them for the library's app
GIFT_CARD, BALANCE, SALE = "Gift Card", "Gift Card Balance", "POS Invoice"
CARD_STATUS = "ivendnext_pos.api.pos_invoice.get_gift_card_status"   # the till's own: balance, expired, redeemed
CARD_FIELDS = ["name", "sale", "position", "status", "card_number", "card_value", "card_item", "threshold", "gift_card",
               "creation", "release_after_utc"]


def use_prefix(prefix: str):
    global CARD, SETTINGS
    CARD, SETTINGS = f"{prefix} Card", f"{prefix} Settings"


def load_settings(t) -> gcs.Settings:
    return gcs.Settings(t.get(SETTINGS, "Default"))


def utc(now: _dt.datetime) -> str:
    return now.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_plus(creation: str, hours: int) -> str:
    """The shop's own clock: the Card record's ``creation`` (the shop's local time) plus the hold."""
    base = _dt.datetime.fromisoformat(str(creation).split(".")[0])
    return (base + _dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def new_number(t) -> str:
    """A 16-digit card number no gift card in the shop holds yet (the engine's own numbers are 16 digits too). From
    ``secrets``: a gift card number is a bearer credential."""
    for _ in range(8):
        n = str(10 ** 15 + secrets.randbelow(9 * 10 ** 15))
        if t.get(GIFT_CARD, n) is None:
            return n
    raise ShopError(0, "no free card number after 8 tries")


def _set(t, rec: dict, **fields) -> dict:
    t.update(CARD, rec["name"], fields)
    return dict(rec, **fields)


def _review(t, rec: dict, why: str) -> str:
    _set(t, rec, status="Review", note=why[:300])
    return "Review"


def _balances(t, number: str) -> list[dict]:
    return t.list(BALANCE, [["gift_card", "=", number], ["docstatus", "=", 1]], fields=["name", "balance"])


def net_spend(t, sale: dict):
    """The sale's spend less every return booked against it."""
    rets = t.list(SALE, [["return_against", "=", sale["name"]], ["is_return", "=", 1], ["docstatus", "=", 1]],
                  fields=["name"])
    return gcs.spend(sale) - sum((gcs.return_spend(t.get(SALE, r["name"]) or {}) for r in rets), D(0))


# ---------- 1-2 · issue ----------------------------------------------------------------------------------------------

def on_sale(t, s: gcs.Settings, name: str, now: _dt.datetime) -> dict:
    """``sale.booked``: the cards this sale's net spend earns, each issued held."""
    why = s.why_not_ready()
    if why:
        return {"result": why}
    sale = t.get(SALE, name)
    if not sale:
        return {"result": "the sale is not in the shop"}
    group = sale.get("customer_group")
    if group is None and sale.get("customer"):
        group = (t.get("Customer", sale["customer"]) or {}).get("customer_group")
    why = gcs.why_no_card(sale, s, group) or gcs.why_not_item(t.get("Item", s.card_item), s)
    if why:
        return {"result": why}
    n = gcs.cards_for(net_spend(t, sale), s)
    return {"result": f"{n} card(s)", "cards": [issue_one(t, s, sale, pos, now) for pos in range(1, n + 1)]}


def issue_one(t, s: gcs.Settings, sale: dict, pos: int, now: _dt.datetime) -> str:
    key = gcs.card_key(sale["name"], pos)
    rec = t.get(CARD, key)
    if rec is None:
        try:
            t.insert({"doctype": CARD, "card_key": key, "sale": sale["name"], "customer": sale.get("customer"),
                      "position": pos, "card_number": new_number(t), "card_value": str(s.card_value),
                      "currency": s.currency, "card_item": s.card_item, "threshold": str(s.threshold),
                      "hold_hours": s.hold_hours, "status": "Issuing"})
        except Duplicate:
            pass                                    # another pass wrote it a moment ago: the same card
        rec = t.get(CARD, key)
    if rec.get("status") != "Issuing":
        return rec.get("status")
    number, value = rec["card_number"], D(rec["card_value"])
    gc = t.get(GIFT_CARD, number)
    if gc is None:
        try:
            t.insert({"doctype": GIFT_CARD, "serial_number": number, "item_code": rec["card_item"],
                      "total": str(value), "balance": "0", "first_name": sale.get("customer_name") or sale.get("customer")})
        except Duplicate:
            pass
        gc = t.get(GIFT_CARD, number)
    if not gc or D(gc.get("balance")) != 0 or D(gc.get("total")) != value or _balances(t, number):
        return _review(t, rec, "the gift card with this number is not the one this app issued at 0")
    hold = int(rec.get("hold_hours") if rec.get("hold_hours") is not None else s.hold_hours)
    _set(t, rec, status="Held", gift_card=number, release_after=_local_plus(rec["creation"], hold),
         release_after_utc=utc(now + _dt.timedelta(hours=hold)))
    return "Held"


# ---------- 3 · release ----------------------------------------------------------------------------------------------

def release_due(t, now: _dt.datetime, tick=lambda: None) -> list[tuple[str, str]]:
    """Every held card whose hold has passed (by this service's clock, in UTC), released once — or voided, when its sale
    has since been cancelled or returned below what earned it. ``tick`` is called per card (the worker's progress)."""
    due = t.list(CARD, [["status", "=", "Held"], ["release_after_utc", "<=", utc(now)]], fields=CARD_FIELDS,
                 order_by="release_after_utc asc")
    out = []
    for r in due:
        tick()
        out.append((r["name"], release_one(t, r)))
    return out


def _still_earned(t, rec: dict) -> str:
    """``""`` when the card's sale still earns it; else why not (read now, never from the events)."""
    sale = t.get(SALE, rec["sale"]) or {}
    if int(sale.get("docstatus") or 0) != 1:
        return "the sale was cancelled"
    issued = len(t.list(CARD, [["sale", "=", rec["sale"]]], fields=["name"]))
    if int(rec.get("position") or 0) > gcs.kept(net_spend(t, sale), rec.get("threshold"), issued):
        return "a return took the sale's spend below what earned this card"
    return ""


def release_one(t, rec: dict) -> str:
    gone = _still_earned(t, rec)
    if gone:
        return void_one(t, rec, gone)
    number, value = rec.get("gift_card") or rec["card_number"], D(rec["card_value"])
    gc = t.get(GIFT_CARD, number)
    if not gc:
        return _review(t, rec, "the gift card is no longer in the shop")
    done = _balances(t, number)
    if done:                                        # a release that landed before its record was updated
        mine = [b for b in done if D(b.get("balance")) == value]
        if len(done) == 1 and mine:
            _set(t, rec, status="Released", balance_entry=mine[0]["name"])
            return "Released"
        return _review(t, rec, "the gift card already has a balance entry this app did not expect")
    if D(gc.get("balance")) != 0:
        return _review(t, rec, "the gift card's balance was changed in the shop during the hold")
    if int(gc.get("expired") or 0):
        return _review(t, rec, "the gift card expired during the hold")
    entry = t.insert({"doctype": BALANCE, "gift_card": number, "balance": str(value), "docstatus": 1})
    _set(t, rec, status="Released", balance_entry=entry)
    return "Released"


# ---------- 4 · void ----------------------------------------------------------------------------------------------

def void_one(t, rec: dict, why: str) -> str:
    status, number, value = rec.get("status"), rec.get("gift_card") or rec.get("card_number"), D(rec.get("card_value"))
    gc = t.get(GIFT_CARD, number) if number else None
    done = _balances(t, number) if gc else []
    if status in ("Issuing", "Held") and not done:
        if gc and D(gc.get("balance")) != 0:
            return _review(t, rec, f"{why}; the gift card's balance was changed in the shop")
        _set(t, rec, status="Voided", note=f"{why}; never released"[:300])
        return "Voided"
    if not gc:
        return _review(t, rec, f"{why}; the gift card is no longer in the shop")
    used = (t.method(CARD_STATUS, {"gift_card_no": number}) or {}).get("redeemed")
    zeroed = [b for b in done if D(b.get("balance")) == 0]
    if zeroed and not used and D(gc.get("balance")) == 0:   # this void landed before its record was updated (a
        # restart): never used, so the zero entry can only have removed unspent value. A card used and then zeroed by
        # staff is Review below, never taken for this app's own void.
        _set(t, rec, status="Voided", void_entry=zeroed[0]["name"], note=f"{why}; set to 0"[:300])
        return "Voided"
    if used or D(gc.get("balance")) != value:
        return _review(t, rec, f"{why}; already used at the till (balance {gc.get('balance')} of {rec.get('card_value')})")
    entry = t.insert({"doctype": BALANCE, "gift_card": number, "balance": "0", "docstatus": 1})
    _set(t, rec, status="Voided", void_entry=entry, note=f"{why}; set to 0"[:300])
    return "Voided"


def _cards_of(t, sale: str) -> list[dict]:
    rows = t.list(CARD, [["sale", "=", sale]], fields=CARD_FIELDS)
    return sorted(rows, key=lambda r: -int(r.get("position") or 0))       # the last card first


def on_cancel(t, name: str) -> dict:
    """``sale.cancelled``: every card the sale earned. A cancelled RETURN gives no card back (a voided card stays so)."""
    doc = t.get(SALE, name) or {}
    if int(doc.get("is_return") or 0):
        return {"result": "a cancelled return: no card is given back"}
    out = [(r["name"], void_one(t, r, "the sale was cancelled")) for r in _cards_of(t, name)
           if r.get("status") not in ("Voided", "Review")]
    return {"result": f"{len(out)} card(s)", "cards": out}


def on_return(t, name: str) -> dict:
    """``return.booked``: the cards the sale no longer earns, once all its returns are taken off its spend (the threshold
    the cards were earned under, written on each card)."""
    orig = (t.get(SALE, name) or {}).get("return_against")
    cards = _cards_of(t, orig) if orig else []
    if not cards:
        return {"result": "no card on that sale"}
    keep = gcs.kept(net_spend(t, t.get(SALE, orig) or {"name": orig}), cards[-1].get("threshold"), len(cards))
    out = [(r["name"], void_one(t, r, "a return took the sale's spend below what earned this card"))
           for r in cards if int(r.get("position") or 0) > keep and r.get("status") not in ("Voided", "Review")]
    return {"result": f"keeps {keep} of {len(cards)}", "cards": out}
