"""tools/deploy/copy_records.py: a shop's records move from one installed app to another — stdlib only:
    python3 -m unittest discover -s tools/deploy/tests -p "test_copy_records.py" -v

A stand-in site in memory: two installs (``ivendnext_bln`` and ``acme_bins``), their record types, a field on the shop's
Item, and records. Proven on a real site as well (the recipe's notes)."""

import copy as copylib
import io
import pathlib
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import copy_records as C  # noqa: E402


AUTONAME = {"Location": "field:location_name", "Aisle": "field:aisle_name", "Bin": "field:bin_code",
            "Item In Bin": "format:{bin}--{item}"}     # S2's own naming: each record named from its fields


def fields(*fs):
    return [{"fieldname": n, "fieldtype": t, **({"options": o} if o else {})} for n, t, o in fs]


def types(prefix, mv_name):
    return {
        f"{prefix} Location": fields(("location_name", "Data", None), ("kind", "Select", None)),
        f"{prefix} Aisle": fields(("aisle_name", "Data", None), ("location", "Link", f"{prefix} Location")),
        f"{prefix} Bin": fields(("bin_code", "Data", None), ("aisle", "Link", f"{prefix} Aisle")),
        f"{prefix} Item In Bin": fields(("bin", "Link", f"{prefix} Bin"), ("item", "Link", "Item"), ("qty", "Float", None),
                                        ("movements", "Table", mv_name)),
        mv_name: fields(("kind", "Data", None), ("qty", "Float", None)),
    }


class FakeSite:
    """The four calls copy_records makes, over dicts. ``renames`` gives a record type whose copies the site names itself."""

    def __init__(self, renames=()):
        self.renames, self.seq, self.writes = set(renames), 0, []
        self.meta = {**types("IVENDNEXT BLN", "IVENDNEXT BLN Bin Movement"),
                     **types("ACME BINS", "ACME BINS Bin Movement")}
        self.meta["ACME BINS Bin"].append({"fieldname": "zone", "fieldtype": "Data"})     # the partner's own field
        self.meta["Item"] = fields(("item_name", "Data", None), ("ivendnext_bln_default_bin", "Link", "IVENDNEXT BLN Bin"),
                                   ("acme_bins_default_bin", "Link", "ACME BINS Bin"))
        self.rec = {t: {} for t in self.meta}
        self.installs = {
            "ivendnext_bln": self._install("IVENDNEXT BLN", "ivendnext_bln_default_bin"),
            "acme_bins": self._install("ACME BINS", "acme_bins_default_bin"),
        }
        P = "IVENDNEXT BLN"
        self.rec[f"{P} Location"]["Floor"] = {"name": "Floor", "location_name": "Floor", "kind": "Shop floor", "docstatus": 0}
        self.rec[f"{P} Aisle"]["A1"] = {"name": "A1", "aisle_name": "A1", "location": "Floor", "docstatus": 0}
        self.rec[f"{P} Bin"]["B-12"] = {"name": "B-12", "bin_code": "B-12", "aisle": "A1", "docstatus": 0}
        self.rec[f"{P} Bin"]["B-13"] = {"name": "B-13", "bin_code": "B-13", "aisle": "A1", "docstatus": 2}   # cancelled
        self.rec[f"{P} Item In Bin"]["B-12--MILK"] = {"name": "B-12--MILK", "bin": "B-12", "item": "MILK", "qty": 3,
                                                      "docstatus": 0, "movements": [{"kind": "Sale", "qty": -1, "idx": 1,
                                                                                     "name": "x1", "parent": "B-12--MILK"}]}
        self.rec["Item"]["MILK"] = {"name": "MILK", "item_name": "Milk", "ivendnext_bln_default_bin": "B-12"}

    def _install(self, prefix, field):
        items = [{"kind": "doctype", "name": t, "istable": t.endswith("Movement")} for t in self.meta if t.startswith(prefix)]
        items.reverse()                  # listed against the links' order: the copy must find the order itself
        items.append({"kind": "custom_field", "dt": "Item", "fieldname": field})
        return {"app": "", "prefix": prefix, "status": "Installed", "items": __import__("json").dumps(items)}

    def get(self, doctype, name):
        if doctype == C.INSTALL:
            return self.installs.get(name)
        if doctype == "DocType":
            if name not in self.meta:
                return None
            auto = "hash" if name in self.renames else AUTONAME.get(name.split(" ", 2)[-1], "")
            return {"fields": self.meta[name], "autoname": auto}
        r = self.rec.get(doctype, {}).get(name)
        return copylib.deepcopy(r) if r else None

    def names(self, doctype, filters=None, fields=("name",)):
        rows = list(self.rec[doctype].values())
        for f in filters or []:
            rows = [r for r in rows if r.get(f[0])] if f[1] == "is" else rows
        return [{k: r.get(k) for k in fields} for r in rows]

    def insert(self, doctype, doc):
        self.writes.append(("insert", doctype, doc))
        name = doc.get("name")
        if doctype in self.renames:
            self.seq += 1
            name = f"NEW-{self.seq}"
        for fn, f in ((f["fieldname"], f) for f in self.meta[doctype]):
            if f.get("fieldtype") == "Link" and f.get("options", "").startswith("ACME BINS") and doc.get(fn):
                assert doc[fn] in self.rec[f["options"]], f"{doctype}.{fn} links {doc[fn]}, not yet copied"
        self.rec[doctype][name] = {**doc, "name": name, "docstatus": doc.get("docstatus", 0)}
        return {"name": name}

    def update(self, doctype, name, values):
        self.writes.append(("update", doctype, name, values))
        self.rec[doctype][name].update(values)


def run(site, write=True):
    with redirect_stdout(io.StringIO()) as out:
        rc = C.copy(site, "ivendnext_bln", "acme_bins", write=write)
    return rc, out.getvalue()


class Copy(unittest.TestCase):
    def test_every_record_is_copied_with_its_values(self):
        s = FakeSite()
        rc, _ = run(s)
        self.assertEqual(rc, 0)
        self.assertEqual(s.rec["ACME BINS Bin"]["B-12"]["aisle"], "A1")
        self.assertEqual(s.rec["ACME BINS Item In Bin"]["B-12--MILK"]["qty"], 3)
        self.assertEqual(s.rec["ACME BINS Location"]["Floor"]["kind"], "Shop floor")

    def test_records_are_written_in_the_order_their_links_need(self):
        s = FakeSite()
        run(s)       # the stand-in refuses a link to a record not yet copied
        order = [w[1] for w in s.writes if w[0] == "insert"]
        self.assertLess(order.index("ACME BINS Aisle"), order.index("ACME BINS Bin"))
        self.assertLess(order.index("ACME BINS Bin"), order.index("ACME BINS Item In Bin"))

    def test_a_tables_rows_are_copied_without_their_old_ids(self):
        s = FakeSite()
        run(s)
        rows = s.rec["ACME BINS Item In Bin"]["B-12--MILK"]["movements"]
        self.assertEqual(rows, [{"kind": "Sale", "qty": -1}])

    def test_a_cancelled_record_is_not_copied(self):
        s = FakeSite()
        _, out = run(s)
        self.assertNotIn("B-13", s.rec["ACME BINS Bin"])
        self.assertIn("1 cancelled not copied", out)

    def test_the_value_on_the_shops_own_record_moves_to_your_field(self):
        s = FakeSite()
        run(s)
        self.assertEqual(s.rec["Item"]["MILK"]["acme_bins_default_bin"], "B-12")

    def test_a_record_the_site_names_itself_is_linked_by_its_new_name(self):
        s = FakeSite(renames={"ACME BINS Bin"})
        run(s)
        new = next(n for n, r in s.rec["ACME BINS Bin"].items() if r["bin_code"] == "B-12")
        self.assertEqual(s.rec["ACME BINS Item In Bin"]["B-12--MILK"]["bin"], new)
        self.assertEqual(s.rec["Item"]["MILK"]["acme_bins_default_bin"], new)

    def test_a_second_run_copies_nothing(self):
        s = FakeSite()
        run(s)
        n = len(s.writes)
        rc, out = run(s)
        self.assertEqual((rc, len(s.writes)), (0, n))
        self.assertIn("0 copied, 1 already there", out)

    def test_without_write_nothing_is_written(self):
        s = FakeSite()
        rc, out = run(s, write=False)
        self.assertEqual((rc, s.writes), (0, []))
        self.assertIn("nothing written", out)

    def test_a_field_your_type_lacks_is_named_not_guessed(self):
        s = FakeSite()
        s.meta["ACME BINS Location"] = [f for f in s.meta["ACME BINS Location"] if f["fieldname"] != "kind"]
        _, out = run(s)
        self.assertIn("ACME BINS Location has no field kind", out)
        self.assertNotIn("kind", s.rec["ACME BINS Location"]["Floor"])


class Safety(unittest.TestCase):
    def test_a_value_already_set_in_your_app_is_never_overwritten(self):
        s = FakeSite()
        run(s)
        s.rec["Item"]["MILK"]["acme_bins_default_bin"] = "B-99"        # the customer changed it in your app
        run(s)
        self.assertEqual(s.rec["Item"]["MILK"]["acme_bins_default_bin"], "B-99")

    def test_a_submitted_record_is_copied_submitted_in_one_step(self):
        s = FakeSite()
        s.rec["IVENDNEXT BLN Aisle"]["A1"]["docstatus"] = 1
        run(s)
        self.assertEqual(s.rec["ACME BINS Aisle"]["A1"]["docstatus"], 1)
        self.assertFalse([w for w in s.writes if w[0] == "update" and w[1] == "ACME BINS Aisle"])

    def test_a_record_type_the_site_names_is_not_copied_twice(self):
        s = FakeSite(renames={"ACME BINS Bin"})
        run(s)
        with self.assertRaises(C.Refused) as e:
            run(s)
        self.assertIn("ACME BINS Bin already holds records", str(e.exception))

    def test_a_link_is_mapped_in_its_own_record_types_names_only(self):
        s = FakeSite(renames={"ACME BINS Bin", "ACME BINS Aisle"})
        s.rec["IVENDNEXT BLN Aisle"]["B-12"] = {"name": "B-12", "aisle_name": "B-12", "location": "Floor", "docstatus": 0}
        items = __import__("json").loads(s.installs["ivendnext_bln"]["items"])
        items.sort(key=lambda i: 0 if i.get("name", "").endswith("Aisle") else 1)    # its names are looked at first
        s.installs["ivendnext_bln"]["items"] = __import__("json").dumps(items)
        run(s)                         # an aisle named like a bin: a bin link must take the bin's copy, never the aisle's
        bin_copy = next(n for n, r in s.rec["ACME BINS Bin"].items() if r["bin_code"] == "B-12")
        self.assertEqual(s.rec["ACME BINS Item In Bin"]["B-12--MILK"]["bin"], bin_copy)

    def test_a_record_that_did_not_arrive_fails_the_run(self):
        s = FakeSite()
        real = s.insert
        s.insert = lambda dt, doc: {"name": doc["name"]} if dt == "ACME BINS Item In Bin" else real(dt, doc)
        rc, out = run(s)               # the site answered, but the record is not there
        self.assertEqual(rc, 1)
        self.assertIn("lacks the copy of 1 record(s): B-12--MILK", out)


class Refused(unittest.TestCase):
    def test_a_record_type_with_no_match_in_yours_is_refused(self):
        s = FakeSite()
        items = [i for i in __import__("json").loads(s.installs["acme_bins"]["items"]) if i.get("name") != "ACME BINS Aisle"]
        s.installs["acme_bins"]["items"] = __import__("json").dumps(items)
        with self.assertRaises(C.Refused) as e:
            run(s)
        self.assertIn("IVENDNEXT BLN Aisle", str(e.exception))
        self.assertEqual(s.writes, [])

    def test_an_app_that_is_not_installed_is_refused(self):
        s = FakeSite()
        s.installs["ivendnext_bln"]["status"] = "uninstalled"
        with self.assertRaises(C.Refused):
            run(s)


if __name__ == "__main__":
    unittest.main()
