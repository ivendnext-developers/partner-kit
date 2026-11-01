"""S16's laptop tests: the real service on a local port, a stand-in for the shop's record API, presses signed exactly
as the shop signs them (``outbound.sign``: base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s16_pick_route/tests -p 'test_*.py'

On our test bench the real Desk button was pressed; these prove the service's
own duties fast, and are what the mutation canary turns RED."""

import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import route  # noqa: E402

SECRET = "s16-test-secret"


class FakeTenant:
    def __init__(self):
        self.tasks = {}

    def find_tasks(self, sos, key):
        return {t["sales_order"]: {"name": n, "sales_order": t["sales_order"], "picker": t["picker"], "priority": t["priority"]}
                for n, t in self.tasks.items() if t["sales_order"] in sos and t["press_key"] == key}

    def create_task(self, doc):
        name = f"PCK-{len(self.tasks) + 1:05d}"
        self.tasks[name] = doc
        return name


def body(names=("SO-0001",), key="key-0001-abcdef", picker="pick@shop.example", **extra):
    recs = [{"doctype": "Sales Order", "name": n, "fields": {
        "name": n, "customer": "C1", "set_warehouse": "Main - S", "delivery_date": "2026-10-09",
        "items": [{"item_code": "B", "qty": 2000, "warehouse": "Back - S"}, {"item_code": "A", "qty": 2500, "warehouse": "Main - S"}]}}
        for n in names]
    ctx = {"v": 1, "action": "x", "label": "Assign pick route", "user": "u@shop.example", "lang": "en", "records": recs,
           "inputs": {"picker": picker, "priority": "Urgent"}, "idempotency_key": key, **extra}
    return json.dumps({"point": "desk_action/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=SECRET, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tenant = FakeTenant()
        self.svc = app.Service({"PP_POINT_SECRET": SECRET}, self.tenant)
        self.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.svc))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/press/route"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, raw, headers):
        req = urllib.request.Request(self.url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_s1_one_order_makes_one_task_and_opens_it(self):
        raw = body()
        code, out = self.post(raw, signed(raw))
        self.assertEqual(code, 200)
        self.assertEqual(out["open_record"], {"doctype": route.TASK, "name": "PCK-00001"})
        self.assertEqual(out["message"]["title"], "Route assigned")
        self.assertEqual(out["message"]["body"], "2 lines across 2 warehouses for pick@shop.example.")
        task = self.tenant.tasks["PCK-00001"]
        self.assertEqual([(ln["item_code"], ln["qty"], ln["stop"]) for ln in task["lines"]], [("B", 2.0, 1), ("A", 2.5, 2)])
        self.assertEqual((task["picker"], task["priority"], task["press_key"]), ("pick@shop.example", "Urgent", "key-0001-abcdef"))

    def test_s4_three_orders_one_message(self):
        raw = body(names=("SO-1", "SO-2", "SO-3"))
        code, out = self.post(raw, signed(raw))
        self.assertEqual((code, out["message"]["title"], len(self.tenant.tasks)), (200, "3 routes assigned", 3))
        self.assertNotIn("open_record", out)

    def test_retry_with_the_same_key_makes_no_second_task(self):
        raw = body()
        first = self.post(raw, signed(raw))
        again = self.post(raw, signed(raw))
        self.assertEqual(first, again)
        self.assertEqual(len(self.tenant.tasks), 1)

    def test_a_retry_with_changed_inputs_answers_about_the_task_that_exists(self):
        raw = body()
        self.post(raw, signed(raw))
        raw = body(picker="someone@else.example")      # the same key: the dialog kept it, the user changed the picker
        code, out = self.post(raw, signed(raw))
        self.assertEqual((code, len(self.tenant.tasks)), (200, 1))
        self.assertIn("for pick@shop.example.", out["message"]["body"])

    def test_the_test_routes_need_the_environment_and_the_token(self):
        os.environ["PP_TEST_MODES"] = "1"
        try:
            svc = app.Service({"PP_POINT_SECRET": SECRET, "PP_ADMIN_TOKEN": "t0ken"}, FakeTenant())
        finally:
            del os.environ["PP_TEST_MODES"]
        srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(svc))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/test/received"
            for token, want in (("wrong", 404), ("", 404), ("t0ken", 200)):
                try:
                    code = urllib.request.urlopen(urllib.request.Request(url, headers={"X-PP-Admin": token}), timeout=5).status
                except urllib.error.HTTPError as e:
                    code = e.code
                self.assertEqual(code, want, token)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_a_forged_press_is_refused_and_writes_nothing(self):
        raw = body()
        code, out = self.post(raw, signed(raw, secret="not-the-shops-secret"))
        self.assertEqual((code, out["error"]), (401, "the signature does not match"))
        self.assertEqual(self.tenant.tasks, {})

    def test_a_body_changed_after_signing_is_refused(self):
        raw = body()
        code, _ = self.post(body(picker="someone@else.example"), signed(raw))
        self.assertEqual((code, self.tenant.tasks), (401, {}))

    def test_an_old_press_is_refused(self):
        raw = body()
        code, out = self.post(raw, signed(raw, ts=time.time() - 3600))
        self.assertEqual((code, self.tenant.tasks), (401, {}))
        self.assertEqual(out["error"], "the signature does not match")    # one sentence for every refusal

    def test_s2_refresh_and_s3_missing_answers(self):
        self.svc.mode = "refresh"
        raw = body(key="key-refresh-01")
        code, out = self.post(raw, signed(raw))
        self.assertEqual((code, out["refresh"], "open_record" in out), (200, True, False))
        self.svc.mode = "missing"
        raw = body(key="key-missing-01")
        code, out = self.post(raw, signed(raw))
        self.assertEqual(out, {"open_record": {"doctype": route.TASK, "name": "PT-404"}})
        self.assertEqual(len(self.tenant.tasks), 1)   # the missing answer wrote nothing

    def test_test_routes_are_off_without_the_environment(self):
        req = urllib.request.Request(self.url.replace("/press/route", "/test/received"), headers={"X-PP-Admin": ""})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 404)


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service({"PP_POINT_SECRET": SECRET}, object())
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {"/press/route": (app.SUB, SECRET)}

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
