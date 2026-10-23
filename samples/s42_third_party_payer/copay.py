"""S42 — a third party that pays part of a sale: the plan's rules, as pure functions (standard library only).

The service (service/app.py) reads the shop's records and calls these; the tests call them with fixtures. Nothing here
reads or writes the shop.

    coverage(request, plan, member, customer_barred, list_prices)   the payer door's answer for one sale (PB-8 spec §3)
    return_split(claim_lines, returned, earlier_returns)            what a return gives back to the payer and the patient
    check_plan(plan)                                                a plan's settings, refused in words

The rules are rebuilt from an iVend Retail add-on we built for a pharmacy chain (its calculation and the eight cases its
comments describe), never ported:

- **co-pay %**: the patient pays this share of the covered amount inside the limit;
- **invoice upper limit**: the payer covers at most this much of one sale; the rest of the covered amount is the patient's;
- **maximum patient amount**: the co-pay never exceeds it (the excess over the limit and extra-item pay are not co-pay);
- **extra-item pay**: a fixed amount per stock unit of an item the patient always pays, at face, before anything else;
- **discount before or after the limit**: the limit is compared with the covered amount after the sale's discount
  (``Before the limit``) or before it (``After the limit``);
- **co-pay before or after the discount**: the co-pay % is taken of the amount before the sale's discount (the discount
  is then wholly the payer's) or after it (shared);
- **no partial refunds**: a sale the plan covers is returned whole or not at all;
- **a customer barred from sales a third party pays** (Customer ``pp_icp_insurance_barred``).

Two departures from that add-on, on purpose:
1. **The sale's prices are never changed here.** The add-on re-priced each line from the insurer's special price list and
   added a surcharge so the patient paid the excess over the limit undiscounted. Here the shop's own pricing (the
   plan's price list, its pricing rules) prices the sale; these rules only split its total. So the excess carries the
   sale's own discount, and the payer's share plus the patient's always equals the sale's total, to the cent.
2. **A return is never re-calculated.** The add-on ran the split again on negative amounts, and its 2024 generic version
   clamped every share at zero, which gave a refund nothing back. Here a return gives back each returned line's own
   shares from the claim, in proportion to the quantity returned.

The price-list rule is one a pharmacy customer ran (a third party's add-on: we know the rule, not its code): when the plan names a price list, an
item it does not carry, or carries at zero, is *not sellable on this cover* (BRD VR-29, VR-36). It is read from the
plan's list itself (``list_prices``), never from the line's rate: the till re-prices a missing or zero row from the
store's list without a word (``ivendnext_mpos`` business_logic/mpos_cart.py), so a rate on the line proves nothing.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CONTRACT = "payer/1"
BEFORE_LIMIT, AFTER_LIMIT = "Before the limit", "After the limit"
BEFORE_DISCOUNT, AFTER_DISCOUNT = "Before the discount", "After the discount"
FORMULARY_ONLY, EVERY_ITEM = "Formulary items", "Every item"
ZERO = Decimal(0)

# what a line or a sale is refused for, and the words the till shows (BRD §7; ⟨…⟩ filled in)
WORDS = {
    "barred": "{customer} cannot buy on {payer}.",                              # VR-30
    "no_member": "{customer} has no cover with {payer} today.",
    "plan_off": "{plan} is not active today.",
    "not_on_list": "{item} is not covered by {payer}'s price list.",          # VR-29
    "zero_on_list": "{item} has no price on {payer}'s price list.",           # VR-36
    "not_covered": "{item} is not covered by {plan}: the customer pays it.",  # informational, never a refusal
    "over_limit": "{plan} covers {limit} of {item} on one sale: the customer pays the rest.",
    "partial_return": "A sale {payer} paid part of is returned whole: return every line of it.",
}


def D(v) -> Decimal:
    if v is None or v == "":
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _q(v: Decimal, places: int) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def check_plan(plan: dict) -> list[str]:
    """A plan's settings, refused in words (the Desk's own form cannot express these)."""
    bad = []
    p = D(plan.get("copay_percent"))
    if not ZERO <= p <= 100:
        bad.append("The co-pay % is between 0 and 100.")
    for f, label in (("invoice_upper_limit", "invoice upper limit"), ("max_patient_amount", "maximum patient amount")):
        if D(plan.get(f)) < 0:
            bad.append(f"The {label} is 0 (none) or more.")
    if plan.get("discount_order", BEFORE_LIMIT) not in (BEFORE_LIMIT, AFTER_LIMIT):
        bad.append(f"The discount is applied '{BEFORE_LIMIT}' or '{AFTER_LIMIT}'.")
    if plan.get("copay_order", BEFORE_DISCOUNT) not in (BEFORE_DISCOUNT, AFTER_DISCOUNT):
        bad.append(f"The co-pay is taken '{BEFORE_DISCOUNT}' or '{AFTER_DISCOUNT}'.")
    if plan.get("covers", FORMULARY_ONLY) not in (FORMULARY_ONLY, EVERY_ITEM):
        bad.append(f"The plan covers '{FORMULARY_ONLY}' or '{EVERY_ITEM}'.")
    rows = plan.get("formulary")
    for r in rows if isinstance(rows, list) else []:   # a data set names its formulary; the service resolves the rows
        if bool(r.get("item_code")) == bool(r.get("item_group")):
            bad.append("Each formulary row names an item or an item group, not both.")
        if D(r.get("extra_pay")) < 0 or D(r.get("max_qty")) < 0:
            bad.append("A formulary row's extra-item pay and maximum quantity are 0 (none) or more.")
    return bad


def _row_for(plan: dict, line: dict):
    """The formulary row for a line: the item's own row, else its item group's, else none."""
    rows = plan.get("formulary") or []
    for r in rows:
        if r.get("item_code") and r["item_code"] == line.get("item_code"):
            return r
    for r in rows:
        if r.get("item_group") and r["item_group"] == line.get("item_group"):
            return r
    return None


def _in_force(rec: dict, today: str) -> bool:
    if not int(rec.get("active", 1) or 0):
        return False
    return (not rec.get("valid_from") or rec["valid_from"] <= today) and (not rec.get("valid_to") or today <= rec["valid_to"])


def coverage(request: dict, plan: dict | None, member: dict | None, customer_barred: bool,
             list_prices: dict | None = None, payer: dict | None = None) -> dict:
    """The payer door's coverage answer (``payer/1``, PB-8 spec §3) for one sale.

    request: {sale_ref, customer, date (YYYY-MM-DD), currency, precision, prescription?,
              lines: [{line_id, item_code, item_group, gtin, qty, uom, conversion_factor, rate, amount, discount}]}
      ``amount``  what the line costs the customer, tax included, after the sale's discount (the till's line total);
      ``discount`` the discount the shop's pricing gave on it, on the same basis (0 when none).
    plan, member: the shop's records (None when there is none); payer: the payer record (its title and active tick).
    list_prices: {item_code: price or None} read from the plan's price list (only when the plan names one).

    answer: "cover" (every line sellable on the cover), "refuse" (a line is not sellable on it: the door refuses an
    insured Pay until the line goes), or "no_cover" (the sale cannot be paid by this payer at all).
    """
    today = request.get("date") or ""
    places = int(request.get("precision", 2))
    payer_title = (payer or {}).get("title") or (plan or {}).get("payer") or "the payer"
    names = {"customer": request.get("customer") or "The customer", "payer": payer_title,
             "plan": (plan or {}).get("title") or (plan or {}).get("name") or "The plan"}
    base = {"contract": CONTRACT, "sale_ref": request.get("sale_ref"), "payer": (plan or {}).get("payer"),
            "plan": (plan or {}).get("name"), "member": (member or {}).get("name"),
            "claim_ref": claim_ref(request.get("sale_ref"), (plan or {}).get("payer")),
            "no_partial_refund": bool(int((plan or {}).get("no_partial_refund") or 0))}

    def no_cover(code):
        return dict(base, answer="no_cover", code=code, message=WORDS[code].format(**names), lines=[],
                    totals={"payer_share": "0", "patient_share": str(_q(sum((D(l.get("amount")) for l in
                            request.get("lines") or []), ZERO), places))})

    if customer_barred:
        return no_cover("barred")
    if not member or not _in_force(member, today) or (plan and member.get("plan") != plan.get("name")):
        return no_cover("no_member")
    if not plan or not _in_force(plan, today) or (payer is not None and not _in_force(payer, today)):
        return no_cover("plan_off")

    p = D(plan.get("copay_percent")) / 100
    limit = D(plan.get("invoice_upper_limit"))
    cap = D(plan.get("max_patient_amount"))
    every = plan.get("covers", FORMULARY_ONLY) == EVERY_ITEM
    out, cov = [], []
    refused = False
    for line in request.get("lines") or []:
        item = line.get("item_code")
        net = D(line.get("amount"))
        gross = net + D(line.get("discount"))
        stock_qty = D(line.get("qty")) * (D(line.get("conversion_factor")) or Decimal(1))
        row = _row_for(plan, line)
        res = {"line_id": line.get("line_id"), "item_code": item, "covered": False, "sellable": True,
               "reason": None, "message": None, "covered_qty": "0", "qty_limit": None, "extra_pay": "0"}
        if plan.get("price_list"):
            price = (list_prices or {}).get(item)
            code = "not_on_list" if price is None else ("zero_on_list" if D(price) <= 0 else None)
            if code:
                refused = True
                res.update(sellable=False, reason=code, message=WORDS[code].format(item=item, **names))
                out.append((res, net, ZERO, ZERO, ZERO))
                continue
        covered = (row is not None and int(row.get("covered", 1) or 0)) or (every and (row is None or
                                                                            int(row.get("covered", 1) or 0)))
        if not covered or stock_qty <= 0:
            res.update(reason="not_covered", message=WORDS["not_covered"].format(item=item, **names))
            out.append((res, net, ZERO, ZERO, ZERO))
            continue
        max_qty = D((row or {}).get("max_qty"))
        cqty = min(stock_qty, max_qty) if max_qty > 0 else stock_qty
        if max_qty > 0:
            res["qty_limit"] = str(max_qty)
            if cqty < stock_qty:
                res.update(reason="over_limit", message=WORDS["over_limit"].format(item=item, limit=max_qty, **names))
        f = cqty / stock_qty
        n, g = net * f, gross * f
        x = min(D((row or {}).get("extra_pay")) * cqty, n)
        res.update(covered=True, covered_qty=str(cqty), extra_pay=str(_q(x, places)))
        out.append((res, net, n - x, g - x, x))
        cov.append(len(out) - 1)

    w_n = sum((o[2] for o in out), ZERO)          # covered amount, after the discount, extra-item pay out
    w_g = sum((o[3] for o in out), ZERO)          # the same before the discount
    k = (w_n / w_g) if w_g > 0 else Decimal(1)    # what the sale's discount leaves of each unit covered
    if plan.get("discount_order", BEFORE_LIMIT) == BEFORE_LIMIT:
        in_n = min(w_n, limit) if limit > 0 else w_n
        in_g = in_n / k if k > 0 else in_n
    else:
        in_g = min(w_g, limit) if limit > 0 else w_g
        in_n = in_g * k
    copay = p * (in_g if plan.get("copay_order", BEFORE_DISCOUNT) == BEFORE_DISCOUNT else in_n)
    if cap > 0:
        copay = min(copay, cap)
    copay = min(copay, in_n)
    payer_total = _q(in_n - copay, places)
    total = _q(sum((o[1] for o in out), ZERO), places)

    # the payer's share spread over the covered lines in proportion to each one's covered amount, to the cent
    shares = [ZERO] * len(out)
    if cov and w_n > 0 and payer_total > 0:
        unit = Decimal(1).scaleb(-places)
        raw = [(i, payer_total * out[i][2] / w_n) for i in cov]
        floor = {i: (v // unit) * unit for i, v in raw}
        left = int((payer_total - sum(floor.values(), ZERO)) / unit)
        for i, _ in sorted(raw, key=lambda iv: (iv[1] - floor[iv[0]], -iv[0]), reverse=True)[:left]:
            floor[i] += unit
        for i in cov:
            shares[i] = floor[i]
    lines = []
    for i, (res, net, _n, _g, _x) in enumerate(out):
        res["payer_share"] = str(shares[i])
        res["patient_share"] = str(_q(net, places) - shares[i])
        lines.append(res)
    answer = "refuse" if refused else "cover"
    msg = next((r["message"] for r in lines if not r["sellable"]), None)
    return dict(base, answer=answer, code="not_sellable" if refused else None, message=msg, lines=lines,
                totals={"payer_share": str(payer_total), "patient_share": str(total - payer_total),
                        "total": str(total)},
                rules={"copay_percent": str(D(plan.get("copay_percent"))), "invoice_upper_limit": str(limit),
                       "max_patient_amount": str(cap), "covered_net": str(_q(w_n, places)),
                       "inside_limit": str(_q(in_n, places)), "over_limit": str(_q(w_n - in_n, places)),
                       "copay": str(_q(copay, places))})


def claim_ref(sale_ref, payer) -> str | None:
    """The claim's reference: the same for every press of Pay on one sale, so the receipt's and the claim's agree."""
    if not sale_ref or not payer:
        return None
    return f"{payer}-{sale_ref}"[:140]


def return_split(claim_lines: list[dict], returned: list[dict], earlier: list[dict] | None = None,
                 no_partial_refund: bool = False, places: int = 2) -> dict:
    """What a return gives back.

    claim_lines: the claim's lines {line_id, qty, amount, payer_share} (the sale as it was booked);
    returned: this return's lines {line_id, qty} (positive quantities);
    earlier: the quantities earlier returns already gave back {line_id, qty}.
    With ``no_partial_refund`` a return must give back every line still held, in full; anything else is refused.
    """
    held = {c["line_id"]: D(c["qty"]) for c in claim_lines}
    for e in earlier or []:
        held[e["line_id"]] = held.get(e["line_id"], ZERO) - D(e["qty"])
    back = {r["line_id"]: D(r["qty"]) for r in returned}
    unknown = [lid for lid in back if lid not in held]
    if unknown:
        return {"answer": "refuse", "code": "unknown_line", "message": "A returned line is not on the sale.",
                "lines": []}
    over = [lid for lid, q in back.items() if q > held[lid]]
    if over:
        return {"answer": "refuse", "code": "over_return", "message": "More is returned than the sale still holds.",
                "lines": []}
    if no_partial_refund and any(back.get(lid, ZERO) != q for lid, q in held.items() if q > 0):
        return {"answer": "refuse", "code": "partial_return", "message": WORDS["partial_return"].format(payer="the payer"),
                "lines": []}
    lines, pay_back, pat_back = [], ZERO, ZERO
    for c in claim_lines:
        q = back.get(c["line_id"], ZERO)
        if q <= 0:
            continue
        qty = D(c["qty"])
        held_before = held[c["line_id"]]
        if q == held_before:   # the last of the line: whatever is left, so repeated returns add up exactly
            given_pay = sum((D(e.get("payer_back")) for e in earlier or [] if e["line_id"] == c["line_id"]), ZERO)
            given_amt = sum((D(e.get("amount_back")) for e in earlier or [] if e["line_id"] == c["line_id"]), ZERO)
            pay = D(c["payer_share"]) - given_pay
            amt = D(c["amount"]) - given_amt
        else:
            pay = _q(D(c["payer_share"]) * q / qty, places)
            amt = _q(D(c["amount"]) * q / qty, places)
        lines.append({"line_id": c["line_id"], "qty": str(q), "amount_back": str(amt), "payer_back": str(pay),
                      "patient_back": str(amt - pay)})
        pay_back += pay
        pat_back += amt - pay
    return {"answer": "cover", "code": None, "message": None, "lines": lines,
            "totals": {"payer_back": str(pay_back), "patient_back": str(pat_back)}}
