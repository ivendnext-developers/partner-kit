#!/usr/bin/env python3
"""S45's canaries: each test that guards a shop's secret, its key, a sale issued once, stock never issued twice, a short
part named, the press stamp, the recipe's arithmetic, the food cost's sorting of the ledger, the allergen check or the
service's words must go RED when that check is removed. For each mutation this copies the sample (and the kit folders
it uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN), applies ONE
change (the anchor must match exactly once, and the mutant must compile), runs the test again, and reports RED (the test
caught it) or GREEN (a dead test). The runner is S38's.

    python3 samples/s45_restaurant_back_office/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, R = "test_service.ServiceTest.", "test_many_shops.", "test_rules."
S, B = "service/app.py", "backoffice.py"

CANARIES = [
    # the press and the shop
    ("the signature is checked", S, "        if not secrets or all(bo.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", T + "test_p1_an_unsigned_or_wrongly_signed_press_is_refused"),
    ("each button its own secret", S, 'secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{sub}")]',
     'secrets = [v for k, v in (record or {}).get("secrets", {}).items() if ":sub:" in k]',
     M + "ManyShops.test_another_buttons_secret_another_shops_an_unknown_site_and_no_site_are_refused"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a press before the shop's key arrives is answered in words", S, "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n",
     "", M + "ManyShops.test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403):    # the shop refused the app's user: say so",
     "            if False:", T + "test_i18_the_apps_user_refused_is_said_in_words"),
    ("a press names its own record type", S, '                names = bo.records_of(body, bo.dt("Settings"), most=1)',
     '                names = [r["name"] for r in body["context"]["records"]]',
     T + "test_p2_a_press_on_the_wrong_record_is_refused_before_anything_is_read"),
    # a sale issued once, stock never twice
    ("the issue claims its sales before the stock entry", S, '                    doc = door.create(bo.dt("Issue"), body)      # FIRST: it claims the sales\n',
     "", T + "test_i2_the_issue_is_written_before_the_stock_entry"),
    ("sales an issue names are never taken again", S, ' and x["name"] not in claimed and', " and",
     T + "test_i3_a_press_again_books_nothing_twice"),
    ("an entry already made is found by its link", S, "        if found:                       # an earlier press made it",
     "        if False:                       # an earlier press made it",
     T + "test_i10_a_press_that_stopped_after_its_stock_entry_books_nothing_twice"),
    ("the entry carries its issue's link", B, ' "from_warehouse": issue["issue_from"], f"{FIELD}_issue": issue["name"],',
     ' "from_warehouse": issue["issue_from"],', T + "test_i10_a_press_that_stopped_after_its_stock_entry_books_nothing_twice"),
    ("an unknown outcome leaves the issue Pending", S,
     "                if e.code is None or e.code in (401, 403) or (e.code >= 500 and e.kind != SHORT):",
     "                if e.code in (401, 403):", T + "test_i10_a_press_that_stopped_after_its_stock_entry_books_nothing_twice"),
    ("the start moment", S, " and bo.booked_from(x, start)),", "),", T + "test_i5b_a_start_in_the_middle_of_a_day_takes_only_the_sales_after_it"),
    ("no start, no issue", S, "        if not start:\n            return _warning(NO_START)\n", "",
     T + "test_i6_no_start_date_no_issue"),
    ("only booked sales", S, '[["company", "=", company], ["docstatus", "=", 1], ["posting_date", ">=", since]]',
     '[["company", "=", company], ["posting_date", ">=", since]]', T + "test_i17_a_cancelled_or_draft_sale_is_never_issued"),
    ("a sale amended in Desk is taken when the sale it amends was", S,
     "        claimed |= {x for x in amends if bo.taken_before(x, amends, claimed)}\n", "",
     T + "test_i17b_a_sale_cancelled_and_amended_in_desk_is_not_issued_again"),
    ("every amendment back to the first sale", B, "        name = amends.get(name)\n        if name in claimed:",
     "        if amends.get(name) in claimed:", R + "Groups.test_g9_a_sale_amended_in_desk_is_taken_when_any_sale_it_amends_was"),
    ("store-days that share a sale are written together", B,
     '        joined = [x for x in sets if any(owner.get(s) is x for s in groups[key]["sales"])]', "        joined = []",
     T + "test_i14b_a_sale_whose_lines_left_two_stores_is_issued_at_both_though_the_time_runs_out"),
    ("a dish sold with no recipe is named", B, "                dishes.append(note)", "                pass",
     R + "Groups.test_g7_a_dish_with_no_recipe_issues_nothing_and_is_named"),
    ("a line counts in its stock unit", B, 'qty = num(ln.get("stock_qty")) or num(ln.get("qty"))', 'qty = num(ln.get("qty"))',
     R + "Groups.test_g8_a_line_sold_in_another_unit_counts_in_the_stock_unit"),
    ("a recipe row counts in its part's stock unit", B, 'per = row.get("item_code"), num(row.get("stock_qty")) / num(bom["quantity"])',
     'per = row.get("item_code"), num(row.get("qty") or row.get("stock_qty")) / num(bom["quantity"])',
     R + "Recipes.test_r4b_a_recipe_row_counts_in_its_parts_stock_unit"),
    ("the signature's time window", B, " or abs((now or time.time()) - int(ts)) > SKEW_S:", ":",
     T + "test_p1b_a_press_stamped_outside_the_window_is_refused"),
    # short and refused
    ("every short part is named", B, "        if have + 1e-9 < num(p[\"qty\"]):\n            out.append((p[\"item_code\"], num(p[\"qty\"]), have))",
     "        if have + 1e-9 < num(p[\"qty\"]):\n            out.append((p[\"item_code\"], num(p[\"qty\"]), have))\n            break",
     T + "test_i7_short_names_every_part_and_takes_nothing"),
    ("short at the sales' time is tried at the press", S, "                if e.kind == SHORT and not now:\n                    continue\n",
     "", T + "test_i8_short_at_the_sales_time_is_booked_at_the_press_once_stock_is_in"),
    ("a short issue later is booked at the press", S, '        for now in ([True] if issue.get("status") == "Short" else [False, True]):',
     "        for now in [False]:", T + "test_i9_a_short_issue_is_issued_by_a_later_press_once_the_delivery_is_in"),
    ("an entry at the press carries no date", B, '    when = {} if now else {"posting_date"', '    when = {"posting_date"',
     T + "test_i8_short_at_the_sales_time_is_booked_at_the_press_once_stock_is_in"),
    ("the shop's own words kept", S, '"Not issued: the shop refused the stock entry" + (f": {e.said}" if e.said',
     '"Not issued: the shop refused the stock entry" + (f": {e.kind}" if e.said',
     T + "test_i15_the_shops_refusal_is_kept_on_the_issue_in_its_own_words"),
    # the press stamp
    ("a running press holds the company", S, "        if age is not None and -LOCK_S < age < LOCK_S:\n            raise Busy()\n", "",
     T + "test_i11_another_press_running_touches_nothing"),
    ("the stamp names the record as read", S, '{"run_started": mine, "modified": s.get("modified")}', '{"run_started": mine}',
     T + "test_i12_two_presses_stamping_at_once_one_loses"),
    ("the stamp is cleared", S, "            self._unlock(door, settings_name, mine)", "            pass",
     T + "test_i13_a_dead_presss_stamp_is_taken_over_and_every_stamp_is_cleared"),
    ("a press stops in time", S, "            for keys in bo.sharing_sales(groups):\n                if self.clock() - t0 > BUDGET_S:\n"
     "                    left = True\n                    break\n", "            for keys in bo.sharing_sales(groups):\n",
     T + "test_i14_the_budget_leaves_the_rest_for_the_next_press"),
    # the recipe's arithmetic
    ("per unit the recipe makes", B, 'num(row.get("stock_qty")) / num(bom["quantity"])', 'num(row.get("stock_qty"))',
     R + "Recipes.test_r1_a_dish_takes_its_recipes_parts_per_unit_made"),
    ("a part not stocked is opened", B, "        if (items.get(part) or {}).get(\"is_stock_item\"):\n            got, why = {part: need}, []",
     "        if True:\n            got, why = {part: need}, []", R + "Recipes.test_r2_a_dish_inside_a_dish_is_opened_too"),
    ("a stock item sold is never opened", B, "    if meta.get(\"is_stock_item\"):\n        return {item: qty}, []\n", "",
     R + "Recipes.test_r4_a_stock_item_sold_is_never_opened"),
    ("a loop is refused", B, "    if bom_name in seen or depth >= DEPTH:\n        raise RecipeError(f\"{item}'s recipe {bom_name} goes round in a loop or deeper than {DEPTH} recipes\")\n    bom = boms.get(bom_name)",
     "    bom = boms.get(bom_name)", R + "Recipes.test_r5_a_recipe_that_goes_round_is_refused"),
    ("a return takes nothing back", B, '        if ln["qty"] <= 0:\n            continue\n', '',
     R + "Groups.test_g6_a_return_takes_nothing_back_and_a_stock_item_is_not_issued"),
    ("one issue per store and day", B, '        key = (store, str(sale.get("posting_date"))[:10])', '        key = (store, "")',
     R + "Groups.test_g1_one_issue_per_store_and_day"),
    ("a part of the day past midnight", B, "        if (a <= t < b) if a < b else (t >= a or t < b):", "        if a <= t < b:",
     R + "Groups.test_g8_day_parts"),
    ("the kitchen store", B, '"issue_from": kitchen or store,', '"issue_from": store,',
     R + "Groups.test_g5_a_kitchen_store_issues_for_every_store"),
    ("no account of the app's", B, '        rows.append(row)\n    when', '        row["expense_account"] = "x"\n        rows.append(row)\n    when',
     R + "Records.test_d2_the_stock_entry_is_the_shops_own_material_issue_submitted_in_one_call"),
    # food cost
    ("receipts and transfers are not use", B, '        elif vt == "Stock Entry" and vn in other_issues:', '        elif vt == "Stock Entry":',
     R + "FoodCost.test_f1_theoretical_against_actual"),
    ("the count's own figures", B, 'num(c.get("current_qty")) - num(c.get("qty"))', 'num(c.get("qty")) - num(c.get("current_qty"))',
     R + "FoodCost.test_f1_theoretical_against_actual"),
    ("a sale's return counts back", B, '        q, v = -num(e.get("actual_qty")), -num(e.get("stock_value_difference"))',
     '        q, v = abs(num(e.get("actual_qty"))), abs(num(e.get("stock_value_difference")))',
     R + "FoodCost.test_f1_theoretical_against_actual"),
    ("an edit meanwhile is never written over", S, 'door.update(bo.dt("Food Cost"), name, dict(got, worked_out_at=when, modified=fc.get("modified")))',
     'door.update(bo.dt("Food Cost"), name, dict(got, worked_out_at=when))',
     T + "test_f3_an_edit_while_it_was_worked_out_is_never_written_over"),
    ("a period of at most 92 days", S, "        if (b - a).days >= MOST_DAYS:", "        if False:",
     T + "test_f2_a_period_too_long_or_back_to_front_is_refused_in_words"),
    # allergens
    ("allergens at every depth", B, '            out |= recipe_items(part, items, boms, depth + 1, seen + (bom_name,), row.get("bom_no"))', "            pass",
     R + "Allergens.test_a3_a_dish_inside_a_dish_carries_its_allergens"),
    ("an allergen compared without case", B, '    have = {w.lower() for w in words_of(allergens.get(dish))}',
     '    have = set(words_of(allergens.get(dish)))', R + "Allergens.test_a1_a_dish_missing_an_allergen_of_its_recipe_at_any_depth"),
    ("a word not on the list is named", S, "                if bad:\n", "                if False:\n",
     T + "test_a1_every_finding_is_written_to_a_check_record_the_answer_opens"),
    ("a long body is cut", B, '    return text if len(text) <= most else text[: most - 1] + "…"', "    return text",
     R + "Calls.test_c3_a_long_body_is_cut"),
    # the library's copy and the shop's door
    ("the prefix names the record types and fields", B, '    PREFIX, FIELD = prefix, prefix.lower().replace(" ", "_")', "    PREFIX = prefix",
     M + "Prefix.test_the_record_types_and_fields_follow_the_prefix_and_the_manifest_names_them"),
    ("a redirect is not followed", S, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a record name is one path segment", S, 'urllib.parse.quote(p, safe="")', "urllib.parse.quote(p)",
     M + "ShopApi.test_a_record_name_is_one_path_segment"),
    ("a cut answer is an unknown outcome", S, "(OSError, ValueError, http.client.HTTPException) as e:     # OSError",
     "(OSError, ValueError) as e:     # OSError", M + "ShopApi.test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash"),
    ("a table is read through its record type", S, '            q["parent"] = parent', "            pass",
     M + "ShopApi.test_a_record_and_a_tables_rows_are_read_with_the_token"),
    ("the function checks the signature too", S, "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'ok': 1}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     M + "AsAFunction.test_health_a_signed_press_either_body_form_and_a_refusal"),
    ("an issue is tried once a press", S, '        stuck = sorted((r for r in stuck if r["name"] not in touched),',
     '        stuck = sorted((r for r in stuck),', T + "test_i7_short_names_every_part_and_takes_nothing"),
    ("a time is read as numbers", B, '    return f"{str(sale.get(\'posting_date\'))[:10]} {clock_of(sale.get(\'posting_time\')) or \'00:00:00\'}" >= start',
     '    return f"{str(sale.get(\'posting_date\'))[:10]} {str(sale.get(\'posting_time\')).split(\'.\')[0].zfill(8)}" >= start',
     R + "Groups.test_g7b_a_time_the_shop_prints_without_its_leading_zero"),
    ("an ingredient's template's allergens", S, "        words = {k: own.get(k) if bo.words_of(own.get(k)) else own.get(v.get(\"variant_of\")) for k, v in items.items()}",
     "        words = own", T + "test_a4b_an_ingredient_that_is_a_variant_carries_its_templates_allergens"),
    ("a clean check writes no record", S, "        if not rows:                    # nothing to show: no record is written\n",
     "        if False:\n", T + "test_a4_a_dish_naming_them_all_writes_nothing_and_says_so"),
    # the folds of the Tier-S review
    ("a lost answer keeps the stamp", S, "            unknown = e.code is None or e.code >= 500", "            unknown = False",
     T + "test_i10_a_press_that_stopped_after_its_stock_entry_books_nothing_twice"),
    ("a lost answer on the issue keeps the stamp", S, "            if not unknown:\n                self._unlock(door, settings_name, mine)",
     "            self._unlock(door, settings_name, mine)", T + "test_i10b_a_lost_answer_on_the_issue_itself_keeps_the_stamp_too"),
    ("a recipe that goes round is refused, not booked", S, '                    if problem:     # claimed as Refused: a retry works it out again from the recipes and settings then\n                        body.update(status="Refused", problem=problem)',
     "                    pass", T + "test_i16b_a_store_day_whose_recipe_goes_round_is_refused_and_issued_once_it_is_fixed"),
    ("no store, no call to the shop", S, '        if not issue_from:\n            door.update(bo.dt("Issue"), name, {"status": "Refused", "problem": NO_STORE})\n            return "refused"\n',
     "", T + "test_i16b2_sales_with_no_store_are_refused_without_a_call_until_a_kitchen_store_is_chosen"),
    ("Short before Refused", S, '                       key=lambda r: (r.get("status") != "Short", str(r.get("posting_date")), r["name"]))',
     '                       key=lambda r: (str(r.get("posting_date")), r["name"]))', T + "test_i16c2_short_is_tried_before_refused_and_the_rest_are_counted"),
    ("an entry named by an issue is the app's at any date", S, '        named = {r.get("stock_entry") for r in door.rows_in(bo.dt("Issue"), ["stock_entry"], "stock_entry",',
     '        named = {r.get("stock_entry") for r in door.rows_in(bo.dt("Issue"), ["stock_entry"], "posting_date",',
     T + "test_f1c_an_issue_booked_long_after_its_sales_is_still_the_apps"),
    ("a retry works the parts out again", S, '        door.update(bo.dt("Issue"), name, {"parts": parts, "issue_from": issue_from, "lines": lines})\n        return self._book(door, company, dict(issue, parts=parts, issue_from=issue_from))',
     '        return self._book(door, company, issue)', T + "test_i16c_a_refused_issue_is_tried_again_with_the_recipe_as_it_is_now"),
    ("an issue left out is never tried again", S, '["status", "in", ["Short", "Refused"]]])', '["status", "in", ["Short", "Refused", "Left out"]]])',
     T + "test_i16d_an_issue_left_out_is_never_tried_again"),
    ("new sales before old retries", S, "        # 2. the sales no issue names yet\n",
     "        for old in door.rows(bo.dt(\"Issue\"), [\"name\"], [[\"company\", \"=\", company], [\"status\", \"in\", [\"Short\", \"Refused\"]]]):\n"
     "            if self.clock() - t0 > BUDGET_S:\n                return self._answer(out, left=True)\n"
     "            out[self._retry(door, company, s, old[\"name\"], items, boms)] += 1\n        # 2. the sales no issue names yet\n",
     T + "test_i16e_new_sales_come_before_old_retries"),
    ("a stocked sauce's recipe is read for allergens", S, "        self._recipes(door, names, items, boms, deep=True)",
     "        self._recipes(door, names, items, boms)", T + "test_a2_a_stocked_sauces_own_recipe_is_read_for_its_allergens"),
    ("a variant's blank allergens are named", B, "    if tpl and not words_of(allergens.get(item)) and words_of(allergens.get(tpl)):",
     "    if False:", T + "test_a3_a_variant_with_none_of_its_templates_allergens_is_named"),
    ("the check opens its record", S, '            out["open_record"] = {"doctype": bo.dt("Allergen Check"), "name": doc.get("name")}', "            pass",
     T + "test_a1_every_finding_is_written_to_a_check_record_the_answer_opens"),
    ("no list is said", S, '        if not known:\n            rows.append(', '        if False:\n            rows.append(',
     T + "test_a5_no_allergen_list_is_said_on_the_check"),
    ("a Desk copy is the shop's own", S, '        ours = {r["name"] for r in issues if r["name"] in named\n',
     '        ours = {r["name"] for r in issues if r.get(f"{bo.FIELD}_issue") or r["name"] in named\n',
     T + "test_f1b_a_desk_copy_is_the_shops_own_and_an_entry_from_before_a_reinstall_is_the_apps"),
    ("an entry from before a reinstall is the app's", S, '                or (not r.get(f"{bo.FIELD}_issue") and bo.ours_by_remarks(r.get("remarks")))}',
     '                or False}', T + "test_f1b_a_desk_copy_is_the_shops_own_and_an_entry_from_before_a_reinstall_is_the_apps"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s45-canary-")
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
