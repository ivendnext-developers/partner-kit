"""A stand-in shop for S39's service tests: the records the service reads and the one record type it writes, behind the
same four calls as ``service/app.py``'s ``ShopApi`` (``get_list``, ``get_one``, ``insert``, ``update``). Filters are the
shapes the service sends: ``[field, "=" | "in", value]``. An insert whose name exists raises ``Taken`` (the shop's 409).
``fail`` makes every call raise ``ShopUnreadable`` (a shop that is down); ``before_insert`` runs a hook before an insert
(another till taking the number first)."""

from __future__ import annotations

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
        return True

    def get_list(self, url, key, doctype, fields, filters=None, parent=None, order_by=None, limit=0):
        self.calls.append(("list", doctype, filters, list(fields)))
        if self.fail:
            raise app.ShopUnreadable("down")
        with self.lock:
            out = [{f: r.get(f) for f in fields} for r in self.rows(doctype) if self._match(r, filters)]
        if order_by == "seq desc":
            out.sort(key=lambda r: r.get("seq") or 0, reverse=True)
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

    def update(self, url, key, doctype, name, values):
        self.calls.append(("update", doctype, name, dict(values)))
        if self.fail:
            raise app.ShopUnreadable("down")
        with self.lock:
            for r in self.rows(doctype):
                if r.get("name") == name:
                    r.update(values)
                    return dict(r)
        raise app.ShopUnreadable("404")

    # ── a pharmacy, ready to sell ────────────────────────────────────────────

    def pharmacy(self, today: str = "2026-10-22"):
        """Three schedules, three items in three groups, two pharmacists, two patients, a walk-in profile."""
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
        self.add(f"{P} Pharmacist", name="ph@shop", user="ph@shop", active=1, valid_until="2027-10-22")
        self.add(f"{P} Pharmacist", name="old@shop", user="old@shop", active=1, valid_until="2026-10-21")
        self.add("Customer", name="Ann", pp_rxc_id_number="ID-1", pp_rxc_birth_date="1980-01-01", pp_rxc_authority="")
        self.add("Customer", name="Bob", pp_rxc_id_number="", pp_rxc_birth_date="", pp_rxc_authority="")
        self.add("Customer", name="Cash Sale", pp_rxc_id_number="", pp_rxc_birth_date="", pp_rxc_authority="")
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

    def dispensings(self):
        return sorted(self.rows(f"{P} Dispensing"), key=lambda r: r["seq"])
