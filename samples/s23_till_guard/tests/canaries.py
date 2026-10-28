#!/usr/bin/env python3
"""S23's canaries: each test that guards a rule, a secret or the shop's settings must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S22's.

    python3 samples/s23_till_guard/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CANARIES = [
    ("the signature is checked", "service/app.py", "if not secrets or all(guard.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", "test_service.OneShop.test_each_route_takes_only_its_own_secret"),
    ("each route takes its own secret (one shop)", "service/app.py", 'return "-", [self.secrets[route_key]], self.shop',
     'return "-", list(self.secrets.values()), self.shop', "test_service.OneShop.test_each_route_takes_only_its_own_secret"),
    ("each route takes its own secret (many shops)", "service/app.py", 'f"{self.app}:sub:{route_key}"',
     'f"{self.app}:sub:guard"', "test_service.ManyShops.test_the_scan_route_takes_the_scan_secret_only"),
    ("an old timestamp is refused", "guard.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     "test_service.OneShop.test_an_old_timestamp_is_refused"),
    ("the placeholder price is refused", "guard.py", "if floor and 0 < line", "if False and 0 < line",
     "test_guard.CheckRules.test_a_line_at_the_placeholder_price_is_refused_in_our_words"),
    ("a free line is never refused", "guard.py", "0 < line[\"rate_minor\"] <= floor", "line[\"rate_minor\"] <= floor",
     "test_guard.CheckRules.test_a_free_line_priced_zero_is_never_refused"),
    ("more than the most is refused", "guard.py", "if most and line", "if False and line",
     "test_guard.CheckRules.test_more_than_the_most_on_one_line_is_refused"),
    ("exactly the most is allowed", "guard.py", 'line["qty_milli"] > most', 'line["qty_milli"] >= most',
     "test_guard.CheckRules.test_exactly_the_most_is_allowed"),
    ("the approval amount itself needs a manager", "guard.py", 'ctx["totals"]["grand_minor"] >= limit',
     'ctx["totals"]["grand_minor"] > limit', "test_guard.CheckRules.test_a_large_sale_calls_a_manager"),
    ("what a return takes back is never judged", "guard.py", 'for line in ctx["lines"] if line["qty_milli"] > 0]',
     'for line in ctx["lines"]]', "test_guard.CheckRules.test_what_a_return_takes_back_is_never_judged"),
    ("an exchange's returned line is not judged", "guard.py", 'for line in ctx["lines"] if line["qty_milli"] > 0]',
     'for line in ctx["lines"]]', "test_guard.CheckRules.test_an_exchanges_returned_line_is_not_judged"),
    ("an exchange's sold line is judged", "guard.py", "    sold = sold_lines(ctx)\n",
     '    sold = sold_lines(ctx) if ctx["stage"] == "sale" else []\n',
     "test_guard.CheckRules.test_an_exchanges_sold_line_at_the_placeholder_price_is_refused"),
    ("an exchange that takes a large payment calls a manager", "guard.py", '    if rules["approval_from"]:',
     '    if rules["approval_from"] and ctx["stage"] == "sale":',
     "test_guard.CheckRules.test_an_exchange_that_takes_a_large_payment_calls_a_manager"),
    ("an exchange reads the shop", "service/app.py", 'and ctx["stage"] != "sale" and not guard.sold_lines(ctx):',
     'and ctx["stage"] != "sale":',
     "test_service.OneShop.test_an_exchange_reads_the_shop_and_judges_what_it_sells"),
    ("sentences are plain", "guard.py", '.replace("<", "").replace(">", "")', "",
     "test_guard.CheckRules.test_every_sentence_is_plain_and_at_most_140"),
    ("the settings are kept a minute", "service/app.py", "if hit and now - hit[0] < SETTINGS_TTL:", "if False:",
     "test_service.OneShop.test_the_settings_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the last rules stand in for ten minutes only", "service/app.py", "if hit and now - hit[0] < SETTINGS_STALE:", "if hit:",
     "test_service.OneShop.test_the_shop_down_uses_the_last_rules_for_ten_minutes_then_503"),
    ("the cache is per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     "test_service.ManyShops.test_each_shop_is_answered_from_its_own_rules_with_its_own_key"),
    ("a return reads nothing from the shop", "service/app.py", 'if path == "/tgr/check" and ctx["stage"] != "sale" and not',
     "if False and not", "test_service.OneShop.test_a_return_is_allowed_without_reading_the_shop"),
    ("a 404 is 'no record' only when it names the record", "service/app.py",
     'if e.code == 404 and f"{prefix} Settings Default".encode() in body:', "if e.code == 404:",
     "test_service.ShopApi.test_a_404_that_does_not_name_the_record_is_unreadable_never_rules_off"),
    ("a blank large-sale answer asks the cashier", "guard.py", 'answer = (doc.get("approval_answer") or "ask")',
     'answer = (doc.get("approval_answer") or "approve")',
     "test_guard.CheckRules.test_a_blank_or_unknown_approval_answer_asks_the_cashier"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'allow'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     "test_service.AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP TGR Integration"', '"role": "PP Integration"',
     "test_manifest.ManifestTest.test_the_integration_role_only_reads_the_settings"),
    ("a sale with no sold line reads the shop", "service/app.py", 'and ctx["stage"] != "sale" and not guard.sold_lines(ctx):',
     'and not guard.sold_lines(ctx):', "test_service.OneShop.test_a_sale_with_no_sold_line_still_reads_the_shop"),
    ("a redirect is not followed", "service/app.py",
     "urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:\n            data = _object(",
     "urllib.request.build_opener().open(req, timeout=timeout) as r:\n            data = _object(", "test_service.ShopApi.test_a_redirect_is_not_followed"),
    ("the shelf warning answers inside 1 s", "service/app.py", "return SCAN_BUDGET - (self.clock() - t0)", "return SCAN_BUDGET",
     "test_service.OneShop.test_a_shelf_answer_that_would_come_after_one_second_is_a_plain_allow"),
    ("a shelf read that fails in any way is a plain allow", "service/app.py", "        except Exception:                           # any failure of the read",
     "        except ShopUnreadable:                      # any failure of the read",
     "test_service.OneShop.test_a_shop_answer_of_the_wrong_shape_is_a_plain_allow_never_a_server_error"),
    ("the shelf warning names the sooner batch", "guard.py", "if not mine or expiry >= mine:", "if not mine:",
     "test_guard.ShelfWarning.test_the_soonest_batch_scanned_is_not_warned"),
    ("the shelf warning is off until set", "guard.py", '"shelf_warning": str(doc.get("warn_shorter_shelf_life") or "0")',
     '"shelf_warning": str(doc.get("warn_shorter_shelf_life") or "1")', "test_guard.ShelfWarning.test_off_until_the_shop_sets_it"),
    ("more lines than the most are refused", "guard.py", 'if rules["max_lines"] and len(sold) > rules["max_lines"]:',
     'if False:', "test_guard.LinesAndLowestPrices.test_more_lines_than_the_most_are_refused_and_exactly_the_most_allowed"),
    ("exactly the most lines is allowed", "guard.py", 'len(sold) > rules["max_lines"]:', 'len(sold) >= rules["max_lines"]:',
     "test_guard.LinesAndLowestPrices.test_more_lines_than_the_most_are_refused_and_exactly_the_most_allowed"),
    ("what a return takes back is not counted", "guard.py", 'and len(sold) > rules', 'and len(ctx["lines"]) > rules',
     "test_guard.LinesAndLowestPrices.test_what_a_return_takes_back_is_not_counted"),
    ("a line below its lowest price calls a manager", "guard.py", "    if below:\n", "    if False:\n",
     "test_guard.LinesAndLowestPrices.test_a_line_below_its_lowest_price_calls_a_manager"),
    ("at its lowest price is allowed", "guard.py", "if paid < low:", "if paid <= low:",
     "test_guard.LinesAndLowestPrices.test_at_its_lowest_price_is_allowed"),
    ("a free line is never judged on its lowest price", "guard.py", 'if line["rate_minor"] <= 0:', 'if line["rate_minor"] < 0:',
     "test_guard.LinesAndLowestPrices.test_a_free_line_is_never_judged"),
    ("a line is judged in its own unit", "guard.py", 'code, unit = line.get("item_code") or "", line.get("uom") or ""',
     'code, unit = line.get("item_code") or "", "Nos"', "test_guard.LinesAndLowestPrices.test_the_line_is_judged_in_its_own_unit"),
    ("the latest dated lowest price wins", "guard.py", "(start, price) > best[key][0]", "(start, price) < best[key][0]",
     "test_guard.LinesAndLowestPrices.test_lowest_prices_are_picked_as_the_engine_picks_a_dated_price"),
    ("a lowest price not yet valid is not used", "guard.py", "(start and start > today)", "False",
     "test_guard.LinesAndLowestPrices.test_lowest_prices_are_picked_as_the_engine_picks_a_dated_price"),
    ("a customer's own price is not a lowest price", "guard.py", 'r.get("customer") or r.get("supplier")', 'r.get("supplier")',
     "test_guard.LinesAndLowestPrices.test_lowest_prices_are_picked_as_the_engine_picks_a_dated_price"),
    ("another currency's price is not used", "guard.py", '(r.get("currency") or currency) != currency', "False",
     "test_guard.LinesAndLowestPrices.test_lowest_prices_are_picked_as_the_engine_picks_a_dated_price"),
    ("the question is never shortened away", "guard.py", "plain(why, TEXT_MAX - len(tail) - 1)", "plain(why)",
     "test_guard.LinesAndLowestPrices.test_every_new_sentence_is_plain_and_at_most_140"),
    ("the lowest prices are kept a minute", "service/app.py", "if hits[it] and now - hits[it][0] < SETTINGS_TTL:", "if False:",
     "test_service.LowestPrices.test_the_prices_are_kept_a_minute_and_a_new_item_is_read_alone"),
    ("the last prices stand in for ten minutes only", "service/app.py",
     "if not (hits[it] and now - hits[it][0] < SETTINGS_STALE):", "if not hits[it]:",
     "test_service.LowestPrices.test_the_shop_down_uses_the_last_prices_for_ten_minutes_then_503"),
    ("prices that cannot be read are a 503", "service/app.py", 'return 503, {"error": "the shop\'s lowest prices cannot be read"}',
     'return 200, {"verdict": "allow"}', "test_service.LowestPrices.test_the_shop_down_uses_the_last_prices_for_ten_minutes_then_503"),
    ("the lowest prices are kept per shop", "service/app.py", 'mine_key = self.clock(), [], [], (name, plist)',
     'mine_key = self.clock(), [], [], ("-", plist)', "test_service.ManyShops.test_each_shops_lowest_prices_are_its_own"),
    ("the price read names the list and the items", "service/app.py", '[["price_list", "=", price_list], ["item_code", "in", items], ',
     '[["item_code", "in", items], ', "test_service.PriceApi.test_reads_the_lists_rows_for_the_items_with_the_token"),
    ("a supplier's own price is not a lowest price", "guard.py", 'r.get("customer") or r.get("supplier") or r.get("batch_no")',
     'r.get("customer") or r.get("batch_no")', "test_guard.LinesAndLowestPrices.test_lowest_prices_are_picked_as_the_engine_picks_a_dated_price"),
    ("a unit with no row for a priced item calls a manager", "guard.py", "elif code in priced:", "elif False:",
     "test_guard.LinesAndLowestPrices.test_a_unit_with_no_row_for_a_priced_item_calls_a_manager"),
    ("a discount on the whole sale counts", "guard.py", 'paid = line["rate_minor"] * share[0] // share[1]', 'paid = line["rate_minor"]',
     "test_guard.LinesAndLowestPrices.test_a_discount_on_the_whole_sale_counts"),
    ("a lowest price is never rounded down", "guard.py", "low = math.ceil(round(lowest[(code, unit)] * 10 ** exp, 6))",
     "low = round(lowest[(code, unit)] * 10 ** exp)", "test_guard.LinesAndLowestPrices.test_a_lowest_price_is_never_rounded_down"),
    ("the most lines stays under what the check is sent", "guard.py", 'min(int(_number(doc.get("max_lines_per_sale"))), LINES_SEEN - 1)',
     'int(_number(doc.get("max_lines_per_sale")))', "test_guard.LinesAndLowestPrices.test_the_most_lines_stays_under_what_the_check_is_sent"),
    ("a refusal is answered before any price read", "service/app.py", "            if refused:\n                return 200, refused\n",
     "", "test_service.LowestPrices.test_a_refusal_is_answered_before_any_price_is_read_and_survives_a_failed_read"),
    ("a large basket is read in chunks", "service/app.py", "if chunk and size + n > PRICE_CHUNK:", "if False:",
     "test_service.LowestPrices.test_a_large_basket_is_read_in_chunks_that_keep_the_request_line_short"),
    ("the price reads stop at their budget", "service/app.py", "                    if left < READ_LEAST:\n", "                    if False:\n",
     "test_service.LowestPrices.test_a_slow_shop_runs_out_of_the_budget_answers_503_and_keeps_what_it_read"),
    ("each chunk is kept as it comes", "service/app.py", "                            self.lowest_cache[mine_key + (it,)] = (now, mine)\n", "",
     "test_service.LowestPrices.test_a_slow_shop_runs_out_of_the_budget_answers_503_and_keeps_what_it_read"),
    ("a large sale survives a failed price read", "service/app.py", '                if plain["verdict"] != "allow":\n', "                if False:\n",
     "test_service.LowestPrices.test_a_large_sale_still_calls_a_manager_when_the_prices_cannot_be_read"),
    ("the sale's share is exact", "guard.py", 'paid = line["rate_minor"] * share[0] // share[1]',
     'paid = int(line["rate_minor"] * (share[0] / share[1]) - 1e-9)',
     "test_guard.LinesAndLowestPrices.test_a_line_exactly_at_its_lowest_after_the_sale_discount_is_allowed"),
    ("the price read asks only the rows it may use", "service/app.py", '["customer", "is", "not set"], ', "",
     "test_service.PriceApi.test_reads_the_lists_rows_for_the_items_with_the_token"),
    ("what is still unread is known before the shop is", "service/app.py", "            todo = list(missing)\n", "",
     "test_service.LowestPrices.test_a_shop_whose_key_is_gone_is_a_503_never_a_crash"),
    ("a large sale's approval says its prices were not checked", "guard.py", "    if why and unchecked:\n", "    if False:\n",
     "test_service.LowestPrices.test_a_large_sale_still_calls_a_manager_when_the_prices_cannot_be_read"),
    ("a chunk is counted as it is sent", "service/app.py", "len(urllib.parse.quote_plus(json.dumps(it))) + 4", "len(it) + 3",
     "test_service.PriceApi.test_each_chunk_s_request_line_stays_under_4_kb"),
    ("a reply that is not an object is unreadable", "service/app.py", "    if not isinstance(data, dict):\n", "    if False:\n",
     "test_service.PriceApi.test_a_cut_answer_or_one_that_is_not_an_object_is_unreadable_never_a_crash"),
    ("an empty answer is unreadable, never rules off", "service/app.py", "    data = json.loads(raw)  ", '    data = json.loads(raw or b"{}") or {}  ',
     "test_service.PriceApi.test_an_answer_is_a_json_object_or_nothing"),
    ("a settings answer with no record is unreadable", "service/app.py", '            if not isinstance(data, dict) or not data:\n                raise ValueError("the answer carries no record")    # a missing record is the 404 above, never a 200\n            return data',
     "            return data or None",
     "test_service.PriceApi.test_a_cut_answer_or_one_that_is_not_an_object_is_unreadable_never_a_crash"),
    ("the settings read counts against the check's time", "service/app.py", "lowest = self.lowest(name, shop, ctx, rules, t0)",
     "lowest = self.lowest(name, shop, ctx, rules, self.clock())", "test_service.LowestPrices.test_a_slow_settings_read_counts_against_the_check_s_time"),
    ("each price read is given only the time left", "service/app.py", "min(READ_TIMEOUT, left))", "READ_TIMEOUT)",
     "test_service.LowestPrices.test_each_price_read_is_given_only_the_check_s_time_left"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s23-canary-")
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
