"""S42 — a payer's data set: one JSON file in datasets/ per payer, never code (standard library only).

    python3 dataset.py                    # checks every data set in datasets/
    python3 dataset.py records <file>     # prints the shop records a data set makes, in insert order

A data set is a payer, its price list's name (or null), its formularies and its plans. ``check()`` below is the whole
format: a data set it passes loads with no code change (the tests load the generic insurer and a company paying for its
staff through the same function). The shop's records are made with ``records()``; the price list itself and its prices
are the shop's own (a Price List record and Item Prices), never this file's.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import copay  # noqa: E402

PREFIX = os.environ.get("ICP_PREFIX", "PP ICP")
KINDS = ("Insurer", "Corporate account", "Optical plan", "Other")
FORMATS = ("File",)                       # the standard version: claims as a file; each payer's link is a partner's
NEEDS = ("member_number", "card_serial", "gtin", "prescription", "dose_frequency")
PLAN_KEYS = {"title", "formulary", "covers", "price_list", "copay_percent", "invoice_upper_limit",
             "max_patient_amount", "discount_order", "copay_order", "no_partial_refund"}


def load(path: str) -> dict:
    with open(path if os.path.isabs(path) else os.path.join(HERE, path), encoding="utf-8") as f:
        return json.load(f)


def check(ds: dict) -> list[str]:
    """Every way a data set can be wrong, in words."""
    bad = []
    for k in ("id", "title", "notice", "payer", "plans"):
        if not ds.get(k):
            bad.append(f"The data set has no '{k}'.")
    payer = ds.get("payer") or {}
    for k in ("code", "title", "kind", "customer", "claims_format"):
        if not payer.get(k):
            bad.append(f"The payer has no '{k}'.")
    if payer.get("kind") and payer["kind"] not in KINDS:
        bad.append(f"A payer's kind is one of {', '.join(KINDS)}.")
    if payer.get("claims_format") and payer["claims_format"] not in FORMATS:
        bad.append("The standard version files claims as a file; a payer's own link is a partner's app.")
    extra = set(payer.get("claim_needs") or {}) - set(NEEDS)
    if extra:
        bad.append(f"A claim needs only {', '.join(NEEDS)} (not {', '.join(sorted(extra))}).")
    forms = {f.get("title") for f in ds.get("formularies") or []}
    for f in ds.get("formularies") or []:
        if not f.get("title"):
            bad.append("A formulary has no title.")
        bad += copay.check_plan({"formulary": f.get("rows") or []})
    for p in ds.get("plans") or []:
        unknown = set(p) - PLAN_KEYS
        if unknown:
            bad.append(f"Plan {p.get('title')!r} has keys the format does not know: {', '.join(sorted(unknown))}.")
        if not p.get("title"):
            bad.append("A plan has no title.")
        if p.get("formulary") and p["formulary"] not in forms:
            bad.append(f"Plan {p.get('title')!r} names a formulary the data set does not have.")
        if p.get("covers", copay.FORMULARY_ONLY) == copay.FORMULARY_ONLY and not p.get("formulary"):
            bad.append(f"Plan {p.get('title')!r} covers formulary items but names no formulary.")
        if p.get("price_list") and p["price_list"] != ds.get("price_list"):
            bad.append(f"Plan {p.get('title')!r} names a price list other than the data set's.")
        bad += copay.check_plan(p)
    return bad


def records(ds: dict) -> list[dict]:
    """The shop records the data set makes, in insert order (each with its doctype; names are the titles)."""
    payer = ds["payer"]
    out = [{"doctype": f"{PREFIX} Payer", "code": payer["code"], "title": payer["title"], "kind": payer["kind"],
            "customer": payer["customer"], "claims_format": payer["claims_format"], "active": 1,
            **{f"needs_{k}": int((payer.get("claim_needs") or {}).get(k, 0)) for k in NEEDS}}]
    for f in ds.get("formularies") or []:
        out.append({"doctype": f"{PREFIX} Formulary", "title": f["title"], "payer": payer["code"],
                    "rows": [{k: r[k] for k in ("item_code", "item_group", "covered", "extra_pay", "max_qty") if k in r}
                             for r in f.get("rows") or []]})
    for p in ds["plans"]:
        rec = {"doctype": f"{PREFIX} Plan", "payer": payer["code"], "active": 1}
        rec.update({k: v for k, v in p.items() if v is not None})
        out.append(rec)
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "records":
        print(json.dumps(records(load(argv[1])), indent=1))
        return 0
    rc = 0
    for name in sorted(os.listdir(os.path.join(HERE, "datasets"))):
        if name.endswith(".json"):
            bad = check(load(os.path.join("datasets", name)))
            print(f"{name}: {'ok' if not bad else '; '.join(bad)}")
            rc |= bool(bad)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
