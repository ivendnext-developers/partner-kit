"""The event-feed client — the reference client for reading iVendNext's events reliably.

Python 3.9+, standard library only. Any language can do the same; this file is the reference. Recipe:
``recipes/event_feed.md``.

What it does, in order, every poll:
  1. pull the oldest events not yet marked done (a queue, never a cursor: a row committed late is never skipped);
  2. for each event: skip it if its id is already in the seen-set, else run the handler; the handler's own write and
     the seen-set entry are committed together (``Store.handled``), so an event is acted on once;
  3. a handler that raises → ``failed(id, note)``: the row stays undone and carries the note for a support call;
  4. mark the page done in one call. A crash between 2 and 4 is harmless: the events come back and are skipped as seen.
  A nightly ``reconcile`` lists the records booked in a window and reports any the feed never delivered. A record
  created before this seen-set began (a working folder lost at a restart) that it never saw delivered is ``unknown``,
  not ``missing``: the handled list is gone, so a delivery cannot be told from its absence (``began``).

Two transports, one client:
  * ``engine`` — the engine's feed as it is today: Registered Application + Integration Sync Log read over the record
    API with an integration user. ⚠ Today's grant cannot be scoped to one application (the log's application name is a
    plain text field): the client filters to its own application, but the key COULD read and flip other applications'
    rows. Measured on the bench and recorded in the evidence. Use it only where you are the tenant's one consumer.
  * ``door`` — the event feed's door, live in the POS app: ``events`` / ``done`` / ``failed``, each a POST, scoped by
    the server to the caller's own application, labels decided by the server. ``--door-prefix`` points the client at
    another host of the same three calls.

    python3 feed_client.py run      --base https://your-sandbox.example --transport door \
                                    --state state/a.sqlite
    python3 feed_client.py backlog  ... (prints the not-done count)
    python3 feed_client.py reconcile --since "2026-10-04 00:00:00" --doctype "POS Invoice" ...
    python3 feed_client.py dump     ... (the sample handler's table, one JSON line per row)
The key and secret are read from the environment: FEED_KEY and FEED_SECRET (never from the command line).
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

LOG = "Integration Sync Log"

# The published label table (the P-FEED contract). The door decides labels on the server; the engine transport
# applies the same table on the client, so a handler written against one runs unchanged on the other.
_LABELS = {
    ("POS Invoice", "on_cancel"): "sale.cancelled",
    ("Sales Invoice", "on_submit"): "invoice.booked", ("Sales Invoice", "on_cancel"): "invoice.cancelled",
    ("Sales Order", "on_submit"): "order.booked",
    ("Customer", "after_insert"): "customer.created", ("Customer", "on_update"): "customer.updated",
    ("Item", "after_insert"): "item.created", ("Item", "on_update"): "item.updated",
    ("Stock Entry", "on_submit"): "stock.moved", ("Purchase Receipt", "on_submit"): "goods.received",
    ("Stock Reconciliation", "on_submit"): "stock.counted",
}


def label(doc_type: str, raw_event: str, is_return: bool | None, exists: bool = True) -> str:
    slug = doc_type.lower().replace(" ", "_")
    if not exists:
        return f"{slug}.deleted"
    if doc_type == "POS Invoice" and raw_event == "on_submit":
        return "return.booked" if is_return else "sale.booked"
    return _LABELS.get((doc_type, raw_event), f"{slug}.{raw_event}")


class FeedError(Exception):
    """The server refused (its message is kept) or could not be reached."""


USER_AGENT = "ivendnext-feed-client/1"      # names the caller: an edge may refuse a library's default signature


class Api:
    """A token-authenticated JSON client. Follows no redirect (a key never travels to another host)."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 20):
        self.base, self.timeout = base.rstrip("/"), timeout
        self._auth = f"token {key}:{secret}"
        self._opener = urllib.request.build_opener(_NoRedirect)

    def call(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise FeedError(f"{e.code} {_server_message(e.read())}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
            raise FeedError(f"unreachable: {e}") from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _server_message(raw: bytes) -> str:
    """The server's own sentence, never its traceback."""
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        return raw[:200].decode(errors="replace")
    for k in ("_server_messages", "message", "exception", "exc_type"):
        if d.get(k):
            v = d[k]
            if k == "_server_messages":
                try:
                    v = "; ".join(json.loads(m).get("message", m) for m in json.loads(v))
                except ValueError:
                    pass
            return str(v)[:300]
    return ""


# ── the two transports: events(limit, page) → (events, next_page, backlog) · done(ids) · failed(id, note) ─────

class EngineFeed:
    def __init__(self, api: Api, app: str):
        self.api, self.app = api, app

    def _filters(self):
        return json.dumps([["application_name", "=", self.app], ["flag", "=", 0]])

    def events(self, limit: int = 100, page: str | None = None):
        start = int(page or 0)
        rows = self.api.call("GET", f"/api/resource/{urllib.parse.quote(LOG)}", {
            "filters": self._filters(), "order_by": "creation asc, name asc", "limit_start": start,
            "limit_page_length": limit,
            "fields": json.dumps(["name", "doc_type", "doc_name", "operation_type", "creation", "application_name"]),
        }).get("data", [])
        # labels: one read per page for the POS Invoices' return flag; a record gone since reads ".deleted"
        pos = sorted({r["doc_name"] for r in rows if r["doc_type"] == "POS Invoice"})
        flags = {}
        if pos:
            got = self.api.call("GET", "/api/resource/POS%20Invoice", {
                "filters": json.dumps([["name", "in", pos]]), "fields": json.dumps(["name", "is_return"]),
                "limit_page_length": len(pos)}).get("data", [])
            flags = {g["name"]: bool(g["is_return"]) for g in got}
        out = []
        for r in rows:
            if r.get("application_name") != self.app:   # the filter above is the server's; this is belt and braces
                continue
            exists = r["doc_type"] != "POS Invoice" or r["doc_name"] in flags
            out.append({"id": r["name"], "doc_type": r["doc_type"], "doc_name": r["doc_name"],
                        "raw_event": r["operation_type"], "at": r["creation"],
                        "event": label(r["doc_type"], r["operation_type"], flags.get(r["doc_name"]), exists)})
        nxt = str(start + len(rows)) if len(rows) == limit else None
        return out, nxt, self.backlog()

    def backlog(self) -> int:
        return int(self.api.call("GET", "/api/method/ivendnext_mpos.api.v1.get_count",
                                 {"doctype": LOG, "filters": self._filters()}).get("message", 0))

    def done(self, ids: list[str]) -> int:
        if not ids:
            return 0
        docs = [{"doctype": LOG, "docname": i, "flag": 1} for i in ids]
        res = self.api.call("POST", "/api/method/ivendnext_mpos.api.v1.bulk_update", body={"docs": json.dumps(docs)})
        failed = (res.get("message") or {}).get("failed_docs") or []
        if failed:
            raise FeedError(f"{len(failed)} event(s) could not be marked done")
        return len(ids)

    def failed(self, id_: str, note: str):
        self.api.call("PUT", f"/api/resource/{urllib.parse.quote(LOG)}/{urllib.parse.quote(id_)}",
                      body={"error": note[:1000]})


class DoorFeed:
    def __init__(self, api: Api, prefix: str = "ivendnext_mpos.api.feed"):
        self.api, self.prefix = api, prefix

    def _m(self, name):
        return f"/api/method/{self.prefix}.{name}"

    def events(self, limit: int = 100, page: str | None = None):
        body = {"limit": limit} | ({"page": page} if page else {})     # every call of the door is a POST
        m = self.api.call("POST", self._m("events"), body=body).get("message") or {}
        return m.get("events", []), m.get("page"), int(m.get("backlog", 0))

    def backlog(self) -> int:
        return self.events(limit=1)[2]

    def done(self, ids: list[str]) -> int:
        if not ids:
            return 0
        return int((self.api.call("POST", self._m("done"), body={"ids": ids}).get("message") or {}).get("done", 0))

    def failed(self, id_: str, note: str):
        self.api.call("POST", self._m("failed"), body={"id": id_, "error": note[:1000]})


# ── the partner's own store: the seen-set, written in the same transaction as the handler's work ──────────────

class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = os.path.abspath(path)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("create table if not exists seen (id text primary key, event text, doc_type text, "
                        "doc_name text, raw_event text, at text, handled_at text)")

    def seen(self, id_: str) -> bool:
        return self.db.execute("select 1 from seen where id=?", (id_,)).fetchone() is not None

    def handled(self, ev: dict, work=None):
        """Run ``work(db)`` (the handler's own writes) and record the event as seen — one transaction."""
        self.db.execute("begin")
        try:
            if work:
                work(self.db)
            self.db.execute("insert into seen values (?,?,?,?,?,?,datetime('now'))",
                            (ev["id"], ev["event"], ev["doc_type"], ev["doc_name"], ev.get("raw_event"), ev.get("at")))
            self.db.execute("commit")
        except BaseException:
            self.db.execute("rollback")
            raise

    def delivered(self, doc_type: str, events: tuple[str, ...]) -> set[str]:
        q = f"select doc_name from seen where doc_type=? and event in ({','.join('?' * len(events))})"
        return {r[0] for r in self.db.execute(q, (doc_type, *events))}


def changed(db, doc_type: str, doc_name: str, field: str, value) -> tuple[bool, object]:
    """Judge a value only when the record is new or the value changed (the *judged on change* recipe): call it inside a
    handler, with the ``db`` the handler is given, so the remembered value is committed with the event. Returns
    (True, the previous value or None) the first time a record is seen and whenever the value differs from the last one
    seen; (False, the value) otherwise. Values are compared as text. A record edited twice between two polls is judged
    on its value when it is read, once."""
    db.execute("create table if not exists last_value (doc_type text, doc_name text, field text, value text, "
               "primary key (doc_type, doc_name, field))")
    row = db.execute("select value from last_value where doc_type=? and doc_name=? and field=?",
                     (doc_type, doc_name, field)).fetchone()
    now = None if value is None else str(value)
    if row is not None and row[0] == now:
        return False, value
    db.execute("insert or replace into last_value values (?,?,?,?)", (doc_type, doc_name, field, now))
    return True, (row[0] if row else None)


def poll(feed, store: Store, handler, limit: int = 100, crash_after: int | None = None) -> dict:
    """One pass over the backlog: fetch the oldest not-done page, handle it, mark it done, move to the next page.
    An event whose handler failed stays not-done (with its note); this pass steps over it and the next pass retries it.
    In an app of several parts that read one feed, the app's service hands the pass to its one reader (``Handoff``)."""
    hub = getattr(sys.modules.get(HANDOFF_MODULE), "HUB", None)
    if hub is not None:
        return hub.poll(feed, store, handler, limit)
    n = {"handled": 0, "skipped_seen": 0, "failed": 0, "done": 0}
    page, last_ids = None, None
    while True:
        events, nxt, _ = feed.events(limit, page)
        if not events:
            break
        ids = [e["id"] for e in events]
        if ids == last_ids:      # the page we just marked done came back unchanged: `done` did not take
            raise FeedError(f"{len(ids)} event(s) marked done came back unchanged — check the key's write right")
        last_ids = ids
        ok_ids = []
        for ev in events:
            if store.seen(ev["id"]):
                n["skipped_seen"] += 1
                ok_ids.append(ev["id"])
                continue
            try:
                store.handled(ev, lambda db, ev=ev: handler(ev, db))
            except Exception as e:      # the handler's own failure: leave the event undone, with a note
                feed.failed(ev["id"], f"{type(e).__name__}: {e}")
                n["failed"] += 1
                continue
            n["handled"] += 1
            ok_ids.append(ev["id"])
            if crash_after is not None and n["handled"] >= crash_after:
                raise SystemExit(f"CRASH (injected) after handling {n['handled']}, before marking them done")
        n["done"] += feed.done(ok_ids)
        if nxt is None:
            break                # the last page of this pass; anything newer is read on the next pass
        # the next page: the door's token points past this page. The engine's offset counts what is still not-done
        # ahead of the unread rows — exactly this pass's failures, since every handled row was just marked done
        page = str(n["failed"]) if isinstance(feed, EngineFeed) else nxt
    n["backlog"] = feed.backlog()
    return n


# ── one reader for an app of several parts ───────────────────────────────────────────────────────────────────────

HANDOFF_MODULE = "ivn_feed_handoff"     # where an app's service puts its one reader (``HUB``), for every part's poll
HANDOFF_RECORD = "handoff|"             # the lasting record of a shop's waiting events: a name a shop's never holds


class Handoff:
    """One reader for an app made of several parts that each read the feed: one registration, read once per run.

    The app's service makes one (``Handoff(reads, homes)``), puts it where every part's ``poll`` finds it
    (``sys.modules[HANDOFF_MODULE].HUB``), and for each run calls ``begin()``, then each reading part's own scheduled
    pass, then ``finish()``:
      * a part's ``poll`` reads nothing itself: the first part to poll a shop in a run reads the shop's not-done events
        once (``events`` only, never ``done``), and each part is handed, in order, the events whose record type its own
        registration names (``reads``: part -> record types);
      * one seen-list: a part's event is recorded as seen as ``<part>|<event id>`` in the part's store, in the same
        transaction as the part's own writes, so no part handles an event twice, whichever part failed;
      * a part that fails leaves its note on the event (``failed``) and the event not done; a later run hands it again
        only to the parts that have not handled it;
      * ``finish`` marks done only the events that every part that wants them has recorded as seen, each part's store read
        with a connection of its own; an event no part wants is done at once, as a reader that ignores it would do;
      * an event left waiting for a part is written, with the parts that did handle it, to a lasting record (``ledger``:
        the app's shops store, ``get``/``put``/``delete``), so a part that handled it is not run again even in another copy
        of the function, whose working folder (and so its seen-list) starts empty. One record per shop, read once a run.
    Every not-done event is read each run, as a pass of ``poll`` reads the whole backlog, so an event waiting for a part
    never holds back a newer one. A part is known by the folder its handler's code is in (``homes``: part -> folder), never
    by the order parts run in, so a part's thread still at work when the next part starts still counts as its own part."""

    def __init__(self, reads: dict, homes: dict, ledger=None):
        self.reads = {p: set(types) for p, types in reads.items()}
        self.homes = {p: os.path.realpath(h) + os.sep for p, h in homes.items()}
        self.ledger = ledger
        self.run = 0
        self.shops: dict = {}
        self._lock = threading.Lock()

    def begin(self) -> None:
        """A new run: every shop is read again, once, by the first part that polls it."""
        with self._lock:
            self.run += 1
            self.shops = {}

    def part_of(self, handler) -> str:
        code = getattr(handler, "__code__", None) or getattr(getattr(handler, "__call__", None), "__code__", None)
        where = os.path.realpath(code.co_filename) if code is not None else ""
        for part, home in self.homes.items():
            if where.startswith(home):
                return part
        raise FeedError(f"the handler in {where or 'an unknown file'} is no part's that reads the feed: nothing was handed")

    def wants(self, part: str, ev: dict) -> bool:
        return ev.get("doc_type") in self.reads.get(part, ())

    @staticmethod
    def key(feed) -> tuple:
        """One shop's feed, whichever part opened it: the transport, the shop's address, the door or the application."""
        api = getattr(feed, "api", None)
        return (type(feed).__name__, getattr(api, "base", None) or id(feed), getattr(feed, "prefix", None),
                getattr(feed, "app", None))

    def _shop(self, feed, limit: int) -> dict:
        with self._lock:
            shop = self.shops.setdefault(self.key(feed), {"lock": threading.Lock(), "read": False, "feed": feed,
                                                          "events": [], "stores": {}, "backlog": 0, "handed": {}})
        with shop["lock"]:
            if not shop["read"]:
                events, ids, page = [], set(), None
                while True:
                    got, nxt, backlog = feed.events(limit, page)
                    new = [e for e in got if e["id"] not in ids]
                    events += new
                    ids |= {e["id"] for e in new}
                    shop["backlog"] = backlog
                    if not new or nxt is None:      # the last page, or a page that came back again
                        break
                    page = nxt                      # nothing is marked done while reading: the offset stays true
                kept = (self.ledger.get(self.record(feed)) or {}).get("events") or {} if self.ledger is not None else {}
                shop["handed"] = {i: set(parts) for i, parts in kept.items() if i in ids}
                shop["kept"] = kept
                shop["events"], shop["read"] = events, True
        return shop

    def record(self, feed) -> str:
        """The name of a shop's lasting record of its waiting events, in the app's shops store."""
        import hashlib
        return HANDOFF_RECORD + hashlib.sha256(repr(self.key(feed)).encode()).hexdigest()[:24]

    def poll(self, feed, store, handler, limit: int = 100) -> dict:
        """One part's pass over one shop: the events read once for this run, each handed to the part when it wants it."""
        part = self.part_of(handler)
        path = getattr(store, "path", None)
        if not path:
            raise FeedError(f"{part}: its store has no path, so whether it handled an event cannot be read: nothing was handed")
        shop = self._shop(feed, limit)
        shop["stores"][part] = path
        n = {"handled": 0, "skipped_seen": 0, "failed": 0, "done": 0, "part": part}
        for ev in shop["events"]:
            if not self.wants(part, ev):
                continue
            mine = dict(ev, id=f"{part}|{ev['id']}")
            if part in shop["handed"].get(ev["id"], ()) or store.seen(mine["id"]) \
                    or (len(self.reads) == 1 and store.seen(ev["id"])):     # an app's one reader, before the hand-off
                n["skipped_seen"] += 1
                continue
            try:
                store.handled(mine, lambda db, ev=ev: handler(dict(ev), db))
            except Exception as e:      # the part's own failure: the event stays undone, with the part's note
                feed.failed(ev["id"], f"{part}: {type(e).__name__}: {e}")
                n["failed"] += 1
                continue
            n["handled"] += 1
        n["backlog"] = shop["backlog"]
        return n

    def _seen(self, shop: dict) -> dict:
        """{part: the ids it recorded as seen} among this run's events, read with a connection of this thread's own."""
        out = {}
        for part, path in shop["stores"].items():
            want = [f"{part}|{ev['id']}" for ev in shop["events"] if self.wants(part, ev)]
            db = sqlite3.connect("file:" + urllib.request.pathname2url(path) + "?mode=ro", uri=True, timeout=10)
            try:
                got = set()
                for i in range(0, len(want), 500):
                    chunk = want[i:i + 500]
                    got |= {r[0] for r in db.execute(f"select id from seen where id in ({','.join('?' * len(chunk))})",
                                                     chunk)}
            finally:
                db.close()
            out[part] = got
        return out

    def finish(self) -> dict:
        """Mark done each event of this run that every part wanting it has handled; the others stay for the next run."""
        out = {"done": 0, "waiting": 0, "errors": 0}
        with self._lock:
            shops = [s for s in self.shops.values() if s["read"]]
        for shop in shops:
            try:
                seen = self._seen(shop)
                by = {ev["id"]: {p for p in self.reads if f"{p}|{ev['id']}" in seen.get(p, ())} | shop["handed"].get(ev["id"], set())
                      for ev in shop["events"]}
                ids = [ev["id"] for ev in shop["events"]
                       if all(p in by[ev["id"]] for p in self.reads if self.wants(p, ev))]
                out["waiting"] += len(shop["events"]) - len(ids)
                if self.ledger is not None:     # written before anything is marked done: a lost write marks nothing
                    waiting = {i: sorted(parts) for i, parts in by.items() if parts and i not in set(ids)}
                    if waiting != {i: sorted(v) for i, v in shop["kept"].items()}:
                        name = self.record(shop["feed"])
                        self.ledger.put(name, {"events": waiting}) if waiting else self.ledger.delete(name)
                for i in range(0, len(ids), 100):
                    out["done"] += shop["feed"].done(ids[i:i + 100])
            except Exception:           # noqa: BLE001 — one shop's failure never stops the others: its events stay undone
                out["errors"] += 1
        return out


def queued_docs(feed, limit: int = 500) -> set[tuple[str, str]]:
    """(record type, record) of every event still not done — read only, nothing is marked."""
    out, page = set(), None
    while True:
        events, nxt, _ = feed.events(limit, page)
        out |= {(e["doc_type"], e["doc_name"]) for e in events}
        if nxt is None or not events:
            return out
        page = nxt


def began(api: Api, store: Store, doctype: str) -> str | None:
    """When this seen-set began, on the SHOP's clock: the ``creation`` of the newest submitted ``doctype`` record at
    that moment, kept once in the seen-set's own file (None when the shop held none). It belongs to the folder, not
    to a record type: it is the shop's own time, and ``reconcile`` of any type compares with it. A working folder that is lost
    (a container restarted, a disk replaced) starts an empty seen-set, so a record created at or before this moment
    that the new seen-set never saw delivered may have been handled before the loss: ``reconcile`` names it
    ``unknown``, not ``missing``. The marker is compared with the record's own ``creation``, so no clock of yours is
    involved. A folder that already holds seen events never lost its list and takes none. Call it once before your
    first poll (the ``run`` command does); ``reconcile`` calls it too, which dates the marker from that night."""
    db = store.db
    db.execute("create table if not exists feed_client_meta (k text primary key, v text)")
    row = db.execute("select v from feed_client_meta where k='began'").fetchone()
    if row is None:
        got = []
        if db.execute("select 1 from seen limit 1").fetchone() is None:
            got = api.call("GET", f"/api/resource/{urllib.parse.quote(doctype)}", {
                "filters": json.dumps([["docstatus", "=", 1]]), "fields": json.dumps(["creation"]),
                "order_by": "creation desc", "limit_page_length": 1}).get("data", [])
        db.execute("insert or ignore into feed_client_meta values ('began', ?)", (got[0]["creation"] if got else "",))
        row = db.execute("select v from feed_client_meta where k='began'").fetchone()
    return row[0] or None


def reconcile(api: Api, store: Store, doctype: str, since: str, feed=None,
              events=("sale.booked", "return.booked")) -> dict:
    """The nightly pass: every submitted record of ``doctype`` CREATED since ``since`` that the feed never delivered.
    Run it right after a pass that ended with backlog 0. A record whose event is still in the queue (late, or `failed`
    and waiting) is reported as ``still_queued``, not as missing. A record created at or before the moment this
    seen-set began (``began``) is ``unknown`` — with ``unknown_why`` — not ``missing``: it may have been handled before
    the folder was lost, so look at it in the shop. Every undelivered record is named in one of the lists, never
    silently. What is missing, act on through a handler keyed on the RECORD (not the event id) — the seen-set does not
    know it."""
    rows = api.call("GET", f"/api/resource/{urllib.parse.quote(doctype)}", {
        "filters": json.dumps([["docstatus", "=", 1], ["creation", ">=", since]]),
        "fields": json.dumps(["name", "creation"]), "limit_page_length": 0}).get("data", [])
    booked = {r["name"]: r.get("creation") or "" for r in rows}
    queued = {d for t, d in queued_docs(feed) if t == doctype} if feed else set()
    undelivered = set(booked) - store.delivered(doctype, tuple(events))
    cut = began(api, store, doctype)
    unknown = {n for n in undelivered - queued if cut and booked[n] and booked[n] <= cut}
    out = {"doctype": doctype, "since": since, "booked": len(booked),
           "missing": sorted(undelivered - queued - unknown), "unknown": sorted(unknown),
           "still_queued": sorted(undelivered & queued)}
    if unknown:
        out["unknown_why"] = ("created before this working folder began, so a delivery cannot be told from its absence: "
                              "each may have been handled, check it in the shop")
    return out


def sample_handler(ev, db):
    """The sample handler: record the event in the partner's own table, inside the same transaction as the seen-set.
    A real one writes its own business rows here (and may call the API to read the record the event names)."""
    db.execute("create table if not exists collected (id text, event text, doc_type text, doc_name text, at text)")
    db.execute("insert into collected values (?,?,?,?,?)", (ev["id"], ev["event"], ev["doc_type"], ev["doc_name"],
                                                             ev.get("at")))


def _feed(args, api):
    return DoorFeed(api, args.door_prefix) if args.transport == "door" else EngineFeed(api, args.app)


def main(argv=None):
    p = argparse.ArgumentParser(description="iVendNext event-feed reference client")
    p.add_argument("command", choices=("run", "backlog", "reconcile", "dump"))
    p.add_argument("--base", required=True)
    p.add_argument("--app", help="the Registered Application's name (engine transport)")
    p.add_argument("--transport", choices=("engine", "door"), default="door")
    p.add_argument("--door-prefix", default="ivendnext_mpos.api.feed")
    p.add_argument("--state", default="state/feed.sqlite")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--crash-after", type=int, help="test only: exit after handling N events, before marking done")
    p.add_argument("--since")
    p.add_argument("--doctype", default="POS Invoice")
    p.add_argument("--watch", type=float, help="poll again every N seconds (a service); default: one pass")
    a = p.parse_args(argv)
    key, secret = os.environ.get("FEED_KEY"), os.environ.get("FEED_SECRET")
    if not key or not secret:
        sys.exit("set FEED_KEY and FEED_SECRET in the environment")
    if a.transport == "engine" and not a.app:
        sys.exit("--app is required with --transport engine")
    api, store = Api(a.base, key, secret), Store(a.state)
    if a.command == "dump":       # the sample handler's table, one JSON line per row (duplicates would show)
        store.db.execute("create table if not exists collected (id text, event text, doc_type text, doc_name text, at text)")
        for r in store.db.execute("select id, event, doc_type, doc_name, at from collected order by rowid"):
            print(json.dumps(dict(zip(("id", "event", "doc_type", "doc_name", "at"), r))))
        return
    if a.command == "backlog":
        print(json.dumps({"backlog": _feed(a, api).backlog()}))
    elif a.command == "reconcile":
        if not a.since:
            sys.exit("--since is required")
        print(json.dumps(reconcile(api, store, a.doctype, a.since, _feed(a, api))))
    else:
        while True:
            try:
                began(api, store, a.doctype)     # before any event is handled in a fresh folder; a no-op after the first
            except FeedError:                    # a key that follows other record types may not read this one: no marker
                pass
            print(json.dumps(poll(_feed(a, api), store, sample_handler, a.limit, a.crash_after)), flush=True)
            if not a.watch:
                break
            time.sleep(a.watch)


if __name__ == "__main__":
    try:
        main()
    except FeedError as e:
        sys.exit(f"FEED_ERROR {e}")
