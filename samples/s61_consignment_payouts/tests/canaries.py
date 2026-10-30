#!/usr/bin/env python3
"""S61's canaries: each test that guards a retailer's secret or key, a line paid once, the lines counted (submitted, the
company's, up to the date, never the till day's combined invoice), the share, the cent, the 500-line cap, the second
check before a payout is marked paid, an edit never written over, or the service's words must go RED when that check is
removed. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test
named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is
S16's, by way of S44's.

    python3 samples/s61_consignment_payouts/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, R, S, C = "test_service.ServiceTest.", "test_many_shops.ManyShops.", "test_rules.", "service/app.py", "consign.py"

CANARIES = [
    ("the signature is checked", S, "        if not secrets or all(consign.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", T + "test_s17_each_button_takes_only_its_own_secret_and_a_bad_signature_is_refused"),
    ("each button its own secret", S, 'shops.secrets_for(record, f"{self.app}:sub:{sub}")',
     'shops.secrets_for(record, f"{self.app}:sub:work") + shops.secrets_for(record, f"{self.app}:sub:pay")',
     M + "test_each_button_has_its_own_secret"),
    ("a 417 is a rights problem only by its kind", S, " or (e.code == 417 and e.kind in RIGHTS_KINDS)", " or e.code == 417",
     T + "test_s14b_another_417_is_not_called_a_rights_problem_and_a_long_timestamp_is_refused"),
    ("a long timestamp is refused", C, " and len(ts) <= 20)", ")",
     T + "test_s14b_another_417_is_not_called_a_rights_problem_and_a_long_timestamp_is_refused"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "test_administrators_key_is_never_used"),
    ("a press before the site's key arrives is answered in words", S,
     "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n", "",
     M + "test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403) or (e.code == 417 and e.kind in RIGHTS_KINDS):", "            if False:",
     T + "test_s14_the_apps_user_refused_by_the_site_is_said_in_words"),
    ("the consignor's share only is read", S, 'door.rows(consign.CONSIGNOR, ["name", "share", "since"]', 'door.rows(consign.CONSIGNOR, ["name", "share", "since", "phone"]',
     T + "test_s2_the_reads_ask_only_for_the_consignors_items_and_submitted_or_cancelled_sales"),
    ("only a submitted line", C, 'if head.get("docstatus") != 1 or head.get("company")', 'if head.get("company")',
     R + "WorkOut.test_only_a_submitted_line_of_the_company_on_or_before_the_date"),
    ("only the payout's company", C, ' or head.get("company") != company or day > up_to', " or day > up_to",
     T + "test_s1_work_out_writes_the_owed_lines_and_totals"),
    ("only up to the date", C, " or day > up_to or (since and day < since)", " or (since and day < since)",
     T + "test_s1_work_out_writes_the_owed_lines_and_totals"),
    ("never before Consigned since", C, " or (since and day < since)", "", R + "WorkOut.test_a_sale_before_consigned_since_is_never_theirs"),
    ("the service passes Consigned since", S, '\n                                     consign.date_of(found[0].get("since")))', ")",
     T + "test_s1_work_out_writes_the_owed_lines_and_totals"),
    ("never the till day's combined invoice", C, ' \\\n                or (typ == "Sales Invoice" and head.get("is_consolidated")):', ":",
     T + "test_s1_work_out_writes_the_owed_lines_and_totals"),
    ("a held line is never taken again", C, "        if key in holds or amount is None:", "        if amount is None:",
     T + "test_s3_a_line_another_payout_holds_is_left_and_a_cancelled_payouts_is_taken"),
    ("a cancelled payout holds nothing", C, " or st == CANCELLED:", ":", T + "test_s9_a_paid_payout_cancelled_frees_its_lines"),
    ("a payout is no hold on itself", C, " or p == this or", " or", T + "test_s4_pay_marks_it_paid_once_every_line_is_checked"),
    ("a paid hold wins over a draft's", C, "        if k not in out or st == PAID:", "        if k not in out:",
     R + "Holds.test_a_paid_payout_wins_over_a_draft_holding_the_same_line"),
    ("only a cancelled sale's balance is settled", C, '        if not head or head.get("docstatus") != 2:', "        if not head:",
     R + "WorkOut.test_a_held_line_is_left_and_a_cancelled_sale_settles_its_paid_balance_once"),
    ("a balance of 0 is settled", C, "        if part == 0:\n            continue\n", "",
     R + "WorkOut.test_a_held_line_is_left_and_a_cancelled_sale_settles_its_paid_balance_once"),
    ("taken back negative", C, '"sale_amount": -sold,', '"sale_amount": sold,',
     T + "test_s10_a_sale_cancelled_after_its_payout_was_paid_is_taken_back_once"),
    ("a correction when the payout that paid was cancelled", C, '"kind": TAKEN_BACK if part > 0 else CORRECTION,', '"kind": TAKEN_BACK,',
     T + "test_s21_a_take_back_paid_then_its_payout_cancelled_is_corrected_once"),
    ("only the consignor's own paid payouts", S, '[["consignor", "=", p["consignor"]]], timeout=self.left(t0))', "[], timeout=self.left(t0))",
     T + "test_s22_after_an_item_moves_its_paid_sale_is_taken_back_from_the_consignor_who_was_paid"),
    ("a payout settles only its own company's paid lines", S, ' and r.get("company") == p.get("company")]', "]",
     T + "test_s22b_a_paid_payout_of_another_company_is_never_settled_here"),
    ("the kept lines never stick below zero", S, " and consign.totals(rows[:n])[1] < 0:", " and False:",
     T + "test_s25_the_kept_lines_never_stick_below_zero"),
    ("Pay counts the lines it paid", S, '"lines_paid": len(p.get("lines") or []), ', "",
     T + "test_s4_pay_marks_it_paid_once_every_line_is_checked"),
    ("a paid payout whose lines changed stops every work-out", S, "        if changed:", "        if False:",
     T + "test_s26_a_paid_payout_whose_lines_changed_stops_every_work_out_and_pay"),
    ("the count is compared", C, 'and have.get(p["name"], 0) != p["lines_paid"])', "and False)",
     T + "test_s26_a_paid_payout_whose_lines_changed_stops_every_work_out_and_pay"),
    ("one draft a consignor", S, "        if drafts:", "        if False:",
     T + "test_s10_a_sale_cancelled_after_its_payout_was_paid_is_taken_back_once"),
    ("a moved item's paid line is held for good", S, '"sale_row", keys, t0, parent=consign.PAYOUT) if keys else []',
     '"sale_line", ["-"], t0, parent=consign.PAYOUT) if keys else []',
     T + "test_s23_a_paid_line_moved_to_another_consignor_is_never_paid_again"),
    ("the item's own share", C, 'shares[code] = share_of((it or {}).get("share")) or own', "shares[code] = own",
     T + "test_s1_work_out_writes_the_owed_lines_and_totals"),
    ("a share outside 0 to 100 refused", C, "    if d is None or d < 0 or d > 100:", "    if d is None:",
     R + "Share.test_a_share_outside_0_to_100_or_not_a_number_is_refused"),
    ("to the cent, half away from zero", C, "rounding=ROUND_HALF_UP)", "rounding=ROUND_HALF_EVEN)",
     R + "Part.test_to_the_cent_half_away_from_zero_a_return_the_same_negative"),
    ("money is exact", C, "        d = Decimal(str(v))", "        d = Decimal(v)", R + "Part.test_money_is_exact_never_a_float_rounding"),
    ("at most 500 lines", S, "        n = consign.MOST_LINES\n", "        n = len(rows)\n",
     T + "test_s12_at_most_500_lines_oldest_first_and_the_rest_wait"),
    ("pay needs how and when", C, '    if not payout.get("paid_with") or not date_of(payout.get("paid_on")):', "    if False:",
     T + "test_s5_pay_refuses_without_how_and_when_it_was_paid"),
    ("pay needs the lock on", C, '    if not lock or not lock.get("enabled") or lock.get("mode") != "refuse":', "    if not lock:",
     T + "test_s6_pay_refuses_while_the_lock_is_off"),
    ("a line twice on one payout", C, "    if len(set(keys)) != len(keys) or not all(keys):", "    if not all(keys):",
     T + "test_s7_pay_refuses_a_line_edited_by_hand_or_a_total_that_is_not_the_sum"),
    ("pay refuses a line another payout holds", C, "        if r.get(\"kind\") in (SALE, RETURN) and _row(r) in holds:",
     "        if False:", T + "test_s24_pay_refuses_a_line_another_consignors_payout_took_meanwhile"),
    ("pay compares every line", C, "        if not all(_same(r.get(f), want[f]) for f in COMPARED):", "        if False:",
     T + "test_s7_pay_refuses_a_line_edited_by_hand_or_a_total_that_is_not_the_sum"),
    ("pay needs the line still owed", C, "        if not want:", "        if False:",
     T + "test_s11_a_sale_cancelled_before_pay_stops_the_pay"),
    ("pay checks the totals", C, "    if total is None or total.quantize(CENT) != part or sales is None or sales.quantize(CENT) != sold:",
     "    if total is None or sales is None:",
     T + "test_s7_pay_refuses_a_line_edited_by_hand_or_a_total_that_is_not_the_sum"),
    ("pay refuses a negative total", C, "    if part < 0:\n        return (\"The returns", "    if False:\n        return (\"The returns",
     T + "test_s10_a_sale_cancelled_after_its_payout_was_paid_is_taken_back_once"),
    ("only a draft is paid", C, '    if payout.get("workflow_state") not in (DRAFT, None, ""):', "    if False:",
     R + "PayCheck.test_a_paid_or_cancelled_payout_is_never_paid_again"),
    ("only a draft is worked out", S, "        if (p.get(\"workflow_state\") or consign.DRAFT) != consign.DRAFT:", "        if False:",
     T + "test_s13_only_a_draft_and_only_with_a_consignor"),
    ("a work-out never writes over an edit", S, '"worked_out_by": user,\n                                                "modified": p.get("modified")}',
     '"worked_out_by": user}', T + "test_s15_an_edit_meanwhile_is_never_written_over"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s61-canary-")
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
