"""S28 — the Merge counts button: the rules, and the service behind a press signed the way the shop signs it.

    python3 -m unittest discover -s samples/s28_merge_and_history/tests -p 'test_*.py'
"""

import json
import unittest

from fakes import FakeShop, app, count, merge, press_body, row, signed, CONF


def service(*counts, rule=None):
    shop = FakeShop(counts, settings={"merge_rule": rule} if rule else None)
    return app.Service(CONF, shop), shop


def press(svc, names, key="key-0001-abcd"):
    raw = press_body(names, key)
    return svc.press(signed(raw), raw)


class Rules(unittest.TestCase):
    def test_two_drafts_with_the_same_item_sum(self):
        a = count("A", row("EARBUDS", 3, 10), row("CASE", 1, 4))
        b = count("B", row("EARBUDS", 2.5, 12), time_="11:00:00")
        rows = merge.merge_rows([a, b], merge.SUM)
        self.assertEqual([(r["item_code"], r["qty"], r["valuation_rate"]) for r in rows],
                         [("EARBUDS", 5.5, 12.0), ("CASE", 1.0, 4.0)])

    def test_the_last_rule_takes_the_last_count_by_posting_time(self):
        late = count("A", row("EARBUDS", 7, 11), time_="15:00:00")
        early = count("B", row("EARBUDS", 2, 9), time_="09:00:00")
        rows = merge.merge_rows([late, early], merge.LAST)          # ticked order is not the posting order
        self.assertEqual((rows[0]["qty"], rows[0]["valuation_rate"]), (7.0, 11.0))

    def test_a_time_without_a_leading_zero_is_still_earlier(self):
        nine, half_ten = count("A", row("X", 1, 5), time_="9:00:00"), count("B", row("X", 1, 8), time_="10:30:00")
        self.assertEqual(merge.in_order([half_ten, nine])[0]["name"], "A")       # as the site sends it, read 2026-10-16
        self.assertEqual(merge.merge_rows([half_ten, nine], merge.SUM)[0]["valuation_rate"], 8.0)

    def test_the_valuation_rate_is_the_last_counts_under_sum_too(self):
        rows = merge.merge_rows([count("A", row("X", 1, 5), date="2026-10-15"), count("B", row("X", 1, 8))], merge.SUM)
        self.assertEqual(rows[0]["valuation_rate"], 8.0)

    def test_a_counted_zero_keeps_the_last_real_rate(self):
        rows = merge.merge_rows([count("A", row("X", 5, 78)), count("B", row("X", 0, 0), time_="11:00:00")], merge.SUM)
        self.assertEqual((rows[0]["qty"], rows[0]["valuation_rate"]), (5.0, 78.0))

    def test_quantities_add_as_decimals(self):
        rows = merge.merge_rows([count("A", row("X", 0.1)), count("B", row("X", 0.2), time_="11:00:00")], merge.SUM)
        self.assertEqual(rows[0]["qty"], 0.3)

    def test_another_warehouse_or_batch_is_its_own_row(self):
        rows = merge.merge_rows([count("A", row("X", 1), row("X", 2, wh="Store 2 - DR"), row("X", 4, batch_no="B1"))],
                                merge.SUM)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["batch_no"], "B1")

    def test_blank_rows_are_dropped_and_a_counted_zero_is_kept(self):
        rows = merge.merge_rows([count("A", {"item_code": "", "warehouse": "W", "qty": 3}, row("X", 0),
                                       {"item_code": "Y", "warehouse": None, "qty": 1})], merge.SUM)
        self.assertEqual([(r["item_code"], r["qty"]) for r in rows], [("X", 0.0)])

    def test_the_new_draft_keeps_company_purpose_and_the_last_posting_time(self):
        doc = merge.plan([count("A", row("X", 1), time_="16:00:00"), count("B", row("X", 1))], merge.SUM, "k" * 12)
        self.assertEqual((doc["docstatus"], doc["company"], doc["purpose"], doc["posting_time"], doc["set_posting_time"],
                          doc[merge.KEY_FIELD], doc["set_warehouse"]),
                         (0, "Demo Retail", "Stock Reconciliation", "16:00:00", 1, "k" * 12, "Store 1 - DR"))

    def test_two_stores_leave_the_store_blank(self):
        doc = merge.plan([count("A", row("X", 1)), count("B", row("X", 1), store="Store 2 - DR")], merge.SUM, "k" * 12)
        self.assertNotIn("set_warehouse", doc)


class Refusals(unittest.TestCase):
    def test_a_single_count_is_refused(self):
        self.assertIn("at least two", merge.refusal([count("A", row("X", 1))]))

    def test_a_cancelled_count_is_refused(self):
        self.assertIn("is cancelled", merge.refusal([count("A", row("X", 1)), count("B", row("X", 1), docstatus=2)]))

    def test_serial_numbers_and_bundles_are_refused(self):
        ok = count("A", row("X", 1))
        self.assertIn("serial numbers", merge.refusal([ok, count("B", row("X", 1, serial_no="SN1"))]))
        self.assertIn("bundle", merge.refusal([ok, count("B", row("X", 1, serial_and_batch_bundle="SABB-1"))]))

    def test_submitted_cancelled_company_purpose_and_serials_are_refused(self):
        ok = count("A", row("X", 1))
        cases = {"is submitted": count("B", row("X", 1), docstatus=1),
                 "is cancelled": count("B", row("X", 1), docstatus=2),
                 "different companies": count("B", row("X", 1), company="Other"),
                 "different purposes": count("B", row("X", 1), purpose="Opening Stock"),
                 "serial numbers": count("B", row("X", 1, serial_no="SN1"))}
        for words, other in cases.items():
            self.assertIn(words, merge.refusal([ok, other]), words)
        self.assertEqual(merge.refusal([ok, count("B", row("X", 2))]), "")


class Press(unittest.TestCase):
    def test_a_press_writes_one_draft_comments_each_source_and_opens_it(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2), time_="11:00:00"))
        code, out = press(svc, ["A", "B"])
        self.assertEqual(code, 200, out)
        self.assertEqual(len(shop.made), 1)
        new = shop.made[0]
        self.assertEqual((new["docstatus"], new["items"][0]["qty"]), (0, 5.0))
        self.assertEqual(out["open_record"], {"doctype": merge.COUNT, "name": new["name"]})
        self.assertEqual(shop.notes, {"A": [f"merged into {new['name']}"], "B": [f"merged into {new['name']}"]})

    def test_the_sources_are_never_changed(self):
        a, b = count("A", row("X", 3)), count("B", row("X", 2))
        svc, shop = service(a, b)
        before = json.dumps([shop.counts["A"], shop.counts["B"]], sort_keys=True)
        press(svc, ["A", "B"])
        self.assertEqual(json.dumps([shop.counts["A"], shop.counts["B"]], sort_keys=True), before)

    def test_a_submitted_source_refuses_the_whole_request(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2), docstatus=1))
        code, out = press(svc, ["A", "B"])
        self.assertEqual((code, out["message"]["level"]), (200, "warning"))
        self.assertIn("B is submitted", out["message"]["body"])
        self.assertNotIn("open_record", out)
        self.assertEqual((shop.made, shop.notes), ([], {}))

    def test_the_service_rereads_the_saved_record_not_the_press(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2)))
        shop.counts["B"]["docstatus"] = 1             # submitted after the list was drawn
        self.assertEqual(press(svc, ["A", "B"])[1]["message"]["level"], "warning")

    def test_a_retry_writes_one_draft(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2)))
        first, second = press(svc, ["A", "B"]), press(svc, ["A", "B"])
        self.assertEqual(len(shop.made), 1)
        self.assertEqual(first[1]["open_record"], second[1]["open_record"])
        self.assertEqual(len(shop.notes["A"]), 1)

    def test_a_retry_after_a_failure_finds_the_draft_and_finishes_the_comments(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2)))
        shop.fail_after_create = True
        self.assertEqual(press(svc, ["A", "B"])[0], 502)
        code, out = press(svc, ["A", "B"])
        self.assertEqual((code, len(shop.made)), (200, 1))
        self.assertEqual(sorted(shop.notes), ["A", "B"])

    def test_a_new_key_is_a_new_merge(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2)))
        press(svc, ["A", "B"], "key-0001-abcd")
        press(svc, ["A", "B"], "key-0002-abcd")
        self.assertEqual(len(shop.made), 2)

    def test_the_settings_rule_is_used(self):
        svc, shop = service(count("A", row("X", 3), time_="09:00:00"), count("B", row("X", 2)), rule="Last")
        press(svc, ["A", "B"])
        self.assertEqual(shop.made[0]["items"][0]["qty"], 2.0)

    def test_a_forged_or_stale_press_is_refused_before_anything_is_read(self):
        svc, shop = service(count("A", row("X", 3)), count("B", row("X", 2)))
        raw = press_body(["A", "B"])
        self.assertEqual(svc.press(signed(raw, secret="wrong"), raw)[0], 401)
        self.assertEqual(svc.press(signed(raw, ts=1_000_000), raw)[0], 401)
        self.assertEqual(shop.made, [])

    def test_a_record_of_another_type_is_refused(self):
        svc, _ = service()
        raw = press_body(["A"]).replace(merge.COUNT.encode(), b"Sales Order")
        self.assertEqual(svc.press(signed(raw), raw)[0], 400)

    def test_every_answer_is_in_desks_vocabulary(self):
        for out in (merge.answer("N", ["A", "B"], 3), merge.refused("why")):
            self.assertLessEqual(len(out["message"]["title"]), 60)
            self.assertLessEqual(len(out["message"]["body"]), 280)
            self.assertIn(out["message"]["level"], ("info", "success", "warning"))
            self.assertLessEqual(len(set(out) & {"open_record", "open_page", "refresh"}), 1)


if __name__ == "__main__":
    unittest.main()
