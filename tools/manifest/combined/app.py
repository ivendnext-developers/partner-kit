#!/usr/bin/env python3
"""This app's one service: it sends each call to the part of the app that answers it.

Written by New app (the kit's ``tools/manifest/start.py``) for an app made from one or more of the kit's samples. Each
sample's part sits in ``service/<tag>/``, as the sample was, and answers its own routes under ``/<tag>/``; this file
reads ``service/dispatch.json`` (which part answers which routes) and sends each call there:

    GET  /health                       200 {"status": "ok"}
    POST /<tag>/...                    the part with that tag (its own signature check, its own test call); a
                                       sample whose own routes did not start with /<tag>/ gets the call with
                                       /<tag> taken off, as it answered on its own
    POST /ivendnext/connect|disconnect the site connects the app once; every part reads the same shops store
    anything else                      404

As a function on CitiXsys hosting it is ``service/app.lambda_handler`` (``app.json`` ``"handler"``); a schedule named
``<tag>-<name>`` (``schedules`` in dispatch.json) runs that part's ``<name>``.

The app reads its one feed once. The schedule ``feed`` (``feed`` in dispatch.json) runs the parts that read the site's
new sales and customers, one after another, each handed only the events of the record types its own sample registered
(``_kit/feed_client`` ``Handoff``); an event is marked done on the site only once every part that wants it has handled
it, and a part that already handled it is never run again for it.

On a server or a laptop it is a small web server:

    python3 service/app.py            the port in PORT (default 8080)
    python3 service/app.py --local    reads ../.env.local, answers on http://localhost:8000, and accepts a call from the
                                      site ``localhost`` signed with IVN_TEST_SECRET (send X-iVendNext-Test: 1 to test a
                                      connection point without a sale)

One log line per call (``_kit/calllog.py``): the site, the connection point in plain words, the outcome, the sale. Never
the body, a secret or a signature. Leave this file and ``dispatch.json`` to the tool: *Add a sample* updates them.
Standard library only.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
KIT = os.path.join(HERE, "_kit")
sys.path.insert(0, KIT)
import calllog  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

with open(os.path.join(HERE, "dispatch.json"), encoding="utf-8") as _f:
    DISPATCH = json.load(_f)
MOUNTS = DISPATCH["mounts"]
KIT_MODULES = {os.path.splitext(n)[0] for n in os.listdir(KIT) if n.endswith(".py")}
LOCAL_PORT, LOCAL_SITE = 8000, "localhost"
_parts: dict = {}
_lock = threading.RLock()


def _load(tag: str):
    """The part, imported once: its function handler, the modules it loaded and the folders it put on the path. Each part
    gets its own copy of the kit's helpers (so its point names map to the app's, ``shops.ALIASES``) and its prefix setting
    filled in (never shown to the developer). Afterwards the process is as it was: the part's modules and folders are
    put back only while the part answers a call (``_call``), so one part never finds another's ``app`` or ``worker``."""
    if tag in _parts:
        return _parts[tag]
    m = MOUNTS[tag]
    os.environ[m["prefix_setting"]] = m["prefix"]
    before_modules, before_path = dict(sys.modules), list(sys.path)
    for name in KIT_MODULES:                               # a fresh copy of each helper for this part
        sys.modules.pop(name, None)
    try:
        import shops as part_shops                          # noqa: F811 — this part's own copy
        part_shops.ALIASES.clear()
        part_shops.ALIASES.update(m.get("aliases") or {})
        path, _, attr = m["handler"].rpartition(".")
        file = os.path.join(HERE, *path.split("/")) + ".py"
        sys.path.insert(0, os.path.dirname(file))
        spec = importlib.util.spec_from_file_location(f"ivn_part_{tag}", file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = getattr(module, attr)
        own = {n: mod for n, mod in sys.modules.items() if before_modules.get(n) is not mod}
        # the part's code imports its own service by its file's name (``import app`` in a worker): that name is the part's
        own.setdefault(os.path.splitext(os.path.basename(file))[0], module)
        own_path = [q for q in sys.path if q not in before_path]
    finally:
        for n in [n for n in sys.modules if n not in before_modules]:
            sys.modules.pop(n, None)
        sys.modules.update(before_modules)
        sys.path[:] = before_path
    _parts[tag] = (handler, own, own_path)
    return _parts[tag]


def _call(tag: str, event, context=None):
    """One call or scheduled run of a part, with its own modules and folders in place, one at a time. A module of the
    part's (or a copy of the kit's helpers) that it first imports during a call is kept as its own, for its calls only."""
    with _lock:
        handler, own, own_path = _load(tag)
        saved = {n: sys.modules.get(n) for n in own}
        before = set(sys.modules)
        saved_path = list(sys.path)
        sys.modules.update(own)
        sys.path[:0] = own_path
        try:
            return handler(event, context)
        finally:
            roots = tuple(os.path.realpath(r) + os.sep for r in (os.path.join(HERE, tag), KIT))
            for n in [n for n in sys.modules if n not in before and n not in own]:
                if os.path.realpath(getattr(sys.modules[n], "__file__", None) or os.sep).startswith(roots):
                    own[n] = sys.modules.pop(n)
            for n, mod in saved.items():
                if mod is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = mod
            sys.path[:] = saved_path


ROUTES = {path: tag for tag, m in MOUNTS.items() for path in (m.get("points") or {})}
FEED = DISPATCH.get("feed") or {}
READERS = FEED.get("parts") or {}           # the parts that read the feed: tag -> {"pass": its pass, "reads": record types}
HANDOFF_MODULE = "ivn_feed_handoff"         # feed_client.HANDOFF_MODULE: where every part's poll finds the one reader


def _handoff():
    """The app's one reader, put where every part's ``feed_client.poll`` finds it, for as long as the process lives: a
    part's poll is always handed, never a pass of its own that would mark the others' events done. None when no part
    reads the feed, or the reader's code is missing (then no reading part is run)."""
    if not READERS:
        return None
    path = os.path.join(KIT, "feed_client", "feed_client.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(HANDOFF_MODULE, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[HANDOFF_MODULE] = module
    spec.loader.exec_module(module)
    module.HUB = module.Handoff({t: p.get("reads") or [] for t, p in READERS.items()},
                                {t: os.path.join(HERE, t) for t in READERS}, _Ledger())
    return module.HUB


class _Ledger:
    """The reader's lasting record of the events still waiting for a part: the app's shops store (the table on hosting,
    the file on a laptop), opened when first needed. With neither set, there is none and the seen-list alone counts."""

    def __init__(self):
        self.store = None

    def _open(self):
        if self.store is None:
            if not ((os.environ.get("IVN_SHOPS_TABLE") or "").strip() or (os.environ.get("IVN_SHOPS_FILE") or "").strip()):
                return None
            self.store = shops.open_store(os.environ)
        return self.store

    def get(self, name):
        store = self._open()
        return store.get(name) if store is not None else None

    def put(self, name, record):
        if self._open() is not None:
            self.store.put(name, record)

    def delete(self, name):
        if self._open() is not None:
            self.store.delete(name)


class _Share:
    """The call's time as one part's pass sees it: an equal share of what is left, less the minute a pass waits beyond
    its time, so every part runs and the reader marks done before the call ends."""

    def __init__(self, context, parts_left: int):
        left = context.get_remaining_time_in_millis() if hasattr(context, "get_remaining_time_in_millis") else 900_000
        self.ms = max(5_000, (left - 30_000) // max(1, parts_left) - 60_000)
        self.context = context

    def get_remaining_time_in_millis(self):
        return self.ms

    def __getattr__(self, name):
        return getattr(self.context, name)


HUB = _handoff()


def feed_pass(context=None) -> dict:
    """One run of the app's one reader: each reading part's own scheduled pass in turn, handed the events its sample
    registered; then each event that every part wanting it has handled is marked done."""
    if HUB is None:
        return {"feed": {"error": "the feed's reader (service/_kit/feed_client) is missing: nothing was read"}}
    HUB.begin()
    out = {}
    for n, (tag, p) in enumerate(READERS.items()):
        if not (MOUNTS.get(tag) or {}).get("handler"):
            out[tag] = {"error": "this part has no service"}
            continue
        try:
            out[tag] = _call(tag, {"ivn_schedule": p.get("pass") or "pass"}, _Share(context, len(READERS) - n))
        except Exception as e:      # noqa: BLE001 — one part's failure: its events stay undone, the others go on
            out[tag] = {"error": type(e).__name__}
    out["feed"] = HUB.finish()
    return out


def _tag(path: str) -> str | None:
    """The part that answers a path: the one whose connection point it is, else the one mounted under its first word."""
    path = path.split("?", 1)[0]
    if path in ROUTES:
        return ROUTES[path]
    first = path.strip("/").split("/", 1)[0]
    return first if first in MOUNTS else None


def _inside(tag: str, event: dict) -> dict:
    """The call as the part answers it: under its own route when it was mounted under /<tag>/."""
    if not MOUNTS[tag].get("strip"):
        return event
    path = event.get("path") or "/"
    return {**event, "path": path[len(tag) + 1:] or "/"}


def _point(path: str) -> tuple[str, str]:
    for m in MOUNTS.values():
        p = (m.get("points") or {}).get(path.split("?", 1)[0])
        if p:
            return calllog.plain(p["kind"], p["key"]), p["key"]
    return "a call", ""


def lambda_handler(event, context=None):
    """The function's handler: a call goes to its part; a schedule ``<tag>-<name>`` (``schedules`` in dispatch.json) runs that part's ``<name>``."""
    if isinstance(event, dict) and "ivn_schedule" in event:
        tag, name = (DISPATCH.get("schedules") or {}).get(str(event["ivn_schedule"])) or [None, None]
        if str(event["ivn_schedule"]) == FEED.get("schedule") or (tag in READERS and name == READERS[tag].get("pass")):
            out = feed_pass(context)
            print(json.dumps({"schedule": event["ivn_schedule"], "feed": out.get("feed")}, default=str), flush=True)
            return {"schedule": event["ivn_schedule"], **out}
        if tag not in MOUNTS or not MOUNTS[tag].get("handler"):
            return {"schedule": event["ivn_schedule"], "error": "no part has this schedule"}
        return _call(tag, {"ivn_schedule": name}, context)
    t0 = time.monotonic()
    method, path, headers, raw = function.request(event)
    status, out = 404, None
    try:
        if method == "GET" and path == "/health":
            status, out = 200, function.response(200, {"status": "ok"})
            return out
        tag = _tag(path)
        if path in (shops.CONNECT, shops.DISCONNECT):
            tag = next((t for t, m in MOUNTS.items() if m.get("handler")), None)   # one store: any part with a service
        if tag is None or not MOUNTS[tag].get("handler"):     # no part answers it (a part may have no service)
            status, out = 404, function.response(404, {"error": "no such route"})
            return out
        out = _call(tag, _inside(tag, event) if path not in (shops.CONNECT, shops.DISCONNECT) else event, context)
        status = int(out.get("statusCode") or 500) if isinstance(out, dict) else 500
        return out
    finally:
        if method != "GET":
            record = None
            try:
                record = calllog.record_of((json.loads(raw) or {}).get("context"))
            except (ValueError, AttributeError):
                pass
            point, _ = _point(path)
            print(calllog.line(shops.site_of(headers.get(shops.SITE_HEADER)), point, status, time.monotonic() - t0, record,
                               (headers.get("X-iVendNext-Request-Id") or "-")[:40], testcall.is_test(headers)), flush=True)


def _event(method: str, path: str, headers, raw: bytes) -> dict:
    return {"httpMethod": method, "path": path, "headers": {k: v for k, v in headers.items()},
            "body": base64.b64encode(raw).decode(), "isBase64Encoded": True}


def make_server(port: int, host: str = "0.0.0.0"):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _answer(self, method: str, raw: bytes):
            out = lambda_handler(_event(method, self.path, self.headers, raw))
            body = (out.get("body") or "").encode()
            self.send_response(int(out.get("statusCode") or 500))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._answer("GET", b"")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > 64 * 1024:
                return self._answer("POST", b"x" * (64 * 1024 + 1))
            self._answer("POST", self.rfile.read(n))

        def log_message(self, fmt, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def local_settings(env) -> dict:
    """``--local``: the folder's ``.env.local`` under the process's own settings, and the site ``localhost`` connected
    with IVN_TEST_SECRET for every connection point, in a shops file under ``.local/`` (never a real secret)."""
    out = dict(env)
    path = os.path.join(APP_ROOT, ".env.local")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                name, sep, val = line.strip().partition("=")
                if sep and name and not name.startswith("#"):
                    out.setdefault(name.strip(), val.strip().strip('"'))
    secret = (out.get("IVN_TEST_SECRET") or "").strip()
    if not secret:
        raise SystemExit(f"--local reads IVN_TEST_SECRET from {path}: write one there (any long random text)")
    out.setdefault("PORT", str(LOCAL_PORT))
    out["IVN_LOCAL"] = "1"
    out.setdefault("IVN_LIBRARY_APP", DISPATCH["app"])
    store = out.get("IVN_SHOPS_FILE") or os.path.join(".local", "shops.json")
    store = store if os.path.isabs(store) else os.path.join(APP_ROOT, store)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    out["IVN_SHOPS_FILE"] = store
    for name in ("PP_STATE",):
        if out.get(name) and not os.path.isabs(out[name]):
            out[name] = os.path.join(APP_ROOT, out[name])
            os.makedirs(out[name], exist_ok=True)
    app = out["IVN_LIBRARY_APP"]
    names = {}
    for m in MOUNTS.values():
        for p in (m.get("points") or {}).values():
            names[f"{app}:sub:{p['key']}"] = secret
            names[f"{app}:{p['key']}"] = secret
    shops.FileStore(store, local=True).put(LOCAL_SITE, {"site": LOCAL_SITE, "url": f"http://{LOCAL_SITE}:{out['PORT']}",
                                                         "secrets": names, "previous": {}, "key_id": "local",
                                                         "kind": "free", "connected": "local"})
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    local = "--local" in argv
    if local:
        os.environ.update(local_settings(os.environ))
    port = int(os.environ.get("PORT") or (LOCAL_PORT if local else 8080))
    srv = make_server(port, "127.0.0.1" if local else "0.0.0.0")
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "parts": sorted(MOUNTS)}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
