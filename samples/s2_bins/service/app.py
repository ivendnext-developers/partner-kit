"""S2 bin locations — the partner's outside service (standard library), on the partner's own server.

    POST /webhook             a booked sale (signed by iVendNext; recipes/webhook_receiver.md) → shop-floor bins down
    POST /putaway             {"item", "qty", "bin"}                                    (X-PP-Admin)
    POST /pick                {"item", "qty", "from_bin", "to_bin", "pos_profile"}      (X-PP-Admin)
    POST /reconcile           find every booked sale no webhook delivered               (X-PP-Admin)
    POST /point/where_is_it   the REMOTE binding of the till key (the remote app key's contract @ 8fa89980; the
                              till calls it once the bench carries that key — until then the hosted app pp_bln)
    GET  /status · /health

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "s1_warranty", "service")]
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "tools", "app_template", "service"))
import bins  # noqa: E402
import core  # noqa: E402
from receiver import replay_key, verify  # noqa: E402  (S1's webhook receiver, unchanged: samples/s1_warranty/service)
from store import Store  # noqa: E402
from tenant import Tenant, TenantError  # noqa: E402
import testcall  # noqa: E402  (the template's test call)

BODY_MAX, SKEW_S = 64 * 1024, 300
ROUTES = ("/webhook", "/point/where_is_it", "/putaway", "/pick", "/reconcile")     # every POST route below


def _env(path):
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


CONF = _env(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, ".env.local"))
TENANT = Tenant(CONF["PP_BASE"], CONF["PP_KEY"], CONF["PP_SECRET"])
STORE = Store(os.path.join(HERE, CONF.get("PP_DB", "bins.sqlite3")))
WEBHOOK_SECRETS = [s for s in CONF["PP_WEBHOOK_SECRETS"].split(",") if s]   # one per subscription (SI, POS)
SALE_TYPES = ("Sales Invoice", "POS Invoice")


def handle_sale(doctype, name, via) -> dict:
    with STORE.lock:
        out = bins.booked_sale(TENANT, doctype, name)
        STORE.event(via, json.dumps({"doctype": doctype, "name": name, **out}))
        return out


def reconcile() -> dict:
    """Every booked sale modified since the watermark, handled again (safe: the bin records remember each sale).
    One that fails stops the pass for its type, so the watermark stays before it and the next pass retries."""
    done = {}
    for dt in SALE_TYPES:
        mark = STORE.watermark(dt, CONF.get("PP_SINCE", "2026-10-03 00:00:00"))
        rows = TENANT.list(dt, ["name", "modified"], [["docstatus", "=", 1], ["modified", ">=", mark]])
        done[dt] = []
        for r in rows:
            try:
                handle_sale(dt, r["name"], "reconcile")
            except Exception as e:
                STORE.event("error", f"reconcile {dt} {r['name']}: {e!r}")
                break
            STORE.set_watermark(dt, r["modified"])
            done[dt].append(r["name"])
    return done


def point_verified(headers, raw) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:   # "²" is a digit int() refuses
        return False
    want = base64.b64encode(hmac.new(CONF["PP_POINT_SECRET"].encode(), ts.encode() + b"." + raw,
                                     hashlib.sha256).digest())
    return hmac.compare_digest(want, sig.encode())


class Handler(BaseHTTPRequestHandler):
    timeout = 10       # a client that stalls is dropped, never held for ever

    def _send(self, code, body):
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _admin(self):
        return hmac.compare_digest(self.headers.get("X-PP-Admin") or "", CONF["PP_ADMIN_TOKEN"])

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if self.path == "/status" and self._admin():
            return self._send(200, {"events": STORE.events()})
        return self._send(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n < 0 or n > BODY_MAX:
            return self._send(413, {"error": "too large"})
        raw = self.rfile.read(n)
        if testcall.is_test(self.headers) and self.path not in ROUTES:   # a test is answered only where a route matches
            return self._send(404, {"error": "no such route"})
        try:
            if self.path == "/webhook":
                return self._webhook(raw)
            if self.path == "/point/where_is_it":
                if not point_verified(self.headers, raw):
                    return self._send(401, {"error": "bad signature"})
                if testcall.is_test(self.headers):      # checked as a real call; the bins are not read
                    return self._send(*testcall.answer("where_is_it"))
                ctx = json.loads(raw)["context"]
                return self._send(200, core.where_answer(ctx, bins.point_rows(TENANT, ctx)))
            if not self._admin():
                return self._send(401, {"error": "admin token required"})
            body = json.loads(raw or b"{}")
            if self.path == "/putaway":
                return self._send(200, bins.putaway(TENANT, body["item"], float(body["qty"]), body["bin"]))
            if self.path == "/pick":
                return self._send(200, bins.pick(TENANT, CONF["PP_COMPANY"], body["item"], float(body["qty"]),
                                                 body["from_bin"], body["to_bin"], body["pos_profile"]))
            if self.path == "/reconcile":
                return self._send(200, reconcile())
            return self._send(404, {})
        except bins.Refused as e:
            return self._send(409, {"refused": str(e)})
        except TenantError as e:
            STORE.event("error", str(e))
            return self._send(502, {"error": str(e)})

    def _webhook(self, raw):
        data, how = None, "no secret matched"
        for secret in WEBHOOK_SECRETS:            # verified over the raw body BEFORE anything is parsed
            data, how = verify(raw, self.headers.get("X-Frappe-Webhook-Signature"), secret)
            if data:
                break
        if not data:
            STORE.event("refused", how)
            return self._send(401, {"error": how})
        if testcall.is_test(self.headers):              # checked as a real webhook; no sale is read, nothing is stored
            return self._send(*testcall.answer("webhook"))
        key = replay_key(data)
        if not key or data.get("doctype") not in SALE_TYPES:
            return self._send(400, {"error": "not a booked sale"})
        if STORE.seen(key):
            STORE.event("replay", key)
            return self._send(200, {"ignored": "already seen"})
        out = handle_sale(data["doctype"], data["name"], f"webhook ({how})")
        STORE.mark_seen(key)                      # only AFTER it was handled: a half-done call is handled again
        return self._send(200, out)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    port = int(CONF.get("PP_PORT", "8123"))
    print(f"S2 bin service on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
