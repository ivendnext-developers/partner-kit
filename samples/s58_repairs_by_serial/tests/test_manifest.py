"""S58's laptop tests: the manifest passes the kit's checker and nothing the retailer's install refuses; the app calls
no outside address and holds no money, and its one field on a retailer's record (Stock Entry's Repair) is optional;
the workflow's moves, nothing leaving Collected or Cancelled, and a repair in work cancelled by a manager only; the slip
reads the repair's step, never a tick box (a read-only box is a screen rule, and Duplicate copies a box but never the
step); the save rule locks every field the slip prints once the repair is collected, the copies fetched from the serial
and the customer excepted (they are fetched again at each save); those copies are read only; the report lists the
repairs not collected, by the date promised; the slip reads only fields that exist, skips a blank row and shows the work
only once the unit is ready; the serial, the customer and the sale list their repairs; the rights and the help page.
Data only: no service.

    python3 -m unittest discover -s samples/s58_repairs_by_serial/tests -p 'test_*.py'
"""
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "manifest"))
import site_rules  # noqa: E402
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
P = MANIFEST["prefix"]
REPAIR, TEST, PART = f"{P} Repair", f"{P} Test", f"{P} Part"
DT = {d["name"]: d for d in MANIFEST["doctypes"]}
OUTSIDE = ("extension_subscriptions", "webhooks", "registered_applications", "remote_keys", "desk_actions")
(WF,) = MANIFEST["workflows"]
(LOCK,) = MANIFEST["save_rules"]
(PF,) = MANIFEST["print_formats"]
FETCHED = {
    "item_code": "serial_no.item_code",
    "item_name": "serial_no.item_name",
    "warranty_until": "serial_no.warranty_expiry_date",
    "customer_name": "customer.customer_name",
    "customer_phone": "customer.custom_phone_no",
}


def fields(dt):
    return {f["fieldname"]: f for f in DT[dt]["fields"]}


def rights(role):
    row = next(p for p in DT[REPAIR]["permissions"] if p["role"] == role)
    return {k for k, v in row.items() if k != "role" and v}


def state(name):
    return next(s for s in WF["states"] if s["state"] == f"{P} {name}")


def moves():
    cut = len(P) + 1
    return {(t["state"][cut:], t["action"][cut:]): (t["next_state"][cut:], t["allowed"]) for t in WF["transitions"]}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])
        self.assertEqual(site_rules.refusals(MANIFEST), [])   # nor anything the retailer's install refuses

    def test_no_outside_address_no_money_and_one_optional_field_on_stock_entry(self):
        self.assertEqual(MANIFEST["allowed_urls"], [])
        self.assertFalse([k for k in OUTSIDE if MANIFEST.get(k)])          # no service, feed, key or Desk action
        money = [(d, f["fieldname"]) for d in DT for f in DT[d]["fields"] if f["fieldtype"] in ("Currency", "Percent")]
        self.assertEqual(money, [])                                        # the till charges the repair, not the app
        (cf,) = MANIFEST["custom_fields"]
        self.assertEqual((cf["dt"], cf["fieldtype"], cf["options"]), ("Stock Entry", "Link", REPAIR))
        self.assertTrue(cf["fieldname"].startswith(MANIFEST["app"] + "_"))    # the reserved field prefix
        self.assertFalse(cf.get("reqd") or cf.get("read_only") or cf.get("hidden") or cf.get("default"))
        self.assertEqual(cf.get("allow_on_submit"), 1)                      # a submitted issue can still name it
        self.assertIn('"Material Issue"', cf["depends_on"])                 # shown on a Material Issue only

    def test_no_tick_box_the_slip_reads_the_step(self):
        # read-only is the browser's rule only (the API sets a box) and Desk's Duplicate copies a box but never the
        # workflow's own step (no_copy): so nothing here is a tick, and the slip reads the step
        self.assertFalse([s["state"] for s in WF["states"] if "update_field" in s])
        self.assertFalse([n for d in DT for n, x in fields(d).items() if x["fieldtype"] == "Check"])
        html = PF["html"]
        self.assertIn('state.endswith(" Cancelled")', html)
        self.assertIn('state.endswith(" Ready to collect") or state.endswith(" Collected")', html)

    def test_the_repairs_moves_nothing_leaves_collected_and_a_manager_cancels_work_begun(self):
        self.assertEqual(moves(), {
            ("Received", "Start work"): ("In repair", "Sales User"),
            ("In repair", "Ready"): ("Ready to collect", "Sales User"),
            ("Ready to collect", "Back to work"): ("In repair", "Sales User"),
            ("Ready to collect", "Hand over"): ("Collected", "Sales User"),
            ("Received", "Cancel"): ("Cancelled", "Sales User"),
            ("In repair", "Cancel"): ("Cancelled", "Sales Manager"),
        })
        self.assertEqual(state("Cancelled")["allow_edit"], "System Manager")
        self.assertEqual({s["state"] for s in WF["states"]},
                         {f"{P} {n}" for n in ("Received", "In repair", "Ready to collect", "Collected", "Cancelled")})

    def test_the_lock_holds_every_field_the_slip_prints_once_collected(self):
        self.assertEqual((LOCK["record_type"], LOCK["kind"], LOCK["mode"]), (REPAIR, "locked_in_state", "refuse"))
        self.assertEqual(set(LOCK["states"]), {f"{P} Collected", f"{P} Cancelled"})
        # a copy fetched from the serial or the customer is fetched again at each save: locking it would refuse every
        # later save once the source changes, so the link is locked and the copy follows it (README, bounds)
        html = PF["html"]
        printed = (set(re.findall(r"\bdoc\.(\w+)", html)) | set(re.findall(r'doc\.get_formatted\("(\w+)"\)', html))) \
            - {"get_formatted", "name", "workflow_state"}
        self.assertLessEqual(printed - set(FETCHED), set(LOCK["locked_fields"]))
        self.assertFalse(set(FETCHED) & set(LOCK["locked_fields"]))
        # the history the slip does not print is locked too (the kind, the technician); the sale is not: a till sale
        # cancelled later would leave a link the framework refuses to save, and a locked one could then never change
        self.assertEqual(set(LOCK["locked_fields"]), {"serial_no", "kind", "customer", "store", "received_on", "ready_by",
                                                      "fault", "condition", "tests", "work_done", "technician", "parts"})
        self.assertLessEqual(set(LOCK["locked_fields"]), set(fields(REPAIR)))
        self.assertLessEqual(len(LOCK["message"]), 140)
        self.assertNotIn("enabled", LOCK)   # a manifest installs every rule switched off: the README's set-up switches it on
        readme = (HERE.parent / "README.md").read_text()
        self.assertIn("**Switch the lock on**", readme)
        self.assertIn(LOCK["rule_name"], readme)

    def test_what_is_read_from_the_serial_and_the_customer_is_a_read_only_copy(self):
        f = fields(REPAIR)
        for name, src in FETCHED.items():
            self.assertEqual((f[name].get("fetch_from"), f[name].get("read_only")), (src, 1), name)
        self.assertEqual((f["serial_no"]["options"], f["serial_no"].get("reqd")), ("Serial No", 1))
        self.assertFalse(f["customer"].get("reqd"))   # a unit of the store's own stock has no customer
        typed = [n for n, x in f.items() if x.get("fetch_from") and n not in FETCHED]
        self.assertEqual(typed, [])

    def test_open_repairs_lists_those_not_collected_by_the_date_promised(self):
        (r,) = MANIFEST["reports"]
        self.assertEqual((r["ref_doctype"], r["order_by"]), (REPAIR, "ready_by asc"))
        self.assertEqual(r["filters"], [["workflow_state", "not in", [f"{P} Collected", f"{P} Cancelled"]]])
        self.assertLessEqual(set(r["columns"]) - {"name"}, set(fields(REPAIR)))

    def test_no_table_is_ever_required(self):
        tables = [f for f in DT[REPAIR]["fields"] if f["fieldtype"] == "Table"]
        self.assertEqual(sorted(f["options"] for f in tables), sorted([TEST, PART]))
        self.assertFalse([f["fieldname"] for f in tables if f.get("reqd")])   # Desk drops an all-blank row: none is no rows
        self.assertEqual((DT[TEST].get("istable"), DT[PART].get("istable")), (1, 1))

    def test_the_slip_reads_only_fields_that_exist_and_shows_the_work_once_ready(self):
        html = PF["html"]
        for var, dt in (("doc", REPAIR), ("t", TEST), ("p", PART)):
            used = set(re.findall(rf"\b{var}\.(\w+)", html)) - {"get_formatted"}
            self.assertLessEqual(used, set(fields(dt)) | {"name", "workflow_state"}, var)   # the workflow adds workflow_state
        self.assertIn("{% for t in doc.tests if t.test %}", html)               # a blank row is never printed
        self.assertIn("{% for p in doc.parts if p.part or p.item %}", html)
        ready = html.index('state.endswith(" Ready to collect")')
        for shown_once_ready in ("doc.work_done", "doc.tests", "doc.parts"):
            self.assertGreater(html.index(shown_once_ready), ready, shown_once_ready)
        self.assertIn('dir="auto"', html)
        # a Jinja print places the letter head itself: only Desk's standard layout adds it (APPF run 22)
        self.assertTrue(html.split(">", 1)[1].lstrip().startswith("{% if letter_head and not no_letterhead %}"))
        self.assertIn("{{ letter_head }}", html)

    def test_the_serial_the_customer_and_the_sale_list_their_repairs(self):
        got = {(ln["doctype"], ln["link_doctype"], ln["link_fieldname"]) for ln in MANIFEST["links"]}
        self.assertEqual(got, {("Serial No", REPAIR, "serial_no"), ("Customer", REPAIR, "customer"),
                               ("POS Invoice", REPAIR, "sale")})

    def test_store_staff_keep_repairs_no_one_but_a_system_manager_deletes_and_stock_reads(self):
        self.assertEqual(rights("Sales User"), {"read", "write", "create", "report", "print"})
        self.assertNotIn("delete", rights("Sales Manager"))   # a unit's history is cancelled, never deleted
        self.assertIn("delete", rights("System Manager"))
        self.assertEqual(rights("Stock User"), {"read"})   # to name a repair on a Material Issue

    def test_the_repair_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (REPAIR, "documentation"))
        self.assertTrue(ps["value"].endswith("repairs_by_serial.html#repairs"))


if __name__ == "__main__":
    unittest.main()
