"""S38's laptop tests: the real service, a stand-in for the shop's record API, presses signed exactly as the shop signs
them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s38_expiry_markdown/tests -p 'test_*.py'

On our test bench the real Desk button was pressed on real lots and the till rang them; these prove the service's own
duties fast, and are what the mutation canary turns RED."""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import markdown  # noqa: E402

SECRET = "s38-test-secret"
NOW = datetime.datetime(2026, 10, 22, 6, 0, tzinfo=datetime.timezone.utc).timestamp()   # the shop's day: 2026-10-22
TODAY = datetime.date(2026, 10, 22)
PL = "Standard Selling"


def day(n: int) -> str:
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def groups():
    """All Item Groups › Food (5 days 25%, 2 days 50%) › Dairy (none of its own: Food's) and Bakery (1 day 30% only);
    Hardware (none)."""
    return [{"name": "All Item Groups", "lft": 1, "rgt": 10},
            {"name": "Food", "lft": 2, "rgt": 7, "pp_exm_days_1": 5, "pp_exm_pct_1": 25, "pp_exm_days_2": 2, "pp_exm_pct_2": 50},
            {"name": "Dairy", "lft": 3, "rgt": 4},
            {"name": "Bakery", "lft": 5, "rgt": 6, "pp_exm_days_1": 1, "pp_exm_pct_1": 30},
            {"name": "Hardware", "lft": 8, "rgt": 9}]


def lots():
    return {"MILK-L1": {"item": "MILK", "expiry_date": day(4), "batch_qty": 12},     # first step: 25%
            "MILK-L2": {"item": "MILK", "expiry_date": day(1), "batch_qty": 3},      # last step: 50%
            "MILK-L3": {"item": "MILK", "expiry_date": day(9), "batch_qty": 20},     # not due
            "MILK-L4": {"item": "MILK", "expiry_date": day(-1), "batch_qty": 2},     # past its date
            "BREAD-L1": {"item": "BREAD", "expiry_date": day(1), "batch_qty": 5},    # Bakery's own step: 30%
            "BREAD-L2": {"item": "BREAD", "expiry_date": day(2), "batch_qty": 5},    # Bakery: not due (Food's 2 days ignored)
            "NAIL-L1": {"item": "NAIL", "expiry_date": day(1), "batch_qty": 5},      # Hardware: no steps
            "EGG-L1": {"item": "EGG", "expiry_date": day(3), "batch_qty": 5}}        # no price on the list


ITEMS = {"MILK": {"item_group": "Dairy"}, "BREAD": {"item_group": "Bakery"}, "NAIL": {"item_group": "Hardware"},
         "EGG": {"item_group": "Dairy"}}


def prices():
    return [{"name": "ip-milk", "item_code": "MILK", "uom": "Nos", "price_list": PL, "price_list_rate": 3.99},
            {"name": "ip-milk-crate", "item_code": "MILK", "uom": "Crate", "price_list": PL, "price_list_rate": 45.0},
            {"name": "ip-milk-vip", "item_code": "MILK", "uom": "Nos", "price_list": PL, "price_list_rate": 2.0,
             "customer": "VIP", "valid_from": day(-1)},                                # a customer's own price: not the base
            {"name": "ip-milk-buy", "item_code": "MILK", "uom": "Nos", "price_list": PL, "price_list_rate": 1.0,
             "supplier": "Dairy Co", "valid_from": day(-1)},                           # a supplier's price: not the base
            {"name": "ip-milk-later", "item_code": "MILK", "uom": "Nos", "price_list": PL, "price_list_rate": 9.0,
             "valid_from": day(3)},                                                    # not valid today: not the base
            {"name": "ip-bread", "item_code": "BREAD", "uom": "Nos", "price_list": PL, "price_list_rate": 2.5},
            {"name": "ip-nail", "item_code": "NAIL", "uom": "Nos", "price_list": PL, "price_list_rate": 0.1},
            {"name": "ip-milk-other-list", "item_code": "MILK", "uom": "Nos", "price_list": "Wholesale", "price_list_rate": 3.0}]


class FakeTenant:
    """The shop's record API: settings, lots, items, the group tree, price lists and Item Price rows (created, updated
    with the shop's ``modified`` check, deleted)."""

    def __init__(self, settings=None, refuse=None, edit_before_update=0, duplicate_on_create=0, number_format="#,###.##",
                 price_list=None, clock=None, lists=None):
        # None: the shop's usual settings; False: no record Default at all
        self.settings = {"price_list": PL, "hours_from_utc": 3} if settings is None else None if settings is False else settings
        self.lots, self.items, self.groups = lots(), copy.deepcopy(ITEMS), groups()
        self.prices = {p["name"]: dict({"modified": "2026-10-20 10:00:00.000001", "batch_no": None, "customer": None,
                                        "supplier": None, "valid_from": None, "valid_upto": None, "note": None,
                                        "packing_unit": 0}, **p) for p in prices()}
        self.price_list = price_list if price_list is not None else {"selling": 1, "enabled": 1, "currency": "AED"}
        self.lists = lists or {}            # the shop's other price lists: {name: {selling, enabled, currency}}
        self.number_format, self.refuse, self.clock = number_format, refuse, clock
        self.edit_before_update, self.duplicate_on_create = edit_before_update, duplicate_on_create
        self.writes, self.n, self.doctypes = [], 0, set()

    def _refused(self):
        if self.refuse:
            raise app.TenantError("GET -> HTTP %d" % self.refuse, self.refuse)
        if self.clock:
            self.clock.tick()

    def doc(self, doctype, name):
        self._refused()
        if doctype == "PP EXM Settings" or doctype.endswith(" Settings"):
            if self.settings is None or name != "Default":
                raise app.TenantError("GET -> HTTP 404", 404)
            return dict(self.settings, name="Default")
        if doctype == "Price List":
            if not self.price_list or name != PL:
                raise app.TenantError("GET -> HTTP 404", 404)
            return dict(self.price_list, name=name)
        if doctype == "Currency":
            return {"name": name, "number_format": self.number_format, "fraction_units": 100}
        raise app.TenantError("GET -> HTTP 404", 404)

    def rows(self, doctype, fields, filters):
        self._refused()
        if doctype == "Batch":
            names = filters[0][2]
            return [dict(self.lots[n], name=n) for n in names if n in self.lots]
        if doctype == "Item":
            return [dict(self.items[n], name=n) for n in filters[0][2] if n in self.items]
        if doctype == "Item Group":
            return copy.deepcopy(self.groups)
        if doctype == "Price List":
            out = [dict(v, name=k) for k, v in dict(self.lists, **{PL: self.price_list or {}}).items()]
            for f, op, v in filters:
                out = [r for r in out if (r.get(f) == v) == (op == "=")]
            return out
        if doctype == "Item Price":
            out = list(self.prices.values())
            for f, op, v in filters:
                if op == "=":
                    out = [r for r in out if r.get(f) == v]
                elif op == "in":
                    out = [r for r in out if r.get(f) in v]
                elif op == "like":       # the shop's LIKE ignores case
                    out = [r for r in out if isinstance(r.get(f), str) and r[f].lower().startswith(v.rstrip("%").lower())]
                elif op == "<":
                    out = [r for r in out if r.get(f) and r[f] < v]
            return copy.deepcopy(out)
        raise app.TenantError("GET -> HTTP 403", 403)

    def create(self, doctype, body):
        self._refused()
        if self.duplicate_on_create:            # a second press created the same lot's row a moment before
            self.duplicate_on_create -= 1
            raise app.TenantError("POST -> HTTP 409", 409, "DuplicateEntryError")
        self.n += 1
        name = f"new-{self.n}"
        self.prices[name] = dict(body, name=name, modified=f"2026-10-22 06:00:{self.n:02d}.000001")
        self.writes.append(("create", name, copy.deepcopy(body)))
        self.doctypes.add(doctype)
        return copy.deepcopy(self.prices[name])

    def update(self, doctype, name, body):
        self._refused()
        if self.edit_before_update:
            self.edit_before_update -= 1
            self.prices[name]["modified"] = "2026-10-22 06:59:59.000001"
        if body.get("modified") != self.prices[name]["modified"]:
            raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
        self.prices[name].update({k: v for k, v in body.items() if k != "modified"})
        self.writes.append(("update", name, copy.deepcopy(body)))
        self.doctypes.add(doctype)
        return copy.deepcopy(self.prices[name])

    def delete(self, doctype, name):
        self._refused()
        if name not in self.prices:
            raise app.TenantError("DELETE -> HTTP 404", 404)
        del self.prices[name]
        self.writes.append(("delete", name, None))
        self.doctypes.add(doctype)

    def lot_rows(self, lot):
        return sorted((r for r in self.prices.values() if r.get("batch_no") == lot), key=lambda r: r["uom"])


class Clock:
    """A clock the tenant moves one second per call: a press stops starting lots after the budget."""

    def __init__(self):
        self.t = 0.0

    def tick(self):
        self.t += 1.0

    def __call__(self):
        return self.t


def body(names=("MILK-L1",), records=None, **extra):
    recs = records if records is not None else [{"doctype": "Batch", "name": n, "fields": {"name": n}} for n in names]
    ctx = {"v": 1, "action": "x", "label": "Mark down", "user": "stock@shop.example", "lang": "en", "records": recs,
           "inputs": {}, "idempotency_key": "key-0001-abcdef", **extra}
    return json.dumps({"point": "desk_action/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=SECRET, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.use(FakeTenant())

    def use(self, tenant, clock=None):
        self.tenant = tenant
        self.svc = app.Service({"PP_POINT_SECRET": SECRET}, tenant, clock=clock or (lambda: 0.0), now=NOW)

    def press(self, *names, raw=None, secret=SECRET):
        raw = raw if raw is not None else body(names or ("MILK-L1",))
        return self.svc.handle("POST", "/press/markdown", signed(raw, secret), raw)

    def test_s1_a_lot_in_its_first_step_gets_its_own_price_until_its_expiry_date(self):
        code, out = self.press("MILK-L1")
        self.assertEqual((code, out["message"]["level"], out["refresh"]), (200, "success", True))
        self.assertIn("Marked down 1 lot.", out["message"]["body"])
        rows = self.tenant.lot_rows("MILK-L1")
        self.assertEqual([(r["uom"], r["price_list_rate"]) for r in rows], [("Crate", 33.75), ("Nos", 2.99)])
        for r in rows:       # 3.99 less 25% is 2.9925: rounded DOWN, never more than the step promises
            self.assertEqual((r["price_list"], r["batch_no"], r["valid_from"], r["valid_upto"], r["note"], r["item_code"]),
                             (PL, "MILK-L1", TODAY.isoformat(), day(4), "PP EXM: 25% off until it expires", "MILK"))

    def test_s2_a_lot_in_its_last_step_takes_the_last_percent(self):
        self.press("MILK-L2")
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("MILK-L2")], [22.5, 1.99])

    def test_s3_a_second_press_writes_nothing(self):
        self.press("MILK-L1", "MILK-L2")
        n = len(self.tenant.writes)
        code, out = self.press("MILK-L1", "MILK-L2")
        self.assertEqual((len(self.tenant.writes), out["message"]["body"]), (n, "2 lots already marked down."))

    def test_s4_a_lot_that_reaches_its_last_step_is_changed_with_the_row_as_read(self):
        self.press("MILK-L1")
        self.tenant.lots["MILK-L1"]["expiry_date"] = day(2)
        self.tenant.writes.clear()
        self.press("MILK-L1")
        self.assertEqual([w[0] for w in self.tenant.writes], ["update", "update"])
        self.assertTrue(all(w[2]["modified"] for w in self.tenant.writes))
        self.assertEqual([r["note"] for r in self.tenant.lot_rows("MILK-L1")], ["PP EXM: 50% off until it expires"] * 2)

    def test_s5_a_lot_not_yet_due_or_with_no_steps_is_never_written(self):
        code, out = self.press("MILK-L3", "NAIL-L1", "BREAD-L2")
        self.assertEqual((self.tenant.writes, out["message"]["body"]), ([], "3 lots not yet due."))

    def test_s6_the_nearest_group_with_steps_wins(self):
        self.press("BREAD-L1")     # Bakery's own 1 day 30%, not Food's 50%
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("BREAD-L1")], [1.75])

    def test_s7_a_lot_past_its_date_out_of_stock_or_out_of_every_step_has_the_apps_price_taken_off(self):
        for lot in ("MILK-L1", "MILK-L2"):
            self.press(lot)
        self.tenant.lots["MILK-L1"]["batch_qty"] = 0
        self.tenant.groups[1].update(pp_exm_days_2=None, pp_exm_pct_2=None)   # the last step taken off Food
        self.tenant.writes.clear()
        code, out = self.press("MILK-L1", "MILK-L2")
        self.assertEqual(self.tenant.lot_rows("MILK-L1"), [])
        self.assertEqual([r["note"] for r in self.tenant.lot_rows("MILK-L2")], ["PP EXM: 25% off until it expires"] * 2)
        self.assertIn("Took the markdown off 1 lot.", out["message"]["body"])

    def test_s1b_another_lots_markdown_is_never_the_base(self):
        self.press("MILK-L2")              # L2's own rows now exist, dated today: still not the item's price for L1
        self.press("MILK-L1")
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("MILK-L1")], [33.75, 2.99])

    def test_s7c_a_disabled_lot_has_the_apps_price_taken_off(self):
        self.press("MILK-L1")
        self.tenant.lots["MILK-L1"]["disabled"] = 1
        self.press("MILK-L1")
        self.assertEqual(self.tenant.lot_rows("MILK-L1"), [])

    def test_s7b_a_lot_past_its_date_is_never_marked_down(self):
        code, out = self.press("MILK-L4")
        self.assertEqual((self.tenant.writes, out["message"]["body"]), ([], "1 lot not yet due."))

    def test_s8_a_price_the_shop_typed_for_a_lot_is_never_changed(self):
        self.tenant.prices["ip-own"] = {"name": "ip-own", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                        "price_list_rate": 3.5, "batch_no": "MILK-L1", "note": "manager's own",
                                        "modified": "x"}
        self.tenant.prices["ip-own-2"] = {"name": "ip-own-2", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                          "price_list_rate": 3.5, "batch_no": "MILK-L2", "note": "PP EXM pricing by hand",
                                          "modified": "x"}      # the prefix without its colon is not the app's
        code, out = self.press("MILK-L1", "MILK-L2")
        self.assertEqual((self.tenant.writes, out["message"]["body"]), ([], "2 lots with a price of the shop's own, left as it is."))

    def test_s9_an_item_with_no_price_on_the_list_is_named(self):
        code, out = self.press("EGG-L1")
        self.assertEqual((out["message"]["level"], self.tenant.writes), ("warning", []))
        self.assertIn("no price on the list", out["message"]["body"])

    def test_s10_an_edit_saved_between_the_read_and_the_write_is_never_written_over(self):
        self.press("MILK-L1")
        self.tenant.lots["MILK-L1"]["expiry_date"] = day(1)
        self.tenant.edit_before_update = 1
        self.tenant.writes.clear()
        code, out = self.press("MILK-L1")
        self.assertEqual(self.tenant.writes, [])
        self.assertIn("changed meanwhile: press again", out["message"]["body"])

    def test_s10b_a_second_press_creating_the_same_row_first_is_no_failure(self):
        self.tenant.duplicate_on_create = 1
        code, out = self.press("MILK-L1")
        self.assertEqual(code, 200)
        self.assertIn("changed meanwhile", out["message"]["body"])

    def test_s11_the_apps_expired_prices_are_swept_and_the_shops_own_never(self):
        self.tenant.prices["shop-old"] = {"name": "shop-old", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                          "batch_no": "OLD-S", "valid_upto": day(-3), "price_list_rate": 1.0,
                                          "note": "pp exm: typed by the manager", "modified": "x"}   # the LIKE finds it
        self.tenant.prices["live-own"] = {"name": "live-own", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                          "batch_no": "LIVE-1", "valid_upto": day(3), "price_list_rate": 2.99,
                                          "note": "PP EXM: 25% off until it expires", "modified": "x"}   # live: never swept
        for i in range(25):
            self.tenant.prices[f"old-{i}"] = {"name": f"old-{i}", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                              "batch_no": f"OLD-{i}", "valid_upto": day(-3), "price_list_rate": 1.0,
                                              "note": "PP EXM: 25% off until it expires", "modified": "x"}
        code, out = self.press("MILK-L3")
        self.assertEqual(len([w for w in self.tenant.writes if w[0] == "delete"]), app.SWEEP)
        self.assertNotIn("shop-old", [w[1] for w in self.tenant.writes])
        self.assertNotIn("live-own", [w[1] for w in self.tenant.writes])
        self.assertIn(f"Removed {app.SWEEP} expired markdowns.", out["message"]["body"])

    def test_s12_a_press_stops_in_time_and_says_how_many_are_left(self):
        clock = Clock()
        self.use(FakeTenant(clock=clock), clock=clock)
        names = [f"MILK-X{i}" for i in range(30)]
        for n in names:
            self.tenant.lots[n] = {"item": "MILK", "expiry_date": day(4), "batch_qty": 1}
        code, out = self.press(*names)
        done = len({w[2]["batch_no"] for w in self.tenant.writes if w[0] == "create"})
        self.assertLess(done, 30)
        self.assertEqual(out["message"]["level"], "warning")
        self.assertIn(f"Did {done} of 30 lots. Press Mark down again for the rest.", out["message"]["body"])

    def test_s13_the_currencys_own_digits_are_the_grain(self):
        self.use(FakeTenant(number_format="#,###.###"))     # KWD: three digits
        self.press("MILK-L1")
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("MILK-L1")], [33.75, 2.992])
        self.use(FakeTenant(number_format="#,###"))         # JPY: 100 sen to the yen, and no digits shown
        self.press("MILK-L1")
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("MILK-L1")], [33.0, 2.0])

    def test_s13b_a_currency_the_app_cannot_read_writes_nothing(self):
        self.tenant.doc = (lambda orig: lambda dt, name: (_ for _ in ()).throw(app.TenantError("GET -> HTTP 404", 404))
                           if dt == "Currency" else orig(dt, name))(self.tenant.doc)
        code, out = self.press("MILK-L1")
        self.assertEqual((out["message"]["level"], self.tenant.writes), ("warning", []))

    def test_s4b_a_newer_item_price_moves_the_lots_row_to_today(self):
        """The shop's lookup reads the newest valid_from first and the lot only after it: a lot row older than the item's
        own row would never be read. A new item price from yesterday: the press moves the lot's row to today, re-priced."""
        self.tenant.prices["ip-old-lot"] = {"name": "ip-old-lot", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                            "batch_no": "MILK-L1", "price_list_rate": 2.99, "valid_from": day(-5),
                                            "valid_upto": day(4), "note": "PP EXM: 25% off until it expires", "modified": "x"}
        self.tenant.prices["ip-milk"].update(valid_from=day(-1))     # the same price, re-entered from yesterday
        self.press("MILK-L1")
        row = self.tenant.prices["ip-old-lot"]
        self.assertEqual((row["valid_from"], row["price_list_rate"]), (TODAY.isoformat(), 2.99))

    def test_s14_no_settings_or_a_list_the_tills_do_not_sell_from_is_said_in_words(self):
        self.use(FakeTenant(settings={}))
        self.assertEqual(self.press()[1]["message"]["body"], app.NO_SETTINGS)
        self.use(FakeTenant(settings=False))    # no record Default at all
        self.assertEqual(self.press()[1]["message"]["body"], app.NO_SETTINGS)
        self.use(FakeTenant(price_list={"selling": 0, "enabled": 1}))
        self.assertEqual(self.press()[1]["message"]["body"], app.bad_list(PL))
        self.assertEqual(self.tenant.writes, [])

    def test_s15_the_apps_user_refused_by_the_shop_is_said_in_words(self):
        self.use(FakeTenant(refuse=403))
        self.assertEqual(self.press()[1]["message"]["body"], app.REFUSED)
        self.use(FakeTenant(refuse=500))
        self.assertEqual(self.press()[0], 502)

    def test_s16_the_shops_day_decides_the_days_left(self):
        # 22:00 UTC on 2026-10-21 is already 2026-10-22 at UTC+3: MILK-L1 has 4 days left (25%), not 5
        self.svc.now = datetime.datetime(2026, 10, 21, 22, 0, tzinfo=datetime.timezone.utc).timestamp()
        self.tenant.lots["MILK-L1"]["expiry_date"] = day(5)
        self.press("MILK-L1")
        self.assertEqual(self.tenant.lot_rows("MILK-L1")[0]["valid_from"], TODAY.isoformat())

    def test_a_press_must_name_one_to_100_lots(self):
        for recs in ([], [{"doctype": "Sales Order", "name": "SO-1"}],
                     [{"doctype": "Batch", "name": f"L{i}"} for i in range(101)]):
            raw = body(records=recs)
            self.assertEqual(self.press(raw=raw)[0], 400)

    def test_a_press_signed_with_another_secret_or_late_is_refused(self):
        self.assertEqual(self.press(secret="other")[0], 401)
        raw = body()
        self.assertEqual(self.svc.handle("POST", "/press/markdown", signed(raw, ts=time.time() - 600), raw)[0], 401)
        self.assertEqual(self.tenant.writes, [])

    def test_every_answer_fits_the_answers_limit(self):
        long = {k: 10 ** 6 for k, *_ in markdown.WORDS}
        self.assertLessEqual(len(markdown.answer(long, 1, 100, 99)["message"]["body"]), 280)


MEMBER, STAFF, CLUB, EURO, AUSTIN = "Member Prices", "Staff Prices", "Club Prices", "Euro Prices", "Austin Prices"


def other_lists():
    """The shop's other price lists: a member list (milk 3.49, a crate 39.99), a staff list (2.50), a store's own list
    (4.29), a club list with no milk price, a list in another currency, a buying list and a list switched off."""
    on = {"selling": 1, "enabled": 1, "currency": "AED"}
    return {MEMBER: on, STAFF: on, AUSTIN: on, CLUB: on, EURO: dict(on, currency="EUR"),
            "Buying": dict(on, selling=0), "Old Members": dict(on, enabled=0)}


def rings(tenant, price_list, lot, uom="Nos"):
    """What the till charges for one ``lot`` of MILK to a customer on ``price_list``, read the way the shop reads it
    (``get_item_price``: the list's rows for the item with no lot or this lot, valid today, for no particular customer,
    newest ``valid_from`` first and the lot before the lot-less row), and the till's fallback to the store's list when
    the customer's list has no price (``apply_price_list_fallback``)."""
    def first(pl):
        rows = [r for r in tenant.prices.values() if r["item_code"] == "MILK" and r["price_list"] == pl
                and r.get("uom") == uom and (r.get("batch_no") or "") in ("", lot) and not r.get("customer")
                and not r.get("supplier") and (r.get("valid_from") or "2000-01-01") <= TODAY.isoformat()
                <= (r.get("valid_upto") or "2500-12-31")]
        rows.sort(key=lambda r: (r.get("valid_from") or "", r.get("batch_no") or ""), reverse=True)
        return rows[0]["price_list_rate"] if rows else 0
    return first(price_list) or first(PL)


class OtherLists(unittest.TestCase):
    """A member, priced from the member list, paid 3.49 for a lot of milk marked down to 2.99 on the store's list, while
    a walk-in paid 2.99. Each other selling list in the currency that prices the item now gets the lot's own price too:
    the same step's percent off that list's own price."""

    use, press = ServiceTest.use, ServiceTest.press

    def setUp(self):
        self.use(FakeTenant(lists=other_lists()))
        for name, pl, uom, rate in (("ip-milk-member", MEMBER, "Nos", 3.49), ("ip-milk-member-crate", MEMBER, "Crate", 39.99),
                                    ("ip-milk-staff", STAFF, "Nos", 2.50), ("ip-milk-austin", AUSTIN, "Nos", 4.29),
                                    ("ip-milk-euro", EURO, "Nos", 4.20), ("ip-milk-buying", "Buying", "Nos", 4.50),
                                    ("ip-milk-old", "Old Members", "Nos", 3.29)):
            self.tenant.prices[name] = dict(self.tenant.prices["ip-milk"], name=name, price_list=pl, uom=uom,
                                            price_list_rate=rate)

    def lists_of(self, lot):
        return {(r["price_list"], r["uom"]): r["price_list_rate"] for r in self.tenant.lot_rows(lot)}

    def test_m1_a_member_pays_the_steps_percent_off_the_member_price_never_more_than_a_walk_in(self):
        self.assertEqual((rings(self.tenant, PL, "MILK-L1"), rings(self.tenant, MEMBER, "MILK-L1")), (3.99, 3.49))
        code, out = self.press("MILK-L1")
        self.assertEqual(out["message"]["body"], "Marked down 1 lot.")
        self.assertEqual((rings(self.tenant, PL, "MILK-L1"), rings(self.tenant, MEMBER, "MILK-L1")), (2.99, 2.61))
        self.assertEqual(rings(self.tenant, MEMBER, "MILK-L1", uom="Crate"), 29.99)   # 39.99 less 25%, rounded down
        self.assertEqual(rings(self.tenant, MEMBER, "MILK-L3"), 3.49)       # another lot of the same milk: the member price
        member = [r for r in self.tenant.lot_rows("MILK-L1") if r["price_list"] == MEMBER][0]
        self.assertEqual((member["batch_no"], member["valid_from"], member["valid_upto"], member["note"]),
                         ("MILK-L1", TODAY.isoformat(), day(4), "PP EXM: 25% off until it expires"))

    def test_m2_no_price_for_the_item_another_currency_buying_only_or_switched_off_gets_nothing(self):
        self.press("MILK-L1")
        written = {r["price_list"] for r in self.tenant.lot_rows("MILK-L1")}
        self.assertEqual(written, {PL, MEMBER, STAFF, AUSTIN})   # not club (no milk price), euro, buying or switched off
        self.assertEqual(rings(self.tenant, CLUB, "MILK-L1"), 2.99)   # the till takes the store's list, lot and all

    def test_m3_every_list_takes_the_steps_percent_off_its_own_price(self):
        self.press("MILK-L1")
        self.assertEqual({pl: rings(self.tenant, pl, "MILK-L1") for pl in (PL, MEMBER, STAFF, AUSTIN)},
                         {PL: 2.99, MEMBER: 2.61, STAFF: 1.87, AUSTIN: 3.21})   # 25% off 3.99, 3.49, 2.50, 4.29

    def test_m4_the_last_step_reaches_every_list_and_a_second_press_writes_nothing(self):
        self.press("MILK-L1")
        self.tenant.lots["MILK-L1"]["expiry_date"] = day(2)                 # 50%
        self.press("MILK-L1")
        self.assertEqual({pl: rings(self.tenant, pl, "MILK-L1") for pl in (PL, MEMBER, STAFF, AUSTIN, CLUB)},
                         {PL: 1.99, MEMBER: 1.74, STAFF: 1.25, AUSTIN: 2.14, CLUB: 1.99})
        self.tenant.writes.clear()
        code, out = self.press("MILK-L1")
        self.assertEqual((self.tenant.writes, out["message"]["body"]), ([], "1 lot already marked down."))

    def test_m5_a_list_whose_price_changed_is_marked_down_from_its_new_price_at_the_next_press(self):
        self.press("MILK-L1")
        self.tenant.prices["ip-milk-member"]["price_list_rate"] = 2.89
        self.press("MILK-L1")
        self.assertEqual((rings(self.tenant, MEMBER, "MILK-L1"), rings(self.tenant, PL, "MILK-L1")), (2.16, 2.99))

    def test_m6_a_lot_out_of_stock_has_the_markdown_taken_off_every_list(self):
        self.press("MILK-L1")
        self.tenant.lots["MILK-L1"]["batch_qty"] = 0
        code, out = self.press("MILK-L1")
        self.assertEqual((self.tenant.lot_rows("MILK-L1"), out["message"]["body"]), ([], "Took the markdown off 1 lot."))
        self.assertEqual(rings(self.tenant, MEMBER, "MILK-L1"), 3.49)

    def test_m7_a_lot_price_the_shop_typed_on_the_member_list_is_left_as_it_is(self):
        self.tenant.prices["ip-own-member"] = dict(self.tenant.prices["ip-milk-member"], name="ip-own-member",
                                                   batch_no="MILK-L1", price_list_rate=3.25, note="manager's own")
        self.press("MILK-L1")
        self.assertEqual({k: v for k, v in self.lists_of("MILK-L1").items() if k[0] in (PL, MEMBER)},
                         {(PL, "Nos"): 2.99, (PL, "Crate"): 33.75, (MEMBER, "Nos"): 3.25})
        self.assertNotIn("ip-own-member", [w[1] for w in self.tenant.writes])

    def test_m8_a_press_writes_only_the_lots_item_price_rows(self):
        """A return pays back the price its sale booked (the shop's return copies the sale's own line), so a markdown
        taken off after the sale changes nothing about it: the press writes the lot's Item Price rows and nothing else."""
        self.press("MILK-L1")
        self.tenant.lots["MILK-L1"]["batch_qty"] = 0
        self.press("MILK-L1")
        self.assertEqual(self.tenant.doctypes, {"Item Price"})
        self.assertTrue(all(w[0] == "delete" or w[2].get("batch_no") in (None, "MILK-L1") for w in self.tenant.writes))

    def test_m9_a_lot_marked_down_before_this_version_gets_the_other_lists_at_the_next_press(self):
        for uom, rate in (("Nos", 2.99), ("Crate", 33.75)):        # the old version wrote the settings' list alone
            self.tenant.prices[f"old-{uom}"] = dict(self.tenant.prices["ip-milk"], name=f"old-{uom}", uom=uom,
                                                    price_list_rate=rate, batch_no="MILK-L1", valid_from=TODAY.isoformat(),
                                                    valid_upto=day(4), note="PP EXM: 25% off until it expires")
        code, out = self.press("MILK-L1")
        self.assertEqual(out["message"]["body"], "Marked down 1 lot.")
        self.assertEqual({(w[0], w[2]["price_list"]) for w in self.tenant.writes},
                         {("create", MEMBER), ("create", STAFF), ("create", AUSTIN)})
        self.assertEqual(rings(self.tenant, MEMBER, "MILK-L1"), 2.61)


class OverHttp(unittest.TestCase):
    """The same service behind its own web server: the press, the health check, and no test route without the token."""

    def setUp(self):
        self.tenant = FakeTenant()
        self.svc = app.Service({"PP_POINT_SECRET": SECRET}, self.tenant, now=NOW)
        self.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.svc, log=open(os.devnull, "w")))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_press_over_http(self):
        raw = body()
        req = urllib.request.Request(self.base + "/press/markdown", data=raw, headers=signed(raw), method="POST")
        with urllib.request.urlopen(req) as r:
            self.assertEqual(json.loads(r.read())["message"]["title"], "Mark down")
        with urllib.request.urlopen(self.base + "/health") as r:
            self.assertEqual(json.loads(r.read()), {"ok": 1})


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service({"PP_POINT_SECRET": SECRET}, object())
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {"/press/markdown": (app.SUB, SECRET)}

    def call(self, path, raw, secret, test=True):
        import base64, hashlib, hmac, time
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        return self.svc.handle("POST", path, h, raw)

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and refused
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
