"""S40's two document checks against the stand-in shop: the goods receipt (shelf life, the pack's expiry, the Letter of
Undertaking, the supplier's number, the ERP's own receipts) and the stock entry (a disposal needs the regulator's visit).

    python3 -m unittest discover -s samples/s40_expiry_recall/tests -p 'test_*.py'
"""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakeshop import DISP, QUAR, FakeTenant, call, check_body, day, service  # noqa: E402

import recall  # noqa: E402


def receipt(lines, **kw):
    out = {"name": "PR-9", "supplier": "Dawa Ltd", "posting_date": day(0), "is_return": 0,
           "supplier_delivery_note": "INV-4471", "items": []}
    out.update(kw)
    for ln in lines:
        out["items"].append(dict({"item_code": "PARA", "qty": 10000, "batch_no": None, "serial_and_batch_bundle": None,
                                  "pp_rcl_pack_expiry": None, "pp_rcl_lou": 0, "pp_rcl_lou_days": None}, **ln))
    return out


class Receipt(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.svc = service(self.shop)

    def check(self, fields, user="receiver@shop"):
        code, out = call(self.svc, "/check/receipt", check_body("Purchase Receipt", fields, user))
        self.assertEqual(code, 200)
        return out

    def add_lot(self, name, item, expiry, made=None):
        self.shop.lots[name] = {"item": item, "expiry_date": expiry, "manufacturing_date": made, "disabled": 0,
                                "batch_qty": 0, "modified": "x"}

    def test_c1_a_lot_with_a_long_life_passes(self):
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-B"}])), {"verdict": "allow"})

    def test_c2_a_short_dated_lot_is_refused(self):
        out = self.check(receipt([{"batch_no": "PARA-A"}]))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("lot PARA-A has 30 days left, under 180", out["reason"])
        self.assertLessEqual(len(out["reason"]), 140)

    def test_c3_a_letter_of_undertaking_with_its_days_lets_it_in(self):
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-A", "pp_rcl_lou": 1, "pp_rcl_lou_days": 30}])),
                         {"verdict": "allow"})

    def test_c4_a_letter_of_undertaking_for_more_days_than_the_lot_has_is_refused(self):
        out = self.check(receipt([{"batch_no": "PARA-A", "pp_rcl_lou": 1, "pp_rcl_lou_days": 60}]))
        self.assertIn("the Letter of Undertaking covers 60", out["reason"])

    def test_c5_a_letter_of_undertaking_with_no_days_is_refused(self):
        out = self.check(receipt([{"batch_no": "PARA-A", "pp_rcl_lou": 1, "pp_rcl_lou_days": 0}]))
        self.assertIn("needs its days", out["reason"])

    def test_c6_an_expired_lot_is_refused_even_exempt_or_with_a_letter(self):
        self.shop.items["TRAM"]["pp_rcl_shelf_life_exempt"] = 1
        out = self.check(receipt([{"item_code": "TRAM", "batch_no": "TRAM-X", "pp_rcl_lou": 1, "pp_rcl_lou_days": 1}]))
        self.assertIn("lot TRAM-X expired on", out["reason"])

    def test_c7_an_exempt_item_skips_the_minimum(self):
        self.shop.items["PARA"]["pp_rcl_shelf_life_exempt"] = 1
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-A"}])), {"verdict": "allow"})

    def test_c8_the_items_own_minimum_wins(self):
        self.shop.items["PARA"]["pp_rcl_min_shelf_days"] = 20
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-A"}])), {"verdict": "allow"})

    def test_c9_an_expiry_the_shop_may_have_worked_out_asks_for_the_packs(self):
        """Made today, expiring today + shelf life: what the shop writes when nobody typed an expiry."""
        self.add_lot("AMOX-G", "AMOX", day(730), day(0))
        out = self.check(receipt([{"item_code": "AMOX", "batch_no": "AMOX-G"}]))
        self.assertIn("type the expiry printed on lot AMOX-G's pack", out["reason"])
        ok = self.check(receipt([{"item_code": "AMOX", "batch_no": "AMOX-G", "pp_rcl_pack_expiry": day(730)}]))
        self.assertEqual(ok, {"verdict": "allow"})

    def test_c9b_with_a_shelf_life_the_packs_date_is_needed_even_when_the_lots_dates_were_edited(self):
        """A manufacturing date corrected or blanked after the guess leaves the guessed expiry on the lot."""
        self.add_lot("AMOX-E", "AMOX", day(730), day(-10))       # made-date edited later: no longer adds up
        self.add_lot("AMOX-F", "AMOX", day(730), None)           # made-date blanked
        for lot in ("AMOX-E", "AMOX-F"):
            self.assertIn("Pack expiry", self.check(receipt([{"item_code": "AMOX", "batch_no": lot}]))["reason"])

    def test_c9c_a_shop_receiving_on_handheld_unticks_it_and_only_the_arithmetic_is_asked(self):
        self.shop.settings["pack_expiry_required"] = 0
        self.add_lot("AMOX-E", "AMOX", day(730), day(-10))
        self.assertEqual(self.check(receipt([{"item_code": "AMOX", "batch_no": "AMOX-E"}])), {"verdict": "allow"})
        self.add_lot("AMOX-G", "AMOX", day(730), day(0))
        self.assertIn("Pack expiry", self.check(receipt([{"item_code": "AMOX", "batch_no": "AMOX-G"}]))["reason"])

    def test_c9d_a_backdated_receipt_counts_from_today(self):
        out = self.check(receipt([{"item_code": "TRAM", "batch_no": "TRAM-X"}], posting_date=day(-400)))
        self.assertIn("lot TRAM-X expired on", out["reason"])
        self.assertIn("30 days left", self.check(receipt([{"batch_no": "PARA-A"}], posting_date=day(-300)))["reason"])

    def test_c9e_a_line_rejected_whole_is_not_judged(self):
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-A", "qty": 0, "rejected_qty": 10000}])),
                         {"verdict": "allow"})

    def test_c9f_a_letter_with_no_days_is_refused_whenever_ticked(self):
        out = self.check(receipt([{"batch_no": "PARA-B", "pp_rcl_lou": 1, "pp_rcl_lou_days": 0}]))
        self.assertIn("needs its days", out["reason"])

    def test_c9h_the_erps_receipt_is_never_asked_for_a_pack_date_and_still_flags_an_expired_lot(self):
        out = self.check(receipt([{"item_code": "TRAM", "batch_no": "TRAM-X"}]), user="sap@shop")
        self.assertIn("expired on", out["fields"]["pp_rcl_short_dated"])
        self.add_lot("AMOX-G", "AMOX", day(30), day(-700))
        out = self.check(receipt([{"item_code": "AMOX", "batch_no": "AMOX-G"}]), user="sap@shop")
        self.assertIn("30 days left", out["fields"]["pp_rcl_short_dated"])

    def test_c9g_the_erp_user_is_matched_whatever_its_case(self):
        out = self.check(receipt([{"batch_no": "PARA-A"}]), user="SAP@Shop")
        self.assertEqual(out["verdict"], "fill")

    def test_c10_a_pack_expiry_that_differs_from_the_lot_is_refused(self):
        out = self.check(receipt([{"batch_no": "PARA-B", "pp_rcl_pack_expiry": day(200)}]))
        self.assertIn("the pack says", out["reason"])

    def test_c11_a_line_with_no_lot_or_a_lot_with_no_expiry_is_refused(self):
        self.assertIn("name the lot of PARA", self.check(receipt([{}]))["reason"])
        self.assertIn("lot AMOX-N has no expiry date", self.check(receipt([{"item_code": "AMOX", "batch_no": "AMOX-N"}]))["reason"])

    def test_c12_the_bundles_lots_are_judged(self):
        out = self.check(receipt([{"serial_and_batch_bundle": "B11"}]))       # PARA-B and PARA-A, a draft bundle
        self.assertIn("lot PARA-A has 30 days left", out["reason"])

    def test_c13_an_item_with_no_expiry_date_is_not_judged(self):
        self.assertEqual(self.check(receipt([{"item_code": "SOAP", "batch_no": "SOAP-N"}])), {"verdict": "allow"})

    def test_c14_the_suppliers_number_is_required_when_the_settings_say_so(self):
        out = self.check(receipt([{"batch_no": "PARA-B"}], supplier_delivery_note=""))
        self.assertIn("Supplier Delivery Note", out["reason"])
        self.shop.settings["supplier_note_required"] = 0
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-B"}], supplier_delivery_note="")), {"verdict": "allow"})

    def test_c15_a_return_is_not_judged_for_shelf_life(self):
        self.assertEqual(self.check(receipt([{"batch_no": "TRAM-X", "item_code": "TRAM"}], is_return=1)),
                         {"verdict": "allow"})

    def test_c16_the_erps_own_receipt_is_flagged_never_refused(self):
        out = self.check(receipt([{"batch_no": "PARA-A"}, {"item_code": "TRAM", "batch_no": "TRAM-X"}]), user="sap@shop")
        self.assertEqual(out["verdict"], "fill")
        v = out["fields"]["pp_rcl_short_dated"]
        self.assertTrue(v.startswith("Row 1: lot PARA-A has 30 days left") and v.endswith("(+1 more)"), v)
        self.assertLessEqual(len(v), 140)
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-B"}]), user="sap@shop"), {"verdict": "allow"})

    def test_c17_a_shop_that_refuses_the_apps_user_is_refused_in_words_the_erps_receipt_too(self):
        """The app cannot run, so it cannot tell the ERP's user: it refuses, never lets a receipt through unchecked."""
        self.shop.refuse = 403
        for user in ("receiver@shop", "sap@shop"):
            self.assertEqual(self.check(receipt([{"batch_no": "PARA-B"}]), user=user)["verdict"], "refuse")

    def test_c18_no_settings_refuses(self):
        self.shop.settings = None
        self.assertEqual(self.check(receipt([{"batch_no": "PARA-B"}]))["verdict"], "refuse")

    def test_c20_an_item_the_app_cannot_read_is_refused(self):
        self.assertIn("could not read item NOPE", self.check(receipt([{"item_code": "NOPE", "batch_no": "PARA-B"}]))["reason"])

    def test_c19_a_check_must_be_signed_with_its_own_secret(self):
        raw = check_body("Purchase Receipt", receipt([{"batch_no": "PARA-A"}]))
        self.assertEqual(call(self.svc, "/check/receipt", raw, "s40-block")[0], 401)


def entry(lines, **kw):
    out = {"name": "STE-9", "purpose": "Material Issue", "posting_date": day(0), "pp_rcl_disposal_record": None,
           "items": []}
    out.update(kw)
    for ln in lines:
        out["items"].append(dict({"item_code": "TRAM", "qty": 4000, "s_warehouse": QUAR, "batch_no": "TRAM-X",
                                  "serial_and_batch_bundle": None}, **ln))
    return out


VISIT = {"workflow_state": "PP RCL Visit recorded", "officer_name": "J. Mwangi", "authority": "PPB",
         "visit_date": day(0), "signed_form": "/private/files/ppb-form.pdf", "store": QUAR, "reason": "Expired",
         "lines": [{"item": "TRAM", "batch": "TRAM-X", "qty": 4}]}


class Disposal(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.svc = service(self.shop)

    def check(self, fields):
        code, out = call(self.svc, "/check/disposal", check_body("Stock Entry", fields))
        self.assertEqual(code, 200)
        return out

    def test_d1_a_controlled_disposal_with_no_record_is_refused(self):
        out = self.check(entry([{}]))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("only with the regulator's visit", out["reason"])

    def test_d2_a_record_whose_visit_is_not_recorded_is_refused(self):
        self.shop.put_own("Disposal Record", "DSP-00001", dict(VISIT, workflow_state="PP RCL Draft"))
        self.assertIn("no regulator's visit", self.check(entry([{}], pp_rcl_disposal_record="DSP-00001"))["reason"])
        self.shop.put_own("Disposal Record", "DSP-00002", dict(VISIT, signed_form=""))
        self.assertIn("no regulator's visit", self.check(entry([{}], pp_rcl_disposal_record="DSP-00002"))["reason"])

    def test_d3_a_recorded_visit_that_covers_the_lot_lets_it_through(self):
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))
        self.assertEqual(self.check(entry([{}], pp_rcl_disposal_record="DSP-00001")), {"verdict": "allow"})

    def test_d4_a_record_that_does_not_cover_the_quantity_or_the_lot_is_refused(self):
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))
        self.assertIn("does not cover TRAM lot TRAM-X x 5",
                      self.check(entry([{"qty": 5000}], pp_rcl_disposal_record="DSP-00001"))["reason"])
        self.assertIn("does not cover", self.check(entry([{}, {}], pp_rcl_disposal_record="DSP-00001"))["reason"])

    def test_d5_an_item_without_the_schedule_field_is_refused_loudly(self):
        del self.shop.items["TRAM"]["pp_rxc_schedules"]
        out = self.check(entry([{}]))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("cannot read TRAM's schedules (no field pp_rxc_schedules)", out["reason"])

    def test_d6_an_expired_lot_issued_from_the_dispensary_is_a_disposal_too(self):
        self.assertEqual(self.check(entry([{"s_warehouse": DISP}]))["verdict"], "refuse")

    def test_d7_a_disabled_lot_issued_anywhere_is_a_disposal(self):
        self.shop.lots["TRAM-A"]["disabled"] = 1
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "batch_no": "TRAM-A"}]))["verdict"], "refuse")

    def test_d8_a_transfer_of_good_stock_between_stores_and_into_quarantine_and_a_receipt_are_allowed(self):
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "t_warehouse": "Front - ICG", "batch_no": "TRAM-A"}],
                                          purpose="Material Transfer")), {"verdict": "allow"})
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "t_warehouse": QUAR, "batch_no": "TRAM-X"}],
                                          purpose="Material Transfer")), {"verdict": "allow"})
        n = len(self.shop.reads)
        self.assertEqual(self.check(entry([{"s_warehouse": None, "t_warehouse": DISP}], purpose="Material Receipt")),
                         {"verdict": "allow"})
        self.assertEqual([r[1] for r in self.shop.reads[n:]], ["PP RCL Settings"])   # a Desk receipt: the settings only

    def test_d8b_any_issue_of_a_witnessed_item_is_a_disposal_damaged_good_stock_too(self):
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "batch_no": "TRAM-A"}]))["verdict"], "refuse")

    def test_d8c_stock_leaving_quarantine_for_anywhere_else_is_a_disposal_whatever_the_purpose(self):
        for purpose, t in (("Material Transfer", DISP), ("Material Transfer", "Scrap - ICG"), ("Repack", None)):
            self.assertEqual(self.check(entry([{"t_warehouse": t}], purpose=purpose))["verdict"], "refuse", purpose)
        self.assertEqual(self.check(entry([{"t_warehouse": "Quarantine 2 - ICG"}], purpose="Material Transfer")),
                         {"verdict": "allow"})                             # between quarantine stores

    def test_d8d_one_visit_covers_its_lines_once(self):
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))
        self.assertEqual(self.check(entry([{}], pp_rcl_disposal_record="DSP-00001")), {"verdict": "allow"})
        self.shop.entries.append({"name": "STE-1", "docstatus": 1, "pp_rcl_disposal_record": "DSP-00001",
                                  "item_code": "TRAM", "batch_no": "TRAM-X", "transfer_qty": 4.0,
                                  "serial_and_batch_bundle": None})
        out = self.check(entry([{}], pp_rcl_disposal_record="DSP-00001"))
        self.assertIn("does not cover TRAM lot TRAM-X x 4", out["reason"])

    def test_d8e_the_record_is_for_the_lines_store_and_its_visit_not_after_the_disposal(self):
        self.shop.put_own("Disposal Record", "DSP-00001", dict(VISIT, store=DISP))
        self.assertIn("is for", self.check(entry([{}], pp_rcl_disposal_record="DSP-00001"))["reason"])
        self.shop.put_own("Disposal Record", "DSP-00002", dict(VISIT, visit_date=day(3)))
        self.assertIn("after this disposal", self.check(entry([{}], pp_rcl_disposal_record="DSP-00002"))["reason"])

    def test_d8f_records_not_locked_refuse_every_disposal(self):
        self.shop.lock_rule_on = False
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))
        self.assertIn("switch on the save rule",
                      self.check(entry([{}], pp_rcl_disposal_record="DSP-00001"))["reason"])

    def test_d8g_quantities_are_compared_in_the_stock_unit(self):
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))      # 4 units
        out = self.check(entry([{"qty": 4000, "transfer_qty": 40000}], pp_rcl_disposal_record="DSP-00001"))
        self.assertIn("x 40", out["reason"])                                        # 4 boxes of 10

    def test_d9_an_item_with_no_schedule_needs_no_visit(self):
        self.assertEqual(self.check(entry([{"item_code": "PARA", "batch_no": "PARA-A"}])), {"verdict": "allow"})

    def test_d10_only_the_listed_schedules_need_the_visit(self):
        self.shop.settings["witness_schedules"] = "POM\n"
        self.assertEqual(self.check(entry([{}])), {"verdict": "allow"})
        self.shop.settings["witness_schedules"] = "CD Schedule 2\nCD Schedule 3"
        self.assertEqual(self.check(entry([{}]))["verdict"], "refuse")

    def test_d11_a_schedule_not_yet_in_force_does_not_count(self):
        self.shop.items["TRAM"]["pp_rxc_schedules"][0]["effective_from"] = day(10)
        self.assertEqual(self.check(entry([{}])), {"verdict": "allow"})

    def test_d12_every_disposal_and_no_disposal(self):
        self.shop.settings["witness_rule"] = "Every disposal"
        del self.shop.items["PARA"]["pp_rxc_schedules"]           # never read under this rule
        self.assertEqual(self.check(entry([{"item_code": "PARA", "batch_no": "PARA-A"}]))["verdict"], "refuse")
        self.shop.settings["witness_rule"] = "No disposal"
        self.assertEqual(self.check(entry([{}])), {"verdict": "allow"})

    def test_d13_the_bundles_lots_are_judged(self):
        self.shop.bundles.append({"name": "B20", "voucher_type": "Stock Entry", "voucher_no": "STE-9", "warehouse": DISP,
                                  "docstatus": 0, "is_cancelled": 0, "entries": [{"batch_no": "TRAM-X", "qty": -4}]})
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "batch_no": None,
                                             "serial_and_batch_bundle": "B20"}]))["verdict"], "refuse")

    def test_d8h_a_visit_after_a_backdated_disposal_is_refused(self):
        self.shop.put_own("Disposal Record", "DSP-00001", dict(VISIT, visit_date=day(-1)))
        out = self.check(entry([{}], pp_rcl_disposal_record="DSP-00001", posting_date=day(-30)))
        self.assertIn("after this disposal", out["reason"])

    def test_d8i_a_consumption_writes_off_and_only_a_repack_into_a_witnessed_item_transforms(self):
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "batch_no": "TRAM-A"}],
                                          purpose="Material Consumption for Manufacture"))["verdict"], "refuse")
        laundered = entry([{"s_warehouse": DISP, "batch_no": "TRAM-A"}, {"s_warehouse": None, "t_warehouse": DISP,
                                                                         "item_code": "PARA", "batch_no": "PARA-B"}],
                          purpose="Repack")
        self.assertEqual(self.check(laundered)["verdict"], "refuse")       # controlled out, an unscheduled item in
        part_pack = entry([{"s_warehouse": DISP, "batch_no": "TRAM-A"}, {"s_warehouse": None, "t_warehouse": DISP,
                                                                         "batch_no": "TRAM-A"}], purpose="Repack")
        self.assertEqual(self.check(part_pack), {"verdict": "allow"})
        mixed = entry([{"s_warehouse": DISP, "batch_no": "TRAM-A", "qty": 10000},
                       {"s_warehouse": None, "t_warehouse": DISP, "batch_no": "TRAM-A", "qty": 1000},
                       {"s_warehouse": None, "t_warehouse": DISP, "item_code": "PARA", "batch_no": "PARA-B", "qty": 9000}],
                      purpose="Repack")
        self.assertEqual(self.check(mixed)["verdict"], "refuse")           # one unscheduled finished line

    def test_d8j_no_quarantine_store_named_refuses_a_disposal_loudly_and_nothing_else(self):
        self.shop.settings["quarantine_stores"] = ""
        self.assertIn("names no quarantine store", self.check(entry([{"s_warehouse": DISP, "batch_no": "TRAM-A"}]))["reason"])
        self.assertEqual(self.check(entry([{"s_warehouse": DISP, "t_warehouse": "Front - ICG", "batch_no": "TRAM-A"}],
                                          purpose="Material Transfer")), {"verdict": "allow"})
        self.assertEqual(self.check(entry([{"item_code": "PARA", "s_warehouse": DISP, "batch_no": "PARA-A"}])),
                         {"verdict": "allow"})

    def test_d8k_a_lock_rule_left_on_but_made_to_flag_or_emptied_or_bypassed_locks_nothing(self):
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))
        every = "store\nnotice\nreason\nlines\nofficer_name\nauthority\nofficer_id\nvisit_date\nsigned_form\nattested_by\nmethod"
        for edit in ({"mode": "flag"}, {"states": ""}, {"locked_fields": "officer_name"}, {"bypass_roles": "Stock Manager"},
                     {"locked_fields": every}):                           # every field but the prior notice's date
            self.shop.lock_rule_edit = edit
            self.assertIn("switch on the save rule",
                          self.check(entry([{}], pp_rcl_disposal_record="DSP-00001"))["reason"], edit)

    def test_d8l_earlier_draws_are_read_in_units_and_this_entry_never_counts_against_itself(self):
        self.shop.put_own("Disposal Record", "DSP-00001", copy.deepcopy(VISIT))      # 4
        self.shop.entries.append({"name": "STE-9", "docstatus": 1, "pp_rcl_disposal_record": "DSP-00001",
                                  "item_code": "TRAM", "batch_no": "TRAM-X", "transfer_qty": 4.0,
                                  "serial_and_batch_bundle": None})                   # itself, resubmitted
        self.assertEqual(self.check(entry([{}], pp_rcl_disposal_record="DSP-00001")), {"verdict": "allow"})
        self.shop.entries.append({"name": "STE-1", "docstatus": 1, "pp_rcl_disposal_record": "DSP-00001",
                                  "item_code": "TRAM", "batch_no": "TRAM-X", "transfer_qty": 2.0,
                                  "serial_and_batch_bundle": None})
        self.assertIn("does not cover", self.check(entry([{"qty": 3000}], pp_rcl_disposal_record="DSP-00001"))["reason"])

    def test_d8m_the_erps_stock_entries_are_flagged_never_refused(self):
        """SAP brings its receipts and disposals as stock entries, as its own user, in the background."""
        code, out = call(self.svc, "/check/disposal", check_body("Stock Entry", entry([{}]), user="sap@shop"))
        self.assertEqual(out["verdict"], "fill")
        self.assertIn("regulator's visit", out["fields"]["pp_rcl_erp_check"])
        rec = entry([{"s_warehouse": None, "t_warehouse": DISP, "item_code": "PARA", "batch_no": "PARA-A"}],
                    purpose="Material Receipt")
        code, out = call(self.svc, "/check/disposal", check_body("Stock Entry", rec, user="sap@shop"))
        self.assertIn("30 days left", out["fields"]["pp_rcl_erp_check"])
        code, out = call(self.svc, "/check/disposal", check_body("Stock Entry", rec))
        self.assertEqual(out, {"verdict": "allow"})                                  # a Desk receipt into stock

    def test_d15_no_settings_refuses_a_disposal_and_a_count(self):
        self.shop.settings = None
        self.assertIn("has no settings yet", self.check(entry([{}]))["reason"])
        code, out = call(self.svc, "/check/count", check_body("Stock Reconciliation", count([{}])))
        self.assertIn("has no settings yet", out["reason"])

    def test_d16_a_record_that_is_not_there_is_refused(self):
        self.assertIn("no regulator's visit", self.check(entry([{}], pp_rcl_disposal_record="DSP-404"))["reason"])

    def test_d14_a_shop_that_refuses_the_apps_user_refuses_the_disposal(self):
        self.shop.refuse = 403
        self.assertEqual(self.check(entry([{}]))["verdict"], "refuse")


def count(lines):
    return {"name": "SR-1", "purpose": "Stock Reconciliation", "posting_date": day(0),
            "items": [dict({"item_code": "TRAM", "warehouse": QUAR, "qty": 0, "current_qty": 4000, "batch_no": "TRAM-X",
                            "serial_and_batch_bundle": None, "current_serial_and_batch_bundle": None}, **ln) for ln in lines]}


class Count(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.svc = service(self.shop)

    def check(self, fields):
        code, out = call(self.svc, "/check/count", check_body("Stock Reconciliation", fields))
        self.assertEqual(code, 200)
        return out

    def test_k1_a_count_never_disposes_of_witnessed_quarantined_or_blocked_stock(self):
        self.assertIn("may not dispose of TRAM", self.check(count([{}]))["reason"])
        self.assertEqual(self.check(count([{"warehouse": DISP, "batch_no": "TRAM-X"}]))["verdict"], "refuse")

    def test_k2_a_count_up_or_of_good_or_unscheduled_stock_is_allowed(self):
        self.assertEqual(self.check(count([{"qty": 5000}])), {"verdict": "allow"})
        self.assertEqual(self.check(count([{"warehouse": DISP, "batch_no": "TRAM-A"}])), {"verdict": "allow"})
        self.assertEqual(self.check(count([{"item_code": "PARA", "batch_no": "PARA-A"}])), {"verdict": "allow"})


if __name__ == "__main__":
    unittest.main()
