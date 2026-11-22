"""Does a PRINTED receipt show the figures the sale was BOOKED with? Used by the money kit (kit.py) on every basket and by
the receipt pack's (S4) tests. A format prints money; it never decides it, so each figure must sit NEXT TO ITS OWN LABEL in the printed
text — a number that appears anywhere else on the page (a payment row, a CSS width) proves nothing.

    agrees(inv, html, total_label="Total", tax_label="VAT") -> list of differences (empty = the print agrees)

The expected VAT is the figure the till screen and the seeded receipt print: every tax the sale books, a charge's own
tax included (Fulfillment Tax, Surcharge Tax); a charge's own amount rides total_taxes_and_charges and is not tax. When the format shows 'Taxable value @ N%' rows (the S4
sample does), their amounts must add up to the sale's net total.
Imports frappe.utils only; takes the invoice document and the rendered html.
The tax-figure expression is COPIED from ivendnext/iVendNext_PWA · apps/ivendnext_mpos/ivendnext_mpos/business_logic/
receipt_tax.py · receipt_tax_figure @ 9dc717ba1 (build 2.1.0.726, 2026-11-22); a defect here is a defect there — report
it on the POS app's board.
"""

import re

from frappe.utils import flt, fmt_money

ARABIC = "؀-ۿ"


def text_of(html: str, marker: str = 'class="pp-rcp"') -> str:
    """The receipt as text: tags out, the page's styles out, spaces collapsed. From `marker` on, when the format has one."""
    body = html[html.index(marker):] if marker in html else html
    body = re.sub(r"(?is)<style.*?</style>", " ", body)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


CHARGE_TAX_ROWS = ("Fulfillment Tax", "Surcharge Tax")   # a charge's own tax: it is tax (receipt_tax.CHARGE_TAX_ROWS)


def expected_tax(inv) -> float:
    """What the till prints as Tax: the taxes the sale books less each charge row's own amount (a row marked
    custom_surcharge that is not a charge's tax row), copied from receipt_tax.receipt_tax_figure @ 9dc717ba1."""
    return flt(flt(inv.get("total_taxes_and_charges"))
               - sum(flt(t.get("tax_amount")) for t in inv.get("taxes") or []
                     if t.get("custom_surcharge") and t.get("description") not in CHARGE_TAX_ROWS))


def _forms(inv, field: str, value) -> list[str]:
    return [fmt_money(value, currency=inv.currency), inv.get_formatted(field)] if field in inv.as_dict() else \
        [fmt_money(value, currency=inv.currency)]


def next_to(text: str, label: str, forms: list[str]) -> bool:
    return any(re.search(rf"(?<![A-Za-z]){re.escape(label)}\s+{re.escape(f)}", text) for f in forms)


def agrees(inv, html: str, total_label: str = "Total", tax_label: str = "VAT") -> list[str]:
    text = text_of(html)
    diffs = []
    total_field = "rounded_total" if flt(inv.rounded_total) else "grand_total"
    total = inv.get(total_field)
    if not next_to(text, total_label, _forms(inv, total_field, total)):
        diffs.append(f"printed receipt has no '{total_label}' row showing the booked {fmt_money(total, currency=inv.currency)}")
    tax = expected_tax(inv)
    if not next_to(text, tax_label, [fmt_money(tax, currency=inv.currency)] + ([inv.get_formatted("total_taxes_and_charges")]
                                                                               if abs(tax - flt(inv.total_taxes_and_charges)) < 0.005 else [])):
        diffs.append(f"printed receipt has no '{tax_label}' row showing the booked tax {fmt_money(tax, currency=inv.currency)}")
    taxable = re.findall(rf"Taxable value @ [\d.]+%\s+([^{ARABIC}]+)", text)
    if taxable:
        printed = sum(float(re.sub(r"[^0-9.\-]", "", t.replace(",", "")) or 0) for t in taxable)
        if abs(printed - flt(inv.net_total)) > 0.02 * max(len(taxable), 1):
            diffs.append(f"the taxable values add up to {printed:.2f}, the booked net total is {flt(inv.net_total):.2f}")
    return diffs
