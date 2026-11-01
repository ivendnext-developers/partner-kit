"""S20's laptop tests: the core (``capture.py``) and the real service on a local port, called exactly as the shop calls it.

    python3 -m unittest discover -s samples/s20_capture/tests -p 'test_*.py'

On our test bench the till's own scan and new-customer calls reached this service; these prove its own duties fast,
and are what the mutation canary turns RED."""

import base64
import hashlib
import hmac
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service")]
import app  # noqa: E402
import capture  # noqa: E402

SCAN_SECRET, CUSTOMER_SECRET, QTY_SECRET = "s20-scan-secret", "s20-customer-secret", "s20-qty-secret"
CONF = {"PP_POINT_SECRET_SCAN": SCAN_SECRET, "PP_POINT_SECRET_CUSTOMER": CUSTOMER_SECRET, "PP_POINT_SECRET_QTY": QTY_SECRET,
        "PP_LINE_ATTRIBUTE": "Warranty ref", "PP_BARRED_PHONES": "+971 50 000 0000"}
CID = "9f2c" * 8


def scan_ctx(**line):
    return {"v": 1, "point": "capture", "event": "scan", "sale_ref": "", "store": "Main - S", "pos_profile": "Mall",
            "operator": "c@shop.example", "customer": None, "lang": "en",
            "line": {"item_code": "PHONE-X", "item_group": "Handsets", "qty_milli": 1000, "uom": "Nos", "batch_no": "",
                     "serial_no": "", "scanned_code": "5901234123457", **line}}


def customer_ctx(phone="+971501234567", cid=CID, name="Ana Diaz"):
    return {"v": 1, "point": "capture", "event": "customer_add", "challenge_id": cid, "store": "Main - S",
            "pos_profile": "Mall", "operator": "c@shop.example", "lang": "en",
            "customer": {"customer_name": name, "phone": phone, "email": "", "customer_group": ""}}


def qty_ctx(qty, answered=1, seq=1):
    return {"v": 1, "point": "capture", "event": "qty_change", "seq": seq, "sale_ref": "sale-3f9c", "store": "Main - S",
            "pos_profile": "Mall", "operator": "c@shop.example", "customer": None, "lang": "en",
            "line": {"line_ref": "q8k2v0d1mz", "item_code": "PHONE-X", "item_group": "Handsets", "uom": "Nos",
                     "qty_milli_answered": answered * 1000, "qty_milli": round(qty * 1000)}}


def verify_ctx(code, cid=CID):
    return {"v": 1, "point": "capture", "event": "verify", "challenge_id": cid, "code": code}


def body(ctx):
    return json.dumps({"point": "capture/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}


class CoreTest(unittest.TestCase):
    conf = capture.settings_from(CONF)

    def setUp(self):
        self.now = [1000.0]
        self.codes = capture.Codes(clock=lambda: self.now[0])
        self.sent = []

    def add(self, **kw):
        return capture.on_customer(customer_ctx(**kw), self.conf, self.codes, lambda p, c: self.sent.append((p, c)))

    def test_a_scan_puts_one_reference_on_the_line(self):
        out = capture.on_scan(scan_ctx(), self.conf)
        self.assertEqual(out["verdict"], "allow")
        self.assertEqual(len(out["line_attributes"]), 1)
        row = out["line_attributes"][0]
        self.assertEqual(row["name"], "Warranty ref")
        self.assertRegex(row["value"], r"^WR-[0-9A-F]{10}$")

    def test_each_scan_gets_its_own_reference(self):
        """Two units of one model scanned by their item barcode look the same, and no line id is sent: never one ref."""
        refs = {capture.on_scan(scan_ctx(), self.conf)["line_attributes"][0]["value"] for _ in range(20)}
        self.assertEqual(len(refs), 20)

    def test_no_attribute_set_means_nothing_recorded(self):
        conf = capture.settings_from({**CONF, "PP_LINE_ATTRIBUTE": ""})
        self.assertEqual(capture.on_scan(scan_ctx(), conf), {"verdict": "allow"})

    def test_no_phone_is_refused_and_nothing_is_sent(self):
        out = self.add(phone="")
        self.assertEqual(out["verdict"], "refuse")
        self.assertEqual(self.sent, [])

    def test_a_barred_phone_is_refused_however_it_is_written(self):
        self.assertEqual(self.add(phone="+97150-000-0000")["verdict"], "refuse")
        self.assertEqual(self.sent, [])

    def test_a_new_phone_is_challenged_and_the_code_is_sent_to_it(self):
        out = self.add()
        self.assertEqual(out, {"verdict": "challenge", "prompt": "Ask the customer for the 6-digit code we just sent.",
                               "length": 6})
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], "+971501234567")
        self.assertRegex(self.sent[0][1], r"^[0-9]{6}$")

    def test_the_right_code_is_ok_once(self):
        self.add()
        code = self.sent[0][1]
        self.assertEqual(capture.on_verify(verify_ctx(code), self.codes), {"verdict": "ok"})
        self.assertEqual(capture.on_verify(verify_ctx(code), self.codes)["verdict"], "refuse")   # spent

    def test_a_wrong_code_is_refused_and_the_right_one_still_works(self):
        self.add()
        code = self.sent[0][1]
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(capture.on_verify(verify_ctx(wrong), self.codes),
                         {"verdict": "refuse", "reason": "That code is not right."})
        self.assertEqual(capture.on_verify(verify_ctx(code), self.codes), {"verdict": "ok"})

    def test_a_code_for_another_challenge_is_refused(self):
        self.add()
        out = capture.on_verify(verify_ctx(self.sent[0][1], cid="a" * 32), self.codes)
        self.assertEqual(out["reason"], "This code has expired. Add the customer again.")

    def test_a_code_older_than_ten_minutes_is_refused(self):
        self.add()
        self.now[0] += capture.CODE_TTL_S
        self.assertEqual(capture.on_verify(verify_ctx(self.sent[0][1]), self.codes)["verdict"], "refuse")

    def test_the_same_phone_again_is_challenged_again(self):
        """No phone skips the code: a second add sends a second code (the product's token is spent by the create)."""
        self.add()
        capture.on_verify(verify_ctx(self.sent[0][1]), self.codes)
        self.assertEqual(self.add(cid="b" * 32)["verdict"], "challenge")
        self.assertEqual(len(self.sent), 2)

    def test_a_quantity_up_to_three_is_allowed_four_or_five_asked_more_refused(self):
        conf = capture.settings_from(CONF)
        self.assertEqual([capture.on_qty(qty_ctx(q), conf)["verdict"] for q in (2, 3, 4, 5, 6, 12)],
                         ["allow", "allow", "confirm", "confirm", "refuse", "refuse"])
        self.assertEqual(capture.on_qty(qty_ctx(6), conf)["reason"], "At most 5 of PHONE-X on one line.")

    def test_the_new_quantity_is_judged_never_the_last_allowed_one(self):
        conf = capture.settings_from(CONF)
        self.assertEqual(capture.on_qty(qty_ctx(2, answered=9), conf), {"verdict": "allow"})    # a cut back is allowed
        self.assertEqual(capture.on_qty(qty_ctx(9, answered=2), conf)["verdict"], "refuse")

    def test_the_shop_sets_its_own_limits(self):
        conf = capture.settings_from(dict(CONF, PP_QTY_ASK_ABOVE="1", PP_QTY_MOST="2"))
        self.assertEqual([capture.on_qty(qty_ctx(q), conf)["verdict"] for q in (1, 2, 3)], ["allow", "confirm", "refuse"])
        self.assertEqual(capture.settings_from(dict(CONF, PP_QTY_MOST="x"))["most"], 5)

    def test_every_answer_is_plain_and_fits(self):
        for out in (self.add(phone=""), self.add(phone="+971500000000"), self.add(),
                    capture.on_verify(verify_ctx("999999", cid="d" * 32), self.codes)):
            for key in ("reason", "prompt"):
                if key in out:
                    self.assertTrue(1 <= len(out[key]) <= 140 and not {"<", ">"} & set(out[key]), out)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.svc = app.Service(CONF, lambda p, c: self.sent.append((p, c)))
        self.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.svc))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, ctx, secret, raw=None, ts=None, path=None):
        raw = raw if raw is not None else body(ctx)
        path = path or {SCAN_SECRET: "/cap/scan", QTY_SECRET: "/cap/qty"}.get(secret, "/cap/customer")
        req = urllib.request.Request(self.base + path, data=raw, headers=signed(raw, secret, ts), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_scan_then_customer_then_verify_over_the_wire(self):
        code, out = self.post(scan_ctx(), SCAN_SECRET)
        self.assertEqual((code, out["line_attributes"][0]["name"]), (200, "Warranty ref"))
        code, out = self.post(customer_ctx(), CUSTOMER_SECRET)
        self.assertEqual((code, out["verdict"]), (200, "challenge"))
        code, out = self.post(verify_ctx(self.sent[0][1]), CUSTOMER_SECRET)
        self.assertEqual((code, out), (200, {"verdict": "ok"}))

    def test_a_quantity_change_over_the_wire(self):
        self.assertEqual(self.post(qty_ctx(6), QTY_SECRET), (200, {"verdict": "refuse",
                                                                  "reason": "At most 5 of PHONE-X on one line."}))
        self.assertEqual(self.post(qty_ctx(6), SCAN_SECRET, path="/cap/qty")[0], 401)
        self.assertEqual(self.post(qty_ctx(6), QTY_SECRET, path="/cap/scan")[0], 401)
        self.assertEqual(self.post(scan_ctx(), QTY_SECRET, path="/cap/qty")[0], 400)   # signed, but not this address's event

    def test_a_shop_without_the_quantity_secret_still_runs_the_other_two(self):
        svc = app.Service({k: v for k, v in CONF.items() if k != "PP_POINT_SECRET_QTY"}, lambda p, c: None)
        raw = body(qty_ctx(6))
        self.assertEqual(svc.call("/cap/qty", signed(raw, QTY_SECRET), raw)[0], 401)
        raw = body(scan_ctx())
        self.assertEqual(svc.call("/cap/scan", signed(raw, SCAN_SECRET), raw)[0], 200)
        with self.assertRaises(KeyError):                                  # a scan or customer secret is never optional
            app.Service({k: v for k, v in CONF.items() if k != "PP_POINT_SECRET_SCAN"}, lambda p, c: None)

    def test_each_subscription_signs_with_its_own_secret(self):
        self.assertEqual(self.post(scan_ctx(), CUSTOMER_SECRET, path="/cap/scan")[0], 401)
        self.assertEqual(self.post(customer_ctx(), SCAN_SECRET, path="/cap/customer")[0], 401)
        self.assertEqual(self.sent, [])          # a forged customer call sends no message

    def test_an_address_answers_only_its_own_event(self):
        self.assertEqual(self.post(customer_ctx(), SCAN_SECRET, path="/cap/scan")[0], 400)
        self.assertEqual(self.sent, [])

    def test_an_unsigned_body_is_never_parsed(self):
        deep = b"[" * 100000 + b"]" * 100000      # would raise RecursionError if parsed
        self.assertEqual(self.post(None, SCAN_SECRET, raw=deep, ts=time.time() - 3600)[0], 401)
        self.assertEqual(self.post(None, SCAN_SECRET, raw=deep)[0], 400)    # signed, then read: refused, not a crash

    def test_an_old_call_is_refused(self):
        self.assertEqual(self.post(scan_ctx(), SCAN_SECRET, ts=time.time() - 3600)[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        for raw in (b"not json", body({"v": 1, "event": "something"}), body({**scan_ctx(), "line": {}})):
            self.assertEqual(self.post(None, SCAN_SECRET, raw=raw)[0], 400)

    def test_the_outbox_stand_in_writes_a_private_file(self):
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "outbox.jsonl")
        app.Outbox(path).send("+971501234567", "123456")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        with open(path) as f:
            self.assertEqual(json.loads(f.read())["code"], "123456")


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(app.Service(CONF, lambda p, c: None)))
        import threading
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {p: (app.Service.KEYS[p], CONF[name]) for p, (name, _events) in app.Service.PATHS.items()}
        self.assertEqual(set(self.routes), set(app.Service.PATHS))     # every signed point route of the service

    def call(self, path, raw, secret, test=True):
        import base64, hashlib, hmac, time
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        import json, urllib.error, urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", data=raw, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

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
