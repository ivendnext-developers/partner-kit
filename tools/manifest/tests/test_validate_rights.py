"""Permission rows must state all nine rights. Stdlib only:  python3 -m unittest discover -s tools/manifest/tests -v

The framework stores a right a row leaves out as ON (measured on the bench: a row of `read` only came back with all nine ON), so the
checker refuses a row that does not write every right as 0 or 1."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

FULL = json.loads((HERE / "fixtures/full_ok.json").read_text())
NINE = ("read", "write", "create", "delete", "report", "export", "share", "print", "email")


def with_row(row):
    m = copy.deepcopy(FULL)
    m["doctypes"][1].setdefault("permissions", []).append(row)
    return validate(m)


class PermissionRights(unittest.TestCase):
    def test_a_row_of_read_and_write_only_is_refused_and_names_what_it_leaves_out(self):
        r = with_row({"role": "Retail Manager", "read": 1, "write": 1})
        self.assertEqual(len(r), 1, r)
        self.assertIn("leaves out", r[0]["reason"])
        for right in ("create", "delete", "report", "export", "share", "print", "email"):
            self.assertIn(right, r[0]["reason"])

    def test_a_row_with_all_nine_written_passes(self):
        self.assertEqual(with_row({"role": "Retail Manager", **{x: 0 for x in NINE}, "read": 1}), [])

    def test_a_right_that_is_not_0_or_1_is_refused(self):
        r = with_row({"role": "Retail Manager", **{x: 0 for x in NINE}, "export": "yes"})
        self.assertEqual(len(r), 1, r)
        self.assertIn("0 or 1", r[0]["reason"])

    def test_the_visitor_row_still_gets_its_one_visitor_refusal(self):
        r = with_row({"role": "Guest", "read": 1})
        self.assertEqual(len(r), 1, r)
        self.assertIn("not signed in", r[0]["reason"])


if __name__ == "__main__":
    unittest.main()
