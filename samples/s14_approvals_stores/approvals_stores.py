#!/usr/bin/env python3
"""S14 — the outside half of price-change approvals ACROSS STORES. Python 3.9+, standard library only.

Derived from ``samples/s11_approvals/approvals.py`` (this kit, commit daf7943, after its deep review): the history reading, the
apply-once shape, the crash handling and the export are S11's. A defect in those parts is a defect there too: report it on the kit's
board (``ivendnext-developers/partner-kit``).

What S14 adds to S11. A chain has stores and a head office. A request names its STORE; a store manager approves up to a LIMIT (a
percentage of the price now); above it the change waits for head office. The shop's workflow cannot hold a limit (a manifest carries
no condition), and it accepts a state written straight into a request when the writer's roles allow that move (measured: a person given both approving roles), so the service decides:

    BASE=https://shop.example AP_KEY=… AP_SECRET=… python3 approvals_stores.py apply
    BASE=… AP_KEY=… AP_SECRET=… python3 approvals_stores.py export --day 2026-10-04 --out state/export

WHO MAY APPROVE is read from the shop's own table, ``PP APS Approval Rule`` (one row per person: *Store* with a store and a limit, or
*Head Office*). A person with no row, a row that is not whole, or a store row for another store, is not believed — the check fails
closed. APPLY, for each request in *Store Approved* or *Head Office Approved*, oldest first, takes S11's refusals — and adds:
    * a request is not applied if ANY approval in its history was given by the person who raised it (each step, not only the last);
    * *Store Approved*: the approver must hold a Store rule for THIS request's store, and the change (|new − now| ÷ now) must be within
      that rule's limit; above it the request waits, named in the report, for head office;
    * *Head Office Approved*: the approver must hold a Head Office rule — a store manager who writes that state himself is not believed;
    * the request's store is, like its item, price list and price, fixed once raised: a change at any time after is not applied;
    * a STORE approval is valid only while the price row is as the manager saw it: if the price row changed after the approval (an
      earlier request applied, another role's edit) the limit was judged against a price that is gone, so the request is not applied —
      the manager rejects it and it is raised again. This stops a limit being climbed by requests approved side by side. The limit is per
      request, not cumulative: requests approved and applied one after another each move the price by up to the limit (a chain that wants a
      cap per day adds it).
Everything else is S11: the price is written only if it is not already the approved one, the workflow's Apply action moves the request on,
a kill between the two is finished by the next run, a request with ten or more recorded changes is not applied (the shop shows only the
latest ten). EXPORT is S11's, with the store and both approvals as columns.

Bounds: one service per shop (no lock). The rules are read at apply time, both ways: an approver whose rule was removed after approving is
no longer believed, and one whose limit was raised after approving is believed at the new limit. A request names a price list; the service
does not tie the price list to the store, so a store manager's approval moves the price on whatever list the request names — every store's
price where they share one list, another store's own list where the requester named it (a shop with one list per store adds that check).
A head-office approval names the price it wants and is applied whatever the row holds. The limit is read against the price row at apply
time. A request edited between the service's read and its action ends *Applied* showing the edit while the price written is the approved
one (milliseconds; the export marks it *changed_after_raise*). A reject that lands in that window fails the action: the service puts the
price back and says so — within one run; a reject after a run killed between its price and its action is seen by no later run.
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

DT, RULE = "PP APS Price Change Request", "PP APS Approval Rule"
REQUESTED, STORE_OK, HO_OK = "PP APS Requested", "PP APS Store Approved", "PP APS Head Office Approved"
REJECTED, APPLIED = "PP APS Rejected", "PP APS Applied"
APPLY_STATES = (STORE_OK, HO_OK)
ACTION_APPLY = "PP APS Apply"
TRACKED_FIELDS = ("item", "price_list", "new_rate", "store")
SHOP_VERSIONS = 10      # the form-load call returns at most the latest ten versions of a record


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


def load_rules(api):
    """The approval rules, by person. A row that is not whole (a Store row with no store or a limit of 0 or blank, an unknown level, a row whose name is not its person) is left out."""
    rules = {}
    for r in _list(api, RULE, [], ["name", "user", "level", "store", "limit_pct"], order="name asc"):
        if r.get("user") != r["name"]:                       # a row is named by its person; an edited person leaves the old one holding it
            continue
        if r.get("level") == "Head Office" or (r.get("level") == "Store" and r.get("store") and float(r.get("limit_pct") or 0) > 0):
            rules[r["name"]] = r                            # (a blank limit is stored as 0, so a Store row needs a limit above 0)
    return rules


def change_pct(now, new):
    """How far the new price is from the one now, in percent of the one now; a price of nothing (or less) has no percentage (infinite)."""
    now, new = float(now), float(new)
    return 0.0 if now == new else float("inf") if now <= 0 else abs(new - now) / now * 100


def authority(doc, vs, rules, now_rate):
    """Is the approval that put the request in its present state believable? (None = yes, else the sentence why not.)"""
    steps = approvals(vs)
    if not steps:
        return "no version records the approval (change tracking is off or its history was cleared)"
    for i, state, who in steps:
        if who == doc.get("owner"):
            return f"approved by the person who raised it (the {'head office' if state == HO_OK else 'store'} step)"
    _, state, who = [s for s in steps if s[1] == doc["workflow_state"]][-1] if any(s[1] == doc["workflow_state"] for s in steps) else (None, None, None)
    if who is None:
        return "no version records the approval (change tracking is off or its history was cleared)"
    rule = rules.get(who)
    if state == HO_OK:
        if rule is None or rule["level"] != "Head Office":
            return f"{who} gave the head-office approval but is not a head-office approver (no approval rule, or a store rule)"
        return None
    if rule is None:
        return f"{who} approved but there is no approval rule for them (or it is not whole): their approval is not believed"
    if rule["level"] != "Store" or rule["store"] != doc.get("store"):
        return f"{who} is not an approver for store {doc.get('store')!r}"
    pct = change_pct(now_rate, doc["new_rate"])
    if pct > float(rule["limit_pct"]) + 1e-9:
        return f"above the store manager's limit ({rule['limit_pct']}%): the change is {'more than the whole price' if pct == float('inf') else f'{pct:.1f}%'}; it waits for head office"
    return None


def apply_one(api, name, rules, crash_after_write=False):
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
    why = authority(doc, vs, rules, price["price_list_rate"])
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
    if crash_after_write:
        os._exit(3)                                          # test only: after the price, before the action
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


def apply_all(api, crash_after_write=False):
    report = {"applied": [], "not_applied": [], "skipped": []}
    rules = load_rules(api)
    for r in _list(api, DT, [["workflow_state", "in", list(APPLY_STATES)]], ["name"]):
        try:
            res = apply_one(api, r["name"], rules, crash_after_write)
        except F.FeedError as e:                              # the shop refused: say so, go on with the next
            res = {"request": r["name"], "result": "not applied", "why": f"the shop said: {str(e)[:200]}"}
        report["applied" if res["result"] == "applied" else "not_applied" if res["result"] == "not applied" else "skipped"].append(res)
    return report


def _cell(v):
    """A spreadsheet runs a cell that starts with = + - @ (a requester writes the reason freely): the file shows it as text."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


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
            w.writerow([_cell(r.get(k, "")) for k in fields] + [_cell(who[STORE_OK]), _cell(who[HO_OK]), _cell(who[APPLIED]), _cell(who[REJECTED]), "yes" if tracked_changes(vs) else ""])
    return {"path": path, "requests": len(seen)}


def main(argv=None):
    p = argparse.ArgumentParser(description="S14 price-change approvals across stores: apply the approved ones, export the day's")
    p.add_argument("command", choices=("apply", "export"))
    p.add_argument("--base", default=os.environ.get("BASE"))
    p.add_argument("--day")
    p.add_argument("--out", default="state/export")
    p.add_argument("--crash-after-write", action="store_true", help="test only: die after the price, before the workflow action")
    a = p.parse_args(argv)
    api = F.Api(a.base, os.environ["AP_KEY"], os.environ["AP_SECRET"])
    print(json.dumps(apply_all(api, a.crash_after_write) if a.command == "apply" else export_day(api, a.day, a.out)))


if __name__ == "__main__":
    main()
