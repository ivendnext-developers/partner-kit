"""S3's service, one shop and many: each sale judged at the shop's own threshold, each deviation written once under the
names the prefix gives, each connected shop served with its own key, and the App library's handshake.

    python3 -m unittest discover -s samples/s3_price_audit/tests -p 'test_*.py'
"""

import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path[:0] = [os.path.join(SAMPLE, "outside")]
import app  # noqa: E402
import feed_client as F  # noqa: E402
import service  # noqa: E402
import worker  # noqa: E402
import ed25519  # noqa: E402  (the template's, put on the path by app.py)
import shops  # noqa: E402


class FakeShop:
    """The record API as the service calls it: ``call(method, path, params, body)``; refusals as the shop gives them."""

    def __init__(self, threshold=None, settings_status=None, write_status=None, installed=None):
        self.sales, self.db, self.calls, self.installed = {}, {}, [], installed   # installed: the prefix the shop has
        self.threshold, self.settings_status, self.write_status = threshold, settings_status, write_status

    def sale(self, name, lines, doc_type="POS Invoice", **over):
        self.sales[(doc_type, name)] = {"name": name, "docstatus": 1, "is_return": 0, "is_consolidated": 0,
                                        "posting_date": "2026-10-18", "pos_profile": "Store 1",
                                        "items": [{"name": f"{name}-{i}", "item_code": c, "qty": 1, "price_list_rate": plr,
                                                   "rate": rate, "pricing_rules": ""} for i, (c, plr, rate) in enumerate(lines)],
                                        **over}

    def call(self, method, path, params=None, body=None):
        self.calls.append((method, path))
        parts = [urllib.parse.unquote(p) for p in path.split("/")[3:]]
        dt = parts[0]
        if method == "GET" and dt.endswith(" Settings"):
            if self.settings_status:
                raise F.FeedError(str(self.settings_status) if " " in str(self.settings_status) else f"{self.settings_status} refused")
            if dt != (f"{self.installed} Settings" if self.installed else service.SETTINGS):   # a type it does not have
                raise F.FeedError(f"500 Module import failed for {dt}")
            if self.threshold is None:
                raise F.FeedError(f"404 {dt} Default not found")
            return {"data": {"name": "Default", "threshold_percent": self.threshold}}
        if method == "GET":
            if (dt, parts[1]) not in self.sales:
                raise F.FeedError(f"404 {dt} {parts[1]} not found")
            return {"data": self.sales[(dt, parts[1])]}
        if method == "POST":
            if self.write_status:
                raise F.FeedError(f"{self.write_status} refused")
            if dt != (f"{self.installed} Deviation" if self.installed else service.DT):
                raise F.FeedError(f"500 Module import failed for {dt}")
            if body["line_key"] in self.db.setdefault(dt, {}):
                raise F.FeedError("409 Duplicate entry")
            self.db[dt][body["line_key"]] = body
            return {"data": body}
        raise AssertionError(path)

    def settings_reads(self):
        return [c for c in self.calls if c[1].endswith("/Default")]


class FakeFeed:
    def __init__(self, events):
        self.events_, self.marked, self.failed_ = list(events), [], []

    def events(self, limit, page):
        left = [e for e in self.events_ if e["id"] not in self.marked]
        return left[:limit], None, None

    def backlog(self):
        return len([e for e in self.events_ if e["id"] not in self.marked])

    def done(self, ids):
        self.marked += ids
        return len(ids)

    def failed(self, i, note):
        self.failed_.append((i, note))


class Seen:
    def __init__(self):
        self.ids = set()

    def seen(self, i):
        return i in self.ids

    def handled(self, ev, fn):
        fn(None)
        self.ids.add(ev["id"])


def manifest():
    with open(os.path.join(SAMPLE, "outside", "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def ev(i, name, event="sale.booked", doc_type="POS Invoice"):
    return {"id": i, "event": event, "doc_name": name, "doc_type": doc_type}


CASE, CHARGER, CABLE = ("CASE", 1299.0, 1039.2), ("CHARGER", 100.0, 97.0), ("CABLE", 20.0, 20.0)   # 20 %, 3 %, 0 % below


def recorded(t, dt=None):
    return sorted((dt or service.DT) in t.db and t.db[dt or service.DT] or {})


class Threshold(unittest.TestCase):
    def test_each_shop_is_judged_at_its_own_threshold(self):
        a, b = FakeShop(threshold=10), FakeShop(threshold=2)
        for t in (a, b):
            t.sale("S1", [CASE, CHARGER, CABLE])
            worker.one_pass(t, FakeFeed([ev(1, "S1")]), Seen())
        self.assertEqual(recorded(a), ["S1-0"])
        self.assertEqual(recorded(b), ["S1-0", "S1-1"])
        self.assertEqual(b.db[service.DT]["S1-1"]["threshold_percent"], 2.0)

    def test_a_shop_with_no_settings_record_is_judged_at_10(self):
        t = FakeShop(threshold=None)
        t.sale("S1", [CASE, ("CHARGER", 100.0, 89.0)])                      # 20 % and 11 %
        worker.one_pass(t, FakeFeed([ev(1, "S1")]), Seen())
        self.assertEqual(recorded(t), ["S1-0", "S1-1"])
        self.assertEqual(t.db[service.DT]["S1-0"]["threshold_percent"], 10.0)

    def test_a_refused_settings_read_leaves_the_sale_not_done_and_writes_nothing(self):
        t = FakeShop(threshold=10, settings_status=403)
        t.sale("S1", [CASE])
        feed = FakeFeed([ev(1, "S1")])
        out = worker.one_pass(t, feed, Seen())
        self.assertEqual((out["feed"]["failed"], feed.marked, recorded(t)), (1, [], []))
        self.assertIn("403", feed.failed_[0][1])
        t.settings_status = None                                           # the shop gives the right: the next pass judges it
        worker.one_pass(t, feed, Seen())
        self.assertEqual((feed.marked, recorded(t)), ([1], ["S1-0"]))

    def test_a_translated_no_record_answer_still_falls_back_to_10(self):
        t = FakeShop(threshold=10, settings_status="404 IVENDNEXT PDA Settings Default no encontrado #")
        t.sale("S1", [CASE, ("CHARGER", 100.0, 89.0)])
        worker.one_pass(t, FakeFeed([ev(1, "S1")]), Seen())
        self.assertEqual(recorded(t), ["S1-0", "S1-1"])

    def test_only_the_records_own_404_falls_back_to_10(self):
        t = FakeShop(threshold=10, settings_status=404)                  # a 404 that does not name the record
        t.sale("S1", [CASE])
        feed = FakeFeed([ev(1, "S1")])
        worker.one_pass(t, feed, Seen())
        self.assertEqual((feed.marked, recorded(t)), ([], []))

    def test_a_missing_settings_record_type_is_never_judged_at_10(self):
        t = FakeShop(threshold=None, installed="IVENDNEXT PDA")
        t.sale("S1", [CASE])
        feed = FakeFeed([ev(1, "S1")])
        service.use_prefix("IVENDNEXT PDO")                              # a prefix the shop never installed
        try:
            worker.one_pass(t, feed, Seen())
        finally:
            service.use_prefix("PP PDO")
        self.assertEqual((feed.marked, recorded(t, "IVENDNEXT PDO Deviation")), ([], []))
        self.assertIn("500", feed.failed_[0][1])

    def test_the_threshold_is_read_once_a_pass_and_only_when_a_sale_is_judged(self):
        t = FakeShop(threshold=10)
        t.sale("S1", [CASE])
        t.sale("S2", [CASE])
        worker.one_pass(t, FakeFeed([ev(1, "C9", "customer.created", "Customer")]), Seen())
        self.assertEqual(t.settings_reads(), [])
        worker.one_pass(t, FakeFeed([ev(2, "S1"), ev(3, "S2")]), Seen())
        self.assertEqual(len(t.settings_reads()), 1)
        t.threshold = 50                                                   # a change applies on the next pass
        t.sale("S3", [CASE])
        worker.one_pass(t, FakeFeed([ev(4, "S3")]), Seen())
        self.assertEqual(recorded(t), ["S1-0", "S2-0"])


class Writes(unittest.TestCase):
    def test_a_second_delivery_writes_nothing_and_the_event_is_done(self):
        t = FakeShop(threshold=10)
        t.sale("S1", [CASE])
        worker.one_pass(t, FakeFeed([ev(1, "S1")]), Seen())
        feed = FakeFeed([ev(2, "S1")])                                     # the note was lost: the shop refuses the second
        out = worker.one_pass(t, feed, Seen())
        self.assertEqual((out["feed"]["failed"], feed.marked, recorded(t)), (0, [2], ["S1-0"]))

    def test_a_write_the_shop_refuses_leaves_the_event_not_done(self):
        t = FakeShop(threshold=10, write_status=403)
        t.sale("S1", [CASE])
        feed = FakeFeed([ev(1, "S1")])
        out = worker.one_pass(t, feed, Seen())
        self.assertEqual((out["feed"]["failed"], feed.marked), (1, []))

    def test_an_exchange_is_judged_for_what_it_sells_and_a_line_handed_back_never(self):
        t = FakeShop(threshold=10)
        t.sale("X1", [("OLD", 100.0, 50.0), CASE], is_return=1)
        t.sales[("POS Invoice", "X1")]["items"][0]["qty"] = -1           # handed back at half its list price
        t.sale("S1", [("BACK", 100.0, 50.0), CHARGER])
        t.sales[("POS Invoice", "S1")]["items"][0]["qty"] = -1           # an item handed back inside a sale
        worker.one_pass(t, FakeFeed([ev(1, "X1", "return.booked"), ev(2, "S1")]), Seen())
        self.assertEqual(recorded(t), ["X1-1"])

    def test_a_price_the_key_cannot_read_fails_the_sale_never_reads_0(self):
        t = FakeShop(threshold=10)
        t.sale("S1", [CASE])
        del t.sales[("POS Invoice", "S1")]["items"][0]["rate"]            # a field above the role's permission level
        t.sale("S2", [CASE])
        del t.sales[("POS Invoice", "S2")]["items"][0]["qty"]             # a quantity it cannot read is not "nothing sold"
        feed = FakeFeed([ev(1, "S1"), ev(2, "S2")])
        out = worker.one_pass(t, feed, Seen())
        self.assertEqual((out["feed"]["failed"], feed.marked), (2, []))
        self.assertTrue(all("not readable" in n for _, n in feed.failed_))

    def test_a_sale_deleted_before_it_is_read_never_blocks_the_feed(self):
        t = FakeShop(threshold=10)
        feed = FakeFeed([ev(1, "GONE-1")])
        out = worker.one_pass(t, feed, Seen())
        self.assertEqual((out["feed"]["failed"], feed.marked), (0, [1]))

    def test_a_return_a_roll_up_and_a_draft_are_not_judged(self):
        t = FakeShop(threshold=10)
        t.sale("R1", [CASE], is_return=1)
        t.sales[("POS Invoice", "R1")]["items"][0]["qty"] = -1
        t.sale("C1", [CASE], doc_type="Sales Invoice", is_consolidated=1)
        t.sale("D1", [CASE], docstatus=0)
        t.sale("I1", [CASE], doc_type="Sales Invoice")
        worker.one_pass(t, FakeFeed([ev(1, "R1", "return.booked"), ev(2, "C1", "invoice.booked", "Sales Invoice"), ev(3, "D1"),
                                     ev(4, "I1", "invoice.booked", "Sales Invoice")]), Seen())
        self.assertEqual(recorded(t), ["I1-0"])
        self.assertEqual(t.db[service.DT]["I1-0"]["invoice_doctype"], "Sales Invoice")


class Prefix(unittest.TestCase):
    def tearDown(self):
        service.use_prefix("PP PDO")

    def test_the_librarys_app_reads_and_writes_its_own_record_types(self):
        with tempfile.TemporaryDirectory() as d:
            app.Service({"IVN_LIBRARY_APP": "ivendnext_pda", "PDO_PREFIX": "IVENDNEXT PDA", "PP_STATE": d},
                        store=shops.FileStore(os.devnull))
        self.assertEqual((service.DT, service.SETTINGS), ("IVENDNEXT PDA Deviation", "IVENDNEXT PDA Settings"))
        t = FakeShop(threshold=2)
        t.sale("S1", [CASE, CHARGER])
        worker.one_pass(t, FakeFeed([ev(1, "S1")]), Seen())
        self.assertEqual(recorded(t, "IVENDNEXT PDA Deviation"), ["S1-0", "S1-1"])
        self.assertTrue(any(p.endswith("IVENDNEXT%20PDA%20Settings/Default") for _, p in t.settings_reads()))

    def test_every_record_type_name_follows_the_prefix(self):
        """A census, not a list: under another prefix no module constant still names a sample record type (S22's, kit #127).
        The sample's code is PDO and the library's is PDA, so a name the prefix missed is written to a record type the
        library never installs: every write fails."""
        service.use_prefix("IVENDNEXT PDA")
        left = [(m.__name__, k) for m in (service, worker, app) for k, v in vars(m).items()
                if isinstance(v, str) and v.startswith("PP PDO ")]
        self.assertEqual(left, [])
        self.assertEqual(sorted(d["name"] for d in manifest()["doctypes"]),
                         sorted(n.replace("IVENDNEXT PDA", "PP PDO") for n in (service.DT, service.SETTINGS)))


class ManyShops(unittest.TestCase):
    def test_each_shop_is_served_with_its_own_key_and_one_without_a_user_stops_none(self):
        shop_a, shop_b = FakeShop(threshold=10), FakeShop(threshold=10)
        shop_a.sale("S1", [CASE])
        shop_b.sale("S1", [CHARGER])
        by_key = {"ka": (shop_a, FakeFeed([ev(1, "S1")])), "kb": (shop_b, FakeFeed([ev(1, "S1")]))}
        records = {"a.example": {"url": "https://a.example", "secrets": {"user:pda@a.example": "ka:sa", "ivendnext_pda:x": "y"}},
                   "b.example": {"url": "https://b.example", "secrets": {"user:pda@b.example": "kb:sb"}},
                   "c.example": {"url": "https://c.example", "secrets": {"ivendnext_pda:x": "y"}},
                   "d.example": {"url": "https://d.example", "secrets": {"user:pda@d.example": "kd:sd"}},
                   "e.example": {"url": "https://e.example", "secrets": {"user:pda@e.example": "ke:se"}}}

        class Store:
            def sites(self):
                return sorted(records)

            def get(self, site):
                return records[site]

        seen_urls = []

        def opener(record):
            base, key, secret = worker.api_credentials(record)
            seen_urls.append((base, key))
            if key == "kd":
                raise RuntimeError("the shop did not answer")
            if key == "ke":
                raise F.FeedError("403 Not permitted")
            return by_key[key]

        log = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            out = worker.pass_all(Store(), d, log=log, opener=opener)
        self.assertEqual(out["a.example"]["handled"], 1)
        self.assertEqual(out["b.example"]["handled"], 1)
        self.assertEqual(out["c.example"], {"error": "no_user"})
        self.assertEqual(out["d.example"], {"error": "RuntimeError"})
        self.assertEqual(out["e.example"], {"error": "FeedError 403"})
        self.assertEqual((recorded(shop_a), recorded(shop_b)), (["S1-0"], []))   # B's charger is 3 % below: not recorded
        self.assertEqual(sorted(seen_urls), [("https://a.example", "ka"), ("https://b.example", "kb"), ("https://d.example", "kd"), ("https://e.example", "ke")])
        lines = [json.loads(x) for x in log.getvalue().splitlines()]
        self.assertEqual({x["site"] for x in lines}, set(records))
        self.assertNotIn("sa", log.getvalue())
        self.assertNotIn("pda@", log.getvalue())

    def test_a_shop_gone_during_the_pass_is_logged_as_gone(self):
        class Store:
            def sites(self):
                return ["a.example"]

            def get(self, site):
                return None
        log = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            out = worker.pass_all(Store(), d, log=log)
        self.assertEqual(out["a.example"], {"error": "gone"})
        self.assertEqual(json.loads(log.getvalue()), {"site": "a.example", "error": "gone"})

    def test_a_shops_store_that_does_not_answer_is_not_a_healthy_pass(self):
        class Broken:
            def sites(self):
                raise RuntimeError("table unreachable")
        self.assertIsNone(worker.pass_all(Broken(), "/tmp", log=io.StringIO()))
        self.assertEqual([worker.healthy_pass(x) for x in (None, {}, {"a": {"busy": True, "stuck": True}})], [False, True, False])

    def test_a_shop_busy_past_the_limit_is_stuck_and_never_run_twice(self):
        gate, calls = threading.Event(), []

        class Store:
            def sites(self):
                return ["a.example"]

            def get(self, site):
                return {"url": "https://a.example"}

        def opener(record):
            calls.append(1)
            gate.wait(5)
            raise RuntimeError("released")
        busy = {}
        with tempfile.TemporaryDirectory() as d:
            worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            out = worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            self.assertEqual((out["a.example"], len(calls)), ({"busy": True, "stuck": False}, 1))
            th, since = busy["a.example"]
            busy["a.example"] = (th, since - worker.STUCK_S - 1)
            worker.PROGRESS.pop("a.example", None)
            out = worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            self.assertEqual(out["a.example"], {"busy": True, "stuck": True})
            gate.set()
            th.join(5)


PAID_SECRET = hashlib.sha256(b"test L1").digest()
KEYS = {"L1": (base64.b64encode(ed25519.public_key(PAID_SECRET)).decode(), frozenset({"paid"}))}


def make_key(host, app_id="ivendnext_pda"):
    payload = {"typ": "applib-key", "v": 1, "kid": "L1", "id": "K7Q2M9XW4TPA", "app": app_id, "host": host,
               "to": "customer:test", "kind": "paid", "iat": "2026-10-18", "exp": None}
    pb = json.dumps(payload, separators=(",", ":")).encode()
    b64u = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")   # noqa: E731
    return f"IVN1-{b64u(pb)}.{b64u(ed25519.sign(PAID_SECRET, pb))}"


class Service(unittest.TestCase):
    def serve(self, svc):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(svc))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}"

    def post(self, url, body, site):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"X-iVendNext-Site": site})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def code(self, url):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def svc(self, d):
        self.addCleanup(service.use_prefix, "PP PDO")
        return app.Service({"IVN_LIBRARY_APP": "ivendnext_pda", "PDO_PREFIX": "IVENDNEXT PDA", "PP_STATE": d},
                           store=shops.FileStore(os.path.join(d, "shops.json")), keys=KEYS)

    def test_a_shop_connects_with_its_own_key_and_the_goodbye_forgets_it(self):
        with tempfile.TemporaryDirectory() as d:
            svc = self.svc(d)
            base, a, b = self.serve(svc), "shop-a.ivendnext.com", "shop-b.ivendnext.com"
            secrets = {"user:pda@shop-a.example": "k:s"}
            self.assertEqual(self.post(base + shops.CONNECT, {"key": make_key(a), "site": a, "secrets": secrets}, a)[0], 200)
            self.assertEqual(svc.store.sites(), [a])
            self.assertEqual(self.post(base + shops.CONNECT, {"key": make_key(a), "site": b, "secrets": secrets}, b),
                             (403, {"refused": "key_other_site"}))
            self.assertEqual(self.post(base + shops.CONNECT, {"key": make_key(a, "ivendnext_gcs"), "site": a,
                                                              "secrets": secrets}, a), (403, {"refused": "key_other_app"}))
            self.assertEqual(self.post(base + shops.DISCONNECT, {"key": make_key(b), "site": a}, a),
                             (403, {"refused": "key_other_site"}))
            self.assertEqual(svc.store.sites(), [a])
            self.assertEqual(self.post(base + shops.DISCONNECT, {"key": make_key(a), "site": a}, a)[0], 200)
            self.assertEqual(svc.store.sites(), [])

    def test_health_is_503_once_the_worker_stalls_and_nothing_else_is_answered(self):
        with tempfile.TemporaryDirectory() as d:
            svc = self.svc(d)
            base = self.serve(svc)
            self.assertEqual(self.code(base + "/health"), 200)                 # just started: the grace
            svc.started -= app.HEALTH_GRACE_S + 1
            worker.HEARTBEAT[0] = time.monotonic() - app.HEALTH_GRACE_S - 1
            self.assertEqual(self.code(base + "/health"), 503)
            worker.HEARTBEAT[0] = time.monotonic()
            self.assertEqual(self.code(base + "/health"), 200)
            self.assertEqual(self.code(base + "/anything"), 404)

    def test_without_the_librarys_id_or_a_writable_notes_folder_it_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            app.Service({})
        with tempfile.TemporaryDirectory() as d:
            ro = os.path.join(d, "ro")
            os.mkdir(ro, 0o500)
            try:
                with self.assertRaises(SystemExit) as e:
                    app.Service({"IVN_LIBRARY_APP": "ivendnext_pda", "PP_STATE": os.path.join(ro, "s3")},
                                store=shops.FileStore(os.devnull))
            finally:
                os.chmod(ro, 0o700)
            self.assertIn("not writable", str(e.exception))


class Manifest(unittest.TestCase):
    def setUp(self):
        self.m = manifest()

    def rights(self, dt, role):
        d = next(x for x in self.m["doctypes"] if x["name"] == dt)
        return {k for k, v in next(p for p in d["permissions"] if p["role"] == role).items() if v == 1}

    def test_the_services_role_reads_the_settings_and_creates_deviations_only(self):
        self.assertEqual(self.rights("PP PDO Deviation", "PP PDO Integration"), {"read", "create"})
        self.assertEqual(self.rights("PP PDO Settings", "PP PDO Integration"), {"read"})

    def test_a_deviation_is_named_by_its_sale_line_so_the_shop_refuses_a_second(self):
        d = next(x for x in self.m["doctypes"] if x["name"] == "PP PDO Deviation")
        self.assertEqual(d["autoname"], "field:line_key")

    def test_the_shop_calls_nothing_outside_and_names_the_one_service_its_site_connects(self):
        self.assertEqual(self.m["allowed_urls"], ["https://pdo.partner.example"])
        for k in ("webhooks", "remote_actions", "extension_subscriptions", "pos_actions"):
            self.assertFalse(self.m.get(k), k)



class Scheduled(unittest.TestCase):
    """PAYWHENUSED: hosted as a function on a schedule. Each call is one pass of the shops it claims; a shop another call
    holds is left to it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="s3-fn-")
        conf = {"IVN_LIBRARY_APP": "ivendnext_pda", "IVN_SHOPS_FILE": os.path.join(self.dir, "shops.json"),
                "PP_STATE": self.dir}
        self.svc = app.Service(conf, scheduled=True)
        self.shops = {"ka": FakeShop(threshold=10), "kb": FakeShop(threshold=10)}
        self.feeds = {k: FakeFeed([ev(1, "S1")]) for k in self.shops}
        for k, t in self.shops.items():
            t.sale("S1", [CASE])
            site = f"{k[1]}.example"
            self.svc.store.put(site, {"url": f"https://{site}", "secrets": {f"user:pda@{site}": f"{k}:s"}})

    def run_pass(self):
        def opener(record):
            key = worker.api_credentials(record)[1]
            return self.shops[key], self.feeds[key]
        with mock.patch.object(worker, "open_shop", opener), mock.patch("sys.stdout", io.StringIO()):
            return app.scheduled(self.svc, "pass")

    def claims(self):
        with open(os.path.join(self.dir, "shops.json")) as f:
            return sorted(n for n in json.load(f) if "|" in n)

    def test_a_call_passes_each_claimed_shop_and_frees_its_claim(self):
        out = self.run_pass()
        self.assertEqual((out["a.example"]["handled"], out["b.example"]["handled"]), (1, 1))
        self.assertEqual((recorded(self.shops["ka"]), recorded(self.shops["kb"])), (["S1-0"], ["S1-0"]))
        self.assertEqual(self.claims(), [])

    def test_canary_a_shop_another_call_holds_is_left_to_it(self):
        self.assertTrue(self.svc.store.claim("pass|a.example", time.time() + 1000, 1000))
        self.assertEqual(sorted(self.run_pass()), ["b.example"])
        self.assertEqual(recorded(self.shops["ka"]), [])
        self.assertEqual(self.claims(), ["pass|a.example"])

    def test_a_shop_that_finished_is_freed_while_a_slow_one_still_works(self):
        seen_free = []

        def opener(record):
            key = worker.api_credentials(record)[1]
            if key == "ka":                                  # A is slow: it waits for B's claim to be freed
                end = time.monotonic() + 3
                while time.monotonic() < end and "pass|b.example" in self.claims():
                    time.sleep(0.02)
                seen_free.append("pass|b.example" not in self.claims())
            return self.shops[key], self.feeds[key]

        with mock.patch.object(worker, "open_shop", opener), mock.patch("sys.stdout", io.StringIO()):
            app.scheduled(self.svc, "pass")
        self.assertEqual(seen_free, [True])
        self.assertEqual(self.claims(), [])

    def test_health_answers_200_as_a_function(self):
        self.svc.started -= app.HEALTH_GRACE_S + 1
        worker.HEARTBEAT[0] = time.monotonic() - app.HEALTH_GRACE_S - 1      # stale, whatever the machine's uptime
        self.assertEqual(app.handle(self.svc, "GET", "/health", {}, b""), (200, {"ok": 1}))


if __name__ == "__main__":
    unittest.main()
