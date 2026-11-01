"""S2's hosted till key (``service/where.py``): the press checked with the till key's own secret, the shop's bin records read
with the app's user's key and limited to the till's store, one shop or many (the app template's handshake), and the words
the cashier reads when the app is not set up or the shop cannot be read.

    python3 -m unittest discover -s samples/s2_bins/tests -p 'test_where.py' -v
"""

import base64
import hashlib
import hmac
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service"), str(KIT / "tools" / "contracts")]
import check  # noqa: E402
import core  # noqa: E402
import where  # noqa: E402
import shops  # noqa: E402

SECRET, STORE, OTHER = "point-secret-1", "Store 1 - DR", "Store 2 - DR"
ONE = {"IVN_POINT_SECRET": SECRET, "IVN_SHOP_URL": "https://shop.example", "IVN_SHOP_KEY": "k:s", "BLN_PREFIX": "IVENDNEXT BLN"}
SHOP = {  # the shop's records, as the record API lists them
    "IVENDNEXT BLN Location": [{"name": "Floor 1", "kind": "Shop floor", "store": STORE},
                               {"name": "Back 1", "kind": "Back room", "store": STORE},
                               {"name": "Floor 2", "kind": "Shop floor", "store": OTHER}],
    "IVENDNEXT BLN Item In Bin": [{"item": "CASE", "bin": "F1-01", "location": "Floor 1", "qty": 4},
                                  {"item": "CABLE", "bin": "B1-07", "location": "Back 1", "qty": 12},
                                  {"item": "CABLE", "bin": "F2-01", "location": "Floor 2", "qty": 9},
                                  {"item": "EARBUDS", "bin": "F2-01", "location": "Floor 2", "qty": 3},
                                  {"item": "PHONE", "bin": "F1-01", "location": "Floor 1", "qty": 0},
                                  {"item": "CASE", "bin": "B1-07", "location": None, "qty": 2}],   # saved before 1.1.0
}


def _match(row, flt):
    field, op, value = flt
    if op == "in":
        return row.get(field) in value
    if op == ">":
        return float(row.get(field) or 0) > value
    return row.get(field) == value


class Reader:
    """A stand-in for the shop's record API: lists rows from a dict per shop address, counts its reads, can go down."""

    def __init__(self, by_url=None, lax=False):
        self.by_url, self.calls, self.filters, self.down = by_url or {"https://shop.example": SHOP}, [], {}, False
        self.timeouts, self.refuse = [], None
        self.lax = lax          # a shop that answers more than it was asked: ignores every filter but the items

    def __call__(self, url, key, doctype, fields, filters, timeout=None):
        self.calls.append((url, key, doctype))
        self.timeouts.append(timeout)
        self.filters[doctype] = filters
        if self.down:
            raise where.ShopUnreadable("down")
        if self.refuse:
            raise where.ShopUnreadable("refused", self.refuse)
        rows = [r for r in self.by_url[url].get(doctype, [])
                if all(_match(r, f) for f in filters if not self.lax or f[0] == "item")]
        return [{k: r.get(k) for k in fields} for r in rows]


def ctx(*codes, store=STORE):
    return {"sale_ref": "S-1", "store": store, "pos_profile": "Store 1 — R1", "company": "Demo", "currency": "USD",
            "operator": "cashier@shop.example", "customer": None,
            "lines": [{"item_code": c, "qty": 1, "uom": "Nos", "luid": f"l{i}"} for i, c in enumerate(codes)]}


def raw_of(context):
    return json.dumps({"point": "where_is_it", "context": context}, separators=(",", ":")).encode()


def signed(raw, secret, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
    if site:
        h[shops.SITE_HEADER] = site
    return h


def body(out):
    return out[1]["message"]["body"]


class OneShop(unittest.TestCase):
    def setUp(self):
        self.reader = Reader()
        self.svc = where.Service(ONE, reader=self.reader)

    def press(self, context, secret=SECRET, ts=None, path=where.ROUTE):
        raw = raw_of(context)
        return self.svc.handle("POST", path, signed(raw, secret, ts), raw)

    def test_each_item_is_named_with_its_bin_at_this_store(self):
        code, out = self.press(ctx("CASE", "CABLE"))
        self.assertEqual(code, 200)
        self.assertEqual(out["message"]["body"], "CASE: shop floor F1-01 (4); CABLE: back room B1-07 (12), fetch it")
        self.assertEqual(out["message"]["level"], "info")

    def test_another_stores_bin_is_never_named(self):
        code, out = self.press(ctx("EARBUDS"))
        self.assertEqual(body((code, out)), "EARBUDS: no bin recorded")
        self.assertNotIn("F2-01", json.dumps(out))
        code, out = self.press(ctx("CABLE"))
        self.assertNotIn("F2-01", body((code, out)))

    def test_an_empty_bin_is_not_named(self):
        self.assertEqual(body(self.press(ctx("PHONE"))), "PHONE: no bin recorded")

    def test_the_reads_ask_only_for_held_items_and_this_stores_locations(self):
        self.press(ctx("CASE", "CABLE"))
        self.assertEqual(self.reader.filters["IVENDNEXT BLN Item In Bin"],
                         [["item", "in", ["CABLE", "CASE"]], ["qty", ">", 0], ["location", "in", ["Back 1", "Floor 1"]]])
        self.assertEqual(self.reader.filters["IVENDNEXT BLN Location"], [["store", "=", STORE]])

    def test_a_record_with_no_location_yet_is_not_named(self):
        self.assertEqual(body(self.press(ctx("CASE"))), "CASE: shop floor F1-01 (4)")   # not the location-less B1-07 row

    def test_a_chain_is_read_only_at_the_tills_store(self):
        """Forty stores, thirty items, a bin for each item in each store: one store's rows come back, never 1,200."""
        shop = {"IVENDNEXT BLN Location": [{"name": f"Floor {n}", "kind": "Shop floor", "store": f"Store {n}"} for n in range(40)],
                "IVENDNEXT BLN Item In Bin": [{"item": f"I{i:02d}", "bin": f"S{n}-{i:02d}", "location": f"Floor {n}", "qty": 1}
                                              for n in range(40) for i in range(30)]}
        reader = Reader({"https://shop.example": shop})
        svc = where.Service(ONE, reader=reader)
        raw = raw_of(ctx(*[f"I{i:02d}" for i in range(30)], store="Store 7"))
        out = svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw)
        self.assertTrue(body(out).startswith("I00: shop floor S7-00 (1)"), body(out))
        self.assertNotIn("too many", body(out))

    def test_a_store_with_no_location_reads_nothing_more(self):
        self.assertEqual(body(self.press(ctx("CASE", store="Store 9 - DR"))), "CASE: no bin recorded")
        self.assertEqual([c[2] for c in self.reader.calls], ["IVENDNEXT BLN Location"])

    def test_more_rows_than_one_answer_takes_is_said_never_cut(self):
        big = dict(SHOP, **{"IVENDNEXT BLN Item In Bin": SHOP["IVENDNEXT BLN Item In Bin"] +
                            [{"item": "CASE", "bin": f"X-{i}", "location": "Floor 1", "qty": 1}
                                                            for i in range(where.ROWS_MAX)]})
        svc = where.Service(ONE, reader=Reader({"https://shop.example": big}))
        raw = raw_of(ctx("CASE"))
        self.assertEqual(body(svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw)), where.TOO_MANY)

    def test_only_the_first_thirty_items_are_looked_up(self):
        codes = [f"ITEM-{i:02d}" for i in range(40)]
        code, out = self.press(ctx(*codes))
        self.assertEqual(len(self.reader.filters["IVENDNEXT BLN Item In Bin"][0][2]), where.CODES_MAX)
        self.assertIn("more", out["message"]["body"])

    def test_every_read_shares_one_deadline(self):
        t = [100.0]
        reader = Reader()
        def slow(*a, **k):
            t[0] += 2.5                          # the first read takes 2.5 s: past the deadline, the second is never sent
            return reader(*a, **k)
        svc = where.Service(ONE, reader=slow, clock=lambda: t[0])
        raw = raw_of(ctx("CASE"))
        out = svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw)
        self.assertEqual(body(out), where.UNREADABLE)
        self.assertEqual(len(reader.calls), 1)

    def test_a_read_gets_only_the_time_left(self):
        t = [100.0]
        reader = Reader()
        def slow(*a, **k):
            out = reader(*a, **k)
            t[0] += 1.5                          # the first read takes 1.5 s, so 0.7 s are left for the second
            return out
        svc = where.Service(ONE, reader=slow, clock=lambda: t[0])
        raw = raw_of(ctx("CASE"))
        svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw)
        self.assertEqual(reader.timeouts[0], where.READ_TIMEOUT)
        self.assertAlmostEqual(reader.timeouts[1], where.DEADLINE - 1.5)

    def test_a_refused_key_is_a_set_up_problem_not_an_outage(self):
        self.reader.refuse = 401
        self.assertEqual(body(self.press(ctx("CASE"))), where.REFUSED)
        self.reader.refuse = 403
        self.assertEqual(body(self.press(ctx("CASE"))), where.NO_RIGHTS)
        self.reader.refuse = 500
        self.assertEqual(body(self.press(ctx("CASE"))), where.UNREADABLE)

    def test_a_timestamp_that_is_not_plain_digits_is_refused_not_a_crash(self):
        raw = raw_of(ctx("CASE"))
        h = dict(signed(raw, SECRET), **{"X-iVendNext-Timestamp": "\u00b2"})
        self.assertEqual(self.svc.handle("POST", where.ROUTE, h, raw)[0], 401)

    def test_an_empty_secret_is_refused_at_start(self):
        with self.assertRaises(SystemExit):
            where.Service(dict(ONE, IVN_POINT_SECRET=" "), reader=Reader())

    def test_a_shop_that_answers_more_than_asked_still_never_names_another_stores_bin(self):
        svc = where.Service(ONE, reader=Reader(lax=True))
        raw = raw_of(ctx("EARBUDS", "CABLE"))
        out = svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw)
        self.assertEqual(body(out), "EARBUDS: no bin recorded; CABLE: back room B1-07 (12), fetch it")

    def test_the_shop_is_read_with_the_apps_key_and_only_read(self):
        self.press(ctx("CASE"))
        self.assertEqual(self.reader.calls, [("https://shop.example", "k:s", "IVENDNEXT BLN Location"),
                                             ("https://shop.example", "k:s", "IVENDNEXT BLN Item In Bin")])

    def test_an_empty_sale_reads_nothing(self):
        code, out = self.press(ctx())
        self.assertEqual((code, out["message"]["body"]), (200, "There are no items on this sale yet."))
        self.assertEqual(self.reader.calls, [])

    def test_a_wrong_secret_or_an_old_timestamp_is_refused(self):
        self.assertEqual(self.press(ctx("CASE"), secret="another")[0], 401)
        self.assertEqual(self.press(ctx("CASE"), ts=time.time() - 400)[0], 401)
        raw = raw_of(ctx("CASE"))
        self.assertEqual(self.svc.handle("POST", where.ROUTE, {}, raw)[0], 401)
        self.assertEqual(self.reader.calls, [])

    def test_a_body_changed_after_signing_is_refused(self):
        raw = raw_of(ctx("CASE"))
        self.assertEqual(self.svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw_of(ctx("CABLE")))[0], 401)
        self.assertEqual(self.svc.handle("POST", where.ROUTE, signed(b"", SECRET), raw)[0], 401)   # a signature over the time alone

    def test_another_route_and_a_bad_body(self):
        self.assertEqual(self.press(ctx("CASE"), path="/webhook")[0], 404)
        raw = b'{"context": "x"}'
        self.assertEqual(self.svc.handle("POST", where.ROUTE, signed(raw, SECRET), raw)[0], 400)
        self.assertEqual(self.svc.handle("POST", where.ROUTE, {}, None)[0], 413)
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"status": "ok"}))

    def test_the_shop_down_is_said_in_words(self):
        self.reader.down = True
        code, out = self.press(ctx("CASE"))
        self.assertEqual((code, out["message"]["body"], out["message"]["level"]), (200, where.UNREADABLE, "warning"))

    def test_every_answer_holds_the_contract(self):
        if not check.available():
            self.skipTest("the contracts folder is missing from this copy of the kit")
        self.reader.down = False
        answers = [self.press(ctx("CASE", "CABLE"))[1], self.press(ctx())[1], self.press(ctx("ZZZ"))[1]]
        self.reader.down = True
        answers.append(self.press(ctx("CASE"))[1])
        words = (where.NOT_SET_UP, where.REFUSED, where.NO_RIGHTS, where.UNREADABLE, where.TOO_MANY)
        answers += [where._warning(w) for w in words]
        for a in answers:
            self.assertEqual(check.errors("remote_till_key", "answer", a), [])
        self.assertLessEqual(max(len(w) for w in words), core.BODY_MAX)


class TheManifest(unittest.TestCase):
    """The service finds a record by its Location, so the manifest must fill it from the bin, and the role must read it."""

    def test_what_is_in_each_bin_fills_its_location_from_the_bin(self):
        m = json.loads((HERE.parent / "manifest.json").read_text())
        dt = {d["name"]: d for d in m["doctypes"]}
        field = {f["fieldname"]: f for f in dt["PP BLN Item In Bin"]["fields"]}["location"]
        self.assertEqual((field["fieldtype"], field["options"], field["fetch_from"], field.get("read_only")),
                         ("Link", "PP BLN Location", "bin.location", 1))


class ShopApi(unittest.TestCase):
    """``read_list`` against a real HTTP server: the list read's shape, a refusal, and a redirect never followed."""

    def setUp(self):
        seen = self.seen = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                if self.path.startswith("/api/resource/IVENDNEXT%20BLN%20Bin?"):
                    self.send_response(200); self.end_headers(); self.wfile.write(b'{"data": [{"name": "F1-01"}]}')
                elif self.path.startswith("/api/resource/Moved"):   # to an address that answers: following it would succeed
                    self.send_response(302)
                    self.send_header("Location", "/api/resource/IVENDNEXT%20BLN%20Bin?moved=1"); self.end_headers()
                else:
                    self.send_response(403); self.end_headers(); self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_list_read_sends_the_key_the_fields_and_the_filters(self):
        rows = where.read_list(self.url, "k:s", "IVENDNEXT BLN Bin", ["name"], [["name", "in", ["F1-01"]]])
        self.assertEqual(rows, [{"name": "F1-01"}])
        path, auth = self.seen[0]
        self.assertEqual(auth, "token k:s")
        self.assertIn("filters=%5B%5B%22name%22%2C+%22in%22%2C+%5B%22F1-01%22%5D%5D%5D", path)
        self.assertIn(f"limit_page_length={where.ROWS_MAX + 1}", path)     # one more than an answer takes: a cut list is seen

    def test_a_refusal_is_unreadable(self):
        with self.assertRaises(where.ShopUnreadable):
            where.read_list(self.url, "k:s", "IVENDNEXT BLN Location", ["name"], [])

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(where.ShopUnreadable):
            where.read_list(self.url, "k:s", "Moved", ["name"], [])
        self.assertEqual(len(self.seen), 1)


class ManyShops(unittest.TestCase):
    APP = "ivendnext_bln"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = shops.FileStore(os.path.join(self.tmp.name, "shops.json"))
        other = {k: [dict(r, store=STORE) if k.endswith("Location") else r for r in v] for k, v in SHOP.items()}
        other["IVENDNEXT BLN Item In Bin"] = [{"item": "CASE", "bin": "F2-01", "location": "Floor 2", "qty": 1}]
        self.reader = Reader({"https://a.example.com": SHOP, "https://b.example.com": other})
        self.svc = where.Service({"IVN_LIBRARY_APP": self.APP, "BLN_PREFIX": "IVENDNEXT BLN"}, store=self.store,
                                 reader=self.reader)
        for site, users in (("a.example.com", {"user:bins@a.example.com": "ka:sa"}), ("b.example.com", {"user:bins@b": "kb:sb"})):
            self.store.put(site, {"site": site, "url": f"https://{site}", "previous": {},
                                  "secrets": {f"{self.APP}:where_is_it": f"secret-{site}", "IVENDNEXT BLN x": "webhook", **users}})

    def tearDown(self):
        self.tmp.cleanup()

    def press(self, site, secret, context=None):
        raw = raw_of(context or ctx("CASE"))
        return self.svc.handle("POST", where.ROUTE, signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_records_with_its_own_key(self):
        self.assertEqual(body(self.press("a.example.com", "secret-a.example.com")), "CASE: shop floor F1-01 (4)")
        self.assertEqual(body(self.press("b.example.com", "secret-b.example.com")), "CASE: shop floor F2-01 (1)")
        self.assertEqual({(u, k) for u, k, _ in self.reader.calls}, {("https://a.example.com", "ka:sa"),
                                                                     ("https://b.example.com", "kb:sb")})

    def test_only_the_till_keys_own_secret_and_only_for_its_shop(self):
        self.assertEqual(self.press("a.example.com", "secret-b.example.com")[0], 401)
        self.assertEqual(self.press("a.example.com", "webhook")[0], 401)
        self.assertEqual(self.press("c.example.com", "secret-a.example.com")[0], 401)
        self.assertEqual(self.reader.calls, [])

    def test_before_the_shop_hands_over_its_user_it_says_so(self):
        self.store.put("a.example.com", {"site": "a.example.com", "url": "https://a.example.com", "previous": {},
                                         "secrets": {f"{self.APP}:where_is_it": "secret-a.example.com"}})
        code, out = self.press("a.example.com", "secret-a.example.com")
        self.assertEqual((code, out["message"]["body"]), (200, where.NOT_SET_UP))
        self.assertEqual(self.reader.calls, [])

    def test_the_shops_store_down_is_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")
        svc = where.Service({"IVN_LIBRARY_APP": self.APP}, store=Down(), reader=self.reader)
        raw = raw_of(ctx("CASE"))
        self.assertEqual(svc.handle("POST", where.ROUTE, signed(raw, "x", site="a.example.com"), raw)[0], 503)


class AsAFunction(unittest.TestCase):
    """The load balancer's event in, its response out: health, a signed press, a refusal; one log line, no body."""

    def test_health_a_signed_press_and_a_refusal(self):
        svc = where.Service(ONE, reader=Reader())
        entry = where.function.entry(lambda: svc, where.handle)
        raw = raw_of(ctx("CASE"))
        ok = {"httpMethod": "POST", "path": where.ROUTE, "headers": {k.lower(): v for k, v in signed(raw, SECRET).items()},
              "body": base64.b64encode(raw).decode(), "isBase64Encoded": True}
        log = io.StringIO()
        with mock.patch.object(sys, "stdout", log):
            health = entry({"httpMethod": "GET", "path": "/health", "headers": {}, "body": ""})
            pressed = entry(ok)
            refused = entry(dict(ok, headers={}))
        self.assertEqual(health["statusCode"], 200)
        self.assertEqual((pressed["statusCode"], json.loads(pressed["body"])["message"]["body"]), (200, "CASE: shop floor F1-01 (4)"))
        self.assertEqual(refused["statusCode"], 401)
        lines = [json.loads(x) for x in log.getvalue().splitlines()]
        self.assertEqual([x["status"] for x in lines], [200, 200, 401])
        self.assertNotIn("CASE", log.getvalue())

    def test_the_log_says_why_the_shop_was_not_read(self):
        reader = Reader()
        reader.refuse = 403
        entry = where.function.entry(lambda: where.Service(ONE, reader=reader), where.handle)
        raw = raw_of(ctx("CASE"))
        log = io.StringIO()
        with mock.patch.object(sys, "stdout", log):
            entry({"httpMethod": "POST", "path": where.ROUTE, "headers": signed(raw, SECRET), "body": raw.decode()})
        self.assertEqual(json.loads(log.getvalue())["shop"], 403)

    def test_the_built_package_imports_s2s_core(self):
        """The package the hosting runs (deploy_app's zip of app.json's list) holds one core, S2's."""
        app = json.loads((HERE.parent / "app.json").read_text())
        names = [n for p in app["package"] for n in ([p] if p.endswith(".py") else [])]
        self.assertEqual([n for n in names if n.endswith("/core.py")], ["samples/s2_bins/core.py"])
        with tempfile.TemporaryDirectory() as d:
            for n in names:
                Path(d, n).parent.mkdir(parents=True, exist_ok=True)
                Path(d, n).write_bytes((KIT / n).read_bytes())
            import subprocess
            r = subprocess.run([sys.executable, "-I", "-c", "import importlib.util as u;"
                                "s=u.spec_from_file_location('w','samples/s2_bins/service/where.py');m=u.module_from_spec(s);"
                                "s.loader.exec_module(m);print(m.core.where_answer.__name__, m.core.TITLE)"],
                               cwd=d, capture_output=True, text=True, env={"IVN_POINT_SECRET": "x"})
            self.assertEqual(r.stdout.strip(), "where_answer Where is it?", r.stderr)


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

    def test_a_list_read_cut_short_is_the_shop_unreadable_never_a_crash(self):
        with mock.patch.object(where.urllib.request, "build_opener", return_value=types.SimpleNamespace(open=cut_answer)):
            with self.assertRaises(where.ShopUnreadable) as e:
                where.read_list("https://shop.example", "k:s", "IVENDNEXT BLN Bin", ["name"], [])
        self.assertIn("IncompleteRead", str(e.exception))


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = where.Service(ONE, reader=lambda *a, **k: [])
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {where.ROUTE: (where.KEY, SECRET)}

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


class OwnServerTestCall(unittest.TestCase):
    """``service/app.py``, the whole S2 service for your own server, answers the test call (``X-iVendNext-Test: 1``,
    tools/app_template/service/testcall.py) at its till key's route: checked as a real call, then answered 200
    {"test": "ok", "point": "where_is_it"} without reading a bin; a route it does not have is 404."""
    BAD = b"not a call"          # a body the till key's handler cannot read: a real call with it is never answered 200
    routes = {"/point/where_is_it": ("where_is_it", "own-point-secret")}

    def setUp(self):
        import shutil
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        port = self.free_port()
        conf = {"PP_BASE": "http://127.0.0.1:9", "PP_KEY": "k", "PP_SECRET": "s", "PP_WEBHOOK_SECRETS": "w1", "PP_PORT": port,
                "PP_ADMIN_TOKEN": "t0ken", "PP_POINT_SECRET": "own-point-secret", "PP_DB": os.path.join(d, "bins.sqlite3")}
        Path(d, ".env.local").write_text("".join(f"{k}={v}\n" for k, v in conf.items()))
        self.serve([str(HERE.parent / "service" / "app.py"), str(Path(d, ".env.local"))], d, port)

    def serve(self, argv, cwd, port):
        """Run the server in its own process; it prints its line just before it serves its port."""
        import socket, subprocess
        self.port = port
        p = subprocess.Popen([sys.executable, "-I", "-B", *argv], cwd=cwd, env={"PATH": os.environ.get("PATH", "")},
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        def stop():
            p.kill()
            p.communicate()
        self.addCleanup(stop)
        self.assertIn(f":{port}", p.stdout.readline())
        for _ in range(200):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)

    @staticmethod
    def free_port():
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def call(self, path, raw, secret, test=True):
        import urllib.error, urllib.request
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=raw, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (urllib.error.URLError, OSError):     # the handler failed on the body: the connection closed unanswered
            return 0, None

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and failed
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_at_the_webhook_stores_no_sale(self):
        """The webhook answers a test call after its own signature check, and handles no sale (nothing is stored)."""
        import re as _re
        import urllib.error
        import urllib.request
        sys.path.insert(0, str(HERE.parents[1] / "s1_warranty" / "service"))
        import receiver
        source = (HERE.parent / "service" / "app.py").read_text(encoding="utf-8")
        header = _re.search(r'self\.headers\.get\("(X-[A-Za-z]+-Webhook-Signature)"\)', source).group(1)
        body = json.dumps({"doctype": "POS Invoice", "name": "T-1", "modified": "2026-10-31 10:00:00"}).encode()

        def post(secret):
            h = {header: receiver._sign(secret, body).decode(), "X-iVendNext-Test": "1"}
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/webhook", data=body, headers=h, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        self.assertEqual(post("w1"), (200, {"test": "ok", "point": "webhook"}))
        self.assertEqual(post("not-w1")[0], 401)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/status", headers={"X-PP-Admin": "t0ken"})
        with urllib.request.urlopen(req, timeout=10) as r:
            events = json.loads(r.read()).get("events") or []
        self.assertFalse([e for e in events if "T-1" in json.dumps(e)], events)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
