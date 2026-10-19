"""S4's laptop tests, the second set (0.1.2): the template reads only the sale it is given, and every figure it prints is the
sale's own, in the shop's own money text. A stand-in sale is rendered for each sale shape (standard-rated, zero-rated, a mix,
a return, a charge row, a discount with rounding) and its printed text is compared with the recorded text in `golden/`, which
is what the 0.1.1 template printed for the same stand-in sales (it was run once against stand-in readers, and the two matched
line for line). The stand-in formats money the same way on both sides and holds the address as one line, so these texts prove
the figures, the rows and their order, not the shop's own money or address text: that was checked on a sandbox (README, *0.1.2*).
To change a golden on purpose, read the difference first, then write `text(render(sale(shape)))` into `golden/<shape>.txt`.
Needs jinja2: skipped without it, and said (CI installs it and sets S4_REQUIRE_JINJA).

    python3 -m unittest discover -s samples/s4_receipt_pack/tests -p 'test_*.py'
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent
sys.path.insert(0, str(SAMPLE.parents[1] / "tools" / "manifest"))
import validate  # noqa: E402

try:
    import jinja2
    from jinja2 import meta, nodes
    from jinja2.sandbox import SandboxedEnvironment
except ImportError:  # the kit's CI installs it; a laptop without it skips the rendering tests and says so
    if os.environ.get("S4_REQUIRE_JINJA"):  # CI sets this: a skipped template test must not read as green
        raise
    jinja2 = None

NEED_JINJA = unittest.skipUnless(jinja2, "jinja2 is not installed: the rendering tests did not run")
HTML = (SAMPLE / "receipt.html").read_text(encoding="utf-8")
MANIFEST = json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8"))
GOLDEN = HERE / "golden"
ADDRESS = "1 Main Street, Dubai"
ACCT = "VAT - X"


class Row:
    """A document or a row of one, as a print template reads it: attributes, get(), update(), get_formatted(field).
    get_formatted formats a number the way the shop does (a symbol, a thousands comma, two decimals) and a text as it is."""

    symbol = "$ "

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def update(self, values):
        self.__dict__.update(values)

    def get_formatted(self, field):
        v = self.__dict__.get(field)
        if v is None:
            return ""
        if field == "qty":  # a quantity is a plain number, not money
            return f"{v:g}"
        return f"{self.symbol}{v:,.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def line(code, qty, rate, rate_pct, name=None):
    amount = round(qty * rate, 2)
    return Row(item_code=code, item_name=name or code, qty=qty, rate=rate, amount=amount, net_amount=amount, serial_no=None,
               item_tax_rate=json.dumps({ACCT: float(rate_pct)}))


def tax(amount, **kw):
    return Row(account_head=ACCT, rate=5.0, tax_amount=amount, description="VAT", custom_surcharge=0, **kw)


def sale(shape):
    """A stand-in till sale of one of the shapes. Every figure is consistent with the lines, as a booked sale's are."""
    base = dict(name="POS-0001", company="Demo Shop", currency="AED", customer_name="Walk-in", tax_id=None, is_return=0,
                custom_printed=0, posting_date="2026-10-16", posting_time="10:00:00", company_address_display=ADDRESS,
                pp_rcp_company_tax_id="TAX-1", discount_amount=0, rounded_total=0, rounding_adjustment=0, change_amount=0,
                custom_item_surcharges=[], custom_tax_before_surcharge=0, write_off_amount=0.0)
    std = [line("CASE", 2, 50.0, 5, "Phone case"), line("CABLE", 1, 20.0, 5, "Cable")]
    mixed = [line("CASE", 2, 50.0, 5, "Phone case"), line("BOOK", 1, 20.0, 0, "Book")]
    pay = lambda amount: [Row(mode_of_payment="Cash", amount=amount)]  # noqa: E731
    if shape == "standard":
        d = dict(items=std, taxes=[tax(6.0)], net_total=120.0, total_taxes_and_charges=6.0, grand_total=126.0, payments=pay(126.0))
    elif shape == "zero":
        d = dict(items=[line("BOOK", 2, 25.0, 0, "Book")], taxes=[tax(0.0)], net_total=50.0, total_taxes_and_charges=0.0,
                 grand_total=50.0, payments=pay(50.0))
    elif shape == "mix":
        d = dict(items=mixed, taxes=[tax(5.0)], net_total=120.0, total_taxes_and_charges=5.0, grand_total=125.0, payments=pay(125.0))
    elif shape == "return":
        d = dict(items=[line("CASE", -1, 50.0, 5, "Phone case")], taxes=[tax(-2.5)], net_total=-50.0,
                 total_taxes_and_charges=-2.5, grand_total=-52.5, is_return=1, payments=pay(-52.5))
    elif shape == "item_charge":  # charge money from Item Surcharge rows rides total_taxes_and_charges but is not tax
        d = dict(items=std, taxes=[tax(6.0)], net_total=120.0, total_taxes_and_charges=36.0, grand_total=156.0,
                 custom_item_surcharges=[Row()], custom_tax_before_surcharge=6.0, payments=pay(156.0))
    elif shape == "delivery_charge":  # the delivery charge is a tax row that is not tax
        d = dict(items=std, taxes=[tax(6.0), Row(account_head="Fulfilment - X", rate=0, tax_amount=10.0, custom_surcharge=1,
                                                 description="Fulfillment Charges")],
                 net_total=120.0, total_taxes_and_charges=16.0, grand_total=136.0, payments=pay(136.0))
    elif shape == "discount_rounding":
        d = dict(items=std, taxes=[tax(5.6)], net_total=112.0, total_taxes_and_charges=5.6, grand_total=117.6, rounded_total=118.0,
                 rounding_adjustment=0.4, discount_amount=8.0, payments=pay(118.0))
    else:
        raise ValueError(shape)
    base.update(d)
    return Row(**base)


SHAPES = ["standard", "zero", "mix", "return", "item_charge", "delivery_charge", "discount_rounding"]


def render(doc, html=None, **env_globals):
    env = SandboxedEnvironment(autoescape=False)
    return env.from_string((html or HTML).replace("@@LOGO@@", "LOGO")).render(doc=doc, **env_globals)


def text(h):
    """The printed text, a row to a line, a cell to a ' | ': the same reduction the site checks use."""
    h = re.sub(r"<img[^>]*>", "[logo]", h)
    h = re.sub(r"</tr>|<br\s*/?>|</div>", "\n", h)
    h = re.sub(r"</td>", " | ", h)
    h = re.sub(r"<[^>]+>", "", h)
    return "\n".join(ln.strip() for ln in h.splitlines() if ln.strip()) + "\n"


def row_value(printed, label):
    """The cell after the first cell whose text is `label`, in the printed text."""
    for ln in printed.splitlines():
        cells = [c.strip() for c in ln.split("|")]
        if cells and cells[0] == label:
            return cells[1]
    raise AssertionError(f"no row {label!r} in:\n{printed}")


@NEED_JINJA
class Clean(unittest.TestCase):
    def test_the_template_reads_only_the_sale_it_is_given(self):
        names = meta.find_undeclared_variables(SandboxedEnvironment().parse(HTML))
        # `_` is the throwaway a `{% set _ = list.append(x) %}` assigns to (the engine reports it inside a loop); it is never
        # called: a call to `_` would be the engine's translation function, a name outside the sale
        tree = SandboxedEnvironment().parse(HTML)
        self.assertEqual([c for c in tree.find_all(nodes.Call) if isinstance(c.node, nodes.Name) and c.node.name == "_"], [])
        self.assertEqual(sorted(names - {"doc", "receipt_tax_detail", "_"}), [], "a name outside the sale and the product's own helper")
        # the words the kit may not hold are held split in two, so no file of the kit holds either
        low = HTML.lower()
        self.assertNotIn("fr" + "appe", low)
        self.assertNotIn("erp" + "next", low)

    def test_each_sale_shape_prints_what_the_old_template_printed(self):
        for shape in SHAPES:
            with self.subTest(shape=shape):
                self.assertEqual(text(render(sale(shape))), (GOLDEN / f"{shape}.txt").read_text(encoding="utf-8"))

    def test_the_product_tax_lines_print_when_its_helper_is_registered(self):
        calls = []

        def helper(doc, tax_figure):
            calls.append(tax_figure)
            return {"lines": [{"label": "VAT 5%", "amount": 6.0}, {"label": "Levy", "amount": 1234.5}]}

        printed = text(render(sale("standard"), receipt_tax_detail=helper))
        self.assertEqual(calls, [6.0])
        self.assertEqual(row_value(printed, "VAT 5%"), "$ 6.00")
        self.assertEqual(row_value(printed, "Levy"), "$ 1,234.50")  # a figure the template had to format itself

    def test_total_and_vat_equal_the_booked_figures(self):
        for shape in ("standard", "mix", "zero", "return"):
            with self.subTest(shape=shape):
                d = sale(shape)
                printed = text(render(d))
                self.assertEqual(row_value(printed, "Total"), d.get_formatted("grand_total"))
                self.assertEqual(row_value(printed, "VAT"), d.get_formatted("total_taxes_and_charges"))
                self.assertEqual(row_value(printed, "Subtotal (excl. VAT)"), d.get_formatted("net_total"))

    def test_a_worked_out_figure_uses_the_documents_own_formatter_not_a_symbol_of_its_own(self):
        class Dirham(Row):
            symbol = "AED "

        d = Dirham(**sale("mix").__dict__)
        d.items = [Dirham(**i.__dict__) for i in d.items]
        d.payments = [Dirham(**p.__dict__) for p in d.payments]
        printed = text(render(d))
        for label in ("Taxable value @ 5%", "Taxable value @ 0%", "VAT", "Total"):
            self.assertTrue(row_value(printed, label).startswith("AED "), label)

    def test_the_stand_in_field_is_put_back(self):
        d = sale("mix")
        d.write_off_amount = 7.25
        render(d)
        self.assertEqual(d.write_off_amount, 7.25)

    def test_the_tax_number_is_the_sales_own_field(self):
        d = sale("standard")
        self.assertEqual(row_value(text(render(d)), "Tax Registration No."), "TAX-1")
        d.company_trn = "UAE-TRN"  # a UAE shop's own regional field wins
        self.assertEqual(row_value(text(render(d)), "Tax Registration No."), "UAE-TRN")
        d.company_trn = None
        d.pp_rcp_company_tax_id = None  # a sale saved before the package was installed
        self.assertEqual(row_value(text(render(d)), "Tax Registration No."), "—")

    def test_the_address_is_the_sales_own_and_a_sale_with_none_prints_none(self):
        self.assertIn(ADDRESS, text(render(sale("standard"))))
        d = sale("standard")
        d.company_address_display = None
        printed = text(render(d))
        self.assertNotIn("Main Street", printed)
        self.assertEqual(printed.splitlines()[:3], ["[logo]", "Demo Shop", "Tax Registration No. | TAX-1 |"])

    def test_the_company_is_the_sales_own_company(self):
        self.assertEqual(text(render(sale("standard"))).splitlines()[1], "Demo Shop")


class Manifest(unittest.TestCase):
    def test_the_package_adds_one_field_that_copies_the_companys_tax_id(self):
        self.assertEqual(MANIFEST["version"], "0.1.2")
        (f,) = MANIFEST["custom_fields"]
        self.assertEqual((f["dt"], f["fieldname"], f["fetch_from"]), ("POS Invoice", "pp_rcp_company_tax_id", "company.tax_id"))
        self.assertEqual(validate.validate(MANIFEST), [])


if __name__ == "__main__":
    unittest.main()
