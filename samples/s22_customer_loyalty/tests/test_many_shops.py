"""S22 serving many shops through the app template's handshake (tools/app_template/service/shops.py): each shop
connects itself, every press is checked with its own shop's secret and answered from its own records, and the feed
worker polls each connected shop with its own key and its own note. Two shops share a customer name on purpose."""

import base64
import datetime
import hashlib
import hmac
import importlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(SAMPLE, "service")]
import app  # noqa: E402
import loyalty  # noqa: E402
import shops  # noqa: E402  (the template's, through app.py's path)
import worker  # noqa: E402
import ed25519  # noqa: E402  (the template's)
from fake_shop import sale, shop  # noqa: E402

PAID = hashlib.sha256(b"s22 test L1").digest()
KEYS = {"L1": (base64.b64encode(ed25519.public_key(PAID)).decode(), frozenset({"paid"}))}
APP, A, B = "ivendnext_lyl", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
MEMBER = f"{APP}:{APP}_member"


def key(host, app_id=APP) -> str:
    pb = json.dumps({"typ": "applib-key", "v": 1, "kid": "L1", "id": "K7Q2M9XW4TPA", "app": app_id, "host": host,
                     "to": "customer:test", "kind": "paid", "iat": "2026-10-13", "exp": None}).encode()
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")  # noqa: E731
    return f"IVN1-{b(pb)}.{b(ed25519.sign(PAID, pb))}"


def connect(svc, site, secret, app_id=APP):
    body = {"key": key(site, app_id), "site": site,
            "secrets": {MEMBER: secret, "user:pp-lyl-service@x.example": f"k-{site}:s-{site}"}}
    return shops.handle(svc.store, svc.app, shops.CONNECT, {shops.SITE_HEADER: site}, json.dumps(body).encode(), KEYS)


def press(svc, site, secret, customer="C1"):
    raw = json.dumps({"app": APP, "key": f"{APP}_member", "context": {"customer": customer, "lines": []}}).encode()
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
    if site:
        h[shops.SITE_HEADER] = site
    return svc.press(h, raw)


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="s22-shops-")
        self.shops = {A: shop(), B: shop()}
        for site, total in ((A, "400.00"), (B, "1000.00")):         # the same customer name in both shops
            t = self.shops[site]
            sale(t, "S1", "C1", total)
            loyalty.on_sale(t, loyalty.Settings.load(t), "S1", "2026-10-01")
        conf = {"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": os.path.join(self.dir, "shops.json"), "PP_STATE": self.dir}
        self.svc = app.Service(conf, client=lambda record: self.shops[record["site"]])
        self.assertEqual(connect(self.svc, A, "secret-a"), (200, {"connected": A}))
        self.assertEqual(connect(self.svc, B, "secret-b"), (200, {"connected": B}))

    def test_each_shop_is_answered_from_its_own_records(self):
        code, a = press(self.svc, A, "secret-a")
        self.assertEqual(code, 200)
        self.assertIn("USD 8.00 pending", a["message"]["body"])            # 2% of A's 400
        code, b = press(self.svc, B, "secret-b")
        self.assertIn("USD 20.00 pending", b["message"]["body"])           # 2% of B's 1000
        self.assertNotIn("20.00", a["message"]["body"])

    def test_canary_b_cannot_call_as_a(self):
        self.assertEqual(press(self.svc, A, "secret-b")[0], 401)           # B's secret, A's site
        self.assertEqual(press(self.svc, B, "secret-a")[0], 401)

    def test_canary_an_unknown_site_and_no_site(self):
        self.assertEqual(press(self.svc, "shop-c.ivendnext.com", "secret-a")[0], 401)
        self.assertEqual(press(self.svc, None, "secret-a")[0], 401)

    def test_a_key_for_the_sample_name_is_not_this_apps(self):
        self.assertEqual(connect(self.svc, A, "x", app_id="pp_lyl"), (403, {"refused": "key_other_app"}))
        self.assertEqual(press(self.svc, A, "secret-a")[0], 200)            # the refused connect changed nothing

    def test_after_disconnect_a_press_is_refused(self):
        body = json.dumps({"key": key(A), "site": A}).encode()
        self.assertEqual(shops.handle(self.svc.store, APP, shops.DISCONNECT, {shops.SITE_HEADER: A}, body, KEYS)[0], 200)
        self.assertEqual(press(self.svc, A, "secret-a")[0], 401)
        self.assertEqual(press(self.svc, B, "secret-b")[0], 200)

    def test_no_customer_is_answered_without_reading_the_shop(self):
        svc = app.Service(self.svc.conf, client=lambda record: (_ for _ in ()).throw(AssertionError("read the shop")))
        code, ans = press(svc, A, "secret-a", customer="")
        self.assertEqual((code, ans["message"]["title"]), (200, "No member on this sale"))

    def test_member_cash_is_not_offered_to_many_shops(self):
        svc = app.Service(dict(self.svc.conf, PP_WALLET_SECRET="w" * 32), client=self.svc.client)
        self.assertEqual(svc.wallet_answer("preview", {}, b"{}")[0], 404)

    def test_the_handed_over_key_reaches_the_shops_api(self):
        record = self.svc.store.get(A)
        self.assertEqual(app.api_credentials(record), (f"https://{A}", f"k-{A}", f"s-{A}"))
        with self.assertRaises(app.ShopError):
            app.api_credentials(dict(record, secrets={MEMBER: "x"}))


class Worker(unittest.TestCase):
    class Feed:
        def __init__(self, events):
            self.q = list(events)

        def events(self, limit=100, page=None):
            return list(self.q), None, len(self.q)

        def done(self, ids):
            self.q = [e for e in self.q if e["id"] not in ids]
            return len(ids)

        def failed(self, id_, note):
            raise AssertionError(note)

        def backlog(self):
            return len(self.q)

    def test_one_poll_per_shop_with_its_own_key_note_and_records(self):
        state = tempfile.mkdtemp(prefix="s22-worker-")
        store = shops.FileStore(os.path.join(state, "shops.json"))
        fakes, feeds = {A: shop(), B: shop()}, {}
        for site, total in ((A, "400.00"), (B, "1000.00")):
            sale(fakes[site], "S1", "C1", total)
            feeds[site] = self.Feed([{"id": "e1", "event": "sale.booked", "doc_type": "POS Invoice", "doc_name": "S1"}])
            store.put(site, {"site": site, "url": f"https://{site}", "secrets": {"user:u": "k:s"}})
        store.put("shop-x.ivendnext.com", {"site": "shop-x.ivendnext.com", "url": "https://x", "secrets": {}})   # no key
        last, log = {}, io.StringIO()
        now = datetime.datetime(2026, 10, 13, 3, 0, tzinfo=datetime.timezone.utc)
        out = worker.pass_all(store, state, last, now=now, log=log,
                              opener=lambda r: (fakes[r["site"]], feeds[r["site"]]) if r["site"] in fakes
                              else (_ for _ in ()).throw(app.ShopError(0, "no key")))
        for site, total in ((A, "8.00"), (B, "20.00")):
            earn = [r for r in fakes[site].db[loyalty.LEDGER].values() if r["entry_type"] == "Earn"]
            self.assertEqual([str(r["amount"]) for r in earn], [total])
            self.assertEqual(feeds[site].backlog(), 0)
        self.assertEqual(out["shop-x.ivendnext.com"], {"error": "ShopError"})       # the others went on
        self.assertEqual(len({worker.shop_state(state, s) for s in (A, B)}), 2)       # two notes, never one
        self.assertEqual(last, {A: "2026-10-13", B: "2026-10-13"})
        self.assertNotIn("k:s", log.getvalue())
        again = worker.pass_all(store, state, last, now=now, log=log, opener=lambda r: (fakes[r["site"]], self.Feed([])))
        self.assertNotIn("credited", again[A])                                    # the daily jobs once a day

    def test_a_daily_job_that_fails_is_not_rerun_on_every_pass(self):
        state = tempfile.mkdtemp(prefix="s22-daily-")
        store = shops.FileStore(os.path.join(state, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {"user:u": "k:s"}})
        fake, calls = shop(), []

        def broken(t, s, today):
            calls.append(today)
            raise app.ShopError(417, "a customer the shop will not save")

        real, loyalty.evaluate_tiers = loyalty.evaluate_tiers, broken
        self.addCleanup(setattr, loyalty, "evaluate_tiers", real)
        last, now, log = {}, datetime.datetime(2026, 10, 13, 3, 0, tzinfo=datetime.timezone.utc), io.StringIO()
        for _ in range(3):
            out = worker.pass_all(store, state, last, now=now, log=log, opener=lambda r: (fake, self.Feed([])))
        self.assertEqual(json.loads(log.getvalue().splitlines()[0]), {"site": A, "error": "ShopError"})   # logged by class
        self.assertEqual(calls, ["2026-10-13"])                                  # tried once that day, logged, not rerun
        self.assertNotIn("error", out[A])                                         # later passes serve the feed
        worker.pass_all(store, state, last, now=now + datetime.timedelta(days=1), log=io.StringIO(),
                        opener=lambda r: (fake, self.Feed([])))
        self.assertEqual(calls, ["2026-10-13", "2026-10-14"])                    # and tried again the next day

    def test_a_refused_customer_is_counted_in_the_log_never_named(self):
        state = tempfile.mkdtemp(prefix="s22-refused-")
        store = shops.FileStore(os.path.join(state, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {"user:u": "k:s"}})
        real, loyalty.evaluate_tiers = loyalty.evaluate_tiers, lambda t, s, today: [{"customer": "Ann Lee", "refused": 417}]
        self.addCleanup(setattr, loyalty, "evaluate_tiers", real)
        log = io.StringIO()
        worker.pass_all(store, state, {}, now=datetime.datetime(2026, 10, 13, 3, 0, tzinfo=datetime.timezone.utc),
                        log=log, opener=lambda r: (shop(), self.Feed([])))
        line = json.loads(log.getvalue().splitlines()[0])
        self.assertEqual(line["moved"], "1 customer(s) refused (417)")
        self.assertNotIn("Ann Lee", log.getvalue())


    def test_a_stuck_shop_never_holds_up_another_and_is_not_run_twice(self):
        state = tempfile.mkdtemp(prefix="s22-stuck-")
        store = shops.FileStore(os.path.join(state, "shops.json"))
        for site in (A, B):
            store.put(site, {"site": site, "url": f"https://{site}", "secrets": {"user:u": "k:s"}})
        release, fake_b = threading.Event(), shop()

        class Stuck(self.Feed):
            def events(self, limit=100, page=None):
                release.wait(10)                                           # a shop that drips its answer
                return [], None, 0

        opener = lambda r: (shop(), Stuck([])) if r["site"] == A else (fake_b, self.Feed([]))   # noqa: E731
        busy, now = {}, datetime.datetime(2026, 10, 13, 1, 0, tzinfo=datetime.timezone.utc)
        t0 = time.monotonic()
        out = worker.pass_all(store, state, {}, now=now, log=io.StringIO(), opener=opener, busy=busy, deadline=0.5)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertIn("feed", out[B])                                     # B was served while A hung
        self.assertNotIn(A, out)
        again = worker.pass_all(store, state, {}, now=now, log=io.StringIO(), opener=opener, busy=busy, deadline=0.5)
        self.assertEqual(again[A], {"busy": True})                        # never two passes at once for one shop
        release.set()

    def test_a_shops_store_that_does_not_answer_ends_the_pass_never_the_worker(self):
        class Down:
            def sites(self):
                raise ConnectionError("Scan answered 500")
        log = io.StringIO()
        self.assertEqual(worker.pass_all(Down(), tempfile.mkdtemp(), {}, log=log), {})
        self.assertIn("ConnectionError", log.getvalue())


class Health(unittest.TestCase):
    def test_health_is_503_once_the_feed_worker_stalls(self):
        conf = {"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": os.path.join(tempfile.mkdtemp(), "s.json")}
        svc = app.Service(conf)
        srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(svc))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_port}/health"

        def health():
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                with e:
                    return e.code

        self.assertEqual(health(), 200)                                   # just started: the grace period
        svc.started -= app.HEALTH_GRACE_S + 1
        worker.HEARTBEAT[0] = time.monotonic() - app.HEALTH_GRACE_S - 1
        self.assertEqual(health(), 503)
        worker.HEARTBEAT[0] = time.monotonic()
        self.assertEqual(health(), 200)


class Prefix(unittest.TestCase):
    def test_the_librarys_app_reads_its_own_record_types(self):
        try:
            app.use_prefix("IVENDNEXT LYL")
            self.assertEqual((loyalty.LEDGER, app.wallet.LEDGER, app.receipts.VERIFIED, loyalty.BALANCE),
                             ("IVENDNEXT LYL Ledger", "IVENDNEXT LYL Ledger", "IVENDNEXT LYL Verified", "IVENDNEXT LYL Balance"))
        finally:
            app.use_prefix("PP LYL")
        self.assertEqual((loyalty.MEMBER, loyalty.BALANCE), ("PP LYL Member", "PP LYL Balance"))

    def test_every_record_type_name_follows_the_prefix(self):
        """A census, not a list: under another prefix no module constant still names the sample's own record types.
        Bound: it reads module-level constants only, not a name written inline in a function or built by an f-string."""
        try:
            app.use_prefix("X")
            left = [f"{mod.__name__}.{k}" for mod in (loyalty, app.receipts, app.wallet, app, importlib.import_module("settings_sync"))
                    for k, v in vars(mod).items()
                    if isinstance(v, str) and v.startswith("PP LYL ")]
        finally:
            app.use_prefix("PP LYL")
        self.assertEqual(left, [])


if __name__ == "__main__":
    unittest.main()
