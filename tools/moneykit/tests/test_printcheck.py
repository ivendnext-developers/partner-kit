"""Laptop tests of ``printcheck.expected_tax`` (PRINTCHECKTAX), with no shop: the function and its constant are read out
of printcheck.py and run with a plain ``flt``, so nothing of the shop is imported. The figure is the POS app's
``receipt_tax_figure`` at 9dc717ba1: a charge's own amount is not tax, its own tax is.

    python3 -m unittest discover -s tools/moneykit/tests -p 'test_*.py'
"""
import ast
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "printcheck.py"


def load():
    tree = ast.parse(SOURCE.read_text("utf-8"))
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "expected_tax")
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "CHARGE_TAX_ROWS" for t in n.targets))]
    ns = {"flt": lambda v, p=None: float(v or 0)}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns["expected_tax"]


def row(description, amount, charge=0):
    return {"description": description, "tax_amount": amount, "custom_surcharge": charge}


class ExpectedTax(unittest.TestCase):
    expected_tax = staticmethod(load())

    def test_a_sale_with_no_charge_prints_every_tax(self):
        self.assertEqual(self.expected_tax({"total_taxes_and_charges": 15.0, "taxes": [row("VAT 15%", 15.0)]}), 15.0)

    def test_a_charges_own_amount_comes_off_and_its_tax_stays(self):
        inv = {"total_taxes_and_charges": 15.0 + 5.0 + 0.75 + 2.0 + 0.30,
               "taxes": [row("VAT 15%", 15.0), row("Fulfillment Charges", 5.0, 1), row("Fulfillment Tax", 0.75, 1),
                         row("Gift wrap", 2.0, 1), row("Surcharge Tax", 0.30, 1)]}
        self.assertAlmostEqual(self.expected_tax(inv), 16.05)


if __name__ == "__main__":
    unittest.main()
