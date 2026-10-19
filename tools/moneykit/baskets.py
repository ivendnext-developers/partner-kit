"""The money kit's basket set — PURE (no framework import): built on the laptop or inside the bench the same way.

Two shared sources, each named, neither copied — both OPTIONAL in the kit (its steps golden:<file> and seeder:<file>):
- the GOLDEN baskets — ivendnext/iVendNext_PWA · ``GOLDEN_REL`` below, the file the POS app's own offline tests use, read in
  place wherever the kit's step golden:<file> names it (on our test bench: the app's pinned clone, 05bb4dab…). Their items
  (WIDGET, UN-A, …) are made up for the offline mirror's own snapshots, so each is MAPPED to a real shop item (``POOL``);
  what a basket keeps is its SHAPE — lines, quantities, markdowns, a sale discount. A basket the shop cannot express is
  SKIPPED with its reason.
- the PROMOTION fixtures — one basket per fixture (``PROMO_BASKETS``: the basket each fixture's expectation says to ring),
  seeded by the seeder the step seeder:<file> names, rung with only that fixture switched on.
⚠ ``POOL`` and ``PROMO_BASKETS`` name our test shop's catalogue (a demo phone-and-accessories store): on your own shop,
give no golden file and no seeder, and ring your OWN recorded baskets (recorded:<file>, or the release gate's baskets file).
Identical baskets after mapping are kept once. Every count is reported.
"""
from __future__ import annotations

import json

GOLDEN_REL = "apps/ivendnext_mpos/js_tests/fixtures/offline_tax_parity_golden.json"
# the golden items, in sorted order, map round-robin onto these shop items (each priced, stocked, not serialised)
POOL = ["CABLE-USBC-1M", "CASE-LEATHER", "MAGSAFE-CHARGER", "CASE-SILICONE-MAGSAFE", "AIRPODS-3", "AIRPODS-PRO-2"]

W41, W41C, W45, W45C = ("Apple Watch Series 9-41MM-GPS", "Apple Watch Series 9-41MM-GPSC",
                        "Apple Watch Series 9-45MM-GPS", "Apple Watch Series 9-45MM-GPSC")
MAC, IPHONE, IPAD = "MacBook Air (M3)-MID-8GB-256", "iPhone 15-BLU-128", "iPad (10th gen)-64-WIFI"
POD3, PODPRO, CABLE, CASE = "AIRPODS-3", "AIRPODS-PRO-2", "CABLE-USBC-1M", "CASE-LEATHER"

# fixture -> the basket its expectation row says to ring (items translated to this shop's catalogue where the row
# names a group); a fixture the seeder SKIPS on this shop (its items absent) is skipped here too
PROMO_BASKETS = {
    "UC-003-ITEM-PCT": [(POD3, 1)],
    "UC-004-ITEM-DATED": [(PODPRO, 1)],
    "UC-005-ITEM-VOLUME": [(POD3, 2)],
    "UC-006-TXN-TOTAL": [(PODPRO, 1)],
    "UC-007-TXN-QTY": [(CABLE, 5)],
    "UC-008-BUYX-PRICEOFY": [(PODPRO, 2)],
    "UC-009-B1G1F": [(POD3, 2)],
    "UC-010-BILLVAL-FREEITEM": [(W41, 1), (CABLE, 1)],
    "UC-011-BILLVAL-BILLDISC": [(W45, 1)],
    "UC-012-GROUP-N-PCT": [(W41, 2)],
    "UC-013-SAMEGROUP-FREE": [(PODPRO, 1), (POD3, 1)],
    "UC-014-XGROUP-FREE": [(MAC, 1), (POD3, 1)],
    "UC-015-LOWEST-VALUE": [(W41, 1), (W45C, 1)],
    "UC-016-XGROUP-PCT": [(IPHONE, 1), (IPAD, 1)],
    "UC-017-GET-GIFTCARD": [(PODPRO, 1)],
    "UC-019-GET-COUPON": [(POD3, 1)],
    "UC-020-GROUP-A-OR-B": [(MAC, 2)],
    "UC-020B-GROUP-A-AND-B": [(MAC, 1), (POD3, 1), (W41, 1)],
    "UC-021-GIFTCARD-HALF": [(POD3, 1), (PODPRO, 1)],
    "UC-022-GETY-FIXED": [(POD3, 1), (CASE, 1)],
    "UC-023-BUYN-FIXED": [(POD3, 3)],
    "UC-024-GROUP-N-FIXED": [(W41, 1), (W41C, 1), (POD3, 1)],
    "UC-B06-AMOUNT-SALE": [(CASE, 1)],
    "UC-B09-ANNIVERSARY": [("CASE-SILICONE-MAGSAFE", 1)],
    "UC-B15-AMOUNT-SPLIT": [(CABLE, 1), ("MAGSAFE-CHARGER", 3)],
}


def _key(b: dict) -> str:
    return json.dumps([b["lines"], b.get("sale_discount"), b.get("promo")], sort_keys=True)


def golden_baskets(golden: dict) -> tuple[list[dict], list[dict]]:
    fixtures = golden.get("fixtures") or []
    codes = sorted({ln["item_code"] for f in fixtures for ln in f.get("lines") or []})
    mapping = {c: POOL[i % len(POOL)] for i, c in enumerate(codes)}
    out, skipped, seen = [], [], set()
    for f in fixtures:
        lines, why = f.get("lines") or [], None
        if f.get("refuses"):
            why = "built to be refused by the offline mirror"
        elif any(ln.get("cross_sell_parent") for ln in lines):
            why = "a cross-sell companion line (no cross-sell offer is set up on this shop)"
        elif (f.get("opts") or {}).get("customer"):
            why = "a named test customer this shop does not carry"
        elif any((ln.get("uom") or "Nos") != "Nos" for ln in lines):
            why = "a pack unit this shop's items do not carry"
        if why:
            skipped.append({"source": "golden", "name": f["name"], "why": why})
            continue
        b = {"source": "golden", "name": f["name"], "promo": None,
             "lines": [[mapping[ln["item_code"]], ln["qty"], (ln.get("markdown") or {}).get("pct")] for ln in lines],
             "sale_discount": (f.get("opts") or {}).get("sale_discount")}
        if _key(b) in seen:
            skipped.append({"source": "golden", "name": f["name"], "why": "the same basket as one already kept, once "
                                                                          "its items are mapped"})
            continue
        seen.add(_key(b))
        out.append(b)
    return out, skipped


def promo_baskets(seeded: set[str]) -> tuple[list[dict], list[dict]]:
    out, skipped = [], []
    for uc, lines in PROMO_BASKETS.items():
        if uc not in seeded:
            skipped.append({"source": "promotion", "name": uc, "why": "the seeder did not create it on this shop"})
            continue
        out.append({"source": "promotion", "name": uc, "promo": uc, "lines": [[c, q, None] for c, q in lines],
                    "sale_discount": None})
    return out, skipped


def recorded_baskets(recorded: dict | None) -> list[dict]:
    """A partner's own baskets with the answers they expect (the shape of the release gate's ``baskets.json``)."""
    out = []
    for r in (recorded or {}).get("baskets") or []:
        out.append({"source": "recorded", "name": r["name"], "promo": None, "lines": r["lines"],
                    "sale_discount": r.get("sale_discount"), "expect": r.get("expect")})
    return out


def basket_set(golden: dict, seeded: set[str], recorded: dict | None = None) -> dict:
    g, gs = golden_baskets(golden)
    p, ps = promo_baskets(seeded)
    r = recorded_baskets(recorded)
    for i, b in enumerate(g + p + r):   # recorded baskets come last, so the shared set keeps its ids
        b["id"] = f"B{i + 1:03d}"
    return {"baskets": g + p + r, "skipped": gs + ps,
            "counts": {"golden_in_file": len(golden.get("fixtures") or []), "golden_used": len(g),
                       "promotion_fixtures": len(PROMO_BASKETS), "promotion_used": len(p),
                       "recorded": len(r), "skipped": len(gs) + len(ps)}}


def items_used(baskets: list[dict]) -> dict[str, float]:
    """item -> the most units one run asks for (a stock top-up covers a whole run)."""
    need: dict[str, float] = {}
    for b in baskets:
        for code, qty, _ in b["lines"]:
            need[code] = need.get(code, 0) + float(qty)
    return need
