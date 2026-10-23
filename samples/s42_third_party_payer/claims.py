"""S42 — claims: built from a booked sale, filed as a file, followed to payment (standard library only).

    build_claim(sale, payer, member)        a claim from a sale the payer door booked (PB-8 spec §5: what it stores)
    apply_return(claim, split)              a return's give-back on its claim's lines
    claims_file(claims, payer)              the generic payer's claims file (CSV), one row per claim line
    move(claim, to, **why)                  a status change, refused in words when the flow does not allow it
    match_remittance(lines, claims)         a payer's remittance against its claims: expected against received

Pure functions over plain dicts: the service (service/app.py) reads and writes the shop's records with them, the tests
call them with fixtures.

A claim's lines are the sale's own: what the payer door booked as the payer's share of each line. Nothing is
re-calculated here (the door stored the split it booked); a return reduces each line by what it gave back.

What a payer needs on a claim is its data (the payer's ``needs_*`` ticks, from the data set), never code: Saudi's NPHIES
bills a drug by its GTIN, Abu Dhabi's Shafafiya wants dose and frequency per line, Ghana's NHIA claim form the member
number and card serial (`Pharmacy_Regulatory_Matrix.md` §SA, §AE, §GH). A claim missing what its payer needs is
*Incomplete* and is never put in a file: the claims clerk fills it on the Desk first. ⚠ The counter-rules app (K1)
keeps a prescription's directions as free text, with no structured dose or frequency, so the clerk types them.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from copay import D, ZERO

META = ("owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield", "parenttype",
        "doctype")


def rows(lines: list[dict]) -> list[dict]:
    """A child table's rows as written back: every field kept (a row sent without one is cleared), the shop's own
    bookkeeping fields left out."""
    return [{k: v for k, v in l.items() if k not in META} for l in lines]


def filed_as(claim: dict) -> str:
    """What a Ready claim becomes when it goes in a file: Submitted the first time, Resubmitted after a rejection."""
    return RESUBMITTED if int(claim.get("resubmissions") or 0) else SUBMITTED

READY, INCOMPLETE, SUBMITTED, ACCEPTED, REJECTED, RESUBMITTED, PAID, SHORT, BILLED, RETURNED = (
    "Ready", "Incomplete", "Submitted", "Accepted", "Rejected", "Resubmitted", "Paid", "Short paid",
    "Billed to patient", "Returned")
STATUSES = (READY, INCOMPLETE, SUBMITTED, ACCEPTED, REJECTED, RESUBMITTED, PAID, SHORT, BILLED, RETURNED)
# where a claim may go from each status (FR-K4-05). A rejected claim is corrected and made Ready again (the next file
# sends it as Resubmitted), or billed back to the patient; a short-paid one has its difference billed back or is
# settled as it stands (Paid, with the shortfall kept).
FLOW = {
    INCOMPLETE: (READY, RETURNED),
    READY: (SUBMITTED, RESUBMITTED, INCOMPLETE, RETURNED),
    SUBMITTED: (ACCEPTED, REJECTED, PAID, SHORT),
    ACCEPTED: (PAID, SHORT, REJECTED),
    REJECTED: (READY, BILLED),
    RESUBMITTED: (ACCEPTED, REJECTED, PAID, SHORT),
    SHORT: (BILLED, PAID),
    PAID: (),
    BILLED: (),
    RETURNED: (),
}
FILE_COLUMNS = ("claim_ref", "sale_date", "store", "member_number", "card_serial", "policy_number", "prescription",
                "prescriber", "prescriber_licence", "line", "item_code", "gtin", "qty", "uom", "dose", "frequency",
                "amount", "payer_share", "patient_share")


def build_claim(sale: dict, payer: dict, member: dict) -> dict:
    """A claim from a booked payer sale.

    sale (the door's record of the sale, PB-8 spec §5): {doctype, name, posting_date, store, customer, claim_ref,
      payer, plan, member, prescription, prescriber, prescriber_licence, is_return,
      lines: [{line_id, item_code, gtin, qty, uom, amount, payer_share, patient_share, dose?, frequency?}]}
    payer: the payer record (its needs_* ticks); member: the member record.
    """
    lines = []
    for l in sale.get("lines") or []:
        if D(l.get("payer_share")) <= 0:
            continue                      # an uncovered or refused line is the patient's: never on a claim
        lines.append({k: l.get(k) for k in ("line_id", "item_code", "gtin", "qty", "uom", "amount", "payer_share",
                                             "patient_share", "dose", "frequency")})
    claim = {
        "name": sale["claim_ref"], "claim_ref": sale["claim_ref"], "payer": sale["payer"], "plan": sale.get("plan"),
        "member": sale.get("member"), "customer": sale.get("customer"), "sale_doctype": sale["doctype"],
        "sale": sale["name"], "sale_date": sale.get("posting_date"), "store": sale.get("store"),
        "member_number": member.get("member_number"), "card_serial": member.get("card_serial"),
        "policy_number": member.get("policy_number"), "prescription": sale.get("prescription"),
        "prescriber": sale.get("prescriber"), "prescriber_licence": sale.get("prescriber_licence"),
        "lines": lines, "total": str(sum((D(l["amount"]) for l in lines), ZERO)),
        "payer_share": str(sum((D(l["payer_share"]) for l in lines), ZERO)), "received": "0", "billed_back": "0",
    }
    missing = what_is_missing(claim, payer)
    claim["status"] = INCOMPLETE if missing else READY
    claim["incomplete_reason"] = "; ".join(missing)
    return claim


def what_is_missing(claim: dict, payer: dict) -> list[str]:
    """What the claim's payer needs that the claim does not carry, in words."""
    miss = []
    if int(payer.get("needs_member_number") or 0) and not claim.get("member_number"):
        miss.append("the member number")
    if int(payer.get("needs_card_serial") or 0) and not claim.get("card_serial"):
        miss.append("the card serial number")
    if int(payer.get("needs_prescription") or 0) and not claim.get("prescription"):
        miss.append("the prescription")
    for l in claim.get("lines") or []:
        if int(payer.get("needs_gtin") or 0) and not l.get("gtin"):
            miss.append(f"the GTIN of line {l['line_id']} ({l['item_code']})")
        if int(payer.get("needs_dose_frequency") or 0) and not (l.get("dose") and l.get("frequency")):
            miss.append(f"the dose and frequency of line {l['line_id']} ({l['item_code']})")
    if not claim.get("lines"):
        miss.append("a line the payer pays part of")
    return miss


def apply_return(claim: dict, split: dict) -> dict:
    """A return's give-back (copay.return_split's answer) on the claim: each line's payer share is reduced by what the
    return gave back. A claim whose every line came back is *Returned*; one already filed keeps its status and the
    reduction is what the next file, or the remittance, is matched against."""
    back = {l["line_id"]: l for l in split.get("lines") or []}
    for l in claim["lines"]:
        b = back.get(l["line_id"])
        if not b:
            continue
        l["returned_qty"] = str(D(l.get("returned_qty")) + D(b["qty"]))
        l["payer_back"] = str(D(l.get("payer_back")) + D(b["payer_back"]))
    claim["payer_share"] = str(sum((D(l["payer_share"]) - D(l.get("payer_back")) for l in claim["lines"]), ZERO))
    if all(D(l.get("returned_qty")) >= D(l["qty"]) for l in claim["lines"]) and claim["status"] in (READY, INCOMPLETE):
        claim["status"] = RETURNED
    return claim


def move(claim: dict, to: str, **why) -> dict:
    """Move a claim to another status (FR-K4-05), or raise ValueError in words."""
    if to not in STATUSES:
        raise ValueError(f"'{to}' is not a claim status.")
    if to not in FLOW[claim["status"]]:
        raise ValueError(f"A claim that is {claim['status']} cannot become {to}.")
    if to == REJECTED and not why.get("reason"):
        raise ValueError("A rejected claim keeps the payer's reason.")
    if to == READY and what_is_missing(claim, why.get("payer") or {}):
        raise ValueError("The claim still lacks: " + "; ".join(what_is_missing(claim, why["payer"])) + ".")
    if to == BILLED:
        due = D(claim["payer_share"]) - D(claim.get("received"))
        if due <= 0:
            raise ValueError("Nothing is left to bill back to the patient.")
        claim["billed_back"] = str(due)
    if to == REJECTED:
        claim["rejection_reason"] = why["reason"]
    if to == READY and claim["status"] == REJECTED:
        claim["resubmissions"] = int(claim.get("resubmissions") or 0) + 1
    claim["status"] = to
    return claim


def claims_file(claims: list[dict], payer: dict) -> str:
    """The generic payer's claims file: CSV, one row per claim line, every claim Ready (a corrected one goes again),
    none Incomplete. A payer's own format (NPHIES' FHIR, eClaimLink's XML, NHIA's form) is a partner's: it reads the same
    claims."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(FILE_COLUMNS)
    for c in claims:
        if c["status"] != READY or c["payer"] != payer.get("code", c["payer"]):
            continue
        for l in c["lines"]:
            share = D(l["payer_share"]) - D(l.get("payer_back"))
            if share <= 0:
                continue
            row = dict(c, line=l["line_id"], **{k: l.get(k) for k in ("item_code", "gtin", "qty", "uom", "dose",
                                                                       "frequency", "amount", "patient_share")})
            row["payer_share"] = str(share)
            w.writerow([_cell(row.get(k)) for k in FILE_COLUMNS])
    return out.getvalue()


def _cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s   # a spreadsheet never runs a cell as a formula


def match_remittance(lines: list[dict], claims: dict[str, dict]) -> list[dict]:
    """A remittance's lines {claim_ref, paid, rejected?, reason?} against the claims (by reference): each line's
    claim, what was expected (the claim's payer share less returns and what earlier remittances paid), what was
    paid, and what that makes the claim (FR-K4-06). An unknown reference is kept as *Unmatched*, never dropped."""
    out = []
    for r in lines:
        c = claims.get(r.get("claim_ref"))
        paid = D(r.get("paid"))
        if not c:
            out.append({"claim_ref": r.get("claim_ref"), "expected": "0", "paid": str(paid), "result": "Unmatched"})
            continue
        expected = D(c["payer_share"]) - D(c.get("received"))
        if r.get("rejected"):
            result = REJECTED
        elif paid == expected:
            result = PAID
        elif paid < expected:
            result = SHORT
        else:
            result = "Over paid"
        out.append({"claim_ref": c["claim_ref"], "expected": str(expected), "paid": str(paid), "result": result,
                    "difference": str(expected - paid), "reason": r.get("reason")})
    return out
