"""S4's laptop tests: the printed totals add up. The sale's net_total already has a whole-sale discount inside it, so a
Discount row inside the sum (Subtotal + VAT − Discount) printed lines that did not add up to the Total. The discount
prints after the Total, as "Discount included in the total", outside the sum; a Rounding row sits before the Total.
The manifest the installer reads carries the same template.

    python3 -m unittest discover -s samples/s4_receipt_pack/tests -p 'test_*.py'
"""
import base64
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent
sys.path.insert(0, str(SAMPLE.parents[1] / "tools" / "manifest"))
import validate  # noqa: E402

HTML = (SAMPLE / "receipt.html").read_text(encoding="utf-8")
MANIFEST = json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8"))


def labels(html):
    """The first cell of each row of the totals table (the one holding the Total), in print order."""
    table = next(t for t in re.findall(r"<table.*?</table>", html, re.S) if "<td>Total</td>" in t)
    return re.findall(r"<tr[^>]*><td>([^<]+)</td>", table)


class TotalsTest(unittest.TestCase):
    def test_no_discount_row_inside_the_sum(self):
        rows = labels(HTML)
        self.assertNotIn("Discount", rows[: rows.index("Total")])

    def test_the_discount_prints_after_the_total_as_included(self):
        rows = labels(HTML)
        self.assertIn("Discount included in the total", rows[rows.index("Total") + 1:])

    def test_rounding_prints_before_the_total(self):
        rows = labels(HTML)
        self.assertIn("Rounding", rows[: rows.index("Total")])

    def test_the_manifest_carries_this_template_and_passes_the_checker(self):
        logo = base64.b64encode((SAMPLE / "logo.png").read_bytes()).decode()
        self.assertEqual(MANIFEST["print_formats"][0]["html"], HTML.replace("@@LOGO@@", logo))
        self.assertEqual(validate.validate(MANIFEST), [])


if __name__ == "__main__":
    unittest.main()
