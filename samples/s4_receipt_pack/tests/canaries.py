#!/usr/bin/env python3
"""S4's canaries: each guard must go RED when it is taken out. For each mutation this copies the sample (and the manifest
checker it imports) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN), applies
ONE change (the anchor must match exactly once), runs the test again, and reports RED (the test caught it) or GREEN (a dead
test). The runner is S29's (`samples/s29_print_pack/tests/canaries.py`, from S26's); a defect there is a defect here. It needs
jinja2, because the template tests are skipped without it (a skipped test would read as GREEN).

    python3 samples/s4_receipt_pack/tests/canaries.py      # exit 0 only when every canary is RED
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, M = "receipt.html", "manifest.json"
T = "test_clean."
OUT = T + "Clean.test_the_template_reads_only_the_sale_it_is_given"
GOLD = T + "Clean.test_each_sale_shape_prints_what_the_old_template_printed"
TOTALS = T + "Clean.test_total_and_vat_equal_the_booked_figures"
NUM = "test_totals.TotalsTest.test_the_manifest_carries_this_template_and_passes_the_checker"
# the words the kit may not hold are held split in two here too
UP = "fr" + "appe"
UP2 = "erp" + "next"

CANARIES = [
    # the template reads only the sale
    ("a record reader in the company line is caught", R, '{{ doc.company }}</div>',
     '{{ ' + UP + '.db.get_value("Company", doc.company, "company_name") }}</div>', OUT),
    ("a record-list reader in the address is caught", R, "{{ doc.company_address_display }}",
     '{{ ' + UP + '.get_all("Address") }}', OUT),
    ("an upstream name in a comment is caught", R, "{#- Money text for a figure", "{#- " + UP2 + " Money text for a figure", OUT),
    ("a money formatter of the framework is caught", R, "{{ money(tax_figure) }}",
     "{{ " + UP + ".utils.fmt_money(tax_figure) }}", OUT),
    ("a call to the engine's translation function is caught", R, "<td>Thank you</td>", "<td>{{ _('Thank you') }}</td>", OUT),
    # the tax number
    ("the tax number missing is caught", R, '{{ tax_no or "—" }}', '{{ "—" }}', T + "Clean.test_the_tax_number_is_the_sales_own_field"),
    ("a UAE shop's own tax field ignored is caught", R, 'doc.get("company_trn") or doc.get("pp_rcp_company_tax_id")',
     'doc.get("pp_rcp_company_tax_id")', T + "Clean.test_the_tax_number_is_the_sales_own_field"),
    ("the package's own field ignored is caught", R, 'doc.get("company_trn") or doc.get("pp_rcp_company_tax_id")',
     'doc.get("company_trn")', T + "Clean.test_the_tax_number_is_the_sales_own_field"),
    ("a manifest field that copies another record's number is caught", M, '"fetch_from": "company.tax_id"',
     '"fetch_from": "customer.tax_id"', T + "Manifest.test_the_package_adds_one_field_that_copies_the_companys_tax_id"),
    ("a manifest that adds no field is caught", M, '"fieldname": "pp_rcp_company_tax_id"', '"fieldname": "pp_rcp_other"',
     T + "Manifest.test_the_package_adds_one_field_that_copies_the_companys_tax_id"),
    # the address and the company
    ("the address missing is caught", R, "{{ doc.company_address_display }}", '{{ "" }}', T + "Clean.test_the_address_is_the_sales_own_and_a_sale_with_none_prints_none"),
    ("an address line printed for a sale with none is caught", R, "{%- if doc.company_address_display %}", "{%- if true %}",
     T + "Clean.test_the_address_is_the_sales_own_and_a_sale_with_none_prints_none"),
    ("another company's name is caught", R, '{{ doc.company }}</div>', '{{ doc.customer_name }}</div>',
     T + "Clean.test_the_company_is_the_sales_own_company"),
    # the money
    ("a printed total that differs from the booked one is caught", R, '{% else %}{{ doc.get_formatted("grand_total") }}{% endif %}</td>',
     '{% else %}{{ doc.get_formatted("net_total") }}{% endif %}</td>', TOTALS),
    ("a VAT figure that differs from the booked one is caught", R, "{{ money(tax_figure) }}", "{{ money(0) }}", GOLD),
    ("a taxable value that differs is caught", R, "{{ money(ns.taxable[key]) }}", "{{ money(0) }}", GOLD),
    ("a charge that differs is caught", R, "{{ money(charges) }}", "{{ money(0) }}", GOLD),
    ("a tax line of the product's helper that is not formatted is caught", R, "{{ money(t.amount) }}", "{{ t.amount }}",
     T + "Clean.test_the_product_tax_lines_print_when_its_helper_is_registered"),
    ("a symbol of the template's own is caught", R, '{{- doc.get_formatted("write_off_amount") -}}',
     '{{- "$ " ~ ("%.2f" | format(v)) -}}', T + "Clean.test_a_worked_out_figure_uses_the_documents_own_formatter_not_a_symbol_of_its_own"),
    ("a stand-in field not put back is caught", R, '  {%- set _ = doc.update({"write_off_amount": keep}) -%}\n', "",
     T + "Clean.test_the_stand_in_field_is_put_back"),
    # the template is the manifest's
    ("a template that is not the one in the manifest is caught", R, "Thank you", "Thanks", NUM),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s4-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(kit, "tools", "manifest"), os.path.join(tmp, "r", "tools", "manifest"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ, S4_REQUIRE_JINJA="1", PYTHONDONTWRITEBYTECODE="1")
        cmd = [sys.executable, "-m", "unittest", test]
        base = subprocess.run(cmd, cwd=os.path.join(dest, "tests"), capture_output=True, text=True, timeout=120, env=env)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.normpath(os.path.join(dest, path))
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(src.replace(anchor, mutant))
        p = subprocess.run(cmd, cwd=os.path.join(dest, "tests"), capture_output=True, text=True, timeout=120, env=env)
        last = (p.stderr.strip().splitlines() or [""])[-1]
        return ("RED" if p.returncode else "GREEN"), last
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        import jinja2  # noqa: F401
    except ImportError:
        sys.exit("the canaries need jinja2 (the template tests skip without it): pip install jinja2")
    bad = 0
    for c in CANARIES:
        verdict, last = run(*c)
        bad += verdict != "RED"
        print(f"{verdict:6} {c[0]} — {c[4]} — {last}")
    print(f"{len(CANARIES) - bad} of {len(CANARIES)} canaries RED")
    sys.exit(1 if bad else 0)
