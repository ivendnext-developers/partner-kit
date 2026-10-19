"""S22 — check-by-workflow: a back-office check that BLOCKS a document, with no code in the shop.

The shop's Purchase Receipt workflow (``apply_config.py``) books a receipt only at *PP LYL Verified*, a step only your
service's role may take, after its own check; a manager-held *PP LYL Override* also books it; every other role loses the
right to submit a receipt (a workflow alone does not stop a submit through the API: such a submit lands in the first
submitted state, which is why *Overridden* is listed before *Verified*).

The check here is a generic one: no receipt row receives more than its purchase order still waits for. Your own check
goes in ``problems`` (a count of unit codes, a quality sign-off, an ASN match). The service then takes the *Verify*
action itself; when the check fails it leaves the receipt where it is and comments why. Acting once: a receipt already
past *Pending Verification* is left alone, so a replayed event changes nothing.
"""

from __future__ import annotations

import json

import money

DT = "Purchase Receipt"
PENDING, VERIFIED, VERIFY = "PP LYL Pending Verification", "PP LYL Verified", "PP LYL Verify"


def problems(t, pr: dict) -> list[str]:
    out, orders = [], {}
    for r in pr.get("items") or []:
        po, line = r.get("purchase_order"), r.get("purchase_order_item")
        if not po or not line:
            out.append(f"Row {r.get('idx')}: {r.get('item_code')} is not on a purchase order.")
            continue
        if po not in orders:
            orders[po] = {i["name"]: i for i in (t.get("Purchase Order", po) or {}).get("items") or []}
        ordered = orders[po].get(line)
        if not ordered:
            out.append(f"Row {r.get('idx')}: its purchase order line {line} is gone.")
            continue
        waiting = money.D(ordered.get("qty")) - money.D(ordered.get("received_qty"))
        if money.D(r.get("qty")) > waiting:
            out.append(f"Row {r.get('idx')}: {r.get('item_code')} receives {money.D(r.get('qty')):g} but {po} "
                       f"waits for {waiting:g}.")
    return out


def on_receipt(t, name: str) -> dict:
    pr = t.get(DT, name)
    if not pr or int(pr.get("docstatus") or 0) != 0 or pr.get("workflow_state") != PENDING:
        return {"receipt": name, "result": "not waiting for verification"}
    found = problems(t, pr)
    if found:
        t.method("ivendnext_mpos.api.v1.add_comment", {"reference_doctype": DT, "reference_name": name,
                                                         "content": "Not verified: " + " ".join(found)[:900],
                                                         "comment_email": "", "comment_by": ""})
        return {"receipt": name, "result": "not verified", "why": found}
    t.method("ivendnext_mpos.api.v1.apply_workflow", {"doc": json.dumps(pr, default=str), "action": VERIFY})
    return {"receipt": name, "result": "verified"}
