#!/usr/bin/env python3
"""S52 — a stand-in telecom company's API, so the whole flow runs on a laptop with no network (standard library only).

A real telecom company's API is its own: read its documentation and change ``service/telecom.py``, never this file's
callers. This stand-in has the three calls the sample needs, each for ONE account, named by the ``X-Account`` header and
proved by its key (``Authorization: Bearer <key>``):

    GET  /v1/plans          the account's plans: code, name, price (minor units), currency, decimals, the phones it fits
    POST /v1/offers         {"phones": [item codes], "customer": "<id>"}  ->  {"offers": [{"phone", "plans": [...]}]}
                            the plans for each phone it knows, at THIS account's price, for THIS customer (a customer the
                            account refuses gets none, with a reason)
    POST /v1/activations    {"plan", "phone", "serial", "customer", "reference"} with an Idempotency-Key header
                            ->  201 {"activation": "ACT-...", "status": "active"}; the same key again gives the SAME number
                            (200), so a retry after a lost answer never activates twice
    GET  /health

The accounts are in ``accounts.json`` beside this file: two, ``ACC-NORTH`` and ``ACC-SOUTH``, with different prices and a
different plan list, so a test can tell which account answered. Faults for the tests (``POST /standin/faults``, from this
machine only, unless TEL_STANDIN_OPEN=1): ``down`` (every call 503), ``slow`` (seconds before each answer),
``late_activation`` (the activation is made, then the answer waits this long), ``refuse_activation`` (an activation is
refused with 422), ``price_change`` (minor units added to every price). ``GET /standin/calls`` lists the calls made,
account and path only.

    python3 samples/s52_phone_plans/standin/telecom_api.py            # on 127.0.0.1:8154
    # TEL_STANDIN_PORT, TEL_STANDIN_HOST, TEL_STANDIN_ACCOUNTS (another accounts file), TEL_STANDIN_OPEN=1 (faults from
    # another machine: a test bench whose driver runs in a container; never on a network you do not own)
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


class Telecom:
    """The stand-in's state: the accounts, the activations made (by account and idempotency key) and the faults."""

    def __init__(self, accounts: dict):
        self.accounts, self.lock = accounts, threading.Lock()
        self.activations: dict[tuple[str, str], dict] = {}
        self.faults = {"down": False, "slow": 0.0, "late_activation": 0.0, "refuse_activation": False, "price_change": 0}
        self.calls: list[dict] = []

    def account(self, headers) -> tuple:
        name = headers.get("X-Account") or ""
        acc = self.accounts.get(name)
        given = (headers.get("Authorization") or "").removeprefix("Bearer ")
        if not acc or not hmac.compare_digest(given.encode(), acc["key"].encode()):
            return None, None
        return name, acc

    def plans(self, acc: dict) -> list[dict]:
        bump = int(self.faults["price_change"] or 0)            # the telecom company changed its prices
        return [dict(p, price_minor=p["price_minor"] + bump, currency=acc["currency"], exponent=acc["exponent"])
                for p in acc["plans"]]

    def offers(self, acc: dict, body: dict) -> dict:
        customer = body.get("customer") or ""
        if customer and customer in acc.get("refused_customers", []):
            return {"offers": [], "refused": "This customer cannot take a new plan with us."}
        out = []
        for phone in body.get("phones") or []:
            fits = [p for p in self.plans(acc) if phone in p["phones"]]
            if fits:
                out.append({"phone": phone, "plans": fits})
        return {"offers": out}

    def activate(self, name: str, acc: dict, body: dict, key: str) -> tuple[int, dict]:
        with self.lock:
            done = self.activations.get((name, key))
            if done:
                return 200, done
            if self.faults["refuse_activation"]:
                return 422, {"error": "The SIM for this phone is not ready: activate it in our shop portal."}
            plan = next((p for p in acc["plans"] if p["code"] == body.get("plan")), None)
            if not plan or body.get("phone") not in plan["phones"]:
                return 422, {"error": "This plan does not fit this phone."}
            done = {"activation": f"ACT-{name[-5:]}-{len(self.activations) + 1:05d}", "status": "active",
                    "plan": plan["code"], "reference": body.get("reference") or ""}
            self.activations[(name, key)] = done
            return 201, done


def load_accounts(path: str | None = None) -> dict:
    with open(path or os.path.join(HERE, "accounts.json"), encoding="utf-8") as f:
        return json.load(f)


def make_server(tel: Telecom, port: int = 0, host: str = "127.0.0.1", open_faults: bool = False) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}") if 0 <= n <= 65536 else {}
            except ValueError:
                return {}

        def _standin(self, body) -> bool:
            if not self.path.startswith("/standin/"):
                return False
            if not open_faults and self.client_address[0] not in ("127.0.0.1", "::1"):
                self._send(403, {"error": "this machine only"})
            elif self.path == "/standin/faults" and body is not None:
                tel.faults.update({k: v for k, v in body.items() if k in tel.faults})
                self._send(200, tel.faults)
            elif self.path == "/standin/calls":
                self._send(200, {"calls": tel.calls})
            else:
                self._send(404, {"error": "not found"})
            return True

        def _route(self, method: str):
            body = self._body() if method == "POST" else None
            if self._standin(body):
                return
            if self.path == "/health":
                return self._send(200, {"ok": 1})
            name, acc = tel.account(self.headers)
            tel.calls.append({"account": name or "-", "path": self.path})
            if tel.faults["down"]:
                return self._send(503, {"error": "down for maintenance"})
            if tel.faults["slow"]:
                time.sleep(float(tel.faults["slow"]))
            if not acc:
                return self._send(401, {"error": "unknown account or key"})
            if method == "GET" and self.path == "/v1/plans":
                return self._send(200, {"plans": tel.plans(acc)})
            if method == "POST" and self.path == "/v1/offers":
                return self._send(200, tel.offers(acc, body))
            if method == "POST" and self.path == "/v1/activations":
                key = (self.headers.get("Idempotency-Key") or "")[:100]
                if not key:
                    return self._send(400, {"error": "an Idempotency-Key is required"})
                code, out = tel.activate(name, acc, body, key)
                if tel.faults["late_activation"]:
                    time.sleep(float(tel.faults["late_activation"]))   # made, but the answer comes late
                return self._send(code, out)
            return self._send(404, {"error": "not found"})

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def log_message(self, fmt, *args):
            pass

    class Server(ThreadingHTTPServer):
        request_queue_size = 64          # many tills at once, as the two-retailers test calls it

    return Server((host, port), Handler)


if __name__ == "__main__":
    srv = make_server(Telecom(load_accounts(os.environ.get("TEL_STANDIN_ACCOUNTS") or None)),
                      int(os.environ.get("TEL_STANDIN_PORT") or 8154), os.environ.get("TEL_STANDIN_HOST") or "127.0.0.1",
                      os.environ.get("TEL_STANDIN_OPEN") == "1")
    print(json.dumps({"telecom stand-in": srv.server_address[1]}), flush=True)
    srv.serve_forever()
