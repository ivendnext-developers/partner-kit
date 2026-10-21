"""POS train T11's declarations — stdlib only, no bench:  python3 -m unittest discover -s tools/manifest/tests -v

Train T11 (iVendNext_PWA 4c3f11b55, 2026-10-16) added two save-rule kinds (`unique_across`, with `scope_fields`;
`role_for_action`, with `action`), the document check (`doccheck`, a subscription with settings) and a capture event
(`customer_select`). The fixture carries one of each and passes; the checker copy taken before T11 refused the two save-rule
keys (`RULE_KEYS` lacked them) and the two subscriptions. Each planted fault is refused with its own reason."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

T11 = json.loads((HERE / "fixtures/t11_ok.json").read_text())


def planted(change):
    m = copy.deepcopy(T11)
    change(m)
    return validate(m)


def reasons(errs):
    return " | ".join(e["reason"] for e in errs)


class Good(unittest.TestCase):
    def test_the_t11_fixture_passes(self):
        self.assertEqual(validate(T11), [])

    def test_each_down_answer_of_a_document_check_passes(self):
        for down in ("allow_and_flag", "refuse", "ask"):
            self.assertEqual(planted(lambda m: m["extension_subscriptions"][0].update(down_answer=down)), [], down)

    def test_a_cancel_held_by_role_with_no_condition_passes(self):
        self.assertEqual(planted(lambda m: m["save_rules"][1].update(action="cancel", conditions=[])), [])


class Refused(unittest.TestCase):
    def test_scope_fields_must_be_a_list_of_names(self):
        errs = planted(lambda m: m["save_rules"][0].update(scope_fields="customer_group"))
        self.assertEqual(len(errs), 1, reasons(errs))

    def test_a_document_check_cannot_answer_for_the_till(self):
        errs = planted(lambda m: m["extension_subscriptions"][0].update(down_answer="allow"))
        self.assertIn("this extension point can only: allow_and_flag, refuse, ask", reasons(errs))

    def test_a_document_check_takes_no_store_scope(self):
        errs = planted(lambda m: m["extension_subscriptions"][0].update(scope=["Mall"]))
        self.assertIn("(scope)", reasons(errs))

    def test_an_unknown_capture_event_names_the_three(self):
        errs = planted(lambda m: m["extension_subscriptions"][1]["settings"].update(event="customer_pick"))
        self.assertIn("scan, customer_add or customer_select", reasons(errs))

    def test_a_save_rule_key_the_product_does_not_know_is_refused(self):
        errs = planted(lambda m: m["save_rules"][1].update(actions=["submit"]))
        self.assertEqual(len(errs), 1, reasons(errs))


if __name__ == "__main__":
    unittest.main()
