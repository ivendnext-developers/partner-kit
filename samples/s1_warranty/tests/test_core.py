"""Core tests for S1 — run with:  python3 -m unittest discover -s samples/s1_warranty/tests -v
Stdlib only, no framework, no bench. The contexts in contexts/ were RECORDED from the bench's own
build_context (tests/record_contexts.py); each test also checks the answer against the till's closed
vocabulary, so the same answer can be bound at the till unchanged."""

import json
import pathlib
import sys
import unittest
from datetime import date

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import core  # noqa: E402

TERMS = {   # the service's terms.json, plus the item groups the bench reported for these codes (the setup record)
    "items": {"PP-WRC-PHONE": 24},
    "groups": {"iPhone": 12, "iPad": 12, "Mac": 12, "Watch": 12, "Audio": 12},
    "item_group": {"PP-WRC-PHONE": "iPhone", "AIRPODS-3": "Audio", "CABLE-USBC-1M": "Accessories",
                   "CASE-LEATHER": "Accessories"},
}

def ctx(name):
    return json.loads((HERE / "contexts" / f"{name}.json").read_text())


def valid_for_till(result):
    """The closed vocabulary as validate_result enforces it (app_button.py @ 05bb4dab:352-399), message kind."""
    assert set(result) == {"message"}, result
    m = result["message"]
    assert set(m) == {"title", "body", "level"}, m
    assert m["title"].strip() and len(m["title"].strip()) <= core.TITLE_MAX
    assert m["body"].strip() and len(m["body"].strip()) <= core.BODY_MAX
    assert m["level"] in core.LEVELS
    return m


class WarrantyAnswer(unittest.TestCase):
    def test_covered(self):
        m = valid_for_till(core.warranty_answer(ctx("covered"), TERMS))
        self.assertEqual(m["level"], "success")
        self.assertIn("months", m["body"])

    def test_not_covered(self):
        m = valid_for_till(core.warranty_answer(ctx("not_covered"), TERMS))
        self.assertEqual(m["level"], "info")
        self.assertIn("not covered", m["body"])

    def test_unknown_item(self):
        m = valid_for_till(core.warranty_answer(ctx("unknown"), TERMS))
        self.assertEqual(m["level"], "warning")
        self.assertIn("unknown item", m["body"])

    def test_own_term_beats_group(self):
        self.assertEqual(core.term_for("PP-WRC-PHONE", TERMS), (core.COVERED, 24))

    def test_empty_sale(self):
        valid_for_till(core.warranty_answer({"lines": []}, TERMS))

    def test_many_lines_stay_within_the_body_cap(self):
        lines = [{"item_code": f"ITEM-{i:03d}-WITH-A-LONG-CODE", "qty": 1, "uom": "Nos", "luid": str(i)} for i in range(60)]
        m = valid_for_till(core.warranty_answer({"lines": lines}, TERMS))
        self.assertIn("more", m["body"])

    def test_duplicate_lines_are_named_once(self):
        c = ctx("covered")
        c["lines"] = c["lines"] * 3
        body = core.warranty_answer(c, TERMS)["message"]["body"]
        self.assertEqual(body.count(c["lines"][0]["item_code"]), 1)


class Registrations(unittest.TestCase):
    def test_one_per_covered_serial(self):
        regs, skipped = core.registrations(
            [{"item_code": "PP-WRC-PHONE", "serials": ["S1", "S2"]}, {"item_code": "CABLE-USBC-1M", "serials": []},
             {"item_code": "NOPE", "serials": ["X"]}], TERMS, date(2026, 1, 31))
        self.assertEqual([r["serial_no"] for r in regs], ["S1", "S2"])
        self.assertEqual(regs[0]["expires"], "2028-01-31")
        self.assertEqual({s["item_code"]: s["reason"] for s in skipped},
                         {"CABLE-USBC-1M": "not covered", "NOPE": "unknown item"})

    def test_covered_line_without_serials_is_skipped_with_a_reason(self):
        regs, skipped = core.registrations([{"item_code": "PP-WRC-PHONE", "serials": []}], TERMS, date(2026, 1, 1))
        self.assertEqual(regs, [])
        self.assertEqual(skipped[0]["reason"], "no serial numbers on the line")

    def test_month_end_clamps(self):
        self.assertEqual(core.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(core.add_months(date(2027, 12, 15), 12), date(2028, 12, 15))

    def test_comment_names_every_serial_and_every_skip(self):
        text = core.comment_text("ACC-SINV-1", [{"serial_no": "S1", "item_code": "A", "months": 12, "expires": "2027-01-01"}],
                                 [{"item_code": "B", "reason": "not covered"}])
        self.assertIn("S1", text)
        self.assertIn("B: not registered — not covered", text)


class NoFramework(unittest.TestCase):
    def test_core_imports_no_framework(self):
        src = (HERE.parent / "core.py").read_text()
        for name in ("frappe", "erpnext", "ivendnext", "requests"):
            self.assertNotIn(f"import {name}", src)
            self.assertNotIn(f"from {name}", src)


if __name__ == "__main__":
    unittest.main()
