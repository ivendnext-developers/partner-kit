"""S2's process: putaway, pick, and what a booked sale takes off the shop floor. Over the API only.

Where the stock IS booked stays the engine's (its warehouses, its Stock Entry, its valuation and ledger). Which BIN
it sits in is the partner's, in the manifest's own record types. Every write to a bin record is ONE save carrying
both the new quantity and the movement row that explains it, so a quantity never changes without its reason.
"""

from __future__ import annotations

from datetime import datetime

import core
from tenant import TenantError

ITEM_IN_BIN, BIN, LOCATION = "PP BLN Item In Bin", "PP BLN Bin", "PP BLN Location"


class Refused(Exception):
    pass


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def where(tenant, bin_code) -> dict:
    b = tenant.get(BIN, bin_code)
    loc = tenant.get(LOCATION, b["location"])
    return {"bin": bin_code, "location": loc["name"], "kind": loc["kind"], "warehouse": loc["warehouse"],
            "store": loc["store"]}


def _row(tenant, bin_code, item):
    try:
        return tenant.get(ITEM_IN_BIN, f"{bin_code}--{item}")
    except TenantError as e:
        if e.code == 404:
            return None
        raise


def _move(tenant, place, item, delta, kind, reference):
    """Add ``delta`` to (bin, item) with its movement row — one save. Creates the record on first use."""
    row = _row(tenant, place["bin"], item)
    mv = {"kind": kind, "qty": abs(delta), "reference": reference, "at": _now()}
    if row is None:
        if delta < 0:
            raise Refused(f"{item} is not in bin {place['bin']}")
        return tenant.insert(ITEM_IN_BIN, {"bin": place["bin"], "item": item, "qty": delta, "kind": place["kind"],
                                           "warehouse": place["warehouse"], "store": place["store"], "movements": [mv]})
    qty = float(row.get("qty") or 0) + delta
    if qty < 0:
        raise Refused(f"bin {place['bin']} holds {row.get('qty')} of {item}, not {abs(delta)}")
    return tenant.update(ITEM_IN_BIN, row["name"], {"qty": qty, "movements": (row.get("movements") or []) + [mv]})


def putaway(tenant, item, qty, bin_code) -> dict:
    """Assign stock already RECEIVED into a back room to one of its bins (the partner's records only)."""
    place = where(tenant, bin_code)
    if place["kind"] != core.BACK:
        raise Refused(f"{bin_code} is not a back-room bin")
    on_hand = tenant.stock_balance(item, place["warehouse"])
    assigned = sum(float(r["qty"] or 0) for r in tenant.list(ITEM_IN_BIN, ["qty"], [["item", "=", item],
                                                                                   ["warehouse", "=", place["warehouse"]]]))
    if qty <= 0 or qty > on_hand - assigned:
        raise Refused(f"only {on_hand - assigned:g} of {item} in {place['warehouse']} is not yet in a bin")
    return _move(tenant, place, item, qty, "Putaway", f"putaway {_now()}")


def pick(tenant, company, item, qty, from_bin, to_bin, pos_profile) -> dict:
    """Move stock from a back-room bin to a shop-floor bin of the till's own store: the ENGINE books the transfer
    (a Stock Entry, created and booked over the API), then the two bin records follow it."""
    src, dst = where(tenant, from_bin), where(tenant, to_bin)
    selling = tenant.selling_warehouse(pos_profile)
    if src["kind"] != core.BACK or dst["kind"] != core.FLOOR or dst["warehouse"] != selling:
        raise Refused(f"a pick goes from a back-room bin to a shop-floor bin of {selling}")
    row = _row(tenant, from_bin, item)
    if qty <= 0 or row is None or float(row.get("qty") or 0) < qty:
        raise Refused(f"bin {from_bin} holds {row.get('qty') if row else 0} of {item}")
    se = tenant.transfer(company, item, qty, src["warehouse"], selling)
    _move(tenant, src, item, -qty, "Pick out", se["name"])
    _move(tenant, dst, item, qty, "Pick in", se["name"])
    return {"stock_entry": se["name"], "docstatus": se.get("docstatus")}


def booked_sale(tenant, doctype, name) -> dict:
    """A booked sale takes its items off the shop-floor bins of the store it sold from — once (core.sale_decrements)."""
    sale = tenant.get(doctype, name)
    if sale.get("docstatus") != 1 or sale.get("is_return") or sale.get("is_consolidated"):
        return {"skipped": "not a booked sale that moved stock from a till (returns and roll-ups are not counted)"}
    if doctype == "Sales Invoice" and not sale.get("update_stock"):
        return {"skipped": "this sale moved no stock"}
    by_store = {}
    for it in sale.get("items") or []:
        wh = it.get("warehouse") or sale.get("set_warehouse")
        by_store.setdefault(wh, []).append({"item_code": it["item_code"], "qty": it.get("stock_qty") or it.get("qty")})
    applied = []
    for store, lines in by_store.items():
        codes = sorted({line["item_code"] for line in lines})
        names = [r["name"] for r in tenant.list(ITEM_IN_BIN, ["name"], [["store", "=", store], ["kind", "=", core.FLOOR],
                                                                        ["item", "in", codes]])]
        rows = [tenant.get(ITEM_IN_BIN, n) for n in names]           # with their movements
        by_name = {r["name"]: r for r in rows}
        for step in core.sale_decrements(name, lines, rows):
            r = by_name[step["name"]]
            mv = {"kind": "Sale", "qty": step["take"], "short": step["short"], "reference": name, "at": _now()}
            tenant.update(ITEM_IN_BIN, r["name"], {"qty": float(r["qty"] or 0) - step["take"],
                                                   "movements": (r.get("movements") or []) + [mv]})
            applied.append(dict(step, bin=r["bin"], item=r["item"]))
    return {"applied": applied}


def point_rows(tenant, context) -> list[dict]:
    """The remote binding's loader: the same rows the hosted app reads, over the API."""
    codes = sorted({line["item_code"] for line in context.get("lines") or []})
    if not codes:
        return []
    return tenant.list(ITEM_IN_BIN, ["name", "item", "bin", "qty", "kind"],
                       [["item", "in", codes], ["store", "=", context["store"]]])
