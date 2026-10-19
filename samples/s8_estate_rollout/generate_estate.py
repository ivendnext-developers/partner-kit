#!/usr/bin/env python3
"""Writes ``estate.json`` — an estate of regions and stores as one file (S8). Standard library only.

    python3 generate_estate.py --stores 51 > estate.json

The file is the whole truth about the estate: a real customer keeps it in their own repository and edits it by hand. This
generator exists only so the sample (and its tests) can hold 50+ stores without a person typing them. The shop-specific
names (company, reference profile, items, print formats) are the sandbox template's; change them for another shop.
"""

import argparse
import json

REGIONS = [("N", "North", 1.00), ("S", "South", 0.97), ("W", "West", 1.03)]
FORMATS = ["mPOS Receipt", 'Print Format Receipt 3"']


def build(stores: int) -> dict:
    est = {
        "_what": "S8: an estate as code. Regions carry a price list, prices and one promotion; each store gets a warehouse, a till "
                 "profile (cloned from the reference profile), a receipt format and a cashier; each region has a manager.",
        "company": "Demo Retail", "abbr": "DR", "parent_warehouse": "All Warehouses - DR",
        "reference_profile": "Store 1 — R1", "currency": "USD", "prefix": "PP EST",
        "promotion_prefix": "PP-EST-", "user_prefix": "pp-est-",       # what orphan detection and remove look for, besides `prefix`
        # a till's outlet defaults live on its WAREHOUSE (measured at beta's pin): the engine refuses a profile whose warehouse has no
        # price list, and the till refuses an outlet with no cash customer. The reference store's own values:
        "warehouse_defaults": {"custom_cash_customer": "Walk-in — Demo Retail", "custom_item_tax_template": "United States Sales Tax - DR",
                               "custom_company_currency": "USD"},
        "settings": {"Retail Setting": {"reason_sale_discount": 1}},
        "reasons": [{"id": "PP EST Sale Discount", "type": "Sale Discount"}],
        "items": {"CABLE-USBC-1M": 15.0, "CASE-PHONE": 29.0, "EARBUDS": 129.0},
        "roles": {"store": ["Retail Cashier"], "region": ["Retail Manager"]},
        "regions": [], "stores": [],
    }
    for code, name, factor in REGIONS:
        est["regions"].append({
            "code": code, "name": name, "price_list": f"PP EST {name}",
            "prices": {k: round(v * factor, 2) for k, v in est["items"].items()},
            "promotion": {"id": f"PP-EST-{code}", "description": f"10% off the sale in {name} stores", "discount_percent": 10},
            "manager": f"pp-est-mgr-{code.lower()}@demo-retail.example"})
    for i in range(stores):
        code, _n, _f = REGIONS[i % len(REGIONS)]
        n = i // len(REGIONS) + 1
        est["stores"].append({"code": f"{code}{n:03d}", "region": code, "print_format": FORMATS[(i // 2) % len(FORMATS)],
                              "cashier": f"pp-est-{code.lower()}{n:03d}@demo-retail.example"})
    return est


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", type=int, default=51)
    print(json.dumps(build(ap.parse_args().stores), indent=1))
