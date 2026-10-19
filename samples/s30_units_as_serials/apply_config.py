#!/usr/bin/env python3
"""S30 — set a shop up so each pack's printed code is a serial number (standard library only). No code runs in the shop.

    PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 apply_config.py [--remove]

From config.json it sets, over the record API:
  * Stock Settings: the values under ``stock_settings`` (the earlier values are kept in the shop's before-file for --remove);
  * a Defective store per entry of ``defective_warehouses``: a unit moved there cannot be sold at the till, which
    refuses a unit that is in another store;
  * each item of ``items`` with both Has Batch No and Has Serial No, **no Serial No Series** (so a receipt must be given
    the printed codes and none is made up), no automatic batch, its selling price, and its barcodes. A barcode that is
    on the item it ``replaces`` moves to the new item.

Run it twice and nothing doubles. ``--remove`` puts Stock Settings back and undoes only what THIS script made or moved
(listed in the before-file as it goes): a record that was already in the shop is never touched. A record it made that
stock or a sale points at is retired (disabled), and the line says so. It cannot undo stock, and an item's Has
Serial No cannot be switched off once the item has stock.

The key belongs to the shop's administrator (it edits Stock Settings, Warehouse, Item and Item Price).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shop as S  # noqa: E402

def before_file():
    """One before-file per shop (``.s30_<host>_before.json``): the earlier Stock Settings, and every record this script
    made or barcode it moved, so ``--remove`` undoes exactly that, on that shop."""
    host = urllib.parse.urlparse(os.environ["PP_BASE"]).netloc.replace(":", "_") or "shop"
    return os.path.join(HERE, f".s30_{host}_before.json")


def read_before():
    p = before_file()
    return json.load(open(p)) if os.path.exists(p) else {"settings": None, "made": [], "moved": []}


def write_before(b):
    json.dump(b, open(before_file(), "w"), indent=1)


def load():
    return json.load(open(os.environ.get("PP_CONFIG") or os.path.join(HERE, "config.json")))


def defective_names(shop, conf):
    names = [w["warehouse_name"] for w in conf.get("defective_warehouses", [])]
    if not names:
        return []
    return [w["name"] for w in shop.list("Warehouse", [["warehouse_name", "in", names], ["company", "=", conf["company"]]], ["name"])]


def barcode_owner(shop, code):
    rows = shop.list("Item Barcode", [["barcode", "=", code]], ["parent", "name"], parent="Item")
    return rows[0]["parent"] if rows else None


def item_doc(it):
    return {"item_code": it["item_code"], "item_name": it["item_name"], "item_group": it["item_group"],
            "stock_uom": it.get("stock_uom", "Nos"), "is_stock_item": 1, "has_batch_no": 1, "has_serial_no": 1,
            "serial_no_series": "", "create_new_batch": 0}


def apply(shop, conf, out=print):
    # 1. Stock Settings, the earlier values kept once
    keys = sorted(conf.get("stock_settings", {}))
    cur = shop.get("Stock Settings", "Stock Settings")
    before = read_before()
    if before["settings"] is None:
        before["settings"] = {k: cur.get(k) for k in keys}
        write_before(before)

    def made(dt, name):
        before["made"].append([dt, name])
        write_before(before)
    want = {k: v for k, v in conf.get("stock_settings", {}).items() if cur.get(k) != v}
    if want:
        shop.update("Stock Settings", "Stock Settings", want)
    out(f"  Stock Settings: {conf.get('stock_settings')} ({'changed ' + str(sorted(want)) if want else 'already so'})")

    # 2. the Defective stores
    for w in conf.get("defective_warehouses", []):
        found = shop.list("Warehouse", [["warehouse_name", "=", w["warehouse_name"]], ["company", "=", conf["company"]]], ["name"])
        if found:
            out(f"  kept     Warehouse: {found[0]['name']}")
            continue
        doc = shop.insert("Warehouse", {"warehouse_name": w["warehouse_name"], "parent_warehouse": w["parent_warehouse"],
                                        "company": conf["company"], "is_group": 0})
        made("Warehouse", doc["name"])
        out(f"  created  Warehouse: {doc['name']} (a Defective store: the till will not sell a unit that is here)")

    # 3. the batch+serial items, their prices and barcodes
    for it in conf.get("items", []):
        doc = shop.get("Item", it["item_code"])
        if not doc:
            doc = shop.insert("Item", item_doc(it))
            made("Item", it["item_code"])
            out(f"  created  Item: {it['item_code']} (Has Batch No, Has Serial No, no Serial No Series)")
        else:
            off = {k: v for k, v in item_doc(it).items() if k in ("has_batch_no", "has_serial_no") and doc.get(k) != v}
            for k, why in (("serial_no_series", "a receipt would make up codes instead of taking the printed ones"),
                           ("create_new_batch", "a receipt would make up batches")):
                if doc.get(k):
                    out(f"  ⚠ Item {it['item_code']} has {k} set: {why}; clear it in Desk (left as it is)")
            if off:
                raise SystemExit(f"Item {it['item_code']} exists without {sorted(off)}: iVendNext refuses to switch on "
                                 "serial numbers for an item with stock; choose a new item code")
            out(f"  kept     Item: {it['item_code']}")
        if it.get("price_list") and not shop.list("Item Price", [["item_code", "=", it["item_code"]], ["price_list", "=", it["price_list"]]], ["name"]):
            p = shop.insert("Item Price", {"item_code": it["item_code"], "price_list": it["price_list"], "price_list_rate": it["price"], "selling": 1})
            made("Item Price", p["name"])
            out(f"  created  Item Price: {it['item_code']} at {it['price']} in {it['price_list']}")
        for code in it.get("barcodes", []):
            owner = barcode_owner(shop, code)
            if owner == it["item_code"]:
                continue
            if owner and owner != it.get("replaces"):
                out(f"  ⚠ barcode {code} is on item {owner}, not on {it.get('replaces')}: left there")
                continue
            if owner:
                old = shop.get("Item", owner)
                shop.update("Item", owner, {"barcodes": [b for b in old.get("barcodes", []) if b["barcode"] != code]})
            new = shop.get("Item", it["item_code"])
            shop.update("Item", it["item_code"], {"barcodes": new.get("barcodes", []) + [{"barcode": code}]})
            before["moved"].append([code, owner, it["item_code"]])
            write_before(before)
            out(f"  moved    barcode {code}: {owner or '(new)'} → {it['item_code']}")


def remove(shop, conf, out=print):
    if not os.path.exists(before_file()):
        out(f"  nothing recorded for this shop ({os.path.basename(before_file())} is not here): nothing to undo")
        return
    before = read_before()
    for code, owner, to in reversed(before["moved"]):          # barcodes back to the item they came from
        new = shop.get("Item", to) or {}
        shop.update("Item", to, {"barcodes": [b for b in new.get("barcodes", []) if b["barcode"] != code]})
        if owner:
            old = shop.get("Item", owner) or {}
            shop.update("Item", owner, {"barcodes": old.get("barcodes", []) + [{"barcode": code}]})
        out(f"  moved back barcode {code} → {owner or '(none)'}")
    for dt, name in reversed(before["made"]):                 # only what this script made, newest first
        gone(shop, dt, name, out, retire={"disabled": 1} if dt in ("Item", "Warehouse") else None)
    if before["settings"] is not None:
        shop.update("Stock Settings", "Stock Settings", before["settings"])
        out("  Stock Settings put back to their earlier values")
    if os.path.exists(before_file()):
        os.remove(before_file())
    out("  (stock stays: received units, their batches and the receipts are the shop's history)")


def gone(shop, dt, name, out, retire=None):
    try:
        shop.delete(dt, name)
        out(f"  removed  {dt}: {name}")
    except S.F.FeedError as e:
        if retire:
            shop.update(dt, name, retire)
            out(f"  retired  {dt}: {name} {retire} (stock or a sale points at it)")
        else:
            out(f"  kept     {dt}: {name} ({str(e)[:80]})")


if __name__ == "__main__":
    print("S30 remove" if "--remove" in sys.argv else "S30 apply")
    (remove if "--remove" in sys.argv else apply)(S.Shop.from_env(), load())
