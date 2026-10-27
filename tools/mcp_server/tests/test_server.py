"""Laptop tests of our MCP server, no bench: a fake shop on localhost answers the record API and enforces a role per
key ("reader" may read, "writer" may also write). The bench test (run_mcp.sh) repeats the role check on the real tenant.

    python3 -m unittest discover -s tools/mcp_server/tests -p 'test_*.py'
"""

import ast
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import server as S  # noqa: E402

SECRETS = {"reader": "rs3cret-reader-0000", "writer": "ws3cret-writer-1111"}
HITS = []


class Shop(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _who(self):
        a = self.headers.get("Authorization", "")
        key, _, secret = a.removeprefix("token ").partition(":")
        return key if SECRETS.get(key) == secret else None

    def do_GET(self):
        HITS.append(("GET", self.path, self._who()))
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/steal")
            self.end_headers()
            return
        if not self._who():
            return self._reply(401, {"exc_type": "AuthenticationError"})
        self._reply(200, {"data": [{"name": "ITEM-1"}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        HITS.append(("POST", self.path, self._who(), body))
        who = self._who()
        if who != "writer":
            return self._reply(403, {"exc_type": "PermissionError",
                                     "_server_messages": json.dumps([json.dumps({"message": "Not permitted"})]),
                                     "exception": "Traceback (most recent call last): secret internals"})
        self._reply(200, {"data": dict(body, name="CMT-1")})


def start(handler, srv=None):
    h = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    return h


COMMENT = {"comment_type": "Comment", "reference_doctype": "Item", "reference_name": "ITEM-1", "content": "hello"}


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shop = start(Shop)
        cls.base = f"http://127.0.0.1:{cls.shop.server_port}"
        cls.tmp = tempfile.mkdtemp()

    def setUp(self):
        HITS.clear()
        self.audit = os.path.join(self.tmp, f"{self._testMethodName}.jsonl")

    def srv(self, writes=False):
        return S.Server(self.base, writes=writes, audit=self.audit)

    def call(self, srv, name, args, who="reader"):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
        return srv.handle(msg, (who, SECRETS[who]) if who else None, "test")["result"]

    def test_tools_json_is_generated_from_the_description_and_fresh(self):
        venv = ROOT.parents[1] / ".venv" / "bin" / "python"
        if not venv.exists():
            self.skipTest("no .venv with PyYAML")
        r = subprocess.run([str(venv), str(ROOT / "generate.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_title_is_whole_and_a_write_title_says_what_it_does(self):
        # the title is what the person sees when asked to approve a call, so a write's title is its whole summary
        for t in json.loads((ROOT / "tools.json").read_text())["tools"]:
            title = t["annotations"]["title"]
            self.assertTrue(title.strip(), t["name"])
            if not t["annotations"]["readOnlyHint"]:
                self.assertEqual(title, t["description"].split("\n\n")[0], t["name"])

    def test_read_only_by_default_lists_no_write_tool_and_refuses_one(self):
        srv = self.srv()
        names = {t["name"] for t in srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, None, "t")
                 ["result"]["tools"]}
        self.assertIn("listItems", names)
        self.assertFalse(names & {"createComment", "createStockEntry", "updatePartnerRecord"})
        r = self.call(srv, "createComment", {"body": COMMENT, "confirm": True}, "writer")
        self.assertTrue(r["isError"])
        self.assertIn("read-only", r["content"][0]["text"])
        self.assertFalse([h for h in HITS if h[0] == "POST"], "nothing reached the shop")

    def test_a_write_without_confirmation_is_refused_and_nothing_is_sent(self):
        srv = self.srv(writes=True)
        r = self.call(srv, "createComment", {"body": COMMENT}, "writer")
        self.assertTrue(r["isError"])
        prev = json.loads(r["content"][0]["text"])
        self.assertEqual(prev["would_send"]["method"], "POST")
        self.assertEqual(prev["would_send"]["body"], COMMENT)
        r = self.call(srv, "createComment", {"body": COMMENT, "confirm": False}, "writer")
        self.assertTrue(r["isError"])
        self.assertFalse([h for h in HITS if h[0] == "POST"], "an unconfirmed write must not reach the shop")

    def test_a_confirmed_write_goes_with_the_persons_own_key_and_the_shop_decides(self):
        srv = self.srv(writes=True)
        ok = self.call(srv, "createComment", {"body": COMMENT, "confirm": True}, "writer")
        self.assertFalse(ok["isError"], ok)
        no = self.call(srv, "createComment", {"body": COMMENT, "confirm": True}, "reader")
        self.assertTrue(no["isError"])
        text = no["content"][0]["text"]
        self.assertIn("403", text)
        self.assertNotIn("Traceback", text, "the shop's traceback never reaches the AI client")
        posts = [h for h in HITS if h[0] == "POST"]
        self.assertEqual([p[2] for p in posts], ["writer", "reader"], "each call carried its own caller's key")

    def test_no_key_is_refused_before_the_shop(self):
        r = self.call(self.srv(), "listItems", {}, None)
        self.assertTrue(r["isError"])
        self.assertFalse(HITS)

    def test_arguments_are_checked_against_the_schema(self):
        srv = self.srv()
        self.assertIn("unknown arguments", self.call(srv, "listItems", {"sql": "x"})["content"][0]["text"])
        self.assertIn("missing arguments", self.call(srv, "getItem", {})["content"][0]["text"])
        self.assertIn("must be a integer", self.call(srv, "listItems", {"limit_page_length": "9"})["content"][0]["text"])
        self.assertFalse(HITS)

    def test_a_path_value_cannot_escape_its_segment(self):
        self.call(self.srv(), "getItem", {"name": "../../method/ivendnext_mpos.api.v1.submit?x="})
        self.assertEqual(HITS[0][1], "/api/resource/Item/..%2F..%2Fmethod%2Fivendnext_mpos.api.v1.submit%3Fx%3D")
        for dots in (".", ".."):
            r = self.call(self.srv(), "getPartnerRecord", {"record_type": dots, "name": ".."})
            self.assertTrue(r["isError"])
        self.assertEqual(len(HITS), 1, "a dot segment never reaches the shop")

    def test_plain_http_only_to_this_machine(self):
        with self.assertRaises(ValueError):
            S.Server("http://shop.example", audit=self.audit)
        S.Server("https://shop.example", audit=self.audit)

    def test_the_log_holds_the_path_template_not_the_record(self):
        self.call(self.srv(), "getItem", {"name": "SECRET-RECORD-NAME"})
        self.assertNotIn("SECRET-RECORD-NAME", open(self.audit).read())

    def test_no_redirect_is_followed_with_the_key(self):
        srv = self.srv()
        srv.tools["listItems"] = dict(srv.tools["listItems"], _http=dict(srv.tools["listItems"]["_http"],
                                                                          path="/redirect"))
        r = self.call(srv, "listItems", {})
        self.assertTrue(r["isError"])
        self.assertEqual(len(HITS), 1, "only the shop itself was called")

    def test_audit_log_has_every_call_and_never_a_secret_or_a_value(self):
        srv = self.srv(writes=True)
        self.call(srv, "listItems", {"filters": '[["item_name","like","SECRET-CUSTOMER-VALUE"]]'})
        self.call(srv, "createComment", {"body": COMMENT}, "writer")
        self.call(srv, "createComment", {"body": COMMENT, "confirm": True}, "writer")
        log = open(self.audit).read()
        rows = [json.loads(x) for x in log.splitlines()]
        self.assertEqual([r["tool"] for r in rows], ["listItems", "createComment", "createComment"])
        self.assertEqual([r["confirmed"] for r in rows], [False, False, True])
        for needle in (*SECRETS.values(), "SECRET-CUSTOMER-VALUE", "hello"):
            self.assertNotIn(needle, log)
        self.assertIn('"key": "writ~', log, "the key appears only as a fingerprint")

    def test_stdio_transport_end_to_end(self):
        env = dict(os.environ, IVN_BASE=self.base, IVN_KEY="reader", IVN_SECRET=SECRETS["reader"],
                   IVN_MCP_AUDIT=self.audit)
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                                                                               "capabilities": {}, "clientInfo": {"name": "t"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "listItems", "arguments": {}}}]
        p = subprocess.run([sys.executable, str(ROOT / "server.py")], input="\n".join(map(json.dumps, msgs)) + "\n",
                           capture_output=True, text=True, env=env, timeout=30)
        out = [json.loads(x) for x in p.stdout.splitlines()]
        self.assertEqual([o["id"] for o in out], [1, 2, 3], "no answer to the notification")
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("ITEM-1", out[2]["result"]["content"][0]["text"])

    def test_http_transport_end_to_end(self):
        srv = self.srv()
        h = http.server.ThreadingHTTPServer(("127.0.0.1", 0), None)
        h.server_close()
        port = h.server_port
        threading.Thread(target=S.serve_http, args=(srv, "127.0.0.1", port), daemon=True).start()
        import time
        time.sleep(0.3)

        def post(msg, auth=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=json.dumps(msg).encode(), method="POST",
                                         headers={"Content-Type": "application/json", **({"Authorization": auth}
                                                                                         if auth else {})})
            with urllib.request.urlopen(req) as r:
                return r.status, (json.loads(r.read()) if r.status == 200 else None)

        st, out = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "listItems", "arguments": {}}}, f"token reader:{SECRETS['reader']}")
        self.assertEqual(st, 200)
        self.assertFalse(out["result"]["isError"])
        st, _ = post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(st, 202)

    def test_standard_library_only(self):
        tree = ast.parse((ROOT / "server.py").read_text())
        mods = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)} | \
               {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertEqual(mods - set(sys.stdlib_module_names) - {"__future__"}, set())


if __name__ == "__main__":
    unittest.main()
