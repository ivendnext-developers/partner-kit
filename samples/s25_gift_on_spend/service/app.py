#!/usr/bin/env python3
"""S25 — the service: the feed worker beside a health address, for one shop or many (standard library only).

    GET  /health                    200 {"ok": 1}; many shops: 503 once no worker pass has finished for 3 minutes
    POST /ivendnext/connect         many shops: the app template's handshake (tools/app_template/service/shops.py)
    POST /ivendnext/disconnect

The shop never calls this service: it has no till key, no check and no webhook. Everything it does starts from the
shop's event feed, which it pulls (worker.py).

On CitiXsys hosting, many shops run as a FUNCTION on a schedule (app.json "runs": "function", "schedule";
``lambda_handler`` below): each scheduled call is one pass of the shops it can claim (the feed, then the releases due), so
nothing is billed while no shop has a sale to read. The claim keeps two copies from working one shop at once, as the
container's single copy did: two at once could release one held card twice.

    python3 service/app.py service/.env.local     # ONE SHOP: PP_BASE, PP_KEY, PP_SECRET, PP_STATE, PP_PORT (8156),
                                                  # GCS_PREFIX; the worker runs beside it every PP_WATCH seconds

MANY SHOPS (guide chapter 14b): set IVN_LIBRARY_APP (the App library's id, ivendnext_gcs) and a store (IVN_SHOPS_TABLE on
CitiXsys hosting, else IVN_SHOPS_FILE). Each shop connects itself after its install and hands over its integration
user's key ("user:<email>": "<api key>:<api secret>"); the worker then reads that shop's feed with that key. The handshake
and ``api_credentials`` are S22's (``samples/s22_customer_loyalty/service/app.py`` @ 3546aaf; a defect there may be a
defect here).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import cards  # noqa: E402
import function  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import worker  # noqa: E402
from shop import ShopError  # noqa: E402

BODY_MAX = 64 * 1024
HEALTH_GRACE_S = 180


def api_credentials(record: dict) -> tuple[str, str, str]:
    """(address, key, secret): the integration user's key the shop handed over at connect ("user:<email>")."""
    users = sorted(k for k in record.get("secrets") or {} if k.startswith("user:"))
    if not users or ":" not in record["secrets"][users[0]]:
        raise ShopError(0, "the shop has not handed over its integration user's key")
    key, secret = record["secrets"][users[0]].split(":", 1)
    return record["url"], key, secret


class Service:
    def __init__(self, conf: dict, store=None, keys=None, scheduled: bool = False):
        self.conf, self.keys, self.started, self.scheduled = conf, keys, time.monotonic(), scheduled
        self.app = oneshop.value(conf, oneshop.MANY)
        if conf.get("GCS_PREFIX"):
            cards.use_prefix(conf["GCS_PREFIX"].strip())
        self.store = (store or shops.open_store(conf)) if self.app else None

    def healthy(self) -> bool:
        if self.scheduled:                       # a function: each scheduled call is its own pass, logged as it ends
            return True
        stale = time.monotonic() - worker.HEARTBEAT[0] > HEALTH_GRACE_S
        return not (time.monotonic() - self.started > HEALTH_GRACE_S and stale)


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """One request, for the web server and the function alike."""
    if method == "POST":
        if len(raw) > BODY_MAX:
            return 413, {"error": "too large"}
        if svc.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(svc.store, svc.app, path, headers, raw, svc.keys)
        return 404, {"error": "not found"}
    if path != "/health":
        return 404, {"error": "not found"}
    if not svc.healthy():
        return 503, {"ok": 0, "why": "the feed worker has not finished a pass"}   # restart me
    return 200, {"ok": 1}


def scheduled(svc: Service, name: str, seconds: float = 900) -> dict:
    """One scheduled pass (the function's worker): the shops this call claims, each to its end, each claim freed as its
    shop finishes. A shop stuck past the call's limit ends the call; its claim is taken over once stale
    (``function.Claimed``)."""
    store = function.Claimed(svc.store, seconds)
    state = svc.conf.get("PP_STATE") or os.path.join(HERE, "state")
    # the wait outlasts the call: a shop still at work when the limit comes ends with the call, never thawed into the next
    return worker.pass_all(store, state, opener=worker.open_shop, deadline=seconds + 60, finished=store.release) or {}


lambda_handler = function.entry(lambda: Service(dict(os.environ), scheduled=True), handle, scheduled)


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > BODY_MAX:
                return self._send(413, {"error": "too large"})
            self._send(*handle(svc, "POST", self.path, self.headers, self.rfile.read(n)))

        def do_GET(self):
            self._send(*handle(svc, "GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):
            sys.stderr.write("s25 %s\n" % (fmt % args))   # the request line only: no header, no body, no secret

    return Handler


def run_one_shop(conf: dict):
    """One shop from the settings: the worker's pass every PP_WATCH seconds, its heartbeat for /health."""
    from shop import Shop
    import feed_client as F
    one = oneshop.settings(conf, ["PP_BASE", "PP_KEY", "PP_SECRET"])      # the fallback way: one shop on your own server
    t = Shop(one["PP_BASE"], one["PP_KEY"], one["PP_SECRET"])
    state = conf.get("PP_STATE") or os.path.join(HERE, "state")
    os.makedirs(state, exist_ok=True)
    seen = F.Store(os.path.join(state, "feed.sqlite"))
    feed = F.DoorFeed(F.Api(one["PP_BASE"], one["PP_KEY"], one["PP_SECRET"]))
    while True:
        try:
            print(json.dumps(worker.one_pass(t, feed, seen), default=str), flush=True)
            worker.HEARTBEAT[0] = time.monotonic()
        except Exception as e:                   # noqa: BLE001 — the worker never dies; /health says when it stalls
            print(json.dumps({"worker": type(e).__name__, "detail": str(e)[:200]}), flush=True)
        time.sleep(float(conf.get("PP_WATCH") or 30))


if __name__ == "__main__":
    conf = worker.env(sys.argv[1]) if sys.argv[1:] else dict(os.environ)      # hosting: the environment
    svc = Service(conf)
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8156)), make_handler(svc))
    target = (worker.serve_all, (svc.store, conf)) if svc.app else (run_one_shop, (conf,))
    threading.Thread(target=target[0], args=target[1], daemon=True).start()
    print(f"s25 gift card on spend on :{srv.server_port}" + (f", many shops ({svc.app})" if svc.app else ", one shop"),
          flush=True)
    srv.serve_forever()
