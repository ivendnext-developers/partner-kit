"""S53's laptop tests: the manifest passes the kit's checker and nothing the retailer's install refuses; the app calls
no outside address and holds no money; the ticket's workflow ticks the two boxes the report and the retailer's own message
read, and leaves a closed ticket to a System Manager on Desk's screen; the phone and e-mail are the customer's, read only;
the report lists open tickets by Ready by; the slip and the garment tag read only fields that exist and skip a blank
measurement row; the rights and the help page. Data only: no service.

    python3 -m unittest discover -s samples/s53_alteration_tickets/tests -p 'test_*.py'
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
TICKET, GARMENT, MEASURE = f"{P} Ticket", f"{P} Garment", f"{P} Measure"
DT = {d["name"]: d for d in MANIFEST["doctypes"]}
OUTSIDE = ("extension_subscriptions", "webhooks", "registered_applications", "remote_keys", "desk_actions", "custom_fields")
(WF,) = MANIFEST["workflows"]


def fields(dt):
    return {f["fieldname"]: f for f in DT[dt]["fields"]}


def rights(role):
    row = next(p for p in DT[TICKET]["permissions"] if p["role"] == role)
    return {k for k, v in row.items() if k != "role" and v}


def state(name):
    return next(s for s in WF["states"] if s["state"] == f"{P} {name}")


def moves():
    return {(t["state"][len(P) + 1:], t["action"][len(P) + 1:]): t["next_state"][len(P) + 1:] for t in WF["transitions"]}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])
        self.assertEqual(site_rules.refusals(MANIFEST), [])   # nor anything the retailer's install refuses

    def test_no_outside_address_and_no_money_is_held(self):
        self.assertEqual(MANIFEST["allowed_urls"], [])
        self.assertFalse([k for k in OUTSIDE if MANIFEST.get(k)])          # no service, feed, key or field on a retailer's record
        money = [(d, f["fieldname"]) for d in DT for f in DT[d]["fields"] if f["fieldtype"] in ("Currency", "Percent")]
        self.assertEqual(money, [])                                        # the charge and the deposit stay at the till
        self.assertFalse(fields(TICKET)["sale"].get("reqd") or fields(TICKET)["order"].get("reqd"))

    def test_ready_ticks_ready_to_collect_and_going_back_unticks_it(self):
        self.assertEqual((state("Ready to collect")["update_field"], state("Ready to collect")["update_value"]), ("ready_to_collect", "1"))
        for back in ("With the tailor", "Fitting"):
            self.assertEqual((state(back)["update_field"], state(back)["update_value"]), ("ready_to_collect", "0"), back)
        m = moves()
        self.assertEqual(m[("With the tailor", "Ready")], "Ready to collect")
        self.assertEqual(m[("Fitting", "Ready")], "Ready to collect")
        self.assertEqual(m[("Ready to collect", "Back to tailor")], "With the tailor")
        self.assertFalse(fields(TICKET)["ready_to_collect"].get("default"))   # a new ticket is not ready

    def test_hand_over_and_cancel_close_the_ticket_and_leave_it_to_a_system_manager(self):
        for end in ("Handed over", "Cancelled"):
            s = state(end)
            self.assertEqual((s["update_field"], s["update_value"], s["allow_edit"]), ("closed", "1", "System Manager"), end)
        m = moves()
        self.assertEqual(m[("Ready to collect", "Hand over")], "Handed over")
        self.assertEqual({k[0] for k, v in m.items() if k[1] == "Cancel"}, {"Taken", "With the tailor", "Fitting", "Ready to collect"})
        self.assertFalse([k for k in m if k[0] in ("Handed over", "Cancelled")])   # nothing leaves a closed state
        self.assertFalse([k for k, v in m.items() if v == "Handed over" and k[0] != "Ready to collect"])

    def test_the_phone_and_e_mail_are_the_customers_read_only(self):
        f = fields(TICKET)
        self.assertEqual((f["customer_phone"]["fetch_from"], f["customer_phone"].get("read_only")), ("customer.custom_phone_no", 1))
        self.assertEqual((f["customer_email"]["fetch_from"], f["customer_email"].get("read_only")), ("customer.custom_email", 1))

    def test_tickets_due_lists_open_tickets_by_ready_by(self):
        (r,) = MANIFEST["reports"]
        self.assertEqual((r["ref_doctype"], r["filters"], r["order_by"]), (TICKET, [["closed", "=", 0]], "due_date asc"))
        self.assertLessEqual(set(r["columns"]) - {"name"}, set(fields(TICKET)))
        # a Check the report filters on is never a standard filter: Desk turns the saved filter into the unticked box and
        # drops it, so the report would list closed tickets too (run 11; run 20's bench browser pass saw it)
        f = fields(TICKET)
        self.assertFalse([x[0] for x in r["filters"] if f[x[0]]["fieldtype"] == "Check" and f[x[0]].get("in_standard_filter")])

    def test_child_tables_are_never_required(self):
        tables = [f for f in DT[TICKET]["fields"] if f["fieldtype"] == "Table"]
        self.assertEqual({f["options"] for f in tables}, {GARMENT, MEASURE})
        self.assertFalse([f["fieldname"] for f in tables if f.get("reqd")])   # Desk drops an all-blank row: none is no rows
        for t in (GARMENT, MEASURE):
            self.assertEqual(DT[t].get("istable"), 1)

    def test_the_slip_and_tag_read_only_fields_that_exist(self):
        (pf,) = MANIFEST["print_formats"]
        html = pf["html"]
        for var, dt in (("doc", TICKET), ("g", GARMENT), ("m", MEASURE)):
            used = set(re.findall(rf"\b{var}\.(\w+)", html)) - {"get_formatted"}
            self.assertLessEqual(used, set(fields(dt)) | {"name"}, var)
        self.assertIn("Garment tag", html)
        self.assertIn("{% for m in doc.measurements if m.measure %}", html)   # a blank row keeps its unit's default: never printed
        self.assertEqual(html.count("{{ doc.name }}"), 2)   # on the slip and on the tag

    def test_the_customer_the_sale_and_the_order_list_their_tickets(self):
        got = {(ln["doctype"], ln["link_fieldname"]) for ln in MANIFEST["links"]}
        self.assertEqual(got, {("Customer", "customer"), ("POS Invoice", "sale"), ("Sales Order", "order")})

    def test_store_staff_work_tickets_and_only_managers_delete(self):
        self.assertEqual(rights("Sales User"), {"read", "write", "create", "report", "print"})
        self.assertIn("delete", rights("Sales Manager"))
        self.assertTrue(all(t["allowed"] == "Sales User" for t in WF["transitions"]))

    def test_the_ticket_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (TICKET, "documentation"))
        self.assertTrue(ps["value"].endswith("#tickets"))


if __name__ == "__main__":
    unittest.main()
