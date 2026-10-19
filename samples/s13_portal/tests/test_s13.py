"""Laptop tests of S13's portal (portal.py), no bench: a fake shop answers the few calls the portal makes.

    python3 -m unittest discover -s samples/s13_portal/tests -p 'test_*.py'
"""
import base64
import hashlib
import json
import pathlib
import re
import sys
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import portal as P  # noqa: E402

SHOP = "https://shop.example"
REDIRECT = "https://portal.example/callback"
SECRET = "sec-ZZZZ9999"
CONF = {"PORTAL_SHOP": SHOP, "PORTAL_CLIENT_ID": "client-1", "PORTAL_CLIENT_SECRET": SECRET, "PORTAL_REDIRECT": REDIRECT}
TOKEN = "tok-AAAA1111"
INVOICES = [{"name": "POS-INV-0001", "posting_date": "2026-10-07", "customer": "Walk-in", "grand_total": 120.5, "currency": "ZAR", "pos_profile": "Store A", "status": "Paid"},
            {"name": "POS-INV-0002", "posting_date": "2026-10-08", "customer": "Thabo", "grand_total": 75.0, "currency": "ZAR", "pos_profile": "Store A", "status": "Paid"}]


class FakeShop:
    """Speaks the shop's side: the token exchange, the profile, the record list, the revoke. ``calls`` records every call."""

    def __init__(self):
        self.calls, self.invoices, self.records_status, self.exchange_status = [], list(INVOICES), 200, 200

    def __call__(self, method, path, token=None, form=None):
        self.calls.append((method, path, token, dict(form or {})))
        if path.endswith("oauth2.get_token"):
            return (self.exchange_status, {"access_token": TOKEN, "token_type": "Bearer"} if self.exchange_status == 200 else {"error": "invalid_grant"})
        if path.endswith("oauth2.openid_profile"):
            return (200, {"email": "thabo@x", "name": "Thabo", "roles": ["Retail Cashier"]}) if token == TOKEN else (401, {})
        if path.startswith("/api/resource/POS%20Invoice"):
            if token != TOKEN:
                return 401, {}
            return (200, {"data": self.invoices}) if self.records_status == 200 else (self.records_status, {"exc_type": "PermissionError"})
        if path.endswith("oauth2.revoke_token"):
            return 200, {}
        raise AssertionError((method, path))

    def writes_to_exchange(self):
        return [c for c in self.calls if c[1].endswith("get_token")]


def cookie_of(resp):
    for k, v in resp.headers:
        if k == "Set-Cookie":
            return v.split(";")[0]
    return None


class T(unittest.TestCase):
    def setUp(self):
        self.shop = FakeShop()
        self.p = P.Portal(CONF, http=self.shop)

    def sign_in(self):
        r = self.p.handle("GET", "/login")
        ck = cookie_of(r)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(dict(r.headers)["Location"]).query)
        cb = self.p.handle("GET", "/callback", query={"code": "c1", "state": q["state"][0]}, cookie=ck)
        return cookie_of(cb) or ck, q, cb              # the portal gives a NEW session id at sign-in

    def test_signed_out_shows_the_sign_in_link_and_nothing_of_the_shop(self):
        r = self.p.handle("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn(b'href="/login"', r.body)
        self.assertNotIn(b"POS-INV", r.body)
        self.assertEqual(self.shop.calls, [], "a guest costs the shop nothing")

    def test_login_sends_the_browser_to_the_shop_with_pkce_s256_a_state_and_the_exact_redirect(self):
        r = self.p.handle("GET", "/login")
        self.assertEqual(r.status, 302)
        u = urllib.parse.urlparse(dict(r.headers)["Location"])
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        self.assertEqual(u.netloc, "shop.example")
        self.assertTrue(u.path.endswith("oauth2.authorize"))
        self.assertEqual((q["client_id"], q["redirect_uri"], q["response_type"], q["code_challenge_method"]), ("client-1", REDIRECT, "code", "S256"))
        self.assertGreaterEqual(len(q["state"]), 16)
        self.assertGreaterEqual(len(q["code_challenge"]), 43)
        self.assertNotIn("code_verifier", q)
        cookie = [v for k, v in r.headers if k == "Set-Cookie"][0]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_the_callback_exchanges_the_code_with_the_verifier_that_matches_the_challenge_and_the_client_secret(self):
        ck, q, cb = self.sign_in()
        self.assertEqual(cb.status, 302)
        ex = self.shop.writes_to_exchange()
        self.assertEqual(len(ex), 1)
        form = ex[0][3]
        self.assertEqual(form["code"], "c1")
        self.assertEqual(form["redirect_uri"], REDIRECT)
        digest = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(digest, q["code_challenge"][0])
        self.assertEqual(form["client_secret"], SECRET, "sent today though the shop does not check it: a portal must not depend on that gap")

    def test_after_sign_in_the_page_lists_the_users_records_with_their_token_and_a_desk_deep_link(self):
        ck, _, _ = self.sign_in()
        r = self.p.handle("GET", "/", cookie=ck)
        self.assertEqual(r.status, 200)
        self.assertIn(b"POS-INV-0001", r.body)
        self.assertIn(b'href="https://shop.example/app/pos-invoice/POS-INV-0001"', r.body)
        rec = [c for c in self.shop.calls if c[1].startswith("/api/resource/POS%20Invoice")]
        self.assertTrue(rec and all(c[2] == TOKEN for c in rec), "every record call carries the person's own token")
        self.assertNotIn(TOKEN.encode(), r.body, "the token never reaches the page")

    def test_a_wrong_state_is_refused_and_nothing_is_exchanged(self):
        ck = cookie_of(self.p.handle("GET", "/login"))
        r = self.p.handle("GET", "/callback", query={"code": "c1", "state": "not-the-state"}, cookie=ck)
        self.assertEqual(r.status, 400)
        self.assertEqual(self.shop.writes_to_exchange(), [])

    def test_a_callback_with_no_session_cookie_is_refused_and_nothing_is_exchanged(self):
        r = self.p.handle("GET", "/login")
        state = urllib.parse.parse_qs(urllib.parse.urlparse(dict(r.headers)["Location"]).query)["state"][0]
        r2 = self.p.handle("GET", "/callback", query={"code": "c1", "state": state}, cookie=None)       # another browser
        self.assertEqual(r2.status, 400)
        self.assertEqual(self.shop.writes_to_exchange(), [])

    def test_a_callback_works_once(self):
        ck, q, _ = self.sign_in()
        r = self.p.handle("GET", "/callback", query={"code": "c1", "state": q["state"][0]}, cookie=ck)
        self.assertEqual(r.status, 400)
        self.assertEqual(len(self.shop.writes_to_exchange()), 1)

    def test_a_user_the_shop_refuses_reads_nothing_and_is_told_so_in_words(self):
        ck, _, _ = self.sign_in()
        self.shop.records_status = 403
        r = self.p.handle("GET", "/", cookie=ck)
        self.assertEqual(r.status, 200)
        self.assertIn(b"ivn-error-state", r.body)
        self.assertIn(b"not allowed", r.body)
        self.assertNotIn(b"POS-INV", r.body)
        self.assertNotIn(b"PermissionError", r.body, "the shop's error text is not echoed")

    def test_a_record_name_cannot_inject_markup(self):
        ck, _, _ = self.sign_in()
        self.shop.invoices = [dict(INVOICES[0], name='X"><script>alert(1)</script>', customer="<img src=x onerror=1>")]
        r = self.p.handle("GET", "/", cookie=ck)
        self.assertNotIn(b"<script>", r.body)
        self.assertNotIn(b"<img", r.body)

    def test_sign_out_revokes_at_the_shop_and_forgets_the_session(self):
        ck, _, _ = self.sign_in()
        self.assertEqual(self.p.handle("GET", "/logout", cookie=ck).status, 405, "signing out is a POST")
        r = self.p.handle("POST", "/logout", cookie=ck)
        self.assertEqual(r.status, 302)
        self.assertTrue([c for c in self.shop.calls if c[1].endswith("revoke_token") and c[3].get("token") == TOKEN])
        again = self.p.handle("GET", "/", cookie=ck)
        self.assertIn(b'href="/login"', again.body)
        self.assertNotIn(b"POS-INV", again.body)

    def test_a_token_the_shop_no_longer_accepts_sends_the_person_back_to_sign_in(self):
        ck, _, _ = self.sign_in()
        self.shop.records_status = 401
        r = self.p.handle("GET", "/", cookie=ck)
        self.assertIn(b'href="/login"', r.body)
        self.assertNotIn(b"POS-INV", r.body)
        self.assertIn("Max-Age=0", [v for k, v in r.headers if k == "Set-Cookie"][0])

    def test_the_shop_saying_no_at_sign_in_is_a_clean_page_and_nothing_is_exchanged(self):
        r0 = self.p.handle("GET", "/login")
        state = urllib.parse.parse_qs(urllib.parse.urlparse(dict(r0.headers)["Location"]).query)["state"][0]
        r = self.p.handle("GET", "/callback", query={"error": "access_denied", "state": state}, cookie=cookie_of(r0))
        self.assertEqual(r.status, 403)
        self.assertEqual(self.shop.writes_to_exchange(), [])

    def test_a_refused_exchange_is_a_clean_page_without_a_session(self):
        self.shop.exchange_status = 400
        ck, _, cb = self.sign_in()
        self.assertEqual(cb.status, 502)
        self.assertIn(b'href="/login"', self.p.handle("GET", "/", cookie=ck).body)

    def test_the_shop_unreachable_is_a_clean_page(self):
        ck, _, _ = self.sign_in()
        self.shop.records_status = 0
        r = self.p.handle("GET", "/", cookie=ck)
        self.assertEqual(r.status, 502)
        self.assertIn(b"ivn-error-state", r.body)

    def test_every_response_is_not_cached_and_carries_the_content_policy(self):
        for r in (self.p.handle("GET", "/"), self.p.handle("GET", "/login")):
            h = dict(r.headers)
            self.assertEqual(h["Cache-Control"], "no-store")
            self.assertIn("default-src 'none'", h["Content-Security-Policy"])
            self.assertEqual(h["Referrer-Policy"], "no-referrer")

    def test_the_pending_sign_ins_are_capped(self):
        for _ in range(P.MAX_SESSIONS + 50):
            self.p.handle("GET", "/login")
        self.assertLessEqual(len(self.p.sessions), P.MAX_SESSIONS)

    def test_a_flood_of_logins_cannot_sign_real_users_out(self):
        ck, _, _ = self.sign_in()
        for _ in range(P.MAX_SESSIONS + 50):
            self.p.handle("GET", "/login")
        self.assertIn(b"POS-INV-0001", self.p.handle("GET", "/", cookie=ck).body, "the signed-in session survived the flood")
        self.assertLessEqual(len(self.p.sessions), P.MAX_SESSIONS)

    def test_expired_pending_sign_ins_go_before_anything_else_at_the_cap(self):
        now = [1000.0]
        p = P.Portal(CONF, http=self.shop, clock=lambda: now[0])
        for _ in range(P.MAX_SESSIONS):
            p.handle("GET", "/login")
        now[0] += P.PENDING_SECONDS + 1
        p.handle("GET", "/login")
        self.assertEqual(len(p.sessions), 1, "the expired ones were cleared, not the live one kept out")

    def test_the_session_id_is_new_after_sign_in_and_the_one_before_it_is_worth_nothing(self):
        r = self.p.handle("GET", "/login")
        before = cookie_of(r)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(dict(r.headers)["Location"]).query)
        cb = self.p.handle("GET", "/callback", query={"code": "c1", "state": q["state"][0]}, cookie=before)
        after = cookie_of(cb)
        self.assertTrue(after and after != before)
        self.assertIn(b'href="/login"', self.p.handle("GET", "/", cookie=before).body, "an id planted before sign-in sees nothing")
        self.assertIn(b"POS-INV-0001", self.p.handle("GET", "/", cookie=after).body)

    def test_an_https_portal_marks_its_cookie_secure_and_host_bound_without_being_told(self):
        p = P.Portal(dict(CONF), http=self.shop)                              # the redirect is https
        cookie = [v for k, v in p.handle("GET", "/login").headers if k == "Set-Cookie"][0]
        self.assertTrue(cookie.startswith("__Host-pp_sid=") and "; Secure" in cookie, cookie)
        plain = P.Portal(dict(CONF, PORTAL_REDIRECT="http://127.0.0.1:8141/callback"), http=self.shop)
        self.assertNotIn("Secure", [v for k, v in plain.handle("GET", "/login").headers if k == "Set-Cookie"][0])

    def test_a_wrong_state_does_not_spend_the_real_one(self):
        r0 = self.p.handle("GET", "/login")
        ck = cookie_of(r0)
        state = urllib.parse.parse_qs(urllib.parse.urlparse(dict(r0.headers)["Location"]).query)["state"][0]
        self.assertEqual(self.p.handle("GET", "/callback", query={"code": "c1", "state": "forged"}, cookie=ck).status, 400)
        self.assertEqual(self.p.handle("GET", "/callback", query={"code": "c1", "state": state}, cookie=ck).status, 302, "a forged link cannot burn the person's sign-in")

    def test_every_value_in_the_table_is_escaped(self):
        ck, _, _ = self.sign_in()
        bad = "<b>x</b>\"'"
        self.shop.invoices = [{k: bad for k in ("name", "posting_date", "customer", "grand_total", "currency", "pos_profile", "status")}]
        body = self.p.handle("GET", "/", cookie=ck).body.decode()
        self.assertNotIn("<b>", body)
        self.assertIn("&lt;b&gt;", body)

    def test_each_total_shows_its_currencys_decimals_and_a_thousands_separator(self):
        ck, _, _ = self.sign_in()
        self.shop.invoices = [dict(INVOICES[0], grand_total=2338.2), dict(INVOICES[1], name="POS-INV-0003", grand_total=0.1 + 0.2, currency="USD"),
                              dict(INVOICES[1], name="POS-INV-0004", grand_total=1500, currency="JPY"),
                              dict(INVOICES[1], name="POS-INV-0005", grand_total=1234.5675, currency="KWD")]
        body = self.p.handle("GET", "/", cookie=ck).body.decode()
        totals = re.findall(r'<td class="ivn-num">([^<]*)</td>', body)
        self.assertEqual(totals, ["2,338.20 ZAR", "0.30 USD", "1,500 JPY", "1,234.568 KWD"], "never 2338.2 ZAR or 0.30000000000000004 USD")

    def test_a_shop_redirect_is_not_followed_and_the_token_goes_only_where_it_was_sent(self):
        import http.server
        import threading
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            status, body = P.http_to_shop(f"http://127.0.0.1:{srv.server_port}")("GET", "/x", token="tok")
        finally:
            srv.shutdown()
        self.assertEqual((status, body, seen), (302, {}, [("/x", "Bearer tok")]))

    def test_a_shop_that_cannot_be_reached_is_status_zero_not_an_error(self):
        self.assertEqual(P.http_to_shop("http://127.0.0.1:9")("GET", "/x"), (0, {}))

    def test_the_page_does_not_say_signed_in_as_nobody(self):
        ck, _, _ = self.sign_in()
        orig = self.shop.__call__
        self.p.http = lambda m, path, token=None, form=None: (500, {}) if path.endswith("openid_profile") else orig(m, path, token, form)
        body = self.p.handle("GET", "/", cookie=ck).body.decode()
        self.assertIn("Signed in. ", body)
        self.assertNotIn("Signed in as .", body)

    def test_the_kits_stylesheet_is_served_from_the_kits_folder_and_an_unknown_path_is_not_found(self):
        r = self.p.handle("GET", "/ivn-kit.css")
        self.assertEqual((r.status, dict(r.headers)["Content-Type"]), (200, "text/css"))
        self.assertIn(b"ivn-kit 0.1.0", r.body[:400])
        self.assertEqual(self.p.handle("GET", "/etc/passwd").status, 404)
        self.assertEqual(self.p.handle("GET", "/ivn-kit.css/../portal.py").status, 404)

    def test_the_page_uses_the_kits_classes_and_no_colour_or_font_of_its_own(self):
        ck, _, _ = self.sign_in()
        body = self.p.handle("GET", "/", cookie=ck).body.decode()
        self.assertIn('class="ivn"', body)
        self.assertIn('href="ivn-kit.css"', body)
        for bad in ("style=", "rgb(", "font-family"):
            self.assertNotIn(bad, body, bad)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", body), "no colour literal")

    # ── a second review's cases ──────────────────────────────────────────────────────────────────────────
    def test_the_client_secret_goes_to_the_shop_at_sign_in_and_sign_out_and_nowhere_else(self):
        r = self.p.handle("GET", "/login")
        ck, q, cb = self.sign_in()
        home = self.p.handle("GET", "/", cookie=ck)
        out = self.p.handle("POST", "/logout", cookie=ck)
        rv = [c for c in self.shop.calls if c[1].endswith("revoke_token")]
        self.assertEqual((rv[0][3].get("client_id"), rv[0][3].get("client_secret")), ("client-1", SECRET))
        for resp in (r, cb, home, out):
            self.assertNotIn(SECRET.encode(), resp.body + repr(resp.headers).encode())

    def test_a_portal_without_its_client_secret_does_not_start(self):
        with self.assertRaises(KeyError):
            P.Portal({k: v for k, v in CONF.items() if k != "PORTAL_CLIENT_SECRET"}, http=self.shop)

    def test_a_session_dropped_during_the_exchange_leaves_no_live_token(self):
        r = self.p.handle("GET", "/login")
        ck = cookie_of(r)
        st = urllib.parse.parse_qs(urllib.parse.urlparse(dict(r.headers)["Location"]).query)["state"][0]
        orig = self.shop.__call__

        def exchange_then_evict(method, path, token=None, form=None):
            res = orig(method, path, token, form)
            if path.endswith("get_token"):
                self.p.sessions.clear()                     # a flood's eviction, or a second callback, while the shop answers
            return res
        self.p.http = exchange_then_evict
        cb = self.p.handle("GET", "/callback", query={"code": "c1", "state": st}, cookie=ck)
        self.assertNotEqual(cb.status, 302)
        self.assertTrue([c for c in self.shop.calls if c[1].endswith("revoke_token") and c[3].get("token") == TOKEN], "the orphaned token is revoked")
        self.assertEqual(self.p.sessions, {})

    def test_a_link_to_login_does_not_sign_a_signed_in_person_out(self):
        ck, _, _ = self.sign_in()
        r = self.p.handle("GET", "/login", cookie=ck)
        self.assertEqual((r.status, dict(r.headers).get("Location")), (302, "/"))
        self.assertIsNone(cookie_of(r), "the signed-in cookie is not replaced")
        self.assertIn(b"POS-INV", self.p.handle("GET", "/", cookie=ck).body)

    def test_responses_do_not_name_the_server_software(self):
        h = P.make_handler(self.p)
        self.assertEqual((h.server_version, h.sys_version), ("portal", ""))


if __name__ == "__main__":
    unittest.main()
