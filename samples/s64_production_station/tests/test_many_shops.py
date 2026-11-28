"""S64 for many retailers (the app template's handshake, ``tools/app_template/service/shops.py``) and its door
(``app.Tenant``): each retailer's presses and links are checked with its own secrets and read with its own key under the
library's prefix; a record name is one path segment, a redirect is never followed, a report is a form post and the
engine's label calls name their arguments.

    python3 -m unittest discover -s samples/s64_production_station/tests -p 'test_*.py'
"""

import base64
import datetime
import hashlib
import hmac
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(SAMPLE, "service"), SAMPLE,
                os.path.join(SAMPLE, "..", "..", "tools", "app_template", "service")]
import app  # noqa: E402
import fakeshop as F  # noqa: E402
import pst  # noqa: E402
import shops  # noqa: E402

APP = "ivendnext_pst"


class Clock:
    t = datetime.datetime(2026, 11, 4, 14, 30, tzinfo=datetime.timezone.utc).timestamp()

    def __call__(self):
        return self.t


class ManyRetailers(unittest.TestCase):
    def setUp(self):
        self.store = shops.FileStore(os.path.join(tempfile.mkdtemp(), "shops.json"))
        for site, n in (("shop-a.ivendnext.com", "a"), ("shop-b.ivendnext.com", "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:link": f"link-{n}", f"{APP}:sub:work": f"work-{n}", "user:pst@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:link": "link-c"}})     # no user key yet
        self.doors, self.clock = {}, Clock()
        self.svc = app.Service({"IVN_LIBRARY_APP": APP, "PST_PREFIX": "IVENDNEXT PST", "PST_PAGE_URL": F.PAGE},
                               store=self.store, tenants=self.door, now=self.clock, clock=self.clock)

    def tearDown(self):
        pst.use_prefix("PP PST")

    def door(self, url, key):
        if url not in self.doors:
            shop = F.Shop(self.clock)
            st = shop.db.pop("PP PST Station")["PST-S-00001"]
            shop.db["IVENDNEXT PST Station"] = {"PST-S-00001": st}
            shop.key = key
            self.doors[url] = shop
        return self.doors[url]

    def press(self, route, doctype, secret, site):
        raw = json.dumps({"point": "desk_action/1", "context": {"v": 1, "records": [{"doctype": doctype,
                                                                                    "name": "PST-S-00001"}]}}).encode()
        ts = str(int(self.clock()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        code, out, _ = self.svc.handle("POST", route, {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig,
                                                       shops.SITE_HEADER: site}, raw)
        return code, json.loads(out)

    def test_each_retailer_with_its_own_secrets_and_key_under_the_librarys_prefix(self):
        self.assertEqual(self.press("/pst/link", "IVENDNEXT PST Station", "link-b", "shop-a.ivendnext.com")[0], 401)
        self.assertEqual(self.press("/pst/link", "IVENDNEXT PST Station", "work-a", "shop-a.ivendnext.com")[0], 401)
        code, out = self.press("/pst/link", "IVENDNEXT PST Station", "link-a", "shop-a.ivendnext.com")
        self.assertEqual(code, 200, out)
        door = self.doors["https://shop-a.ivendnext.com"]
        self.assertEqual(door.key, "key-a:sec-a")
        link = door.db["IVENDNEXT PST Station"]["PST-S-00001"]["link"]
        self.assertIn("#s=shop-a.ivendnext.com&t=PST-S-00001.1.", link)
        self.assertNotIn("https://shop-b.ivendnext.com", self.doors)
        token = link.split("&t=")[1]
        _, body, _ = self.svc.handle("POST", "/pst/board", {}, json.dumps({"s": "shop-b.ivendnext.com", "t": token}).encode())
        self.assertEqual(json.loads(body), {"state": "unknown"})       # another retailer's link reads nothing

    def test_a_press_before_the_key_arrives_is_answered_in_words_and_reads_nothing(self):
        code, out = self.press("/pst/link", "IVENDNEXT PST Station", "link-c", "shop-c.ivendnext.com")
        self.assertEqual(code, 200)
        self.assertIn("not set up yet", out["message"]["body"])
        self.assertEqual(self.doors, {})

    def test_the_library_prefix_is_required(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": APP, "PST_PAGE_URL": F.PAGE}, store=self.store)


class ShopApi(unittest.TestCase):
    def test_one_path_segment_no_redirect_a_form_post_report_and_the_engines_calls(self):
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def _r(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, self.headers.get("Content-Type"), self.rfile.read(n).decode()))
                self.send_response(302)
                self.send_header("Location", "https://elsewhere.example/")
                self.end_headers()
            do_GET = do_POST = do_PUT = _r

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            t = app.Tenant(f"http://127.0.0.1:{srv.server_port}", "k", "s")
            for go in (lambda: t.doc("PP PST Station", "A/B"), lambda: t.report("POS Sale Report", {"warehouse": "S"}),
                       lambda: t.engine(app.LABEL, {"item_code": "TOPS BLU", "price": "19.99"}),
                       lambda: t.rows("PP PST Tag", ["worker", "sum(quantity) as pieces"], [], group_by="worker")):
                with self.assertRaises(app.TenantError) as e:
                    go()
                self.assertEqual(e.exception.code, 302)
            self.assertEqual(seen[0][:2], ("GET", "/api/resource/PP%20PST%20Station/A%2FB"))
            self.assertEqual(seen[1][:3], ("POST", "/api/method/ivendnext_mpos.api.v1.run_report",
                                           "application/x-www-form-urlencoded"))
            self.assertIn("report_name=POS+Sale+Report", seen[1][3])
            self.assertEqual(seen[2][:2], ("GET", "/api/method/ivendnext_pos.api.label_printing.get_item_barcode_for_label"
                                                  "?item_code=TOPS+BLU&price=19.99"))
            self.assertIn("group_by=worker", seen[3][1])
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
