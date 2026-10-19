"""A deployable app: one signed route, one health route, standard library only.

    POST /point/hello          the remote till key's call (signed by iVendNext)   -> 200 {"message": {...}}
    GET  /health               is the process up                                   -> 200 {"status": "ok"}
    POST /ivendnext/connect    a shop's site hands over its library key and secrets (many shops; shops.py)
    POST /ivendnext/disconnect the shop is uninstalled: forget it

It runs in one of two ways. Settings come from the environment, never from a file in the image:
  ONE SHOP — you hold its secret:
    IVN_POINT_SECRET            the signing secret you and the shop both hold
    IVN_POINT_SECRET_PREVIOUS   optional — the old secret, accepted while you rotate (see the chapter)
  MANY SHOPS — each connects itself after it installs your app from the App library (guide chapter 14b):
    IVN_LIBRARY_APP             your app's id in the App library (the key names it), e.g. ivendnext_lyl
    IVN_SHOPS_TABLE             on CitiXsys hosting: the app's own shops table (set by the hosting)
    IVN_SHOPS_FILE              elsewhere: a JSON file the app may write (tests, your laptop, your own server)
    Each call then names its shop (X-iVendNext-Site) and is checked with that shop's secret for this route,
    the one the install made for your till key: "<IVN_LIBRARY_APP>:<KEY>". A site the app does not know gets 401.
  PORT                          optional — default 8080

Every call is verified against the RAW body before it is parsed: base64(HMAC-SHA256(secret, "<timestamp>.<raw body>")),
a timestamp within five minutes of your clock. The same check as samples/s6_ai_till_key/service.py (a defect there is a
defect here). One log line per request: the request id, the status, the milliseconds. Never the body, the context, the
secret or the signature.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

BODY_MAX, SKEW_S, ROUTE = 64 * 1024, 300, "/point/hello"
KEY = "hello"           # the till key's name in your manifest (remote_keys[].key); its secret is "<app>:<key>"
CONNECT, DISCONNECT, SITE = shops.CONNECT, shops.DISCONNECT, shops.SITE_HEADER


def verified(secrets: list, headers, raw: bytes) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:   # "²" is a digit int() refuses
        return False
    for secret in secrets:
        want = base64.b64encode(hmac.new(secret, ts.encode() + b"." + raw, hashlib.sha256).digest())
        if hmac.compare_digest(want, sig.encode()):
            return True
    return False


def settings(env) -> dict:
    port = int(env.get("PORT") or 8080)
    app = (env.get("IVN_LIBRARY_APP") or "").strip()
    if app:
        return {"app": app, "store": shops.open_store(env), "port": port}
    secret = (env.get("IVN_POINT_SECRET") or "").strip()
    if not secret:
        raise SystemExit("neither IVN_POINT_SECRET (one shop) nor IVN_LIBRARY_APP (many shops) is set: "
                         "the app does not start without a way to check a call")
    previous = (env.get("IVN_POINT_SECRET_PREVIOUS") or "").strip()
    return {"secrets": [s.encode() for s in (secret, previous) if s], "port": port}


def call_secrets(conf: dict, headers) -> list:
    """What this call may be signed with: one shop's secret, or the shop the call names."""
    if "secrets" in conf:
        return conf["secrets"]
    site = shops.site_of(headers.get(SITE))
    return shops.secrets_for(conf["store"].get(site), f"{conf['app']}:{KEY}") if site else []


def handle(conf: dict, method: str, path: str, headers, raw: bytes | None, log=sys.stdout) -> tuple[int, dict]:
    """One call: (status, answer). The web server below and the function entry (``function.py``) both call this."""
    t0, rid, code = time.monotonic(), (headers.get("X-iVendNext-Request-Id") or "-")[:40], 500
    try:
        if method == "GET":
            code, out = (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
            return code, out
        if raw is None or len(raw) > BODY_MAX:      # None: the web server saw a length it will not read
            code = 413
            return code, {"error": "too large"}
        if "store" in conf and path in (CONNECT, DISCONNECT):
            code, out = shops.handle(conf["store"], conf["app"], path, headers, raw, conf.get("keys"))
            return code, out
        try:
            secrets = call_secrets(conf, headers)
        except Exception as e:      # noqa: BLE001 — the store did not answer: nothing was checked
            log.write(json.dumps({"request": rid, "error": type(e).__name__}) + "\n")
            code = 503
            return code, {"error": "unavailable"}
        if not verified(secrets, headers, raw):
            code = 401
            return code, {"error": "bad signature"}
        if path != ROUTE:
            code = 404
            return code, {"error": "no such route"}
        try:
            context = json.loads(raw)["context"]
            result = core.answer(context)
        except Exception as e:      # noqa: BLE001 — log the class only: a message can carry shop data
            log.write(json.dumps({"request": rid, "error": type(e).__name__}) + "\n")
            code = 400
            return code, {"error": "bad request"}
        code = 200
        return code, result
    finally:
        if method != "GET":
            log.write(json.dumps({"request": rid, "status": code, "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
            log.flush()


def make_server(conf: dict, port: int | None = None, log=sys.stdout):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(*handle(conf, "GET", self.path, self.headers, b"", log))

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > BODY_MAX:
                return self._send(*handle(conf, "POST", self.path, self.headers, None, log))
            self._send(*handle(conf, "POST", self.path, self.headers, self.rfile.read(n), log))

        def log_message(self, fmt, *args):  # the framework's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", conf["port"] if port is None else port), Handler)


def main():
    conf = settings(os.environ)
    srv = make_server(conf)
    # A platform stops a container with SIGTERM: finish the call in hand, then exit 0.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


# As a function on CitiXsys hosting (app.json "runs": "function", "handler": "service/app.lambda_handler"; chapter 14b).
lambda_handler = function.entry(lambda: settings(os.environ), handle)


if __name__ == "__main__":
    main()
