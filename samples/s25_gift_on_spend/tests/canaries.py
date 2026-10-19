#!/usr/bin/env python3
"""S25's canaries: each money, idempotency, and hold test must go RED when the rule it guards is broken. For each
mutation this copies the sample (and the kit tools it uses) to a temporary folder, runs the one test named on that
unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must
compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S22's
(`samples/s22_customer_loyalty/tests/canaries.py` @ 3546aaf; a defect there is a defect here).

    python3 samples/s25_gift_on_spend/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G, C, W, A = "service/gcs.py", "service/cards.py", "service/worker.py", "service/app.py"

CANARIES = [
    # the rules
    ("a gift card line on the sale earns nothing", G, 'if i.get("transaction_mode") in GIFT_CARD_LINES)', "if False)",
     "test_rules.Spend.test_a_gift_card_sold_on_the_sale_does_not_count"),
    ("only gift card lines are taken out: an exchange earns on its net", G,
     'if i.get("transaction_mode") in GIFT_CARD_LINES)', 'if (i.get("transaction_mode") or "Sale") != "Sale")',
     "test_rules.Spend.test_an_item_return_line_in_a_sale_counts_with_its_own_sign"),
    ("a till return takes its whole value off", G, "return max(-(D(ret.get(\"grand_total\")) - _gift_card_lines(ret)) + reversed_discount, Decimal(0))",
     "return max(-(D(ret.get(\"grand_total\")) - sum((D(i.get(\"amount\")) for i in ret.get(\"items\") or [] if i.get(\"transaction_mode\") != \"Sale\"), Decimal(0))) + reversed_discount, Decimal(0))",
     "test_rules.Spend.test_a_returns_spend_is_its_value_whatever_it_was_refunded_to"),
    ("a gift card or store credit spent earns nothing", G, 'if p.get("type") in NO_EARN_TENDERS)', "if False)",
     "test_rules.Spend.test_what_a_gift_card_or_store_credit_paid_does_not_count"),
    ("loyalty points earn nothing", G, ' + D(sale.get("loyalty_amount"))', "",
     "test_rules.Spend.test_loyalty_points_and_what_is_owed_do_not_count"),
    ("what is still owed earns nothing", G, 'owed = max(D(sale.get("outstanding_amount")), Decimal(0))', "owed = Decimal(0)",
     "test_rules.Spend.test_loyalty_points_and_what_is_owed_do_not_count"),
    ("a sale on account earns nothing on that part", G, 'NO_EARN_TENDERS = ("Gift Certificate", "Store Credit", "On Account", "Wallet")',
     'NO_EARN_TENDERS = ("Gift Certificate", "Store Credit", "Wallet")', "test_rules.Spend.test_a_sale_on_account_earns_nothing_on_that_part"),
    ("a partner wallet earns nothing", G, 'NO_EARN_TENDERS = ("Gift Certificate", "Store Credit", "On Account", "Wallet")',
     'NO_EARN_TENDERS = ("Gift Certificate", "Store Credit", "On Account")',
     "test_rules.Spend.test_a_partner_wallet_earns_nothing_and_a_negative_tender_row_is_ignored"),
    ("a negative tender row is ignored", G, "(max(D(p.get(\"amount\")), Decimal(0)) for p in", "(D(p.get(\"amount\")) for p in",
     "test_rules.Spend.test_a_partner_wallet_earns_nothing_and_a_negative_tender_row_is_ignored"),
    ("a return's tender discount reversal counts", G, "reversed_discount = min(D(ret.get(\"custom_tender_discount_amount\")), Decimal(0))",
     "reversed_discount = Decimal(0)", "test_rules.Spend.test_a_return_takes_off_what_was_refunded_after_its_tender_discount"),
    ("a used card zeroed by staff is never this app's void", C, "    if zeroed and not used and D(gc.get(\"balance\")) == 0:",
     "    if zeroed and D(gc.get(\"balance\")) == 0:", "test_cards.Folds.test_a_card_used_then_zeroed_by_staff_is_review_never_this_apps_void"),
    ("a shop making progress is not stuck", W, "time.monotonic() - max(since, PROGRESS.get(site, since)) > STUCK_S",
     "time.monotonic() - since > STUCK_S", "test_service.HealthyPass.test_a_shop_busy_past_the_limit_is_stuck_and_a_catching_up_one_is_not"),
    ("a release backlog counts as progress", W, "tick = (lambda: PROGRESS.__setitem__(site, time.monotonic())) if site is not None else (lambda: None)",
     "tick = lambda: None", "test_service.HealthyPass.test_a_release_backlog_counts_as_progress"),
    ("a tender discount is not money paid", G, 'tender_discount = max(D(sale.get("custom_tender_discount_amount")), Decimal(0))',
     "tender_discount = Decimal(0)", "test_rules.Spend.test_a_tender_discount_is_not_money_paid"),
    ("a void cut short finishes as its own void", C, "    if zeroed and not used and D(gc.get(\"balance\")) == 0:", "    if False:",
     "test_cards.Folds.test_a_void_cut_short_by_a_restart_finishes_as_its_own_void"),
    ("a busy shop is marked stuck only past the limit", W, '"stuck": time.monotonic() - max(since, PROGRESS.get(site, since)) > STUCK_S}', '"stuck": True}',
     "test_service.HealthyPass.test_a_shop_busy_past_the_limit_is_stuck_and_a_catching_up_one_is_not"),
    ("at most the shop's cards per sale", G, "return min(int(a // s.threshold), s.max_cards)", "return int(a // s.threshold)",
     "test_rules.Cards.test_one_per_full_threshold_up_to_the_shops_cap"),
    ("compared at the currency's precision", G, "a = rnd(amount, s.places)", "a = D(amount)",
     "test_rules.Cards.test_compared_at_the_currencys_precision"),
    ("a walk-in never earns", G, "if not customer or customer in s.walk_in:", "if not customer:",
     "test_rules.WhoEarns.test_these_never_earn"),
    ("an excluded group never earns", G, "if customer_group and customer_group in s.excluded_groups:", "if False:",
     "test_rules.WhoEarns.test_these_never_earn"),
    ("a layaway, order or quotation never earns", G, "if (sale.get(\"transaction_mode\") or PLAIN_SALE) != PLAIN_SALE:",
     "if False:", "test_rules.WhoEarns.test_these_never_earn"),
    ("another currency never earns", G, 'if (sale.get("currency") or "") != s.currency:', "if False:",
     "test_rules.WhoEarns.test_these_never_earn"),
    ("a rechargeable or cashback item is refused", G, '        if int(item.get(flag) or 0):\n', "        if False:\n",
     "test_cards.Folds.test_a_gift_card_item_that_could_turn_into_money_issues_nothing"),
    ("an item expiring inside the hold is refused", G, "if days and days * 24 <= s.hold_hours:", "if False:",
     "test_rules.Ready.test_the_gift_card_item_must_not_turn_into_money"),
    # issue
    ("one card per sale and position (the shop's name)", G, 'return f"{sale}:{int(position)}"',
     'return f"{sale}:{int(position)}:" + __import__("uuid").uuid4().hex', "test_cards.Issue.test_a_replayed_sale_earns_no_second_card"),
    ("the card is issued at 0", C, '"total": str(value), "balance": "0",', '"total": str(value), "balance": str(value),',
     "test_cards.Issue.test_a_sale_over_the_threshold_earns_one_card_held_at_0"),
    ("a number in the shop is never reused", C, "        if t.get(GIFT_CARD, n) is None:", "        if True:",
     "test_cards.Issue.test_a_number_already_in_the_shop_is_never_reused"),
    ("a gift card that is not ours at 0 is review", C,
     'if not gc or D(gc.get("balance")) != 0 or D(gc.get("total")) != value or _balances(t, number):', "if not gc:",
     "test_cards.Issue.test_a_gift_card_that_is_not_ours_at_0_is_review_not_held"),
    ("a sale handled after its return issues on its net", C, "n = gcs.cards_for(net_spend(t, sale), s)",
     "n = gcs.cards_for(gcs.spend(sale), s)", "test_cards.Folds.test_a_sale_handled_after_its_return_earns_only_what_its_net_earns"),
    # hold and release
    ("never released before the hold", C, "release_after_utc=utc(now + _dt.timedelta(hours=hold))", "release_after_utc=utc(now)",
     "test_cards.Release.test_nothing_is_released_before_the_hold_has_passed"),
    ("the hold the card was issued with", C, 'hold = int(rec.get("hold_hours") if rec.get("hold_hours") is not None else s.hold_hours)',
     "hold = int(load_settings(t).hold_hours)", "test_cards.Release.test_the_hold_is_the_one_the_card_was_issued_with"),
    ("one balance entry per card, even after a crash", C, "    if done:                                        # a release",
     "    if False:                                        # a release", "test_cards.Release.test_a_crash_after_the_balance_entry_never_writes_a_second"),
    ("a balance changed during the hold is review", C,
     'if D(gc.get("balance")) != 0:\n        return _review(t, rec, "the gift card\'s balance was changed in the shop during the hold")',
     'if False:\n        return _review(t, rec, "the gift card\'s balance was changed in the shop during the hold")',
     "test_cards.Release.test_a_balance_changed_in_the_shop_during_the_hold_is_review"),
    ("a release reads the sale again (cancelled)", C, "    if int(sale.get(\"docstatus\") or 0) != 1:\n        return \"the sale was cancelled\"",
     "    if False:\n        return \"the sale was cancelled\"", "test_cards.Folds.test_a_release_reads_the_sale_again_and_voids_a_cancelled_one"),
    ("a release reads the returns again", C, 'if int(rec.get("position") or 0) > gcs.kept(net_spend(t, sale), rec.get("threshold"), issued):',
     "if False:", "test_cards.Folds.test_a_release_reads_the_returns_too"),
    # void
    ("a held card voided is never released", C, '_set(t, rec, status="Voided", note=f"{why}; never released"[:300])',
     '_set(t, rec, note=f"{why}; never released"[:300])', "test_cards.Void.test_a_cancel_during_the_hold_voids_and_the_card_is_never_released"),
    ("a released unspent card is set to 0", C, '"gift_card": number, "balance": "0", "docstatus": 1})',
     '"gift_card": number, "balance": str(value), "docstatus": 1})', "test_cards.Void.test_a_cancel_after_the_release_sets_an_unspent_card_to_0"),
    ("a spent card is review, nothing taken", C, '    if used or D(gc.get("balance")) != value:', "    if used:",
     "test_cards.Void.test_a_card_already_spent_is_review_and_keeps_its_balance"),
    ("a card used at the till is never voided", C, '    if used or D(gc.get("balance")) != value:',
     '    if D(gc.get("balance")) != value:', "test_cards.Folds.test_a_card_used_at_the_till_is_never_voided_even_at_full_balance"),
    ("a return voids the last cards first", C, 'key=lambda r: -int(r.get("position") or 0))', 'key=lambda r: int(r.get("position") or 0))',
     "test_cards.Void.test_a_return_voids_the_last_cards_first"),
    ("a return keeps what the spend still earns", G, "return min(int(max(D(net), Decimal(0)) // t), issued) if t > 0 else 0",
     "return 0", "test_cards.Void.test_a_return_below_the_threshold_voids_and_one_above_keeps"),
    ("a cancelled return changes nothing", C, '    if int(doc.get("is_return") or 0):', "    if False:",
     "test_cards.Void.test_a_cancelled_return_gives_no_card_back_and_changes_nothing"),
    # the worker and the service
    ("one shop's failure stops no other", W,
     "        except Exception as e:                   # noqa: BLE001 — one shop's failure never stops the others",
     "        except ZeroDivisionError as e:", "test_service.ManyShops.test_each_shop_is_served_with_its_own_key_and_records_and_one_failure_stops_none"),
    ("a store that does not answer is not a healthy pass", W, "        return None                              # not a pass",
     "        return {}                              # not a pass", "test_service.HealthyPass.test_a_pass_counts_only_when_the_store_answered_and_no_shop_was_stuck"),
    ("a stuck shop is not a healthy pass", W, 'return out is not None and not any((v or {}).get("stuck") for v in out.values())',
     "return out is not None", "test_service.HealthyPass.test_a_pass_counts_only_when_the_store_answered_and_no_shop_was_stuck"),
    ("/health says when the worker stalls", A, "return not (time.monotonic() - self.started > HEALTH_GRACE_S and stale)",
     "return True", "test_service.Health.test_health_is_503_once_the_worker_stalls_and_200_while_it_passes"),
    ("the prefix names the library app's record types", C, '    CARD, SETTINGS = f"{prefix} Card", f"{prefix} Settings"',
     "    CARD, SETTINGS = CARD, SETTINGS", "test_service.Health.test_the_prefix_names_the_library_apps_record_types"),
    ("the manifest names a card by its key", "manifest.json", '"autoname": "field:card_key"', '"autoname": "hash"',
     "test_manifest.Manifest.test_a_card_is_named_by_its_key_so_the_shop_refuses_a_second"),
    ("the manifest names the service its site connects", "manifest.json", '"https://gcs.partner.example"', '"https://gcs.partner.example/x"',
     "test_manifest.Manifest.test_the_shop_calls_nothing_outside_and_names_the_one_service_its_site_connects"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s25-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("state", "__pycache__"))
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
