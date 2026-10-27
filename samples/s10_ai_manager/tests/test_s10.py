"""Laptop tests of S10 (the manager's AI assistant), no bench and no AI: a fake shop answers the record API and enforces a role per
key ("manager" may read and write promotions and prices, "reader" may only read); our MCP server runs with each profile; the
scripted assistant plays the manager's sentences.

    python3 -m unittest discover -s samples/s10_ai_manager/tests -p 'test_*.py'
"""
import http.server
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
S10 = HERE.parent
sys.path[:0] = [str(S10), str(S10.parents[1] / "tools" / "mcp_server")]
import assistant as A  # noqa: E402
import server as S  # noqa: E402

SECRETS = {"manager": "m4nager-s3cret-0001", "reader": "r3ader-s3cret-0002"}
STATE, HITS = {}, []
PROFILES = [{"name": "Store 1 — R1", "warehouse": "Demo Retail — Store 1 - DR"},
            {"name": "Store 2 — R1", "warehouse": "Demo Retail — Store 2 - DR"}]


def reset():
    STATE.clear()
    STATE.update(promos={"PROMO-AIRPODS": {"name": "PROMO-AIRPODS", "description": "10% off AirPods 3", "active": 0},
                         "PROMO-CASES": {"name": "PROMO-CASES", "description": "10% off cases", "active": 0},
                         "PROMO-COUPON": {"name": "PROMO-COUPON", "description": "buy AirPods 3, earn a 10% discount coupon", "active": 0},
                         # a "10" that is not a 10% — the assistant must not take it for the manager's promotion
                         "PROMO-PRO": {"name": "PROMO-PRO", "description": "15% off AirPods Pro, buy 10 or more", "active": 0}},
                 prices={"IP-1": {"name": "IP-1", "item_code": "PP-MGR-1", "price_list": "Retail", "price_list_rate": 100.0, "selling": 1}})
    HITS.clear()


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
        key, _, secret = self.headers.get("Authorization", "").removeprefix("token ").partition(":")
        return key if SECRETS.get(key) == secret else None

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        parts = [urllib.parse.unquote(p) for p in u.path.split("/")[3:]]
        HITS.append(("GET", parts, self._who()))
        if not self._who():
            return self._reply(401, {})
        flt = json.loads(q.get("filters", "[]"))
        if parts == ["POS Profile"]:
            return self._reply(200, {"data": [dict(p) for p in PROFILES if all(p.get(f) == v for f, _, v in flt)]})
        if parts == ["POS Invoice"]:       # one store, one day: 3 sales
            return self._reply(200, {"data": [{"total": 300.5, "sales": 3}]})
        if parts == ["POS Closing Entry"]:
            assert "sum(grand_total)" in q.get("fields", ""), "closings are added up in the shop, never listed"
            return self._reply(200, {"data": [{"total": 300.5, "closings": 2}]})
        if parts == ["Bin"]:
            return self._reply(200, {"data": [{"actual_qty": 7.0}]})
        if parts == ["Promotion Bonus Buys Master"]:
            like = [v.strip("%").lower() for f, op, v in flt if f == "description"]      # the shop's LIKE, one word
            return self._reply(200, {"data": [dict(p) for p in STATE["promos"].values() if all(w in p["description"].lower() for w in like)]})
        if parts == ["Item Price"]:
            return self._reply(200, {"data": [dict(p) for p in STATE["prices"].values() if p["item_code"] == next((v for f, _, v in flt if f == "item_code"), None)]})
        if parts == ["Customer"]:
            return self._reply(200, {"data": [{"name": "SECRET-CUSTOMER"}]})
        return self._reply(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        HITS.append(("POST", urllib.parse.urlparse(self.path).path, self._who(), json.loads(self.rfile.read(n) or b"{}")))
        self._reply(200, {"data": {}})

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        parts = [urllib.parse.unquote(p) for p in urllib.parse.urlparse(self.path).path.split("/")[3:]]
        HITS.append(("PUT", parts, self._who(), body))
        if self._who() != "manager":
            return self._reply(403, {"exc_type": "PermissionError"})
        table = {"Promotion Bonus Buys Master": "promos", "Item Price": "prices"}.get(parts[0])
        if not table or parts[1] not in STATE[table]:
            return self._reply(404, {})
        STATE[table][parts[1]].update(body)
        self._reply(200, {"data": STATE[table][parts[1]]})


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shop = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        threading.Thread(target=cls.shop.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.shop.server_port}"
        cls.tmp = tempfile.mkdtemp()

    def setUp(self):
        reset()
        self.audit = os.path.join(self.tmp, f"{self._testMethodName}.jsonl")

    def start(self, profile="profile_writes.json", writes=True):
        prof = json.loads((S10 / profile).read_text()) if profile else None
        srv = S.Server(self.base, writes=writes, audit=self.audit, profile=prof)
        h = http.server.ThreadingHTTPServer(("127.0.0.1", 0), None)
        h.server_close()
        port = h.server_port
        threading.Thread(target=S.serve_http, args=(srv, "127.0.0.1", port), daemon=True).start()
        import time
        time.sleep(0.3)
        return srv, f"http://127.0.0.1:{port}/mcp"

    def asst(self, who="manager", says=True, **kw):
        _, url = self.start(**kw)
        self.said = []
        return A.Assistant(url, who, SECRETS[who], manager=lambda preview: (self.said.append(preview), says)[1])

    # ── what the server offers ──────────────────────────────────────────────────────────────────────────────────────
    def test_read_only_server_lists_no_write_tool_with_either_profile(self):
        for prof in ("profile_read.json", "profile_writes.json"):
            names = set(self.asst(profile=prof, writes=False).tools())
            self.assertIn("listPOSInvoices", names)
            self.assertFalse(names & {"updatePartnerRecord", "createPartnerRecord", "createStockEntry", "createComment"}, prof)

    def test_the_read_profile_never_lists_a_write_even_when_the_server_allows_writes(self):
        names = set(self.asst(profile="profile_read.json", writes=True).tools())
        self.assertNotIn("updatePartnerRecord", names)
        self.assertEqual(names, set(json.loads((S10 / "profile_read.json").read_text())["tools"]))

    def test_the_writes_profile_lists_one_write_and_carries_the_profiles_words(self):
        srv, url = self.start()
        listed = {t["name"]: t for t in A.Assistant(url, "manager", SECRETS["manager"]).rpc("tools/list")["tools"]}
        self.assertIn("updatePartnerRecord", listed)
        self.assertNotIn("createStockEntry", listed)
        self.assertIn("without confirm first", listed["updatePartnerRecord"]["description"])
        self.assertNotEqual(listed["updatePartnerRecord"]["description"], srv.tools["updatePartnerRecord"]["description"])

    def test_a_profile_naming_a_tool_the_server_lacks_is_refused_at_start(self):
        with self.assertRaises(ValueError):
            S.Server(self.base, audit=self.audit, profile={"tools": {"noSuchTool": "x"}})

    def test_a_tool_outside_the_profile_is_refused_before_the_shop(self):
        a = self.asst()
        err, body = a.tool("createStockEntry", {"body": {}, "confirm": True})
        self.assertTrue(err)
        self.assertFalse(HITS)

    def test_record_types_outside_the_allow_list_are_refused_before_the_shop(self):
        a = self.asst()
        for tool, args in (("listPartnerRecords", {"record_type": "Customer"}),
                           ("getPartnerRecord", {"record_type": "Customer", "name": "X"}),
                           ("updatePartnerRecord", {"record_type": "POS Invoice", "name": "X", "body": {"grand_total": 1}, "confirm": True}),
                           ("updatePartnerRecord", {"record_type": "Customer", "name": "X", "body": {}, "confirm": True})):
            err, body = a.tool(tool, args)
            self.assertTrue(err, tool)
            self.assertIn("profile", json.dumps(body))
        self.assertFalse(HITS, "none of them reached the shop")
        a = self.asst(profile="profile_read.json")
        err, _ = a.tool("listPartnerRecords", {"record_type": "Promotion Bonus Buys Master"})
        self.assertFalse(err)

    def test_a_write_may_change_only_the_fields_the_profile_names(self):
        a = self.asst()
        for rt, name, body in (("Item Price", "IP-1", {"selling": 0}), ("Item Price", "IP-1", {"price_list_rate": 5, "price_list": "Other"}),
                               ("Promotion Bonus Buys Master", "PROMO-AIRPODS", {"active": 1, "discount_percent": 90}),
                               ("Promotion Bonus Buys Master", "PROMO-AIRPODS", {"sequence_number": 1})):
            err, out = a.tool("updatePartnerRecord", {"record_type": rt, "name": name, "body": body, "confirm": True})
            self.assertTrue(err, (rt, body))
            self.assertIn("changes only these fields", json.dumps(out))
        self.assertFalse([h for h in HITS if h[0] == "PUT"], "none of them reached the shop")
        err, out = a.tool("updatePartnerRecord", {"record_type": "Item Price", "name": "IP-1", "body": {"price_list_rate": 5.0}, "confirm": True})
        self.assertFalse(err, out)
        self.assertEqual(STATE["prices"]["IP-1"]["price_list_rate"], 5.0)

    def test_a_profile_fails_closed(self):
        with self.assertRaises(ValueError):          # offers the general record tools but says no record types
            S.Server(self.base, audit=self.audit, profile={"tools": {"listPartnerRecords": "x"}})
        with self.assertRaises(ValueError):          # no "any field" form of a write
            S.Server(self.base, audit=self.audit, profile={"tools": {"listPartnerRecords": "x", "updatePartnerRecord": "y"},
                                                           "record_types": {"read": ["Item Price"], "write": ["Item Price"]}})
        srv = S.Server(self.base, audit=self.audit, profile={})       # an empty profile offers nothing, it does not mean "no profile"
        names = [t["name"] for t in srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, None, "t")["result"]["tools"]]
        self.assertEqual(names, [])

    def test_the_log_holds_neither_the_record_type_nor_the_field_names_the_assistant_supplied(self):
        a = self.asst()
        a.tool("updatePartnerRecord", {"record_type": "SECRET-RECORD-TYPE", "name": "x", "body": {"secretfield": 1}, "confirm": True})
        a.tool("updatePartnerRecord", {"record_type": "Item Price", "name": "x", "body": {"SECRET-FIELD": 1}, "confirm": True})
        log = open(self.audit).read()
        self.assertIn("refused: outside this profile", log)
        for needle in ("SECRET-RECORD-TYPE", "SECRET-FIELD", "secretfield"):
            self.assertNotIn(needle, log)

    # ── reading ─────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_what_sold_yesterday_adds_up_in_the_shop_never_lists_sales(self):
        r = self.asst().ask("What sold in the Store 1 store yesterday?", today="2026-10-04")
        self.assertEqual(r["figure"], {"profile": "Store 1 — R1", "day": "2026-10-03", "total": 300.5, "sales": 3})
        self.assertIn("300.50", r["answer"])
        self.assertIn("2026-10-03", r["answer"])
        q = [h for h in HITS if h[1] == ["POS Invoice"]]
        self.assertEqual(len(q), 1)

    def test_a_store_name_matching_two_or_no_stores_is_not_guessed(self):
        r = self.asst().ask("What sold in the Demo Retail store yesterday?", today="2026-10-04")
        self.assertNotIn("figure", r)
        self.assertIn("2 stores", r["answer"])
        self.assertFalse([h for h in HITS if h[1] == ["POS Invoice"]])

    def test_closing_and_stock_answers(self):
        a = self.asst()
        r = a.ask("Show me the closing for the Store 1 store on 2026-10-03")
        self.assertEqual((r["figure"]["total"], r["figure"]["closings"]), (300.5, 2))
        r = a.ask("How many PP-MGR-1 are in the Store 1 store?")
        self.assertEqual(r["figure"]["qty"], 7.0)

    def test_reading_never_writes(self):
        a = self.asst(profile="profile_read.json", writes=False)
        a.ask("What sold in the Store 1 store yesterday?", today="2026-10-04")
        self.assertEqual({h[0] for h in HITS}, {"GET"})

    # ── writing: every write waits for the yes ──────────────────────────────────────────────────────────────────────
    def test_the_assistant_previews_asks_and_only_then_confirms(self):
        a = self.asst()
        r = a.ask("Put the 10% off AirPods promotion on")
        self.assertTrue(r["wrote"], r)
        self.assertEqual(len(self.said), 1)
        self.assertIn("switch '10% off AirPods 3' on", self.said[0])
        puts = [c for c in r["calls"] if c["tool"] == "updatePartnerRecord"]
        self.assertEqual([c["confirmed"] for c in puts], [False, True], "preview first, then the confirmed call")
        self.assertEqual([h[0] for h in HITS if h[0] == "PUT"], ["PUT"], "exactly one write reached the shop")
        self.assertEqual(STATE["promos"]["PROMO-AIRPODS"]["active"], 1)
        self.assertEqual(STATE["promos"]["PROMO-CASES"]["active"], 0, "only the named promotion moved")
        self.assertEqual(STATE["promos"]["PROMO-COUPON"]["active"], 0, "a 10% coupon on AirPods is not a 10% off AirPods promotion")
        self.assertEqual(STATE["promos"]["PROMO-PRO"]["active"], 0, "a promotion with a 10 in its words, not a 10%, did not move")

    def test_a_no_from_the_manager_sends_nothing(self):
        r = self.asst(says=False).ask("Put the 10% off AirPods promotion on")
        self.assertFalse(r["wrote"])
        self.assertEqual(len(self.said), 1)
        self.assertFalse([h for h in HITS if h[0] == "PUT"])
        self.assertEqual(STATE["promos"]["PROMO-AIRPODS"]["active"], 0)
        self.assertEqual([c["confirmed"] for c in r["calls"] if c["tool"] == "updatePartnerRecord"], [False])

    def test_two_matching_promotions_are_not_guessed(self):
        r = self.asst().ask("Put the 10% off promotion on")
        self.assertFalse(r["wrote"])
        self.assertIn("2 promotions", r["answer"])
        self.assertEqual(self.said, [])
        self.assertFalse([h for h in HITS if h[0] == "PUT"])

    def test_a_readers_confirmed_write_is_refused_by_the_shop_and_said_so(self):
        r = self.asst(who="reader").ask("Put the 10% off AirPods promotion on")
        self.assertFalse(r["wrote"])
        self.assertIn("refused", r["answer"])
        self.assertIn("Nothing was changed", r["answer"])
        self.assertEqual(STATE["promos"]["PROMO-AIRPODS"]["active"], 0)
        self.assertEqual([h[2] for h in HITS if h[0] == "PUT"], ["reader"], "it carried the reader's own key, and the shop said no")

    def test_a_price_change_and_switching_a_promotion_off(self):
        a = self.asst()
        r = a.ask("Change the price of PP-MGR-1 to 120")
        self.assertTrue(r["wrote"])
        self.assertEqual(STATE["prices"]["IP-1"]["price_list_rate"], 120.0)
        self.assertIn("from 100.00 to 120.00", self.said[0])
        a.ask("Put the 10% off AirPods promotion on")
        self.assertTrue(a.ask("Take the 10% off AirPods promotion off")["wrote"])
        self.assertEqual(STATE["promos"]["PROMO-AIRPODS"]["active"], 0)
        r = a.ask("Take the 10% off AirPods promotion off")
        self.assertFalse(r["wrote"])
        self.assertIn("already off", r["answer"])

    def test_the_audit_log_carries_the_managers_fingerprint_and_no_secret_or_value(self):
        a = self.asst()
        a.ask("Put the 10% off AirPods promotion on")
        rows = [json.loads(x) for x in open(self.audit).read().splitlines()]
        wr = [r for r in rows if r["tool"] == "updatePartnerRecord"]
        self.assertEqual([r["confirmed"] for r in wr], [False, True])
        self.assertEqual({r["key"] for r in rows}, {S.fingerprint("manager")})
        self.assertEqual(wr[1]["status"], 200)
        log = open(self.audit).read()
        for needle in (*SECRETS.values(), "PROMO-AIRPODS", "AirPods"):
            self.assertNotIn(needle, log)


if __name__ == "__main__":
    unittest.main()
