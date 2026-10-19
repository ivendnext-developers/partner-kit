"""The service's OWN store — a local SQLite file. Nothing here is added to the tenant: the warranties,
the terms, the replay set and the reconciliation watermark all belong to the partner."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS terms (kind TEXT NOT NULL CHECK (kind IN ('item','group')), key TEXT NOT NULL,
                                  months INTEGER NOT NULL, PRIMARY KEY (kind, key));
CREATE TABLE IF NOT EXISTS warranty (serial_no TEXT PRIMARY KEY, item_code TEXT NOT NULL, invoice TEXT NOT NULL,
                                     months INTEGER NOT NULL, starts TEXT NOT NULL, expires TEXT NOT NULL,
                                     registered_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processed (doctype TEXT NOT NULL, name TEXT NOT NULL, comment TEXT, via TEXT NOT NULL,
                                      at TEXT NOT NULL, PRIMARY KEY (doctype, name));
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watermark (doctype TEXT PRIMARY KEY, modified TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL,
                                   detail TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.executescript(SCHEMA)
        self.lock = threading.RLock()   # one writer at a time: a webhook and a reconciliation never interleave

    def load_terms(self, terms_file: str) -> None:
        """Seed the terms table from a JSON file ({"items": {...}, "groups": {...}}) the first time only."""
        if self.db.execute("SELECT 1 FROM terms LIMIT 1").fetchone():
            return
        data = json.load(open(terms_file))
        with self.lock:
            self.db.executemany("INSERT INTO terms VALUES (?,?,?)",
                                [("item", k, v) for k, v in data.get("items", {}).items()]
                                + [("group", k, v) for k, v in data.get("groups", {}).items()])

    def terms(self) -> dict:
        out = {"items": {}, "groups": {}}
        for kind, key, months in self.db.execute("SELECT kind, key, months FROM terms"):
            out["items" if kind == "item" else "groups"][key] = months
        return out

    def is_processed(self, doctype: str, name: str) -> bool:
        return bool(self.db.execute("SELECT 1 FROM processed WHERE doctype=? AND name=?", (doctype, name)).fetchone())

    def record(self, doctype: str, name: str, regs: list[dict], comment: str | None, via: str) -> int:
        """Register the warranties and mark the sale processed — one transaction. Returns rows newly registered."""
        with self.lock:
            self.db.execute("BEGIN")
            before = self.db.total_changes
            # a serial sold again (after a return) takes the NEW sale's warranty — the Comment then says what is
            # stored. Returns do not void a warranty in this sample (a stated bound).
            self.db.executemany(
                "INSERT INTO warranty VALUES (?,?,?,?,?,?,?) ON CONFLICT(serial_no) DO UPDATE SET "
                "item_code=excluded.item_code, invoice=excluded.invoice, months=excluded.months, "
                "starts=excluded.starts, expires=excluded.expires, registered_at=excluded.registered_at",
                [(r["serial_no"], r["item_code"], name, r["months"], r["starts"], r["expires"], now()) for r in regs])
            added = self.db.total_changes - before
            self.db.execute("INSERT OR IGNORE INTO processed VALUES (?,?,?,?,?)", (doctype, name, comment, via, now()))
            self.db.execute("COMMIT")
            return added

    def seen(self, key: str) -> bool:
        return bool(self.db.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone())

    def mark_seen(self, key: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO seen VALUES (?,?)", (key, now()))

    def watermark(self, doctype: str, default: str) -> str:
        row = self.db.execute("SELECT modified FROM watermark WHERE doctype=?", (doctype,)).fetchone()
        return row[0] if row else default

    def set_watermark(self, doctype: str, modified: str) -> None:
        self.db.execute("INSERT INTO watermark VALUES (?,?) ON CONFLICT(doctype) DO UPDATE SET modified=excluded.modified",
                        (doctype, modified))

    def event(self, kind: str, detail: str) -> None:
        self.db.execute("INSERT INTO events (at, kind, detail) VALUES (?,?,?)", (now(), kind, detail))

    def status(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "warranties": q("SELECT COUNT(*) FROM warranty"),
            "processed": q("SELECT COUNT(*) FROM processed"),
            "seen": q("SELECT COUNT(*) FROM seen"),
            "watermarks": dict(self.db.execute("SELECT doctype, modified FROM watermark").fetchall()),
            "events": [dict(zip(("at", "kind", "detail"), r)) for r in
                       self.db.execute("SELECT at, kind, detail FROM events ORDER BY id DESC LIMIT 30")],
            "by_invoice": dict(self.db.execute("SELECT invoice, COUNT(*) FROM warranty GROUP BY invoice").fetchall()),
            "processed_via": dict(self.db.execute("SELECT name, via FROM processed").fetchall()),
        }
