#!/usr/bin/env python3
"""S44's canaries: each test that guards a shop's secret, its key, the walk-in customer, a return, the campaign's days,
tills and groups, a customer winning once, the fairness of the pool, a draw never repeated or written over someone's
edit, or the service's words must go RED when that check is removed. For each mutation this copies the sample (and the
kit folders it uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN),
applies ONE change (the anchor must match exactly once, and the mutant must compile), runs the test again, and reports
RED (the test caught it) or GREEN (a dead test). The runner is S16's, by way of S38's.

    python3 samples/s44_lucky_draw/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, S, D = "test_service.ServiceTest.", "test_many_shops.", "service/app.py", "draw.py"
R = "test_rules."

CANARIES = [
    ("the signature is checked", S, "        if not secrets or all(draw.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", T + "test_s18_each_button_takes_only_its_own_secret"),
    ("each button its own secret", S, '        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{sub}")]',
     '        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:count")]',
     M + "ManyShops.test_each_button_has_its_own_secret"),
    ("each shop's own user key", S, 'if k.startswith("user:") and k != "user:Administrator")', 'if ":" in k)',
     M + "ManyShops.test_each_shop_is_written_with_its_own_key_under_the_librarys_prefix"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a press before the shop's key arrives is answered in words", S, "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n",
     "", M + "ManyShops.test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403):", "            if False:",
     T + "test_s14_the_apps_user_refused_by_the_shop_is_said_in_words"),
    ("the walk-in customer is never an entry", D, "        if not customer or customer in walk_ins or not day", "        if not customer or not day",
     T + "test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign"),
    ("returns are netted", D, "        n = int(((total + back.get(s[\"name\"], Decimal(0))) / rules.spend)",
     "        n = int(((total) / rules.spend)", T + "test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign"),
    ("only submitted returns", S, '                            [["docstatus", "=", 1], ["is_return", "=", 1],',
     '                            [["is_return", "=", 1],', T + "test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign"),
    ("only submitted sales", S, '        sale_filters = [["docstatus", "=", 1], ["is_return", "=", 0],',
     '        sale_filters = [["is_return", "=", 0],', T + "test_s19_the_sales_read_asks_only_for_the_campaigns_submitted_till_sales"),
    ("only the campaign's company", S, '["is_return", "=", 0], ["company", "=", rules.company],',
     '["is_return", "=", 0],', T + "test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign"),
    ("rounded down, never up", D, ".to_integral_value(rounding=ROUND_FLOOR))", ".to_integral_value())",
     R + "Entries.test_entries_are_the_net_total_divided_rounded_down"),
    ("money is exact", D, "        d = Decimal(str(v))", "        d = Decimal(v)",
     R + "Entries.test_money_is_exact_never_a_float_rounding"),
    ("the most per sale caps", D, "        if rules.most:\n            n = min(n, rules.most)\n", "",
     T + "test_s4_most_entries_per_sale_caps_a_sale"),
    ("the campaign's days in the core too", D, " or not rules.start <= day <= rules.end:", ":",
     R + "Entries.test_outside_the_days_or_tills_or_groups_or_walk_in_is_no_entry"),
    ("the campaign's tills", D, "        if rules.tills and s.get(\"pos_profile\") not in rules.tills:\n            continue\n", "",
     R + "Entries.test_outside_the_days_or_tills_or_groups_or_walk_in_is_no_entry"),
    ("the groups below a group", D, "any(l <= g[\"lft\"] and g[\"rgt\"] <= r", "any(l == g[\"lft\"] and g[\"rgt\"] == r",
     T + "test_s6_a_customer_group_takes_its_groups_below_it"),
    ("sale order is date, time, number", D, "    out.sort()\n", "",
     R + "Entries.test_the_order_is_date_then_time_then_number"),
    ("a customer wins once", D, "        pool = [p for p in pool if entries[p][1] != customer]", "        pool = [p for p in pool if p != i]",
     R + "Draw.test_a_customer_wins_once_and_the_numbers_are_the_whole_lists"),
    ("each entry the same chance", D, "            at += entries[i][2]", "            at += 1",
     R + "Draw.test_each_entry_has_the_same_chance"),
    ("the drawn number is the whole list's", D, "        number = first[i] + r - (ends[j - 1] if j else 0)", "        number = r + 1",
     T + "test_s8_the_draw_writes_winners_then_reserves_each_customer_once_and_its_record"),
    ("winners first, then reserves", D, '"Winner" if i < winners else "Reserve"', '"Winner"',
     R + "Draw.test_results_rank_winners_then_reserves"),
    ("a draw is never repeated", S, '        if sub == "draw" and draw.already_drawn(c):', "        if False:",
     T + "test_s9_a_second_draw_finds_drawn_and_writes_nothing"),
    ("a draw's record left on it counts as drawn", D, ' or any(c.get(k) for k in DRAW_RECORD) or bool(c.get("results"))', "",
     T + "test_s21_a_status_set_back_to_open_by_hand_draws_nothing"),
    ("the order is the real time", D, "            out.append((day, seconds_of(s.get(\"posting_time\")), s[\"name\"], customer, n))",
     "            out.append((day, str(s.get(\"posting_time\") or \"\"), s[\"name\"], customer, n))",
     R + "Entries.test_the_order_is_the_real_time_as_the_shop_sends_it"),
    ("the total is what the customer paid", D, '    return rounded if rounded else _money(sale.get("base_grand_total"))',
     '    return _money(sale.get("base_grand_total"))', R + "Entries.test_the_total_is_what_the_customer_paid"),
    ("hours from UTC in range", D, "                                    or not -12 <= hours <= 14):", "                                    or False):",
     R + "Rules.test_a_rule_is_read_or_named_in_a_sentence"),
    ("a press out of time writes nothing", S, "        self.left(t0)                   # out of time after the reads: nothing is written\n", "",
     T + "test_s22_a_press_out_of_time_writes_nothing"),
    ("no draw before the campaign ends", S, '        if sub == "draw" and draw.today_at(c.get("hours_from_utc"), now) <= rules.end:',
     "        if False:", T + "test_s7_a_draw_before_the_last_day_ends_at_the_shop_is_refused_and_writes_nothing"),
    ("the shop's day, not UTC", D, "    return (t + datetime.timedelta(hours=hours if", "    return (t + datetime.timedelta(hours=0 if",
     R + "Rules.test_the_shops_day_is_utc_moved_by_its_hours"),
    ("a write carries the campaign as read", S, '"count_fingerprint": mark, "modified": c.get("modified")}',
     '"count_fingerprint": mark}', T + "test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign"),
    ("a stale write is said in words", S, "            if e.kind == STALE:", "            if False:",
     T + "test_s10_an_edit_saved_while_the_press_read_is_never_written_over"),
    ("a count keeps the draw's record", S, '        if sub == "count":              # a count after the draw',
     '        if False:              # a count after the draw', T + "test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign"),
    ("a draw with no entries writes nothing", S, "            if not n:\n                return draw.count_answer(entries)",
     "            if False:\n                return draw.count_answer(entries)", T + "test_s16_a_draw_with_no_entries_writes_nothing"),
    ("a bad rule reads no sales", S, "        if isinstance(rules, str):\n            return _warning(rules)\n",
     "        if isinstance(rules, str):\n            rules = draw.Rules('PP Co', draw.date_of('2026-10-01'), draw.date_of('2026-10-31'), 1, 0, 1, 0, [], [])\n",
     T + "test_s13_a_rule_that_cannot_be_read_is_said_in_words_and_reads_no_sales"),
    ("winners at most 50", D, "    if winners is None or not 1 <= winners <= MOST_WINNERS:", "    if winners is None or not 1 <= winners:",
     T + "test_s13_a_rule_that_cannot_be_read_is_said_in_words_and_reads_no_sales"),
    ("one campaign a press", D, '    if len(ctx["records"]) != 1:', '    if not ctx["records"]:',
     T + "test_s17_a_press_on_anything_but_one_campaign_is_refused_before_any_read"),
    ("a long body is cut", D, '    return text if len(text) <= most else text[: most - 1] + "…"', "    return text",
     R + "Answers.test_every_answer_fits_the_answers_limit"),
    ("the prefix names the record type", D, '    PREFIX, CAMPAIGN = prefix, f"{prefix} Campaign"', "    pass",
     M + "Prefix.test_the_record_type_follows_the_prefix_and_the_manifest_names_it"),
    ("a redirect is not followed", S, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a record name is one path segment", S, 'urllib.parse.quote(p, safe="")', "urllib.parse.quote(p)",
     M + "ShopApi.test_a_record_name_is_one_path_segment"),
    ("a cut answer is an unknown outcome", S, "(OSError, ValueError, http.client.HTTPException) as e:     # OSError",
     "(OSError, ValueError) as e:     # OSError", M + "ShopApi.test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash"),
    ("the function checks the signature too", S, "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'ok': 1}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     M + "AsAFunction.test_health_a_signed_press_either_body_form_and_a_refusal"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s44-canary-")
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
