# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check.py,
# at development cff85a09aa4d9391bd0de4af68964d2181a753a5; changed: the import, the fixture folder and one id in a comment. A defect here is a defect there:
# report it with the Kit defect form (feedback/README.md).
"""Validator tests: stdlib only, no bench. Every fixture passes; each kept gate, planted into a good
manifest, is refused with its own reason and nothing else; what Desk allows the shop's administrator
passes."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validate import validate, version_key, warnings  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent / "fixtures"
FIXTURES = {
    p.name: json.loads(p.read_text())
    for p in sorted(HERE.glob("*.json"))
    if isinstance(json.loads(p.read_text()), dict) and "app" in json.loads(p.read_text())
}
FULL, V2 = FIXTURES["full_ok.json"], FIXTURES["full_v2_ok.json"]
KINDS, FISCAL = FIXTURES["kinds_v2_ok.json"], FIXTURES["fiscal_v2_ok.json"]


def planted(base, change):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


def _setter(dt, prop, value, field=None):
    return lambda m: m["property_setters"].append(
        {"doc_type": dt, "field_name": field, "property": prop, "value": value}
    )


def _field(dt, **extra):
    return lambda m: m["custom_fields"].append(
        {"dt": dt, "fieldname": "pp_tst_x", "fieldtype": "Data", "label": "X", **extra}
    )


def _sub(**extra):
    return lambda m: m["extension_subscriptions"][0].update(extra)


def _reader(**extra):
    return lambda m: m["fiscal_readers"][0].update(extra)


# (label, base, change, a phrase the ONE refusal's reason contains). One row per gate on the list.
KEPT = [
    # S: the installer reads it
    ("the prefix", FULL, lambda m: m.update(prefix="pp tst"), "one to three upper-case"),
    ("the app name", FULL, lambda m: m.update(app="pp_other"), "the prefix in lower case"),
    ("the version", FULL, lambda m: m.update(version="1.0"), "major.minor.patch"),
    ("a kind not a list", FULL, lambda m: m.update(webhooks={}), "must be a list of objects"),
    ("a missing key", FULL, lambda m: m["webhooks"][0].pop("event"), "names its event"),
    ("a field not an object", FULL, lambda m: m["doctypes"][0]["fields"].append(1), "an object"),
    (
        "a Desk action's service",
        KINDS,
        lambda m: m["desk_actions"][0].update(service="nope"),
        "extension_subscriptions",
    ),
    # A: the books
    (
        "an engine flag word",
        KINDS,
        lambda m: m.update(prefix="IGNORE X", app="ignore_x"),
        "IGNORE",
    ),
    ("a field without the prefix", FULL, _field("Purchase Order", fieldname="x"), "pp_tst_"),
    ("a ledger's required field", FULL, _field("GL Entry", reqd=1), "ledger row"),
    ("a ledger's default", FULL, _setter("Stock Ledger Entry", "default", "1", "qty"), "ledger"),
    (
        "a default that posts",
        FULL,
        _setter("Purchase Invoice Item", "default", "1", "rate"),
        "posts",
    ),
    (
        "a tax row's precision",
        FULL,
        _setter("Sales Taxes and Charges", "precision", "0", "rate"),
        "till",
    ),
    (
        "a till expense's precision",
        FULL,
        _setter("Store Expense Detail", "precision", "0", "amount"),
        "till",
    ),
    (
        "a precision that posts",
        FULL,
        _setter("Stock Entry Detail", "precision", "0", "qty"),
        "posts",
    ),
    (
        "the sale's numbering",
        V2,
        lambda m: m["naming_rules"].append({"document_type": "POS Invoice", "prefix": "X-"}),
        "numbered by the shop's own series",
    ),
    (
        "the sale's numbering by setter",
        FULL,
        _setter("Sales Invoice", "autoname", "X-.###"),
        "series",
    ),
    (
        "a purchase workflow writing a standard field",
        V2,
        lambda m: m["workflows"].append(
            {
                "name": "PI Check",
                "document_type": "Purchase Invoice",
                "states": [
                    {
                        "state": "Draft",
                        "allow_edit": "Accounts User",
                        "update_field": "set_warehouse",
                    }
                ],
                "transitions": [
                    {
                        "state": "Draft",
                        "action": "Check",
                        "next_state": "Draft",
                        "allowed": "Accounts User",
                    }
                ],
            }
        ),
        "update_field is one of the app's own fields",
    ),
    (
        "a notification writing a standard field",
        FULL,
        lambda m: m["notifications"][0].update(
            document_type="Purchase Invoice",
            set_property_after_alert="additional_discount_percentage",
            property_value="10",
        ),
        "set_property_after_alert",
    ),
    (
        "a workflow writing a standard field",
        V2,
        lambda m: m["workflows"][0]["states"][0].update(update_field="set_warehouse"),
        "update_field is one of the app's own fields",
    ),
    ("a module's discount", KINDS, _sub(max_discount_percent=10), "the shop's to set"),
    (
        "a payer's clearing mode",
        KINDS,
        lambda m: m["extension_subscriptions"].append(
            dict(
                m["extension_subscriptions"][0],
                key="pay",
                point="payer",
                settings={"clearing_mode": "x"},
            )
        ),
        "clearing mode",
    ),
    ("a fiscal writer level", FISCAL, _reader(writer_level=0), "writer_level"),
    (
        "a fiscal result field",
        FISCAL,
        _reader(status_field="nope"),
        "the installer makes the result",
    ),
    (
        "a fiscal field's level",
        FISCAL,
        lambda m: m["custom_fields"][0].update(permlevel=5),
        "must sit at writer_level",
    ),
    (
        "a fiscal mark's type",
        FISCAL,
        lambda m: (
            m["custom_fields"].append(
                {"dt": "POS Invoice", "fieldname": "pp_fbr_qr", "fieldtype": "Int", "permlevel": 2}
            ),
            m["fiscal_readers"][0].update(qr_field="pp_fbr_qr"),
        ),
        "prints the QR",
    ),
    (
        "a fiscal field limited to roles",
        FISCAL,
        lambda m: m["custom_fields"][0].update(write_roles=["PP FBR Writer"]),
        "its writer role is the reader's",
    ),
    # T: the till's own sale or new customer saves
    ("a required field on a customer", FULL, _field("Customer", reqd=1), "the till"),
    ("a required field on an override", FULL, _field("Manager Override Log", reqd=1), "the till"),
    (
        "unique on a sale's line",
        FULL,
        _setter("POS Invoice Item", "unique", "1", "item_code"),
        "till",
    ),
    (
        "a workflow on the sale",
        V2,
        lambda m: m["workflows"][0].update(document_type="POS Invoice"),
        "the till's own records",
    ),
    (
        "a notification inside the sale's save",
        FULL,
        lambda m: m["notifications"][0].update(document_type="POS Invoice", event="Submit"),
        "runs inside the till's save",
    ),
    (
        "a webhook condition on a customer",
        FULL,
        lambda m: m["webhooks"][0].update(doctype="Customer"),
        "runs inside every save",
    ),
    (
        "a required sale detail",
        FULL,
        lambda m: m["sale_attributes"][0].update(required=1),
        "stop every sale",
    ),
    # B: data out where the consent does not show it
    ("an address not plain", FULL, lambda m: m["allowed_urls"].append("ftp://x"), "plain http(s)"),
    (
        "a webhook to an address not listed",
        FULL,
        lambda m: m["webhooks"][0].update(url="https://elsewhere.example/x"),
        "allowed_urls",
    ),
    (
        "a print loading an outside image",
        FULL,
        lambda m: m["print_formats"][0].update(html='<img src="https://p.example/x.png">'),
        "load anything from outside",
    ),
    (
        "a print running raw SQL",
        FULL,
        lambda m: m["print_formats"][0].update(html="{{ frappe.db.sql('select 1') }}"),
        "raw database queries",
    ),
    (
        "a print building an address",
        FULL,
        lambda m: m["print_formats"][0].update(html='<img src="/x?c={{ doc.customer }}">'),
        "built address",
    ),
    (
        "a print reading without rights",
        FULL,
        lambda m: m["print_formats"][0].update(html="{{ frappe.get_all('Customer') }}"),
        "skip the viewer's rights",
    ),
    (
        "an SMS notification",
        FULL,
        lambda m: m["notifications"][0].update(channel="SMS"),
        "outside service",
    ),
    (
        "a file named by a field",
        FULL,
        lambda m: m["notifications"][0].update(attach_files="All"),
        "private file",
    ),
    (
        "a recipient field the app gives an address",
        FULL,
        lambda m: (
            m["custom_fields"].append(
                {
                    "dt": "Item",
                    "fieldname": "pp_tst_desk",
                    "fieldtype": "Data",
                    "default": "x@p.example",
                }
            ),
            m["notifications"][0].update(
                document_type="Item",
                recipients=[{"receiver_by_document_field": "pp_tst_desk"}],
            ),
        ),
        "the consent does not show",
    ),
    (
        "a notification copied to an address",
        FULL,
        lambda m: m["notifications"][0]["recipients"].append({"cc": "me@partner.example"}),
        "never to an address",
    ),
    (
        "records open to Guest",
        FULL,
        lambda m: m["doctypes"][1]
        .setdefault("permissions", [])
        .append({"role": "Guest", "read": 1}),
        "outside the shop's staff",
    ),
    (
        "a report for All",
        V2,
        lambda m: m["reports"][0].update(roles=["All"]),
        "outside the shop's staff",
    ),
    (
        "a till key's address not listed",
        FIXTURES["sample_s2_bins.json"],
        lambda m: m["remote_keys"][0].update(endpoint_url="https://elsewhere.example/k"),
        "endpoint_url",
    ),
    # C: code in the shop's saves or a viewer's browser
    ("a server script", FULL, lambda m: m.update(server_scripts=[{}]), "server script"),
    (
        "a notification's condition with a call",
        FULL,
        lambda m: m["notifications"][0].update(
            condition="frappe.db.set_value('User', 'x', 'y', 1)"
        ),
        "Server Script's globals",
    ),
    (
        "a recipient's condition with a call",
        FULL,
        lambda m: m["notifications"][0]["recipients"][0].update(condition="doc.get('x')"),
        "Server Script's globals",
    ),
    (
        "the framework in a message",
        FULL,
        lambda m: m["notifications"][0].update(message="{{ frappe.get_all('Customer') }}"),
        "Server Script's globals",
    ),
    (
        "a webhook's own body",
        FULL,
        lambda m: m["webhooks"][0].update(json='{"a": 1}'),
        "thin body",
    ),
    ("a client script", FULL, lambda m: m.update(client_scripts=[{}]), "client script"),
    ("a web page", FULL, lambda m: m.update(web_pages=[{}]), "web page"),
    ("a web template", FULL, lambda m: m.update(web_templates=[{}]), "web template"),
    ("an HTML field", FULL, _field("Purchase Order", fieldtype="HTML"), "HTML field"),
    (
        "a display condition in JavaScript",
        FULL,
        _field("Purchase Order", depends_on="eval:alert(1)"),
        "JavaScript",
    ),
    ("script in a label", FULL, _field("Purchase Order", label="<script>"), "script runs"),
    ("script in a setter", FULL, _setter("Item", "description", "<script>x</script>"), "script"),
    (
        "a setter's display condition",
        FULL,
        _setter("Item", "depends_on", "eval:alert(1)", "item_name"),
        "JavaScript",
    ),
    (
        "a script print format",
        FULL,
        lambda m: m["print_formats"][0].update(print_format_type="JS"),
        "script print format",
    ),
    (
        "a custom block",
        FULL,
        lambda m: m["workspaces"][0]["blocks"].append({"type": "custom_block", "data": {}}),
        "custom block",
    ),
    (
        "a shortcut's stats filter",
        FULL,
        lambda m: m["workspaces"][0]["shortcuts"][0].update(stats_filter="x"),
        "stats_filter",
    ),
    (
        "a shortcut label with markup",
        FULL,
        lambda m: m["workspaces"][0]["shortcuts"][0].update(label="<b>"),
        "plain text",
    ),
    ("a workspace icon", FULL, lambda m: m["workspaces"][0].update(icon='x" y'), "icon"),
    (
        "a query report",
        V2,
        lambda m: m["reports"][0].update(report_type="Query Report"),
        "query report",
    ),
    (
        "a script report",
        V2,
        lambda m: m["reports"][0].update(report_type="Script Report"),
        "script report",
    ),
    (
        "a report's order",
        V2,
        lambda m: m["reports"][0].update(order_by="x; drop table y"),
        "order_by",
    ),
]

# what Desk lets the shop's administrator do, which the checker refused before
ALLOWED = [
    ("a record type without the prefix", FULL, lambda m: m["doctypes"][0].update(name="Line")),
    (
        "a notification on a shop type with a condition",
        FULL,
        lambda m: m["notifications"][0].update(document_type="Material Request", event="Submit"),
    ),
    ("a label on a shop's field", FULL, _setter("Item", "label", "Product", "item_name")),
    ("hidden on a sale's field", FULL, _setter("POS Invoice", "hidden", "1", "remarks")),
    ("a default that does not post", FULL, _field("Purchase Order", default="A")),
    ("the app's own field's default on a purchase", FULL, _field("Purchase Invoice", default="A")),
    ("a required field on a customer group", FULL, _field("Customer Group", reqd=1)),
    (
        "a plain notification condition",
        FULL,
        lambda m: m["notifications"][0].update(condition="doc.title == 'x' and doc.qty > 2"),
    ),
    (
        "journal numbering",
        V2,
        lambda m: m["naming_rules"].append({"document_type": "Journal Entry", "prefix": "JV-"}),
    ),
    ("a required field on a purchase", FULL, _field("Material Request", reqd=1)),
    (
        "list settings and a link on shop types",
        V2,
        lambda m: (
            m["list_settings"].append({"doctype": "Supplier", "fields": ["supplier_name"]}),
            m["links"].append(
                {"doctype": "Supplier", "link_doctype": "Item", "link_fieldname": "x"}
            ),
        ),
    ),
    (
        "a workflow that submits",
        V2,
        lambda m: m["workflows"][0]["states"][-1].update(doc_status=1),
    ),
    ("a kind the checker does not know", FULL, lambda m: m.update(receipt_blocks=[{}])),
    ("a service switched on", KINDS, _sub(enabled=1, scope=["Main"])),
]


class Fixtures(unittest.TestCase):
    def test_every_fixture_passes(self):
        for name, m in FIXTURES.items():
            with self.subTest(name):
                self.assertEqual(validate(m), [])


class Kept(unittest.TestCase):
    def test_each_gate_is_refused_with_its_own_reason_only(self):
        for label, base, change, phrase in KEPT:
            with self.subTest(label):
                out = planted(base, change)
                self.assertEqual(len(out), 1, out)
                self.assertIn(phrase, out[0]["reason"])

    def test_a_manifest_is_an_object(self):
        self.assertEqual(validate([])[0]["reason"], "a manifest is a JSON object")


class Allowed(unittest.TestCase):
    def test_what_desk_allows_passes(self):
        for label, base, change in ALLOWED:
            with self.subTest(label):
                self.assertEqual(planted(base, change), [])


class Helpers(unittest.TestCase):
    def test_versions_compare_as_numbers(self):
        self.assertLess(version_key("1.9.0"), version_key("1.10.0"))

    def test_an_unknown_kind_is_warned_never_refused(self):
        m = dict(FULL, webhook=[{}])
        self.assertEqual(validate(m), [])
        self.assertEqual([w["what"] for w in warnings(m)], ["unknown_kind"])

    def test_a_fiscal_reader_warns_what_the_shop_grants(self):
        self.assertEqual([w["what"] for w in warnings(FISCAL)], ["level_zero"])
