#!/usr/bin/env python3
"""S43's canaries: each test that guards a co-pay rule, the price-list rule, who may buy on cover, a claim's flow, a
return, the remittance or a secret must go RED when that rule is broken. For each mutation this copies the sample (and
the kit folders it uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else
BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs the test again, and
reports RED (the test caught it) or GREEN (a dead test). The runner is S39's (``samples/s39_pharmacy_counter/tests/
canaries.py``), itself S37's and S23's, copied: a defect there is a defect here.

    python3 samples/s43_third_party_payer/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, K, S, M = "test_rules.", "test_claims.", "test_service.", "test_manifest.ManifestTest."
CP, CL, SV = "copay.py", "claims.py", "service/app.py"

CANARIES = [
    # the add-on's co-pay rules
    ("the co-pay is taken before the discount", CP, 'copay = p * (in_g if plan.get("copay_order", BEFORE_DISCOUNT) == BEFORE_DISCOUNT else in_n)',
     "copay = p * in_n", R + "AddOnCases.test_case_2_copay_before_the_discount"),
    ("the co-pay after the discount", CP, 'copay = p * (in_g if plan.get("copay_order", BEFORE_DISCOUNT) == BEFORE_DISCOUNT else in_n)',
     "copay = p * in_g", R + "AddOnCases.test_case_6_copay_after_the_discount"),
    ("the maximum co-pay", CP, "        copay = min(copay, cap)\n", "        pass\n", R + "AddOnCases.test_case_3_maximum_patient_amount"),
    ("the limit after the discount", CP, "        in_n = min(w_n, limit) if limit > 0 else w_n\n", "        in_n = w_n\n",
     R + "AddOnCases.test_case_4_limit_on_the_amount_after_the_discount"),
    ("the limit before the discount", CP, "        in_g = min(w_g, limit) if limit > 0 else w_g\n", "        in_g = w_g\n",
     R + "AddOnCases.test_case_5_limit_on_the_amount_before_the_discount"),
    ("the order of the limit and the discount", CP, 'if plan.get("discount_order", BEFORE_LIMIT) == BEFORE_LIMIT:',
     'if plan.get("discount_order", BEFORE_LIMIT) != BEFORE_LIMIT:', R + "AddOnCases.test_case_5_limit_on_the_amount_before_the_discount"),
    ("extra-item pay is the patient's", CP, 'x = min(D((row or {}).get("extra_pay")) * cqty, n)', "x = ZERO",
     R + "AddOnCases.test_case_1_no_copay_no_limit"),
    ("the co-pay never exceeds what is covered", CP, "    copay = min(copay, in_n)\n", "    copay = copay\n",
     R + "EveryCombination.test_every_combination_splits_the_sale_exactly_and_within_the_rules"),
    ("the payer's share spread to the cent", CP, "            floor[i] += unit\n", "            pass\n",
     R + "EveryCombination.test_every_combination_splits_the_sale_exactly_and_within_the_rules"),
    ("the quantity limit", CP, "cqty = min(stock_qty, max_qty) if max_qty > 0 else stock_qty", "cqty = stock_qty",
     R + "EveryCombination.test_the_quantity_limit_covers_only_that_many_units"),
    ("an uncovered line is the patient's", CP, "        if not covered or stock_qty <= 0 or net <= 0:", "        if stock_qty <= 0 or net <= 0:",
     R + "EveryCombination.test_every_combination_splits_the_sale_exactly_and_within_the_rules"),
    # the price-list rule
    ("an item off the list", CP, 'code = "not_on_list" if price is None else', 'code = None if price is None else',
     R + "PriceList.test_an_item_off_the_list_is_refused_in_the_payers_words"),
    ("an item at zero on the list", CP, '("zero_on_list" if D(price) <= 0 else None)', "None",
     R + "PriceList.test_an_item_at_zero_on_the_list_is_refused"),
    ("the list is read by the service", SV, '                rate = C.D(r.get("price_list_rate"))', "                rate = C.D(1)", S + "Calls.test_an_item_at_zero_on_the_list_is_not_sellable_whatever_the_line_says"),
    ("a row in another unit", SV, "                    continue                                 # another unit, neither the line's nor the stock unit", "                    rank = 0",
     S + "Calls.test_a_list_row_counts_only_as_the_engine_applies_it"),
    ("a row for another customer", SV, '(r.get("customer") and r["customer"] != customer)', "False",
     S + "Calls.test_a_list_row_counts_only_as_the_engine_applies_it"),
    ("a batch's own price", SV, 'r["item_code"] != l.get("item_code") or r.get("batch_no") or', 'r["item_code"] != l.get("item_code") or',
     S + "Calls.test_a_list_row_counts_only_as_the_engine_applies_it"),
    ("a line's own unit first", CP, 'price = lp[line.get("line_id")] if line.get("line_id") in lp else lp.get(item)', "price = lp.get(item)",
     S + "Calls.test_two_lines_of_one_item_in_two_units_are_judged_each_on_its_own_unit"),
    ("a line at zero or below", CP, "if not covered or stock_qty <= 0 or net <= 0:", "if not covered or stock_qty <= 0:",
     R + "EveryCombination.test_a_line_at_zero_or_below_is_the_patients"),
    ("amounts in whole minor units", SV, 'raise ValueError("each line\'s money is whole minor units")', "pass",
     S + "Calls.test_a_line_not_at_the_sales_precision_or_a_repeated_line_id_is_refused"),
    ("the lines add up to the sale", SV, 'raise ValueError("the lines do not add up to the sale\'s total")', "pass",
     S + "Door.test_the_old_wire_is_refused"),
    ("the door's envelope", SV, 'ctx = body.get("context") if body.get("point") == C.CONTRACT else None', "ctx = body.get(\"context\")",
     S + "Door.test_the_old_wire_is_refused"),
    # the door's answer (payer/1)
    ("money back in minor units", CP, "        return int(D(v).scaleb(exp))", "        return float(D(v))",
     S + "Door.test_every_answer_is_one_the_doors_contract_takes"),
    ("only the contract's keys", CP, 'return dict(head, answer="refuse", lines=[line(r, False) for r in out["lines"]])',
     'return dict(out, answer="refuse", lines=[line(r, False) for r in out["lines"]])',
     S + "Door.test_every_answer_is_one_the_doors_contract_takes"),
    ("the rounded total caps the payer", CP, '        payer_total = max(min(payer_total, _q(D(request["payer_cap"]), places)), ZERO)',
     "        pass", S + "Door.test_the_payers_share_never_passes_the_rounded_total"),
    ("a cover that pays nothing", CP, '    if minor(out["totals"]["payer_share"]) <= 0:', "    if False:",
     S + "Door.test_a_cover_that_would_pay_nothing_is_no_cover"),
    ("the covered quantity in the line's unit", CP, '"covered_qty": float(D(r["covered_qty"]) / cf),',
     '"covered_qty": float(D(r["covered_qty"])),', S + "Door.test_a_pack_lines_covered_quantity_is_in_the_lines_own_unit"),
    ("a tax-excluded discount carries its tax", CP, "            discount = _q(discount * max(amount / paid, Decimal(1)), exp)",
     "            pass", S + "Door.test_a_tax_excluded_sales_discount_is_read_with_its_tax"),
    ("a sale's discount never read with less than itself", CP, "max(amount / paid, Decimal(1))", "amount / paid",
     S + "Door.test_a_sales_discount_on_prices_without_tax_is_read_with_at_most_its_tax"),
    ("a booking cancelled with its day is no claim", SV, "        if not int(doc.get(\"is_return\") or 0) and not doc.get(DOOR[\"journal\"]):",
     "        if False:", S + "Claims.test_a_sale_whose_booking_journal_was_cancelled_is_no_claim"),
    ("a disabled payer customer is left out", SV, " or \\\n                    not self.billable(shop, payer[\"customer\"]):", ":",
     S + "Door.test_a_disabled_payer_customer_leaves_that_cover_out_not_the_answer"),
    ("text the door takes", CP, "    text = \"\".join(c for c in str(text or \"\") if c not in _REFUSED_CHARS and",
     "    text = \"\".join(c for c in str(text or \"\") if True or", S + "Door.test_a_title_with_markup_is_sent_as_text_the_door_takes"),
    ("a returned line in its own unit", SV, '"back_qty": abs(C.D(it.get("qty")))}', '"back_qty": abs(C.D(it.get("stock_qty") or it.get("qty")))}',
     S + "Claims.test_a_returned_line_counts_back_in_its_own_unit"),
    ("the refusal fits the door's answer", SV, "REFUSAL_MAX = 250", "REFUSAL_MAX = 300",
     S + "Claims.test_a_long_refusal_fits_the_doors_answer_and_a_broken_body_is_read_as_a_refusal"),
    ("the door's empty item group is filled", SV, '                    if not l.get("item_group"):        # the door sends an empty group as ""',
     '                    if "item_group" not in l:', S + "Calls.test_the_item_group_is_read_from_the_shop_when_the_door_does_not_send_it"),
    ("a payer is never the sale's own customer", SV, ' or payer["customer"] == customer or ', " or False or ",
     S + "Door.test_a_payer_whose_customer_is_the_sales_own_is_never_offered"),
    ("the door's refusal in its words", SV, "        if got.get(\"refused\"):", "        if False:",
     S + "Claims.test_a_bill_back_the_door_refuses_says_why_and_leaves_the_claim"),
    ("the answer's deadline", SV, "if t0 is not None and time.monotonic() - t0 > ANSWER_BY:", "if False:",
     S + "Calls.test_a_slow_shop_answers_503_before_the_doors_five_seconds"),
    ("one reference, two sales", SV, 'if held.get("sale") != name:', "if False:",
     S + "Claims.test_two_sales_under_one_claim_reference_fail_loudly_never_silently"),
    ("the till's own posting is not a second claim", SV, 'if doctype == "Sales Invoice" and (doc.get("is_consolidated") or any(', 'if False and (doc.get("is_consolidated") or any(',
     S + "Claims.test_the_tills_own_posting_of_a_payer_sale_is_never_a_second_claim"),
    ("a return before its claim", SV, '                raise ValueError("the return\'s claim is not made yet")', '                return "-"',
     S + "Claims.test_a_return_before_its_claim_is_tried_again_never_dropped"),
    ("lines of one claim summed", SV, "result = K.settle(c, sum((C.D(r.get(\"paid\")) for r in mine), C.ZERO),", "result = K.settle(c, C.D(mine[-1].get(\"paid\")),",
     S + "Claims.test_several_remittance_lines_for_one_claim_are_summed_before_it_is_settled"),
    ("a later part payment is kept", CL, '    if to == claim["status"] == SHORT:', "    if False:",
     K + "Settle.test_part_then_the_rest"),
    ("returned by money, not units", CL, '    if D(claim["payer_share"]) <= 0 and claim["status"] in (READY, INCOMPLETE):', "    if False:",
     K + "ClaimsFile.test_a_claim_is_returned_when_the_payer_is_owed_nothing_whatever_the_units"),
    ("the door's answer is read", SV, '        if not got.get("journal"):', "        if False:",
     S + "Claims.test_a_door_that_books_nothing_leaves_the_claim_unchanged"),
    ("a plan's own currency", CP, 'and plan["currency"] != request["currency"]:', "and False:",
     S + "Calls.test_a_sale_in_another_currency_than_the_plans_list_has_no_cover"),
    ("the stock unit's row times the pack", SV, "rank, rate = 1, rate * (C.D(l.get(\"conversion_factor\")) or C.Decimal(1))", "continue",
     S + "Calls.test_a_line_in_a_pack_unit_takes_the_stock_units_price_times_the_pack"),
    ("Mark ready goes through the flow", SV, "            K.move(c, to, payer=payer)\n", "            c[\"status\"] = to\n",
     S + "Claims.test_the_clerk_marks_a_claim_ready_only_once_complete_and_a_corrected_one_goes_again"),
    ("only a short-paid claim is settled", SV, '        if to == K.PAID and c["status"] != K.SHORT:', "        if False:",
     S + "Claims.test_only_a_short_paid_claim_is_settled_as_it_stands"),
    ("a claim's status is never typed", "manifest.json", '"read_only": 1,\n     "description": "Moved by the claims file', '"read_only": 0,\n     "description": "Moved by the claims file',
     M + "test_a_claims_status_is_never_typed"),
    # who may buy on cover
    ("a barred customer", CP, "    if customer_barred:\n", "    if False:\n", R + "WhoMayBuyOnCover.test_a_barred_customer_is_refused_in_the_brds_words"),
    ("a member out of date", CP, "    if not member or not _in_force(member, today) or", "    if not member or",
     R + "WhoMayBuyOnCover.test_a_member_out_of_date_is_no_cover"),
    ("a member of another plan", CP, ' or (plan and member.get("plan") != plan.get("name")):', ":",
     R + "WhoMayBuyOnCover.test_a_member_of_another_plan_is_no_cover"),
    ("an inactive payer", CP, " or (payer is not None and not _in_force(payer, today)):", ":",
     R + "WhoMayBuyOnCover.test_an_inactive_plan_or_payer_is_no_cover"),
    ("another customer's member", SV, "            member = None                                   # a member reference of another customer is no cover",
     "            pass", S + "Calls.test_another_customers_member_reference_is_no_cover"),
    ("the barred tick at covers", SV, "        if self.barred(shop, customer):\n            return {\"covers\": []", "        if False:\n            return {\"covers\": []",
     S + "Calls.test_a_barred_customer_has_no_cover"),
    ("the member number masked", SV, '"member_label": "…" + num[-4:],', '"member_label": num,',
     S + "Calls.test_covers_lists_the_customers_cover_with_the_member_number_masked"),
    # returns
    ("no partial refunds", CP, "    if no_partial_refund and any(", "    if False and any(",
     R + "Returns.test_no_partial_refund_refuses_part_of_a_sale"),
    ("the last unit takes what is left", CP, "        if q == held_before:", "        if False:",
     R + "Returns.test_three_returns_of_a_third_add_up_to_the_cent"),
    ("over-return", CP, "    over = [lid for lid, q in back.items() if q > held[lid]]", "    over = []",
     R + "Returns.test_more_than_the_sale_holds_is_refused"),
    ("a return reduces its claim once", SV, 'if name in (claim.get("returns") or "").split("\\n"):', "if False:",
     S + "Claims.test_a_return_reduces_its_claim_once"),
    # claims
    ("an uncovered line is never claimed", CL, '        if D(l.get("payer_share")) <= 0:\n            continue', "        if False:\n            continue",
     K + "BuildClaim.test_a_line_the_payer_pays_nothing_of_is_not_on_the_claim"),
    ("what the payer needs", CL, '    if int(payer.get("needs_prescription") or 0) and not claim.get("prescription"):',
     "    if False:", K + "BuildClaim.test_a_claim_missing_what_its_payer_needs_is_incomplete"),
    ("dose and frequency where asked", CL, '        if int(payer.get("needs_dose_frequency") or 0) and not (l.get("dose") and l.get("frequency")):',
     "        if False:", K + "BuildClaim.test_gtin_dose_and_frequency_are_asked_only_where_the_payer_needs_them"),
    ("only Ready claims are filed", CL, '        if c["status"] != READY or', "        if False or",
     K + "ClaimsFile.test_one_row_per_line_of_each_ready_claim"),
    ("a cell is never a formula", CL, "return \"'\" + s if s[:1] in", "return s if s[:1] in",
     K + "ClaimsFile.test_a_cell_never_runs_as_a_formula"),
    ("the flow refuses a skipped step", CL, '    if to not in FLOW[claim["status"]]:', "    if False:",
     K + "Flow.test_moves_the_flow_does_not_allow_are_refused_in_words"),
    ("a rejection keeps its reason", CL, '    if to == REJECTED and not why.get("reason"):', "    if False:",
     K + "Flow.test_moves_the_flow_does_not_allow_are_refused_in_words"),
    ("bill back only what is due", CL, '        due = D(claim["payer_share"]) - D(claim.get("received"))', "        due = D(claim[\"payer_share\"])",
     K + "Flow.test_a_short_paid_claim_bills_back_only_the_difference"),
    ("a claim made once", SV, '            return "-"\n        return "made"', '        return "made"',
     S + "Claims.test_a_booked_sale_becomes_a_ready_claim_once"),
    ("another payer's sale is not ours", SV, '        if not sale or sale["payer"] not in ours:', "        if not sale:",
     S + "Claims.test_a_sale_with_no_payer_leg_or_another_payers_is_not_ours"),
    ("a short payment", CL, "        elif paid < expected:\n            result = SHORT", "        elif paid < expected:\n            result = PAID",
     K + "Remittance.test_expected_against_received"),
    ("a claim of another payer is never matched", SV, 'if not c or c.get("payer") != remit.get("payer"):', "if not c:",
     S + "Claims.test_a_remittance_pays_shorts_and_rejects_claims"),
    ("no door, no bill", SV, "        if got is None:\n", "        if False:\n",
     S + "Claims.test_without_the_payer_door_nothing_is_billed_and_the_claim_is_unchanged"),
    # the calls
    ("a bad signature", SV, "        if not secrets or all(verify(ts, sig, raw, s) for s in secrets):", "        if not secrets:",
     S + "Calls.test_a_bad_signature_an_old_one_and_a_wrong_route_secret_are_refused"),
    ("an old signature", SV, "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "Calls.test_a_bad_signature_an_old_one_and_a_wrong_route_secret_are_refused"),
    ("a route with no secret", SV, "            return [s for s in [self.secrets[route_key]] if s], self.shop",
     "            return [self.secrets[route_key] or \"\"], self.shop", S + "Calls.test_a_route_whose_secret_is_not_set_refuses_every_call"),
    # the manifest
    ("members are never a till role's", "manifest.json", '"role": "PP ICP Claims Clerk",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,\n     "report": 1,\n     "export": 1,\n     "share": 0,\n     "print": 1,\n     "email": 0\n    },\n    {\n     "role": "PP ICP Integration",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 0,\n     "report": 0,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    }\n   ]\n  },\n  {\n   "name": "PP ICP Claim Line"',
     '"role": "PP ICP Claims Clerk",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,\n     "report": 1,\n     "export": 1,\n     "share": 0,\n     "print": 1,\n     "email": 0\n    },\n    {\n     "role": "Sales User",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 0,\n     "report": 0,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    }\n   ]\n  },\n  {\n   "name": "PP ICP Claim Line"',
     M + "test_members_and_claims_are_never_a_till_roles"),
    ("a claim's name is its reference", "manifest.json", '"autoname": "field:claim_ref"', '"autoname": "hash"',
     M + "test_a_claims_name_is_its_reference_so_a_second_insert_is_refused"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s43-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local"))
        for sub in ("tools/manifest", "tools/app_template", "tools/contracts", "contracts"):
            shutil.copytree(os.path.join(kit, sub), os.path.join(tmp, "r", sub), ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f).read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        open(f, "w").write(src.replace(anchor, mutant))
        if f.endswith(".py"):
            py_compile.compile(f, doraise=True)
        p = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                           capture_output=True, text=True, timeout=120)
        last = (p.stderr.strip().splitlines() or [""])[-1]
        return ("RED" if p.returncode else "GREEN"), last
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    bad = 0
    for c in CANARIES:
        verdict, last = run(*c)
        bad += verdict != "RED"
        print(f"{verdict:6} {c[0]} — {c[4]} — {last}")
    print(f"{len(CANARIES) - bad} of {len(CANARIES)} canaries RED")
    sys.exit(1 if bad else 0)
