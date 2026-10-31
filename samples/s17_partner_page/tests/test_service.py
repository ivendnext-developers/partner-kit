"""S17's laptop tests: the real service on a local port and a stand-in for the shop's ``api/page.submit`` that checks
the signature and takes one answer per nonce, as the shop does. Contexts are minted exactly as the shop mints them
(``partner_page.sign_context``).

    python3 -m unittest discover -s samples/s17_partner_page/tests -p 'test_*.py'

On our test bench the page was opened through the shop's own calls; these prove
the service's own duties fast, and are what the mutation canary turns RED."""

import http.client
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import page  # noqa: E402

SECRET = "s17-test-secret"


def ctx(nonce="a" * 32, secret=SECRET, ttl=300, **where):
    now = int(time.time())
    payload = {"v": 1, "page": "board-1", "nonce": nonce, "iat": now, "exp": now + ttl, "lang": "en",
               "theme": {"mode": "light", "vars": {"--ivn-accent": "#2e75b6"}}, "user": "cashier@shop.example",
               **(where or {"store": "Main - S", "pos_profile": "Till 1",
                            "sale": {"sale_ref": "s-1", "lines": [{"item_code": "A", "qty": 1, "uom": "Nos"}]}})}
    return page.sign_context(secret, payload)


class FakeShop:
    """The shop's submit: the signature over <timestamp>.<body> with the page's secret, one answer per nonce."""

    def __init__(self):
        self.got, self.answered = [], set()

    def post(self, url, body, headers):
        want = page.sign(SECRET, headers["X-iVendNext-Timestamp"], body)
        if headers["X-iVendNext-Signature"] != want:
            return 401, json.dumps({"exception": "AuthenticationError: The answer's signature does not match."}).encode()
        nonce = json.loads(body)["ctx_nonce"]
        if nonce in self.answered:
            msg = json.dumps({"message": "This page has already answered."})
            return 409, json.dumps({"_server_messages": json.dumps([msg])}).encode()
        self.answered.add(nonce)
        self.got.append(json.loads(body))
        return 200, b'{"message": {"ok": 1}}'


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.shop = FakeShop()
        self.board = app.Board({"PP_BASE": "http://shop.invalid", "PP_PAGE_SECRET": SECRET}, post=self.shop.post)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.board))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_the_page_is_served(self):
        code, html = self.call("/board/")
        self.assertEqual(code, 200)
        self.assertIn(b'history.replaceState(null, "", location.pathname)', html)   # the context leaves the address

    def test_open_on_the_till_shows_where_and_offers_an_order(self):
        c = ctx()
        code, out = self.call("/board/api/open", {"ctx": c})
        self.assertEqual(code, 200)
        self.assertEqual(out["where"], {"on": "till", "store": "Main - S", "pos_profile": "Till 1", "sale_ref": "s-1", "lines": 1})
        self.assertEqual(out["delivery_order"], page.delivery_order("a" * 32))

    def test_open_in_desk_carries_the_record(self):
        code, out = self.call("/board/api/open", {"ctx": ctx(doctype="Sales Order", name="SO-0042")})
        self.assertEqual((code, out["where"]), (200, {"on": "desk", "doctype": "Sales Order", "name": "SO-0042"}))

    def test_a_forged_context_is_refused(self):
        code, out = self.call("/board/api/open", {"ctx": ctx(secret="not-the-shops-secret")})
        self.assertEqual((code, out["error"]), (403, "the context's signature does not match"))
        code, _ = self.call("/board/api/answer", {"ctx": ctx(nonce="b" * 32, secret="not-the-shops-secret")})
        self.assertEqual((code, self.shop.got), (403, []))

    def test_a_context_changed_after_signing_is_refused(self):
        body, sig = ctx().split(".")
        other = page.b64(json.dumps({"v": 1, "nonce": "c" * 32, "exp": int(time.time()) + 300}).encode())
        code, _ = self.call("/board/api/open", {"ctx": other + "." + sig})
        self.assertEqual(code, 403)

    def test_an_expired_context_is_refused(self):
        code, out = self.call("/board/api/open", {"ctx": ctx(ttl=-1)})
        self.assertEqual(code, 403)
        self.assertIn("run out", out["error"])

    def test_a_context_opens_once(self):
        c = ctx()
        self.assertEqual(self.call("/board/api/open", {"ctx": c})[0], 200)
        code, out = self.call("/board/api/open", {"ctx": c})
        self.assertEqual(code, 403)
        self.assertIn("already opened", out["error"])

    def test_s1_the_answer_is_signed_and_sent_once(self):
        c = ctx()
        code, out = self.call("/board/api/answer", {"ctx": c, "note": "Delivery booked."})
        self.assertEqual((code, out["ok"]), (200, 1))
        sent = self.shop.got[0]
        self.assertEqual(sent["ctx_nonce"], "a" * 32)
        self.assertEqual(sent["result"]["sale_attributes"],
                         [{"sale_attribute": page.ATTRIBUTE, "attribute_value": out["delivery_order"]}])
        code, out = self.call("/board/api/answer", {"ctx": c})
        self.assertEqual((code, out["refused_by"]), (409, "partner service"))     # S3, refused by the service itself
        self.board.check_once = False
        code, out = self.call("/board/api/answer", {"ctx": c})
        self.assertEqual((code, out["refused_by"], out["error"]), (409, "shop", "This page has already answered."))
        self.assertEqual(len(self.shop.got), 1)

    def test_an_unreachable_shop_releases_the_answer(self):
        self.board._post = lambda url, body, headers: self.board._http_post("http://127.0.0.1:9/x", body, headers)
        c = ctx()
        code, out = self.call("/board/api/answer", {"ctx": c})
        self.assertEqual((code, out["refused_by"]), (502, "network"))
        self.board._post = self.shop.post                   # the shop is back: the same context may answer
        code, out = self.call("/board/api/answer", {"ctx": c, "note": {"not": "text"}})
        self.assertEqual(code, 200)
        self.assertNotIn("message", self.shop.got[0]["result"])   # a note that is not text is dropped, not sent

    def test_the_test_routes_need_the_environment_and_the_token(self):
        os.environ["PP_TEST_MODES"] = "1"
        try:
            board = app.Board({"PP_BASE": "http://shop.invalid", "PP_PAGE_SECRET": SECRET, "PP_ADMIN_TOKEN": "t0ken"})
        finally:
            del os.environ["PP_TEST_MODES"]
        srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(board))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/test/opened"
            for token, want in (("wrong", 404), ("", 404), ("t0ken", 200)):
                try:
                    code = urllib.request.urlopen(urllib.request.Request(url, headers={"X-PP-Admin": token}), timeout=5).status
                except urllib.error.HTTPError as e:
                    code = e.code
                self.assertEqual(code, want, token)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_desk_takes_no_answer(self):
        code, _ = self.call("/board/api/answer", {"ctx": ctx(doctype="Sales Order", name="SO-1")})
        self.assertEqual((code, self.shop.got), (400, []))


def cut_answer(*args, **kwargs):
    """What ``urlopen`` / ``opener.open`` give back when the answer starts and the connection closes before its end: reading it
    raises ``http.client.IncompleteRead``, an ``HTTPException`` that is not an ``OSError``."""
    class Answer:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *n):
            raise http.client.IncompleteRead(b"")
    return Answer()


class AnswerCutShort(unittest.TestCase):
    """An answer cut short (``http.client.IncompleteRead``) is handled on the path a refused connection already takes."""

    def test_a_shop_answer_cut_short_releases_the_answer_like_an_unreachable_shop(self):
        board = app.Board({"PP_BASE": "http://shop.invalid", "PP_PAGE_SECRET": SECRET})
        with mock.patch.object(app.urllib.request, "urlopen", cut_answer):
            self.assertEqual(board._http_post("http://shop.invalid/x", b"{}", {}), (0, b""))


if __name__ == "__main__":
    unittest.main()
