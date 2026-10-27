#!/usr/bin/env python3
"""S3 for many shops — the feed worker beside a health address and the App library's handshake (standard library only).

    GET  /health                    200 {"ok": 1}; 503 once no worker pass has finished for 3 minutes (restart me)
    POST /ivendnext/connect         the app template's handshake (tools/app_template/service/shops.py)
    POST /ivendnext/disconnect

The shop never calls this service with a sale: it has no till key, no check and no webhook. Everything it does starts
from each shop's event feed, which it pulls (worker.py).

On CitiXsys hosting it runs as a FUNCTION on a schedule (app.json "runs": "function", "schedule"; ``lambda_handler``
below): each scheduled call is one pass of the shops it can claim, so nothing is billed while no shop has a sale to read.

Settings, from the environment (names only in ``app.json``): IVN_LIBRARY_APP (the App library's id, ``ivendnext_pda``),
PDO_PREFIX (``IVENDNEXT PDA`` for the library's app), PP_STATE (a folder for each shop's handled-events note), and a
store: IVN_SHOPS_TABLE on CitiXsys hosting, else IVN_SHOPS_FILE. For one shop on your own server, run ``service.py``.
The server is S25's (``samples/s25_gift_on_spend/service/app.py`` @ 4128c03; a defect there may be a defect here).
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
import function  # noqa: E402
import service  # noqa: E402
import shops  # noqa: E402
import worker  # noqa: E402

BODY_MAX = 64 * 1024
HEALTH_GRACE_S = 180
CLAIM_STALE_S = 150    # above the function's timeout (app.json "timeout": 120): a pass stopped by it frees its shops


class Service:
    def __init__(self, conf: dict, store=None, keys=None, scheduled: bool = False):
        self.conf, self.keys, self.started, self.scheduled = conf, keys, time.monotonic(), scheduled
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        if not self.app:
            raise SystemExit("IVN_LIBRARY_APP is not set: for one shop, run service.py")
        if conf.get("PDO_PREFIX"):
            service.use_prefix(conf["PDO_PREFIX"].strip())
        self.store = store or shops.open_store(conf)
        state = conf.get("PP_STATE") or os.path.join(HERE, "state")
        try:                                     # every shop's note lives here: a folder it cannot write serves no shop
            os.makedirs(state, exist_ok=True)
            with open(os.path.join(state, ".write-probe"), "w") as f:
                f.write("ok")
        except OSError as e:
            raise SystemExit(f"PP_STATE {state} is not writable ({type(e).__name__}): set it to the scratch folder")

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
        if path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(svc.store, svc.app, path, headers, raw, svc.keys)
        return 404, {"error": "not found"}
    if path != "/health":
        return 404, {"error": "not found"}
    if not svc.healthy():
        return 503, {"ok": 0, "why": "the feed worker has not finished a pass"}
    return 200, {"ok": 1}


def scheduled(svc: Service, name: str) -> dict:
    """One scheduled pass (the function's worker): the shops this call claims, each to its end, then their claims freed.
    A shop stuck past the function's timeout ends the call; its claim goes stale in CLAIM_STALE_S."""
    store = function.Claimed(svc.store, CLAIM_STALE_S)
    state = svc.conf.get("PP_STATE") or os.path.join(HERE, "state")
    out = worker.pass_all(store, state, opener=worker.open_shop, deadline=900.0) or {}   # to its end
    store.release(out)
    return out


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
            sys.stderr.write("s3 %s\n" % (fmt % args))   # the request line only: no header, no body, no secret

    return Handler


if __name__ == "__main__":
    conf = dict(os.environ)
    svc = Service(conf)
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PORT") or 8080)), make_handler(svc))
    threading.Thread(target=worker.serve_all, args=(svc.store, conf), daemon=True).start()
    print(f"s3 price-deviation audit on :{srv.server_port}, many shops ({svc.app}, {service.DT})", flush=True)
    srv.serve_forever()
