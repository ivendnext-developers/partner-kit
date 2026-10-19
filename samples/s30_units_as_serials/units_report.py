#!/usr/bin/env python3
"""S30 — what became of every unit: in stock, defective, sold, counted out, issued (standard library only; read-only).

    PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 units_report.py [--csv units.csv] [--only "counted out"]

A count with *Reconcile All Serial Nos / Batches* takes every unit of the store out and puts the counted ones back in,
so a unit the count did not find reads *Delivered*, the same status as a sold one. This report tells them apart by the
voucher type of the unit's latest outward movement: a Stock Reconciliation is *counted out*, a sale (POS Invoice, Sales
Invoice, Delivery Note) is *sold*. A unit in a Defective store (config.json ``defective_warehouses``) is *defective*.
A till sale moves no stock until its day is closed, so such a unit reads *sold, till day not closed*.

It reads the items of config.json ``items``, or ``--item`` (repeatable). It writes nothing to the shop.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apply_config as C  # noqa: E402
import shop as S  # noqa: E402
import units as U  # noqa: E402

COLUMNS = ["result", "serial", "item", "batch", "warehouse", "status", "voucher_type", "voucher_no"]


def run(shop, items, defective, out=print, csv_path=None, only=None):
    serials = shop.serials_of(items)
    moves = shop.movements([s["name"] for s in serials]) if serials else {}
    rep = U.report(serials, moves, set(defective))
    out(json.dumps(rep["counts"]))
    rows = [r for r in rep["rows"] if not only or r["result"] in only]
    for r in rows:
        out("  " + " · ".join(str(r[c] or "") for c in COLUMNS))
    if csv_path:
        with open(csv_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, COLUMNS)
            w.writeheader()
            w.writerows({c: r[c] for c in COLUMNS} for r in rows)
    return rep


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--item", action="append")
    p.add_argument("--csv")
    p.add_argument("--only", action="append", choices=U.ORDER)
    p.add_argument("--config")
    a = p.parse_args(argv)
    conf = json.load(open(a.config or os.environ.get("PP_CONFIG") or os.path.join(HERE, "config.json")))
    shop = S.Shop.from_env()
    items = a.item or [i["item_code"] for i in conf["items"]]
    defective = C.defective_names(shop, conf)
    run(shop, items, defective, csv_path=a.csv, only=a.only)


if __name__ == "__main__":
    main()
