"""S1's webhook answers the site's Test connection: a call marked ``X-iVendNext-Test: 1`` is checked as a real call, then answered
``{"test": "ok"}`` with no work done. A call that is not signed gets the real refusal. The signature travels in our own
header, and is checked over the bytes received however the sender laid the JSON out.

    python3 -m unittest discover -s samples/s1_warranty/tests -p 'test_test_marker.py' -v
"""
import base64
import hashlib
import hmac
import http.server
import json
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "service"))
import app  # noqa: E402
import receiver  # noqa: E402

SECRET = "the-webhook-secret"


class NoWork:
    env = {"PP_WEBHOOK_SECRET": SECRET}

    def __init__(self):
        self.store = self

    def event(self, *a):
        pass

    def process(self, *a):
        raise AssertionError("a test call does no work")


class Marker(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(NoWork()))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, signature, header=app.HEADER):
        body = json.dumps({"test": 1}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}/webhook", data=body, method="POST",
                                     headers={"X-iVendNext-Test": "1", "Content-Type": "application/json", header: signature})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_a_signed_test_call_is_answered_with_no_work_done(self):
        body = json.dumps({"test": 1}).encode()
        sig = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
        self.assertEqual(self.post(sig), (200, {"test": "ok", "point": "webhook"}))

    def test_a_test_call_with_a_bad_signature_gets_the_real_refusal(self):
        self.assertEqual(self.post("bad")[0], 401)

    def test_the_signature_travels_in_our_own_header_and_no_other(self):
        sig = receiver._sign(SECRET, json.dumps({"test": 1}).encode()).decode()
        self.assertEqual(self.post(sig, "X-iVendNext-Webhook-Signature")[0], 200)
        self.assertEqual(self.post(sig, "X-Another-Webhook-Signature")[0], 401)


class Layout(unittest.TestCase):
    def test_a_body_laid_out_either_way_verifies_over_the_bytes_received(self):
        data = {"name": "S-1", "doctype": "POS Invoice", "event": "on_submit", "modified": "2026-11-12 10:00:00"}
        compact, indented = json.dumps(data).encode(), json.dumps(data, indent=1, sort_keys=True).encode()
        for body in (compact, indented):
            self.assertEqual(receiver.verify(body, receiver._sign(SECRET, body).decode(), SECRET), (data, "raw-body"))
        self.assertNotEqual(compact, indented)
        rebuilt = json.dumps(json.loads(indented), separators=(",", ":")).encode()     # a receiver's own layout
        self.assertIsNone(receiver.verify(rebuilt, receiver._sign(SECRET, indented).decode(), SECRET)[0])


if __name__ == "__main__":
    unittest.main()
