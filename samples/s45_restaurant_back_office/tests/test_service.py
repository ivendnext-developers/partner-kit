"""S45's laptop tests: the real service, a stand-in for the shop's record API (``fakeshop.py``), presses signed exactly
as the shop signs them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s45_restaurant_back_office/tests -p 'test_*.py'

On our test bench the real Desk buttons were pressed on a café's real till sales; these prove the service's own duties
fast, and are what the mutation canary turns RED."""

import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import backoffice as bo  # noqa: E402
import fakeshop as fs  # noqa: E402

SECRETS = {"issue": "s45-issue", "foodcost": "s45-foodcost", "allergens": "s45-allergens"}
NOW = datetime.datetime(2026, 10, 22, 14, 0, tzinfo=datetime.timezone.utc).timestamp()


def body(doctype, names):
    return {"point": "desk_action/1", "context": {"v": 1, "action": "a1", "label": "x", "user": "mgr@x", "lang": "en",
                                                   "idempotency_key": "k1", "inputs": {},
                                                   "records": [{"doctype": doctype, "name": n, "fields": {"name": n}}
                                                               for n in names]}}


def signed(payload, secret, ts=None):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw


class Clock:
    def __init__(self, step=0.0):
        self.t, self.step = 0.0, step

    def __call__(self):
        self.t += self.step
        return self.t


class ServiceTest(unittest.TestCase):
    def svc(self, shop, clock=None, now=NOW):
        conf = {f"PP_SECRET_{k.upper()}": v for k, v in SECRETS.items()}
        return app.Service(conf, tenant=shop, clock=clock or Clock(), now=lambda: now)

    def press(self, svc, path, doctype, names, secret=None):
        sub = app.SUBS[path]
        h, raw = signed(body(doctype, names), secret or SECRETS[sub])
        return svc.handle("POST", path, h, raw)

    def issue(self, shop, **kw):
        return self.press(self.svc(shop, **kw), "/press/issue", "PP RBO Settings", [fs.CO])

    # ── Issue ingredients ──
    def test_i1_one_issue_per_store_and_day_and_its_material_issue(self):
        shop = fs.FakeTenant()
        code, out = self.issue(shop)
        self.assertEqual(code, 200, out)
        (iss,) = shop.issues.values()
        self.assertEqual((iss["status"], iss["sales"], iss["store"], iss["posting_time"]), ("Issued", "S1\nS2", fs.STORE, "12:30:00"))
        (se,) = shop.entries.values()
        self.assertEqual({r["item_code"]: round(r["qty"], 6) for r in se["items"]},
                         {"BUN": 2, "PATTY": 2, "BEANS": 0.018, "MILK": 0.15})
        self.assertEqual((se["pp_rbo_issue"], iss["stock_entry"], se["posting_date"]), (iss["name"], se["name"], "2026-10-22"))
        self.assertIn("Issued the ingredients of 1 store-day", out["message"]["body"])

    def test_i2_the_issue_is_written_before_the_stock_entry(self):
        shop = fs.FakeTenant()
        self.issue(shop)
        writes = [c for c in shop.calls if c.startswith(("POST", "PUT"))]
        self.assertLess(writes.index("POST PP RBO Issue"), writes.index("POST Stock Entry"))

    def test_i3_a_press_again_books_nothing_twice(self):
        shop = fs.FakeTenant()
        self.issue(shop)
        code, out = self.issue(shop)
        self.assertEqual((len(shop.issues), len(shop.entries)), (1, 1))
        self.assertEqual(out["message"]["body"], "Nothing new to issue.")

    def test_i4_a_sale_posted_late_is_caught_by_the_next_press(self):
        shop = fs.FakeTenant()
        self.issue(shop)
        shop.sales.append({"name": "S9", "posting_date": "2026-10-22", "posting_time": "12:10:00", "owner": "ana@x",
                           "set_warehouse": fs.STORE, "pos_profile": "Café", "company": fs.CO, "docstatus": 1,
                           "items": [{"item_code": "BURGER", "qty": 1, "stock_qty": 1, "net_amount": 80}]})
        self.issue(shop)
        self.assertEqual(sorted(i["sales"] for i in shop.issues.values()), ["S1\nS2", "S9"])
        self.assertEqual(len(shop.entries), 2)

    def test_i5_sales_before_the_start_date_are_never_issued(self):
        shop = fs.FakeTenant(settings_=fs.settings(start_from="2026-10-23 00:00:00"))
        self.issue(shop)
        self.assertEqual((shop.issues, shop.entries), ({}, {}))

    def test_i5b_a_start_in_the_middle_of_a_day_takes_only_the_sales_after_it(self):
        shop = fs.FakeTenant(settings_=fs.settings(start_from="2026-10-22 12:15:00"))
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual(iss["sales"], "S2")

    def test_i6_no_start_date_no_issue(self):
        shop = fs.FakeTenant(settings_=fs.settings(start_from=None))
        code, out = self.issue(shop)
        self.assertEqual(out["message"]["body"], app.NO_START)
        self.assertEqual(shop.issues, {})

    def test_i7_short_names_every_part_and_takes_nothing(self):
        shop = fs.FakeTenant(stock={"BUN": 1, "PATTY": 20, "MILK": 0.1, "BEANS": 1})
        code, out = self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual(iss["status"], "Short")
        self.assertIn("BUN (needs 2, has 1)", iss["problem"])
        self.assertIn("MILK (needs 0.15, has 0.1)", iss["problem"])
        self.assertEqual(shop.entries, {})
        self.assertEqual(out["message"]["level"], "warning")

    def test_i8_short_at_the_sales_time_is_booked_at_the_press_once_stock_is_in(self):
        shop = fs.FakeTenant()
        real = shop.create

        def at_the_sales_time_short(doctype, b):
            if doctype == "Stock Entry" and b.get("set_posting_time"):
                raise app.TenantError("417", 417, "NegativeStockError", "BUN needed")
            return real(doctype, b)
        shop.create = at_the_sales_time_short
        self.issue(shop)
        (iss,) = shop.issues.values()
        (se,) = shop.entries.values()
        self.assertEqual(iss["status"], "Issued")
        self.assertNotIn("posting_date", se)               # the shop dates it at the moment it books it
        self.assertIn("came in", se["remarks"])
        self.assertNotIn("LIST Bin", shop.calls)            # never marked Short on the way: booked in the same try

    def test_i9_a_short_issue_is_issued_by_a_later_press_once_the_delivery_is_in(self):
        shop = fs.FakeTenant(stock={"BUN": 1, "PATTY": 20, "MILK": 5, "BEANS": 1})
        self.issue(shop)
        shop.stock["BUN"] = 10
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual((iss["status"], iss["problem"], len(shop.entries)), ("Issued", "", 1))

    def test_i10_a_press_that_stopped_after_its_stock_entry_books_nothing_twice(self):
        shop = fs.FakeTenant(lose_answer=1)
        code, out = self.issue(shop)
        self.assertEqual(code, 502)                         # the shop tells the user to check before trying again
        (iss,) = shop.issues.values()
        self.assertEqual(iss["status"], "Pending")
        self.assertTrue(shop.settings[fs.CO]["run_started"])     # the stamp stays: the shop may still be writing
        self.assertEqual(self.issue(shop)[1]["message"]["body"], app.BUSY)
        self.assertEqual(len(shop.entries), 1)
        self.issue(shop, now=NOW + app.LOCK_S + 1)          # the stamp has lapsed: the entry is found by its link
        self.assertEqual((iss["status"], len(shop.entries)), ("Issued", 1))
        self.assertEqual(iss["stock_entry"], next(iter(shop.entries)))
        self.assertEqual(shop.settings[fs.CO]["run_started"], "")

    def test_i10b_a_lost_answer_on_the_issue_itself_keeps_the_stamp_too(self):
        shop = fs.FakeTenant()
        real = shop.create

        def lost(doctype, b):
            out = real(doctype, b)
            if doctype.endswith(" Issue"):
                raise app.TenantError("POST -> TimeoutError")
            return out
        shop.create = lost
        self.assertEqual(self.issue(shop)[0], 502)
        shop.create = real
        self.assertEqual(self.issue(shop)[1]["message"]["body"], app.BUSY)
        self.issue(shop, now=NOW + app.LOCK_S + 1)
        self.assertEqual(len(shop.issues), 1)               # the sales were claimed once
        self.assertEqual(len(shop.entries), 1)

    def test_i11_another_press_running_touches_nothing(self):
        stamp = datetime.datetime.fromtimestamp(NOW - 20, datetime.timezone.utc).isoformat(timespec="seconds")
        shop = fs.FakeTenant(settings_=fs.settings(run_started=stamp))
        code, out = self.issue(shop)
        self.assertEqual(out["message"]["body"], app.BUSY)
        self.assertEqual((shop.issues, shop.entries), ({}, {}))

    def test_i12_two_presses_stamping_at_once_one_loses(self):
        shop = fs.FakeTenant(stale_lock=1)
        code, out = self.issue(shop)
        self.assertEqual(out["message"]["body"], app.BUSY)
        self.assertEqual(shop.issues, {})

    def test_i13_a_dead_presss_stamp_is_taken_over_and_every_stamp_is_cleared(self):
        stamp = datetime.datetime.fromtimestamp(NOW - 300, datetime.timezone.utc).isoformat(timespec="seconds")
        shop = fs.FakeTenant(settings_=fs.settings(run_started=stamp))
        self.issue(shop)
        self.assertEqual(len(shop.entries), 1)
        self.assertEqual(shop.settings[fs.CO]["run_started"], "")

    def test_i14_the_budget_leaves_the_rest_for_the_next_press(self):
        shop = fs.FakeTenant()
        shop.sales.append({"name": "S3", "posting_date": "2026-10-21", "posting_time": "09:00:00", "owner": "ana@x",
                           "set_warehouse": fs.STORE, "pos_profile": "Café", "company": fs.CO, "docstatus": 1,
                           "items": [{"item_code": "BURGER", "qty": 1, "stock_qty": 1, "net_amount": 80}]})
        code, out = self.issue(shop, clock=Clock(step=3.0))
        self.assertIn("press Issue ingredients again", out["message"]["body"])
        self.assertEqual([i["posting_date"] for i in shop.issues.values()], ["2026-10-21"])     # oldest day first
        self.issue(shop)
        self.assertEqual(len(shop.issues), 2)

    def test_i15_the_shops_refusal_is_kept_on_the_issue_in_its_own_words(self):
        shop = fs.FakeTenant(refuse_entry=("UOMMustBeIntegerError", "Quantity (0.5) cannot be a fraction in row 1"))
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual(iss["status"], "Refused")
        self.assertIn("cannot be a fraction", iss["problem"])

    def test_i16_a_day_that_sold_nothing_with_a_recipe_claims_its_sales_and_books_nothing(self):
        shop = fs.FakeTenant(sales=[{"name": "S5", "posting_date": "2026-10-22", "posting_time": "10:00:00", "owner": "x",
                                     "set_warehouse": fs.STORE, "pos_profile": "Café", "company": fs.CO, "docstatus": 1,
                                     "items": [{"item_code": "SALAD", "qty": 1, "stock_qty": 1, "net_amount": 30}]}])
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual((iss["status"], shop.entries), ("Nothing to issue", {}))

    def test_i16b_a_store_day_whose_recipe_goes_round_is_not_taken_up_until_it_is_fixed(self):
        shop = fs.FakeTenant()
        shop.boms["BOM-BURGER"]["items"].append({"item_code": "BURGER", "stock_qty": 1, "bom_no": "BOM-BURGER"})
        shop.items["BURGER"]["is_stock_item"] = 0
        out = self.issue(shop)[1]
        self.assertEqual(shop.issues, {})
        self.assertIn("Not taken up, fix and press again", out["message"]["body"])
        shop.boms["BOM-BURGER"]["items"].pop()
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual((iss["status"], iss["sales"]), ("Issued", "S1\nS2"))

    def test_i16c_a_refused_issue_is_tried_again_with_the_recipe_as_it_is_now(self):
        shop = fs.FakeTenant()
        real = shop.create
        refuse = {"on": True}

        def refused(doctype, b):
            if doctype == "Stock Entry" and refuse["on"] and any(r["item_code"] == "PATTY" for r in b["items"]):
                raise app.TenantError("417", 417, "ValidationError", "PATTY: no valuation rate")
            return real(doctype, b)
        shop.create = refused
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual(iss["status"], "Refused")
        shop.boms["BOM-BURGER"]["items"] = [{"item_code": "BUN", "stock_qty": 1}]     # the recipe fixed: no patty
        self.issue(shop)
        self.assertEqual(iss["status"], "Issued")
        (se,) = shop.entries.values()
        self.assertEqual(sorted(r["item_code"] for r in se["items"]), ["BEANS", "BUN", "MILK"])

    def test_i16d_an_issue_left_out_is_never_tried_again(self):
        shop = fs.FakeTenant(stock={"BUN": 0, "PATTY": 20, "MILK": 5, "BEANS": 1})
        self.issue(shop)
        (iss,) = shop.issues.values()
        iss["status"] = "Left out"                          # a manager's choice
        shop.stock["BUN"] = 10
        self.issue(shop)
        self.assertEqual((iss["status"], shop.entries), ("Left out", {}))

    def test_i16e_new_sales_come_before_old_retries(self):
        shop = fs.FakeTenant(stock={"BUN": 0, "PATTY": 0, "MILK": 0, "BEANS": 0})
        for d in range(15, 21):                             # six stuck days
            shop.sales.append({"name": f"OLD{d}", "posting_date": f"2026-10-{d}", "posting_time": "10:00:00", "owner": "x",
                               "set_warehouse": fs.STORE, "pos_profile": "Café", "company": fs.CO, "docstatus": 1,
                               "items": [{"item_code": "BURGER", "qty": 1, "stock_qty": 1, "net_amount": 80}]})
        shop.settings[fs.CO]["start_from"] = "2026-10-15 00:00:00"
        self.issue(shop, now=NOW)
        self.assertEqual(sum(i["status"] == "Short" for i in shop.issues.values()), 7)
        shop.stock.update(BUN=50, PATTY=50, MILK=50, BEANS=50)
        shop.sales.append({"name": "NEW", "posting_date": "2026-10-22", "posting_time": "13:00:00", "owner": "x",
                           "set_warehouse": fs.STORE, "pos_profile": "Café", "company": fs.CO, "docstatus": 1,
                           "items": [{"item_code": "BURGER", "qty": 1, "stock_qty": 1, "net_amount": 80}]})
        self.issue(shop, clock=Clock(step=1.0))           # a second per look at the clock: retries first would starve it
        new = [i for i in shop.issues.values() if i["sales"] == "NEW"]
        self.assertEqual([i["status"] for i in new], ["Issued"])     # the new day first, retries with what is left

    def test_i17_a_cancelled_or_draft_sale_is_never_issued(self):
        shop = fs.FakeTenant()
        shop.sales[0]["docstatus"] = 2
        self.issue(shop)
        (iss,) = shop.issues.values()
        self.assertEqual(iss["sales"], "S2")

    def test_i18_the_apps_user_refused_is_said_in_words(self):
        shop = fs.FakeTenant(refuse=("LIST POS Invoice", 403))
        code, out = self.issue(shop)
        self.assertEqual((code, out["message"]["body"]), (200, app.REFUSED))

    # ── the press itself ──
    def test_p1_an_unsigned_or_wrongly_signed_press_is_refused(self):
        svc = self.svc(fs.FakeTenant())
        self.assertEqual(self.press(svc, "/press/issue", "PP RBO Settings", [fs.CO], secret="wrong")[0], 401)
        self.assertEqual(self.press(svc, "/press/issue", "PP RBO Settings", [fs.CO], secret=SECRETS["foodcost"])[0], 401)
        self.assertEqual(svc.handle("POST", "/press/issue", {}, b"{}")[0], 401)

    def test_p2_a_press_on_the_wrong_record_is_refused_before_anything_is_read(self):
        shop = fs.FakeTenant()
        code, out = self.press(self.svc(shop), "/press/issue", "Item", ["BUN"])
        self.assertEqual(code, 400)
        self.assertEqual(shop.calls, [])

    # ── Work out food cost ──
    def test_f1_food_cost_from_the_shops_own_ledger(self):
        shop = fs.FakeTenant()
        self.issue(shop)
        (se,) = shop.entries
        shop.entries["WASTE-1"] = {"name": "WASTE-1", "purpose": "Material Issue", "posting_date": "2026-10-22",
                                   "company": fs.CO, "docstatus": 1}
        shop.ledger = [{"item_code": "BUN", "actual_qty": -2, "stock_value_difference": -8, "voucher_type": "Stock Entry", "voucher_no": se},
                       {"item_code": "BUN", "actual_qty": -1, "stock_value_difference": -4, "voucher_type": "Stock Entry", "voucher_no": "WASTE-1"}]
        shop.recos = {"SR-1": [{"item_code": "BUN", "qty": 10, "current_qty": 11, "amount_difference": -4}]}
        shop.foodcosts["FC-1"] = {"name": "FC-1", "company": fs.CO, "store": fs.STORE, "from_date": "2026-10-22",
                                  "to_date": "2026-10-22", "modified": "m1"}
        code, out = self.press(self.svc(shop), "/press/foodcost", "PP RBO Food Cost", ["FC-1"])
        fc = shop.foodcosts["FC-1"]
        (bun,) = fc["lines"]
        self.assertEqual((bun["recipe_qty"], bun["other_qty"], bun["count_qty"], bun["actual_qty"]), (2, 1, 1, 4))
        self.assertEqual((fc["food_sales"], fc["theoretical_cost"], fc["actual_cost"]), (187, 8, 16))
        self.assertIn("% actual", out["message"]["body"])

    def test_f1b_a_desk_copy_is_the_shops_own_and_an_entry_from_before_a_reinstall_is_the_apps(self):
        shop = fs.FakeTenant()
        base = {"purpose": "Material Issue", "posting_date": "2026-10-22", "company": fs.CO, "docstatus": 1}
        shop.entries["COPY"] = dict(base, name="COPY", pp_rbo_issue="RBO-ISS-00001", remarks="PP RBO: the ingredients of 3 sales")
        shop.entries["OLD"] = dict(base, name="OLD", remarks="PP RBO: the ingredients of 2 sales at Café on 2026-10-22")
        shop.ledger = [{"item_code": "BUN", "actual_qty": -1, "stock_value_difference": -4, "voucher_type": "Stock Entry", "voucher_no": "COPY"},
                       {"item_code": "BUN", "actual_qty": -2, "stock_value_difference": -8, "voucher_type": "Stock Entry", "voucher_no": "OLD"}]
        shop.foodcosts["FC-4"] = {"name": "FC-4", "company": fs.CO, "store": fs.STORE, "from_date": "2026-10-22",
                                  "to_date": "2026-10-22", "modified": "m"}
        self.press(self.svc(shop), "/press/foodcost", "PP RBO Food Cost", ["FC-4"])
        (bun,) = shop.foodcosts["FC-4"]["lines"]
        self.assertEqual((bun["recipe_qty"], bun["other_qty"]), (2, 1))

    def test_f2_a_period_too_long_or_back_to_front_is_refused_in_words(self):
        shop = fs.FakeTenant()
        shop.foodcosts["FC-2"] = {"name": "FC-2", "company": fs.CO, "store": fs.STORE, "from_date": "2026-01-01",
                                  "to_date": "2026-10-22", "modified": "m"}
        out = self.press(self.svc(shop), "/press/foodcost", "PP RBO Food Cost", ["FC-2"])[1]
        self.assertIn("at most 92 days", out["message"]["body"])
        self.assertNotIn("lines", shop.foodcosts["FC-2"])

    def test_f3_an_edit_while_it_was_worked_out_is_never_written_over(self):
        shop = fs.FakeTenant()
        shop.foodcosts["FC-3"] = {"name": "FC-3", "company": fs.CO, "store": fs.STORE, "from_date": "2026-10-22",
                                  "to_date": "2026-10-22", "modified": "m1"}
        real = shop.rows

        def edit_meanwhile(doctype, *a, **k):
            if doctype == "Stock Ledger Entry":
                shop.foodcosts["FC-3"]["modified"] = "m2"
            return real(doctype, *a, **k)
        shop.rows = edit_meanwhile
        out = self.press(self.svc(shop), "/press/foodcost", "PP RBO Food Cost", ["FC-3"])[1]
        self.assertIn("changed while it was worked out", out["message"]["body"])
        self.assertNotIn("lines", shop.foodcosts["FC-3"])

    # ── Check allergens ──
    def press_check(self, shop, names):
        return self.press(self.svc(shop), "/press/allergens", "Item", names)[1]

    def test_a1_every_finding_is_written_to_a_check_record_the_answer_opens(self):
        shop = fs.FakeTenant()
        out = self.press_check(shop, ["BURGER", "COFFEE", "SALAD"])
        (chk,) = shop.checks.values()
        found = {(r["item_code"], r["finding"]): r["detail"] for r in chk["lines"]}
        self.assertEqual(found[("BURGER", "Misses an allergen of its recipe")], "Sesame (from BUN)")
        self.assertIn("Diary", found[("COFFEE", "Not on your allergen list")])
        self.assertIn(("SALAD", "No recipe to check"), found)
        self.assertEqual(out["open_record"], {"doctype": "PP RBO Allergen Check", "name": chk["name"]})
        self.assertEqual((out["message"]["level"], chk["items_checked"], chk["flagged"]), ("warning", 3, 3))
        self.assertFalse([c for c in shop.calls if c.startswith("PUT") or (c.startswith("POST") and "Check" not in c)])

    def test_a2_a_stocked_sauces_own_recipe_is_read_for_its_allergens(self):
        shop = fs.FakeTenant()
        shop.items.update(MAYO={"is_stock_item": 1, "default_bom": "BOM-MAYO", "stock_uom": "Litre"},
                          EGG={"is_stock_item": 1, "stock_uom": "Nos", "pp_rbo_allergens": "Eggs"})
        shop.boms["BOM-MAYO"] = {"docstatus": 1, "is_active": 1, "quantity": 1, "items": [{"item_code": "EGG", "stock_qty": 2}]}
        shop.boms["BOM-BURGER"]["items"].append({"item_code": "MAYO", "stock_qty": 0.02})
        shop.items["BURGER"]["pp_rbo_allergens"] = "Cereals containing gluten, Sesame"
        self.press_check(shop, ["BURGER"])
        (chk,) = shop.checks.values()
        self.assertEqual([(r["finding"], r["detail"]) for r in chk["lines"]],
                         [("Misses an allergen of its recipe", "Eggs (from EGG)")])

    def test_a3_a_variant_with_none_of_its_templates_allergens_is_named(self):
        shop = fs.FakeTenant()
        shop.items["BURGER-DBL"] = {"is_stock_item": 0, "default_bom": "BOM-BURGER", "variant_of": "BURGER"}
        shop.items["BURGER"]["pp_rbo_allergens"] = "Cereals containing gluten, Sesame"
        self.press_check(shop, ["BURGER-DBL"])
        (chk,) = shop.checks.values()
        self.assertIn(("BURGER-DBL", "Variant with no allergens"), {(r["item_code"], r["finding"]) for r in chk["lines"]})

    def test_a4_a_dish_naming_them_all_writes_nothing_and_says_so(self):
        shop = fs.FakeTenant()
        shop.items["BURGER"]["pp_rbo_allergens"] = "Cereals containing gluten, Sesame"
        out = self.press_check(shop, ["BURGER"])
        self.assertEqual(out["message"]["body"], "1 item names every allergen of its recipe.")
        self.assertNotIn("open_record", out)

    def test_a5_no_allergen_list_is_said_on_the_check(self):
        shop = fs.FakeTenant(settings_=fs.settings(allergens=""))
        self.press_check(shop, ["COFFEE"])
        (chk,) = shop.checks.values()
        self.assertIn("No allergen list", [r["finding"] for r in chk["lines"]])

    def test_a6_every_answer_holds_the_message_limits(self):
        shop = fs.FakeTenant()
        for code in list(shop.items):
            shop.items[code]["pp_rbo_allergens"] = ", ".join(f"Word{i}" for i in range(40))
        out = self.press_check(shop, list(shop.items))
        self.assertLessEqual(len(out["message"]["body"]), 280)


class Library(unittest.TestCase):
    def test_l1_the_librarys_copy_needs_its_prefix(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": "ivendnext_rbo", "IVN_SHOPS_FILE": "/nonexistent"})
        bo.use_prefix("PP RBO")


if __name__ == "__main__":
    unittest.main()
