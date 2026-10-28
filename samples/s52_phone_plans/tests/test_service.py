"""S52's laptop tests: the stand-in telecom company runs as a real web server on this machine, and two retailers, each
with its own telecom account, call one service. Every call goes through the service's own entry (``Service.handle``),
signed the way the till signs it, so the signature, the shops store and the telecom calls are all exercised.

    python3 -m unittest discover -s samples/s52_phone_plans/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(SAMPLE, "service"), os.path.join(SAMPLE, "standin")]
import app  # noqa: E402
import ed25519  # noqa: E402  (the template's, through app.py's path)
import worker  # noqa: E402
import telecom  # noqa: E402  (the service's client: service/ is ahead of standin/ on the path)
import feed_client as F  # noqa: E402  (the kit's, through worker.py's path)
import plans  # noqa: E402
import shops  # noqa: E402
import telecom_api as standin  # noqa: E402  (the stand-in telecom company)
from fake_shop import FakeFeed, paid_sale, retailer  # noqa: E402

APP, A, B = "ivendnext_tel", "north-phones.ivendnext.com", "south-phones.ivendnext.com"
PAID = hashlib.sha256(b"s52 test L1").digest()
KEYS = {"L1": (base64.b64encode(ed25519.public_key(PAID)).decode(), frozenset({"paid"}))}
SECRETS = {A: ("plans-secret-north", "check-secret-north"), B: ("plans-secret-south", "check-secret-south")}
ACCOUNTS = standin.load_accounts()


def library_key(host) -> str:
    pb = json.dumps({"typ": "applib-key", "v": 1, "kid": "L1", "id": "K7Q2M9XW4TPA", "app": APP, "host": host,
                     "to": "customer:test", "kind": "paid", "iat": "2026-10-28", "exp": None}).encode()
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")  # noqa: E731
    return f"IVN1-{b(pb)}.{b(ed25519.sign(PAID, pb))}"


def signed(secret: str, body: dict, site: str | None, ts: int | None = None) -> tuple[dict, bytes]:
    raw = json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
    if site:
        h[shops.SITE_HEADER] = site
    return h, raw


def key_press(lines=("PP-TEL-PHONE-X1",), customer="CUST-1") -> dict:
    return {"app": APP, "key": f"{APP}_plans", "context": {"sale_ref": "s1", "currency": "USD", "customer": customer,
            "lines": [{"item_code": c, "qty": 1.0, "uom": "Nos", "luid": f"l{i}"} for i, c in enumerate(lines)]}}


def check_call(plan="PP-TEL-S", rate=2500, customer="CUST-1", phone="PP-TEL-PHONE-X1", stage="sale", qty=1000) -> dict:
    lines = [{"line_no": 1, "item_code": phone, "item_group": "Phones", "qty_milli": 1000, "uom": "Nos",
              "rate_minor": 49900, "amount_minor": 49900, "discount_minor": 0, "line_attributes": []}]
    if plan:
        lines.append({"line_no": 2, "item_code": plan, "item_group": "Mobile Plans", "qty_milli": qty, "uom": "Nos",
                      "rate_minor": rate, "amount_minor": rate * qty // 1000, "discount_minor": 0, "line_attributes": []})
    return {"point": "check/1", "context": {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2,
            "sale_ref": "s1", "currency": "USD", "customer": customer, "lines": lines,
            "totals": {"grand_minor": sum(ln["amount_minor"] for ln in lines)}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tel = standin.Telecom(standin.load_accounts())
        self.tel_srv = standin.make_server(self.tel)
        threading.Thread(target=self.tel_srv.serve_forever, daemon=True).start()
        self.tmp = tempfile.mkdtemp()
        self.shops = {f"https://{A}": retailer(f"https://{A}", "ACC-NORTH", ACCOUNTS["ACC-NORTH"]["key"]),
                      f"https://{B}": retailer(f"https://{B}", "ACC-SOUTH", ACCOUNTS["ACC-SOUTH"]["key"])}
        conf = {"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": os.path.join(self.tmp, "shops.json"), "PP_STATE": self.tmp,
                "TEL_API": f"http://127.0.0.1:{self.tel_srv.server_address[1]}", "TEL_ACTIVATE_TIMEOUT": "0.5"}
        self.svc = app.Service(conf, opener=lambda url, key, secret, timeout: self.shops[url])
        for site in (A, B):
            body = {"key": library_key(site), "site": site, "secrets": {
                f"{APP}:{APP}_plans": SECRETS[site][0], f"{APP}:sub:plans": SECRETS[site][1],
                "user:pp-tel@integration.invalid": f"k-{site}:s-{site}"}}
            code, _ = shops.handle(self.svc.store, APP, shops.CONNECT, {shops.SITE_HEADER: site}, json.dumps(body).encode(), KEYS)
            self.assertEqual(code, 200)

    def tearDown(self):
        self.tel_srv.shutdown()
        self.tel_srv.server_close()

    def shop(self, site):
        return self.shops[f"https://{site}"]

    def press(self, site, body=None, secret=None):
        h, raw = signed(secret or SECRETS.get(site, ("x", "x"))[0], body or key_press(), site)
        return self.svc.handle("POST", app.PLANS, h, raw)

    def check(self, site, body=None, secret=None):
        h, raw = signed(secret or SECRETS.get(site, ("x", "x"))[1], body or check_call(), site)
        return self.svc.handle("POST", app.CHECKS, h, raw)

    def faults(self, **f):
        self.tel.faults.update(f)

    def accounts_called(self):
        return [c["account"] for c in self.tel.calls]


class PlansKey(Base):
    def test_the_key_lists_the_plans_at_this_retailers_own_price(self):
        code, out = self.press(A)
        self.assertEqual(code, 200)
        self.assertIn("S 20 GB USD 25.00", out["message"]["body"])
        code, out = self.press(B)
        self.assertIn("S 25 GB USD 22.00", out["message"]["body"])
        self.assertEqual(self.accounts_called(), ["ACC-NORTH", "ACC-SOUTH"])

    def test_the_key_answers_a_message_only_and_never_money(self):
        _, out = self.press(A)
        self.assertEqual(set(out), {"message"})          # no sale_attributes, no line values, no price on the sale

    def test_no_phone_on_the_sale_says_so(self):
        _, out = self.press(A, key_press(lines=("SOMETHING-ELSE",)))
        self.assertIn("No phone on this sale", out["message"]["body"])

    def test_a_customer_the_telecom_company_refuses_is_told_plainly(self):
        _, out = self.press(A, key_press(customer="PP TEL Refused"))
        self.assertEqual(out["message"]["level"], "warning")
        self.assertIn("cannot take a new plan", out["message"]["body"])

    def test_the_telecom_company_down_is_a_plain_message_and_nothing_is_added(self):
        self.faults(down=True)
        code, out = self.press(A)
        self.assertEqual(code, 200)
        self.assertEqual(set(out), {"message"})
        self.assertEqual(out["message"]["title"], "Telecom company not answering")
        self.assertIn("Nothing was added", out["message"]["body"])


class CheckAtPay(Base):
    def test_a_plan_at_the_telecom_companys_price_for_this_account_is_allowed(self):
        self.assertEqual(self.check(A), (200, {"verdict": "allow"}))
        self.assertEqual(self.check(B, check_call(rate=2200)), (200, {"verdict": "allow"}))

    def test_the_price_comes_from_this_retailers_account_not_another(self):
        code, out = self.check(B, check_call(rate=2500))   # North's price, at South
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("now USD 22.00 with the telecom company, not USD 25.00", out["reason"])
        self.assertEqual(self.accounts_called(), ["ACC-SOUTH"])

    def test_a_plan_needs_the_customer_on_the_sale(self):
        _, out = self.check(A, check_call(customer=None))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("needs the customer", out["reason"])

    def test_the_tills_walk_in_customer_is_no_customer_for_a_plan(self):
        _, out = self.check(A, check_call(customer="Walk-in Customer"))   # what the till sends when the cashier added none
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("needs the customer", out["reason"])

    def test_a_plan_needs_a_phone_it_fits(self):
        _, out = self.check(A, check_call(plan="PP-TEL-L", rate=5000))   # L fits X2 only
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("needs a phone it fits", out["reason"])

    def test_two_plans_for_one_phone_are_refused(self):
        body = check_call()
        body["context"]["lines"].append(dict(body["context"]["lines"][1], line_no=3, item_code="PP-TEL-M", rate_minor=3500))
        _, out = self.check(A, body)
        self.assertEqual(out["verdict"], "refuse")

    def test_a_sale_without_a_plan_never_asks_the_telecom_company(self):
        self.assertEqual(self.check(A, check_call(plan=None)), (200, {"verdict": "allow"}))
        self.assertEqual(self.tel.calls, [])

    def test_the_telecom_company_down_refuses_the_plan_in_plain_words(self):
        self.faults(down=True)
        _, out = self.check(A)
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("not answering", out["reason"])

    def test_the_telecom_company_too_slow_refuses_inside_the_tills_time(self):
        self.faults(slow=2.5)
        t0 = time.monotonic()
        _, out = self.check(A)
        self.assertLess(time.monotonic() - t0, 2.5)        # the till waits 3 seconds: answered before it gives up
        self.assertEqual(out["verdict"], "refuse")

    def test_a_plan_sold_in_an_exchange_is_refused_never_sold_unconfirmed(self):
        body = check_call(stage="return")                      # a return without its sale, selling a phone and a plan
        _, out = self.check(A, body)
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("own sale", out["reason"])
        self.assertEqual(self.tel.calls, [])

    def test_a_return_is_allowed_without_any_read(self):
        reads = self.shop(A).reads
        body = check_call(stage="return")
        for ln in body["context"]["lines"]:
            ln["qty_milli"] = -ln["qty_milli"]                 # the goods coming back
        self.assertEqual(self.check(A, body), (200, {"verdict": "allow"}))
        self.assertEqual(self.shop(A).reads, reads)

    def test_every_answer_is_one_the_till_takes(self):
        for body in (check_call(), check_call(rate=1), check_call(customer=None)):
            _, out = self.check(A, body)
            self.assertIn(out["verdict"], ("allow", "refuse"))
            if out["verdict"] == "refuse":
                self.assertTrue(1 <= len(out["reason"]) <= 140 and "<" not in out["reason"])


class Callers(Base):
    def test_an_unknown_retailer_gets_401(self):
        self.assertEqual(self.press("stranger.ivendnext.com", secret="anything")[0], 401)
        self.assertEqual(self.check("stranger.ivendnext.com", secret="anything")[0], 401)

    def test_another_retailers_secret_gets_401(self):
        self.assertEqual(self.press(A, secret=SECRETS[B][0])[0], 401)

    def test_the_keys_secret_does_not_sign_the_check(self):
        self.assertEqual(self.check(A, secret=SECRETS[A][0])[0], 401)

    def test_an_old_timestamp_gets_401(self):
        h, raw = signed(SECRETS[A][0], key_press(), A, ts=int(time.time()) - 3600)
        self.assertEqual(self.svc.handle("POST", app.PLANS, h, raw)[0], 401)


class TwoRetailersAtOnce(Base):
    def test_two_retailers_at_the_same_moment_each_answered_with_its_own_account_only(self):
        n, go, out = 12, threading.Barrier(24), {A: [], B: []}

        def call(site, kind):
            go.wait()
            rate = 2500 if site == A else 2200
            res = self.press(site) if kind == "press" else self.check(site, check_call(rate=rate))
            out[site].append((kind, res))

        threads = [threading.Thread(target=call, args=(site, kind)) for site in (A, B) for kind in ("press", "check")
                   for _ in range(n // 2)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(20)
        for site, own, other in ((A, "USD 25.00", "USD 22.00"), (B, "USD 22.00", "USD 25.00")):
            self.assertEqual(len(out[site]), n)
            for kind, (code, ans) in out[site]:
                self.assertEqual(code, 200)
                if kind == "press":
                    self.assertIn(own, ans["message"]["body"])
                    self.assertNotIn(other, ans["message"]["body"])
                else:
                    self.assertEqual(ans, {"verdict": "allow"})   # each at its own account's price
        calls = self.accounts_called()
        self.assertEqual(calls.count("ACC-NORTH"), n)
        self.assertEqual(calls.count("ACC-SOUTH"), n)
        self.assertEqual(self.shop(A).reads, n)
        self.assertEqual(self.shop(B).reads, n)

    def test_the_service_holds_no_account_between_calls(self):
        self.press(A)
        self.shop(A).put("PP TEL Settings", "Default", title="Default", telecom_account="ACC-SOUTH",
                         telecom_key=ACCOUNTS["ACC-SOUTH"]["key"], plan_item_group="Mobile Plans", price_list="Standard Selling")
        _, out = self.press(A)                            # the retailer changed its account: the next call uses it
        self.assertIn("USD 22.00", out["message"]["body"])


class AfterPayment(Base):
    def activate(self, site, sale="POS-1"):
        t = self.shop(site)
        return worker.activate_sale(self.svc, t, self.svc.settings(t), sale)

    def row(self, site, key="POS-1:2"):
        return self.shop(site).db.get("PP TEL Activation", {}).get(key)

    def test_activation_after_payment_writes_the_number_back(self):
        paid_sale(self.shop(A), "POS-1")
        self.assertEqual(self.activate(A), [{"key": "POS-1:2", "status": "Activated"}])
        row = self.row(A)
        self.assertEqual((row["status"], row["sale"], row["plan"], row["phone"], row["serial_no"]),
                         ("Activated", "POS-1", "PP-TEL-S", "PP-TEL-PHONE-X1", "IMEI-1"))
        self.assertTrue(row["activation_number"].startswith("ACT-NORTH-"))

    def test_a_second_pass_never_activates_twice(self):
        paid_sale(self.shop(A), "POS-1")
        self.activate(A)
        self.assertEqual(self.activate(A)[0]["again"], True)
        self.assertEqual(len(self.tel.activations), 1)

    def test_the_telecom_company_answers_late_after_the_sale_is_paid(self):
        paid_sale(self.shop(A), "POS-1")
        self.faults(late_activation=1.5)                  # it activates, but its answer comes after our 0.5 s
        with self.assertRaises(telecom.TelecomDown):
            self.activate(A)
        self.assertEqual(self.row(A)["status"], "Pending")
        self.faults(late_activation=0)
        self.activate(A)                                  # the next pass asks again with the same key
        row = self.row(A)
        self.assertEqual(row["status"], "Activated")
        self.assertEqual(len(self.tel.activations), 1)    # one activation at the telecom company, the same number
        self.assertEqual(row["activation_number"], next(iter(self.tel.activations.values()))["activation"])

    def test_a_refused_activation_is_written_as_failed_with_the_reason_and_not_retried(self):
        paid_sale(self.shop(A), "POS-1")
        self.faults(refuse_activation=True)
        self.activate(A)
        row = self.row(A)
        self.assertEqual(row["status"], "Failed")
        self.assertIn("SIM for this phone is not ready", row["message"])
        self.faults(refuse_activation=False)
        self.activate(A)
        self.assertEqual(self.row(A)["status"], "Failed")
        self.assertEqual(self.tel.activations, {})

    def test_two_plans_on_a_line_of_two_phones_each_go_on_its_own_phone(self):
        paid_sale(self.shop(A), "POS-1", serial="IMEI-1\nIMEI-2", phones=2, plans=["PP-TEL-S", "PP-TEL-M"])
        self.activate(A)
        self.assertEqual((self.row(A, "POS-1:2")["serial_no"], self.row(A, "POS-1:3")["serial_no"]), ("IMEI-1", "IMEI-2"))

    def test_the_activation_key_names_the_retailer_so_two_retailers_never_share_one(self):
        paid_sale(self.shop(A), "POS-1")
        worker.activate_sale(self.svc, self.shop(A), self.svc.settings(self.shop(A)), "POS-1", A)
        self.assertEqual([k for _, k in self.tel.activations], [f"{A}/POS-1:2"])

    def test_a_refused_telecom_key_is_retried_not_failed(self):
        paid_sale(self.shop(A), "POS-1")
        self.shop(A).db["PP TEL Settings"]["Default"]["telecom_key"] = "rotated"   # the key the retailer is about to fix
        with self.assertRaises(telecom.TelecomDown):             # the event stays undone: nothing written Failed
            self.activate(A)
        self.assertNotEqual((self.row(A) or {}).get("status"), "Failed")
        self.shop(A).db["PP TEL Settings"]["Default"]["telecom_key"] = ACCOUNTS["ACC-NORTH"]["key"]
        self.activate(A)
        self.assertEqual(self.row(A)["status"], "Activated")

    def test_each_retailer_activates_with_its_own_account(self):
        paid_sale(self.shop(A), "POS-1")
        paid_sale(self.shop(B), "POS-1")                 # the same sale name at both: their own rows, their own accounts
        self.activate(A)
        self.activate(B)
        self.assertTrue(self.row(A)["activation_number"].startswith("ACT-NORTH-"))
        self.assertTrue(self.row(B)["activation_number"].startswith("ACT-SOUTH-"))

    def test_the_feed_leaves_the_event_undone_while_the_telecom_company_is_down(self):
        paid_sale(self.shop(A), "POS-1")
        feed = FakeFeed([{"id": "e1", "doc_type": "POS Invoice", "doc_name": "POS-1", "event": "sale.booked"}])
        seen = F.Store(os.path.join(self.tmp, "feed.sqlite"))
        t = self.shop(A)
        self.faults(down=True)
        self.assertEqual(F.poll(feed, seen, worker.handler(self.svc, t))["failed"], 1)
        self.assertEqual(feed.backlog(), 1)
        self.faults(down=False)
        self.assertEqual(F.poll(feed, seen, worker.handler(self.svc, t))["handled"], 1)
        self.assertEqual(self.row(A)["status"], "Activated")

    def test_the_plans_prices_follow_this_retailers_account(self):
        self.assertEqual(worker.sync_prices(self.svc, self.shop(A), self.svc.settings(self.shop(A)))["prices_written"], 3)
        self.assertEqual(worker.sync_prices(self.svc, self.shop(B), self.svc.settings(self.shop(B)))["prices_written"], 2)
        rate = lambda site, code: next(r["price_list_rate"] for r in self.shop(site).db["Item Price"].values()  # noqa: E731
                                       if r["item_code"] == code)
        self.assertEqual((rate(A, "PP-TEL-S"), rate(B, "PP-TEL-S")), (25.0, 22.0))
        self.assertEqual(worker.sync_prices(self.svc, self.shop(A), self.svc.settings(self.shop(A)))["prices_written"], 0)

    def test_a_price_the_telecom_company_moves_moves_the_existing_row(self):
        worker.sync_prices(self.svc, self.shop(A), self.svc.settings(self.shop(A)))
        self.faults(price_change=50)                               # the telecom company raises every price by 0.50
        self.assertEqual(worker.sync_prices(self.svc, self.shop(A), self.svc.settings(self.shop(A)))["prices_written"], 3)
        rows = {r["item_code"]: r["price_list_rate"] for r in self.shop(A).db["Item Price"].values()}
        self.assertEqual((len(self.shop(A).db["Item Price"]), rows["PP-TEL-S"]), (3, 25.5))   # the same rows, moved

    def test_a_catalogue_code_outside_the_plans_group_never_gets_a_price(self):
        self.shop(A).db["Item"]["PP-TEL-L"]["item_group"] = "Phones"          # one of the retailer's own goods, say
        worker.sync_prices(self.svc, self.shop(A), self.svc.settings(self.shop(A)))
        self.assertNotIn("PP-TEL-L", {r["item_code"] for r in self.shop(A).db["Item Price"].values()})


class OneRetailer(unittest.TestCase):
    def test_one_retailer_from_its_settings_and_the_web_server(self):
        tel = standin.make_server(standin.Telecom(standin.load_accounts()))
        threading.Thread(target=tel.serve_forever, daemon=True).start()
        shop = retailer("https://one.example", "ACC-NORTH", ACCOUNTS["ACC-NORTH"]["key"])
        svc = app.Service({"IVN_POINT_SECRET": "p", "IVN_CHECK_SECRET": "c", "IVN_SHOP_URL": "https://one.example",
                           "IVN_SHOP_KEY": "k:s", "TEL_API": f"http://127.0.0.1:{tel.server_address[1]}"},
                          opener=lambda *a: shop)
        srv = app.make_server(svc, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            h, raw = signed("c", check_call(), None)
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}{app.CHECKS}", data=raw, headers=h)
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"verdict": "allow"})
        finally:
            srv.shutdown()
            srv.server_close()
            tel.shutdown()
            tel.server_close()


class Rules(unittest.TestCase):
    def test_price_changes_writes_only_what_differs(self):
        cat = [{"code": "P", "price_minor": 2500, "exponent": 2}]
        self.assertEqual(plans.price_changes(cat, {"P": {"name": "x", "price_list_rate": 25}}), [])
        self.assertEqual(plans.price_changes(cat, {})[0]["name"], None)

    def test_words_are_plain_and_capped(self):
        self.assertEqual(plans.plain("a <b> " + "x" * 200)[:4], "a b ")
        self.assertLessEqual(len(plans.plain("x" * 300)), 140)


if __name__ == "__main__":
    unittest.main()
