#!/usr/bin/env python3
"""S54's canaries: each test that guards a retailer's secret, its key, one run a press, the run's stores and dates, the
till's open days, the attribute's order, the sell-through, a press out of time, a report that is not the one asked, the
row cap, or the service's words must go RED when that check is removed. For each mutation this copies the sample (and
the kit folders it uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else
BROKEN), applies ONE change (the anchor must match exactly once, and a Python mutant must compile), runs the test again,
and reports RED (the test caught it) or GREEN (a dead test). The runner is S49's (S44's before it): a defect here is a
defect there.

    python3 samples/s54_sell_through/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, S, D = "test_service.ServiceTest.", "test_service.ManyRetailers.", "service/app.py", "sst.py"
C = "test_core."

CANARIES = [
    ("the press's signature is checked", S, "        if not secrets or all(sst.verify(ts, sig, raw, s.decode()) for s in secrets):",
     "        if not secrets:", T + "test_s6_a_press_signed_with_another_secret_or_too_old_is_refused_before_any_read"),
    ("a store named twice counts once", D, "        if s and s not in stores:", "        if s:",
     C + "RunOf.test_a_store_twice_or_blank_counts_once"),
    ("the colour attribute differs from the size", D, "    if colour == size:", "    if False:",
     C + "RunOf.test_each_misfilled_run_says_what_to_fix"),
    ("Sold since at most two years back", D, "    if (today - since).days > DAYS_MAX:", "    if False:",
     C + "RunOf.test_each_misfilled_run_says_what_to_fix"),
    ("a run or attribute not found is said in words", S, "            if e.code == 404:", "            if False:",
     T + "test_s13_a_run_or_attribute_not_found_is_said_in_words"),
    ("a stale press is refused", D, " or abs((now or time.time()) - int(ts)) > SKEW_S:", ":",
     T + "test_s6_a_press_signed_with_another_secret_or_too_old_is_refused_before_any_read"),
    ("one run a press", D, "    if len(ctx[\"records\"]) != 1:", "    if not ctx[\"records\"]:",
     T + "test_s7_a_press_on_anything_but_one_run_is_refused_before_any_read"),
    ("only runs are pressed", D, ' or rec.get("doctype") != RUN or not isinstance', " or not isinstance",
     T + "test_s7_a_press_on_anything_but_one_run_is_refused_before_any_read"),
    ("each retailer's own user key, never Administrator's", S, ' and k != "user:Administrator")', ")",
     M + "test_each_retailer_is_checked_with_its_own_secret_and_written_with_its_own_key_under_the_librarys_prefix"),
    ("a refused user is said in words", S, "            if e.code in (401, 403):", "            if False:",
     T + "test_s5_the_apps_user_refused_by_the_retailer_is_said_in_words"),
    ("a misfilled run reads nothing else", S, "        if isinstance(run, str):\n            return sst.message(run, \"warning\")",
     "        if isinstance(run, str):\n            pass", T + "test_s4_a_misfilled_run_is_said_in_words_and_reads_nothing_else"),
    ("at least one store", D, "    if not stores:\n", "    if False:\n", C + "RunOf.test_each_misfilled_run_says_what_to_fix"),
    ("at most 20 stores", D, "    if len(stores) > STORES_MAX:", "    if False:", C + "RunOf.test_each_misfilled_run_says_what_to_fix"),
    ("Sold since not after today", D, "    if since > today + datetime.timedelta(days=1):", "    if False:", C + "RunOf.test_each_misfilled_run_says_what_to_fix"),
    ("the sales report reads from Sold since", S, '"from_date": run.since.isoformat(), "to_date": (today + datetime.timedelta(days=1)).isoformat()}',
     '"from_date": "2000-01-01", "to_date": (today + datetime.timedelta(days=1)).isoformat()}', T + "test_s2_the_reads_name_the_group_the_dates_and_each_store"),
    ("the sales report reads to UTC's tomorrow", S, '"to_date": (today + datetime.timedelta(days=1)).isoformat()}', '"to_date": today.isoformat()}',
     T + "test_s2_the_reads_name_the_group_the_dates_and_each_store"),
    ("each store's own reports", S, "door.report(sst.POS_SALE_REPORT, dict(pos, warehouse=s), timeout=self.left(t0))",
     "door.report(sst.POS_SALE_REPORT, dict(pos, warehouse=run.stores[0]), timeout=self.left(t0))",
     T + "test_s1_a_press_writes_the_rows_of_the_runs_stores_in_the_retailers_order"),
    ("the stock report is the group's", S, '{"warehouse": s, "item_group": run.item_group},',
     '{"warehouse": s, "item_group": ""},', T + "test_s2_the_reads_name_the_group_the_dates_and_each_store"),
    ("a named style reads that style only", S, '            item_filters.append(["variant_of", "=", run.style])', "            pass",
     T + "test_s3_a_named_style_reads_that_style_only"),
    ("only enabled items", S, ', ["disabled", "=", 0]]', "]", T + "test_s2_the_reads_name_the_group_the_dates_and_each_store"),
    ("the till's open days leave stock", D, ' - _num(r.get("reserved_qty_for_pos"))', "",
     C + "Reports.test_stock_less_the_tills_open_days"),
    ("only the store's own warehouse", D, ' and r.get("warehouse") in (None, store):', ":",
     C + "Reports.test_stock_less_the_tills_open_days"),
    ("only the run's items are counted", D, '        if isinstance(item, str) and item in items:\n            out[item] = out.get(item, 0.0) + _num(r.get("unit_solds"))',
     '        if isinstance(item, str):\n            out[item] = out.get(item, 0.0) + _num(r.get("unit_solds"))',
     C + "Reports.test_pos_sale_report_by_its_column_names_as_lists_or_dicts"),
    ("a sales report without its columns is refused", D, '    if rows and not any("item" in r and "unit_solds" in r for r in rows):',
     "    if False:", T + "test_s12_a_report_answered_without_its_columns_writes_nothing"),
    ("a stock report without its columns is refused", D, '    if rows and not any("item_code" in r and "actual_qty" in r for r in rows):',
     "    if False:", C + "Reports.test_stock_less_the_tills_open_days"),
    ("an answer with no rows is refused", D, '        raise ValueError(f"{report} answered no rows")', "        return []",
     C + "Reports.test_a_sale_report_without_its_columns_is_refused"),
    ("a report made prepared is named with its cure", D, '    if isinstance(msg, dict) and msg.get("prepared_report"):', "    if False:",
     C + "Reports.test_a_sale_report_without_its_columns_is_refused"),
    ("a report's 417 or 403 is a refusal", S, "            if e.code in (403, 417):\n                raise ReportRefused(name, e.code) from None",
     "            if e.code in (403,):\n                raise ReportRefused(name, e.code) from None",
     T + "test_s5c_the_door_turns_a_reports_403_and_417_into_a_refusal_and_nothing_else"),
    ("a refused report is said in words", S, "            return 200, sst.message(REPORT_REFUSED.format(e.report), \"warning\")",
     "            raise", T + "test_s5b_a_report_refusing_the_apps_user_is_named_in_words"),
    ("number sizes go by number", D, "            return (1, float(size), \"\")", "            return (2, 0.0, size)",
     C + "Rows.test_number_sizes_without_a_list_go_by_number"),
    ("the stock call names no company", S, '{"warehouse": s, "item_group": run.item_group},',
     '{"company": "x", "warehouse": s, "item_group": run.item_group},', T + "test_s2_the_reads_name_the_group_the_dates_and_each_store"),
    ("sizes in the attribute's own order", D, '    rows.sort(key=lambda r: r.get("idx") if isinstance(r.get("idx"), int) else 0)', "",
     C + "Attributes.test_an_attributes_own_order"),
    ("a style's variants only", D, " or (run.style and style != run.style):", ":",
     C + "Attributes.test_a_named_style_keeps_its_own_variants_only"),
    ("an item with no size is left out", D, '    return {k: v for k, v in out.items() if v["size"]}', "    return out",
     C + "Attributes.test_the_groups_variants_with_their_size_and_colour"),
    ("sell-through counts negative stock as none", D, "    return round(100.0 * sold / (sold + max(in_stock, 0.0)), 1)",
     "    return round(100.0 * sold / (sold + in_stock), 1)", C + "Rows.test_sell_through"),
    ("nothing sold is 0 sold through", D, "    if sold <= 0:\n        return 0.0\n", "", C + "Rows.test_sell_through"),
    ("none left at 0 or below", D, '"none_left": 1 if stock_n <= 0 else 0', '"none_left": 0',
     T + "test_s1_a_press_writes_the_rows_of_the_runs_stores_in_the_retailers_order"),
    ("rows in the run's order of stores", D, "colour, size_key(size), place[store])", "colour, size_key(size), store)",
     T + "test_s1_a_press_writes_the_rows_of_the_runs_stores_in_the_retailers_order"),
    ("a row needs a sale or stock", D, "            if not s and not q:\n                continue\n", "",
     C + "Rows.test_rows_side_by_side_in_the_retailers_order"),
    ("too many rows write nothing", S, "        if len(rows) > sst.ROWS_MAX:", "        if False:",
     T + "test_s10_more_rows_than_a_run_holds_write_nothing"),
    ("a group too large to read is said", S, "        if len(item_rows) >= sst.ITEMS_MAX:", "        if False:",
     T + "test_s14_a_group_larger_than_one_run_reads_is_said"),
    ("no time for the save writes nothing", S, "        if BUDGET_S - (self.clock() - t0) < SAVE_FROM:", "        if False:",
     T + "test_s9_too_little_time_left_for_the_save_writes_nothing"),
    ("a read past the press's time writes nothing", S, '            raise TenantError("the press ran out of time")', "            pass",
     T + "test_s8_reads_that_take_the_press_time_write_nothing_and_say_so"),
    ("the reads go side by side", S, "max_workers=min(READERS, len(calls))", "max_workers=1",
     T + "test_s15_the_press_reads_side_by_side"),
    ("a press before the key is answered in words", S, "        if door is None:\n            return 200, sst.message(NOT_SET_UP, \"warning\")",
     "        if door is None:\n            return 502, {}", M + "test_a_press_before_the_key_arrives_is_answered_in_words_and_reads_nothing"),
    ("the library's prefix is required", S, "        if self.app and not prefix:", "        if False:",
     M + "test_the_library_prefix_is_required"),
    ("a record name is one path segment", S, 'urllib.parse.quote(p, safe="")', "urllib.parse.quote(p)",
     "test_service.ShopApi.test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed_and_a_report_is_a_form_post"),
    ("a redirect is never followed", S, "            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout or self.timeout) as r:",
     "            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:",
     "test_service.ShopApi.test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed_and_a_report_is_a_form_post"),
    ("the feed registration is frozen", "manifest.json", '"description": "the sell-through service reads the two reports and the items and writes the rows as this user; leave the feed off"',
     '"description": "the sell-through service reads the reports and writes the rows as this user; leave the feed off"',
     "test_manifest.ManifestTest.test_the_feed_registration_is_frozen"),
    ("the answer fits the extension point's words", D, 'body if len(body) <= 280 else body[:279] + "…"', "body",
     C + "Rows.test_every_answer_fits_the_extension_points_words"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s54-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local", "screenshots"))
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
