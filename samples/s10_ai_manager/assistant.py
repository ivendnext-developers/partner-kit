#!/usr/bin/env python3
"""assistant.py — a SCRIPTED stand-in for a manager's AI assistant (Python 3.9+, standard library only).

A real assistant (the one the customer already pays for, or a free model on their own machine) reads the profile's tool
words and decides which tools to call. This script plays that part with fixed rules, so the whole path is testable with no AI
account: the manager's sentence -> tool calls on our MCP server -> an answer in words. It keeps the rules the profile's
instructions give a real assistant: it adds sales up in the shop (never lists them), and it NEVER sets confirm until the
manager has said yes — it asks first, through ``manager(preview_text) -> bool``.

    a = Assistant("http://localhost:8130/mcp", key, secret, manager=lambda preview: True)
    a.ask("What sold in the Store 1 store yesterday?", today="2026-10-04")
        -> {"answer": "...", "figure": {...}, "wrote": False, "calls": [...]}
"""
import datetime
import json
import re
import urllib.error
import urllib.request


class Assistant:
    def __init__(self, url, key, secret, manager=None):
        self.url, self.auth, self.manager = url, f"token {key}:{secret}", manager or (lambda preview: False)
        self.n = 0
        self.calls = []

    # ── the wire ────────────────────────────────────────────────────────────────────────────────────────────────────
    def rpc(self, method, params=None):
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method, **({"params": params} if params else {})}
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": self.auth})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["result"]

    def tool(self, name, args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        text = r["content"][0]["text"]
        try:
            body = json.loads(text)
        except ValueError:
            body = text
        self.calls.append({"tool": name, "args": sorted(args), "confirmed": args.get("confirm") is True, "error": r["isError"]})
        return r["isError"], body

    def tools(self):
        return [t["name"] for t in self.rpc("tools/list")["tools"]]

    # ── understanding the manager ───────────────────────────────────────────────────────────────────────────────────
    def ask(self, question, today=None):
        today = datetime.date.fromisoformat(today) if today else datetime.date.today()
        self.calls = []
        q = question.strip().rstrip("?.! ")
        m = (re.match(r"(?i)what (?:sold|did we sell) (?:in|at) the (?P<store>.+?) store (?P<when>yesterday|today|on \d{4}-\d{2}-\d{2})$", q) or None)
        if m:
            return self._sales(m["store"], _day(m["when"], today))
        m = re.match(r"(?i)(?:what is|show me) the closing (?:for|of) the (?P<store>.+?) store (?P<when>yesterday|today|on \d{4}-\d{2}-\d{2})$", q)
        if m:
            return self._closing(m["store"], _day(m["when"], today))
        m = re.match(r"(?i)how many (?P<item>\S+) (?:are )?(?:in|at) the (?P<store>.+?) store$", q)
        if m:
            return self._stock(m["item"], m["store"])
        m = re.match(r"(?i)(?:put|switch on|turn on) the (?P<pct>\d+)% (?P<what>.+?) promotion on$", q)
        if m:
            return self._promotion(m["what"], m["pct"], 1)
        m = re.match(r"(?i)(?:take|switch|turn) the (?P<pct>\d+)% (?P<what>.+?) promotion off$", q)
        if m:
            return self._promotion(m["what"], m["pct"], 0)
        m = re.match(r"(?i)(?:change|set) the price of (?P<item>\S+) to (?P<rate>\d+(?:\.\d+)?)$", q)
        if m:
            return self._price(m["item"], float(m["rate"]))
        return self._done("I do not know how to answer that.")

    def _done(self, answer, **more):
        return {"answer": answer, "wrote": False, "calls": list(self.calls), **more}

    # ── reading ─────────────────────────────────────────────────────────────────────────────────────────────────────
    def _profile(self, store):
        err, body = self.tool("listPOSProfiles", {"fields": '["name","warehouse"]', "limit_page_length": 100})
        if err:
            return None, f"The shop would not show me the stores ({_why(body)})."
        hits = [p for p in body["data"] if store.lower() in (p["name"] + " " + (p.get("warehouse") or "")).lower()]
        if len(hits) != 1:
            return None, f"I found {len(hits)} stores called '{store}', so I cannot say which you mean."
        return hits[0]["name"], None

    def _sales(self, store, day):
        profile, why = self._profile(store)
        if why:
            return self._done(why)
        err, body = self.tool("listPOSInvoices", {
            "fields": '["sum(grand_total) as total", "count(name) as sales"]',
            "filters": json.dumps([["pos_profile", "=", profile], ["posting_date", "=", day], ["docstatus", "=", 1]])})
        if err:
            return self._done(f"The shop would not give me the sales ({_why(body)}).")
        row = body["data"][0]
        total, sales = float(row.get("total") or 0), int(row.get("sales") or 0)
        return self._done(f"The {store} store ({profile}) sold {total:,.2f} across {sales:,} sales on {day}.",
                          figure={"profile": profile, "day": day, "total": total, "sales": sales})

    def _closing(self, store, day):
        profile, why = self._profile(store)
        if why:
            return self._done(why)
        err, body = self.tool("listPartnerRecords", {
            "record_type": "POS Closing Entry", "fields": '["sum(grand_total) as total", "count(name) as closings"]',
            "filters": json.dumps([["pos_profile", "=", profile], ["posting_date", "=", day], ["docstatus", "=", 1]])})
        if err:
            return self._done(f"The shop would not give me the closings ({_why(body)}).")
        row = body["data"][0]                                     # added up in the shop, like the sales: never a list of closings
        total, closings = round(float(row.get("total") or 0), 2), int(row.get("closings") or 0)
        return self._done(f"The {store} store closed {closings} till day(s) on {day}, {total:,.2f} in all.",
                          figure={"profile": profile, "day": day, "total": total, "closings": closings})

    def _stock(self, item, store):
        profile, why = self._profile(store)
        if why:
            return self._done(why)
        err, body = self.tool("listPOSProfiles", {"fields": '["warehouse"]', "filters": json.dumps([["name", "=", profile]])})
        wh = body["data"][0]["warehouse"]
        err, body = self.tool("listStockBalances", {"fields": '["actual_qty"]', "filters": json.dumps([["item_code", "=", item], ["warehouse", "=", wh]])})
        if err:
            return self._done(f"The shop would not give me the stock ({_why(body)}).")
        qty = sum(float(r["actual_qty"]) for r in body["data"])
        return self._done(f"The {store} store has {qty:g} of {item}.", figure={"item": item, "warehouse": wh, "qty": qty})

    # ── writing: ask the manager, then confirm ──────────────────────────────────────────────────────────────────────
    def _write(self, record_type, name, body, words):
        args = {"record_type": record_type, "name": name, "body": body}
        err, preview = self.tool("updatePartnerRecord", args)          # no confirm: nothing is sent, we get the preview
        if not (err and isinstance(preview, dict) and "would_send" in preview):
            return self._done(f"I could not prepare the change ({_why(preview)}). Nothing was changed.")
        if not self.manager(f"{words} Shall I go ahead?"):
            return self._done("Understood — I have not changed anything.", asked=True)
        err, out = self.tool("updatePartnerRecord", dict(args, confirm=True))
        if err:
            return self._done(f"The shop refused the change ({_why(out)}). Nothing was changed.", asked=True)
        return {"answer": "Done. The shop has saved the change.", "wrote": True, "asked": True, "calls": list(self.calls), "result": out}

    def _promotion(self, what, pct, want):
        err, body = self.tool("listPartnerRecords", {
            "record_type": "Promotion Bonus Buys Master", "fields": '["name","description","active"]',
            "filters": json.dumps([["description", "like", f"%{what.split()[-1]}%"]]), "limit_page_length": 100})
        if err:
            return self._done(f"The shop would not show me the promotions ({_why(body)}).")
        # the promotion the manager means: its words say "10%" as written (not a 10 inside a number) and every word they used
        rows = [r for r in body["data"] if f"{pct}%" in (r["description"] or "")
                and all(w.lower() in (r["description"] or "").lower() for w in what.split())]
        if len(rows) != 1:
            return self._done(f"I found {len(rows)} promotions matching '{pct}% {what}', so I will not guess which to change.")
        p = rows[0]
        if int(p["active"]) == want:
            return self._done(f"'{p['description']}' is already {'on' if want else 'off'}. Nothing to change.")
        return self._write("Promotion Bonus Buys Master", p["name"], {"active": want},
                           f"I will switch '{p['description']}' {'on' if want else 'off'} (it is {'off' if want else 'on'} now).")

    def _price(self, item, rate):
        err, body = self.tool("listPartnerRecords", {
            "record_type": "Item Price", "fields": '["name","price_list","price_list_rate"]',
            "filters": json.dumps([["item_code", "=", item], ["selling", "=", 1]])})
        if err:
            return self._done(f"The shop would not show me the prices ({_why(body)}).")
        rows = body["data"]
        if len(rows) != 1:
            return self._done(f"I found {len(rows)} selling prices for {item}, so I will not guess which to change.")
        r = rows[0]
        return self._write("Item Price", r["name"], {"price_list_rate": rate},
                           f"I will change {item} in the price list '{r['price_list']}' from {float(r['price_list_rate']):,.2f} to {rate:,.2f}.")


def _day(when, today):
    if when.lower() == "yesterday":
        return (today - datetime.timedelta(days=1)).isoformat()
    if when.lower() == "today":
        return today.isoformat()
    return when.split()[-1]


def _why(body):
    if isinstance(body, dict):
        return str(body.get("status") or body.get("refused") or body.get("message") or body)[:160]
    return str(body)[:160]
