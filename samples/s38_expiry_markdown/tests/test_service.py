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
            {"name": "ip-milk-later", "item_code": "MILK", "uom": "Nos", "price_list": PL, "price_list_rate": 9.0,
             "valid_from": day(3)},                                                    # not valid today: not the base
            {"name": "ip-bread", "item_code": "BREAD", "uom": "Nos", "price_list": PL, "price_list_rate": 2.5},
            {"name": "ip-nail", "item_code": "NAIL", "uom": "Nos", "price_list": PL, "price_list_rate": 0.1},
            {"name": "ip-milk-other-list", "item_code": "MILK", "uom": "Nos", "price_list": "Wholesale", "price_list_rate": 3.0}]


class FakeTenant:
    """The shop's record API: settings, lots, items, the group tree, price lists and Item Price rows (created, updated
    with the shop's ``modified`` check, deleted)."""

    def __init__(self, settings=None, refuse=None, edit_before_update=0, duplicate_on_create=0, fraction=100,
                 price_list=None, clock=None):
        # None: the shop's usual settings; False: no record Default at all
        self.settings = {"price_list": PL, "hours_from_utc": 3} if settings is None else None if settings is False else settings
        self.lots, self.items, self.groups = lots(), copy.deepcopy(ITEMS), groups()
        self.prices = {p["name"]: dict({"modified": "2026-10-20 10:00:00.000001", "batch_no": None, "customer": None,
                                        "supplier": None, "valid_from": None, "valid_upto": None, "note": None,
                                        "packing_unit": 0}, **p) for p in prices()}
        self.price_list = price_list if price_list is not None else {"selling": 1, "enabled": 1, "currency": "AED"}
        self.fraction, self.refuse, self.clock = fraction, refuse, clock
        self.edit_before_update, self.duplicate_on_create = edit_before_update, duplicate_on_create
        self.writes, self.n = [], 0

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
            return {"name": name, "fraction_units": self.fraction}
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
        return copy.deepcopy(self.prices[name])

    def delete(self, doctype, name):
        self._refused()
        if name not in self.prices:
            raise app.TenantError("DELETE -> HTTP 404", 404)
        del self.prices[name]
        self.writes.append(("delete", name, None))

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
        for i in range(25):
            self.tenant.prices[f"old-{i}"] = {"name": f"old-{i}", "item_code": "MILK", "uom": "Nos", "price_list": PL,
                                              "batch_no": f"OLD-{i}", "valid_upto": day(-3), "price_list_rate": 1.0,
                                              "note": "PP EXM: 25% off until it expires", "modified": "x"}
        code, out = self.press("MILK-L3")
        self.assertEqual(len([w for w in self.tenant.writes if w[0] == "delete"]), app.SWEEP)
        self.assertNotIn("shop-old", [w[1] for w in self.tenant.writes])
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
        self.use(FakeTenant(fraction=1000))     # KWD: three digits
        self.press("MILK-L1")
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("MILK-L1")], [33.75, 2.992])
        self.use(FakeTenant(fraction=1))        # JPY: none
        self.press("MILK-L1")
        self.assertEqual([r["price_list_rate"] for r in self.tenant.lot_rows("MILK-L1")], [33.0, 2.0])

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
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/test/received")


if __name__ == "__main__":
    unittest.main()
