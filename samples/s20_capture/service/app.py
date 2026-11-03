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

On CitiXsys hosting it runs as a FUNCTION for many sites (app.json; ``lambda_handler`` below): each site connects itself
(``shops.py``) and its calls name it. The codes are kept in the shops store, so any copy of the function checks a code another
sent. A code goes to your message gateway (CAP_MESSAGE_URL, posted {"phone", "code"}); with no gateway set, a customer is added
with no code.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAMPLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(SAMPLE)), "tools", "app_template", "service"))   # the test call
import capture  # noqa: E402
import function  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402


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
    KEYS = {"/cap/scan": "on_scan", "/cap/customer": "on_customer", "/cap/qty": "on_qty"}   # the manifest's subscription keys

    def __init__(self, conf: dict, send):
        self.secrets = {path: conf[key] for path, (key, _events) in self.PATHS.items()     # a missing scan or customer secret stops the
                        if key != "PP_POINT_SECRET_QTY" or conf.get(key)}           # start; the quantity one is optional (0.1.0's)
        self.conf, self.send, self.codes = capture.settings_from(conf), send, capture.Codes()

    def refusal(self, path: str, headers, raw: bytes) -> str:
        """Why this call is not the shop's, else nothing."""
        if path not in self.secrets:                    # a subscription this shop has not handed a secret for
            return "the signature does not match"
        return capture.verify(headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature"), raw,
                              self.secrets[path])

    def call(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        why = self.refusal(path, headers, raw)
        if why:
            return 401, {"error": why}
        if testcall.is_test(headers):                   # checked as a real call; the capture itself does not run
            return testcall.answer(self.KEYS[path])
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
            if not self.send and capture.phone(ctx["customer"].get("phone")):   # no gateway set: no way to send a code
                return 200, {"verdict": "allow"}
            return 200, capture.on_customer(ctx, self.conf, self.codes, self.send)
        return 200, capture.on_verify(ctx, self.codes)


class StoreCodes:
    """``capture.Codes``' two calls, kept in the shops store: a code sent by one copy of the function is checked by another."""

    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock

    def issue(self, challenge_id: str, number: str) -> str:
        code = capture.new_code()
        self.store.put(f"code{shops.CLAIM_MARK}{challenge_id}", {"code": code, "at": self.clock()})
        return code

    def check(self, challenge_id: str, code: str) -> str:
        name = f"code{shops.CLAIM_MARK}{challenge_id}"
        found = self.store.get(name)
        if not found or self.clock() - float(found.get("at") or 0) >= capture.CODE_TTL_S:
            return "unknown"
        if not hmac.compare_digest(str(found.get("code")), code):
            return "wrong"
        self.store.delete(name)
        return "ok"


def gateway(url: str):
    """The partner's own message gateway, posted the phone and the code."""
    def send(phone: str, code: str) -> None:
        req = urllib.request.Request(url, data=json.dumps({"phone": phone, "code": code}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2):
            pass
    return send


class Hosted(Service):
    """The same answers for many sites: the site the call names gives the secret for that address."""

    def __init__(self, conf: dict, store=None):
        self.app = oneshop.value(conf, oneshop.MANY)
        self.store = store or shops.open_store(conf)
        self.conf = capture.settings_from(conf)
        url = oneshop.value(conf, "CAP_MESSAGE_URL")
        self.send, self.codes = gateway(url) if url else None, StoreCodes(self.store)

    def refusal(self, path: str, headers, raw: bytes) -> str:
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, f"{self.app}:sub:{self.KEYS[path]}")
        why = "the signature does not match"
        for secret in secrets:
            why = capture.verify(headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature"), raw, secret.decode())
            if not why:
                return ""
        return why

    def handle(self, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if len(raw) > capture.BODY_MAX:
            return 413, {"error": "too large"}
        if path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.call(path, headers, raw) if path in self.PATHS else (404, {"error": "not found"})


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 1a): settings from the environment.
lambda_handler = function.entry(lambda: Hosted(dict(os.environ)), lambda svc, method, path, headers, raw: svc.handle(method, path, headers, raw))


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
