#!/usr/bin/env python3
"""S14 — the outside half of price-change approvals ACROSS STORES. Python 3.9+, standard library only.

A chain has stores and a head office. A request names its STORE; a store manager approves up to a LIMIT (a percentage of the price
now); above it the change waits for head office.

    BASE=https://shop.example AP_KEY=… AP_SECRET=… LIMIT_PCT=10 python3 approvals_stores.py apply
    BASE=… AP_KEY=… AP_SECRET=… python3 approvals_stores.py export --day 2026-10-04 --out state/export

WHO MAY APPROVE is the shop's own: the workflow's roles, and one User Permission per person on their store, so a manager of another
store cannot open the request. The limit is one number for the chain, ``LIMIT_PCT`` (10 when unset). APPLY, for each request in
*Store Approved* or *Head Office Approved*, oldest first:
    * a request is not applied if any approval in its history was given by the person who raised it;
    * *Store Approved*: the change (|new − now| ÷ now) must be within the limit; above it the request waits, named in the report, for
      head office;
    * the request's item, price list, price and store are fixed once raised: a change after that is not applied;
    * a STORE approval holds only while the price row is as the manager saw it: if the row changed after the approval, the limit was
      judged against a price that is gone, so the request is not applied: the manager rejects it and it is raised again.
The price is written only if it is not already the approved one, the workflow's Apply action moves the request, and a kill between
the two is finished by the next run. A request with ten or more recorded changes is not applied (the shop shows only the latest ten).
EXPORT writes the day's requests, with the store and both approvals as columns, the same bytes for the same data.

Bounds: one service per shop (no lock). A request names a price list; a store manager's approval moves the price on whatever list it
names (a chain with one list per store adds that check).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import feed_client as F  # noqa: E402

DT = "PP APS Price Change Request"
REQUESTED, STORE_OK, HO_OK = "PP APS Requested", "PP APS Store Approved", "PP APS Head Office Approved"
REJECTED, APPLIED = "PP APS Rejected", "PP APS Applied"
APPLY_STATES = (STORE_OK, HO_OK)
ACTION_APPLY = "PP APS Apply"
TRACKED_FIELDS = ("item", "price_list", "new_rate", "store")
SHOP_VERSIONS = 10      # the form-load call returns at most the latest ten versions of a record
LIMIT_PCT = 10.0        # a store manager's limit, a percentage of the price now, unless LIMIT_PCT is set


def _q(s):
    return urllib.parse.quote(s, safe="")


def _list(api, dt, filters, fields, order="creation asc"):
    r = api.call("GET", f"/api/resource/{_q(dt)}", {"filters": json.dumps(filters), "fields": json.dumps(fields),
                                                   "order_by": order, "limit_page_length": 0})
    return r["data"]


def versions(api, name):
    """The request's change history, oldest first: (when, who, changed [[field, old, new], …]).

    Read through the form-load call (``get_docinfo``), which checks the key's right on THE REQUEST — so the key needs no right on the
    shop's change-history records. The shop returns at most the latest 10 versions, so a request with ten or more is not applied."""
    r = api.call("GET", "/api/method/ivendnext_mpos.api.v1.get_docinfo", {"doctype": DT, "name": name})
    vs = sorted(r["docinfo"]["versions"], key=lambda v: (v["creation"], v["name"]))
    return [(v["creation"], v["owner"], (json.loads(v["data"] or "{}").get("changed") or [])) for v in vs]


def approvals(vs):
    """Every approval in the history, oldest first: (index, state reached, who)."""
    return [(i, c[2], who) for i, (_, who, changed) in enumerate(vs) for c in changed if c[0] == "workflow_state" and c[2] in APPLY_STATES]


def tracked_changes(vs):
    """Every change of the item, price list, price or store since the request was raised, by anyone (a request is raised whole)."""
    return [f"{c[0]}: {c[1]!r} -> {c[2]!r} by {who}" for _, who, changed in vs for c in changed if c[0] in TRACKED_FIELDS]


def change_pct(now, new):
    """How far the new price is from the one now, in percent of the one now; a price of nothing (or less) has no percentage (infinite)."""
    now, new = float(now), float(new)
    return 0.0 if now == new else float("inf") if now <= 0 else abs(new - now) / now * 100


def authority(doc, vs, limit_pct, now_rate):
    """Does the approval that put the request in its present state hold? (None = yes, else the sentence why not.)"""
    steps = approvals(vs)
    if not steps:
        return "no version records the approval (change tracking is off or its history was cleared)"
    for i, state, who in steps:
        if who == doc.get("owner"):
            return f"approved by the person who raised it (the {'head office' if state == HO_OK else 'store'} step)"
    if doc["workflow_state"] == STORE_OK:
        pct = change_pct(now_rate, doc["new_rate"])
        if pct > limit_pct + 1e-9:
            changed = "more than the whole price" if pct == float("inf") else f"{pct:.1f}%"
            return f"above the store manager's limit ({limit_pct}%): the change is {changed}; it waits for head office"
    return None


def apply_one(api, name, limit_pct):
    doc = api.call("GET", f"/api/resource/{_q(DT)}/{_q(name)}")["data"]
    if doc.get("workflow_state") not in APPLY_STATES:
        return {"request": name, "result": "skipped", "why": f"state is {doc.get('workflow_state')}"}
    vs = versions(api, name)
    if len(vs) >= SHOP_VERSIONS:
        return {"request": name, "result": "not applied", "why": f"{SHOP_VERSIONS} or more recorded changes: the shop shows only the latest {SHOP_VERSIONS}, so its history cannot be checked"}
    changed = tracked_changes(vs)
    if changed:
        return {"request": name, "result": "not applied", "why": "changed after it was raised", "changes": changed}
    rows = _list(api, "Item Price", [["item_code", "=", doc["item"]], ["price_list", "=", doc["price_list"]], ["selling", "=", 1]],
                 ["name", "price_list_rate", "modified"])
    if len(rows) != 1:
        return {"request": name, "result": "not applied", "why": f"{len(rows)} selling price rows for {doc['item']} in {doc['price_list']}"}
    price, wrote = rows[0], False
    why = authority(doc, vs, limit_pct, price["price_list_rate"])
    if why:
        return {"request": name, "result": "not applied", "why": why}
    if doc["workflow_state"] == STORE_OK and abs(float(price["price_list_rate"]) - float(doc["new_rate"])) > 0.0001:
        seen = [vs[i][0] for i, st, _ in approvals(vs) if st == STORE_OK][-1]
        if str(price.get("modified") or "") > str(seen):
            return {"request": name, "result": "not applied", "why": "the price changed after the store manager approved (the limit was judged against the price they saw): "
                                                                     "reject it and raise it again"}
    if abs(float(price["price_list_rate"]) - float(doc["new_rate"])) > 0.0001:
        api.call("PUT", f"/api/resource/Item%20Price/{_q(price['name'])}", body={"price_list_rate": float(doc["new_rate"])})
        wrote = True
    try:
        api.call("POST", "/api/method/ivendnext_mpos.api.v1.apply_workflow", body={"doc": json.dumps(doc), "action": ACTION_APPLY})
    except F.FeedError as e:      # the price may already be live: say so, the next run finishes the action without writing it again
        if wrote and api.call("GET", f"/api/resource/{_q(DT)}/{_q(name)}")["data"].get("workflow_state") not in APPLY_STATES + (APPLIED,):
            api.call("PUT", f"/api/resource/Item%20Price/{_q(price['name'])}", body={"price_list_rate": float(price["price_list_rate"])})
            return {"request": name, "result": "not applied", "wrote_price": False, "price_row": price["name"],      # a reject landed between our read and our action
                    "why": f"rejected while it was being applied: the price was put back to {price['price_list_rate']}"}
        return {"request": name, "result": "not applied", "wrote_price": wrote, "price_row": price["name"],
                "why": f"{'THE PRICE IS ALREADY WRITTEN' if wrote or float(price['price_list_rate']) == float(doc['new_rate']) else 'the price is unchanged'}"
                       f" but the workflow action failed ({str(e)[:160]}); the next run takes the action if the request is still approved — if it was rejected meanwhile, put the price back by hand"}
    return {"request": name, "result": "applied", "price_row": price["name"], "wrote_price": wrote}


def setting_limit():
    """The chain's limit from LIMIT_PCT, or the default when it is unset or not a positive number."""
    try:
        v = float(os.environ.get("LIMIT_PCT") or LIMIT_PCT)
    except ValueError:
        return LIMIT_PCT
    return v if v > 0 else LIMIT_PCT


def apply_all(api, limit_pct=None):
    report = {"applied": [], "not_applied": [], "skipped": []}
    limit_pct = setting_limit() if limit_pct is None else limit_pct
    for r in _list(api, DT, [["workflow_state", "in", list(APPLY_STATES)]], ["name"]):
        try:
            res = apply_one(api, r["name"], limit_pct)
        except F.FeedError as e:                              # the shop refused: say so, go on with the next
            res = {"request": r["name"], "result": "not applied", "why": f"the shop said: {getattr(e, 'detail', str(e))[:200]}"}
        report["applied" if res["result"] == "applied" else "not_applied" if res["result"] == "not applied" else "skipped"].append(res)
    return report


def export_day(api, day, out_dir):
    """One CSV for the day, sorted by name — identical bytes for identical data. *changed_after_raise* is "yes" where the item, price list, price or
    store was changed after the request was raised (the columns show the request as it is now; the history holds the rest). The approvers are
    read from the same ten-version window as APPLY: a request with more than ten recorded changes may show blank names (the shop's own history
    keeps them all)."""
    fields = ["name", "item", "price_list", "new_rate", "store", "reason", "workflow_state", "owner", "creation", "modified"]
    seen, nxt = {}, (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    for flt in ([["creation", ">=", f"{day} 00:00:00"], ["creation", "<", f"{nxt} 00:00:00"]],       # to the very end of the day, fractions included
                [["modified", ">=", f"{day} 00:00:00"], ["modified", "<", f"{nxt} 00:00:00"]]):
        for r in _list(api, DT, flt, fields):
            seen[r["name"]] = r
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"approvals_{day}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields + ["store_approved_by", "head_office_approved_by", "applied_by", "rejected_by", "changed_after_raise"])
        for name in sorted(seen):
            r, who = seen[name], {STORE_OK: "", HO_OK: "", APPLIED: "", REJECTED: ""}
            vs = versions(api, name)
            for _, owner, changed in vs:
                for c in changed:
                    if c[0] == "workflow_state" and c[2] in who:
                        who[c[2]] = owner
            w.writerow([r.get(k, "") for k in fields] + [who[STORE_OK], who[HO_OK], who[APPLIED], who[REJECTED], "yes" if tracked_changes(vs) else ""])
    return {"path": path, "requests": len(seen)}


def main(argv=None):
    p = argparse.ArgumentParser(description="S14 price-change approvals across stores: apply the approved ones, export the day's")
    p.add_argument("command", choices=("apply", "export"))
    p.add_argument("--base", default=os.environ.get("BASE"))
    p.add_argument("--day")
    p.add_argument("--out", default="state/export")
    a = p.parse_args(argv)
    api = F.Api(a.base, os.environ["AP_KEY"], os.environ["AP_SECRET"])
    print(json.dumps(apply_all(api) if a.command == "apply" else export_day(api, a.day, a.out)))


if __name__ == "__main__":
    main()
