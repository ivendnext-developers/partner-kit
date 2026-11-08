#!/usr/bin/env python3
"""S63 — a stand-in hotel system, so the whole flow runs on a laptop with no network (standard library only).

    POST /v1/find  {"room", "guest"}                            ->  {"folio"}, or 404 {"error"} with the sentence the server reads
    POST /v1/post  {"folio", "lines", "receipt", "currency"}    ->  201 {"references": [one per line]}, or 409 {"error"}
    POST /standin/mode {"mode": "up" | "down" | "lost"}         down: every call answers 503 · lost: a post books, then no answer
    GET  /standin/posted                                        what is on the folios
    GET  /health

    python3 samples/s63_room_charge/standin/hotel_api.py        # on 127.0.0.1:8161 (HOTEL_STANDIN_PORT)
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GUESTS = {"412": {"guest": "Smith", "folio": "R-1001", "post": True}, "518": {"guest": "Jones", "folio": "R-1002", "post": False},
          "6A": {"guest": "Khan", "folio": "R-1003", "post": True}}


class Hotel:
    def __init__(self):
        self.lock, self.mode, self.posted, self.seq, self.finds = threading.Lock(), "up", [], 0, 0

    def find(self, room: str, guest: str) -> tuple[int, dict]:
        self.finds += 1
        g = GUESTS.get(room)
        if not g or g["guest"].casefold() != guest.casefold():
            return 404, {"error": f"Room {room} has no guest named {guest}."}
        if not g["post"]:
            return 404, {"error": f"Room {room} can't take charges. Ask for another way to pay."}
        return 200, {"folio": g["folio"]}

    def post(self, body: dict) -> tuple[int, dict]:
        if body["folio"] not in {g["folio"] for g in GUESTS.values() if g["post"]}:
            return 409, {"error": "This guest is no longer staying."}
        with self.lock:
            refs = []
            for ln in body["lines"]:
                self.seq += 1
                refs.append(f"L-{self.seq:04d}")
                self.posted.append(dict(ln, reference=refs[-1], folio=body["folio"], receipt=body["receipt"]))
        return 201, {"references": refs}


def make_server(hotel: Hotel, port: int, host: str = "127.0.0.1"):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/standin/posted":
                return self._send(200, {"posted": hotel.posted, "finds": hotel.finds})
            return self._send(200, {"ok": 1})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/standin/mode":
                hotel.mode = body["mode"]
                return self._send(200, {"mode": hotel.mode})
            if hotel.mode == "down":
                return self._send(503, {"error": "down"})
            if self.path == "/v1/find":
                return self._send(*hotel.find(body["room"], body["guest"]))
            if self.path == "/v1/post":
                out = hotel.post(body)
                if hotel.mode == "lost":                # it booked; the answer never leaves
                    self.close_connection = True
                    self.connection.close()
                    return None
                return self._send(*out)
            return self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    make_server(Hotel(), int(os.environ.get("HOTEL_STANDIN_PORT") or 8161), os.environ.get("HOTEL_STANDIN_HOST") or "127.0.0.1").serve_forever()
