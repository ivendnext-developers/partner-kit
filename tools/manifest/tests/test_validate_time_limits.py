"""The checker's time limits against the numbers the product publishes — stdlib only, no bench:
python3 -m unittest discover -s tools/manifest/tests -v

``validate.py`` is a copy of the shop's checker and carries each extension point's longest time to answer
(``SUB_POINTS``) and the capture events' (``CAPTURE_EVENTS``). The product publishes the same numbers in the contract
pages this repository copies (``contracts/pages``). This test holds the two together: a re-copy that changes a number on
either side, or a page that says another number than the table, fails here until the expected figures below are
re-read from the pages and updated. It reads the pages, not the product's code, so a number the pages leave unsaid is
not held. A time over the longest is refused in the product's sentence by ``test_validate_waveb.py`` (a check
at 11 seconds, a scan capture at 4)."""

import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import validate  # noqa: E402

PAGES = HERE.parents[2] / "contracts" / "pages"

# The longest time to answer, in seconds, as each page says it (the figures are read from the pages' own sentences below).
LONGEST = {"desk_action": 10, "page": 10, "check": 10, "capture": 10, "doccheck": 10, "fulfil": 10}
CAPTURE = {"scan": 3, "customer_add": 10, "customer_select": 10, "qty_change": 3}


def page(name):
    return re.sub(r"\s+", " ", (PAGES / f"{name}.md").read_text(encoding="utf-8"))


class TimeLimits(unittest.TestCase):
    def test_the_checker_table_is_the_figures_above(self):
        self.assertEqual(validate.SUB_POINTS, LONGEST)
        self.assertEqual({e: top for e, (_known, top) in validate.CAPTURE_EVENTS.items()}, CAPTURE)

    def test_each_page_says_the_same_figure(self):
        self.assertIn("3 seconds unless raised, 10 at most", page("partner_check"))
        self.assertIn("3 seconds to answer unless the subscription allows more, 10 at most", page("desk_action"))
        self.assertIn("at most 10 seconds", page("partner_page"))
        capture = page("partner_capture")
        self.assertIn("On scan (1.5 seconds unless raised, 3 at most)", capture)
        self.assertIn("On customer add (3 seconds unless raised, 10 at most)", capture)
        self.assertIn("On customer select (3 seconds unless raised, 10 at most)", capture)
        self.assertIn("On a quantity change (1.5 seconds unless raised, 3 at most)", capture)
        self.assertIn("the time to answer (3 seconds unless raised, at most 10)", page("doccheck"))
        self.assertIn("a time to answer (5 seconds unless raised, at most 10)", page("partner_fulfil"))


if __name__ == "__main__":
    unittest.main()
