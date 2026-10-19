#!/usr/bin/env python3
"""S5 — apply the configuration pack over the record API (standard library only). No code runs in the shop.

    PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 apply_config.py [--remove]

The key belongs to a user who may edit Retail Setting, Reason Code Master, Item, Item Price, Stock Entry, Customer, Customer
Group, Transaction Item Attribute and the promotion masters. Measured on the bench, these roles together do: System Manager,
Retail Manager, Item Manager, Stock Manager, Sales Master Manager. That is the shop's administrator (recipes/integration_user.md describes narrow roles for
connected apps; a one-time set-up like this one is the administrator's). It is IDEMPOTENT: run it twice and nothing
doubles. --remove puts back what it changed (the switches to their earlier values) and deletes what it made.

PP_CONFIG=<path> uses another configuration file than config.json (the tests give it fresh IMEIs on every run).
Writes a small file, .s5_before.json, next to itself: the earlier values of the switches, so --remove can restore them.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = json.load(open(os.environ.get("PP_CONFIG") or os.path.join(HERE, "config.json")))
BEFORE = os.path.join(HERE, ".s5_before.json")
BASE = os.environ["PP_BASE"].rstrip("/")
AUTH = f"token {os.environ['PP_KEY']}:{os.environ['PP_SECRET']}"
DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} → {e.code}: {e.read()[:400].decode(errors='replace')}")


def q(dt):
    return "/api/resource/" + urllib.parse.quote(dt)


def get(dt, name=None, **params):
    if name is not None:
        return call("GET", f"{q(dt)}/{urllib.parse.quote(name)}").get("data")
    qs = urllib.parse.urlencode({k: json.dumps(v) for k, v in params.items()})
    return call("GET", f"{q(dt)}?{qs}").get("data", [])


def exists(dt, name):
    try:
        urllib.request.urlopen(urllib.request.Request(f"{BASE}{q(dt)}/{urllib.parse.quote(name)}", headers={"Authorization": AUTH}), timeout=30)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def ensure(dt, name, doc, live=None):
    """Create the record if it is not there; say what happened. ``live`` = (field, value): a record that --remove
    retired (rather than deleted) is switched back on by this call, so run, remove, run again leaves it live."""
    if exists(dt, name):
        if live and get(dt, name).get(live[0]) != live[1]:
            call("PUT", f"{q(dt)}/{urllib.parse.quote(name)}", {live[0]: live[1]})
            print(f"  restored {dt}: {name} ({live[0]} = {live[1]})")
            return False
        print(f"  kept     {dt}: {name}")
        return False
    call("POST", q(dt), dict(doc, doctype=dt))
    print(f"  created  {dt}: {name}")
    return True


def remove(dt, name, retire=None):
    """Delete the record. A record a booked sale points at cannot be deleted (the shop keeps its history): then it is
    RETIRED — ``retire`` = (field, value) — or left, and the line says which."""
    if not exists(dt, name):
        return
    req = urllib.request.Request(f"{BASE}{q(dt)}/{urllib.parse.quote(name)}", method="DELETE", headers={"Authorization": AUTH})
    try:
        urllib.request.urlopen(req, timeout=30)
        print(f"  removed  {dt}: {name}")
    except urllib.error.HTTPError as e:
        if e.code != 417 or "LinkExists" not in e.read().decode(errors="replace"):
            raise SystemExit(f"DELETE {dt} {name} → {e.code}")
        if retire:
            call("PUT", f"{q(dt)}/{urllib.parse.quote(name)}", {retire[0]: retire[1]})
            print(f"  retired  {dt}: {name} ({retire[0]} = {retire[1]}; a booked sale points at it)")
        else:
            print(f"  kept     {dt}: {name} (a booked sale points at it)")


def apply():
    # 1. coded reasons, each switched on by its Retail Setting flag
    before = json.load(open(BEFORE)) if os.path.exists(BEFORE) else None
    setting = get("Retail Setting", "Retail Setting")
    if before is None:
        before = {f: setting.get(f) for f in CONF["reason_flags"]}
        json.dump(before, open(BEFORE, "w"))
    for r in CONF["reasons"]:
        ensure("Reason Code Master", r["id"], {"id": r["id"], "description": r["id"].replace("PP CFG ", ""), "reason_type": r["type"],
                                              "is_active": 1, "comment_required": r.get("comment_required", 0)}, live=("is_active", 1))
    call("PUT", f"{q('Retail Setting')}/Retail%20Setting", {f: 1 for f in CONF["reason_flags"]})
    print("  switched on:", ", ".join(CONF["reason_flags"]))

    # 2. an IMEI per unit: serial numbers are the shop's own tracking; the IMEI IS the serial number
    it = CONF["imei_item"]
    ensure("Item", it["item_code"], {"item_code": it["item_code"], "item_name": it["item_name"], "item_group": it["item_group"],
                                     "stock_uom": "Nos", "is_stock_item": 1, "has_serial_no": 1})
    if not get("Item Price", fields=["name"], filters=[["item_code", "=", it["item_code"]], ["price_list", "=", it["price_list"]]]):
        call("POST", q("Item Price"), {"doctype": "Item Price", "item_code": it["item_code"], "price_list": it["price_list"],
                                       "price_list_rate": it["price"], "selling": 1})
        print(f"  created  Item Price: {it['item_code']} at {it['price']} in {it['price_list']}")
    have = {s["name"] for s in get("Serial No", fields=["name"], filters=[["item_code", "=", it["item_code"]]], limit_page_length=0)}
    todo = [i for i in it["imeis"] if i not in have]
    if todo:
        call("POST", q("Stock Entry"), {"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
                                        "company": it["company"], "docstatus": 1,
                                        "items": [{"item_code": it["item_code"], "qty": len(todo), "t_warehouse": it["warehouse"],
                                                   "basic_rate": it["price"] * 0.6, "use_serial_batch_fields": 1, "serial_no": "\n".join(todo)}]})
        print(f"  received {len(todo)} unit(s) with their IMEIs as serial numbers")

    # 3. a line detail with a pattern, for goods that carry no serial number (online; the pattern is checked at capture)
    la = CONF["line_attribute"]
    ensure("Transaction Item Attribute", la["name"], {"attribute_name": la["name"], "validation_type": "No Validation",
                                                      "regex_pattern": la["regex"], "sequence": la["sequence"], "active": 1}, live=("active", 1))

    # 4. member pricing: a tier is a customer group; one promotion per tier that EXCLUDES every other group
    mt = CONF["member_tiers"]
    for g in mt["groups"]:
        ensure("Customer Group", g, {"customer_group_name": g, "parent_customer_group": "All Customer Groups", "is_group": 0})
    ensure("Customer", mt["member_example"], {"customer_name": mt["member_example"], "customer_group": mt["groups"][0], "customer_type": "Individual"},
           live=("disabled", 0))
    others = [g["name"] for g in get("Customer Group", fields=["name"], filters=[["is_group", "=", 0]], limit_page_length=0)
              if g["name"] not in mt["groups"]]
    wh = [w["name"] for w in get("Warehouse", fields=["name"], filters=[["company", "=", CONF["imei_item"]["company"]], ["is_group", "=", 0]],
                                 limit_page_length=0)]
    seqs = [m["sequence_number"] or 0 for m in get("Promotion Bonus Buys Master", fields=["sequence_number"], limit_page_length=0)]
    ensure("Promotion Bonus Buys Master", mt["promotion_id"], {
        "id": mt["promotion_id"], "description": f"{mt['discount_percent']}% off the sale for {', '.join(mt['groups'])}",
        "promotion_type": "Bonus Buys", "discount_type": "Percent", "discount_percent": mt["discount_percent"],
        "minimum_bill_amount": 0, "minimum_quantity": 1, "active": 1, "sequence_number": (max(seqs) + 1) if seqs else 1,
        "table_applicability": [{"day": d, "enabled": 1, "start_time": "00:00:00", "end_time": "23:59:59"} for d in DAYS],
        "table_applicable_source": [{"source_type": "Warehouse", "source": w} for w in wh],
        "table_promotion_exclusion_list": [{"source_type": "Customer Group", "source": g} for g in others]})
    # a customer group added since the first run must not get the member discount: the list is recomputed EVERY run
    promo = get("Promotion Bonus Buys Master", mt["promotion_id"])
    have = sorted(r["source"] for r in promo.get("table_promotion_exclusion_list") or [] if r["source_type"] == "Customer Group")
    if have != sorted(others):
        call("PUT", f"{q('Promotion Bonus Buys Master')}/{urllib.parse.quote(mt['promotion_id'])}",
             {"table_promotion_exclusion_list": [{"source_type": "Customer Group", "source": g} for g in others]})
        print(f"  updated  the promotion's exclusion list: {have} → {sorted(others)}")
    print(f"  the promotion excludes these customer groups: {others}")
    # a customer with no group is not excluded by any promotion, so it would get the member price
    no_group = [c["name"] for c in get("Customer", fields=["name"], filters=[["customer_group", "is", "not set"]], limit_page_length=0)]
    if no_group:
        print(f"  ⚠ these customers have no customer group and get the member price; give each a group: {no_group}")


def undo():
    mt, it, la = CONF["member_tiers"], CONF["imei_item"], CONF["line_attribute"]
    remove("Promotion Bonus Buys Master", mt["promotion_id"])
    remove("Customer", mt["member_example"], ("disabled", 1))
    for g in mt["groups"]:
        remove("Customer Group", g)
    remove("Transaction Item Attribute", la["name"], ("active", 0))
    if os.path.exists(BEFORE):
        call("PUT", f"{q('Retail Setting')}/Retail%20Setting", json.load(open(BEFORE)))
        os.remove(BEFORE)
        print("  switches put back to their earlier values")
    for r in CONF["reasons"]:
        remove("Reason Code Master", r["id"], ("is_active", 0))
    print("  (the item, its price and its serial numbers are stock records: they stay; a sold IMEI cannot be deleted)")


if __name__ == "__main__":
    print("S5 remove" if "--remove" in sys.argv else "S5 apply")
    undo() if "--remove" in sys.argv else apply()
