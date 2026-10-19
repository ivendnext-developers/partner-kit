#!/usr/bin/env python3
"""S26 — keep a derived price list in step with its source. Python 3.9+, standard library only.

    DPL_KEY=… DPL_SECRET=… python3 sync.py run --base https://shop.example --state state/dpl.sqlite --watch 15

Each pass, in order:

  RULES     — read every PP DPL Rule; refuse (and report) a rule that cannot run: a bad number, two currencies, a step
              or floor finer than the rule's decimal places, two rules on one target list, a loop of lists (``prices.usable``).
  BACKFILL  — a rule that is new, or whose numbers changed, has every source price worked out again, in pages, the
              page cursor saved after each page: a crash resumes where it stopped, and nothing is written twice.
  FEED      — every Item Price event (``tools/feed_client``, the door by default): the row is read again; a source
              row gives its target row; a row gone gives its made rows an end date (never deleted).

  RECONCILE — a nightly, read-only report: every target price against its source, by name. It changes nothing.

A target row the service made carries ``PP-DPL <rule> <source row>`` in its note (the stamp). It is found by that stamp
before every write, so a replayed event writes nothing new. A row at the target without this rule's stamp is a
person's price, and so is a stamped row last changed by anyone but the service: both are held, never overwritten, and
listed. The service's own writes make no event for it (the feed's contract), so it carries a change down a chain of
lists (A → B → C) itself.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import feed_client as F  # noqa: E402
import prices as P  # noqa: E402

RULE = "PP DPL Rule"
FIELDS = ["name", "item_code", "uom", "price_list", "price_list_rate", "valid_from", "valid_upto", "note",
          "customer", "supplier", "batch_no", "modified_by"]
PAGE = 200
GENERAL = [["customer", "is", "not set"], ["supplier", "is", "not set"], ["batch_no", "is", "not set"]]


class Shop:
    """The shop over the record API (and one wrapper call, who am I). Nothing here computes a price."""

    def __init__(self, api: F.Api):
        self.api = api

    @staticmethod
    def _q(dt, name=None):
        p = "/api/resource/" + urllib.parse.quote(dt)
        return p if name is None else f"{p}/{urllib.parse.quote(name, safe='')}"

    def _list(self, dt, filters, fields, order_by="name asc", limit=0):
        return self.api.call("GET", self._q(dt), {"filters": json.dumps(filters), "fields": json.dumps(fields),
                                                  "order_by": order_by, "limit_page_length": limit}).get("data", [])

    def me(self) -> str:
        return self.api.call("POST", "/api/method/ivendnext_mpos.api.v1.get_logged_user").get("message") or ""

    def rules(self) -> list[dict]:
        return self._list(RULE, [], ["name", "enabled", "source_price_list", "target_price_list", "factor", "offset",
                                     "rounding_step", "rounding", "floor", "decimal_places"])

    def lists(self) -> dict[str, str]:
        """Each price list's currency."""
        return {r["name"]: r["currency"] for r in self._list("Price List", [], ["name", "currency"])}

    def price(self, name: str) -> dict | None:
        try:
            return self.api.call("GET", self._q("Item Price", name)).get("data")
        except F.FeedError as e:
            if str(e).startswith("404"):
                return None
            raise

    def rows(self, price_list: str, item: str | None = None, uom: str | None = None, after: str = "", limit: int = 0) -> list[dict]:
        """The general price rows of a list (no customer, supplier or batch), by name; one item and unit, or a page."""
        f = [["price_list", "=", price_list], *GENERAL]
        if item is not None:
            f += [["item_code", "=", item], ["uom", "=", uom]]
        if after:
            f.append(["name", ">", after])
        return [r for r in self._list("Item Price", f, FIELDS, limit=limit) if P.general(r)]

    def stamped(self, price_list: str, stamp: str) -> list[dict]:
        """The rows of a list carrying one stamp, whatever their item and unit."""
        return self._list("Item Price", [["price_list", "=", price_list], ["note", "=", stamp]], FIELDS)

    def made_from(self, source_row: str) -> list[dict]:
        """The rows made from one source row: their note is a stamp ending in that row's name."""
        return self._list("Item Price", [["note", "like", f"{P.STAMP} % {source_row}"]], FIELDS)

    def insert(self, doc: dict) -> dict:
        return self.api.call("POST", self._q("Item Price"), body={"doctype": "Item Price", **doc})["data"]

    def update(self, name: str, fields: dict) -> dict:
        return self.api.call("PUT", self._q("Item Price", name), body=fields)["data"]


def report() -> dict:
    return {"written": 0, "unchanged": 0, "ended": [], "held": [], "raised": []}


def _day(v) -> str:
    return str(v or "")[:10]


class Service:
    def __init__(self, shop, db, today: _dt.date | None = None):
        self.shop, self.db, self.today = shop, db, today
        db.execute("create table if not exists backfill (rule text primary key, fingerprint text, after text, done integer)")
        self.rules: dict[str, P.Rule] = {}
        self.refused: list[dict] = []

    def load(self):
        self.rules, self.refused = P.usable(self.shop.rules(), self.shop.lists())
        self.me = self.shop.me()

    def _yesterday(self) -> str:
        return str((self.today or _dt.date.today()) - _dt.timedelta(days=1))

    def _theirs(self, rows: list[dict], rule: P.Rule) -> list[dict]:
        """A person's prices: rows still selling (no end date, or one from today on) without this rule's stamp."""
        today = str(self.today or _dt.date.today())
        return [r for r in rows if not P.stamped_by(r.get("note"), rule.name) and (not r.get("valid_upto") or _day(r["valid_upto"]) >= today)]

    @staticmethod
    def _why(row: dict) -> str:
        return ("made by another rule, or by a rule since deleted" if (row.get("note") or "").startswith(P.STAMP + " ")
                else "a price at the target that the service did not make")

    # ---------- a source row gives its target rows, and on down the chain
    def on_row(self, src: dict, rep: dict, only: str | None = None, depth: int = 0):
        if depth > len(self.rules) or not P.general(src):
            return
        for rule in [r for r in self.rules.values() if r.source == src["price_list"] and only in (None, r.name)]:
            rate, raised = P.derive(src["price_list_rate"], rule)
            st = P.stamp(rule.name, src["name"])
            what = {"rule": rule.name, "item": src["item_code"], "uom": src["uom"], "list": rule.target}
            theirs = self._theirs(self.shop.rows(rule.target, src["item_code"], src["uom"]), rule)
            if theirs:
                rep["held"].append({**what, "row": theirs[0]["name"], "why": self._why(theirs[0])})
                continue
            mine = self.shop.stamped(rule.target, st)          # by its stamp: found even when the source's item or unit changed
            want = {"item_code": src["item_code"], "uom": src["uom"], "price_list_rate": str(rate),
                    "valid_upto": src.get("valid_upto") or None}
            if src.get("valid_from"):
                want["valid_from"] = src["valid_from"]
            if mine and mine[0].get("modified_by") != self.me:
                rep["held"].append({**what, "row": mine[0]["name"], "why": "changed by a person since the service wrote it"})
                continue
            if mine and P.D(mine[0]["price_list_rate"]) == rate and all(str(mine[0].get(k) or "") == str(v or "")
                                                                        for k, v in want.items() if k != "price_list_rate"):
                row = mine[0]
                rep["unchanged"] += 1
            elif mine:
                row = self.shop.update(mine[0]["name"], want)
                rep["written"] += 1
            else:
                row = self.shop.insert({"price_list": rule.target, "note": st, **want})
                rep["written"] += 1
            if raised:
                rep["raised"].append({**what, "rate": str(rate), "why": "below the floor: raised to the floor"})
            self.on_row(row, rep, depth=depth + 1)       # our own write makes no event: carry it down the chain

    # ---------- a source row deleted: the rows made from it stop selling (never deleted: history points at them)
    def on_gone(self, source_row: str, rep: dict):
        y = self._yesterday()
        for row in self.shop.made_from(source_row):
            if row.get("valid_upto") and _day(row["valid_upto"]) <= y:
                continue
            if row.get("modified_by") != self.me:
                rep["held"].append({"row": row["name"], "why": "its source is gone, but a person changed it: left as it is"})
                continue
            fields = {"valid_upto": y}
            if row.get("valid_from") and _day(row["valid_from"]) > y:
                fields["valid_from"] = y
            row = self.shop.update(row["name"], fields)
            rep["ended"].append(row["name"])
            self.on_row(row, rep, depth=1)               # the end date goes down the chain too

    def handler(self, ev: dict, _db):
        """The feed handler: every Item Price event, read again (one change writes several events; each is cheap)."""
        if ev["doc_type"] != "Item Price":
            return
        rep = report()
        row = self.shop.price(ev["doc_name"])
        if row is None or not P.general(row):          # deleted, or now for one customer, supplier or batch: no longer a source
            self.on_gone(ev["doc_name"], rep)
        else:
            self.on_row(row, rep)
        if rep["written"] or rep["ended"] or rep["held"] or rep["raised"]:
            print(json.dumps({"event": ev["event"], "row": ev["doc_name"], **rep}), flush=True)

    # ---------- a new or changed rule: every source price again, in pages, resumable
    def backfill(self, only: str | None = None, crash_after_pages: int | None = None) -> dict:
        rep, pages = report(), 0
        if only is None:      # a rule switched off or refused forgets its backfill, so it is worked out again when it is back
            self.db.execute(f"delete from backfill where rule not in ({','.join('?' * len(self.rules))})", tuple(self.rules))
        for rule in [r for r in self.rules.values() if only in (None, r.name)]:
            got = self.db.execute("select fingerprint, after, done from backfill where rule=?", (rule.name,)).fetchone()
            fp = rule.fingerprint()
            if got and got[0] == fp and got[2] and not only:
                continue
            after = got[1] if got and got[0] == fp and not got[2] else ""
            while True:
                page = self.shop.rows(rule.source, after=after, limit=PAGE)
                if not page:
                    break
                for src in page:
                    self.on_row(src, rep, only=rule.name)
                after = page[-1]["name"]
                self.db.execute("insert into backfill values (?,?,?,0) on conflict(rule) do update set "
                                "fingerprint=excluded.fingerprint, after=excluded.after, done=0", (rule.name, fp, after))
                pages += 1
                if crash_after_pages is not None and pages >= crash_after_pages:
                    raise SystemExit(f"CRASH (injected) after {pages} page(s) of {rule.name}")
            self.db.execute("insert into backfill values (?,?,'',1) on conflict(rule) do update set "
                            "fingerprint=excluded.fingerprint, after='', done=1", (rule.name, fp))
        return rep

    # ---------- the nightly report: read-only, by name
    def reconcile(self) -> dict:
        diffs, held = [], []
        today = str(self.today or _dt.date.today())
        for rule in self.rules.values():
            srcs, tgts = self.shop.rows(rule.source), self.shop.rows(rule.target)
            mine = {r["note"]: r for r in tgts if P.stamped_by(r.get("note"), rule.name)}
            them = self._theirs(tgts, rule)
            theirs = {(r["item_code"], r["uom"]) for r in them}
            held += [{"rule": rule.name, "row": r["name"], "item": r["item_code"], "why": self._why(r)} for r in them]
            for s in srcs:
                if (s["item_code"], s["uom"]) in theirs:
                    continue
                want, _ = P.derive(s["price_list_rate"], rule)
                row = mine.get(P.stamp(rule.name, s["name"]))
                at = {"rule": rule.name, "item": s["item_code"], "uom": s["uom"], "source_row": s["name"]}
                if row is None:
                    diffs.append({**at, "what": "no target price", "want": str(want)})
                elif row.get("modified_by") != self.me:
                    held.append({**at, "row": row["name"], "why": "changed by a person since the service wrote it"})
                elif (row["item_code"], row["uom"]) != (s["item_code"], s["uom"]):
                    diffs.append({**at, "row": row["name"], "what": "item or unit differs from its source"})
                elif P.D(row["price_list_rate"]) != want:
                    diffs.append({**at, "row": row["name"], "what": "price differs", "have": str(P.D(row["price_list_rate"])), "want": str(want)})
                elif _day(row.get("valid_upto")) != _day(s.get("valid_upto")):
                    diffs.append({**at, "row": row["name"], "what": "end date differs"})
            names = {s["name"] for s in srcs}
            for note, row in mine.items():
                if note.split(" ")[-1] in names or (row.get("valid_upto") and _day(row["valid_upto"]) < today):
                    continue
                if row.get("modified_by") != self.me:
                    held.append({"rule": rule.name, "row": row["name"], "item": row["item_code"],
                                 "why": "its source is gone, but a person changed it: left as it is"})
                else:
                    diffs.append({"rule": rule.name, "row": row["name"], "item": row["item_code"],
                                  "what": "its source is gone, and it still sells"})
        return {"rules": sorted(self.rules), "refused": self.refused, "differences": diffs, "held": held,
                "clean": not diffs and not self.refused}


def main(argv=None):
    p = argparse.ArgumentParser(description="S26 — keep a derived price list in step with its source")
    p.add_argument("command", choices=("run", "backfill", "reconcile", "status"))
    p.add_argument("--base", required=True)
    p.add_argument("--state", default="state/dpl.sqlite")
    p.add_argument("--transport", choices=("door", "engine"), default="door")
    p.add_argument("--app", help="the feed registration's name (engine transport only)")
    p.add_argument("--rule", help="backfill: this rule only, from the start")
    p.add_argument("--watch", type=float, help="run: repeat every N seconds")
    p.add_argument("--crash-after-pages", type=int, help="test only")
    a = p.parse_args(argv)
    key, secret = os.environ.get("DPL_KEY"), os.environ.get("DPL_SECRET")
    if not key or not secret:
        sys.exit("set DPL_KEY and DPL_SECRET in the environment")
    api, store = F.Api(a.base, key, secret), F.Store(a.state)
    svc = Service(Shop(api), store.db)
    feed = F.DoorFeed(api) if a.transport == "door" else F.EngineFeed(api, a.app)
    while True:
        svc.load()
        if a.command == "reconcile":
            print(json.dumps(svc.reconcile()))
            return
        if a.command == "status":
            print(json.dumps({"rules": sorted(svc.rules), "refused": svc.refused, "backlog": feed.backlog(),
                              "backfills": svc.db.execute("select rule, done from backfill").fetchall()}))
            return
        if a.command == "backfill" and a.rule:
            svc.db.execute("delete from backfill where rule=?", (a.rule,))
        out = {"refused": svc.refused, "backfill": svc.backfill(a.rule, a.crash_after_pages)}
        if a.command == "run":
            out["feed"] = F.poll(feed, store, svc.handler)
        print(json.dumps(out), flush=True)
        if not (a.watch and a.command == "run"):
            return
        time.sleep(a.watch)


if __name__ == "__main__":
    try:
        main()
    except (F.FeedError, RuntimeError) as e:
        sys.exit(f"DPL_ERROR {e}")
