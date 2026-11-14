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
import os
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


class PlainWordsTest(unittest.TestCase):
    def test_the_english_words_cover_every_name_the_store_sees(self):   # Desk shows people's words, never the code
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        names = {d["name"] for d in m.get("doctypes", [])}
        for key in ("print_formats", "reports", "registered_applications", "sale_attributes", "workspaces",
                    "number_cards", "notifications", "dashboard_charts"):
            names |= {x["name"] for x in m.get(key, [])}
        for wf in m.get("workflows", []):
            names |= {wf["name"]} | {s["state"] for s in wf["states"]} | {t["action"] for t in wf["transitions"]}
        for d in m.get("doctypes", []):
            names |= {p["role"] for p in d.get("permissions", []) if not p["role"].endswith(" Integration")}
        (en,) = [t["words"] for t in m["translations"] if t["language"] == "en"]
        self.assertEqual(sorted(n for n in names if n.startswith(m["prefix"]) and n not in en), [])
        self.assertTrue(all(w and not w.startswith(m["prefix"]) for w in en.values()))


if __name__ == "__main__":
    unittest.main()
