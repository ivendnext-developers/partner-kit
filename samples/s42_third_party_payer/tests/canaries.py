#!/usr/bin/env python3
"""S42's canaries: each test that guards a co-pay rule, the price-list rule, who may buy on cover, a claim's flow, a
return, the remittance or a secret must go RED when that rule is broken. For each mutation this copies the sample (and
the kit folders it uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else
BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs the test again, and
reports RED (the test caught it) or GREEN (a dead test). The runner is S39's (``samples/s39_pharmacy_counter/tests/
canaries.py``), itself S37's and S23's, copied: a defect there is a defect here.

    python3 samples/s42_third_party_payer/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("an uncovered line is the patient's", CP, "        if not covered or stock_qty <= 0:\n", "        if stock_qty <= 0:\n",
     R + "EveryCombination.test_every_combination_splits_the_sale_exactly_and_within_the_rules"),
    # the price-list rule
    ("an item off the list", CP, 'code = "not_on_list" if price is None else', 'code = None if price is None else',
     R + "PriceList.test_an_item_off_the_list_is_refused_in_the_payers_words"),
    ("an item at zero on the list", CP, '("zero_on_list" if D(price) <= 0 else None)', "None",
     R + "PriceList.test_an_item_at_zero_on_the_list_is_refused"),
    ("the list is read by the service", SV, '                out[c] = r.get("price_list_rate") or 0', "                out[c] = 1", S + "Calls.test_an_item_at_zero_on_the_list_is_not_sellable_whatever_the_line_says"),
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
    ("the member number masked", SV, '"member_label": ("…" + num[-4:]) if num else ""', '"member_label": num',
     S + "Calls.test_covers_lists_the_customers_cover_with_the_member_number_masked"),
    # returns
    ("no partial refunds", CP, "    if no_partial_refund and any(", "    if False and any(",
     R + "Returns.test_no_partial_refund_refuses_part_of_a_sale"),
    ("the last unit takes what is left", CP, "        if q == held_before:", "        if False:",
     R + "Returns.test_three_returns_of_a_third_add_up_to_the_cent"),
    ("over-return", CP, "    over = [lid for lid, q in back.items() if q > held[lid]]", "    over = []",
     R + "Returns.test_more_than_the_sale_holds_is_refused"),
    ("a return reduces its claim once", SV, 'if not claim or name in (claim.get("returns") or "").split("\\n"):', "if not claim:",
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
    ("a claim made once", SV, '        return "-" if out.get("duplicate") else "made"', '        return "made"',
     S + "Claims.test_a_booked_sale_becomes_a_ready_claim_once"),
    ("another payer's sale is not ours", SV, '        if not sale or sale["payer"] not in ours:', "        if not sale:",
     S + "Claims.test_a_sale_with_no_payer_leg_or_another_payers_is_not_ours"),
    ("a short payment", CL, "        elif paid < expected:\n            result = SHORT", "        elif paid < expected:\n            result = PAID",
     K + "Remittance.test_expected_against_received"),
    ("a claim of another payer is never matched", SV, 'if c and c.get("payer") == remit.get("payer"):', "if c:",
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
    tmp = tempfile.mkdtemp(prefix="s42-canary-")
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
