#!/usr/bin/env python3
"""record_expect.py — fill in each basket's recorded answer from a gate run's own record (never by hand arithmetic).

    python3 record_expect.py baskets.json runs/gate_123.json > baskets.recorded.json

Takes the booked grand total and tax of every basket that MATCHED (its preview equalled its booking) in that run. Re-record only when
a price or tax rule you control changes; a recorded answer you edit by hand is an answer you made up. Standard library only.
"""
import json
import sys


def main(baskets_path, run_path):
    src, run = json.load(open(baskets_path)), json.load(open(run_path))
    rows = run["gate"]
    if len(rows) != len(src["baskets"]):
        sys.exit("the run and the baskets file do not have the same baskets")
    for b, r in zip(src["baskets"], rows):
        if b["name"] != r["name"]:
            sys.exit(f"basket '{b['name']}' is paired with the run's '{r['name']}': the run and the baskets file are not the same")
        if r["state"] != "matched":
            sys.exit(f"basket {r['id']} '{r['name']}' did not match in that run ({r['state']}): record from a clean run")
        b["expect"] = {"grand_total": round(float(r["booked"]["grand_total"]), 2), "tax": round(float(r["booked"]["tax"]), 2)}
    json.dump(src, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main(*sys.argv[1:3])
