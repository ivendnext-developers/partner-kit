"""S1 warranty — the OUTSIDE service (the connected form). Standard library only.

    python3 service/app.py <env-file>

When a sale is booked, iVendNext calls ``POST /webhook``. The service verifies the call, reads the sale's
lines and serial numbers over the record API as the integration user, registers the warranties in its OWN
store (SQLite), and writes ONE Comment on the sale — the result a shopkeeper sees in Desk. A reconciliation
pull (``POST /reconcile``, and on a timer) finds every sale no webhook delivered.

Env file (KEY=VALUE; ⛔ never commit it): PP_BASE, PP_KEY, PP_SECRET, PP_WEBHOOK_SECRET, PP_ADMIN_TOKEN,
PP_PORT (8121), PP_DB (warranty.sqlite3), PP_TERMS (terms.json), PP_SINCE (first watermark),
PP_RECONCILE_SECONDS (3600; 0 = off).
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import core  # noqa: E402
from receiver import HEADER, replay_key, verify  # noqa: E402
from store import Store  # noqa: E402
from tenant import Tenant, TenantError  # noqa: E402

DOCTYPES = ("Sales Invoice", "POS Invoice")
MAX_BODY = 64 * 1024   # a thin webhook body is a few hundred bytes


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), msg, flush=True)


def load_env(path: str) -> dict:
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


class Service:
    def __init__(self, env: dict):
        self.env = env
        self.tenant = Tenant(env["PP_BASE"], env["PP_KEY"], env["PP_SECRET"])
        self.store = Store(os.path.join(HERE, env.get("PP_DB", "warranty.sqlite3")))
        self.store.load_terms(os.path.join(HERE, env.get("PP_TERMS", "terms.json")))

    # ---- idempotent: safe for a webhook, a retry, a replay and a reconciliation to reach the same sale ----
    def process(self, doctype: str, name: str, via: str) -> str:
        with self.store.lock:
            if self.store.is_processed(doctype, name):
                return "already processed"
            doc = self.tenant.get(doctype, name)
            if doc.get("docstatus") != 1:
                return "not submitted — left for a later pass"
            if doc.get("is_return") or doc.get("is_consolidated"):
                # a return gives no new warranty; a consolidated invoice repeats POS sales already handled
                self.store.record(doctype, name, [], None, via)
                return "skipped (return or consolidated)"
            items = [r for r in doc.get("items") or [] if r.get("item_code")]
            terms = self.store.terms()
            terms["item_group"] = self.tenant.item_groups([r["item_code"] for r in items])
            lines = [{"item_code": r["item_code"],
                      "serials": self.tenant.serials_of(r) if core.term_for(r["item_code"], terms)[0] == core.COVERED else []}
                     for r in items]
            regs, skipped = core.registrations(lines, terms, date.fromisoformat(doc["posting_date"]))
            comment = None
            if regs or any(s["reason"] == "no serial numbers on the line" for s in skipped):
                if self.tenant.has_our_comment(doctype, name):
                    comment = "(already present)"   # a crash after the comment, before the commit: never twice
                else:
                    comment = self.tenant.add_comment(doctype, name, core.comment_text(name, regs, skipped))
            added = self.store.record(doctype, name, regs, comment, via)
            msg = f"{doctype} {name} via {via}: {added} warranty(ies) registered, {len(skipped)} line(s) skipped, comment {comment}"
            self.store.event("processed", msg)
            return msg

    def reconcile(self) -> dict:
        """The pull that recovers missed deliveries: every submitted sale modified since the watermark."""
        out = {}
        for dt in DOCTYPES:
            wm = self.store.watermark(dt, self.env.get("PP_SINCE", "2000-01-01 00:00:00"))
            done = 0
            while True:
                rows = self.tenant.list(dt, ["name", "modified"], [["docstatus", "=", 1], ["modified", ">=", wm]],
                                        "modified asc", 200)
                newest = wm
                for r in rows:
                    try:
                        self.process(dt, r["name"], "reconcile")
                    except Exception as e:   # any failure: stop here, keep the watermark before it, say so
                        self.store.event("error", f"reconcile {dt} {r['name']}: {type(e).__name__}: {e}"[:300])
                        rows = []   # stop here: the watermark stays before the failure, so it is retried
                        break
                    newest, done = r["modified"], done + 1
                if newest != wm:
                    self.store.set_watermark(dt, newest)
                if len(rows) < 200 or newest == wm:
                    break
                wm = newest
            out[dt] = done
        self.store.event("reconcile", json.dumps(out))
        return out


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict) -> None:
            raw = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _admin(self) -> bool:
            ok = hmac.compare_digest(self.headers.get("X-PP-Admin", ""), svc.env["PP_ADMIN_TOKEN"])
            if not ok:
                self._send(403, {"error": "admin token required"})
            return ok

        def log_message(self, fmt, *args):   # one line per request, no headers (no secrets in the log)
            log(f"{self.address_string()} {fmt % args}")

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if self.path == "/status" and self._admin():
                return self._send(200, svc.store.status())
            if self.path not in ("/status",):
                self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._send(400, {"error": "bad Content-Length"})
            if not 0 <= size <= MAX_BODY:
                return self._send(413, {"error": f"body over {MAX_BODY} bytes"})
            body = self.rfile.read(size)
            if self.path == "/reconcile":
                if self._admin():
                    try:
                        self._send(200, svc.reconcile())
                    except TenantError as e:
                        self._send(502, {"error": str(e)})
                return
            if self.path != "/webhook":
                return self._send(404, {"error": "not found"})
            data, how = verify(body, self.headers.get(HEADER), svc.env["PP_WEBHOOK_SECRET"])
            if data is None:
                svc.store.event("refused", how)
                return self._send(401, {"error": how})
            key = replay_key(data)
            if key is None or data.get("doctype") not in DOCTYPES:
                svc.store.event("refused", f"unexpected payload {sorted(data)}")
                return self._send(400, {"error": "payload must carry doctype, name, event, modified"})
            if svc.store.seen(key):
                svc.store.event("replay-ignored", key)
                return self._send(200, {"ignored": "replay"})
            svc.store.event("verified", f"{key} ({how})")
            try:
                result = svc.process(data["doctype"], data["name"], "webhook")
            except TenantError as e:
                svc.store.event("error", f"webhook {key}: {e}")
                return self._send(502, {"error": "could not read the sale; it will be retried or reconciled"})
            svc.store.mark_seen(key)
            self._send(200, {"result": result})

    return Handler


def main() -> None:
    env = load_env(sys.argv[1])
    svc = Service(env)
    every = int(env.get("PP_RECONCILE_SECONDS", "3600"))
    if every > 0:
        def loop():
            while True:
                time.sleep(every)
                try:
                    log(f"timer reconcile {svc.reconcile()}")
                except Exception as e:   # the timer must survive a bench restart
                    log(f"timer reconcile failed: {e}")
        threading.Thread(target=loop, daemon=True).start()
    port = int(env.get("PP_PORT", "8121"))
    log(f"pp_wrc service listening on :{port}, reconciling every {every}s")
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(svc)).serve_forever()


if __name__ == "__main__":
    main()
