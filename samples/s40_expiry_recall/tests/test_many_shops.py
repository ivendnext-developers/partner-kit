"""S40 for many shops (the app template's handshake): each call checked with its own shop's and its own door's secret,
read and written with that shop's own key under the library's prefix, a call before the shop's key arrives answered, and the
function entry answering the same."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakeshop import NOW, FakeTenant, check_body, press_body, signed  # noqa: E402

import app  # noqa: E402
import recall  # noqa: E402
import shops  # noqa: E402

APP, A, B = "ivendnext_rcl", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "RCL_PREFIX": "IVENDNEXT RCL"}


def library_tenant():
    t = FakeTenant(prefix="ivendnext_rcl")
    for it in t.items.values():
        for k in [k for k in it if k.startswith("pp_rcl_")]:
            it["ivendnext_rcl_" + k[len("pp_rcl_"):]] = it.pop(k)
    t.put_own("Recall Notice", "RCL-00001", {"notice_ref": "R", "recall_class": "Class I", "status": "Open", "lots": []})
    return t


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.store = shops.FileStore(os.path.join(tempfile.mkdtemp(), "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:block": f"bl-{n}", f"{APP}:sub:receipt": f"rc-{n}", "user:rcl@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:block": "bl-c", f"{APP}:sub:receipt": "rc-c"}})
        self.doors = {}
        self.svc = app.Service(LIB, store=self.store, tenants=self.door, now=NOW)

    def tearDown(self):
        recall.use_prefix("PP RCL")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = library_tenant()
            self.doors[url].key = key
        return self.doors[url]

    def send(self, route, raw, secret, site):
        h = signed(raw, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return self.svc.handle("POST", route, h, raw)

    def block(self, secret, site):
        raw = press_body("IVENDNEXT RCL Recall Notice", "RCL-00001", {"recall_class": "Class I",
                         "received_on": "2026-10-22 08:00:00", "lots": [{"batch": "AMOX-A"}]})
        return self.send("/press/block", raw, secret, site)

    def test_each_shop_is_written_with_its_own_key_under_the_librarys_prefix(self):
        for secret, site in (("bl-a", A), ("bl-b", B)):
            self.assertIn("Blocked 1 lot.", self.block(secret, site)[1]["message"]["body"])
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        for d in self.doors.values():
            self.assertEqual(d.get_own("Recall Notice", "RCL-00001")["status"], "Blocked")

    def test_the_receipt_reads_the_librarys_item_fields(self):
        raw = check_body("Purchase Receipt", {"posting_date": "2026-10-22", "supplier_delivery_note": "X", "items": [
            {"item_code": "PARA", "batch_no": "PARA-A", "ivendnext_rcl_lou": 1, "ivendnext_rcl_lou_days": 30}]})
        self.assertEqual(self.send("/check/receipt", raw, "rc-a", A), (200, {"verdict": "allow"}))
        self.doors[f"https://{A}"].items["PARA"]["ivendnext_rcl_min_shelf_days"] = 10
        raw2 = check_body("Purchase Receipt", {"posting_date": "2026-10-22", "supplier_delivery_note": "X",
                                               "items": [{"item_code": "PARA", "batch_no": "PARA-A"}]})
        self.assertEqual(self.send("/check/receipt", raw2, "rc-a", A), (200, {"verdict": "allow"}))

    def test_another_shops_or_another_doors_secret_and_an_unknown_site_are_refused(self):
        for secret, site in (("bl-b", A), ("rc-a", A), ("bl-a", "shop-z.ivendnext.com"), ("bl-a", None)):
            self.assertEqual(self.block(secret, site)[0], 401, (secret, site))
        self.assertEqual(sum(len(d.writes) for d in self.doors.values()), 0)

    def test_a_call_before_connect_again(self):
        code, out = self.block("bl-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["body"]), (200, app.NOT_SET_UP))
        raw = check_body("Purchase Receipt", {"items": []})
        self.assertEqual(self.send("/check/receipt", raw, "rc-c", "shop-c.ivendnext.com")[0], 503)  # the down answer
        self.assertEqual(self.doors, {})

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:block": "bl-a", "user:Administrator": "adm:sec"}))
        self.assertEqual((self.block("bl-a", A)[1]["message"]["body"], self.doors), (app.NOT_SET_UP, {}))

    def test_many_shops_without_the_librarys_prefix_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": APP}, store=self.store)

    def test_the_function_entry_answers_health(self):
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"ok": 1}))


if __name__ == "__main__":
    unittest.main()
