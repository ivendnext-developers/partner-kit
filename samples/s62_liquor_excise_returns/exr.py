"""S62 — *Liquor excise returns*: the pure core (no framework, no network), shared by the service and its tests.

The retailer's Desk button on a draft return (the Desk action extension point, ``desk_action/1``) sends one signed POST
per press:

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang",
                                           "records": [{"doctype": "PP EXR Return", "name", "fields": {"name"}}],
                                           "inputs": {}, "idempotency_key"}}

``verify`` checks the signature the retailer's site puts on every call; ``return_of`` takes the press's one return;
``last_balances`` picks each item's balance from its last ledger row before a moment; ``work_out`` turns the items' duty
classes, litres and strength, their balances at both ends of the period and the store's ledger totals into the return's
lines; the ``message`` and ``summary_of`` functions build the reply in the extension point's closed vocabulary. ⛔ The
answer never writes anything: the service writes the return itself, with its own API key and its own rights, BEFORE it
answers.

**The lines.** For each duty class with stock or a movement, the twelve ``MOVEMENTS`` in order, each with its units (the
items' stock units), its volume (units times each item's litres, in the return's unit) and its pure alcohol (the volume
times each item's strength). *Opening stock* and *Closing stock* are each item's balance (``qty_after_transaction`` of its
last ledger row, ordered as the ledger orders them: ``posting_datetime``, then ``creation``) at the end of the day before
*From* and at the end of *To*. A stock count of an item without batches writes its ledger row with ``actual_qty`` 0 and
sets the balance directly, so no sum of ``actual_qty`` sees it: *Count difference* is what is left, the closing less the
opening and every other line: per item, then once more per class on the rounded lines, so each printed column adds up.
Out lines are positive figures; *Count difference* carries its sign.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PREFIX = "PP EXR"
CLASS, RETURN, LINE = "PP EXR Duty Class", "PP EXR Return", "PP EXR Return Line"
FIELD = "pp_exr_"                       # the prefix of the three fields on Item: <FIELD>class, <FIELD>ml, <FIELD>abv
DRAFT, FILED, DROPPED = "PP EXR Draft", "PP EXR Filed", "PP EXR Dropped"
LOCK_RULE = "PP EXR return locked once filed"
SKEW_S = 300                            # a request stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024
MOST_DAYS = 366                         # one return covers at most a year
GALLON = Decimal("3.785411784")         # litres in a US gallon
PLACES = Decimal("0.001")
UNITS = ("Litres", "US gallons")

OPENING, CLOSING, COUNT = "Opening stock", "Closing stock", "Count difference"
RECEIVED, TRANSFERRED_IN, RETURNED_IN, OTHER_IN = ("Received from suppliers", "Transferred in", "Returned by customers",
                                                   "Other in")
SOLD, TRANSFERRED_OUT, RETURNED_OUT, WRITTEN_OFF, OTHER_OUT = ("Sold", "Transferred out", "Returned to suppliers",
                                                               "Written off", "Other out")
INS = (RECEIVED, TRANSFERRED_IN, RETURNED_IN, OTHER_IN)
OUTS = (SOLD, TRANSFERRED_OUT, RETURNED_OUT, WRITTEN_OFF, OTHER_OUT)
MOVEMENTS = (OPENING, *INS, *OUTS, COUNT, CLOSING)
SALES = ("Sales Invoice", "POS Invoice", "Delivery Note")
PURCHASES = ("Purchase Receipt", "Purchase Invoice")
TRANSFER = ("Material Transfer", "Material Transfer for Manufacture")
SKIPPED = ("Stock Entry", "Stock Reconciliation")   # never in the voucher-type totals: entries by purpose, counts by difference


def use_prefix(prefix: str):
    """Every name under another prefix: *IVENDNEXT EXR Return* and the field ``ivendnext_exr_class`` for the library's app."""
    global PREFIX, CLASS, RETURN, LINE, FIELD, DRAFT, FILED, DROPPED, LOCK_RULE
    PREFIX = prefix
    CLASS, RETURN, LINE = f"{prefix} Duty Class", f"{prefix} Return", f"{prefix} Return Line"
    FIELD = prefix.lower().replace(" ", "_") + "_"
    DRAFT, FILED, DROPPED = f"{prefix} Draft", f"{prefix} Filed", f"{prefix} Dropped"
    LOCK_RULE = f"{prefix} return locked once filed"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the retailer's site's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit() and len(ts) <= 20) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def return_of(body: dict) -> tuple[str, str]:
    """(the return's name, the pressing user), or ``ValueError`` — checked before anything is read or written."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if len(ctx["records"]) != 1:
        raise ValueError("one return a press")
    rec = ctx["records"][0]
    if not isinstance(rec, dict) or rec.get("doctype") != RETURN or not isinstance(rec.get("name"), str) or not rec["name"]:
        raise ValueError("not a return")
    user = ctx.get("user")
    return rec["name"], user if isinstance(user, str) else ""


def number(v) -> Decimal | None:
    """A quantity or measure as the site sent it, exactly (never through a float's rounding), or None."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)) or v == "":
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def date_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def moment(v) -> datetime.datetime | None:
    """A ledger time as the site sends it (``2026-10-14 10:28:24`` or with microseconds), or None."""
    try:
        return datetime.datetime.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def period(start, end) -> tuple[str, str] | str:
    """The two ledger bounds of a period ``[start 00:00, the day after end 00:00)``, or the words that refuse it."""
    a, b = date_of(start), date_of(end)
    if not a or not b:
        return "Fill From and To, then save the return."
    if b < a:
        return "To is before From. Correct the period, save, and work it out again."
    if (b - a).days >= MOST_DAYS:
        return f"A return covers at most {MOST_DAYS} days. Make one return a period."
    return f"{a.isoformat()} 00:00:00", f"{(b + datetime.timedelta(days=1)).isoformat()} 00:00:00"


def item_of(row: dict) -> dict:
    """An item's class and measures: litres per stock unit (its millilitres, above 0, over 1,000) and strength (above 0,
    at most 100), or None. Millilitres keep a miniature exact (37.5 ml) at a site's usual three places."""
    ml, abv = number(row.get(FIELD + "ml")), number(row.get(FIELD + "abv"))
    litres = ml / 1000 if ml is not None and ml > 0 else None
    return {"item_name": row.get("item_name") or row.get("name"), "class": row.get(FIELD + "class") or "",
            "litres": litres,
            "abv": abv if abv is not None and 0 < abv <= 100 else None}


def last_balances(ats: list[dict], rows: list[dict]) -> dict[str, Decimal]:
    """Each item's balance from its last ledger row: ``ats`` names each item's last ``posting_datetime`` (``at``), ``rows``
    holds the rows at those times; of an item's rows at its time, the last by ``creation`` (then ``name``) wins."""
    last = {r.get("item_code"): moment(r.get("at")) for r in ats if r.get("item_code") and moment(r.get("at"))}
    best: dict[str, tuple] = {}
    for r in rows:
        item = r.get("item_code")
        if item not in last or moment(r.get("posting_datetime")) != last[item]:
            continue
        key = (str(r.get("creation") or ""), str(r.get("name") or ""))
        qty = number(r.get("qty_after_transaction"))
        if qty is not None and (item not in best or key > best[item][0]):
            best[item] = (key, qty)
    return {item: qty for item, (_, qty) in best.items()}


def kind_of(voucher_type: str, qty: Decimal, purpose: str | None = None) -> str:
    """The line a movement into (``qty`` above 0) or out of the store goes on."""
    inward = qty > 0
    if voucher_type in SALES:
        return RETURNED_IN if inward else SOLD
    if voucher_type in PURCHASES:
        return RECEIVED if inward else RETURNED_OUT
    if voucher_type == "Stock Entry":
        if purpose in TRANSFER:
            return TRANSFERRED_IN if inward else TRANSFERRED_OUT
        if purpose == "Material Receipt" and inward:
            return RECEIVED
        if purpose == "Material Issue" and not inward:
            return WRITTEN_OFF
    return OTHER_IN if inward else OTHER_OUT


def work_out(items: dict[str, dict], opening: dict, closing: dict, moves: list[dict], entries: list[dict],
             purposes: dict[str, str], unit: str, codes: dict[str, str] | None = None) -> tuple[list[dict], list[str], int]:
    """(the return's lines, the names of items that moved with no litres or no strength, the count of items counted).

    ``items``: every item with a class (``item_of``); ``opening`` / ``closing``: balances by item; ``moves``: the store's
    totals per item and voucher type (``qty`` signed; Stock Entry and Stock Reconciliation rows are not read here);
    ``entries``: the Stock Entries' net movement per item and entry (``voucher_no``); ``purposes``: each entry's purpose."""
    if unit not in UNITS:
        raise ValueError(f"the unit is one of {', '.join(UNITS)}")
    per: dict[str, dict[str, Decimal]] = {}

    def add(item, movement, qty):
        if item in items and qty:
            figures = per.setdefault(item, {})
            figures[movement] = figures.get(movement, Decimal(0)) + qty

    for item in items:
        add(item, OPENING, opening.get(item) or Decimal(0))
        add(item, CLOSING, closing.get(item) or Decimal(0))
    for r in moves:
        qty = number(r.get("qty"))
        if qty and r.get("voucher_type") not in SKIPPED:
            kind = kind_of(r.get("voucher_type") or "", qty)
            add(r.get("item_code"), kind, abs(qty))
    nets: dict[tuple[str, str], Decimal] = {}
    for r in entries:
        qty = number(r.get("qty"))
        if qty:
            key = (r.get("item_code"), r.get("voucher_no"))
            nets[key] = nets.get(key, Decimal(0)) + qty
    for (item, entry), qty in nets.items():
        if qty:
            add(item, kind_of("Stock Entry", qty, purposes.get(entry)), abs(qty))
    totals: dict[tuple[str, str], list[Decimal]] = {}
    missing = []
    for item, figures in per.items():
        it = items[item]
        if it["litres"] is None or it["abv"] is None:
            missing.append(it["item_name"] or item)
        litres = it["litres"] or Decimal(0)
        for movement, qty in figures.items():
            if not qty:
                continue
            vol = qty * litres
            t = totals.setdefault((it["class"], movement), [Decimal(0), Decimal(0), Decimal(0)])
            t[0] += qty
            t[1] += vol
            t[2] += vol * (it["abv"] or Decimal(0)) / 100
    scale = Decimal(1) if unit == "Litres" else 1 / GALLON
    lines = []
    for cls in sorted({c for c, _ in totals}):
        rows = {}
        for movement in MOVEMENTS:
            t = totals.get((cls, movement)) or [Decimal(0)] * 3
            rows[movement] = {"duty_class": cls, "return_code": (codes or {}).get(cls) or "", "movement": movement,
                              "units": _round(t[0]), "volume": _round(t[1] * scale), "pure_alcohol": _round(t[2] * scale)}
        for col in ("units", "volume", "pure_alcohol"):   # the count is what is left of the ROUNDED lines, so each
            rows[COUNT][col] = (rows[CLOSING][col] - rows[OPENING][col]   # column adds up as printed (Tier-S review)
                                - sum(rows[m][col] for m in INS) + sum(rows[m][col] for m in OUTS))
        lines += [rows[m] for m in MOVEMENTS]
    return lines, sorted(set(missing)), len(per)


def _round(v: Decimal) -> Decimal:
    """Three places, half away from zero, once per line (never per item)."""
    return v.quantize(PLACES, rounding=ROUND_HALF_UP)


def as_written(lines: list[dict]) -> list[dict]:
    """The lines as the record API takes them (numbers as floats: each is exact to the 3 places it shows)."""
    return [{k: float(v) if isinstance(v, Decimal) else v for k, v in ln.items()} for ln in lines]


def _sum(lines: list[dict], movement: str, field: str) -> Decimal:
    return sum((ln[field] for ln in lines if ln["movement"] == movement), Decimal(0))


def _fit(text: str, most: int = 280) -> str:
    return text if len(text) <= most else text[: most - 1] + "…"


def _n(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def message(body: str, level: str = "success", refresh: bool = False, title: str = "Liquor excise returns") -> dict:
    out = {"message": {"title": title, "body": _fit(body), "level": level}}
    if refresh:
        out["refresh"] = True
    return out


def summary_of(lines: list[dict], missing: list[str], counted: int, unit: str) -> str:
    """The words written on the return and said to the user after *Work out the return*."""
    if not lines:
        return ("Nothing to return: no item with a duty class had stock in this store or moved in this period. "
                "Check the store, the period, and the duty class on your liquor items.")
    u = "litres" if unit == "Litres" else "US gallons"
    classes = len({ln["duty_class"] for ln in lines})
    body = (f"{_n(classes, 'duty class', 'duty classes')}, {_n(counted, 'item', 'items')}. "
            f"Sold {_sum(lines, SOLD, 'volume'):,.3f} {u} ({_sum(lines, SOLD, 'pure_alcohol'):,.3f} {u} of pure alcohol); "
            f"closing stock {_sum(lines, CLOSING, 'volume'):,.3f} {u}.")
    if _sum(lines, COUNT, "units"):          # units are exact: a volume left over by rounding alone is no count
        body += f" Stock counts changed {_sum(lines, COUNT, 'volume'):+,.3f} {u}."
    if missing:
        names = ", ".join(missing[:3]) + (f" and {len(missing) - 3:,} more" if len(missing) > 3 else "")
        body += (f" {_n(len(missing), 'item has', 'items have')} no litres or no strength, so "
                 f"{'its' if len(missing) == 1 else 'their'} volume or pure alcohol is left out (units counted): {names}.")
    return _fit(body, 1000)
