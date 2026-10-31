"""S17 — the partner's order board, framed by the shop on the till (a sheet over the sale) and in Desk (a page).
Standard library only.

    GET  /board/             the page itself (``board.html``); the shop opens it with ``#ctx=…`` in the address
    POST /board/api/open     {ctx}                  → where it was opened, checked (signature · expiry · nonce once)
    POST /board/api/answer   {ctx, delivery_order}  → the till's answer, sent ONCE to the shop, server to server

The answer goes from THIS server to the shop's ``ivendnext_mpos.api.page.submit``, signed with the page's secret —
never from the browser, which never holds the secret. The service refuses a second answer for one context itself,
and the shop refuses it again (``This page has already answered.``): two locks, either is enough.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` and the caller sends ``X-PP-Admin``:
``POST /test/once`` switches the service's own one-answer check off or on (the bench proves the shop still refuses)
and ``GET /test/opened`` lists the contexts opened. A partner's copy deletes them.

    python3 service/app.py service/.env.local
    env: PP_BASE (the shop), PP_PAGE_SECRET (handed back at install as pp_pge:sub:board), PP_ADMIN_TOKEN, PP_PORT (8132)
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import page  # noqa: E402

SUBMIT = "/api/method/ivendnext_mpos.api.page.submit"
BODY_MAX = 32 * 1024


def shop_words(raw: bytes) -> str:
    """The sentence the shop refused with, from its error body (its own words, never ours)."""
    try:
        data = json.loads(raw or b"{}")
        for m in json.loads(data.get("_server_messages") or "[]"):
            text = json.loads(m).get("message") if isinstance(m, str) else None
            if text:
                return text
        return (data.get("exception") or "").split(": ", 1)[-1] or "refused"
    except ValueError:
        return "refused"


class Board:
    def __init__(self, conf: dict, post=None):
        self.base, self.secret = conf["PP_BASE"].rstrip("/"), conf["PP_PAGE_SECRET"]
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)
        self.opened, self.answered = page.OnceSet(), page.OnceSet()
        self.check_once, self.log = True, []
        self._post = post or self._http_post
        self._lock = threading.Lock()

    def _http_post(self, url: str, body: bytes, headers: dict) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError, http.client.HTTPException):     # unreachable, timed out (TimeoutError is an OSError) or cut short
            return 0, b""                             # the caller releases the claim; the shop's own once-check still holds

    def open(self, data: dict) -> tuple[int, dict]:
        payload, why = page.read_context(data.get("ctx"), self.secret)
        if not payload:
            return 403, {"error": why}
        if not self.opened.claim(payload["nonce"], payload["exp"]):
            return 403, {"error": "this page was already opened; open it again from the shop"}
        if self.test_modes:
            self.log = (self.log + [payload])[-20:]
        out = {"where": page.where(payload), "theme": payload.get("theme")}
        if out["where"]["on"] == "till":
            out["delivery_order"] = page.delivery_order(payload["nonce"])
        return 200, out

    def answer(self, data: dict) -> tuple[int, dict]:
        payload, why = page.read_context(data.get("ctx"), self.secret)
        if not payload:
            return 403, {"error": why}
        if page.where(payload)["on"] != "till":
            return 400, {"error": "only the till takes an answer"}
        nonce, order = payload["nonce"], page.delivery_order(payload["nonce"])
        with self._lock:
            if self.check_once and not self.answered.claim(nonce, payload["exp"]):
                return 409, {"error": "this page has already answered", "refused_by": "partner service"}
            note = data.get("note")
            body = page.submit_body(nonce, order, note if isinstance(note, str) else None)
            ts = str(int(time.time()))
            code, raw = self._post(self.base + SUBMIT, body, {"Content-Type": "application/json",
                                                              "X-iVendNext-Timestamp": ts,
                                                              "X-iVendNext-Signature": page.sign(self.secret, ts, body)})
            if code != 200:
                self.answered.release(nonce)     # the shop refused: it may be corrected and sent again while it lives
                if code == 0:
                    return 502, {"error": "the shop could not be reached; try again", "refused_by": "network"}
                return 409 if code == 409 else 502, {"error": shop_words(raw), "refused_by": "shop", "status": code}
        return 200, {"ok": 1, "delivery_order": order}


def make_handler(board: Board):
    html = open(os.path.join(HERE, "board.html"), "rb").read()

    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code: int, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _admin(self) -> bool:
            return board.test_modes and self.headers.get("X-PP-Admin") == board.admin

        def do_GET(self):
            if self.path in ("/board", "/board/"):
                return self._send(200, html, "text/html; charset=utf-8")
            if self.path == "/health":
                return self._send(200, {"ok": 1})
            if self.path == "/test/opened" and self._admin():
                return self._send(200, {"opened": board.log})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > BODY_MAX:
                return self._send(413, {"error": "too large"})
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "not JSON"})
            if not isinstance(data, dict):
                return self._send(400, {"error": "not a JSON object"})
            if self.path == "/board/api/open":
                return self._send(*board.open(data))
            if self.path == "/board/api/answer":
                return self._send(*board.answer(data))
            if self.path == "/test/once" and self._admin():
                board.check_once = bool(data.get("on"))
                return self._send(200, {"check_once": board.check_once})
            self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            sys.stderr.write("s17 %s\n" % (fmt % args))   # the request line only: the context rides the body, never the line

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
    board = Board(conf)
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or 8132)), make_handler(board))
    print(f"s17 order board on :{srv.server_port} (test modes {'ON' if board.test_modes else 'off'})", flush=True)
    srv.serve_forever()
