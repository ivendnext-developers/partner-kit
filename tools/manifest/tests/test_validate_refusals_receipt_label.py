"""Three refusals of the manifest checker that had no test of their own — stdlib only, no bench:
python3 -m unittest discover -s tools/manifest/tests -v

Each test plants one mistake into a fixture that passes and asserts that the checker refuses it with that refusal's own
words and nothing else. A refusal whose test is missing is one a later change can drop without any test noticing."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import FIELD_RECEIPT_ONLY_SHOW, LABEL_TEMPLATE_MAX, MARK_TEXT_TYPES, validate  # noqa: E402

WAVEB = json.loads((HERE / "fixtures/waveb_v2_ok.json").read_text())
WAVED = json.loads((HERE / "fixtures/waved_v2_ok.json").read_text())
FISCAL = json.loads((HERE / "fixtures/fiscal_v2_ok.json").read_text())


def planted(base, change):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


class Refusals(unittest.TestCase):
    def test_a_receipt_rule_may_only_show_an_item_field(self):
        # field rules on the receipt preview: hiding (or relabelling) a field the receipt prints is refused
        def hide_on_the_receipt(m):
            m["field_rules"].append(
                {"theme": "PP Partner Till", "surface": "receipt_preview", "field": "item_name", "action": "hide"}
            )

        refusals = planted(WAVEB, hide_on_the_receipt)
        self.assertEqual(len(refusals), 1, refusals)
        self.assertEqual(refusals[0]["reason"], FIELD_RECEIPT_ONLY_SHOW)
        self.assertIn("can only show an item field", refusals[0]["reason"])

    def test_a_qr_field_that_is_not_a_text_field_is_refused(self):
        # the receipt prints the QR and the seal from text: a Check field cannot carry them
        def qr_on_a_check(m):
            m["custom_fields"].append(
                dict(m["custom_fields"][0], fieldname="pp_fbr_qr", label="FBR QR", fieldtype="Check")
            )
            m["fiscal_readers"][0]["qr_field"] = "pp_fbr_qr"

        refusals = planted(FISCAL, qr_on_a_check)
        self.assertEqual(len(refusals), 1, refusals)
        reason = refusals[0]["reason"]
        self.assertIn("qr_field 'pp_fbr_qr' is a field of type Check", reason)
        self.assertIn("the receipt prints the QR and the seal from text", reason)
        for t in MARK_TEXT_TYPES:
            self.assertIn(t, reason)

    def test_a_label_template_over_the_limit_is_refused(self):
        def too_long(m):
            m["label_layouts"][0]["template"] = "{price}" + "x" * LABEL_TEMPLATE_MAX

        refusals = planted(WAVED, too_long)
        self.assertEqual(len(refusals), 1, refusals)
        self.assertEqual(refusals[0]["reason"], f"A label template holds at most {LABEL_TEMPLATE_MAX} characters.")

    def test_a_label_template_at_the_limit_passes(self):
        def at_the_limit(m):
            m["label_layouts"][0]["template"] = "{price}" + "x" * (LABEL_TEMPLATE_MAX - len("{price}"))

        self.assertEqual(planted(WAVED, at_the_limit), [])


if __name__ == "__main__":
    unittest.main()
