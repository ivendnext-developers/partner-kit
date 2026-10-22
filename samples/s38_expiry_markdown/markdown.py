"""S38 — *Mark down*: the pure core (no framework, no network), shared by the service and its tests.

The shop's Desk button on the Batch list (and a lot's form) sends one signed POST per press (the Desk action extension
point, ``desk_action/1``):

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang",
                                           "records": [{"doctype": "Batch", "name", "fields": {"name", "item", "expiry_date"}}, …],
                                           "inputs": {}, "idempotency_key"}}

``verify`` checks the signature the shop puts on every call; ``lots_of`` takes the press's lots; ``groups_of`` and
``steps_for`` read the shop's markdown steps on its item group tree (the nearest group with a step wins); ``pct_for``
picks the step a lot has reached by its days left; ``plan`` decides each lot's writes to the shop's own Item Price rows
(a lot's own price, valid until its expiry date, noted as the app's own); ``answer`` builds the reply in the extension
point's closed vocabulary. ⛔ The answer never writes anything: the service writes the prices itself, with its own API
key and its own rights, BEFORE it answers.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time
from decimal import ROUND_FLOOR, Decimal

PREFIX = "PP EXM"
DAYS, PCT = ("pp_exm_days_1", "pp_exm_days_2"), ("pp_exm_pct_1", "pp_exm_pct_2")
SKEW_S = 300             # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
MOST_LOTS = 100          # the Desk action's own limit for a list press


def use_prefix(prefix: str):
    """The fields and the note under another prefix: ``ivendnext_exm_days_1`` and *IVENDNEXT EXM: …* for the library's app."""
    global PREFIX, DAYS, PCT
    PREFIX = prefix
    p = prefix.lower().replace(" ", "_")
    DAYS, PCT = (f"{p}_days_1", f"{p}_days_2"), (f"{p}_pct_1", f"{p}_pct_2")


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


def lots_of(body: dict) -> list[str]:
    """The lots the press names, in its order, or ``ValueError`` — checked before anything is read or written."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    recs = ctx["records"]
    if not 1 <= len(recs) <= MOST_LOTS:
        raise ValueError("one to 100 lots a press")
    out = []
    for rec in recs:
        if not isinstance(rec, dict) or rec.get("doctype") != "Batch" or not isinstance(rec.get("name"), str) \
                or not rec["name"]:
            raise ValueError("not a lot")
        if rec["name"] not in out:
            out.append(rec["name"])
    return out


def _whole(v) -> int | None:
    """A whole number the shop typed, or None (blank, 0 counts as a value only for days)."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def steps_of(row: dict) -> list[tuple[int, float]]:
    """An item group's own steps: ``[(days before expiry, percent off)]``. A step needs both: days from 0 and a percent
    above 0 and below 100. A half-filled or out-of-range step is no step."""
    out = []
    for d, p in zip(DAYS, PCT):
        days, pct = _whole(row.get(d)), row.get(p)
        if days is not None and days >= 0 and isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 < pct < 100:
            out.append((days, float(pct)))
    return out


def groups_of(records) -> dict:
    """The shop's item groups: ``{name: (lft, rgt, steps)}``. Anything that is not a list of records with whole ``lft``
    and ``rgt`` is read as no groups (no lot is marked down)."""
    if not isinstance(records, list):
        return {}
    return {r["name"]: (r["lft"], r["rgt"], steps_of(r)) for r in records
            if isinstance(r, dict) and isinstance(r.get("name"), str) and _whole(r.get("lft")) is not None
            and _whole(r.get("rgt")) is not None}


def steps_for(item_group: str, groups: dict) -> list[tuple[int, float]]:
    """The steps of ``item_group`` or of the nearest group above it that has any: the tree nests by lft/rgt, so the
    largest lft among the groups holding it is the nearest."""
    g = groups.get(item_group)
    if not g:
        return []
    above = [(lft, steps) for lft, rgt, steps in groups.values() if steps and lft <= g[0] and g[1] <= rgt]
    return max(above)[1] if above else []


def pct_for(steps: list[tuple[int, float]], days_left: int) -> float | None:
    """The percent off for a lot with ``days_left`` before its expiry date: the step with the fewest days that the lot has
    reached (5 days 25% and 2 days 50%: 3 days left is 25%, 1 day left is 50%). None before the first step, and for a lot
    past its date."""
    if days_left < 0:
        return None
    reached = [(days, pct) for days, pct in steps if days_left <= days]
    return min(reached)[1] if reached else None


def today_at(hours: float, now: float | None = None) -> datetime.date:
    """The shop's own date, ``hours`` from UTC (blank: UTC)."""
    t = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t + datetime.timedelta(hours=hours or 0)).date()


def date_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None


# the framework's own number formats and their digits (``get_number_format_info``): a currency's digits are its number
# format's, never its fraction units (the yen counts 100 sen and shows none, the rial none and no units at all)
DIGITS = {"#,###.##": 2, "#.###,##": 2, "# ###.##": 2, "# ###,##": 2, "#'###.##": 2, "#, ###.##": 2, "#,##,###.##": 2,
          "#,###.###": 3, "#.###": 0, "#,###": 0, "#.########": 8}


def exponent_of(number_format) -> int:
    """A currency's digits from its number format, as the shop shows it (unknown or blank: 2, the framework's). The shop
    rounds a line to its currency precision setting, which can be fewer digits: the README says so."""
    return DIGITS.get(number_format, 2) if isinstance(number_format, str) else 2


def marked(rate, pct: float, exponent: int) -> float:
    """The item's price less ``pct`` percent, rounded DOWN to the currency's smallest unit, so the customer never pays more
    than the step promises."""
    grain = Decimal(1).scaleb(-exponent)
    v = (Decimal(str(rate)) * (Decimal(100) - Decimal(str(pct))) / Decimal(100)).quantize(grain, rounding=ROUND_FLOOR)
    return float(v)


def note_for(pct: float) -> str:
    p = int(pct) if float(pct).is_integer() else pct
    return f"{PREFIX}: {p}% off until it expires"


def own(row: dict) -> bool:
    """The app's own row: its note starts with the prefix. A price the shop typed for a lot is never the app's."""
    return isinstance(row.get("note"), str) and row["note"].startswith(PREFIX + ": ")


def _blank(v) -> bool:
    return v in (None, "")


def _key(row: dict) -> tuple:
    return row.get("uom") or "", row.get("packing_unit") or 0


def base_rows(rows: list[dict], item: str, today: datetime.date) -> dict:
    """The item's own prices on the list, valid today, for no particular customer or supplier: ``{(uom, packing unit):
    row}``, the latest ``valid_from`` of each."""
    out = {}
    for r in rows:
        if r.get("item_code") != item or not _blank(r.get("batch_no")) or not _blank(r.get("customer")) \
                or not _blank(r.get("supplier")) or not isinstance(r.get("price_list_rate"), (int, float)):
            continue
        frm, upto = date_of(r.get("valid_from")), date_of(r.get("valid_upto"))
        if (frm and frm > today) or (upto and upto < today):
            continue
        k = _key(r)
        if k not in out or (date_of(out[k].get("valid_from")) or datetime.date.min) < (frm or datetime.date.min):
            out[k] = r
    return out


def plan(lot: dict, item: dict | None, rows: list[dict], groups: dict, today: datetime.date, price_list: str,
         exponent: int) -> tuple[str, list]:
    """(the lot's outcome, the writes): ``("create", body)``, ``("update", row, body)`` or ``("delete", row)``.

    Outcomes: ``marked`` (written) · ``already`` (at its step) · ``removed`` (the app's price taken off: past its date,
    no stock, or no longer in a step) · ``not_due`` · ``own_price`` (a price the shop typed: left as it is) · ``no_price``
    (the item has no price on the list) · ``not_tracked`` (gone, or its item is not one the shop prices by lot)."""
    name = lot.get("name")
    lot_rows = [r for r in rows if r.get("batch_no") == name]
    if any(not own(r) for r in lot_rows):
        return "own_price", []
    mine = [r for r in lot_rows if own(r)]
    expiry = date_of(lot.get("expiry_date"))
    if not item or not expiry or item.get("name") != lot.get("item"):
        return ("removed" if mine else "not_tracked"), [("delete", r) for r in mine]
    qty = lot.get("batch_qty")
    pct = pct_for(steps_for(item.get("item_group") or "", groups), (expiry - today).days)
    if pct is None or lot.get("disabled") or (isinstance(qty, (int, float)) and qty <= 0):
        return ("removed" if mine else "not_due"), [("delete", r) for r in mine]
    base = base_rows(rows, lot["item"], today)
    if not base:
        return ("removed" if mine else "no_price"), [("delete", r) for r in mine]
    writes, by_key = [], {}
    for r in mine:
        if _key(r) in by_key or _key(r) not in base:     # a second row for one unit, or a unit no longer priced: off
            writes.append(("delete", r))
        else:
            by_key[_key(r)] = r
    upto, note = expiry.isoformat(), note_for(pct)
    for k, b in sorted(base.items()):
        want = {"price_list_rate": marked(b["price_list_rate"], pct, exponent), "valid_upto": upto, "note": note}
        r = by_key.get(k)
        if r is None:
            writes.append(("create", dict(want, item_code=lot["item"], price_list=price_list, uom=k[0],
                                          packing_unit=k[1], batch_no=name, valid_from=today.isoformat())))
            continue
        # the shop's price lookup takes the newest valid_from first and the lot only after it (``get_item_price``), so a
        # lot's row older than the item's own row is never read: move it to today with the new price
        older = (date_of(r.get("valid_from")) or datetime.date.min) < (date_of(b.get("valid_from")) or datetime.date.min)
        if older or any(r.get(f) != v for f, v in want.items()):
            writes.append(("update", r, dict(want, valid_from=today.isoformat(), modified=r.get("modified"))))
    marked_now = any(w[0] in ("create", "update") for w in writes)
    return ("marked" if marked_now else "already"), writes


def _fit(text: str, most: int = 280) -> str:
    """The extension point's limit on a message's body (280): cut, never refused."""
    return text if len(text) <= most else text[: most - 1] + "…"


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


WORDS = [("marked", "Marked down {}.", "lot", "lots"), ("already", "{} already marked down.", "lot", "lots"),
         ("removed", "Took the markdown off {}.", "lot", "lots"), ("not_due", "{} not yet due.", "lot", "lots"),
         ("own_price", "{} with a price of the shop's own, left as it is.", "lot", "lots"),
         ("no_price", "{} whose item has no price on the list.", "lot", "lots"),
         ("not_tracked", "{} not found.", "lot", "lots"), ("changed", "{} changed meanwhile: press again.", "lot", "lots"),
         ("refused", "{} the shop would not save.", "lot", "lots")]


def answer(outcomes: dict, done: int, total: int, swept: int = 0) -> dict:
    """The reply once the press's writes are made: a count per outcome, the lots left for another press, and the expired
    markdowns removed. ``refresh`` reloads the list or the lot."""
    parts = [w.format(_n(outcomes[k], one, many)) for k, w, one, many in WORDS if outcomes.get(k)]
    if done < total:
        parts.insert(0, f"Did {done} of {total} lots. Press Mark down again for the rest.")
    if swept:
        parts.append(f"Removed {_n(swept, 'expired markdown', 'expired markdowns')}.")
    warn = done < total or outcomes.get("changed") or outcomes.get("refused") or outcomes.get("no_price")
    return {"refresh": True, "message": {"title": "Mark down", "body": _fit(" ".join(parts) or "Nothing to do."),
                                         "level": "warning" if warn else "success"}}
