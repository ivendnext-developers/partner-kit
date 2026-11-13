"""The reference flow presses Allow as the shop's consent page sends it, on either page a shop serves: a form that POSTs
with the page's own token, or a button whose script sends the browser on by GET. No site is needed: a stand-in shop on
127.0.0.1 serves each page and gives a code only to the press its page asks for.

    python3 -m unittest discover -s tools/sign_in/tests
"""
import pathlib
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import signin_flow as flow  # noqa: E402

APPROVE = flow.O + ".approve"
REDIRECT = "http://app.example/cb"
TOKEN = "t0ken-of-this-page"
ADDRESS = APPROVE + "?client_id=c1&redirect_uri=http%3A%2F%2Fapp.example%2Fcb&state=s%201"


def form_page(address=ADDRESS):
    """The page with a form: its address is written escaped, as a page writes an attribute."""
    return f"""<p>{flow.APP} wants to access the following details from your account</p>
<form method="POST" action="{address.replace("&", "&amp;")}">
  <input type="hidden" name="csrf_token" value="{TOKEN}">
  <button type="submit" class="btn">Allow</button>
</form>
<a href="{REDIRECT}?error=access_denied" class="btn">Deny</a>"""


def script_page(address=ADDRESS):
    """The page with two buttons and a script: Allow sends the browser to the address, Deny back to the app."""
    return f"""<div class="h3">{flow.APP}</div><button id="deny">Deny</button><button id="allow">Allow</button>
<script>
  $('#allow').on('click', function(event) {{ window.location.replace("{address}"); }});
  $('#deny').on('click', function(event) {{ window.location.replace("{REDIRECT}?error=access_denied"); }});
</script>"""


class AllowTest(unittest.TestCase):
    def test_a_form_page_is_pressed_by_post_with_its_hidden_fields(self):
        self.assertEqual(flow.allow(form_page()), ("POST", ADDRESS, {"csrf_token": TOKEN}))

    def test_a_script_page_is_pressed_by_get_at_the_pages_own_address(self):
        self.assertEqual(flow.allow(script_page()), ("GET", ADDRESS, None))
        self.assertEqual(flow.allow(script_page(ADDRESS.replace("&", "&amp;"))), ("GET", ADDRESS, None))   # written escaped

    def test_a_page_that_offers_no_allow_gives_nothing_to_press(self):
        for page in ('{"error": "invalid_request", "error_description": "Mismatching redirect URI."}',
                     "<h3>An unexpected error occurred while authorizing the app.</h3>", ""):
            self.assertIsNone(flow.allow(page))

    def test_only_the_shops_own_approve_address_is_pressed(self):
        self.assertIsNone(flow.allow(form_page("http://evil.example" + ADDRESS)))
        self.assertIsNone(flow.allow(script_page("http://evil.example/cb?code=1")))
        self.assertIsNone(flow.allow(form_page().replace('method="POST"', 'method="GET"')))

    def test_a_hidden_field_outside_the_form_is_not_sent(self):
        page = form_page() + '<input type="hidden" name="extra" value="x">'
        self.assertEqual(flow.allow(page), ("POST", ADDRESS, {"csrf_token": TOKEN}))


class Shop:
    """A stand-in shop. ``page``: "form" (Allow is a POST with the page's token; a GET of approve, or a POST without the
    token, is refused), "script" (Allow is a GET), or "skip" (no page: authorize redirects to the approve address)."""

    def __init__(self, page):
        shop, self.page, self.presses = self, page, []

        class H(BaseHTTPRequestHandler):
            def _send(self, code, text="", location=None):
                self.send_response(code)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Length", str(len(text.encode())))
                self.end_headers()
                self.wfile.write(text.encode())

            def _approve(self, method, form):
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
                shop.presses.append((method, form))
                if shop.page == "form" and (method != "POST" or form.get("csrf_token") != TOKEN):
                    return self._send(403, "refused")
                back = urllib.parse.urlencode({"code": "c0de", "state": q["state"]})
                self._send(302, location=f"{q['redirect_uri']}?{back}")

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(url.query))
                if url.path == APPROVE:
                    return self._approve("GET", {})
                if q.get("redirect_uri") != REDIRECT:
                    return self._send(400, '{"error": "invalid_request"}')
                address = APPROVE + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
                if shop.page == "skip":
                    return self._send(302, location=address)
                self._send(200, form_page(address) if shop.page == "form" else script_page(address))

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
                self._approve("POST", dict(urllib.parse.parse_qsl(body)))

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


class AuthorizeTest(unittest.TestCase):
    def shop(self, page):
        shop = Shop(page)
        self.addCleanup(shop.stop)
        self.addCleanup(setattr, flow, "BASE", flow.BASE)
        flow.BASE = shop.base
        return shop

    def test_each_page_gives_a_code_and_the_same_state(self):
        for page, press in (("form", ("POST", {"csrf_token": TOKEN})), ("script", ("GET", {})), ("skip", ("GET", {}))):
            with self.subTest(page):
                shop = self.shop(page)
                a = flow.authorize(flow.browser(), "c1", REDIRECT, "chal", "s 1")
                self.assertEqual((a["code"], a["state_back"], a["redirected_to"]), ("c0de", "s 1", REDIRECT))
                self.assertEqual(shop.presses, [press])                 # pressed once, the way the page asks
                self.assertEqual(a["consent_shown"], page != "skip")

    def test_a_redirect_address_the_shop_refuses_gives_no_code_and_nothing_is_pressed(self):
        for page in ("form", "script"):
            with self.subTest(page):
                shop = self.shop(page)
                a = flow.authorize(flow.browser(), "c1", "http://evil.example/cb", "chal", "s5")
                self.assertEqual((a["code"], a["redirected_to"], a["approve_status"], shop.presses), (None, "", None, []))


if __name__ == "__main__":
    unittest.main()
