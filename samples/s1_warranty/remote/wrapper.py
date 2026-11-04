"""The REMOTE binding — the same pure core, answering a till key from the partner's own server (standard library).

    POST /point/warranty      body {"app", "key", "returns", "context"}  →  200 {"message": {...}}

The binding itself is ``answer()``: load the partner's reference data (its own terms file, plus the item groups
of the items on the sale, read over the API as its integration user) and call ``core.warranty_answer`` — the
same file the outside service and the hosted app call. Everything else here is the door: a size cap and a
signature check over ``<timestamp>.<body>``.

The request, the headers and the signature are the remote app key's, as published at its merge (iVendNext_PWA
``docs/extending/README.md`` §"The remote kind" @ 8fa89980). ⚠ The real till calls HTTPS only, with the certificate
checked: put this behind TLS for a shop; on our test bench it is plain http, called by the stand-in.

    python3 remote/wrapper.py        (env: ../service/.env.local for the tenant, remote/.env.local for the rest)
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [SAMPLE, os.path.join(SAMPLE, "service")]
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(SAMPLE)), "tools", "app_template", "service"))   # the test call
import core  # noqa: E402  (the sample's pure core, unchanged)
import testcall  # noqa: E402  (the template's test call: checked as a real call, answered without the binding)
from tenant import Tenant  # noqa: E402  (the sample's only door into iVendNext)

BODY_MAX, SKEW_S = 64 * 1024, 300


def _env(path):
    out = {}
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                out[k] = v
    return out


CONF = {**_env(os.path.join(SAMPLE, "service", ".env.local")), **_env(os.path.join(HERE, ".env.local"))}
TENANT = Tenant(CONF["PP_BASE"], CONF["PP_KEY"], CONF["PP_SECRET"], timeout=2)
TERMS = json.load(open(os.path.join(SAMPLE, "service", "terms.json")))
SECRET = CONF["PP_POINT_SECRET"].encode()


def answer(context: dict) -> dict:
    """THE REMOTE BINDING: the partner's own terms + the sale's item groups → the pure core."""
    codes = sorted({line["item_code"] for line in context.get("lines") or []})
    terms = {"items": TERMS["items"], "groups": TERMS["groups"], "item_group": TENANT.item_groups(codes)}
    return core.warranty_answer(context, terms)


def verified(headers, raw: bytes) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:
        return False
    want = base64.b64encode(hmac.new(SECRET, ts.encode() + b"." + raw, hashlib.sha256).digest())
    return hmac.compare_digest(want, sig.encode())




class Handler(BaseHTTPRequestHandler):
    timeout = 10       # a client that stalls is dropped, never held for ever

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n < 0 or n > BODY_MAX:
            return self._send(413, {"error": "too large"})
        raw = self.rfile.read(n)
        if testcall.is_test(self.headers) and self.path != "/point/warranty":   # a test is answered only where it matches
            return self._send(404, {"error": "no such point"})
        if not verified(self.headers, raw):
            return self._send(401, {"error": "bad signature"})
        if self.path == "/point/warranty":
            if testcall.is_test(self.headers):      # the signature held above; the binding does not run
                return self._send(*testcall.answer("warranty"))
            return self._send(200, answer(json.loads(raw)["context"]))
        return self._send(404, {"error": "no such point"})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    port = int(CONF.get("PP_POINT_PORT", "8122"))
    print(f"remote binding on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
