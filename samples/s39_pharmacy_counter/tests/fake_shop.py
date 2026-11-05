"""A stand-in shop for S39's service tests: the records the service reads and the one record type it writes, behind the
same calls as ``service/app.py``'s ``ShopApi`` (``get_list``, ``get_one``, ``insert``, ``update``, ``delete``). A list
may group by a field and read ``max(<field>) as last``, ``count(name) as n`` and ``<field> as last``, as the shop's own does. Filters are the
shapes the service sends: ``[field, "=" | "in", value]``. An insert whose name exists raises ``Taken`` (the shop's 409).
``fail`` makes every call raise ``ShopUnreadable`` (a shop that is down); ``before_insert`` runs a hook before an insert
(another till taking the number first)."""

from __future__ import annotations

import re
import threading

import app

P = "PP RXC"


class FakeShop:
    def __init__(self):
        self.tables: dict = {}
        self.calls: list = []
        self.lock = threading.Lock()
        self.fail = False
        self.before_insert = None

    def add(self, doctype: str, **rec):
        self.tables.setdefault(doctype, []).append(dict(rec))
        return rec

    def rows(self, doctype):
        return self.tables.setdefault(doctype, [])

    @staticmethod
    def _match(r, filters):
        for f, op, v in filters or []:
            have = r.get(f)
            if op == "=" and have != v:
                return False
            if op == "in" and have not in v:
                return False
            if op == "is" and bool(have) != (v == "set"):
                return False
            if op == "<=" and not (have and str(have) <= v):
                return False
            if op == "<" and not (have and str(have) < v):
                return False
        return True

    @staticmethod
    def _field(spec):
        """(the column a field reads, the key it answers under, the aggregate): ``max(day) as last`` → (day, last, max)."""
        m = re.fullmatch(r"(?:(max|count)\(`?(\w+)`?\)|(\w+)) as (\w+)", spec)     # max(`day`): the column in backticks
        return (m.group(2) or m.group(3), m.group(4), m.group(1)) if m else (spec, spec, None)

    def get_list(self, url, key, doctype, fields, filters=None, parent=None, order_by=None, limit=0, group_by=None,
                 timeout=None):
        self.calls.append(("list", doctype, filters, list(fields)))
        if self.fail:
            raise app.ShopUnreadable("down")
        specs = [self._field(f) for f in fields]
        with self.lock:
            rows = [r for r in self.rows(doctype) if self._match(r, filters)]
        if group_by:
            groups: dict = {}
            for r in rows:
                groups.setdefault(r.get(group_by), []).append(r)
            out = []
            for g, rs in groups.items():
                o = {}
                for col, as_, agg in specs:
                    vals = [str(r[col]) for r in rs if r.get(col) is not None]
                    o[as_] = (max(vals) if vals else None) if agg == "max" else len(rs) if agg == "count" else rs[0].get(col)
                out.append(o)
        else:
            out = [{as_: r.get(col) for col, as_, _ in specs} for r in rows]
        if order_by == "seq desc":
            out.sort(key=lambda r: r.get("seq") or 0, reverse=True)
        if order_by == "last asc":
            out.sort(key=lambda r: r.get("last") or "")
        return out[:limit] if limit else out

    def get_one(self, url, key, doctype, name):
        self.calls.append(("one", doctype, name))
        if self.fail:
            raise app.ShopUnreadable("down")
        return next((dict(r) for r in self.rows(doctype) if r.get("name") == name), None)

    def insert(self, url, key, doctype, doc):
        self.calls.append(("insert", doctype, doc.get("key")))
        if self.fail:
            raise app.ShopUnreadable("down")
        if self.before_insert:
            hook, self.before_insert = self.before_insert, None
            hook(doc)
        with self.lock:
            if any(r.get("name") == doc["key"] for r in self.rows(doctype)):
                raise app.Taken()
            rec = dict(doc, name=doc["key"])
            self.rows(doctype).append(rec)
        return rec

    def update(self, url, key, doctype, name, values, timeout=None):
        self.calls.append(("update", doctype, name, dict(values)))
        if self.fail:
            raise app.ShopUnreadable("down")
        with self.lock:
            for r in self.rows(doctype):
                if r.get("name") == name:
                    r.update(values)
                    return dict(r)
        raise app.ShopUnreadable("404")

    def delete(self, url, key, doctype, name):
        self.calls.append(("delete", doctype, name))
        if self.fail:
            raise app.ShopUnreadable("down")
        with self.lock:
            before = len(self.rows(doctype))
            self.tables[doctype] = [r for r in self.rows(doctype) if r.get("name") != name]
            self.deleted = getattr(self, "deleted", []) + ([(doctype, name)] if len(self.tables[doctype]) < before else [])

    # ── a pharmacy, ready to sell ────────────────────────────────────────────

    def pharmacy(self, today: str = "2026-10-22"):
        """Three schedules, three items in three groups, two pharmacists, two patients (one with a patient record), a walk-in
        profile."""
        self.add(f"{P} Settings", name="Default", hours_from_utc=0, walk_in_customers="Cash Sale\n")
        lft = iter(range(2, 100, 2))
        self.add("Item Group", name="All Item Groups", lft=1, rgt=100)
        for g, sched, directions in (("Rx", "POM", 1), ("CD", "", 0), ("OTC", "PMED", 0), ("Food", "", 0)):
            n = next(lft)
            self.add("Item Group", name=g, lft=n, rgt=n + 1, pp_rxc_schedule=sched, pp_rxc_needs_directions=directions)
        self.add(f"{P} Drug Schedule", name="POM", axis="Prescription", needs_prescription=1, pharmacist_only=1,
                 dispensary_only=1, validity_days=90, returnable=0, return_gives_back=1)
        self.add(f"{P} Drug Schedule", name="CD2", axis="Controlled", needs_prescription=1, pharmacist_only=1,
                 dispensary_only=1, validity_days=30, max_fills=1, qty_cap=20, freq_qty=40, freq_days=30,
                 needs_id_number=1, needs_birth_date=1, returnable=0, return_gives_back=1)
        self.add(f"{P} Drug Schedule", name="PMED", axis="Pharmacy", qty_cap=2, returnable=1, return_gives_back=1)
        for code, group, uom in (("AMOX", "Rx", "Nos"), ("TRAM", "CD", "Nos"), ("PARA", "OTC", "Nos"), ("BREAD", "Food", "Nos")):
            self.add("Item", name=code, stock_uom=uom, variant_of=None, pp_rxc_directions="as directed" if code == "AMOX" else "")
        self.add(f"{P} Item Schedule", parent="TRAM", schedule="CD2", effective_from=None)
        self.add(f"{P} Item Schedule", parent="TRAM", schedule="POM", effective_from=None)
        self.add("UOM Conversion Detail", parent="AMOX", uom="Strip", conversion_factor=7)
        self.add(f"{P} Pharmacist", name="ph@shop", user="ph@shop", full_name="P. Pharmacist", active=1,
                 valid_until="2027-10-22")
        self.add(f"{P} Pharmacist", name="old@shop", user="old@shop", active=1, valid_until="2026-10-21")
        for c in ("Ann", "Bob", "Cash Sale"):
            self.add("Customer", name=c)
        # the patients' identity and consent are records of the app's own (0.1.2): Ann has one, Bob none
        self.add(f"{P} Patient", name="a1b2c3d4e5", customer="Ann", id_number="ID-1", birth_date="1980-01-01", authority="")
        self.add("POS Profile", name="Dispensary", customer="Walk-in")
        return self

    def prescription(self, name, customer, item, qty, fills=1, written="2026-10-20", reference="", retained=0,
                     status="Active", directions=""):
        self.add(f"{P} Prescription", name=name, customer=customer, reference=reference or f"PAPER-{name}",
                 date_written=written, fills_authorised=fills, retained=retained, status=status, prescriber="Dr Who")
        self.add(f"{P} Prescription Item", parent=name, item_code=item, qty=qty, directions=directions)

    def booked(self, sale_ref, docstatus=1, name=None, is_return=0, key=""):
        self.add("POS Invoice", name=name or f"INV-{len(self.rows('POS Invoice')) + 1}", docstatus=docstatus,
                 custom_mpos_sale_ref=sale_ref.strip().lower(), custom_mpos_idempotency_key=key, is_return=is_return)

    def sent(self, park="PARK-1", sale_ref="sale-ph", owner="ph@shop", items=(("AMOX", 21),), rung_by="cash@shop",
             customer="Ann", rung=True):
        """0.1.5: a sale the pharmacist ``owner`` sent to a till (a park: a draft naming the till it is paid at), rung up
        there by ``rung_by`` (the park disabled onto the draft rung up in its place, which is theirs)."""
        draft = f"{park}-DRAFT"
        self.add("POS Invoice", name=park, docstatus=0, customer=customer, owner=owner, custom_settle_at_register="CASH-1",
                 custom_disabled=1 if rung else 0, custom_pos_recall_reference=draft if rung else None,
                 custom_mpos_sale_ref=sale_ref.strip().lower(), is_return=0)
        if rung:
            self.add("POS Invoice", name=draft, docstatus=0, customer=customer, owner=rung_by, custom_mpos_sale_ref="",
                     is_return=0)
        for code, qty in items:
            self.add("POS Invoice Item", parent=park, item_code=code, stock_qty=qty)

    def gone(self, *names):
        """Records deleted from the shop (a void deletes the park and its draft)."""
        self.tables["POS Invoice"] = [r for r in self.rows("POS Invoice") if r.get("name") not in names]

    def dispensings(self):
        return sorted(self.rows(f"{P} Dispensing"), key=lambda r: r["seq"])
