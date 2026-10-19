"""S27 — the rules, pure: which stock is low, which batch is near its expiry, the alert's key, the request's stamp and
lines. No shop, no clock: everything comes in as plain dicts and a date. Python 3.9+, standard library only.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re

LOW, EXPIRY = "Low stock", "Near expiry"
STAMP = "PP-STK"


def stamp(store: str, day: _dt.date) -> str:
    """The title of the service's draft request for one store and day. A request without it is a person's."""
    return f"{STAMP} {store} {day.isoformat()}"


def ours_for(title: str | None, store: str) -> bool:
    """A draft is the service's for this store when its title carries the stamp and the store. Any other is a person's."""
    return (title or "").startswith(f"{STAMP} {store} ")


def key(kind: str, store: str | None, item: str, batch: str | None, day: _dt.date) -> str:
    """One alert per kind, store, item, batch and day: the alert record's name, so the shop refuses a second."""
    h = hashlib.sha1("\x1f".join((kind, store or "", item, batch or "")).encode()).hexdigest()[:12]
    return f"{day.isoformat()} {'LOW' if kind == LOW else 'EXP'} {h}"


def _f(v) -> float:
    return float(v or 0)


def last_day(today: _dt.date, days: int) -> _dt.date:
    """The last expiry date the alert covers: today plus the settings' days."""
    return today + _dt.timedelta(days=days)


def stores(settings: dict, warehouses: list[dict]) -> list[str]:
    """The stores watched: the settings' list, or every warehouse that is not a group, the source or the clearance."""
    listed = [r["warehouse"] for r in settings.get("stores") or [] if r.get("warehouse")]
    if listed:
        return listed
    skip = {settings.get("source_warehouse"), settings.get("clearance_warehouse")}
    return [w["name"] for w in warehouses if not w.get("is_group") and not w.get("disabled") and w["name"] not in skip]


def low_stock(reorder_rows: list[dict], bins: dict[tuple[str, str], dict], watched: list[str]) -> list[dict]:
    """A reorder row of a watched store whose projected stock is below its level. The quantity is the standard
    reorder's: the reorder quantity, or the shortfall when that is larger. Only a row of type Transfer makes a line."""
    out = []
    for r in reorder_rows:
        store, item, level = r.get("warehouse"), r["item"], _f(r.get("warehouse_reorder_level"))
        if store not in watched or level <= 0:
            continue
        b = bins.get((item, store)) or {}
        projected = _f(b.get("projected_qty"))
        if projected >= level:
            continue
        qty = max(_f(r.get("warehouse_reorder_qty")), level - projected)
        out.append({"kind": LOW, "store": store, "item": item, "batch": None, "qty": projected, "level": level,
                    "move": qty if r.get("material_request_type") == "Transfer" else 0, "uom": b.get("stock_uom")})
    return out


def near_expiry(batches: list[dict], per_store: dict[tuple[str, str], float] | None, watched: list[str],
                today: _dt.date, days: int) -> list[dict]:
    """A batch whose expiry date is on or before today + days (an expired batch still in stock included).
    With the quantity per store known, one alert per watched store that holds some; without it, one alert for the
    batch, its total, and no store."""
    last = last_day(today, days)
    out = []
    for b in batches:
        if b.get("disabled") or not b.get("expiry_date"):
            continue
        exp = _dt.date.fromisoformat(str(b["expiry_date"])[:10])
        if exp > last:
            continue
        base = {"kind": EXPIRY, "item": b["item"], "batch": b["name"], "expiry_date": exp.isoformat(), "uom": b.get("stock_uom")}
        if per_store is None:
            if _f(b.get("batch_qty")) > 0:
                out.append({**base, "store": None, "qty": _f(b.get("batch_qty")), "move": 0, "known": False})
            continue
        for store in watched:
            q = per_store.get((b["name"], store), 0.0)
            if q > 0:
                out.append({**base, "store": store, "qty": q, "move": q, "known": True})
    return out


def lines(alerts: list[dict], settings: dict, day: _dt.date) -> dict[str, list[dict]]:
    """The request lines per store. Low stock: from the source warehouse to the store. Near expiry: from the store to
    the clearance warehouse, only when one is named and the batch's store is known; else alert-only."""
    source, clear = settings.get("source_warehouse"), settings.get("clearance_warehouse")
    per: dict[str, list[dict]] = {}
    for a in alerts:
        if not a.get("store") or a["move"] <= 0:
            continue
        if a["kind"] == LOW and source:
            frm, to = source, a["store"]
        elif a["kind"] == EXPIRY and clear:            # a batch with no known store has no store: skipped above
            frm, to = a["store"], clear
        else:
            continue
        line = {"item_code": a["item"], "qty": a["move"], "from_warehouse": frm, "warehouse": to,
                "schedule_date": day.isoformat()}
        if a["kind"] == EXPIRY:                          # a request line has no batch column: its description names it
            line["description"] = f"{STAMP} batch {a['batch']}"
        if a.get("uom"):
            line.update(uom=a["uom"], conversion_factor=1)
        per.setdefault(a["store"], []).append(line)
        a["line"] = line
    return per


_BATCH = re.compile(re.escape(STAMP) + r" batch ([^\s;<]+)")


def batches_of(line: dict) -> set[str]:
    return set(_BATCH.findall(line.get("description") or ""))


def same_line(a: dict, b: dict) -> bool:
    """The same move already asked for: item, both warehouses, and for a clearance line its batch named on that row."""
    keys = ("item_code", "from_warehouse", "warehouse")
    return tuple(a.get(k) for k in keys) == tuple(b.get(k) for k in keys) and batches_of(a) <= batches_of(b)


def place(lines: list[dict], items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Put new lines on a request's rows. A request holds an item once (the shop's default), so a clearance line
    for an item already there for the same move joins that row: its quantity is added and its batch named. A line
    for an item already there for another move is left off. Returns the rows and the lines left off."""
    rows, left = [dict(i) for i in items], []
    for ln in lines:
        row = next((i for i in rows if i.get("item_code") == ln["item_code"]), None)
        if row is None:
            rows.append(dict(ln))
        elif batches_of(ln) and all(row.get(k) == ln[k] for k in ("from_warehouse", "warehouse")):
            row["qty"] = float(row.get("qty") or 0) + ln["qty"]
            row["description"] = f"{row.get('description') or ''}; {ln['description']}".lstrip("; ")
        else:
            left.append(ln)
    return rows, left
