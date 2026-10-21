"""S20 — *Warranty capture and a member code*: the partner's service behind the shop's three capture subscriptions
(standard library only). Each subscription has its own address, so the address picks the secret the signature is checked
with before the body is read.

    POST /cap/scan      the shop's signed scan call (``capture/1``, event scan)
    POST /cap/customer  the shop's signed customer calls (event customer_add, then verify)
    POST /cap/qty       the shop's signed quantity calls (event qty_change; POS build 2.0.0.654 on)
    GET  /health        200 {"ok": 1}

The message gateway here is a STAND-IN: it appends ``{"phone", "code", "at"}`` to the file ``PP_OUTBOX`` (chmod 600),
where a partner calls its SMS or WhatsApp provider instead (``Outbox.send``). Nothing else is written, and a code is never
logged.

    python3 service/app.py service/.env.local
    env: PP_POINT_SECRET_SCAN, PP_POINT_SECRET_CUSTOMER, PP_POINT_SECRET_QTY (handed back at install as
         pp_cap:sub:on_scan, pp_cap:sub:on_customer and pp_cap:sub:on_qty), PP_LINE_ATTRIBUTE (the shop's active line
         attribute for the reference), PP_QTY_ASK_ABOVE (3) and PP_QTY_MOST (5) (handsets on a line),
         PP_BARRED_PHONES (comma list), PP_OUTBOX (the stand-in gateway's file), PP_PORT (8142)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAMPLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SAMPLE)
import capture  # noqa: E402


class Outbox:
    """The stand-in message gateway: one JSON line per code, in a file only this service's user can read."""

    def __init__(self, path: str):
        self.path, self._lock = path, threading.Lock()

    def send(self, phone: str, code: str) -> None:
        with self._lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (json.dumps({"phone": phone, "code": code, "at": int(time.time())}) + "\n").encode())
            finally:
                os.close(fd)


class Service:
    # each subscription has its own address here and its own secret: the path picks the secret, and the body is read
    # only after its signature holds
    PATHS = {"/cap/scan": ("PP_POINT_SECRET_SCAN", ("scan",)),
             "/cap/customer": ("PP_POINT_SECRET_CUSTOMER", ("customer_add", "verify")),
             "/cap/qty": ("PP_POINT_SECRET_QTY", ("qty_change",))}

    def __init__(self, conf: dict, send):
        self.secrets = {path: conf[key] for path, (key, _events) in self.PATHS.items()     # a missing scan or customer secret stops the
                        if key != "PP_POINT_SECRET_QTY" or conf.get(key)}           # start; the quantity one is optional (0.1.0's)
        self.conf, self.send, self.codes = capture.settings_from(conf), send, capture.Codes()

    def call(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if path not in self.secrets:                    # a subscription this shop has not handed a secret for
            return 401, {"error": "the signature does not match"}
        why = capture.verify(headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature"), raw,
                             self.secrets[path])
        if why:
            return 401, {"error": why}
        try:
            ctx = capture.context_of(json.loads(raw))
        except (ValueError, RecursionError) as e:
            return 400, {"error": str(e)[:200]}
        if ctx["event"] not in self.PATHS[path][1]:
            return 400, {"error": "this address does not answer that event"}
        if ctx["event"] == "scan":
            return 200, capture.on_scan(ctx, self.conf)
        if ctx["event"] == "qty_change":
            return 200, capture.on_qty(ctx, self.conf)
        if ctx["event"] == "customer_add":
            return 200, capture.on_customer(ctx, self.conf, self.codes, self.send)
        return 200, capture.on_verify(ctx, self.codes)


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
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if not 0 <= n <= capture.BODY_MAX:
                return self._send(413, {"error": "no length, or too large"})
            raw = self.rfile.read(n)
            if self.path in svc.PATHS:
                return self._send(*svc.call(self.path, self.headers, raw))
            self._send(404, {"error": "not found"})

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": 1})
            self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            sys.stderr.write("s20 %s\n" % (fmt % args))   # the request line only: no header, no body, no code

    return Handler


def env(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


if __name__ == "__main__":
    conf = env(sys.argv[1])
    svc = Service(conf, Outbox(conf["PP_OUTBOX"]).send)
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or 8142)), make_handler(svc))
    print(f"s20 capture on :{srv.server_port}", flush=True)
    srv.serve_forever()
