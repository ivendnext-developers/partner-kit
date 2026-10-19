"""S24 — Price-checker kiosk: the pure core (no web code, no shop). Standard library only.

A kiosk is a screen on the shop floor. A customer scans an item; the service asks the shop two questions with the app's
own key (its barcode lookup and its line pricer, ``service/app.py``) and this file turns the shop's answers into what the
kiosk shows. Nothing here is a price of ours: the price and the unit are the shop's own figures, the store's price list
price for one unit. Offers are not shown: on iVendNext a selling offer is a promotion, which the engine works out on a
whole sale at the till (a selling Pricing Rule is refused by the engine), so the kiosk says offers are worked out there.

    kiosk_code(text)            the kiosk's code: the framework's random name of its Kiosk record, else None
    scan_text(text)             what was scanned, trimmed, else None
    kiosk_date(text, today)     the kiosk's own date (the shop's day), else the service's
    kiosk_of(record)            the Kiosk record as the pricer needs it; None when it is switched off or incomplete
    pricer_args(kiosk, hit, d)  the arguments for the shop's line pricer: one unit, the scanned unit, the store's list,
                                no price rule
    answer_of(details, kiosk)   what the kiosk shows
"""

from __future__ import annotations

import datetime
import re

CODE = re.compile(r"[0-9a-z]{10}")          # the framework's random name: 10 characters of base 32 hex, lower case
SCAN_MAX = 64
PUBLIC_FILE = re.compile(r"/files/[^\s\"'<>?#\\]+")   # a public file of the shop; a private one cannot show on a kiosk

TEXT = {
    "not_set_up": "This kiosk is not set up. Please ask a member of staff.",
    "not_found": "We could not find this item. Please ask a member of staff.",
    "no_price": "This item has no price here. Please ask a member of staff.",
    "not_on_sale": "This item is not on sale. Please ask a member of staff.",
    "unavailable": "Price checks are not available right now.",
    "busy": "Please wait a moment and scan again.",
    "bad_request": "Please scan the item again.",
}


def kiosk_code(value) -> str | None:
    s = value.strip().lower() if isinstance(value, str) else ""
    return s if CODE.fullmatch(s) else None


def scan_text(value) -> str | None:
    s = value.strip() if isinstance(value, str) else ""
    return s if 0 < len(s) <= SCAN_MAX and s.isprintable() else None


def kiosk_date(value, today: datetime.date) -> str:
    """The kiosk's own date, so a price valid from today starts on the shop's day, not the server's. Taken only when it
    is a real date within a day of the service's; anything else is the service's date."""
    try:
        d = datetime.date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        d = None
    return (d if d and abs((d - today).days) <= 1 else today).isoformat()


def kiosk_of(record: dict | None) -> dict | None:
    """The shop's Kiosk record, with what it fetched from its till profile. Off, or missing what the pricer needs: None."""
    if not isinstance(record, dict) or not int(record.get("enabled") or 0):
        return None
    k = {f: record.get(f) for f in ("pos_profile", "company", "selling_price_list", "currency", "customer", "warehouse")}
    if not all(isinstance(k[f], str) and k[f] for f in ("company", "selling_price_list", "currency")):
        return None
    return k


def pricer_args(kiosk: dict, hit: dict, date: str) -> dict:
    """One unit of the scanned item, in the scanned unit (a barcode's own unit), on the store's price list, for the
    store's walk-in customer (a price row for that customer first, as the till's lookup does), on the kiosk's date, with
    no price rule: the shop's line pricer finds the price row and converts the unit.
    ⛔ Never a ``rate``: given one, the shop's pricer may write a price row (``insert_item_price``)."""
    args = {"item_code": hit["item_code"], "qty": 1, "doctype": "Sales Invoice", "company": kiosk["company"],
            "selling_price_list": kiosk["selling_price_list"], "currency": kiosk["currency"], "conversion_rate": 1,
            "transaction_date": date, "ignore_pricing_rule": 1}
    for src, dst in (("uom", "uom"), ("batch_no", "batch_no")):
        if isinstance(hit.get(src), str) and hit[src]:
            args[dst] = hit[src]
    for f in ("customer", "warehouse"):
        if kiosk.get(f):
            args[f] = kiosk[f]
    return args


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def answer_of(details: dict, kiosk: dict) -> dict:
    """The kiosk's answer from the shop's priced line: the store's price for one unit, in the scanned unit."""
    price = round(_num(details.get("price_list_rate")), 6)
    if price <= 0:                  # no price on the store's list: never shown as free
        return {"status": "no_price", "message": TEXT["no_price"]}
    image = details.get("image") if isinstance(details.get("image"), str) else ""
    return {"status": "found", "item": str(details.get("item_name") or details.get("item_code") or "")[:140],
            "unit": str(details.get("uom") or "")[:40], "currency": kiosk["currency"], "price": price,
            "image": image if PUBLIC_FILE.fullmatch(image) else None}


def refusal(code: str) -> dict:
    return {"status": code, "message": TEXT[code]}
