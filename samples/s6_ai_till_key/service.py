"""S6 — the AI till key's service (standard library only). One route: the remote till key's request.

    POST /point/ai_tip      body {"app", "key", "returns", "context"}  →  200 {"message": {...}}

The request, headers and signature are the remote till key's, as in samples/s1_warranty/remote/wrapper.py (the
signature check and size cap are copied from it; a defect there is a defect here — report it on the programme board).
The binding is core.answer(): build the prompt, ask the provider the SHOP configured, return the message. Failure is
failure: a provider error or a slow provider gives NO answer, so the till says so in its own words (refused, nothing
added to the sale) — this service never invents a tip.

⛔ Logs: one line per request — the request id, the status and the milliseconds. Never the prompt, the context, the
reply, the key or the signature (tests/test_service.py greps the log for each).

    python3 service.py        (env, or .env.local beside this file: PP_POINT_SECRET, PP_POINT_PORT, PP_AI_PROVIDER, ...)
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
sys.path.insert(0, HERE)
import core  # noqa: E402
import providers  # noqa: E402

BODY_MAX, SKEW_S = 64 * 1024, 300


def load_env(path):
    out = {}
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                out[k] = v
    return out


def verified(secret: bytes, headers, raw: bytes) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:
        return False
    want = base64.b64encode(hmac.new(secret, ts.encode() + b"." + raw, hashlib.sha256).digest())
    return hmac.compare_digest(want, sig.encode())


def make_server(conf: dict, provider, port: int = 0, log=sys.stderr):
    secret = conf["PP_POINT_SECRET"].encode()

    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            t0, rid, code = time.monotonic(), self.headers.get("X-iVendNext-Request-Id", "-")[:40], 500
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n < 0 or n > BODY_MAX:
                    code = 413
                    return self._send(code, {"error": "too large"})
                raw = self.rfile.read(n)
                if not verified(secret, self.headers, raw):
                    code = 401
                    return self._send(code, {"error": "bad signature"})
                if self.path != "/point/ai_tip":
                    code = 404
                    return self._send(code, {"error": "no such point"})
                try:
                    context = json.loads(raw)["context"]
                    result = core.answer(context, provider)
                except Exception as e:          # noqa: BLE001 — the CLASS only: a message can carry a url or a key
                    log.write(f"request {rid} provider-or-input failure: {type(e).__name__}\n")
                    code = 502
                    return self._send(code, {"error": "no answer"})
                code = 200
                return self._send(code, result)
            finally:
                log.write(f"request {rid} status {code} {int((time.monotonic() - t0) * 1000)} ms\n")
                log.flush()

        def log_message(self, fmt, *args):      # the framework's own access line carries the path only; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


if __name__ == "__main__":
    conf = {**load_env(os.path.join(HERE, ".env.local")), **{k: v for k, v in os.environ.items() if k.startswith("PP_")}}
    srv = make_server(conf, providers.from_env(conf), int(conf.get("PP_POINT_PORT", "8126")))
    print(f"AI till key on :{srv.server_address[1]} (provider {conf.get('PP_AI_PROVIDER', 'stub')})", flush=True)
    srv.serve_forever()
