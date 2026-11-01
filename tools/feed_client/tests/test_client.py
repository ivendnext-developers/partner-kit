"""Laptop tests of the event-feed client, no bench: the client's own logic against an in-memory log (a not-done queue),
through the ENGINE transport's code (a fake record API) and the DOOR transport's code (a fake door following
the P-FEED contract).

    python3 -m unittest discover -s tools/feed_client/tests -p 'test_*.py'
"""

import ast
import contextlib
import http.client
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import feed_client as F  # noqa: E402


class Log:
    """The engine's Integration Sync Log, in memory: rows in creation order, flag 0 = not done."""

    def __init__(self):
        self.rows = []

    def add(self, app, doc_type, doc_name, op, is_return=False):
        n = len(self.rows)
        self.rows.append({"name": f"r{n:04d}", "application_name": app, "doc_type": doc_type, "doc_name": doc_name,
                          "operation_type": op, "creation": f"2026-10-04 10:00:{n:02d}.000000", "flag": 0,
                          "error": None, "_ret": is_return})

    def undone(self, app):
        return [r for r in self.rows if r["application_name"] == app and r["flag"] == 0]


class FakeApi:
    """Answers the record-API calls EngineFeed makes, from a Log — the same filters, order, offset and paging."""

    def __init__(self, log):
        self.log, self.calls = log, []

    def call(self, method, path, params=None, body=None):
        self.calls.append((method, path))
        params = params or {}
        if path == "/api/resource/Integration%20Sync%20Log" and method == "GET":
            f = dict((k, v) for k, _op, v in json.loads(params["filters"]))
            rows = [r for r in self.log.rows if r["application_name"] == f["application_name"] and r["flag"] == f["flag"]]
            s, n = int(params["limit_start"]), int(params["limit_page_length"])
            return {"data": [dict(r) for r in rows[s:s + n]]}
        if path == "/api/resource/POS%20Invoice":
            names = json.loads(params["filters"])[0][2]
            ret = {}
            for r in self.log.rows:
                if r["doc_type"] == "POS Invoice" and r["doc_name"] in names:
                    ret[r["doc_name"]] = ret.get(r["doc_name"], False) or r["_ret"]
            return {"data": [{"name": k, "is_return": int(v)} for k, v in ret.items()]}
        if path == "/api/method/ivendnext_mpos.api.v1.get_count":
            f = dict((k, v) for k, _op, v in json.loads(params["filters"]))
            return {"message": len(self.log.undone(f["application_name"]))}
        if path == "/api/method/ivendnext_mpos.api.v1.bulk_update":
            for d in json.loads(body["docs"]):
                next(r for r in self.log.rows if r["name"] == d["docname"])["flag"] = d["flag"]
            return {"message": {"failed_docs": []}}
        if method == "PUT" and path.startswith("/api/resource/Integration%20Sync%20Log/"):
            name = urllib.parse.unquote(path.rsplit("/", 1)[1])
            next(r for r in self.log.rows if r["name"] == name)["error"] = body["error"]
            return {}
        raise AssertionError(f"unexpected call {method} {path}")


def _seed(log, n_sales=7):
    for i in range(n_sales):
        for op in ("after_insert", "on_update", "on_submit", "on_change"):
            log.add("A", "POS Invoice", f"SINV-{i}", op, is_return=(i == 3))
        log.add("B", "POS Invoice", f"SINV-{i}", "on_submit")   # another application's row for the same sale
    log.add("A", "Customer", "CUST-1", "after_insert")


def collected(store):
    return [r[0] for r in store.db.execute("select id from collected")]


class TestClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = Log()
        _seed(self.log)
        self.feed = F.EngineFeed(FakeApi(self.log), "A")

    def store(self, name="a"):
        return F.Store(os.path.join(self.tmp, f"{name}.sqlite"))

    def test_every_event_once_small_pages_none_from_b(self):
        st = self.store()
        n = F.poll(self.feed, st, F.sample_handler, limit=3)
        ids = collected(st)
        self.assertEqual(sorted(ids), sorted(r["name"] for r in self.log.rows if r["application_name"] == "A"))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(n["backlog"], 0)
        self.assertFalse(self.log.undone("A"))
        self.assertEqual(len(self.log.undone("B")), 7, "A's run must not touch B's rows")

    def test_crash_before_done_then_restart_is_exactly_once(self):
        st = self.store()
        with self.assertRaises(SystemExit):
            F.poll(self.feed, st, F.sample_handler, limit=5, crash_after=4)
        self.assertEqual(len(self.log.undone("A")), 29, "nothing was marked done before the crash")
        n = F.poll(self.feed, self.store(), F.sample_handler, limit=5)
        self.assertEqual(n["skipped_seen"], 4)
        ids = collected(st)
        self.assertEqual(len(ids), 29)
        self.assertEqual(len(ids), len(set(ids)))

    def test_failed_event_stays_undone_with_note_and_rest_flows(self):
        st = self.store()

        def handler(ev, db):
            if ev["doc_name"] == "SINV-2" and ev["raw_event"] == "on_submit":
                raise ValueError("partner system refused it")
            F.sample_handler(ev, db)

        n = F.poll(self.feed, st, handler, limit=4)
        left = self.log.undone("A")
        self.assertEqual(n["failed"], 1)
        self.assertEqual(len(left), 1)
        self.assertIn("partner system refused it", left[0]["error"])
        self.assertEqual(len(collected(st)), 28, "every other event was handled despite the failure")
        # the next pass retries it; this time the partner's system accepts
        n2 = F.poll(self.feed, st, F.sample_handler, limit=4)
        self.assertEqual((n2["handled"], n2["backlog"]), (1, 0))

    def test_labels_on_the_engine_transport(self):
        st = self.store()
        F.poll(self.feed, st, F.sample_handler, limit=50)
        ev = {r[0]: r[1] for r in st.db.execute("select doc_name || '/' || id, event from collected")}
        labels = sorted(set(ev.values()))
        self.assertIn("sale.booked", labels)
        self.assertIn("return.booked", labels)
        self.assertIn("customer.created", labels)
        self.assertIn("pos_invoice.after_insert", labels)
        self.assertEqual(F.label("POS Invoice", "on_submit", None, exists=False), "pos_invoice.deleted")

    def test_reconcile_finds_a_sale_the_feed_never_delivered(self):
        st = self.store()
        self.log.rows = [r for r in self.log.rows if not (r["doc_name"] == "SINV-5" and r["operation_type"] == "on_submit")]
        F.poll(self.feed, st, F.sample_handler)

        class Booked:
            def call(self, *a, **k):
                return {"data": [{"name": f"SINV-{i}"} for i in range(7)]}

        r = F.reconcile(Booked(), st, "POS Invoice", "2026-10-04 00:00:00")
        self.assertEqual(r["missing"], ["SINV-5"])

    def test_reconcile_reports_a_sale_still_queued_apart_from_missing(self):
        st = self.store()
        F.poll(self.feed, st, F.sample_handler)
        self.log.add("A", "POS Invoice", "SINV-9", "on_submit")       # late: in the queue, not yet collected

        class Booked:
            def call(self, *a, **k):
                return {"data": [{"name": f"SINV-{i}"} for i in (0, 1, 9)]}

        r = F.reconcile(Booked(), st, "POS Invoice", "2026-10-04 00:00:00", self.feed)
        self.assertEqual((r["missing"], r["still_queued"]), ([], ["SINV-9"]))

    def test_a_done_that_does_not_take_stops_the_pass(self):
        class Stuck(F.EngineFeed):
            def done(self, ids):
                return len(ids)                                          # claims done, changes nothing
        with self.assertRaises(F.FeedError):
            F.poll(Stuck(FakeApi(self.log), "A"), self.store(), F.sample_handler, limit=5)

    STANDIN = os.environ.get("FEED_STANDIN") or os.path.join(os.path.dirname(HERE), "standin")

    @unittest.skipUnless(os.path.isdir(STANDIN),
                         "the stand-in for the event feed's extension point is internal to our test bench (FEED_STANDIN)")
    def test_door_and_client_label_tables_are_the_same(self):
        src = open(os.path.join(self.STANDIN, "pp_feed", "pp_feed", "api.py")).read()
        node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign) and n.targets[0].id == "_LABELS")
        self.assertEqual(ast.literal_eval(node.value), F._LABELS)

    def test_no_redirect_is_followed_with_the_key(self):
        self.assertIsNone(F._NoRedirect().redirect_request(None, None, 302, "", {}, "http://elsewhere/"))


class FakeDoor:
    """The door's three calls over the same Log, as the P-FEED contract states them (scoped to one application)."""

    def __init__(self, log, app):
        self.log, self.app, self.failed_calls = log, app, []

    def call(self, method, path, params=None, body=None):
        name = path.rsplit(".", 1)[1]
        if method != "POST":     # the real door takes POST only; it refuses a GET (405) and reads the request's body
            raise F.FeedError(f"405 the door takes POST only, not {method}")
        params = body or {}
        mine = [r for r in self.log.rows if r["application_name"] == self.app]
        if name == "events":
            todo = [r for r in mine if r["flag"] == 0]
            if params.get("page"):
                c, _, n = params["page"].partition("|")
                todo = [r for r in todo if (r["creation"], r["name"]) > (c, n)]
            page = todo[:int(params["limit"])]
            ret = {r["doc_name"]: r["_ret"] for r in self.log.rows}
            evs = [{"id": r["name"], "doc_type": r["doc_type"], "doc_name": r["doc_name"],
                    "raw_event": r["operation_type"], "at": r["creation"],
                    "event": F.label(r["doc_type"], r["operation_type"], ret.get(r["doc_name"]))} for r in page]
            nxt = f"{page[-1]['creation']}|{page[-1]['name']}" if len(page) == int(params["limit"]) else None
            return {"message": {"events": evs, "page": nxt, "backlog": sum(1 for r in mine if r["flag"] == 0)}}
        if name == "done":
            ids = set(body["ids"])
            assert ids <= {r["name"] for r in mine}
            for r in mine:
                if r["name"] in ids:
                    r["flag"] = 1
            return {"message": {"done": len(ids)}}
        if name == "failed":
            self.failed_calls.append(body)
            next(r for r in mine if r["name"] == body["id"])["error"] = body["error"]
            return {"message": {"ok": True}}
        raise AssertionError(path)


class TestApiHeaders(unittest.TestCase):
    def test_every_call_names_the_client_not_the_librarys_default(self):
        seen = []

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"{}"

        class Opener:
            def open(self, req, timeout=None):
                seen.append(req)
                return Reply()

        api = F.Api("https://shop.example", "key", "secret")
        api._opener = Opener()
        api.call("POST", "/api/method/x", body={"limit": 1})
        api.call("GET", "/api/resource/Y", params={"a": "b"})
        self.assertEqual([r.get_header("User-agent") for r in seen], [F.USER_AGENT] * 2)
        self.assertNotIn("urllib", F.USER_AGENT.lower())


class TestDoor(unittest.TestCase):
    def setUp(self):
        self.log = Log()
        _seed(self.log)
        self.api = FakeDoor(self.log, "A")
        self.feed = F.DoorFeed(self.api, "pp_feed.api")
        self.st = F.Store(os.path.join(tempfile.mkdtemp(), "d.sqlite"))

    def test_door_pages_past_a_failed_event_and_notes_it(self):
        def handler(ev, db):
            if ev["doc_name"] == "SINV-1" and ev["raw_event"] == "on_update":
                raise ValueError("no")
            F.sample_handler(ev, db)

        n = F.poll(self.feed, self.st, handler, limit=3)
        self.assertEqual((n["failed"], n["handled"], n["backlog"]), (1, 28, 1))
        self.assertEqual(len(self.api.failed_calls), 1)
        self.assertFalse(self.log.undone("B") == [], "B untouched")
        n2 = F.poll(self.feed, self.st, F.sample_handler, limit=3)
        self.assertEqual((n2["handled"], n2["backlog"]), (1, 0))

    def test_the_door_is_asked_with_post_and_the_body_it_reads(self):
        calls = []
        real = self.api.call

        def spy(method, path, params=None, body=None):
            calls.append((method, path.rsplit(".", 1)[1], params, body))
            return real(method, path, params, body)
        self.api.call = spy
        self.feed.events(limit=2)
        self.feed.backlog()
        self.assertEqual(calls, [("POST", "events", None, {"limit": 2}), ("POST", "events", None, {"limit": 1})])

    def test_door_crash_then_restart_is_exactly_once(self):
        with self.assertRaises(SystemExit):
            F.poll(self.feed, self.st, F.sample_handler, limit=4, crash_after=5)
        n = F.poll(self.feed, self.st, F.sample_handler, limit=4)
        ids = collected(self.st)
        # pages of 4: the first page was marked done before the 5th event crashed, so 1 event comes back
        self.assertEqual((n["skipped_seen"], len(ids), len(set(ids))), (1, 29, 29))


class Shop(FakeApi):
    """The engine's feed as in FakeApi, plus the shop's list of submitted POS Invoices with their ``creation``."""

    def __init__(self, log):
        super().__init__(log)
        self.sales, self.other, self.n, self.deny_sales = {}, {}, 0, False

    def sell(self, name, delivered=True, doctype="POS Invoice"):
        """A record created now, on the shop's clock; its events reach the queue unless ``delivered`` is False."""
        self.n += 1
        (self.sales if doctype == "POS Invoice" else self.other)[name] = f"2026-10-05 09:00:{self.n:02d}.000000"
        if delivered:
            self.log.add("A", doctype, name, "after_insert")
            self.log.add("A", doctype, name, "on_submit")

    def call(self, method, path, params=None, body=None):
        f = json.loads((params or {}).get("filters", "[]"))
        listed = {"/api/resource/POS%20Invoice": self.sales, "/api/resource/Sales%20Invoice": self.other}
        if path in listed and not (f and f[0][0] == "name"):
            self.calls.append((method, path, params))
            if self.deny_sales:
                raise F.FeedError("403 not permitted")
            rows = [{"name": k, "creation": v} for k, v in listed[path].items()]
            for _field, op, val in f:
                if op == ">=":
                    rows = [r for r in rows if r["creation"] >= val]
            if params.get("order_by") == "creation desc":
                rows = sorted(rows, key=lambda r: r["creation"], reverse=True)[:int(params["limit_page_length"])]
            want = json.loads(params["fields"])      # the real record API returns only the fields asked for
            return {"data": [{k: r[k] for k in want} for r in rows]}
        return super().call(method, path, params, body)


class TestRestart(unittest.TestCase):
    """A working folder lost at a restart: a sale it never saw delivered is *unknown*, never *missing*."""
    SINCE = "2026-10-05 00:00:00"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = Log()
        self.shop = Shop(self.log)
        self.feed = F.EngineFeed(self.shop, "A")

    def folder(self, name):
        return F.Store(os.path.join(self.tmp, f"{name}.sqlite"))

    def report(self, store):
        return F.reconcile(self.shop, store, "POS Invoice", self.SINCE, self.feed)

    def lost_folder(self):
        """Three sales handled and marked done by the first folder; the second folder starts empty and polls."""
        first = self.folder("one")
        for n in ("S1", "S2", "S3"):
            self.shop.sell(n)
        F.began(self.shop, first, "POS Invoice")
        F.poll(self.feed, first, F.sample_handler)
        second = self.folder("two")
        F.began(self.shop, second, "POS Invoice")
        F.poll(self.feed, second, F.sample_handler)        # the queue is empty: nothing comes back
        return second

    def test_handled_sales_are_unknown_not_missing_after_a_lost_folder(self):
        r = self.report(self.lost_folder())
        self.assertEqual(r["missing"], [], "a handled sale is not a missed delivery")
        self.assertEqual((r["unknown"], r["still_queued"]), (["S1", "S2", "S3"], []))
        self.assertIn("check it in the shop", r["unknown_why"])

    def test_a_sale_skipped_after_the_restart_is_still_missing(self):
        second = self.lost_folder()
        self.shop.sell("S4", delivered=False)               # booked after the folder began; its events never came
        self.shop.sell("S5")
        F.poll(self.feed, second, F.sample_handler)
        r = self.report(second)
        self.assertEqual((r["missing"], r["unknown"]), (["S4"], ["S1", "S2", "S3"]))

    def test_a_sale_still_queued_is_neither_missing_nor_unknown(self):
        first = self.folder("one")
        self.shop.sell("S1")
        F.poll(self.feed, first, F.sample_handler)
        self.shop.sell("S2")                                # late: its events wait in the queue
        r = self.report(self.folder("two"))                 # a lost folder, S2 not yet handled
        self.assertEqual((r["missing"], r["unknown"], r["still_queued"]), ([], ["S1"], ["S2"]))

    def test_a_fresh_install_dates_the_marker_and_an_upgraded_folder_takes_none(self):
        st = self.folder("lasts")
        self.shop.sell("S1")
        self.shop.sell("S2", delivered=False)
        F.began(self.shop, st, "POS Invoice")               # a fresh install: the marker is the newest sale, S2
        F.poll(self.feed, st, F.sample_handler)
        self.shop.sell("S3", delivered=False)               # after the marker: missing
        r = self.report(st)
        self.assertEqual((r["missing"], r["unknown"]), (["S3"], ["S2"]))      # S1 was delivered
        # the same folder, upgraded in place from a client that kept no marker: seen events exist, so none is taken
        st.db.execute("drop table feed_client_meta")
        calls = len(self.shop.calls)
        self.assertIsNone(F.began(self.shop, st, "POS Invoice"))
        self.assertEqual(len(self.shop.calls), calls, "an upgraded folder reads nothing from the shop")
        r = self.report(st)
        self.assertEqual((r["missing"], r["unknown"]), (["S2", "S3"], []))

    def test_the_marker_is_taken_once_and_not_moved(self):
        st = self.folder("one")
        self.shop.sell("S1")
        m = F.began(self.shop, st, "POS Invoice")
        self.shop.sell("S2", delivered=False)
        self.assertEqual(F.began(self.shop, st, "POS Invoice"), m)
        self.assertEqual(m, self.shop.sales["S1"])

    def test_a_shop_with_no_sale_gives_no_marker_and_nothing_is_unknown(self):
        st = self.folder("one")
        self.assertIsNone(F.began(self.shop, st, "POS Invoice"))
        self.shop.sell("S1", delivered=False)
        r = self.report(st)
        self.assertEqual((r["missing"], r["unknown"]), (["S1"], []))
        self.assertNotIn("unknown_why", r)

    def test_one_marker_serves_every_record_type(self):
        first = self.folder("one")
        self.shop.sell("V1", doctype="Sales Invoice")
        self.shop.sell("S1")
        F.poll(self.feed, first, F.sample_handler)
        second = self.folder("two")
        F.began(self.shop, second, "POS Invoice")
        F.poll(self.feed, second, F.sample_handler)
        r = F.reconcile(self.shop, second, "Sales Invoice", self.SINCE, self.feed, events=("invoice.booked",))
        self.assertEqual((r["missing"], r["unknown"]), ([], ["V1"]))

    def test_run_carries_on_when_the_key_cannot_read_the_default_type(self):
        self.log.add("A", "Customer", "C1", "after_insert")
        self.shop.deny_sales = True
        self.run_command()
        self.assertEqual(self.log.undone("A"), [], "the Customer event was handled")

    def run_command(self):
        real_api, real_env = F.Api, dict(os.environ)
        F.Api = lambda *a, **k: self.shop
        os.environ.update(FEED_KEY="k", FEED_SECRET="s")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                F.main(["run", "--base", "http://shop.invalid", "--transport", "engine", "--app", "A",
                        "--state", os.path.join(self.tmp, "run.sqlite")])
        finally:
            F.Api = real_api
            os.environ.clear()
            os.environ.update(real_env)

    def test_the_run_command_takes_the_marker_before_the_first_poll(self):
        self.shop.sell("S1")
        self.run_command()
        first = self.shop.calls[0]
        self.assertEqual(first[1], "/api/resource/POS%20Invoice", "the marker is read before any event")
        self.assertEqual(json.loads(first[2]["filters"]), [["docstatus", "=", 1]])



class TestChanged(unittest.TestCase):
    """``changed``: a value is judged when the record is new or the value changed, and the memory commits with the event."""

    def test_new_then_same_then_changed(self):
        with tempfile.TemporaryDirectory() as d:
            store = F.Store(os.path.join(d, "s.sqlite"))
            seen = []
            for i, limit in enumerate((500, 500, 800)):
                ev = {"id": f"e{i}", "event": "updated", "doc_type": "Customer", "doc_name": "C1"}
                store.handled(ev, lambda db, v=limit: seen.append(F.changed(db, "Customer", "C1", "credit_limit", v)))
            self.assertEqual(seen, [(True, None), (False, 500), (True, "500")])

    def test_a_handler_that_fails_forgets_the_value_with_the_event(self):
        with tempfile.TemporaryDirectory() as d:
            store = F.Store(os.path.join(d, "s.sqlite"))

            def boom(db):
                F.changed(db, "Customer", "C1", "credit_limit", 900)
                raise RuntimeError("the judge failed")
            with self.assertRaises(RuntimeError):
                store.handled({"id": "e1", "event": "updated", "doc_type": "Customer", "doc_name": "C1"}, boom)
            out = []
            store.handled({"id": "e1", "event": "updated", "doc_type": "Customer", "doc_name": "C1"},
                          lambda db: out.append(F.changed(db, "Customer", "C1", "credit_limit", 900)))
            self.assertEqual(out, [(True, None)], "the failed event's value was remembered without the event")


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

    def test_a_shop_answer_cut_short_is_a_feed_error_never_a_crash(self):
        api = F.Api("https://shop.example", "k", "s")
        api._opener = mock.Mock(open=cut_answer)
        with self.assertRaises(F.FeedError) as e:
            api.call("GET", "/api/resource/Item")
        self.assertIn("unreachable", str(e.exception))


PART = """
CALLS = []
FAIL = set()


def handler(ev, db):
    CALLS.append(ev["id"])
    if ev["id"] in FAIL:
        raise RuntimeError("down")
"""


class TestHandoff(unittest.TestCase):
    """One reader for the parts of one app: the feed read once a run, each event handed to every part that registered its
    record type, recorded per part in the one seen-list, and done only when every part that wants it has handled it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = Log()
        _seed(self.log)
        self.parts = {}
        for name in ("a", "b"):              # each part's handler lives in its own folder, as in an app's service/<tag>/
            folder = os.path.join(self.tmp, "service", name)
            os.makedirs(folder)
            path = os.path.join(folder, "worker.py")
            with open(path, "w") as f:
                f.write(PART)
            spec = __import__("importlib.util").util.spec_from_file_location(f"part_{name}", path)
            module = __import__("importlib.util").util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.parts[name] = module
        self.homes = {n: os.path.join(self.tmp, "service", n) for n in self.parts}
        self.store = F.Store(os.path.join(self.tmp, "feed.sqlite"))     # the samples share one file per shop: one seen-list

    def hub(self, reads):
        return F.Handoff(reads, self.homes)

    def run_once(self, hub, feed, who=("a", "b"), limit=3):
        hub.begin()
        out = {n: hub.poll(feed, self.store, self.parts[n].handler, limit) for n in who}
        out["finish"] = hub.finish()
        return out

    def test_read_once_handed_by_record_type_and_done_after_every_part(self):
        api = FakeApi(self.log)
        feed = F.EngineFeed(api, "A")
        hub = self.hub({"a": ["POS Invoice"], "b": ["POS Invoice", "Customer"]})
        hub.begin()
        hub.poll(feed, self.store, self.parts["a"].handler, 3)
        reads = [c for c in api.calls if c == ("GET", "/api/resource/Integration%20Sync%20Log")]
        hub.poll(feed, self.store, self.parts["b"].handler, 3)
        self.assertEqual([c for c in api.calls if c == ("GET", "/api/resource/Integration%20Sync%20Log")], reads)
        mine = [r["name"] for r in self.log.rows if r["application_name"] == "A"]
        self.assertEqual(len(mine), 29)
        self.assertEqual(self.parts["a"].CALLS, [r["name"] for r in self.log.rows if r["application_name"] == "A"
                                                 and r["doc_type"] == "POS Invoice"])        # every page, in order, once
        self.assertEqual(self.parts["b"].CALLS, mine)
        self.assertEqual(len(self.log.undone("A")), 29)                 # nothing is done while the parts are handed
        self.assertEqual(hub.finish(), {"done": 29, "waiting": 0, "errors": 0})
        self.assertFalse(self.log.undone("A"))
        self.assertEqual(len(self.log.undone("B")), 7)

    def test_a_part_that_fails_leaves_the_event_and_the_other_is_not_run_again(self):
        door = FakeDoor(self.log, "A")
        feed = F.DoorFeed(F.Api("https://shop.example", "k", "s"))
        hub = self.hub({"a": ["POS Invoice"], "b": ["POS Invoice"]})
        sale = next(r["name"] for r in self.log.rows if r["application_name"] == "A" and r["doc_type"] == "POS Invoice")
        self.parts["b"].FAIL.add(sale)
        with mock.patch.object(feed, "api", door):
            first = self.run_once(hub, feed)
            self.assertEqual(first["b"]["failed"], 1)
            self.assertEqual([r["name"] for r in self.log.undone("A")], [sale])    # the customer: no part wants it, done
            self.assertEqual(door.failed_calls[-1]["id"], sale)
            self.assertTrue(door.failed_calls[-1]["error"].startswith("b: RuntimeError"))
            self.parts["b"].FAIL.clear()
            a_before, b_before = list(self.parts["a"].CALLS), list(self.parts["b"].CALLS)
            second = self.run_once(hub, feed)
        self.assertEqual(self.parts["a"].CALLS, a_before)               # a is not run again for the sale it handled
        self.assertEqual(self.parts["b"].CALLS, b_before + [sale])      # b is handed only what it has not handled
        self.assertEqual((second["a"]["skipped_seen"], second["b"]["handled"]), (1, 1))
        self.assertEqual([r["name"] for r in self.log.undone("A") if r["doc_type"] == "POS Invoice"], [])

    def test_an_event_no_part_wants_is_done_and_a_part_that_did_not_poll_keeps_its_events(self):
        feed = F.EngineFeed(FakeApi(self.log), "A")
        out = self.run_once(self.hub({"a": ["Customer"], "b": ["POS Invoice"]}), feed, who=("a",))
        self.assertEqual(self.parts["a"].CALLS, ["r0035"])
        self.assertEqual(out["finish"]["done"], 1)                      # the customer: a, its one part, handled it
        self.assertEqual(len(self.log.undone("A")), 28)                 # b wants the sales and has not been run
        out = self.run_once(self.hub({"a": ["Customer"]}), feed, who=("a",))
        self.assertEqual(out["finish"]["done"], 28)                     # no part wants the sales: done at once
        self.assertFalse(self.log.undone("A"))

    def test_a_handler_of_no_part_is_refused_and_nothing_is_handed(self):
        hub = self.hub({"a": ["POS Invoice"]})
        hub.begin()
        with self.assertRaises(F.FeedError):
            hub.poll(F.EngineFeed(FakeApi(self.log), "A"), self.store, F.sample_handler)
        self.assertEqual(hub.finish(), {"done": 0, "waiting": 0, "errors": 0})
        self.assertEqual(len(self.log.undone("A")), 29)

    def test_an_event_waiting_for_a_part_never_holds_back_a_newer_one(self):
        log = Log()
        for i in range(1500):
            log.add("A", "POS Invoice", f"S{i}", "on_submit")
        feed = F.EngineFeed(FakeApi(log), "A")
        self.parts["b"].FAIL.update(r["name"] for r in log.rows)         # b fails every one of them, run after run
        hub = self.hub({"a": ["POS Invoice"], "b": ["POS Invoice"]})
        self.run_once(hub, feed, limit=100)
        log.add("A", "POS Invoice", "NEW", "on_submit")
        self.parts["a"].CALLS.clear()
        self.parts["b"].CALLS.clear()
        self.run_once(hub, feed, limit=100)
        self.assertEqual(self.parts["a"].CALLS, ["r1500"])                # the new sale reaches a, the rest are seen
        self.assertEqual(self.parts["b"].CALLS[-1], "r1500")
        self.assertEqual([r["name"] for r in log.undone("A")], [f"r{i:04d}" for i in range(1500)])

    def test_the_lasting_record_keeps_a_part_from_running_again_when_its_seen_list_is_lost(self):
        class Ledger(dict):                                                # the app's shops store, as get/put/delete
            def put(self, name, record):
                self[name] = json.loads(json.dumps(record))

            def delete(self, name):
                self.pop(name, None)

        ledger = Ledger()
        feed = F.EngineFeed(FakeApi(self.log), "A")
        hub = F.Handoff({"a": ["Customer"], "b": ["Customer"]}, self.homes, ledger)
        self.parts["b"].FAIL.add("r0035")
        self.run_once(hub, feed)
        self.assertEqual(list(ledger.values()), [{"events": {"r0035": ["a"]}}])
        self.assertTrue(all(name.startswith(F.HANDOFF_RECORD) and "|" in name for name in ledger))   # never a shop's name
        self.store = F.Store(os.path.join(self.tmp, "new_copy.sqlite"))   # a new copy of the function: its seen-list empty
        self.parts["b"].FAIL.clear()
        self.run_once(hub, feed)
        self.assertEqual(self.parts["a"].CALLS, ["r0035"])                # a is not run again for the customer
        self.assertEqual(self.parts["b"].CALLS, ["r0035", "r0035"])
        self.assertEqual(ledger, {})                                       # nothing left waiting: the record is gone
        self.assertFalse(self.log.undone("A"))

    def test_poll_is_handed_once_the_app_puts_its_reader_in_place(self):
        hub = self.hub({"a": ["POS Invoice"], "b": ["Customer"]})
        hub.begin()
        sys.modules[F.HANDOFF_MODULE] = type(sys)("handoff")
        sys.modules[F.HANDOFF_MODULE].HUB = hub
        self.addCleanup(sys.modules.pop, F.HANDOFF_MODULE, None)
        n = F.poll(F.EngineFeed(FakeApi(self.log), "A"), self.store, self.parts["a"].handler, 3)
        self.assertEqual((n["part"], n["handled"], n["done"]), ("a", 28, 0))
        self.assertEqual(len(self.log.undone("A")), 29)                 # b has not handled the customer yet


if __name__ == "__main__":
    unittest.main()
