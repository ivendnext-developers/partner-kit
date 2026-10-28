"""A stand-in for a chain's OWN loyalty system outside iVendNext, for S22's adapter tests (standard library only).

    POST /v1/members/lookup   {"customer"}  ->  {"points", "offer"}
    POST /v1/earn             {"customer", "sale", "value", "earned", "currency"} with an Idempotency-Key header
                              -> 201 {"posted": n}; the same key again -> 200, nothing posted twice

One key (``Authorization: Bearer <key>``). Run on its own for a laptop walk: ``python3 tests/standin_loyalty.py`` (port 8156, key ``chain-loyalty-key``). ``down`` makes every call 503, ``refuse`` 422. ``posted`` keeps what was posted, by key.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Loyalty:
    def __init__(self, key: str = "chain-loyalty-key", members: dict | None = None):
        self.key, self.down, self.refuse, self.lock = key, False, False, threading.Lock()
        self.members = members if members is not None else {"C1": {"points": 1240, "offer": "10% off shoes today"}}
        self.posted: dict[str, dict] = {}
        self.calls: list[str] = []


def serve(loyalty: Loyalty, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            loyalty.calls.append(self.path)
            if loyalty.down:
                return self._send(503, {"error": "down"})
            if loyalty.refuse:
                return self._send(422, {"error": "unknown member"})
            if self.headers.get("Authorization") != f"Bearer {loyalty.key}":
                return self._send(401, {"error": "unknown key"})
            if self.path == "/v1/members/lookup":
                return self._send(200, loyalty.members.get(body.get("customer"), {"points": 0, "offer": ""}))
            if self.path == "/v1/earn":
                idem = self.headers.get("Idempotency-Key") or ""
                with loyalty.lock:
                    if idem in loyalty.posted:
                        return self._send(200, {"posted": len(loyalty.posted)})
                    loyalty.posted[idem] = body
                return self._send(201, {"posted": len(loyalty.posted)})
            return self._send(404, {"error": "not found"})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":         # on a laptop: python3 samples/s22_customer_loyalty/tests/standin_loyalty.py (port 8156)
    import os
    import time
    srv = serve(Loyalty(os.environ.get("LOYALTY_STANDIN_KEY") or "chain-loyalty-key"), int(os.environ.get("LOYALTY_STANDIN_PORT") or 8156))
    print(json.dumps({"loyalty stand-in": srv.server_address[1]}), flush=True)
    while True:
        time.sleep(3600)
