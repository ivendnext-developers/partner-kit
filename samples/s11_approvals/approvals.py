#!/usr/bin/env python3
"""S11 — the outside half of price-change approvals. Python 3.9+, standard library only.

The shop holds the requests and the workflow (``manifest.json``: Requested -> Approved -> Applied, by role). This service does the
two things the manifest cannot, over the record API and with its OWN key (a narrow role):

    BASE=https://shop.example AP_KEY=… AP_SECRET=… python3 approvals.py apply
    BASE=… AP_KEY=… AP_SECRET=… python3 approvals.py export --day 2026-10-04 --out state/export

APPLY   for each request in state Approved, oldest first: change the price row to the approved rate, then take the workflow's
        Apply action (which moves it to Applied). Safe to run twice and to kill at any moment:
          * the price is written only if it is not already the approved rate, so a rerun after a crash between the two steps
            finds the price done and only takes the action;
          * a request in Applied has no further action, so it can never be applied twice;
          * a request whose item, price list or new price was CHANGED at any time after it was raised — by the requester, by the
            approver before approving, or by anyone after — is NOT applied (the change tracking the manifest turns on is read:
            ``Version`` records); it is named in the report, and the approver rejects it so a fresh one is raised;
          * a request approved by the person recorded as having raised it is NOT applied;
          * a request with ten or more recorded changes is NOT applied: the shop shows only the latest ten, so its whole history
            cannot be checked.
        A request with no matching selling price row is not applied either; the report names it.
EXPORT  the day's requests (any request created or last changed on that day) as one CSV, with who made, approved and applied
        each — the same bytes every time for the same data. Run it just AFTER midnight for the day that ended.

Bounds: one service per shop (it takes no lock); "the day's requests" means created or last changed on that day, IN THE SHOP'S
TIME ZONE, so a request changed again on a later day is no longer in that day's file if the export is run late. Who raised a
request is the record's ``owner``, which the shop sets once and refuses to change (measured), so "approved by the person who
raised it" is a firm refusal. The export shows each request as it is NOW (an edit after it was applied shows), with
the approver read from the same ten-version history (blank when that is longer).
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

DT = "PP APR Price Change Request"
APPROVED, APPLIED, REJECTED, REQUESTED = "PP APR Approved", "PP APR Applied", "PP APR Rejected", "PP APR Requested"
ACTION_APPLY = "PP APR Apply"
ACTION_REJECT = "PP APR Reject"
MONEY_FIELDS = ("item", "price_list", "new_rate")
SHOP_VERSIONS = 10      # the form-load call returns at most the latest ten versions of a record


def _q(s):
    return urllib.parse.quote(s, safe="")


def _list(api, dt, filters, fields, order="creation asc"):
    r = api.call("GET", f"/api/resource/{_q(dt)}", {"filters": json.dumps(filters), "fields": json.dumps(fields),
                                                   "order_by": order, "limit_page_length": 0})
    return r["data"]


def versions(api, name):
    """The request's change history, oldest first: (when, who, changed [[field, old, new], …]).

    Read through the form-load call (``get_docinfo``), which checks the key's right on THE REQUEST — so the key needs no right on
    the shop's change-history records at all (those hold other record types' old and new values too). The shop returns at most the
    latest 10 versions, so a request with ten or more is not applied (apply_one)."""
    r = api.call("GET", "/api/method/ivendnext_mpos.api.v1.get_docinfo", {"doctype": DT, "name": name})
    vs = sorted(r["docinfo"]["versions"], key=lambda v: (v["creation"], v["name"]))
    return [(v["creation"], v["owner"], (json.loads(v["data"] or "{}").get("changed") or [])) for v in vs]


def approved_at(vs):
    """Index of the version that made the request Approved (the last one that did), or None."""
    idx = None
    for i, (_, _, changed) in enumerate(vs):
        if any(c[0] == "workflow_state" and c[2] == APPROVED for c in changed):
            idx = i
    return idx


def money_changes(vs):
    """Every change of the item, price list or price since the request was raised, by anyone (a request is raised whole)."""
    return [f"{c[0]}: {c[1]!r} -> {c[2]!r} by {who}" for _, who, changed in vs for c in changed if c[0] in MONEY_FIELDS]


def apply_one(api, name, crash_after_write=False):
    doc = api.call("GET", f"/api/resource/{_q(DT)}/{_q(name)}")["data"]
    if doc.get("workflow_state") != APPROVED:
        return {"request": name, "result": "skipped", "why": f"state is {doc.get('workflow_state')}"}
    vs = versions(api, name)
    if len(vs) >= SHOP_VERSIONS:
        return {"request": name, "result": "not applied", "why": f"{SHOP_VERSIONS} or more recorded changes: the shop shows only the latest {SHOP_VERSIONS}, so its history cannot be checked"}
    i = approved_at(vs)
    if i is None:
        return {"request": name, "result": "not applied", "why": "no version records the approval (change tracking is off or its history was cleared)"}
    if vs[i][1] == doc.get("owner"):
        return {"request": name, "result": "not applied", "why": "approved by the person who raised it"}
    changed = money_changes(vs)
    if changed:
        return {"request": name, "result": "not applied", "why": "changed after it was raised", "changes": changed}
    rows = _list(api, "Item Price", [["item_code", "=", doc["item"]], ["price_list", "=", doc["price_list"]], ["selling", "=", 1]],
                 ["name", "price_list_rate"])
    if len(rows) != 1:
        return {"request": name, "result": "not applied", "why": f"{len(rows)} selling price rows for {doc['item']} in {doc['price_list']}"}
    price, wrote = rows[0], False
    if abs(float(price["price_list_rate"]) - float(doc["new_rate"])) > 0.0001:
        api.call("PUT", f"/api/resource/Item%20Price/{_q(price['name'])}", body={"price_list_rate": float(doc["new_rate"])})
        wrote = True
    if crash_after_write:
        os._exit(3)                                          # test only: after the price, before the action
    try:
        api.call("POST", "/api/method/ivendnext_mpos.api.v1.apply_workflow", body={"doc": json.dumps(doc), "action": ACTION_APPLY})
    except F.FeedError as e:      # the price may already be live: say so, the next run finishes the action without writing it again
        return {"request": name, "result": "not applied", "wrote_price": wrote, "price_row": price["name"],
                "why": f"{'THE PRICE IS ALREADY WRITTEN' if wrote or float(price['price_list_rate']) == float(doc['new_rate']) else 'the price is unchanged'}"
                       f" but the workflow action failed ({str(e)[:160]}); the next run takes the action"}
    return {"request": name, "result": "applied", "price_row": price["name"], "wrote_price": wrote}


def apply_all(api, crash_after_write=False):
    report = {"applied": [], "not_applied": [], "skipped": []}
    for r in _list(api, DT, [["workflow_state", "=", APPROVED]], ["name"]):
        try:
            res = apply_one(api, r["name"], crash_after_write)
        except F.FeedError as e:                              # the shop refused: say so, go on with the next
            res = {"request": r["name"], "result": "not applied", "why": f"the shop said: {str(e)[:200]}"}
        report["applied" if res["result"] == "applied" else "not_applied" if res["result"] == "not applied" else "skipped"].append(res)
    return report


def reject(api, name, reason, presser, min_length=5):
    """A reason asked before a request is rejected (recipes/desk_action.md, *A reason asked before a document is
    rejected*). The press of a Desk action *Reject with reason* calls this with the dialog's required input and the
    pressing user from the press's context. It writes the reason and who pressed into the request's own fields, THEN
    takes the workflow's Reject (the workflow call reads the saved request again, so a reason sent with it would be
    dropped). If the shop refuses the transition (the service's role may not take it), the two fields are put back and
    the user is told. Safe to press twice: a request already rejected is answered, not rejected again."""
    reason = (reason or "").strip()
    if len(reason) < min_length:
        return {"message": {"title": "A reason is needed", "body": f"Write why it is rejected (at least {min_length} characters).",
                            "level": "warning"}}
    doc = api.call("GET", f"/api/resource/{_q(DT)}/{_q(name)}")["data"]
    if doc.get("workflow_state") == REJECTED:
        return {"message": {"title": "Already rejected", "body": f"{name} was rejected: {doc.get('rejection_reason') or ''}"[:280],
                            "level": "info"}, "refresh": True}
    if doc.get("workflow_state") not in (REQUESTED, APPROVED):
        return {"message": {"title": "Cannot be rejected", "body": f"{name} is {doc.get('workflow_state')}.", "level": "warning"}}
    was = {"rejection_reason": doc.get("rejection_reason"), "rejected_by": doc.get("rejected_by")}
    if was != {"rejection_reason": reason, "rejected_by": presser}:
        api.call("PUT", f"/api/resource/{_q(DT)}/{_q(name)}", body={"rejection_reason": reason, "rejected_by": presser})
        doc.update(rejection_reason=reason, rejected_by=presser)
    try:
        api.call("POST", "/api/method/ivendnext_mpos.api.v1.apply_workflow", body={"doc": json.dumps(doc), "action": ACTION_REJECT})
    except F.FeedError as e:
        # a timeout can hide a reject that went through: read the request again, and put the fields back only if it was not
        if api.call("GET", f"/api/resource/{_q(DT)}/{_q(name)}")["data"].get("workflow_state") == REJECTED:
            return {"message": {"title": "Rejected", "body": f"{name} is rejected. The reason is kept on it.", "level": "success"},
                    "refresh": True}
        api.call("PUT", f"/api/resource/{_q(DT)}/{_q(name)}", body=was)
        return {"message": {"title": "Not rejected", "body": f"The shop refused the reject: {e}"[:280], "level": "warning"}}
    return {"message": {"title": "Rejected", "body": f"{name} is rejected. The reason is kept on it.", "level": "success"},
            "refresh": True}


def _cell(v):
    """A spreadsheet runs a cell that starts with = + - @ (a requester writes the reason freely): the file shows it as text."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def export_day(api, day, out_dir):
    """One CSV for the day, sorted by name — identical bytes for identical data. *changed_after_raise* is "yes" where the item, price list or
    price was changed after the request was raised, and "unknown" where the shop's history is cut at its latest ten versions (the columns show the request as it is now; the history holds the rest)."""
    fields = ["name", "item", "price_list", "new_rate", "reason", "workflow_state", "owner", "creation", "modified"]
    seen, nxt = {}, (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    for flt in ([["creation", ">=", f"{day} 00:00:00"], ["creation", "<", f"{nxt} 00:00:00"]],       # to the very end of the day, fractions included
                [["modified", ">=", f"{day} 00:00:00"], ["modified", "<", f"{nxt} 00:00:00"]]):
        for r in _list(api, DT, flt, fields):
            seen[r["name"]] = r
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"approvals_{day}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields + ["approved_by", "applied_by", "changed_after_raise"])
        for name in sorted(seen):
            r, who = seen[name], {"approved_by": "", "applied_by": ""}
            vs = versions(api, name)
            for _, owner, changed in vs:
                for c in changed:
                    if c[0] == "workflow_state" and c[2] == APPROVED:
                        who["approved_by"] = owner
                    if c[0] == "workflow_state" and c[2] == APPLIED:
                        who["applied_by"] = owner
            w.writerow([_cell(r.get(k, "")) for k in fields] + [_cell(who["approved_by"]), _cell(who["applied_by"]), "yes" if money_changes(vs) else ("unknown" if len(vs) >= SHOP_VERSIONS else "")])
    return {"path": path, "requests": len(seen)}


def main(argv=None):
    p = argparse.ArgumentParser(description="S11 price-change approvals: apply the approved ones, export the day's")
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
