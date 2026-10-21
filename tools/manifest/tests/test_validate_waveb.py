"""The Wave B kinds (row WAVEB) — stdlib only, no bench:  python3 -m unittest discover -s tools/manifest/tests -v

Wave B (train T2, PWA#954, 2026-10-08) put four extension points on the product: check before payment (P-CHECK),
capture on scan or customer add (P-CAPTURE), the scan source (P-SCAN) and field rules (P-FIELDS). A manifest declares
the first two as ``extension_subscriptions``, the third as ``scan_sources`` and the fourth as ``field_rules``. The
fixture passes; each forbidden element, planted into it, is refused with its own reason and nothing else. Where the
product has a limit, the kit refuses with the product's own sentence (``partner_check.py``, ``partner_capture.py``,
``pos_fields.py`` at iVendNext_PWA 577a8d41)."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

WAVEB = json.loads((HERE / "fixtures/waveb_v2_ok.json").read_text())


def planted(change, base=WAVEB):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


def at(kind, i=0, **k):
    return lambda m: m[kind][i].update(k)


def sub(i=0, **k):
    return at("extension_subscriptions", i, **k)


def more_checks(n, seconds=3):
    def change(m):
        for j in range(n):
            m["extension_subscriptions"].append(dict(m["extension_subscriptions"][0], key=f"guard{j}",
                                                     timeout_seconds=seconds))
    return change


class Good(unittest.TestCase):
    def test_the_waveb_fixture_passes(self):
        self.assertEqual(validate(WAVEB), [])

    def test_three_checks_within_ten_seconds_pass(self):
        self.assertEqual(planted(more_checks(2, seconds=3)), [])

    def test_a_check_that_may_ask_the_cashier_passes(self):
        self.assertEqual(planted(sub(down_answer="ask")), [])

    def test_a_scan_capture_on_an_item_field_passes(self):
        self.assertEqual(planted(sub(1, settings={"event": "scan", "item_field": "brand"})), [])

    def test_a_scan_source_on_a_shop_table_passes(self):
        self.assertEqual(planted(at("scan_sources", record_type="Serial No", barcode_field="name",
                                    item_from="item_code", status_field="status", available_values=["Active"])), [])

    def test_a_field_rule_showing_an_item_field_passes(self):
        self.assertEqual(planted(lambda m: m["field_rules"].append(
            {"theme": "PP Partner Till", "surface": "item_result", "field": "item_name", "action": "show"})), [])

    def test_the_new_kinds_need_version_2(self):
        m = dict(copy.deepcopy(WAVEB), manifest_version=1)
        reasons = {r["where"]: r["reason"] for r in validate(m)}
        for k in ("extension_subscriptions", "scan_sources", "field_rules"):
            self.assertIn("needs manifest_version 2", reasons.get(k, ""), k)


FORBIDDEN = [
    # P-CHECK — the product's own limits (partner_check.PER_SCOPE_MAX, SCOPE_SECONDS_MAX), in its own words
    ("four checks", more_checks(3, seconds=1), "At most 3 checks may answer one POS Profile."),
    ("three checks slower than ten seconds together", more_checks(2, seconds=4),
     "The checks of one POS Profile may take at most 10 seconds together."),
    ("a check a manager may approve past", sub(may_approve=1), "a manager may approve"),
    ("a check whose down answer the product does not offer", sub(down_answer="allow"), "allow_and_flag, refuse, ask"),
    ("a check slower than its extension point allows", sub(timeout_seconds=11), "at most 10"),
    ("a check with settings", sub(settings={"event": "scan"}), "a check takes no settings"),
    # P-CAPTURE — partner_capture.validate_subscription's sentences
    ("a capture naming no event", sub(1, settings={"item_groups": ["All Item Groups"]}),
     "Name the event in the settings: scan, customer_add, customer_select or qty_change."),
    ("a capture with no settings", lambda m: m["extension_subscriptions"][1].pop("settings"),
     "Name the event in the settings: scan, customer_add, customer_select or qty_change."),
    ("a customer capture with a filter", sub(2, settings={"event": "customer_add", "item_groups": ["x"]}),
     "The settings of a customer_add capture may only carry: event."),
    ("a scan capture with an unknown setting", sub(1, settings={"event": "scan", "item_groups": ["x"], "price": 1}),
     "The settings of a scan capture may only carry: event, item_field, item_groups."),
    ("a scan capture asking about every item", sub(1, settings={"event": "scan"}),
     "Say which items a scan capture asks about: item groups, an item field, or both."),
    ("a scan capture's groups that are not names", sub(1, settings={"event": "scan", "item_groups": "All"}),
     "item_groups must be a list of item group names."),
    ("a scan capture naming 51 groups", sub(1, settings={"event": "scan", "item_groups": [f"g{j}" for j in range(51)]}),
     "A scan capture names at most 50 item groups."),
    ("a scan capture's field that is not a name", sub(1, settings={"event": "scan", "item_field": ["brand"]}),
     "item_field must be the name of one field on Item."),
    ("two captures on scan", lambda m: m["extension_subscriptions"][2].update(settings={"event": "scan",
                                                                                     "item_field": "brand"}),
     "One service answers each."),
    ("a scan capture slower than its event allows", sub(1, timeout_seconds=4), "at most 3"),
    ("a capture asking the cashier when down", sub(1, down_answer="ask"), "allow_and_flag, refuse"),
    ("a capture a manager may approve past", sub(1, may_approve=1), "a manager may approve"),
    # P-SCAN — the declaration records the scan resolver reads
    ("a scan source switched on", at("scan_sources", enabled=1), "switches it on"),
    ("a scan source named without the prefix", at("scan_sources", source_name="Units"), "must start with its prefix"),
    ("a scan source without its table", lambda m: m["scan_sources"][0].pop("record_type"), "names the table"),
    ("a scan source without its code field", lambda m: m["scan_sources"][0].pop("barcode_field"), "names the table"),
    ("a scan source without its item field", lambda m: m["scan_sources"][0].pop("item_from"), "names the table"),
    ("a scan source whose code field is not unique", lambda m: m["doctypes"][0]["fields"][0].pop("unique"),
     "Set unit_code unique on PP WVB Unit first, so one code names one unit."),
    ("a scan source on a field its own table lacks", at("scan_sources", status_field="state"),
     "PP WVB Unit has no field state."),
    ("a scan source whose item field links elsewhere", lambda m: m["doctypes"][0]["fields"][1].update(options="Customer"),
     "item must link to Item."),
    ("a scan source with no sellable status", at("scan_sources", available_values=[]),
     "Name at least one status a unit can be sold in."),
    ("a scan source recording the code with no status field",
     lambda m: (m["scan_sources"][0].pop("status_field"), m["scan_sources"][0].pop("available_values"),
                m["scan_sources"][0].update(capture_as="Unit code")),
     "Recording the code needs a status field, so a returned unit can be sold again."),
    ("a key a scan source may not carry", at("scan_sources", script="x"), "keys this kind may not carry"),
    # P-FIELDS — pos_fields.validate_field_rules' sentences, and the allow-lists of each screen
    ("a field rule on a screen field rules do not reach", at("field_rules", surface="tender"),
     "tender is not a till screen field rules apply to."),
    ("a field rule with no action the product knows", at("field_rules", action="move"), "move is not a field action."),
    ("a field rule naming no field", at("field_rules", field=""), "Name the field each rule applies to."),
    ("a relabel with no label", lambda m: m["field_rules"][0].pop("label"), "Give item_name its new label."),
    ("a label longer than forty", at("field_rules", label="x" * 41), "A label is at most 40 characters."),
    ("two rules on one field", lambda m: m["field_rules"].append(dict(m["field_rules"][1], action="relabel",
                                                                       label="Stars")),
     "points on customer_card has two different rules. Keep one."),
    ("one rule twice", lambda m: m["field_rules"].append(dict(m["field_rules"][1])),
     "points on customer_card has the same rule twice."),
    ("hiding a field the sale needs", at("field_rules", action="hide"), "item_name can't be hidden: the sale needs it."),
    ("a rule a field cannot take", at("field_rules", 2, surface="cart_line", field="qty", action="require"),
     "qty on cart_line can't take this rule."),
    ("a price on a screen", at("field_rules", 1, surface="cart_line", field="rate"), "rate on cart_line can't take this rule."),
    ("showing more on a screen with no record type", at("field_rules", 2, action="show"),
     "Nothing more can be shown on customer_create."),
    ("showing four more Item fields", lambda m: m["field_rules"].extend(
        {"theme": "PP Partner Till", "surface": "item_result", "field": f, "action": "show"}
        for f in ("item_name", "brand", "stock_uom", "item_group")),
     "Up to 3 more Item fields can be shown. This theme shows 4."),
    ("a field rule naming no theme", lambda m: m["field_rules"][0].pop("theme"), "names its till theme"),
    ("a field rule with a label carrying script", at("field_rules", label="<img src=x onerror=1>"), "carrying script"),
    ("a key a field rule may not carry", at("field_rules", formula="x"), "keys this kind may not carry"),
    # what stays refused, and why
    ("a receipt block", lambda m: m.update(receipt_blocks=[{}]), "Receipt Header and Footer"),
    ("a module", lambda m: m.update(extension_modules=[{"point": "check"}]), "cannot install a sandboxed module"),
]


class Refused(unittest.TestCase):
    def test_each_forbidden_element_is_refused_with_its_reason(self):
        for label, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], label)


if __name__ == "__main__":
    unittest.main()
