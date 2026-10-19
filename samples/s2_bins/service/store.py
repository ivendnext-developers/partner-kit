"""The S2 service's own store (SQLite): the replay set, the reconciliation watermark and an event log. The bin
quantities are NOT here — they live in the shop, in the manifest's record types, where staff and the till see them."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
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
        self.lock = threading.RLock()      # one sale at a time: a webhook and a reconciliation never interleave

    def seen(self, key: str) -> bool:
        return bool(self.db.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone())

    def mark_seen(self, key: str):
        self.db.execute("INSERT OR IGNORE INTO seen VALUES (?,?)", (key, now()))

    def watermark(self, doctype: str, default: str) -> str:
        row = self.db.execute("SELECT modified FROM watermark WHERE doctype=?", (doctype,)).fetchone()
        return row[0] if row else default

    def set_watermark(self, doctype: str, modified: str):
        self.db.execute("INSERT INTO watermark VALUES (?,?) ON CONFLICT(doctype) DO UPDATE SET modified=excluded.modified",
                        (doctype, modified))

    def event(self, kind: str, detail: str):
        self.db.execute("INSERT INTO events (at, kind, detail) VALUES (?,?,?)", (now(), kind, detail[:2000]))

    def events(self, limit=50) -> list:
        return [dict(zip(("at", "kind", "detail"), r)) for r in
                self.db.execute("SELECT at, kind, detail FROM events ORDER BY id DESC LIMIT ?", (limit,))]
