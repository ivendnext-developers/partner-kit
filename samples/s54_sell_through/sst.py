"""S54 — *Sell-through by size and colour*: the pure core (no framework, no network), shared by the service and its
tests.

The retailer's Desk button *Work out sell-through* on one run (the Desk action extension point, ``desk_action/1``)
sends one signed POST per press:

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang", "idempotency_key", "inputs": {},
                                           "records": [{"doctype": "PP SST Sell-through", "name", "fields": {"name"}}]}}

``verify`` checks the signature the retailer puts on every press; ``run_of_press`` takes the pressed run; ``run_of``
reads it (its group, style, date, attributes and stores) or says what to fix; ``order_of`` reads an attribute's own
order of values; ``variants_of`` reads the group's items and their size and colour; ``sold_of`` and ``stock_of`` read
the two reports' answers (POS Sale Report, Stock Projected Quantity) by their column names; ``rows_of`` puts them side by
side; ``summary_of`` and ``message`` say what the press did. ⛔ No answer writes anything: the service writes the rows
itself, with its own API key and its own rights, BEFORE it answers.

``verify`` and ``message`` are S49's (``samples/s49_post_sale_feedback/feedback.py``, kit ``main`` ``c9f8c50``): a
defect here is a defect there — report it on the Partner Programme's board.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time

PREFIX = "PP SST"
RUN, STORE, ROW = "PP SST Sell-through", "PP SST Store", "PP SST Row"
SKEW_S = 300                 # a press stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024
STORES_MAX = 20              # stores a run reads: two reports each, side by side, inside the press's 10 seconds
ROWS_MAX = 1000              # rows a press writes on the run in one save
ITEMS_MAX = 5000             # item-attribute rows read for the group (a variant has one per attribute)
DAYS_MAX = 730               # Sold since at most two years back
POS_SALE_REPORT, STOCK_REPORT = "POS Sale Report", "Stock Projected Quantity"


def use_prefix(prefix: str):
    """The record types under another prefix: *IVENDNEXT SST Sell-through* for the library's app."""
    global PREFIX, RUN, STORE, ROW
    PREFIX, RUN, STORE, ROW = prefix, f"{prefix} Sell-through", f"{prefix} Store", f"{prefix} Row"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the press is the retailer's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def run_of_press(body: dict) -> tuple[str, str]:
    """(the pressed run's name, the pressing user), or ``ValueError``. One run a press."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if len(ctx["records"]) != 1:
        raise ValueError("one run a press")
    rec = ctx["records"][0]
    if not isinstance(rec, dict) or rec.get("doctype") != RUN or not isinstance(rec.get("name"), str) or not rec["name"]:
        raise ValueError("not a run")
    user = ctx.get("user")
    return rec["name"], user if isinstance(user, str) else ""


class Run:
    def __init__(self, name, item_group, style, since, size_attribute, colour_attribute, stores):
        self.name, self.item_group, self.style = name, item_group, style
        self.since, self.size_attribute, self.colour_attribute, self.stores = since, size_attribute, colour_attribute, stores


def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def run_of(doc: dict, today: datetime.date) -> Run | str:
    """A run as the service uses it, or the sentence that says what to fix (shown to the buyer)."""
    name = doc.get("name") or ""
    group, size = _text(doc.get("item_group")), _text(doc.get("size_attribute"))
    if not (group and size):
        return f"{name}: fill the item group and the size attribute, then press again."
    try:
        since = datetime.date.fromisoformat(_text(doc.get("sold_since"))[:10])
    except ValueError:
        return f"{name}: fill Sold since, then press again."
    if since > today + datetime.timedelta(days=1):     # a store east of UTC may already be on UTC's tomorrow
        return f"{name}: Sold since is after today."
    if (today - since).days > DAYS_MAX:
        return f"{name}: Sold since may be at most two years back."
    colour = _text(doc.get("colour_attribute"))
    if colour == size:
        return f"{name}: the colour attribute must differ from the size attribute."
    stores = []
    for row in doc.get("stores") or []:
        s = _text(row.get("store")) if isinstance(row, dict) else ""
        if s and s not in stores:
            stores.append(s)
    if not stores:
        return f"{name}: add at least one store, then press again."
    if len(stores) > STORES_MAX:
        return f"{name}: at most {STORES_MAX} stores a run; make a second run for the rest."
    return Run(name, group, _text(doc.get("style")), since, size, colour, stores)


def order_of(attribute: dict) -> dict:
    """{value: its place} in the attribute's own list of values (S, M, L, XL as the retailer listed them)."""
    rows = [r for r in attribute.get("item_attribute_values") or [] if isinstance(r, dict) and _text(r.get("attribute_value"))]
    rows.sort(key=lambda r: r.get("idx") if isinstance(r.get("idx"), int) else 0)
    return {_text(r["attribute_value"]): i for i, r in enumerate(rows)}


def variants_of(rows: list, run: Run) -> dict:
    """{item: {"style", "size", "colour"}} from the group's item rows (one row per item and attribute, as the record API
    answers ``attributes.attribute`` and ``attributes.attribute_value``). An item with no value of the size attribute is
    left out; with no colour attribute named, colour is blank. A run that names a style keeps that style's items only."""
    out: dict = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        item, style = _text(r.get("name")), _text(r.get("variant_of"))
        if not item or not style or (run.style and style != run.style):
            continue
        v = out.setdefault(item, {"style": style, "size": "", "colour": ""})
        attr, value = _text(r.get("attribute")), _text(r.get("attribute_value"))
        if attr == run.size_attribute:
            v["size"] = value
        elif run.colour_attribute and attr == run.colour_attribute:
            v["colour"] = value
    return {k: v for k, v in out.items() if v["size"]}


def _key(c) -> str:
    """A report column's name: its fieldname (``run_report`` answers every column as a dict), else its label."""
    if isinstance(c, dict):
        c = c.get("fieldname") or c.get("label") or ""
    return c.strip().lower().replace(" ", "_") if isinstance(c, str) else ""


def _table(answer, report: str) -> list[dict]:
    """A report's rows as dicts by column name, whether it answered them as lists or as dicts."""
    msg = answer.get("message") if isinstance(answer, dict) and "message" in answer else answer
    if isinstance(msg, dict) and msg.get("prepared_report"):    # moved to the background: run_report never starts a run,
        raise ValueError(f"{report} was made a prepared report, so it answers no rows to this app: untick Prepared "
                         "Report on it")                        # and reads only a run its own user prepared
    if not isinstance(msg, dict) or not isinstance(msg.get("result"), list):
        raise ValueError(f"{report} answered no rows")
    cols = [_key(c) for c in msg.get("columns") or []]
    out = []
    for r in msg["result"]:
        if isinstance(r, dict):
            out.append({_key(k): v for k, v in r.items()})
        elif isinstance(r, (list, tuple)) and cols:
            out.append(dict(zip(cols, r)))
    return out


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def sold_of(answer, items: dict) -> dict:
    """{item: units sold, returns taken off} from POS Sale Report's answer (report type Item: ``item``, ``unit_solds``),
    for the run's items only. A row with neither column is not this report's: ``ValueError``."""
    rows = _table(answer, POS_SALE_REPORT)
    if rows and not any("item" in r and "unit_solds" in r for r in rows):
        raise ValueError("POS Sale Report answered without its item and units columns")
    out: dict = {}
    for r in rows:
        item = r.get("item")
        if isinstance(item, str) and item in items:
            out[item] = out.get(item, 0.0) + _num(r.get("unit_solds"))
    return out


def stock_of(answer, items: dict, store: str) -> dict:
    """{item: units in stock} from Stock Projected Quantity's answer for one store: actual stock less the till's sales
    whose stock has not left yet (``reserved_qty_for_pos``), so a plain till sale counts once whichever way a build books it."""
    rows = _table(answer, STOCK_REPORT)
    if rows and not any("item_code" in r and "actual_qty" in r for r in rows):
        raise ValueError("Stock Projected Quantity answered without its item and actual columns")
    out: dict = {}
    for r in rows:
        item = r.get("item_code")
        if isinstance(item, str) and item in items and r.get("warehouse") in (None, store):
            out[item] = out.get(item, 0.0) + _num(r.get("actual_qty")) - _num(r.get("reserved_qty_for_pos"))
    return out


def sell_through(sold: float, in_stock: float) -> float:
    """Sold ÷ (sold + in stock), as a percent to one place. Nothing sold, or more returned than sold: 0."""
    if sold <= 0:
        return 0.0
    return round(100.0 * sold / (sold + max(in_stock, 0.0)), 1)


def rows_of(items: dict, sold: dict, stock: dict, run: Run, size_order: dict, colour_order: dict) -> list[dict]:
    """One row per style, colour, size and store that sold or holds stock; with no colour attribute, a size's colours
    are counted together. ``sold`` and ``stock`` are {store: {item: units}}. Sorted by style, colour (its attribute's
    order), size (its attribute's order), then the run's order of stores."""
    acc: dict = {}
    for item, v in items.items():
        for store in run.stores:
            s, q = sold.get(store, {}).get(item, 0.0), stock.get(store, {}).get(item, 0.0)
            if not s and not q:
                continue
            k = (v["style"], v["colour"], v["size"], store)
            a = acc.setdefault(k, {"items": [], "sold": 0.0, "in_stock": 0.0})
            a["items"].append(item)
            a["sold"] += s
            a["in_stock"] += q
    far = len(size_order) + len(colour_order) + 1
    place = {s: i for i, s in enumerate(run.stores)}

    def size_key(size):
        """The attribute's own order; an attribute with number values (shoe sizes 6, 6.5 … 11) has no list: by number."""
        if size in size_order:
            return (0, size_order[size], "")
        try:
            return (1, float(size), "")
        except ValueError:
            return (2, 0.0, size)

    def order(k):
        style, colour, size, store = k
        return (style, colour_order.get(colour, far), colour, size_key(size), place[store])

    out = []
    for k in sorted(acc, key=order):
        a = acc[k]
        sold_n, stock_n = round(a["sold"], 3), round(a["in_stock"], 3)
        out.append({"style": k[0], "item": a["items"][0] if len(a["items"]) == 1 else "", "colour": k[1], "size": k[2],
                    "store": k[3], "sold": sold_n, "in_stock": stock_n, "sell_through": sell_through(sold_n, stock_n),
                    "none_left": 1 if stock_n <= 0 else 0})
    return out


def _n(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def summary_of(rows: list[dict], run: Run) -> str:
    sold = sum(r["sold"] for r in rows)
    stock = sum(max(r["in_stock"], 0.0) for r in rows)
    out = sum(1 for r in rows if r["none_left"] and r["sold"] > 0)
    s = (f"{_n(sold)} sold since {run.since.isoformat()}, {_n(stock)} in stock now: {sell_through(sold, stock)}% sold "
         f"through, across {len(run.stores)} store{'' if len(run.stores) == 1 else 's'}.")
    if out:
        s += f" {out} row{'' if out == 1 else 's'} sold out: none left in that store."
    return s


def message(body: str, level: str = "success", title: str = "Sell-through") -> dict:
    """The answer in the extension point's closed vocabulary (title at most 60, body at most 280)."""
    return {"message": {"title": title[:60], "body": body if len(body) <= 280 else body[:279] + "…", "level": level},
            "refresh": True}
