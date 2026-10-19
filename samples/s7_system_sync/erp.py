"""The customer's ERP, as a stand-in — a SQLite file OUTSIDE the shop (sample S7).

A real customer's ERP, order system or warehouse system is theirs; this file is only big enough to be synchronised with.
It keeps what such a system keeps: items, prices per price list, stock movements, and the orders and returns it is told
about. Every change to what the shop must learn (an item, a price, a stock movement) also adds a row to ``changes`` —
the numbered change feed the sync's cursor follows. Standard library only.

    erp = Erp("state/erp.sqlite")
    erp.add_item("A1", "Cable 1m", "Accessories"); erp.set_price("A1", "Demo Retail Price List", 99.0)
    erp.move_stock("A1", 25, unit_cost=40.0, note="purchase")
"""

from __future__ import annotations

import os
import sqlite3

SCHEMA = """
create table if not exists items (erp_id text primary key, name text not null, item_group text not null, deleted integer not null default 0);
create table if not exists prices (erp_id text, price_list text, price real not null, primary key (erp_id, price_list));
create table if not exists movements (id integer primary key autoincrement, erp_id text not null, qty real not null, unit_cost real, note text);
create table if not exists meta (k text primary key, v text not null);
create table if not exists changes (seq integer primary key autoincrement, kind text not null, ref text not null);
create table if not exists documents (
    erp_doc_id text primary key, kind text not null,            -- 'order' | 'return'
    shop_invoice text not null unique,                          -- the shop's own number: the key a second delivery collides on
    return_of text,                                             -- an ORDER's erp_doc_id, for a return
    posting_date text, grand_total real, customer text, shop_created text, cancelled integer not null default 0);
create table if not exists lines (erp_doc_id text, idx integer, erp_item text, item_code text, qty real, amount real,
    primary key (erp_doc_id, idx));
"""


class Erp:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def identity(self) -> str:
        """This ERP's own id (made once, kept in its file). A real system has one already. The sync puts it in the key of every
        stock entry it writes, so two systems — or this one rebuilt from scratch — can never mistake each other's movement 1."""
        r = self.db.execute("select v from meta where k='id'").fetchone()
        if r:
            return r[0]
        v = os.urandom(4).hex()
        self.db.execute("insert into meta values ('id', ?)", (v,))
        return v

    # ── what the ERP's own users do (each also numbers a change for the sync) ───────────────────────────────────
    def _change(self, kind: str, ref: str):
        self.db.execute("insert into changes (kind, ref) values (?,?)", (kind, ref))

    def add_item(self, erp_id: str, name: str, item_group: str):
        self.db.execute("insert into items values (?,?,?,0) on conflict(erp_id) do update set name=excluded.name, "
                        "item_group=excluded.item_group, deleted=0", (erp_id, name, item_group))
        self._change("item", erp_id)

    def delete_item(self, erp_id: str):
        self.db.execute("update items set deleted=1 where erp_id=?", (erp_id,))
        self._change("item", erp_id)

    def set_price(self, erp_id: str, price_list: str, price: float):
        self.db.execute("insert into prices values (?,?,?) on conflict(erp_id, price_list) do update set price=excluded.price",
                        (erp_id, price_list, price))
        self._change("price", f"{erp_id}|{price_list}")

    def move_stock(self, erp_id: str, qty: float, unit_cost: float | None = None, note: str = "") -> int:
        cur = self.db.execute("insert into movements (erp_id, qty, unit_cost, note) values (?,?,?,?)", (erp_id, qty, unit_cost, note))
        self._change("movement", str(cur.lastrowid))
        return cur.lastrowid

    # ── what the ERP answers ────────────────────────────────────────────────────────────────────────────────────
    def changes_after(self, seq: int, limit: int = 500):
        return self.db.execute("select seq, kind, ref from changes where seq > ? order by seq limit ?", (seq, limit)).fetchall()

    def item(self, erp_id: str):
        return self.db.execute("select * from items where erp_id=?", (erp_id,)).fetchone()

    def prices_of(self, erp_id: str):
        return self.db.execute("select price_list, price from prices where erp_id=?", (erp_id,)).fetchall()

    def movement(self, mid: int):
        return self.db.execute("select * from movements where id=?", (mid,)).fetchone()

    def on_hand(self, erp_id: str) -> float:
        """Stock the ERP believes it holds: what it moved in, less what the shop sold (a return carries a negative
        quantity, so it adds back). A cancelled sale is not a sale."""
        moved = self.db.execute("select coalesce(sum(qty),0) from movements where erp_id=?", (erp_id,)).fetchone()[0]
        sold = self.db.execute("select coalesce(sum(l.qty),0) from lines l join documents d using (erp_doc_id) "
                               "where l.erp_item=? and d.cancelled=0", (erp_id,)).fetchone()[0]
        return round(moved - sold, 6)

    def document_by_shop(self, shop_invoice: str):
        return self.db.execute("select * from documents where shop_invoice=?", (shop_invoice,)).fetchone()

    def documents_since(self, since: str):
        return self.db.execute("select * from documents where cancelled=0 and shop_created >= ? order by shop_created", (since,)).fetchall()

    # ── what the sync tells the ERP (idempotent: the shop's invoice number is the key) ──────────────────────────────
    def record_document(self, kind: str, shop_invoice: str, posting_date: str, grand_total: float, customer: str,
                        shop_created: str, lines: list[dict], return_of: str | None = None, cancelled: int = 0) -> tuple[str, bool]:
        """Insert once. A second delivery of the same shop invoice changes nothing and returns the same ERP id."""
        have = self.document_by_shop(shop_invoice)
        if have:
            return have["erp_doc_id"], False
        self.db.execute("begin")
        try:
            n = self.db.execute("select count(*) from documents where kind=?", (kind,)).fetchone()[0] + 1
            doc_id = f"ERP-{'ORD' if kind == 'order' else 'RET'}-{n:06d}"
            self.db.execute("insert into documents values (?,?,?,?,?,?,?,?,?)",
                            (doc_id, kind, shop_invoice, return_of, posting_date, grand_total, customer, shop_created, cancelled))
            for i, ln in enumerate(lines):
                self.db.execute("insert into lines values (?,?,?,?,?,?)",
                                (doc_id, i, ln.get("erp_item"), ln["item_code"], ln["qty"], ln["amount"]))
            self.db.execute("commit")
        except BaseException:
            self.db.execute("rollback")
            raise
        return doc_id, True

    def cancel_document(self, shop_invoice: str) -> bool:
        return self.db.execute("update documents set cancelled=1 where shop_invoice=? and cancelled=0", (shop_invoice,)).rowcount > 0
