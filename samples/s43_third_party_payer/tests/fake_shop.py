"""A stand-in shop for S43's service tests: the records the service reads and writes behind the same calls as
``service/app.py``'s ``ShopApi`` (``get_list``, ``get_one``, ``insert``, ``update``, ``feed``, ``bill_back``). Filters
are the shapes the service sends: ``[field, "=" | "in", value]``. An insert whose name exists answers the shop's
duplicate. ``fail`` makes every call raise ``ShopUnreadable`` (a shop that is down); ``door`` False makes
``bill_back`` answer as a POS app with no payer door; ``refuse`` makes the door refuse it in those words."""

from __future__ import annotations

import copy
import itertools

import app
import dataset

P = "PP ICP"
SHORT = {"payer_code": app.DOOR["payer"], "payer_plan": app.DOOR["plan"], "payer_member": app.DOOR["member"],
         "payer_claim_ref": app.DOOR["claim_ref"], "payer_prescription": app.DOOR["prescription"],
         "payer_prescriber": app.DOOR["prescriber"], "payer_prescriber_licence": app.DOOR["prescriber_licence"],
         "payer_share": app.DOOR["line_payer"], "patient_share": app.DOOR["line_patient"],
         "payer_covered_qty": app.DOOR["line_qty"], "payer_gtin": app.DOOR["line_gtin"],
         "payer_back": app.DOOR["line_back"], "payer_journal": app.DOOR["journal"]}


class FakeShop:
    def __init__(self):
        self.tables: dict = {}
        self.calls: list = []
        self.events: list = []
        self.done: set = set()
        self.failed: list = []
        self.billed: list = []
        self.fail = False
        self.door = True
        self.refuse = None
        self.seq = itertools.count(1)

    def add(self, doctype, **rec):
        self.tables.setdefault(doctype, []).append(copy.deepcopy(rec))
        return rec

    def rows(self, doctype):
        return self.tables.setdefault(doctype, [])

    def find(self, doctype, name):
        return next((r for r in self.rows(doctype) if r.get("name") == name), None)

    @staticmethod
    def _match(r, filters):
        for f, op, v in filters or []:
            have = r.get(f)
            if (op == "=" and have != v) or (op == "in" and have not in v):
                return False
        return True

    def _down(self, what):
        self.calls.append(what)
        if self.fail:
            raise app.ShopUnreadable("down")

    def get_list(self, url, key, doctype, fields, filters=None, limit=0):
        self._down(("list", doctype, filters))
        return [{f: copy.deepcopy(r.get(f)) for f in fields} for r in self.rows(doctype) if self._match(r, filters)]

    def get_one(self, url, key, doctype, name):
        self._down(("one", doctype, name))
        r = self.find(doctype, name)
        return copy.deepcopy(r) if r else None

    def insert(self, url, key, doctype, doc):
        self._down(("insert", doctype))
        name = doc.get("claim_ref") if doctype == f"{P} Claim" else doc.get("name") or f"{doctype[-5:]}-{next(self.seq)}"
        if self.find(doctype, name):
            return {"duplicate": True}
        rec = dict(copy.deepcopy(doc), name=name)
        for i, l in enumerate(rec.get("lines") or []):
            l.setdefault("name", f"{name}-row{i + 1}")
        self.rows(doctype).append(rec)
        return {"data": copy.deepcopy(rec)}

    def update(self, url, key, doctype, name, values):
        self._down(("update", doctype, name))
        r = self.find(doctype, name)
        r.update(copy.deepcopy(values))
        return {"data": copy.deepcopy(r)}

    def feed(self, url, key, call, body):
        self._down(("feed", call))
        if call == "events":
            return {"events": [e for e in self.events if e["id"] not in self.done][: body.get("limit", 50)],
                    "page": None}
        if call == "done":
            self.done.update(body["ids"])
            return {"done": len(body["ids"])}
        self.failed.append(body)
        return {}

    def bill_back(self, url, key, body):
        self._down(("bill_back", body.get("claim_ref")))
        if not self.door:
            return None
        if self.refuse:                         # the door's own words, as ShopApi reads them from its 417
            return {"refused": self.refuse}
        self.billed.append(body)
        return {"journal": f"JV-{len(self.billed)}"}

    # ── a shop with the generic insurer set up ────────────────────────────────

    def generic(self):
        ds = dataset.load("datasets/generic_insurer.json")
        for r in dataset.records(ds):
            dt = r.pop("doctype")
            self.add(dt, name=r.get("code") or r["title"], **r)
        self.add("Customer", name="Generic Insurer", disabled=0)     # the payer's own record (the data set's)
        self.add("Customer", name="C1", **{"pp_icp_insurance_barred": 0})
        self.add("Customer", name="C2", **{"pp_icp_insurance_barred": 1})
        self.add(f"{P} Member", name="m1", customer="C1", plan="Generic Silver", payer="GEN-INS", active=1,
                 member_number="GEN-000123", card_serial="", policy_number="POL-9", valid_from="2026-01-01",
                 valid_to="2026-12-31")
        self.add(f"{P} Member", name="m2", customer="C2", plan="Generic Silver", payer="GEN-INS", active=1,
                 member_number="GEN-000999", valid_to="2026-12-31")
        self.add("Price List", name="Generic Insurer Prices", currency="KES")
        for code, group, rate in (("PHD-AMOX-500", "Prescription Medicines", 120),
                                  ("PHD-PARA-500", "Over-the-Counter Medicines", 25),
                                  ("PHD-TRAM-50", "Controlled Medicines", 0)):
            self.add("Item", name=code, item_group=group, stock_uom="Nos")
            self.add("Item Price", item_code=code, price_list="Generic Insurer Prices", uom="Nos", price_list_rate=rate)
        self.add("Item", name="PHD-VITC", item_group="Over-the-Counter Medicines")   # on no list of the insurer
        return self

    def book(self, name, lines, doctype="POS Invoice", **kw):
        """A sale as the payer door books it (payer.md §4b: its fields' own names, from ``app.DOOR``), with its feed
        event. The tests write the short names below; each is stored under the door's name."""
        doc = {"name": name, "customer": "C1", "posting_date": "2026-10-23", "set_warehouse": "Pharmacy Dispensary",
               "is_return": 0, "payer_code": "GEN-INS", "payer_plan": "Generic Silver", "payer_member": "m1",
               "payer_claim_ref": f"GEN-INS-{name}", "payer_prescription": "RX-77", "payer_prescriber": "Dr A",
               "payer_prescriber_licence": "L-1", "payer_journal": f"JV-{name}", "items": lines}
        doc.update(kw)
        doc = {SHORT.get(k, k): v for k, v in doc.items()}
        doc["items"] = [{SHORT.get(k, k): v for k, v in it.items()} for it in doc.get("items") or []]
        self.add(doctype, **doc)
        ev = {"POS Invoice": "return.booked" if doc["is_return"] else "sale.booked",
              "Sales Invoice": "invoice.booked"}[doctype]
        self.events.append({"id": f"ev-{len(self.events) + 1}", "event": ev, "doc_type": doctype, "doc_name": name})
        return doc
