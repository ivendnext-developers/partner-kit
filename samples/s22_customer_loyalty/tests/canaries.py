#!/usr/bin/env python3
"""S22's canaries: each money, idempotency and permission test must go RED when the rule it guards is broken. For each
mutation this copies the sample (and the kit tools it uses) to a temporary folder, runs the one test named on that unmutated
copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile),
runs the test again, and reports RED (the test caught it) or GREEN (a dead test).

    python3 samples/s22_customer_loyalty/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("amounts are Decimal", "service/money.py",
     'return x if isinstance(x, Decimal) else Decimal(str(x if x is not None else 0))', "return float(x or 0)",
     "test_money.Money.test_amounts_are_decimal_and_round_half_up"),
    ("rounded half-up", "service/money.py", "rounding=ROUND_HALF_UP)", "rounding='ROUND_HALF_EVEN')",
     "test_money.Money.test_amounts_are_decimal_and_round_half_up"),
    ("a partial return reverses its share", "service/money.py",
     "return rnd(min(e * D(this_return) / total, left), places)", "return rnd(left, places)",
     "test_money.Money.test_a_partial_return_reverses_its_share"),
    ("the total reversed is capped", "service/money.py",
     "return rnd(min(e * D(this_return) / total, left), places)", "return rnd(e * D(this_return) / total, places)",
     "test_money.Money.test_total_reversed_never_exceeds_what_was_earned"),
    ("a reversal while Pending reduces the earning", "service/loyalty.py",
     '"status": "Netted" if pending else "Credited"', '"status": "Credited"',
     "test_service.TakingBack.test_a_partial_return_while_pending_reduces_the_earning"),
    ("the shop's unique key makes a replay harmless", "service/loyalty.py",
     "    except Duplicate:\n        return False", "    except Duplicate:\n        raise",
     "test_service.Crash.test_the_replay_after_a_crash_writes_one_row"),
    ("only the manager and the service keep submit", "apply_config.py",
     'if int(r.get("submit") or 0) and r["role"] not in keep:', 'if int(r.get("submit") or 0) and r["role"] == "x":',
     "test_config.Config.test_only_the_manager_and_the_service_may_submit_a_receipt"),
    ("verified only when the check passes", "service/receipts.py", "    if found:\n", "    if False:\n",
     "test_service.CheckByWorkflow.test_verified_only_when_the_check_passes_and_only_once"),
    ("only the maker's send allows self-approval", "apply_config.py",
     'allow_self_approval=int(t["action"] == "PP LYL Send for Verification")', "allow_self_approval=0",
     "test_config.Config.test_only_the_makers_send_allows_self_approval"),
    ("the credit settles first", "service/loyalty.py",
     "        _settle_pending(t, r[\"against_sale\"])      # a return whose own settle was lost is netted before the credit\n", "",
     "test_service.TakingBack.test_the_credit_settles_an_unsettled_return_first"),
    ("switch-on ticks the feed's record types", "apply_config.py", "ticked = [dict(r, enable=on) for r",
     "ticked = [dict(r) for r", "test_config.Config.test_switch_on_names_the_user_and_ticks_every_followed_record_type"),
    ("remove switches off a role it cannot remove", "apply_config.py",
     '                T.update(dt, name, {"disabled": 1})\n', '                pass\n',
     "test_config.Config.test_remove_switches_off_the_user_and_role_a_completed_workflow_step_still_names"),
    # Member cash (the wallet): adapted from the reference implementation's wallet canaries @ 74c99d5
    ("a wallet payment's row is named by its reference (one charge)", "service/wallet.py",
     'return loyalty.key("wallet", site, *parts)', 'return loyalty.key("wallet", site, *parts, __import__("uuid").uuid4().hex)',
     "test_wallet.Wallet.test_authorise_twice_with_one_reference_is_one_charge"),
    ("Member cash never pays more than the balance", "service/wallet.py", "            if amount > credited:",
     "            if False:", "test_wallet.Wallet.test_more_than_the_balance_is_refused_and_stays_refused"),
    ("the cap is the percent of the amount due", "service/money.py",
     'cap = due if D(max_percent) <= 0 else (due * D(max_percent) / 100).quantize(step, rounding="ROUND_DOWN")',
     "cap = due", "test_wallet.Wallet.test_preview_caps_at_the_percent_of_the_amount_due_and_the_balance"),
    ("a refund is never more than the payment has left", "service/wallet.py",
     "            if amount <= 0 or amount > left:", "            if amount <= 0:",
     "test_wallet.Wallet.test_a_payment_refunded_in_two_parts_each_answered_for_itself_and_never_more"),
    ("one refund reference keeps one refund id", "service/wallet.py",
     'correlation_id=_id("PPR-", site, ref))', 'correlation_id=_id("PPR-", site, ref, __import__("uuid").uuid4().hex))',
     "test_wallet.Wallet.test_a_payment_refunded_in_two_parts_each_answered_for_itself_and_never_more"),
    ("reversing twice is safe", "service/wallet.py",
     "        except Duplicate:\n            pass                                                     # another call made it a moment ago: the same one",
     "        except Duplicate:\n            raise", "test_wallet.Wallet.test_reverse_gives_the_whole_payment_back_once"),
    ("status proves absence only for a reference never received", "service/wallet.py",
     'return self._out(req, "unknown", exists=False)', 'return self._out(req, "unknown")',
     "test_wallet.Wallet.test_status_answers_the_asked_reference_and_proves_absence"),
    ("the status answer carries the shop's currency and places", "service/wallet.py",
     "            body = dict(body, currency=body.get(\"currency\") or s.currency,\n                        currency_exponent=body.get(\"currency_exponent\", s.places))",
     "            body = dict(body)", "test_wallet.Wallet.test_status_answers_the_asked_reference_and_proves_absence"),
    ("a write that may still land is never absent", "service/wallet.py",
     "        if (site, _key(site, ref)) in _unsure or (site, _key(site, \"refund\", ref)) in _unsure:",
     "        if False:", "test_wallet.Wallet.test_a_write_that_may_still_land_is_never_absent"),
    ("another shop's status is unknown, never declined", "service/wallet.py",
     '            outcome = "declined" if verb in ("authorise", "refund") else "unknown"', '            outcome = "declined"',
     "test_wallet.Wallet.test_another_shops_question_says_nothing_about_money"),
    ("a reversal that may still land keeps status unknown", "service/wallet.py",
     "                              or (site, _key(site, ref, \"reverse\")) in _unsure):",
     "                              or False):",
     "test_wallet.Wallet.test_a_reversal_that_may_still_land_keeps_status_unknown"),
    ("just after a start, status never says not here", "service/wallet.py",
     "        if not reversed_ and (time.monotonic() - STARTED < SETTLE_S", "        if not reversed_ and (False",
     "test_wallet.Wallet.test_just_after_a_start_status_never_says_not_here"),
    ("an authorise past its deadline writes nothing", "service/wallet.py",
     "        if started is not None and time.monotonic() - started > WRITE_DEADLINE_S:",
     "        if False:", "test_wallet.Wallet.test_an_authorise_past_its_deadline_writes_nothing"),
    ("a refund that waited for the lock sees the reversal", "service/wallet.py",
     "            if self.t.get(LEDGER, _key(site, original, \"reverse\")):  # reversed while this waited for the lock",
     "            if False:", "test_wallet.Wallet.test_a_refund_that_waited_for_the_lock_sees_the_reversal"),
    ("the member lock is a real lock", "service/loyalty.py", "        fcntl.flock(f, fcntl.LOCK_EX)\n", "",
     "test_wallet.Wallet.test_a_refund_that_waited_for_the_lock_sees_the_reversal"),
    ("a money call without its exponent is refused", "service/wallet.py",
     '        elif verb in ("authorise", "refund") and body.get("currency_exponent") is None:',
     "        elif False:", "test_wallet.Wallet.test_a_money_call_without_its_exponent_is_refused"),
    ("a sale paid with Member cash still counts towards the tier", "service/loyalty.py",
     "    rate = 0 if _paid_with_wallet(s, inv) else s.plan(",
     "    if _paid_with_wallet(s, inv):\n        return {\"result\": \"nothing to earn\"}\n    rate = 0 if False else s.plan(",
     "test_wallet.Earning.test_a_sale_paid_with_member_cash_still_counts_towards_the_tier"),
    ("a sale paid with Member cash earns nothing", "service/loyalty.py",
     '    return any(p.get("mode_of_payment") == s.wallet_mode', '    return False and any(p.get("mode_of_payment") == s.wallet_mode',
     "test_wallet.Earning.test_a_sale_paid_with_member_cash_earns_nothing_unless_the_shop_says_so"),
    ("the wallet's route is off until its secret is set", "service/app.py",
     'if not secret or secret == "UNSET" or self.app:', "if not secret or self.app:",
     "test_wallet.Route.test_the_route_is_signed_and_off_until_the_secret_is_set"),
    # many shops (the app template's handshake): each shop's own secret and records, one poll per shop
    ("a press is checked with ITS shop's secret", "service/app.py", "record = self.store.get(site) if site else None",
     "record = self.store.get((self.store.sites() or [site])[0]) if site else None",
     "test_many_shops.ManyShops.test_canary_b_cannot_call_as_a"),
    ("a site that is not connected gets 401", "service/app.py", '            return None, "the signature does not match"         # the same words: an unknown site is not told apart',
     '            return (lambda: self.client({"site": site})), ""', "test_many_shops.ManyShops.test_canary_an_unknown_site_and_no_site"),
    ("Member cash stays one shop's", "service/app.py", 'secret == "UNSET" or self.app:', 'secret == "UNSET":',
     "test_many_shops.ManyShops.test_member_cash_is_not_offered_to_many_shops"),
    ("each shop's feed note is its own", "service/worker.py",
     'path = os.path.join(state, hashlib.sha256(site.encode()).hexdigest()[:16])', "path = state",
     "test_many_shops.Worker.test_one_poll_per_shop_with_its_own_key_note_and_records"),
    ("a stuck shop never holds up another", "service/worker.py", "        busy[site].start()\n", "        busy[site].run()\n",
     "test_many_shops.Worker.test_a_stuck_shop_never_holds_up_another_and_is_not_run_twice"),
    ("a shops store that does not answer never kills the worker", "service/worker.py",
     "    except Exception as e:                       # noqa: BLE001 — the shops store did not answer",
     "    except ZeroDivisionError as e:  # the shops store did not answer",
     "test_many_shops.Worker.test_a_shops_store_that_does_not_answer_ends_the_pass_never_the_worker"),
    ("health says when the feed worker stalls", "service/app.py", "            if svc.app and time.monotonic()",
     "            if False and time.monotonic()", "test_many_shops.Health.test_health_is_503_once_the_feed_worker_stalls"),
    ("one shop's failure never stops the others", "service/worker.py",
     "        except Exception as e:                   # noqa: BLE001 — one shop's failure never stops the others\n"
     "            out[site] = {\"error\": type(e).__name__}\n",
     "        except ZeroDivisionError as e:\n            out[site] = {\"error\": type(e).__name__}\n",
     "test_many_shops.Worker.test_one_poll_per_shop_with_its_own_key_note_and_records"),
    ("the library's prefix names the daily balance rows too", "service/app.py",
     '"Ledger", "Member", "Plan", "Settings", "Balance"))', '"Ledger", "Member", "Plan", "Settings", "Ledger"))',
     "test_many_shops.Prefix.test_the_librarys_app_reads_its_own_record_types"),
    ("a daily job that fails is tried once a day, not every pass", "service/worker.py",
     "                last_daily[site] = today         # tried once a day", "                pass  # tried once a day",
     "test_many_shops.Worker.test_a_daily_job_that_fails_is_not_rerun_on_every_pass"),
    ("every record type follows the prefix (a census)", "service/app.py",
     "    wallet.LEDGER = loyalty.LEDGER", "    wallet.LEDGER = loyalty.LEDGER\n    loyalty.BALANCE = 'PP LYL Balance'",
     "test_many_shops.Prefix.test_every_record_type_name_follows_the_prefix"),
    ("the till names the shop's own spend window", "service/app.py",
     '(spend over the last {s.window_days} days).', 'this year.',
     "test_service.MemberKey.test_the_key_shows_plan_balance_and_next_tier_and_refuses_a_bad_signature"),
    ("a customer the shop refuses does not stop the other members", "service/loyalty.py",
     "            except ShopError as e:       # the shop refuses", "            except KeyError as e:       # the shop refuses",
     "test_service.Tiers.test_a_customer_the_shop_refuses_to_save_does_not_stop_the_others"),
    ("the log counts refused customers", "service/worker.py",
     "        if refused:      # a count", "        if False:      # a count",
     "test_many_shops.Worker.test_a_refused_customer_is_counted_in_the_log_never_named"),
    ("a refused customer keeps its plan, so plan and group never split", "service/loyalty.py",
     "                moved.append({\"customer\": m[\"customer\"], \"refused\": e.status})\n                continue\n",
     "                moved.append({\"customer\": m[\"customer\"], \"refused\": e.status})\n",
     "test_service.Tiers.test_a_customer_the_shop_refuses_to_save_does_not_stop_the_others"),
    ("the till promises no move to an inactive member", "service/app.py",
     '    if m.get("status") == "Inactive":', '    if False:',
     "test_service.MemberKey.test_the_key_shows_plan_balance_and_next_tier_and_refuses_a_bad_signature"),
    ("the wallet's route checks the signature", "service/app.py",
     '        if why:\n            return 401, {"error": why}\n        try:\n            body = json.loads(raw or b"{}")',
     '        if False:\n            return 401, {"error": why}\n        try:\n            body = json.loads(raw or b"{}")',
     "test_wallet.Route.test_the_route_is_signed_and_off_until_the_secret_is_set"),
    ("the web handler sends the wallet's path to the wallet", "service/app.py",
     "            if self.path.startswith(WALLET_PREFIX):", "            if False:",
     "test_wallet.Route.test_the_web_handler_sends_the_wallet_path_to_the_wallet"),
    ("the service may submit a receipt's batch bundle", "config.json",
     '    "write",\n    "submit"\n   ],\n   "why": "the Verify step submits the receipt; for',
     '    "write"\n   ],\n   "why": "the Verify step submits the receipt; for',
     "test_config.Config.test_the_service_may_make_and_submit_a_receipts_batch_bundle"),
    ("the settings name Member cash only once it exists", "apply_config.py",
     '    if st.get("wallet_mode_of_payment") and T.list(', '    if False and T.list(',
     "test_config.Config.test_the_settings_name_member_cash_only_once_its_payment_method_exists"),
    # the follow-up: spend after a cancelled sale, a sale of nothing, the wallet's phone rule, the shop client's name
    ("a cancelled sale takes out only the spend a return left", "service/loyalty.py",
     '    base = max(money.D(earn["sale_base"]) - returned, money.D(0))',
     '    base = money.D(earn["sale_base"])',
     "test_service.TakingBack.test_cancelling_the_sale_after_a_return_takes_the_returned_part_out_of_the_spend_once"),
    ("a sale of nothing or less writes no Earn row", "service/loyalty.py",
     '    if value <= 0:\n        return {"result": "nothing to earn"}\n',
     '    if False:\n        return {"result": "nothing to earn"}\n',
     "test_service.Earning.test_a_sale_of_nothing_or_less_writes_no_earn_row"),
    # the earning base (LYLSPEND): a gift card earns once, when it is spent; a tender discount never earns; returns are
    # measured on the sale's value, so they take back exactly what it earned
    ("a gift card sold earns nothing", "service/money.py",
     'return D(sale.get("grand_total")) - _gift_card_lines(sale, "net_amount") - _gift_card_tax(sale)',
     'return D(sale.get("grand_total")) - _gift_card_tax(sale)',
     "test_service.EarningBase.test_a_gift_card_sold_on_the_sale_earns_nothing_on_it"),
    ("a gift card comes off with its tax", "service/money.py",
     ' - _gift_card_lines(sale, "net_amount") - _gift_card_tax(sale)', ' - _gift_card_lines(sale, "net_amount")',
     "test_service.EarningBase.test_a_taxed_gift_card_comes_off_with_its_tax_and_the_goods_return_takes_back_exactly"),
    ("a gift card's tax is read in either shape", "service/money.py",
     ' else (v or {}).get("tax_amount") if isinstance(v, dict) else 0)', " else 0)",
     "test_service.EarningBase.test_a_taxed_gift_card_comes_off_whichever_shape_the_tax_rows_keep"),
    ("a gift card's tax is taken in the sale's currency", "service/money.py",
     '    return tax / (rate if rate > 0 else 1)', "    return tax",
     "test_service.EarningBase.test_a_taxed_gift_card_in_another_currency_comes_off_at_the_sales_own_figure"),
    ("a gift card comes off at what it added to the sale", "service/money.py",
     '_gift_card_lines(sale, "net_amount")', '_gift_card_lines(sale, "amount")',
     "test_service.EarningBase.test_a_gift_card_under_a_sale_discount_comes_off_at_what_it_added"),
    ("the tender discount never earns", "service/money.py",
     "    return goods_value(sale) - goods_discount", "    return goods_value(sale)",
     "test_service.EarningBase.test_the_tender_discount_is_left_out"),
    ("only the goods' share of the tender discount comes off", "service/money.py",
     '\n                      - _gift_card_lines(sale, "custom_tender_discount_apportioned"))', ")",
     "test_service.EarningBase.test_a_mixed_sale_earns_on_the_rest_only_and_a_replay_writes_nothing"),
    ("the ledger keeps the sale's value, the scale of its returns", "service/loyalty.py",
     '"sale_base": value, "against_sale": invoice,', '"sale_base": money.D(inv.get("grand_total")), "against_sale": invoice,',
     "test_service.EarningBase.test_returning_the_goods_of_a_gift_card_sale_takes_back_exactly_what_was_earned"),
    ("Member cash asks nothing of the customer's phone", "service/wallet.py",
     '    "payer_required": False,', '    "payer_required": True,',
     "test_wallet.Wallet.test_the_declaration_asks_nothing_of_the_customers_phone"),
    ("every call to the shop names the service", "service/shop.py",
     '            "User-Agent": USER_AGENT})', '            })',
     "test_service.ShopClient.test_every_call_to_the_shop_names_the_service_not_the_librarys_default"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s22-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("state", "__pycache__", ".s22_before.json*"))
        for tool in ("feed_client", "manifest", "app_template"):     # app.py imports the template's handshake
            shutil.copytree(os.path.join(kit, "tools", tool), os.path.join(tmp, "r", "tools", tool),
                            ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120,
                              env=dict(os.environ, PP_BEFORE=os.path.join(tmp, "before0.json")))
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
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PP_BEFORE=os.path.join(tmp, "before.json")))
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
