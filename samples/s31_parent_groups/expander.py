#!/usr/bin/env python3
"""S31 — keep a coupon's or a promotion's parent item group written out as its child groups. Python 3.9+, standard library only.

    PGX_KEY=… PGX_SECRET=… python3 expander.py run --base https://shop.example --state state/pgx.sqlite [--watch 15]
    PGX_KEY=… PGX_SECRET=… python3 expander.py reconcile --base https://shop.example --state state/pgx.sqlite

RUN        reads the event feed (``tools/feed_client``, the door by default). A saved Coupon or Promotion Bonus Buys Master
           is read again and given the child-group rows its parent groups need (``groups.plan``); a saved Item Group
           makes every coupon and promotion be checked again, so a group added under a listed parent joins them.
RECONCILE  every coupon and promotion, once: what ``run`` would have written while the service was down.

It writes the record's whole table back with the ``modified`` it read, so a person's save in between makes the shop
refuse the write (the next event retries it). The shop sends no event for the service's own writes. The rows it added
are kept in its own store (``ours``), in the same transaction as the event: a row it did not add is never removed.
A promotion's buy or get row naming a parent group is FLAGGED in the output, never written out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import feed_client as F  # noqa: E402
import groups as G  # noqa: E402

APP = "PP PGX Groups"       # the feed registration the manifest declares


def q(dt, name=None):
    p = "/api/resource/" + urllib.parse.quote(dt)
    return p if name is None else f"{p}/{urllib.parse.quote(name, safe='')}"


class Shop:
    def __init__(self, api):
        self.api = api

    def groups(self) -> dict:
        rows = self.api.call("GET", q("Item Group"), {"fields": json.dumps(["name", "parent_item_group"]), "limit_page_length": 0})["data"]
        return {r["name"]: r.get("parent_item_group") for r in rows}

    def names(self, dt) -> list:
        return [r["name"] for r in self.api.call("GET", q(dt), {"fields": json.dumps(["name"]), "limit_page_length": 0})["data"]]

    def get(self, dt, name):
        return self.api.call("GET", q(dt, name))["data"]

    def put(self, dt, name, body):
        return self.api.call("PUT", q(dt, name), body=body)["data"]


def init(db):
    db.execute("create table if not exists ours (doctype text, record text, tbl text, child text, parent text, "
               "primary key (doctype, record, tbl, child))")
    db.execute("create table if not exists removed (doctype text, record text, tbl text, child text, "
               "primary key (doctype, record, tbl, child))")


def load(db, dt, name):
    mine = {(t, c): p for t, c, p in db.execute("select tbl, child, parent from ours where doctype=? and record=?", (dt, name))}
    gone = {(t, c) for t, c in db.execute("select tbl, child from removed where doctype=? and record=?", (dt, name))}
    return mine, gone


def save(db, dt, name, mine, gone):
    db.execute("delete from ours where doctype=? and record=?", (dt, name))
    db.execute("delete from removed where doctype=? and record=?", (dt, name))
    db.executemany("insert into ours values (?,?,?,?,?)", [(dt, name, t, c, p) for (t, c), p in mine.items()])
    db.executemany("insert into removed values (?,?,?,?)", [(dt, name, t, c) for t, c in gone])


def one(shop, db, dt, name, groups=None, out=print) -> dict:
    """Bring one record up to date. Returns what changed. The store is written before the shop: if the shop refuses,
    the caller's transaction rolls the store back too."""
    doc = shop.get(dt, name)
    mine, gone = load(db, dt, name)
    p = G.plan(dt, doc, groups if groups is not None else shop.groups(), mine, gone)
    for f in p["flags"]:
        out("  FLAG " + f)
    save(db, dt, name, p["mine"], p["removed"])
    body = {}
    for table, (kind, key, _) in G.EXPAND.get(dt, {}).items():
        add, drop = p["add"].get(table, []), p["drop"].get(table, [])
        if add or drop:
            body[table] = G.table_after(doc, table, kind, key, add, drop)
    if body:
        shop.put(dt, name, dict(body, modified=doc["modified"]))
        out(f"  {dt} {name}: " + "; ".join(f"{t} +{len(p['add'].get(t, []))} −{len(p['drop'].get(t, []))}" for t in body))
    return {"added": sum(map(len, p["add"].values())), "dropped": sum(map(len, p["drop"].values())), "flags": len(p["flags"])}


def everything(shop, db, out=print):
    """Every coupon and promotion, each in its own savepoint: a record the shop refuses (a person saved it a moment
    before) rolls back only its own store rows, and is counted under ``failed``; the next save or reconcile catches up."""
    groups = shop.groups()
    n = {"records": 0, "added": 0, "dropped": 0, "flags": 0, "failed": 0}
    for dt in G.EXPAND:
        for name in shop.names(dt):
            db.execute("savepoint one_record")
            try:
                r = one(shop, db, dt, name, groups, out)
            except F.FeedError as e:
                db.execute("rollback to one_record")
                db.execute("release one_record")
                out(f"  NOT WRITTEN {dt} {name}: {e}")
                n["failed"] += 1
                continue
            db.execute("release one_record")
            n["records"] += 1
            for k in ("added", "dropped", "flags"):
                n[k] += r[k]
    return n


def handler(shop, out=print):
    def handle(ev, db):
        if ev["doc_type"] in G.EXPAND and ev["event"] != "deleted":
            one(shop, db, ev["doc_type"], ev["doc_name"], out=out)
        elif ev["doc_type"] == G.GROUP:
            everything(shop, db, out)
    return handle


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    a.add_argument("cmd", choices=["run", "reconcile"])
    a.add_argument("--base", required=True)
    a.add_argument("--state", default=os.path.join(HERE, "state", "pgx.sqlite"))
    a.add_argument("--watch", type=int, default=0, help="seconds between passes; 0 = one pass")
    a.add_argument("--engine-feed", action="store_true", help="read the feed through the shop's own records, not the door")
    args = a.parse_args(argv)
    api = F.Api(args.base, os.environ["PGX_KEY"], os.environ["PGX_SECRET"])
    shop, store = Shop(api), F.Store(args.state)
    init(store.db)
    if args.cmd == "reconcile":
        store.db.execute("begin")
        try:
            print(json.dumps(everything(shop, store.db)))
            store.db.execute("commit")
        except BaseException:
            store.db.execute("rollback")
            raise
        return
    feed = F.EngineFeed(api, APP) if args.engine_feed else F.DoorFeed(api)
    while True:
        print(json.dumps(F.poll(feed, store, handler(shop))))
        if not args.watch:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
