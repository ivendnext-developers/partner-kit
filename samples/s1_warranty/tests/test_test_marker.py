"""S1's webhook answers the site's Test connection: a call marked ``X-iVendNext-Test: 1`` is checked as a real call, then answered
``{"test": "ok"}`` with no work done. A call that is not signed gets the real refusal.

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

SECRET = "the-webhook-secret"


class NoWork:
    env = {"PP_WEBHOOK_SECRET": SECRET, "PP_ADMIN_TOKEN": "admin"}

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

    def post(self, signature):
        body = json.dumps({"test": 1}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}/webhook", data=body, method="POST",
                                     headers={"X-iVendNext-Test": "1", "Content-Type": "application/json", app.HEADER: signature})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_a_signed_test_call_is_answered_with_no_work_done(self):
        body = json.dumps({"test": 1}).encode()
        sig = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
        self.assertEqual(self.post(sig), (200, {"test": "ok"}))

    def test_a_test_call_with_a_bad_signature_gets_the_real_refusal(self):
        self.assertEqual(self.post("bad")[0], 401)


if __name__ == "__main__":
    unittest.main()
