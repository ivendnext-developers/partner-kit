"""Our MCP server for iVendNext — runs OUTSIDE the tenant, acts with the user's OWN key (bring your own AI).

Python 3.9+, standard library only (no third-party code, so no licence question — nothing AGPL). The tools are generated
from the API description (``generate.py`` → ``tools.json``), so the server can do exactly what the record API lets the
key do, and nothing more: every call goes to the tenant with the person's key, and the tenant's permissions decide.

    IVN_BASE=https://shop.example IVN_KEY=… IVN_SECRET=… python3 server.py                 # stdio (an AI desktop app)
    IVN_BASE=https://shop.example python3 server.py --http localhost:8130 [--writes]      # HTTP: each request brings
                                                                                         # its own Authorization header
The rules it keeps:
  * READ-ONLY BY DEFAULT. Write tools are not even listed unless the server is started with --writes.
  * A WRITE NEEDS AN EXPLICIT CONFIRMATION: ``confirm: true`` on the call. Without it nothing is sent to the shop and the
    answer is a preview of the exact write. (Bound: the server cannot see a person; the AI client must ask the person
    before it sets the flag. Clients that show a tool-approval prompt show it for every tool marked destructive.)
  * THE KEY IS THE PERSON'S. The server holds no key of its own; over HTTP it never stores the one a request carries; it
    only ever sends it to IVN_BASE (no redirect is followed).
  * AN AUDIT LOG, one JSON line per call: time, transport, a key fingerprint (never the key or secret), tool, method,
    the path TEMPLATE (never a record's name), the argument NAMES (never their values), confirmed or not, the status.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_TEXT = 100_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fingerprint(key: str) -> str:
    return (key[:4] + "~" + hashlib.sha256(key.encode()).hexdigest()[:8]) if key else "none"


class Server:
    def __init__(self, base: str, writes: bool = False, audit: str = "mcp_audit.jsonl", timeout: float = 30,
                 profile: dict | None = None):
        u = urllib.parse.urlparse(base)
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")):
            raise ValueError("IVN_BASE must be https (plain http only to this machine): the person's key travels on it")
        self.base, self.writes, self.audit_path, self.timeout = base.rstrip("/"), writes, audit, timeout
        spec = json.loads((HERE / "tools.json").read_text())
        self.tools = {t["name"]: t for t in spec["tools"]}
        self.api_version = spec["api_version"]
        # A PROFILE narrows this server for one kind of person (samples/s10_ai_manager/): the tools it lists (with the words the
        # assistant reads for each), and which record types the generic record tools may touch. It can only take away — the
        # shop's permissions for the person's key still decide what is allowed.
        self.profile = profile
        if profile is not None:
            unknown = sorted(set(profile.get("tools", {})) - set(self.tools))
            if unknown:
                raise ValueError(f"the profile names tools this server does not have: {unknown}")
            generic = sorted(n for n in profile.get("tools", {}) if "record_type" in self.tools[n].get("_http", {}).get("path_params", []))
            if generic and not profile.get("record_types"):          # fail closed: a profile that offers the general record tools says which types
                raise ValueError(f"the profile offers {generic}, which reach any record type, but names no record_types")
            if not isinstance((profile.get("record_types") or {}).get("write", {}), dict):     # …and, for a write, which FIELDS (no "any field" form)
                raise ValueError('record_types.write must be an object {record type: [the fields a write may change]}')
        self._lock = threading.Lock()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)   # no proxy, no redirect

    # ── the audit log ───────────────────────────────────────────────────────
    def audit(self, **row):
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}
        with self._lock, open(self.audit_path, "a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    # ── JSON-RPC ────────────────────────────────────────────────────────────
    def handle(self, msg: dict, auth: tuple[str, str] | None, transport: str):
        """One JSON-RPC message in; the response object out (None for a notification)."""
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if "id" not in msg:          # a notification (e.g. notifications/initialized): no answer
            return None
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                result = {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "ivendnext-mcp", "version": "0.1.0"},
                          "instructions": (self.profile or {}).get("instructions") or
                                          "iVendNext records, read with the person's own key. Writes need the "
                                          "person's approval: call with confirm: true only after they said yes."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [self._public(t, self.profile) for t in self.tools.values()
                                    if (self.writes or t["annotations"]["readOnlyHint"]) and self._in_profile(t["name"])]}
            elif method == "tools/call":
                result = self.call(params.get("name"), params.get("arguments") or {}, auth, transport)
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
        except Exception as e:  # noqa: BLE001 — never a traceback to the client
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _in_profile(self, name):
        return self.profile is None or name in self.profile.get("tools", {})

    @staticmethod
    def _public(t, profile=None):
        out = {k: t[k] for k in ("name", "description", "inputSchema", "annotations")}
        if profile and profile["tools"].get(t["name"]):
            out["description"] = profile["tools"][t["name"]]
        return out

    def _record_type_refusal(self, t, args, write):
        """A profile's allow-list for the generic record tools (``{record_type}`` in the path). ``read`` is a list of record types; ``write`` is
        an object {record type: [the only body fields it may change]}. The answer to the assistant is words; the
        audit log gets a fixed phrase — never the record type or field names the assistant supplied."""
        if self.profile is None or "record_type" not in t.get("_http", {}).get("path_params", []):
            return None
        allowed = self.profile.get("record_types", {}).get("write" if write else "read", [])
        rt = args.get("record_type")
        if rt not in allowed:
            return "this profile does not " + ("write" if write else "read") + " that kind of record"
        if write and set(args.get("body") or {}) - set(allowed[rt]):
            return "this profile changes only these fields of that record: " + ", ".join(allowed[rt])
        return None

    @staticmethod
    def _text(obj, error=False):
        text = obj if isinstance(obj, str) else json.dumps(obj, indent=1, default=str)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "\n… (cut at 100 000 characters: ask for fewer fields or a smaller page)"
        return {"content": [{"type": "text", "text": text}], "isError": error}

    # ── one tool call ───────────────────────────────────────────────────────
    def call(self, name, args: dict, auth, transport):
        t = self.tools.get(name)
        h = (t or {}).get("_http", {})
        row = {"transport": transport, "key": fingerprint(auth[0] if auth else ""), "tool": name,
               "args": sorted(args), "method": h.get("method"), "confirmed": bool(args.get("confirm") is True)}
        if not t:
            self.audit(**row, outcome="unknown tool")
            return self._text(f"No tool called {name!r}.", True)
        write = not t["annotations"]["readOnlyHint"]
        if not self._in_profile(name):
            self.audit(**row, outcome="refused: not in this profile")
            return self._text(f"Refused: {name!r} is not one of the tools this server offers.", True)
        if write and not self.writes:
            self.audit(**row, outcome="refused: read-only server")
            return self._text("Refused: this server is read-only. Its operator starts it with --writes to allow "
                              "writes, and each write still needs the person's confirmation.", True)
        if not auth:
            self.audit(**row, outcome="refused: no key")
            return self._text("Refused: no key. The person's own key is required.", True)
        bad = self._check_args(t, args)
        fenced = None if bad else self._record_type_refusal(t, args, write)
        if bad or fenced:
            self.audit(**row, outcome=f"refused: {bad}" if bad else "refused: outside this profile")
            return self._text(f"Refused: {bad or fenced}", True)
        path = h["path"]
        for p in h["path_params"]:
            if str(args[p]).strip() in (".", ".."):
                self.audit(**row, path=h["path"], outcome="refused: a dot segment")
                return self._text(f"Refused: '{args[p]}' is not a record name.", True)
            path = path.replace("{" + p + "}", urllib.parse.quote(str(args[p]), safe=""))
        query = {q: args[q] for q in h["query"] if q in args}
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        row["path"] = h["path"]          # the TEMPLATE: a record's name is an argument value, never logged
        if write and args.get("confirm") is not True:
            self.audit(**row, outcome="refused: not confirmed (preview returned)")
            return self._text({"refused": "This call WRITES to the shop and was not confirmed. Nothing was sent. Show "
                                          "the person this preview; call again with confirm: true only if they agree.",
                               "would_send": {"method": h["method"], "path": path, "body": args.get("body")}}, True)
        data = json.dumps(args["body"]).encode() if "body" in args else (b"{}" if write else None)
        req = urllib.request.Request(url, data=data, method=h["method"],
                                     headers={"Authorization": f"token {auth[0]}:{auth[1]}",
                                              "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                status, payload = r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            status, payload = e.code, _tenant_message(e.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if write:            # sent, but no answer: it may have been written — never let the assistant blindly retry
                self.audit(**row, outcome=f"unknown: no answer ({type(e).__name__})")
                return self._text("No answer from the shop. The write MAY have been made: check the record before "
                                  "trying again.", True)
            self.audit(**row, outcome=f"unreachable: {type(e).__name__}")
            return self._text("The shop could not be reached.", True)
        # a redirect is not followed (the key never travels elsewhere) and counts as a refusal
        self.audit(**row, status=status, outcome="ok" if status < 300 else "refused by the shop")
        if status >= 300:
            return self._text({"status": status, "refused_by_the_shop": payload}, True)
        return self._text(payload)

    @staticmethod
    def _check_args(t, args) -> str | None:
        props, schema = t["inputSchema"]["properties"], t["inputSchema"]
        extra = set(args) - set(props)
        if extra:
            return f"unknown arguments {sorted(extra)}"
        missing = [r for r in schema.get("required", []) if r not in args]
        if missing:
            return f"missing arguments {missing}"
        for k, v in args.items():
            want = props[k].get("type")
            ok = {"string": isinstance(v, str), "integer": isinstance(v, int) and not isinstance(v, bool),
                  "boolean": isinstance(v, bool), "object": isinstance(v, dict)}.get(want, True)
            if not ok:
                return f"argument {k} must be a {want}"
        return None


def _tenant_message(raw: bytes):
    """The shop's own sentence and error type, never its traceback."""
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        return raw[:200].decode(errors="replace")
    msg = d.get("_server_messages")
    if msg:
        try:
            msg = [json.loads(m).get("message", m) for m in json.loads(msg)]
        except ValueError:
            pass
    return {"exc_type": d.get("exc_type"), "message": msg or d.get("message")}


# ── transports ───────────────────────────────────────────────────────────────

def serve_stdio(srv: Server):
    key, secret = os.environ.get("IVN_KEY"), os.environ.get("IVN_SECRET")
    auth = (key, secret) if key and secret else None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            out = srv.handle(msg, auth, "stdio")
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


def serve_http(srv: Server, host: str, port: int):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):          # no request log: the audit log is the record
            pass

        def _send(self, code, obj=None):
            body = b"" if obj is None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(405, {"error": "POST JSON-RPC to /mcp"})

        def do_POST(self):
            if self.path.rstrip("/") != "/mcp":
                return self._send(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._send(400, {"error": "bad Content-Length"})
            if n < 0 or n > 1_000_000:
                return self._send(413, {"error": "too large"})
            auth = None
            a = self.headers.get("Authorization") or ""
            if a.startswith("token ") and ":" in a[6:]:
                auth = tuple(a[6:].split(":", 1))
            try:
                msg = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            if not isinstance(msg, dict):    # a batch (an array) is not supported: one message per request
                return self._send(400, {"jsonrpc": "2.0", "id": None,
                                        "error": {"code": -32600, "message": "one JSON-RPC message per request"}})
            out = srv.handle(msg, auth, "http")
            return self._send(202) if out is None else self._send(200, out)

    http.server.ThreadingHTTPServer((host, port), H).serve_forever()


def main(argv=None):
    p = argparse.ArgumentParser(description="iVendNext MCP server (outside the tenant, the person's own key)")
    p.add_argument("--http", help="host:port to serve Streamable-HTTP JSON-RPC on (default: stdio)")
    p.add_argument("--writes", action="store_true", help="list and allow write tools (each still needs confirm)")
    p.add_argument("--audit", default=os.environ.get("IVN_MCP_AUDIT", "mcp_audit.jsonl"))
    p.add_argument("--profile", help="a JSON profile that narrows the tools and record types (samples/s10_ai_manager/)")
    a = p.parse_args(argv)
    base = os.environ.get("IVN_BASE")
    if not base:
        sys.exit("set IVN_BASE to the shop's address")
    srv = Server(base, writes=a.writes, audit=a.audit, profile=json.loads(pathlib.Path(a.profile).read_text()) if a.profile else None)
    if a.http:
        host, _, port = a.http.rpartition(":")
        serve_http(srv, host or "127.0.0.1", int(port))
    else:
        serve_stdio(srv)


if __name__ == "__main__":
    main()
