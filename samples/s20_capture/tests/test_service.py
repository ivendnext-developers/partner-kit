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

SCAN_SECRET, CUSTOMER_SECRET = "s20-scan-secret", "s20-customer-secret"
CONF = {"PP_POINT_SECRET_SCAN": SCAN_SECRET, "PP_POINT_SECRET_CUSTOMER": CUSTOMER_SECRET,
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
        path = path or ("/cap/scan" if secret == SCAN_SECRET else "/cap/customer")
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


if __name__ == "__main__":
    unittest.main()
