"""S16 for many shops (the app template's handshake): each press checked with its own shop's secret and written with
that shop's own integration key, a press before Connect again answered in words, and one press handled by one call
even when two copies of the function receive it (a claim in the shops table).

    python3 -m unittest discover -s samples/s16_pick_route/tests -p 'test_*.py'
"""

import base64
import itertools
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import app  # noqa: E402
import route  # noqa: E402
import shops  # noqa: E402
from test_service import body, signed  # noqa: E402

APP, A, B = "ivendnext_pck", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "PCK_PREFIX": "IVENDNEXT PCK"}
NUMBERS = itertools.count(1)


class Door:
    """A stand-in for one shop's record API, reached with the key that shop handed over."""

    def __init__(self, url, key, tasks, gate=None, refuse=None, lost=False):
        self.url, self.key, self.tasks, self.gate, self.refuse, self.lost = url, key, tasks, gate, refuse, lost

    def find_tasks(self, sos, key):
        if self.refuse:
            raise app.TenantError("GET -> HTTP %d" % self.refuse, self.refuse)
        return {t["sales_order"]: {"name": n, "sales_order": t["sales_order"], "picker": t["picker"], "priority": t["priority"]}
                for n, t in self.tasks.items() if t["made_with"][0] == self.url and t["sales_order"] in sos
                and t["press_key"] == key}

    def create_task(self, doc):
        if self.gate:
            self.gate.wait(5)                   # a slow shop: holds the press while another copy receives it
        if self.lost:                           # the shop saves the task but its answer never arrives
            self.lost = False
            self.tasks[f"IVN-PCK-{next(NUMBERS):05d}"] = dict(doc, made_with=(self.url, self.key))
            raise app.TenantError("POST -> TimeoutError")
        name = f"IVN-PCK-{next(NUMBERS):05d}"      # the shop's own series: two shops racing never share a number
        self.tasks[name] = dict(doc, made_with=(self.url, self.key))
        return name


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:route": f"route-{n}", "user:pck@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:route": "route-c"}})     # no user key yet
        self.tasks, self.gate, self.refuse, self.lost, self.clock = {}, None, None, False, Clock()
        self.svc = self.copy()

    def tearDown(self):
        route.use_prefix("PP PCK")

    def copy(self):
        """One copy of the function: its own memory, the shared shops table."""
        return app.Service(LIB, store=self.store, clock=self.clock,
                           tenants=lambda url, key: Door(url, key, self.tasks, self.gate, self.refuse, self.lost))

    def press(self, secret, site, svc=None, **kw):
        raw = body(**kw)
        h = signed(raw, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", "/press/route", h, raw)

    def test_each_shop_is_written_with_its_own_key_under_the_librarys_names(self):
        code, out = self.press("route-a", A)
        self.assertEqual((code, out["open_record"]["doctype"]), (200, "IVENDNEXT PCK Pick Task"))
        code, _ = self.press("route-b", B, key="key-0002-abcdef")
        self.assertEqual(code, 200)
        self.assertEqual(sorted(t["made_with"] for t in self.tasks.values()),
                         [(f"https://{A}", "key-a:sec-a"), (f"https://{B}", "key-b:sec-b")])
        self.assertEqual({t["doctype"] for t in self.tasks.values()}, {"IVENDNEXT PCK Pick Task"})

    def test_another_shops_secret_an_unknown_site_and_no_site_are_refused(self):
        for secret, site in (("route-b", A), ("route-a", B), ("route-a", "shop-z.ivendnext.com"), ("route-a", None)):
            code, out = self.press(secret, site)
            self.assertEqual((code, out["error"]), (401, "the signature does not match"), (secret, site))
        self.assertEqual(self.tasks, {})

    def test_a_shop_whose_secret_changed_is_accepted_with_the_previous_one_while_it_moves(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets=dict(rec["secrets"], **{f"{APP}:sub:route": "route-a2"}),
                               previous={f"{APP}:sub:route": "route-a"}))
        self.assertEqual(self.press("route-a", A)[0], 200)

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("route-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["level"], out["message"]["body"]), (200, "warning", app.NOT_SET_UP))
        self.assertNotIn("open_record", out)
        self.assertEqual(self.tasks, {})

    def test_a_shop_that_refuses_the_apps_user_is_told_so_in_words(self):
        self.refuse = 403
        self.svc = self.copy()
        code, out = self.press("route-a", A)
        self.assertEqual((code, out["message"]["body"]), (200, app.REFUSED + app.CONNECT_AGAIN))

    def test_a_shop_that_does_not_answer_is_a_502_so_the_user_checks_the_record(self):
        self.refuse = 500
        self.svc = self.copy()
        self.assertEqual(self.press("route-a", A)[0], 502)

    def test_two_copies_receiving_one_press_make_one_task(self):
        self.gate = threading.Event()
        first, second = self.copy(), self.copy()
        got = {}
        t = threading.Thread(target=lambda: got.update(first=self.press("route-a", A, svc=first)))
        t.start()
        for _ in range(100):                   # wait until the first copy holds the press
            if any(shops.CLAIM_MARK in k for k in self.store._read()):
                break
            time.sleep(0.02)
        code, out = self.press("route-a", A, svc=second)
        self.assertEqual(code, 409)
        self.gate.set()
        t.join(5)
        self.assertEqual(got["first"][0], 200)
        self.assertEqual(len(self.tasks), 1)
        self.assertEqual(self.press("route-a", A, svc=second), got["first"])   # the retry finds the task
        self.assertEqual(len(self.tasks), 1)
        self.assertEqual([k for k in self.store._read() if shops.CLAIM_MARK in k], [])   # no claim is left behind

    def test_the_same_key_from_another_shop_is_another_press(self):
        self.gate = threading.Event()
        holder = self.copy()
        t = threading.Thread(target=lambda: self.press("route-a", A, svc=holder))
        t.start()
        for _ in range(100):
            if any(shops.CLAIM_MARK in k for k in self.store._read()):
                break
            time.sleep(0.02)
        self.gate.set()        # B's own door is not held: only A's claim exists
        self.assertEqual(self.press("route-b", B)[0], 200)
        t.join(5)
        self.assertEqual(len(self.tasks), 2)

    def test_a_claim_left_by_a_stopped_copy_is_taken_over_once_stale(self):
        name = (f"press{shops.CLAIM_MARK}{A}{shops.CLAIM_MARK}"
                + __import__("hashlib").sha256(b"key-0001-abcdef").hexdigest()[:32])
        self.assertTrue(self.store.claim(name, self.clock(), app.CLAIM_STALE))     # a copy stopped while holding it
        self.assertEqual(self.press("route-a", A)[0], 409)
        self.clock.t += app.CLAIM_STALE + 1
        self.assertEqual(self.press("route-a", A)[0], 200)
        self.assertEqual(len(self.tasks), 1)

    def test_a_task_saved_after_the_service_stopped_waiting_is_never_made_twice(self):
        self.lost = True
        self.svc = self.copy()
        self.assertEqual(self.press("route-a", A)[0], 502)        # the shop saved it; the answer never came
        self.assertEqual(self.press("route-a", A)[0], 409)        # the claim stands: "check the record"
        self.clock.t += app.CLAIM_STALE + 1
        code, out = self.press("route-a", A)
        self.assertEqual((code, len(self.tasks)), (200, 1))        # the retry finds the task the shop saved
        self.assertEqual(out["open_record"]["name"], next(iter(self.tasks)))

    def test_a_list_press_retried_after_a_stop_finds_what_was_made_and_makes_the_rest(self):
        names = ("SO-1", "SO-2", "SO-3")
        raw = body(names=names)
        door = Door(f"https://{A}", "key-a:sec-a", self.tasks)
        made = door.create_task(route.plan(json.loads(raw)["context"]["records"][1], {"picker": "pick@shop.example",
                                                                                      "priority": "Urgent"}, "key-0001-abcdef"))
        code, out = self.press("route-a", A, names=names)      # the same key: a retry after a copy stopped mid-press
        self.assertEqual(code, 200)
        by_order = {t["sales_order"]: n for n, t in self.tasks.items()}
        self.assertEqual(sorted(by_order), list(names))
        self.assertEqual(by_order["SO-2"], made)               # found, not made again
        self.assertEqual(len(self.tasks), 3)

    def test_a_claim_the_table_cannot_take_is_a_503_and_writes_nothing(self):
        class NoClaim(shops.FileStore):
            def claim(self, *a):
                raise OSError("down")

        store = NoClaim(os.path.join(self.tmp, "shops.json"))
        svc = app.Service(LIB, store=store, tenants=lambda url, key: Door(url, key, self.tasks))
        self.assertEqual(self.press("route-a", A, svc=svc), (503, {"error": "unavailable"}))
        self.assertEqual(self.tasks, {})

    def test_a_read_with_no_answer_frees_the_press_at_once(self):
        door = Door(f"https://{A}", "key-a:sec-a", self.tasks)
        door.find_tasks = lambda sos, key: (_ for _ in ()).throw(app.TenantError("GET -> TimeoutError"))
        svc = app.Service(LIB, store=self.store, clock=self.clock, tenants=lambda url, key: door)
        self.assertEqual(self.press("route-a", A, svc=svc)[0], 502)
        self.assertEqual(self.press("route-a", A)[0], 200)        # nothing was written: the retry is not held back

    def test_more_orders_than_one_press_may_carry_are_refused_in_words(self):
        names = tuple(f"SO-{i}" for i in range(app.ORDERS_MAX + 1))
        code, out = self.press("route-a", A, names=names)
        self.assertEqual((code, out["message"]["body"], self.tasks), (200, app.TOO_MANY, {}))
        self.assertEqual(self.press("route-a", A, names=names[:-1], key="key-0003-abcdef")[0], 200)
        self.assertEqual(len(self.tasks), app.ORDERS_MAX)

    def test_an_old_press_is_refused_in_the_same_words_as_an_unknown_site(self):
        raw = body()
        for site in (A, "shop-z.ivendnext.com"):
            h = dict(signed(raw, "route-a", ts=time.time() - 3600), **{shops.SITE_HEADER: site})
            self.assertEqual(self.svc.handle("POST", "/press/route", h, raw), (401, {"error": "the signature does not match"}))

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:route": "route-a", "user:Administrator": "adm:sec"}))
        code, out = self.press("route-a", A)
        self.assertEqual((code, out["message"]["body"], self.tasks), (200, app.NOT_SET_UP, {}))

    def test_many_shops_without_the_librarys_prefix_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": APP}, store=self.store)

    def test_a_shops_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        svc = app.Service(LIB, store=Down())
        self.assertEqual(self.press("route-a", A, svc=svc), (503, {"error": "unavailable"}))

    def test_the_handshake_and_health_are_answered(self):
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"ok": 1}))
        code, out = self.svc.handle("POST", shops.CONNECT, {shops.SITE_HEADER: A}, b'{"site": "%s", "key": "x", "secrets": {}}' % A.encode())
        self.assertEqual((code, out), (403, {"refused": "key_form"}))


class ShopApi(unittest.TestCase):
    """``Tenant`` against a stand-in shop on a local port: the token, the shop's status kept, no redirect followed."""

    def setUp(self):
        seen = self.seen = []

        class Shop(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                if "Pick%20Task" in self.path and "redirect" not in self.path:
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1:9/elsewhere")
                    self.end_headers()
                    return
                self.send_response(403)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        route.use_prefix("PP PCK")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            app.tenant_of(self.url, "k:s").find_tasks(["SO-1"], "key-0001-abcdef")
        self.assertEqual(e.exception.code, 302)
        self.assertEqual([h for _, h in self.seen], ["token k:s"])

    def test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash(self):
        class Cut(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b'{"data": ')          # the connection closes before the rest

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Cut)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(app.TenantError) as e:
                app.tenant_of(f"http://127.0.0.1:{srv.server_address[1]}", "k:s").create_task({})
            self.assertIsNone(e.exception.code)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_a_refusal_keeps_the_shops_status(self):
        route.use_prefix("redirect")        # the stand-in answers this record type's address with 403
        with self.assertRaises(app.TenantError) as e:
            app.tenant_of(self.url, "k:s").find_tasks(["SO"], "k")
        self.assertEqual(e.exception.code, 403)


class Prefix(unittest.TestCase):
    def tearDown(self):
        route.use_prefix("PP PCK")

    def test_every_record_type_name_follows_the_prefix(self):
        """A census, not a list: under the library's prefix no module constant still names a sample record type. A name
        the prefix missed is written to a record type the library never installs: every write fails."""
        route.use_prefix("IVENDNEXT PCK")
        left = [(m.__name__, k) for m in (route, app) for k, v in vars(m).items()
                if isinstance(v, str) and v.startswith("PP PCK ")]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        self.assertIn(route.TASK.replace("IVENDNEXT PCK", "PP PCK"), [d["name"] for d in manifest["doctypes"]])


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:route": "route-a", "user:pck@x": "k:s"}})
        self.tasks = {}
        svc = app.Service(LIB, store=store, tenants=lambda url, key: Door(url, key, self.tasks))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        route.use_prefix("PP PCK")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        for b64, key in ((False, "key-0001-abcdef"), (True, "key-0002-abcdef")):
            raw = body(key=key)
            out = self.entry(self.event("/press/route", raw, dict(signed(raw, "route-a"), **{shops.SITE_HEADER: A}), b64=b64))
            self.assertEqual((out["statusCode"], json.loads(out["body"])["message"]["title"]), (200, "Route assigned"))
        raw = body()
        out = self.entry(self.event("/press/route", raw, dict(signed(raw, "route-b"), **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.tasks), 2)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
