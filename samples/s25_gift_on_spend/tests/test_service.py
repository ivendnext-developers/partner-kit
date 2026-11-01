"""S25's worker and service: the feed's three events reach their rules and nothing else does, a pass runs the feed before
the releases, each connected shop is served with its own key, and /health tells the platform when the worker stalls.

    python3 -m unittest discover -s samples/s25_gift_on_spend/tests -p 'test_*.py'
"""

import datetime as dt
import http.client
import io
import json
import os
import sys
import threading
import time
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "service"))
import app  # noqa: E402
import cards  # noqa: E402
import worker  # noqa: E402
from fake_shop import sale, shop  # noqa: E402

T0 = dt.datetime(2026, 10, 15, 8, 0, tzinfo=dt.timezone.utc)


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


def ev(i, event, name, doc_type="POS Invoice"):
    return {"id": i, "event": event, "doc_name": name, "doc_type": doc_type}


class Worker(unittest.TestCase):
    def test_the_three_events_reach_their_rules_and_others_are_done_unread(self):
        t = shop()
        sale(t, "S1")
        sale(t, "S2", grand_total=5)
        feed = FakeFeed([ev(1, "sale.booked", "S1"), ev(2, "sale.booked", "S2"), ev(3, "customer.created", "C9", "Customer")])
        out = worker.one_pass(t, feed, Seen(), clock=lambda: T0)
        self.assertEqual((out["feed"]["handled"], out["feed"]["done"]), (3, 3))
        self.assertEqual(sorted(t.db["PP GCS Card"]), ["S1:1"])

    def test_a_pass_runs_the_feed_before_the_releases(self):
        t = shop()
        sale(t, "S1")
        worker.one_pass(t, FakeFeed([ev(1, "sale.booked", "S1")]), Seen(), clock=lambda: T0)
        sale(t, "S1", docstatus=2)
        later = T0 + dt.timedelta(hours=30)          # the hold has passed AND the cancel is waiting in the feed
        out = worker.one_pass(t, FakeFeed([ev(2, "sale.cancelled", "S1")]), Seen(), clock=lambda: later)
        self.assertEqual(out["released"], [])
        self.assertEqual(t.card("S1:1")["status"], "Voided")
        self.assertNotIn("Gift Card Balance", t.db)

    def test_a_return_event_reaches_the_return_rule(self):
        t = shop()
        sale(t, "S1")
        worker.one_pass(t, FakeFeed([ev(1, "sale.booked", "S1")]), Seen(), clock=lambda: T0)
        sale(t, "R1", grand_total=-1200, is_return=1, return_against="S1")
        worker.one_pass(t, FakeFeed([ev(2, "return.booked", "R1")]), Seen(), clock=lambda: T0)
        self.assertEqual(t.card("S1:1")["status"], "Voided")

    def test_a_failing_event_stays_undone_for_the_next_pass(self):
        t = shop()
        feed = FakeFeed([ev(1, "sale.booked", "S1")])
        t.fail_after_insert = "PP GCS Card"
        sale(t, "S1")
        with self.assertRaises(SystemExit):              # a crash, not a refusal: the feed is never marked
            worker.one_pass(t, feed, Seen(), clock=lambda: T0)
        self.assertEqual(feed.marked, [])
        worker.one_pass(t, feed, Seen(), clock=lambda: T0)
        self.assertEqual((feed.marked, t.card("S1:1")["status"]), ([1], "Held"))


class Store:
    def __init__(self, records):
        self.records = records

    def sites(self):
        return list(self.records)

    def get(self, site):
        return self.records.get(site)


class ManyShops(unittest.TestCase):
    def test_each_shop_is_served_with_its_own_key_and_records_and_one_failure_stops_none(self):
        shops_ = {"a.example": shop(), "b.example": shop()}
        sale(shops_["a.example"], "SA")
        sale(shops_["b.example"], "SB", grand_total=2000)
        feeds = {"a.example": FakeFeed([ev(1, "sale.booked", "SA")]), "b.example": FakeFeed([ev(1, "sale.booked", "SB")])}
        opened = []

        def opener(record):
            opened.append(app.api_credentials(record))
            if record["url"] == "https://c.example":
                raise RuntimeError("down")
            return shops_[record["url"][8:]], feeds[record["url"][8:]]

        recs = {s: {"url": f"https://{s}", "secrets": {"user:gcs@x": f"k-{s}:s-{s}"}} for s in ("a.example", "b.example", "c.example")}
        with self.subTest("pass"), __import__("tempfile").TemporaryDirectory() as d:
            out = worker.pass_all(Store(recs), d, log=io.StringIO(), opener=opener, clock=lambda: T0)
        self.assertEqual(out["c.example"], {"error": "RuntimeError"})
        self.assertEqual(sorted(shops_["a.example"].db["PP GCS Card"]), ["SA:1"])
        self.assertEqual(sorted(shops_["b.example"].db["PP GCS Card"]), ["SB:1"])
        self.assertEqual(sorted(k for _, k, _ in opened), ["k-a.example", "k-b.example", "k-c.example"])

    def test_a_shop_that_handed_over_no_key_is_refused(self):
        with self.assertRaises(Exception):
            app.api_credentials({"url": "https://a.example", "secrets": {"ivendnext_gcs:x": "y"}})


class HealthyPass(unittest.TestCase):
    def test_a_release_backlog_counts_as_progress(self):
        t = shop()
        sale(t, "S1")
        worker.one_pass(t, FakeFeed([ev(1, "sale.booked", "S1")]), Seen(), clock=lambda: T0)
        worker.PROGRESS.pop("r.example", None)
        self.addCleanup(worker.PROGRESS.pop, "r.example", None)
        worker.one_pass(t, FakeFeed([]), Seen(), clock=lambda: T0 + dt.timedelta(hours=25), site="r.example")
        self.assertIn("r.example", worker.PROGRESS)

    def test_a_pass_counts_only_when_the_store_answered_and_no_shop_was_stuck(self):
        class Broken:
            def sites(self):
                raise RuntimeError("table unreachable")
        out = worker.pass_all(Broken(), "/tmp", log=io.StringIO())
        self.assertIsNone(out)
        self.assertEqual([worker.healthy_pass(x) for x in (None, {}, {"a": {"feed": {}}}, {"a": {"busy": True, "stuck": False}},
                                                             {"a": {"busy": True, "stuck": True}})],
                         [False, True, True, True, False])

    def test_a_shop_busy_past_the_limit_is_stuck_and_a_catching_up_one_is_not(self):
        import tempfile
        worker.PROGRESS.pop("a.example", None)                   # another test's pass may have left it set
        self.addCleanup(worker.PROGRESS.pop, "a.example", None)
        gate = threading.Event()

        class Store:
            def sites(self):
                return ["a.example"]

            def get(self, site):
                return {"url": "https://a.example"}

        def opener(record):
            gate.wait(5)
            raise RuntimeError("released")
        busy = {}
        with tempfile.TemporaryDirectory() as d:
            worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            out = worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            self.assertEqual(out["a.example"], {"busy": True, "stuck": False})
            th, since = busy["a.example"]
            busy["a.example"] = (th, since - worker.STUCK_S - 1)
            out = worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            self.assertEqual(out["a.example"], {"busy": True, "stuck": True})
            worker.PROGRESS["a.example"] = time.monotonic()        # it took up an event a moment ago: catching up
            out = worker.pass_all(Store(), d, log=io.StringIO(), opener=opener, busy=busy, deadline=0.05)
            self.assertEqual(out["a.example"], {"busy": True, "stuck": False})
            worker.PROGRESS.pop("a.example", None)
            gate.set()
            th.join(5)


class Health(unittest.TestCase):
    def serve(self, svc):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(svc))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}"

    def code(self, url, data=None):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=3) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_health_is_503_once_the_worker_stalls_and_200_while_it_passes(self):
        svc = app.Service({})
        base = self.serve(svc)
        self.assertEqual(self.code(base + "/health"), 200)                 # just started: the grace
        svc.started -= app.HEALTH_GRACE_S + 1
        worker.HEARTBEAT[0] = time.monotonic() - app.HEALTH_GRACE_S - 1
        self.assertEqual(self.code(base + "/health"), 503)
        worker.HEARTBEAT[0] = time.monotonic()
        self.assertEqual(self.code(base + "/health"), 200)

    def test_one_shop_answers_no_handshake_and_nothing_else(self):
        base = self.serve(app.Service({}))
        self.assertEqual(self.code(base + "/ivendnext/connect", b"{}"), 404)
        self.assertEqual(self.code(base + "/anything"), 404)

    def test_the_prefix_names_the_library_apps_record_types(self):
        try:
            app.Service({"GCS_PREFIX": "IVENDNEXT GCS"})
            self.assertEqual((cards.CARD, cards.SETTINGS), ("IVENDNEXT GCS Card", "IVENDNEXT GCS Settings"))
        finally:
            cards.use_prefix("PP GCS")



class Scheduled(unittest.TestCase):
    """PAYWHENUSED: hosted as a function on a schedule. Each call is one pass (the feed, then the releases due) of the
    shops it claims; a shop another call holds is left to it, so two calls never release one card twice."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="s25-fn-")
        import shops
        self.store = shops.FileStore(os.path.join(self.dir, "shops.json"))
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_gcs", "PP_STATE": self.dir}, store=self.store, scheduled=True)
        self.shops, self.feeds = {}, {}
        for site in ("a.example", "b.example"):
            self.shops[site] = shop()
            sale(self.shops[site], "S1")
            self.feeds[site] = FakeFeed([ev(1, "sale.booked", "S1")])
            self.store.put(site, {"url": f"https://{site}", "secrets": {"user:gcs@x": "k:s"}})

    def run_pass(self):
        with mock.patch.object(worker, "open_shop", lambda r: (self.shops[r["url"][8:]], self.feeds[r["url"][8:]])), \
                mock.patch("sys.stdout", io.StringIO()):
            return app.scheduled(self.svc, "pass")

    def claims(self):
        with open(os.path.join(self.dir, "shops.json")) as f:
            return sorted(n for n in json.load(f) if "|" in n)

    def test_a_call_passes_each_claimed_shop_and_frees_its_claim(self):
        out = self.run_pass()
        self.assertEqual(sorted(out), ["a.example", "b.example"])
        self.assertEqual(sorted(self.shops["a.example"].db["PP GCS Card"]), ["S1:1"])
        self.assertEqual(self.claims(), [])

    def test_canary_a_shop_another_call_holds_is_left_to_it(self):
        self.assertTrue(self.store.claim("pass|a.example", time.time() + 1000, 1000))
        self.assertEqual(sorted(self.run_pass()), ["b.example"])
        self.assertNotIn("PP GCS Card", {k for k, v in self.shops["a.example"].db.items() if v})
        self.assertEqual(self.claims(), ["pass|a.example"])

    def test_health_answers_200_as_a_function(self):
        self.svc.started -= app.HEALTH_GRACE_S + 1
        worker.HEARTBEAT[0] = time.monotonic() - app.HEALTH_GRACE_S - 1      # stale, whatever the machine's uptime
        self.assertEqual(app.handle(self.svc, "GET", "/health", {}, b""), (200, {"ok": 1}))
        self.assertEqual(app.handle(self.svc, "POST", "/anything", {}, b"{}")[0], 404)


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

    def test_a_shop_answer_cut_short_is_the_shop_unreachable_never_a_crash(self):
        import shop
        s = shop.Shop("https://shop.example", "k", "s")
        s._opener = mock.Mock(open=cut_answer)
        with self.assertRaises(shop.ShopError) as e:
            s._call("GET", "/api/resource/Card")
        self.assertEqual(e.exception.status, 0)
        self.assertIn("unreachable", e.exception.message)


if __name__ == "__main__":
    unittest.main()
