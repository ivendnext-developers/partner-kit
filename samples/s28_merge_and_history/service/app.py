"""S28 — one service for both doors of the app ``pp_mhs`` (standard library only).

    POST /mhs/merge                 the shop's signed press of *Merge counts* (``desk_action/1``) → the answer
    GET  /mhs/history/              the customer history page (``history.html``); the shop opens it with ``#ctx=…``
    GET  /mhs/history/ivn-kit.css   the design kit, served from the kit's ``kit/design/`` (a partner copies it beside)
    POST /mhs/history/api/open      {ctx} → the context checked (signature · expiry · nonce once), then the visits

Both doors work through the shop's record API with the service's own key (the app's integration user), and both read
the one settings record ``PP MHS Settings`` named ``Default``: the merge rule and how many sales the page shows.

    python3 service/app.py service/.env.local
    env: PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_ACTION_SECRET (pp_mhs:sub:merge, handed back once at
         install), PP_PAGE_SECRET (pp_mhs:sub:history), PP_PORT (8133)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path.insert(0, SAMPLE)
import history  # noqa: E402
import merge  # noqa: E402

SETTINGS = "PP MHS Settings"
DESIGN = [os.path.join(HERE, "design"), os.path.join(SAMPLE, "..", "..", "kit", "design")]   # a copy beside, else the kit's


class ShopError(Exception):
    def __init__(self, text: str, status: int = 0):
        super().__init__(text)
        self.status = status


class Shop:
    """The service's only door into iVendNext: the record API, as the app's integration user (token key:secret)."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 4):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/{urllib.parse.quote(path)}"
        if params:
            # lists as JSON, text as it is: a JSON-quoted order_by is ignored by the shop (read on a sandbox, 2026-10-16)
            url += "?" + urllib.parse.urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in params.items()})
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise ShopError(f"{method} {path} -> HTTP {e.code}", e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise ShopError(f"{method} {path} -> {e}") from None

    def _list(self, doctype: str, **params) -> list[dict]:
        return self._call("GET", doctype, params)["data"]

    # ── the merge ──
    def count(self, name: str) -> dict:
        return self._call("GET", f"{merge.COUNT}/{name}")["data"]

    def merged_by(self, key: str) -> str | None:
        rows = self._list(merge.COUNT, filters=[[merge.KEY_FIELD, "=", key]], fields=["name"], order_by="creation asc",
                          limit_page_length=1)
        return rows[0]["name"] if rows else None

    def create_count(self, doc: dict) -> str:
        return self._call("POST", merge.COUNT, body=doc)["data"]["name"]

    def comments(self, name: str) -> list[str]:
        rows = self._list("Comment", filters=[["reference_doctype", "=", merge.COUNT], ["reference_name", "=", name],
                                              ["comment_type", "=", "Comment"]], fields=["content"], limit_page_length=100)
        return [r.get("content") or "" for r in rows]

    def add_comment(self, name: str, text: str) -> None:
        self._call("POST", "Comment", body={"comment_type": "Comment", "reference_doctype": merge.COUNT,
                                            "reference_name": name, "content": text})

    # ── both ──
    def settings(self) -> dict:
        try:
            return self._call("GET", f"{SETTINGS}/Default")["data"]
        except ShopError as e:
            if e.status == 404:            # no record yet: the defaults
                return {}
            raise

    # ── the history ──
    def sales(self, doctype: str, customer: str, count: int) -> list[dict]:
        filters = [["customer", "=", customer], ["docstatus", "=", 1]]
        fields = ["name", "customer", "docstatus", "posting_date", "posting_time"]
        if doctype == history.SI:
            filters.append(["is_consolidated", "=", 0])
            fields.append("is_consolidated")
        return self._list(doctype, filters=filters, fields=fields, order_by="posting_date desc, posting_time desc",
                          limit_page_length=count)

    def sale(self, doctype: str, name: str) -> dict:
        return self._call("GET", f"{doctype}/{name}")["data"]

    def full_names(self, users: list[str]) -> dict:
        if not users:
            return {}
        rows = self._list("User", filters=[["name", "in", users]], fields=["name", "full_name"],
                          limit_page_length=len(users))
        return {r["name"]: r.get("full_name") or r["name"] for r in rows}


class Service:
    def __init__(self, conf: dict, shop):
        self.action_secret, self.page_secret, self.shop = conf["PP_ACTION_SECRET"], conf["PP_PAGE_SECRET"], shop
        self.opened = history.OnceSet()
        self._lock = threading.Lock()     # one merge at a time: a retry racing its first try finds its draft

    # ── the Desk button ──
    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        why = merge.verify(headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature"), raw,
                           self.action_secret)
        if why:
            return 401, {"error": why}
        try:
            ctx = merge.context_of(json.loads(raw))
        except ValueError as e:
            return 400, {"error": str(e)}
        names, key = [r["name"] for r in ctx["records"]], ctx["idempotency_key"]
        with self._lock:
            try:
                made = self.shop.merged_by(key)
                if made:                  # a retry from the same dialog: answer about the draft that exists
                    self._comment(names, made)
                    return 200, merge.answer(made, names, len(self.shop.count(made).get("items") or []))
                with ThreadPoolExecutor(max_workers=6) as pool:  # each read is a round trip: Desk waits 10 s at most
                    settings = pool.submit(self.shop.settings)
                    docs = list(pool.map(self.shop.count, names))  # re-read: the saved record, never the press's copy
                why = merge.refusal(docs)
                if why:
                    return 200, merge.refused(why)
                doc = merge.plan(docs, (settings.result().get("merge_rule") or merge.SUM), key)
                made = self.shop.create_count(doc)
                self._comment(names, made, fresh=True)
            except (ShopError, ValueError) as e:
                # a non-2xx: Desk says "did not answer in time. Check the record before you try again" — true, as the
                # draft may exist; the same key's retry finds it and writes no second one
                return 502, {"error": str(e)}
        return 200, merge.answer(made, names, len(doc["items"]))

    def _comment(self, sources: list[str], made: str, fresh: bool = False) -> None:
        """``merged into <name>`` on each source, once. A fresh draft has no comment yet, so only a retry looks first
        (each look is a round trip, and Desk waits at most 10 seconds for the whole press)."""
        text = merge.comment_text(made)

        def one(s):
            if s != made and (fresh or text not in self.shop.comments(s)):
                self.shop.add_comment(s, text)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(one, sources))                  # list(): a failed comment raises here, so the press says so

    # ── the page ──
    def open(self, data: dict) -> tuple[int, dict]:
        payload, why = history.read_context(data.get("ctx"), self.page_secret)
        if not payload:
            return 403, {"error": why}
        if not self.opened.claim(payload["nonce"], payload["exp"]):
            return 403, {"error": "this page was already opened; open it again from the shop"}
        out = {"theme": payload.get("theme"), "lang": payload.get("lang"), "on": "till" if "sale" in payload or payload.get("pos_profile") else "desk"}
        customer = history.customer_of(payload)
        if not customer:
            return 200, {**out, "state": "no_customer"}
        try:
            count = history.count_of(self.shop.settings())
            picked = history.pick(self.shop.sales(history.POS, customer, count),
                                  self.shop.sales(history.SI, customer, count), customer, count)
            with ThreadPoolExecutor(max_workers=5) as pool:     # each read is a round trip: read the sales side by side
                docs = list(pool.map(lambda p: (p[0], self.shop.sale(*p)), picked))
            docs = [(dt, d) for dt, d in docs if d.get("customer") == customer]    # never another customer's
            names = self.shop.full_names(sorted({d.get("owner") for _dt, d in docs if d.get("owner")}))
        except ShopError:
            return 502, {**out, "error": "The shop could not be read. Close this page and open it again."}
        return 200, {**out, "state": "ok", "customer": customer, "count": count,
                     "visits": [history.visit(dt, d, names) for dt, d in docs]}


def design_file(name: str) -> bytes | None:
    for folder in DESIGN:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return open(path, "rb").read()
    return None


def make_handler(svc: Service):
    page = open(os.path.join(HERE, "history.html"), "rb").read()

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

        def do_GET(self):
            if self.path in ("/mhs/history", "/mhs/history/"):
                return self._send(200, page, "text/html; charset=utf-8")
            if self.path in ("/mhs/history/ivn-kit.css", "/mhs/history/ivn-kit.js"):
                data = design_file(self.path.rsplit("/", 1)[1])
                if data is not None:
                    return self._send(200, data, "text/css" if self.path.endswith(".css") else "text/javascript")
            if self.path == "/health":
                return self._send(200, {"ok": 1})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > merge.BODY_MAX:
                return self._send(413, {"error": "too large"})
            raw = self.rfile.read(n)
            if self.path == "/mhs/merge":
                return self._send(*svc.press(self.headers, raw))
            if self.path == "/mhs/history/api/open":
                try:
                    data = json.loads(raw or b"{}")
                except ValueError:
                    return self._send(400, {"error": "not JSON"})
                return self._send(*svc.open(data if isinstance(data, dict) else {}))
            self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            sys.stderr.write("s28 %s\n" % (fmt % args))   # the request line only: the context rides the body

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
    svc = Service(conf, Shop(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or 8133)), make_handler(svc))
    print(f"s28 merge and history on :{srv.server_port}", flush=True)
    srv.serve_forever()
