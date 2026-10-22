#!/usr/bin/env python3
"""S40's canaries: each test that guards a lot, a disposal, a receipt, a customer or a shop's secret must go RED when
that check is removed. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder,
runs the one test named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match
exactly once, and the mutant must compile), runs the test again, and reports RED (caught) or GREEN (a dead test). The
runner is S16's.

    python3 samples/s40_expiry_recall/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RC, CK, M, S, C = "test_recall.Recall.", "test_checks.", "test_many_shops.ManyShops.", "service/app.py", "recall.py"
W = "test_recall.Worklist."

CANARIES = [
    # the lot fence
    ("a lot with no expiry is never saved", C, '    if not date_of(lot.get("expiry_date")) and (item is None or item.get("has_expiry_date")):\n        return "no_expiry"\n', "",
     RC + "test_r2_a_lot_with_no_expiry_is_never_saved"),
    ("a lot already disabled is not written again", C, '    if lot.get("disabled"):\n        return "already"\n', "",
     RC + "test_r3_already_blocked_and_unknown_lots_are_named_and_not_written"),
    ("a lot's write carries the row as read", S, '{"disabled": 1, "modified": b.get("modified")}', '{"disabled": 1}',
     RC + "test_r1_a_lot_with_an_expiry_is_blocked_with_the_row_as_read"),
    ("a lot changed meanwhile is reported, never re-written", S, "                    if e.kind == STALE:\n                        outcome = \"changed\"",
     "                    if False:\n                        outcome = \"changed\"", RC + "test_r10_a_lot_changed_meanwhile_is_reported_and_not_written_over"),
    # the trace
    ("a POS sale's own bundle books no stock", C, ' or r.get("voucher_type") == "POS Invoice":', ":",
     RC + "test_r4_stock_found_per_store_from_the_ledger_never_a_pos_sales_own_bundle"),
    ("the ledger read keeps cancelled moves out", S, ', ["docstatus", "=", 1],\n                             ["is_cancelled", "=", 0]]', "]",
     RC + "test_r4_stock_found_per_store_from_the_ledger_never_a_pos_sales_own_bundle"),
    ("a till sale whose day is open is a customer", C, 'SALES = ("POS Invoice", "Sales Invoice", "Delivery Note")',
     'SALES = ("Sales Invoice", "Delivery Note")', RC + "test_r6_customers_supplied_at_consumer_depth_a_till_sale_before_and_after_its_day_closes"),
    ("customers only at consumer depth", S, '        if depth == "Consumer":\n            docs = {}', "        if True:\n            docs = {}",
     RC + "test_r7_retail_depth_traces_no_customer"),
    ("the clock never overwrites the notice's own", S, '        if not notice.get("complete_by") and done:', "        if done:",
     RC + "test_r8_the_clock_fills_what_the_notice_left_blank_and_never_overwrites"),
    ("a store's own status is kept", S, '{"qty_found": q, "modified": r.get("modified")}', '{"qty_found": q, "status": "To do", "modified": r.get("modified")}',
     RC + "test_r9_a_store_progress_per_store_and_a_stores_own_work_kept"),
    ("the pharmacist's action is kept", C, '"action": kept.get((r["batch_no"], r.get("warehouse") or "")) or "To check"', '"action": "To check"',
     W + "test_w3_the_pharmacists_action_is_kept_across_a_refresh"),
    ("only medicine lots are listed with no expiry", C, ' or not (items.get(b.get("item")) or {}).get("has_expiry_date")', "",
     W + "test_w4_medicine_lots_with_no_expiry_listed_and_others_not"),
    # receiving
    ("a short-dated lot is refused", C, "            if left >= least:\n                continue\n", "            continue\n",
     CK + "Receipt.test_c2_a_short_dated_lot_is_refused"),
    ("an LOU covers only its own days", C, "                if left < lou:", "                if False:",
     CK + "Receipt.test_c4_a_letter_of_undertaking_for_more_days_than_the_lot_has_is_refused"),
    ("an LOU needs its days", C, '        if line.get(f("lou")) and (whole(line.get(f("lou_days"))) or 0) <= 0:', "        if False:",
     CK + "Receipt.test_c5_a_letter_of_undertaking_with_no_days_is_refused"),
    ("an expired lot is refused before any exemption", C, "            if left <= 0:\n                out.append(f\"Row {i}: lot {lot} expired on {exp}.\")\n                continue\n", "",
     CK + "Receipt.test_c6_an_expired_lot_is_refused_even_exempt_or_with_a_letter"),
    ("a worked-out expiry asks for the pack's", C, "                if pack_needed or made is None or made + datetime.timedelta(days=life) == exp:",
     "                if False:", CK + "Receipt.test_c9_an_expiry_the_shop_may_have_worked_out_asks_for_the_packs"),
    ("an edited lot still needs the pack's date", C, "                if pack_needed or made is None or", "                if made is None or",
     CK + "Receipt.test_c9b_with_a_shelf_life_the_packs_date_is_needed_even_when_the_lots_dates_were_edited"),
    ("days left count from today", C, "    since = max(today, posting) if posting else today", "    since = posting or today",
     CK + "Receipt.test_c9d_a_backdated_receipt_counts_from_today"),
    ("a line rejected whole is not judged", C, '        if isinstance(line.get("qty"), (int, float)) and line["qty"] <= 0 and line.get("rejected_qty"):\n            continue',
     "        if False:\n            continue", CK + "Receipt.test_c9e_a_line_rejected_whole_is_not_judged"),
    ("the ERP user matched whatever its case", C, "user.strip().lower() in {u.lower() for u in", "user.strip() in {u for u in",
     CK + "Receipt.test_c9g_the_erp_user_is_matched_whatever_its_case"),
    ("the pack's date must be the lot's", C, "            if pack is not None and pack != exp:", "            if False:",
     CK + "Receipt.test_c10_a_pack_expiry_that_differs_from_the_lot_is_refused"),
    ("a line with no lot is refused", C, "        if not lots:\n            out.append(f\"Row {i}: name the lot", "        if False:\n            out.append(f\"Row {i}: name the lot",
     CK + "Receipt.test_c11_a_line_with_no_lot_or_a_lot_with_no_expiry_is_refused"),
    ("the bundle's lots are judged", C, "    for lot, q in (bundle_lots.get(line.get(\"serial_and_batch_bundle\")) or {}).items():", "    for lot, q in {}.items():",
     CK + "Receipt.test_c12_the_bundles_lots_are_judged"),
    ("the ERP's receipt is flagged, never refused", C, "    if erp:\n        return {\"verdict\": \"fill\"", "    if False:\n        return {\"verdict\": \"fill\"",
     CK + "Receipt.test_c16_the_erps_own_receipt_is_flagged_never_refused"),
    ("the supplier's number when the settings ask", C, '    if settings.get("supplier_note_required") and not', "    if False and not",
     CK + "Receipt.test_c14_the_suppliers_number_is_required_when_the_settings_say_so"),
    # disposal
    ("a disposal needs a record", C, "        if not rec_name:", "        if False:",
     CK + "Disposal.test_d1_a_controlled_disposal_with_no_record_is_refused"),
    ("the visit's signed form is needed", C, '("officer_name", "authority", "visit_date", "signed_form")', '("officer_name", "authority", "visit_date")',
     CK + "Disposal.test_d2_a_record_whose_visit_is_not_recorded_is_refused"),
    ("the record must cover the quantity", C, "            if covered.get((code, lot), 0.0) + 1e-9 < q:", "            if (code, lot) not in covered:",
     CK + "Disposal.test_d4_a_record_that_does_not_cover_the_quantity_or_the_lot_is_refused"),
    ("no schedule field is never 'not controlled'", C, "    if not isinstance(item_doc, dict) or field not in item_doc:\n        raise NoScheduleField(field)\n", "",
     CK + "Disposal.test_d5_an_item_without_the_schedule_field_is_refused_loudly"),
    ("any issue of a witnessed item is a disposal", C, '        if not written_off and not (leaves and line.get("t_warehouse") not in q_stores):',
     '        if not (leaves and line.get("t_warehouse") not in q_stores):', CK + "Disposal.test_d8b_any_issue_of_a_witnessed_item_is_a_disposal_damaged_good_stock_too"),
    ("stock leaving quarantine by any purpose", C, '        if not written_off and not (leaves and line.get("t_warehouse") not in q_stores):',
     "        if not written_off:", CK + "Disposal.test_d8c_stock_leaving_quarantine_for_anywhere_else_is_a_disposal_whatever_the_purpose"),
    ("one visit covers its lines once", C, "    for k, q in (used or {}).items():\n        covered[k] = covered.get(k, 0.0) - q\n", "",
     CK + "Disposal.test_d8d_one_visit_covers_its_lines_once"),
    ("the record is for the line's store", C, '        if record.get("store") and record["store"] != line.get("s_warehouse"):', "        if False:",
     CK + "Disposal.test_d8e_the_record_is_for_the_lines_store_and_its_visit_not_after_the_disposal"),
    ("the record must be locked", C, "        if not locked:", "        if False:",
     CK + "Disposal.test_d8f_records_not_locked_refuse_every_disposal"),
    ("quantities in the stock unit", C, '    for k in ("transfer_qty", "stock_qty"):', '    for k in ():',
     CK + "Disposal.test_d8g_quantities_are_compared_in_the_stock_unit"),
    ("a count never disposes", C, "        out.append(f\"Row {i}: a count may not dispose of {code}: issue it naming its Disposal Record.\")", "        pass",
     CK + "Count.test_k1_a_count_never_disposes_of_witnessed_quarantined_or_blocked_stock"),
    ("a lot of an item without expiry tracking is blocked", C, ' and (item is None or item.get("has_expiry_date"))', "",
     RC + "test_r2b_a_lot_of_an_item_that_does_not_track_expiry_is_blocked"),
    ("no progress record for a quarantine store", S, "{k: q for k, q in stock.items() if k[0] not in recall.quarantines(settings)}", "stock",
     RC + "test_r6c_no_store_progress_for_a_quarantine_store"),
    ("a recalled no-expiry lot is marked", S, '            m["recalled"] = 1 if m["batch"] in recalled else 0', '            m["recalled"] = 0',
     W + "test_w4b_a_no_expiry_lot_on_a_recall_notice_is_marked"),
    ("a schedule not yet in force does not count", C, "        if frm is None or on is None or frm <= on:", "        if True:",
     CK + "Disposal.test_d11_a_schedule_not_yet_in_force_does_not_count"),
    # wave 2: the re-grade and the critic
    ("the visit is not after the posting date", C, "        if visit is not None and visit > posting:", "        if False:",
     CK + "Disposal.test_d8h_a_visit_after_a_backdated_disposal_is_refused"),
    ("a consumption writes off", C, '        written_off = not line.get("t_warehouse") and not made', "        written_off = False",
     CK + "Disposal.test_d8i_a_consumption_writes_off_and_only_a_repack_into_a_witnessed_item_transforms"),
    ("a repack into an unscheduled item launders nothing", C, "            made = all(witnessed(", "            made = any(witnessed(",
     CK + "Disposal.test_d8i_a_consumption_writes_off_and_only_a_repack_into_a_witnessed_item_transforms"),
    ("no quarantine store is loud", C, "        if not q_stores:\n            out.append", "        if False:\n            out.append",
     CK + "Disposal.test_d8j_no_quarantine_store_named_refuses_a_disposal_loudly_and_nothing_else"),
    ("a flagging lock rule locks nothing", C, ' or (rule.get("mode") or "refuse") != "refuse":', ":",
     CK + "Disposal.test_d8k_a_lock_rule_left_on_but_made_to_flag_or_emptied_or_bypassed_locks_nothing"),
    ("the lock covers the visit's state", C, '    return f"{PREFIX} Visit recorded" in states and all(', "    return all(",
     CK + "Disposal.test_d8k_a_lock_rule_left_on_but_made_to_flag_or_emptied_or_bypassed_locks_nothing"),
    ("the lock covers the lines and the visit", C, " and all(k in fields_ for k in LOCKED_FIELDS) \\", " and True \\",
     CK + "Disposal.test_d8k_a_lock_rule_left_on_but_made_to_flag_or_emptied_or_bypassed_locks_nothing"),
    ("the lock covers the prior notice's date", C, '"visit_date", "signed_form", "prior_notice_on")', '"visit_date", "signed_form")',
     CK + "Disposal.test_d8k_a_lock_rule_left_on_but_made_to_flag_or_emptied_or_bypassed_locks_nothing"),
    ("the lock lets no role past", C, "        and not lines(rule.get(\"bypass_roles\"))", "        and True",
     CK + "Disposal.test_d8k_a_lock_rule_left_on_but_made_to_flag_or_emptied_or_bypassed_locks_nothing"),
    ("earlier draws in units", S, 'transfer_qty=(r.get("transfer_qty") or 0) * 1000)', 'transfer_qty=(r.get("transfer_qty") or 0))',
     CK + "Disposal.test_d8l_earlier_draws_are_read_in_units_and_this_entry_never_counts_against_itself"),
    ("this entry never counts against itself", S, '                                 ["name", "!=", fields.get("name") or ""]])', "                                 ])",
     CK + "Disposal.test_d8l_earlier_draws_are_read_in_units_and_this_entry_never_counts_against_itself"),
    ("the ERP's stock entry is flagged", S, "        if not erp:\n            return recall.disposal_answer(problems)", "        if True:\n            return recall.disposal_answer(problems)",
     CK + "Disposal.test_d8m_the_erps_stock_entries_are_flagged_never_refused"),
    ("the ERP's flag names the lot's worst first", C, "                    later.append(msg)", "                    out.append(msg)",
     CK + "Receipt.test_c9h_the_erps_receipt_is_never_asked_for_a_pack_date_and_still_flags_an_expired_lot"),
    ("another depth never wipes customers", S, '        if depth == "Consumer":         # a press at another depth', '        if True:         # a press at another depth',
     RC + "test_r15_a_press_at_another_depth_never_wipes_customers_already_traced"),
    ("only the listed schedules", C, "    return bool(have) and (not wanted or any(s in wanted for s in have))", "    return bool(have)",
     CK + "Disposal.test_d10_only_the_listed_schedules_need_the_visit"),
    ("an unreadable item is refused", C, '            out.append(f"Row {i}: the app could not read item {code}.")', "            pass",
     CK + "Receipt.test_c20_an_item_the_app_cannot_read_is_refused"),
    ("a record that is not there is refused", S, "                if e.code != 404:\n                    raise\n            # what earlier", "                raise\n            # what earlier",
     CK + "Disposal.test_d16_a_record_that_is_not_there_is_refused"),
    ("no settings refuses a disposal", S, "        settings = self.settings(door)\n        if settings is None:\n            return {\"verdict\": \"refuse\", \"reason\": recall.fit(NO_SETTINGS)}\n        erp = recall.is_erp(ctx.get(\"user\"), settings)\n        if not erp and",
     "        settings = self.settings(door) or {}\n        erp = recall.is_erp(ctx.get(\"user\"), settings)\n        if not erp and", CK + "Disposal.test_d15_no_settings_refuses_a_disposal_and_a_count"),
    # the shop's secrets and keys
    ("each door has its own secret", S, '            return [s for s in [self.secrets.get(sub)] if s], self.tenant',
     '            return [s for s in self.secrets.values() if s], self.tenant', RC + "test_r13_a_press_must_be_signed_with_the_buttons_own_secret"),
    ("the signature is checked", S, "        if not secrets or all(recall.verify(ts, sig, raw, s, self.now) for s in secrets):",
     "        if not secrets:", M + "test_another_shops_or_another_doors_secret_and_an_unknown_site_are_refused"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")", M + "test_administrators_key_is_never_used"),
    ("the library's fields follow its prefix", C, '    PREFIX, P = prefix, prefix.lower().replace(" ", "_")', '    PREFIX = prefix',
     M + "test_the_receipt_reads_the_librarys_item_fields"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s40-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local"))
        for sub in ("tools/manifest", "tools/app_template", "tools/contracts", "contracts"):
            shutil.copytree(os.path.join(kit, sub), os.path.join(tmp, "r", sub), ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:
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
