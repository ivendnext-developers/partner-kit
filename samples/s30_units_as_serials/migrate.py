#!/usr/bin/env python3
"""S30 — move a shop's own unit table onto batch+serial items (standard library only).

    PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 migrate.py            # what it would do
    PP_BASE=… PP_KEY=… PP_SECRET=… python3 migrate.py --apply                                          # do it

Why new items: iVendNext refuses to switch on Has Serial No for an item that already has stock or sales booked, so each
old item's units move to a NEW item that has both Has Batch No and Has Serial No (declared in config.json ``items``, made
by ``apply_config.py`` first). For each lot (old item, store, batch):

  1. the shop's own count gives the old item's quantity and value in that lot (a draft count, read and deleted);
  2. the lot moves only when that quantity equals the coded units the table lists for it. Otherwise it is HELD and
     named: packs without a code would leave the stock unseen;
  3. the new item's batch is made (the old batch's name with ``batch_name``, its expiry and manufacturing dates copied),
     and the codes are received into it as serial numbers, at the old valuation rate, one receipt per store;
  4. the old item's lot is counted to 0, one count for every lot that moved.

Run it twice and nothing doubles: a code that is already a serial number of its new item is counted as moved, and a lot
already at 0 is left. A code that is already another item's serial number is a conflict: never one code on two items, and
its lot is held. Each document it makes carries ``PP USN migration`` in its remarks. The count to 0 and the receipt both
post to the company's stock adjustment account at the same rate (the receipt's rows name that account, so an item's or
group's own default expense account is not used), so the value moves from the old item to the new one. A lot whose old
batch has expired is held: iVendNext refuses to receive into an expired batch.

The source table's fields come from config.json ``migration.fields`` (S19's ``PP UNC Unit`` by default: no store field,
so ``default_warehouse`` names it). ⚠ This version names a serial number by its code; a later version of iVendNext names
it by a generated name, with the code in the serial number field. This script reads and writes the name as the code,
as today's iVendNext does; on the later version the lookups by name must read the code field instead.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shop as S  # noqa: E402
import units as U  # noqa: E402


def load(path=None):
    return json.load(open(path or os.environ.get("PP_CONFIG") or os.path.join(HERE, "config.json")))


def read_units(shop, mig):
    f = mig["fields"]
    fields = sorted({v for v in f.values() if v})
    rows = shop.list(mig["record_type"], [], fields)
    return rows


def run(shop, conf, apply=False, out=print):
    mig = conf["migration"]
    units = read_units(shop, mig)
    codes = [(u.get(mig["fields"]["code"]) or "").strip() for u in units]
    existing = shop.serials([c for c in codes if c])
    plan = U.plan_migration(units, existing, mig)
    current = shop.lot_stock(conf["company"], sorted(plan["expected"]))
    today = datetime.date.today().isoformat()
    old = {b: shop.get("Batch", b) or {} for b in sorted({lot[2] for lot in plan["expected"]})}
    expired = {b: str(d["expiry_date"]) for b, d in old.items() if d.get("expiry_date") and str(d["expiry_date"]) < today}
    zero, held = U.zero_rows(plan, current, mig, expired)
    wait = U.held_receipts(held, mig)
    todo = {k: v for k, v in plan["receive"].items() if k not in wait}
    rate = {(mig["item_map"][r["item_code"]], r["warehouse"], U.batch_name(mig.get("batch_name", "{batch}-U"), r["batch_no"])): r["rate"]
            for r in zero}

    summary = {"units_read": len(units), "to_receive": sum(len(v) for v in todo.values()), "moved_before": len(plan["moved"]),
               "skipped": len(plan["skipped"]), "missing": len(plan["missing"]), "conflicts": len(plan["conflicts"]),
               "lots_to_zero": len(zero), "lots_held": len(held)}
    out(json.dumps(summary))
    for kind in ("skipped", "missing", "conflicts"):
        for e in plan[kind]:
            out(f"  {kind[:-1] if kind.endswith('s') else kind}: {e['code'] or '(no code)'} — {e['why']}")
    for h in held:
        out(f"  held lot: {h['item']} · {h['warehouse']} · {h['batch']} — {h['why']}")
    if not apply:
        out("  (nothing booked: the draft count it read was deleted; add --apply)")
        return summary

    batches = {b["name"] for b in shop.list_in("Batch", "name", list(plan["batches"]), ["name"])}
    for new_batch, b in sorted(plan["batches"].items()):
        if new_batch in batches or not any(k[2] == new_batch for k in todo):
            continue
        src = old.get(b["from"]) or {}
        shop.insert("Batch", {"batch_id": new_batch, "item": b["item"], "expiry_date": src.get("expiry_date"),
                              "manufacturing_date": src.get("manufacturing_date"),
                              "description": f"{S.MARK}: from batch {b['from']}"})
        out(f"  made batch {new_batch} (from {b['from']})")
    account = shop.stock_adjustment_account(conf["company"])    # the count to 0 posts here too, so the value only moves
    by_store: dict = {}
    for (item, store, batch), cs in sorted(todo.items()):
        by_store.setdefault(store, []).append({"item_code": item, "qty": len(cs), "t_warehouse": store, "batch_no": batch,
                                               "expense_account": account,
                                               "serial_no": "\n".join(cs), "use_serial_batch_fields": 1,
                                               "basic_rate": rate.get((item, store, batch), 0)})
    for store, rows in by_store.items():
        doc = shop.insert("Stock Entry", {"stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
                                          "company": conf["company"], "docstatus": 1, "remarks": S.MARK, "items": rows})
        out(f"  received {sum(r['qty'] for r in rows)} unit(s) in {store}: {doc['name']}")
    if zero:
        rows = [{"item_code": r["item_code"], "warehouse": r["warehouse"], "batch_no": r["batch_no"], "qty": 0,
                 "use_serial_batch_fields": 1} for r in zero]
        doc = shop.insert("Stock Reconciliation", {"company": conf["company"], "purpose": "Stock Reconciliation", "docstatus": 1,
                                                   "remarks": f"{S.MARK}: the old item counted to 0", "items": rows})
        out(f"  counted {len(rows)} old lot(s) to 0: {doc['name']}")
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--apply", action="store_true", help="write; without it, say what would be done")
    p.add_argument("--config")
    a = p.parse_args(argv)
    print(f"S30 migrate {'(apply)' if a.apply else '(dry run)'} at {datetime.datetime.now():%Y-%m-%d %H:%M}")
    run(S.Shop.from_env(), load(a.config), apply=a.apply)


if __name__ == "__main__":
    main()
