"""S57's laptop tests: the manifest passes the kit's checker and nothing the retailer's install refuses; the app calls
no outside address and holds no money, and its one field on a retailer's record (Stock Entry's Donation) is optional;
Give receipt ticks Receipt given and a given receipt is cancelled by a manager only; the receipt and the report read the
donation's state, never a tick box (a read-only box is a screen rule); the save rule locks every field the receipt prints
once it is given, the customer's own name excepted; a customer's name and e-mail are read-only copies, a donor who is not
one is typed; the report lists donations not cancelled, newest first; the receipt reads only fields that exist, skips a
blank row and states no value; the rights and the help page. Data only: no service.

    python3 -m unittest discover -s samples/s57_donation_intake/tests -p 'test_*.py'
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
DONATION, GOODS = f"{P} Donation", f"{P} Goods"
DT = {d["name"]: d for d in MANIFEST["doctypes"]}
OUTSIDE = ("extension_subscriptions", "webhooks", "registered_applications", "remote_keys", "desk_actions")
(WF,) = MANIFEST["workflows"]
(LOCK,) = MANIFEST["save_rules"]
(PF,) = MANIFEST["print_formats"]


def fields(dt):
    return {f["fieldname"]: f for f in DT[dt]["fields"]}


def rights(role):
    row = next(p for p in DT[DONATION]["permissions"] if p["role"] == role)
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
        self.assertEqual(money, [])                                        # the receipt states no value
        (cf,) = MANIFEST["custom_fields"]
        self.assertEqual((cf["dt"], cf["fieldtype"], cf["options"]), ("Stock Entry", "Link", DONATION))
        self.assertTrue(cf["fieldname"].startswith(MANIFEST["app"] + "_"))    # the reserved field prefix
        self.assertFalse(cf.get("reqd") or cf.get("read_only") or cf.get("hidden") or cf.get("default"))
        self.assertEqual(cf.get("allow_on_submit"), 1)                      # a submitted receipt can still name it
        self.assertIn('"Material Receipt"', cf["depends_on"])               # shown on a Material Receipt only

    def test_give_receipt_ticks_receipt_given_and_the_receipt_reads_the_state(self):
        self.assertEqual((state("Receipt given")["update_field"], state("Receipt given")["update_value"]), ("receipt_given", "1"))
        self.assertNotIn("update_field", state("Received"))
        self.assertNotIn("update_field", state("Cancelled"))     # nothing to tick: the receipt and the report read the state
        f = fields(DONATION)
        self.assertEqual((f["receipt_given"]["fieldtype"], f["receipt_given"].get("read_only")), ("Check", 1))
        self.assertFalse(f["receipt_given"].get("default"))
        self.assertNotIn("cancelled", f)
        # read-only is the browser's rule only: the API can tick a box, so the print never decides by one (review, run 22)
        html = PF["html"]
        self.assertNotIn("doc.receipt_given", html)
        self.assertIn('state.endswith(" Cancelled")', html)
        self.assertIn('state.endswith(" Receipt given")', html)

    def test_a_given_receipt_is_cancelled_by_a_manager_only_and_nothing_leaves_cancelled(self):
        m = moves()
        self.assertEqual(m[("Received", "Give receipt")], ("Receipt given", "Sales User"))
        self.assertEqual(m[("Received", "Cancel")], ("Cancelled", "Sales User"))
        self.assertEqual(m[("Receipt given", "Cancel")], ("Cancelled", "Sales Manager"))
        self.assertEqual(set(m), {("Received", "Give receipt"), ("Received", "Cancel"), ("Receipt given", "Cancel")})
        self.assertEqual(state("Cancelled")["allow_edit"], "System Manager")

    def test_the_lock_holds_every_field_the_receipt_prints_once_it_is_given(self):
        self.assertEqual((LOCK["record_type"], LOCK["kind"], LOCK["mode"]), (DONATION, "locked_in_state", "refuse"))
        self.assertEqual(set(LOCK["states"]), {f"{P} Receipt given", f"{P} Cancelled"})
        # the customer's own name is fetched again at each save: locking it would refuse every later save after the
        # customer is renamed, so the customer link is locked and the name follows the customer (README, bounds)
        printed = set(re.findall(r"\bdoc\.(\w+)", PF["html"])) - {"get_formatted", "name", "workflow_state", "customer_name"}
        self.assertLessEqual(printed | {"goods", "customer", "receipt_given"}, set(LOCK["locked_fields"]))
        self.assertNotIn("customer_name", LOCK["locked_fields"])
        self.assertLessEqual(set(LOCK["locked_fields"]), set(fields(DONATION)))
        self.assertLessEqual(len(LOCK["message"]), 140)
        self.assertNotIn("enabled", LOCK)   # a manifest installs every rule switched off: the README's set-up switches it on
        readme = (HERE.parent / "README.md").read_text()
        self.assertIn("**Switch the lock on**", readme)
        self.assertIn(LOCK["rule_name"], readme)

    def test_a_customers_details_are_read_only_copies_and_a_walk_up_donor_is_typed(self):
        f = fields(DONATION)
        for name, src in (("customer_name", "customer.customer_name"), ("customer_email", "customer.custom_email")):
            self.assertEqual((f[name]["fetch_from"], f[name].get("read_only")), (src, 1), name)   # fetched again at each save
        for name in ("donor_name", "donor_phone", "donor_email", "donor_address"):
            self.assertFalse(f[name].get("fetch_from") or f[name].get("read_only") or f[name].get("reqd"), name)
        self.assertFalse(f["customer"].get("reqd"))

    def test_donations_lists_those_not_cancelled_newest_first(self):
        (r,) = MANIFEST["reports"]
        self.assertEqual((r["ref_doctype"], r["filters"], r["order_by"]), (DONATION, [["workflow_state", "!=", f"{P} Cancelled"]], "received_on desc"))
        self.assertLessEqual(set(r["columns"]) - {"name"}, set(fields(DONATION)))
        # a Check the report filters on is never a standard filter: Desk turns the saved filter into the unticked box and
        # drops it (runs 11 and 20)
        f = fields(DONATION)
        self.assertFalse([x[0] for x in r["filters"] if x[0] in f and f[x[0]]["fieldtype"] == "Check" and f[x[0]].get("in_standard_filter")])

    def test_the_goods_table_is_never_required(self):
        tables = [f for f in DT[DONATION]["fields"] if f["fieldtype"] == "Table"]
        self.assertEqual([f["options"] for f in tables], [GOODS])
        self.assertFalse([f["fieldname"] for f in tables if f.get("reqd")])   # Desk drops an all-blank row: none is no rows
        self.assertEqual(DT[GOODS].get("istable"), 1)

    def test_the_receipt_reads_only_fields_that_exist_and_states_no_value(self):
        html = PF["html"]
        for var, dt in (("doc", DONATION), ("g", GOODS)):
            used = set(re.findall(rf"\b{var}\.(\w+)", html)) - {"get_formatted"}
            self.assertLessEqual(used, set(fields(dt)) | {"name", "workflow_state"}, var)   # the workflow adds workflow_state
        self.assertIn("{% for g in doc.goods if g.category or g.description %}", html)   # a blank row is never printed
        self.assertIn("This receipt describes the goods and states no value.", html)
        self.assertNotIn("No goods or services", html)    # whether a store gave something back is its own words to add
        self.assertIn('doc.donor_name or doc.customer_name or _("an anonymous donor")', html)
        self.assertLess(html.index("Cancelled: this is not a receipt."), html.index("Not yet a receipt"))   # a cancelled one says so first
        self.assertIn('dir="auto"', html)

    def test_a_customer_lists_its_donations(self):
        got = {(ln["doctype"], ln["link_doctype"], ln["link_fieldname"]) for ln in MANIFEST["links"]}
        self.assertEqual(got, {("Customer", DONATION, "customer")})

    def test_store_staff_take_donations_no_one_but_a_system_manager_deletes_and_stock_reads(self):
        self.assertEqual(rights("Sales User"), {"read", "write", "create", "report", "print"})
        self.assertNotIn("delete", rights("Sales Manager"))   # a given receipt is cancelled, never deleted: the donor keeps its number
        self.assertIn("delete", rights("System Manager"))
        self.assertEqual(rights("Stock User"), {"read"})   # to name a donation on a Material Receipt

    def test_the_donation_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (DONATION, "documentation"))
        self.assertTrue(ps["value"].endswith("donation_intake.html#donations"))


if __name__ == "__main__":
    unittest.main()
