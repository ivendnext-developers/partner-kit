#!/usr/bin/env python3
"""S29's canaries: each guard must go RED when it is taken out. For each mutation this copies the sample (and the manifest
checker it imports) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN), applies
ONE change (the anchor must match exactly once, and a mutant .py must compile), runs the test again, and reports RED (the test
caught it) or GREEN (a dead test). The runner is S26's (`samples/s26_derived_prices/tests/canaries.py`; a defect there is a
defect here). It needs jinja2, because the template tests are skipped without it (a skipped test would read as GREEN).

    python3 samples/s29_print_pack/tests/canaries.py      # exit 0 only when every canary is RED
"""
from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B, C, V = "build.py", "catalogue.py", "../../tools/manifest/validate.py"
T = "test_s29."

CANARIES = [
    # the branch
    ("the plain layout is the default branch (without it a stranger's invoice prints blank)", B,
     '"\\n{%- else -%}\\n" + _layout("layout_plain") + "\\n{%- endif -%}\\n"', '"\\n{%- endif -%}\\n"',
     T + "Branch.test_a_stranger_gets_the_plain_layout_not_a_blank_page"),
    ("the branch tests the customer", B, 'f" doc.customer == {json.dumps', 'f" doc.customer != {json.dumps',
     T + "Branch.test_each_customer_gets_their_own_layout"),
    ("each customer has a layout of their own", B, 'out.append(_layout(key))', 'out.append(_layout("layout_a"))',
     T + "Branch.test_the_three_outputs_differ"),
    ("a format of the each-set is its own layout", B, "[(n, _layout(k)) for k, n in names.items()]",
     '[(n, _layout("layout_a")) for k, n in names.items()]', T + "Branch.test_the_each_formats_print_the_same_layouts"),
    ("customers.json: one customer for two layouts is refused", B, "if len(set(c.values())) != len(c):", "if False:",
     T + "Manifests.test_customers_json_is_checked"),
    ("customers.json: an empty or space-edged name is refused", B, "or _BAD_NAME.search(name)", "or False",
     T + "Manifests.test_customers_json_is_checked"),
    ("a name goes into the template as a quoted literal", B, "json.dumps(c[key], ensure_ascii=False)", "'\"' + c[key] + '\"'",
     T + "Branch.test_a_customer_named_with_quotes_braces_and_signs_still_matches_itself"),
    ("customers.json: a missing layout is refused", B, "if set(c) != set(LAYOUTS):", "if False:",
     T + "Manifests.test_customers_json_is_checked"),
    # the template reads only the invoice
    ("a row reader in a template is caught", "layouts/layout_c.html", '{{ item.customer_item_code or "-" }}',
     '{{ fr' 'appe.get_all("Item") }}', T + "Templates.test_a_template_reads_only_the_invoice_it_is_given"),
    ("a figure worked out in a template is caught", "layouts/layout_plain.html", '{{ doc.get_formatted("grand_total") }}',
     "{{ doc.grand_total * 1 }}", T + "Templates.test_every_amount_is_the_documents_own_formatted_value"),
    ("an outside logo is caught", "layouts/layout_a.html", "data:image/png;base64,@@LOGO@@", "https://example.com/logo.png",
     T + "Templates.test_a_logo_is_embedded_never_an_outside_address"),
    ("two layouts with one column set are caught", "layouts/layout_plain.html",
     "<th style=\"text-align:left;\">Description</th><th>Quantity</th><th>Price</th><th>Total</th>",
     "<th style=\"text-align:left;\">Item</th><th>Qty</th><th>Rate</th><th>Amount</th>",
     T + "Templates.test_each_layout_has_a_header_a_column_set_and_a_footer_of_its_own"),
    # the manifest checker still refuses what it must
    ("the checker refuses a script", V, "if isinstance(text, str) and _SCRIPT_RE.search(text):", "if False:",
     T + "Manifests.test_the_checker_refuses_a_script_a_frame_and_an_outside_address"),
    ("the checker refuses a frame", V, "(script|iframe|object|embed)", "(script|object|embed)",
     T + "Manifests.test_the_checker_refuses_a_script_a_frame_and_an_outside_address"),
    ("the checker refuses an outside address", V, "if isinstance(p.get(k), str) and _OUTSIDE_URL_RE.search(p[k]):", "if False:",
     T + "Manifests.test_the_checker_refuses_a_script_a_frame_and_an_outside_address"),
    # the price list
    ("a picture kept outside the shop is not fetched", C, 'if not path.startswith("/") or path.startswith("//"):', "if False:",
     T + "Catalogue.test_a_picture_kept_outside_the_shop_is_never_fetched_or_printed"),
    ("an item with no picture is reported", C, 'missing.append({"item": p["item_code"], "why": why})', "pass",
     T + "Catalogue.test_an_item_with_no_picture_gets_a_placeholder_and_is_reported"),
    ("an item with no picture is a placeholder, not a hole", C, 'else "No photo"', 'else ""',
     T + "Catalogue.test_an_item_with_no_picture_gets_a_placeholder_and_is_reported"),
    ("a picture that is not a picture is not embedded", C, "    if kind is None:\n        return None, \"the picture is not", "    if False:\n        return None, \"the picture is not",
     T + "Catalogue.test_a_picture_that_is_not_a_picture_or_too_big_is_a_placeholder"),
    ("a picture over the limit is not embedded", C, "return None if len(data) > limit else data", "return data",
     T + "ShopReads.test_paging_auth_and_text_order"),
    ("a price for one customer is skipped", C, 'if r.get("customer") or r.get("supplier") or r.get("batch_no"):', "if False:",
     T + "Catalogue.test_only_general_prices_valid_today_and_the_later_start_wins"),
    ("a price not valid today is skipped", C, 'if (_day(r.get("valid_from")) or "") > today or (_day(r.get("valid_upto")) or "9999") < today:',
     "if False:", T + "Catalogue.test_only_general_prices_valid_today_and_the_later_start_wins"),
    ("the later start date wins", C, 'if k not in best or (_day(r.get("valid_from")) or "") > (_day(best[k].get("valid_from")) or ""):',
     "if k not in best:", T + "Catalogue.test_only_general_prices_valid_today_and_the_later_start_wins"),
    ("a name is escaped", C, "    e = html.escape\n", "    e = str\n", T + "Catalogue.test_a_name_is_escaped"),
    ("a cell that starts like a formula is quoted", C, 'if v[:1] in ("=", "+", "-", "@", "\\t", "\\r")', "if False",
     T + "Catalogue.test_the_csv_has_every_item_and_does_not_run_as_a_formula"),
    ("a spreadsheet rate has no thousands comma", C, '_cell(r["currency"]), r["plain"],', '_cell(r["currency"]), r["rate"],',
     T + "Catalogue.test_the_csv_has_every_item_and_does_not_run_as_a_formula"),
    ("one section for each item group", C, 'if r["group"] != group:', "if group is None:",
     T + "Catalogue.test_one_section_per_item_group"),
    ("the picture is embedded as data", C, 'f"data:{kind};base64,', 'f"x:{kind};base64,',
     T + "Catalogue.test_every_item_of_the_list_is_there_once_with_one_picture"),
    ("a long list is read to the end", C, "if len(got) < PAGE:", "if True:", T + "ShopReads.test_paging_auth_and_text_order"),
    ("the key is sent", C, 'f"token {key}:{secret}"', '""', T + "ShopReads.test_paging_auth_and_text_order"),
    ("order_by goes as text", C, '"order_by": "name asc"', '"order_by": json.dumps("name asc")',
     T + "ShopReads.test_paging_auth_and_text_order"),
    ("a photo the shop will not give does not stop the run", C, "    except Unreadable as e:\n        return None,", "    except ZeroDivisionError as e:\n        return None,",
     T + "Catalogue.test_a_photo_the_shop_will_not_give_is_a_placeholder_and_the_run_goes_on"),
    ("a disabled item is left out", C, 'if it.get("disabled"):', "if False:", T + "Catalogue.test_a_disabled_item_is_left_out_and_listed"),
    ("float noise is dropped from a rate", C, "quantize(Decimal(1).scaleb(-9))", "quantize(Decimal(1).scaleb(-30))",
     T + "Catalogue.test_a_rate_prints_with_the_decimals_it_is_stored_with_and_no_float_noise"),
    ("a redirect to another host is refused", C, "        if new.netloc != old.netloc or new.scheme != old.scheme:", "        if False:",
     T + "Redirects.test_a_redirect_to_another_host_is_refused_and_gets_no_key"),
    ("a redirect inside the shop is followed", C, "return super().redirect_request(req, fp, code, msg, headers, newurl)", "return None",
     T + "Redirects.test_a_redirect_to_another_host_is_refused_and_gets_no_key"),
    ("the plain layout carries the tax lines", "layouts/layout_plain.html", '{{ t.description }}</td><td style="text-align:right;">{{ t.get_formatted("tax_amount") }}',
     '</td><td style="text-align:right;">', T + "Branch.test_every_layout_prints_the_tax_so_the_lines_add_up_to_the_total"),
    ("layout B carries the tax lines", "layouts/layout_b.html", '{{ t.description }}</td><td style="text-align:right;">{{ t.get_formatted("tax_amount") }}',
     '</td><td style="text-align:right;">', T + "Branch.test_every_layout_prints_the_tax_so_the_lines_add_up_to_the_total"),
    ("the plain layout carries the company's tax number", "layouts/layout_plain.html", '{%- if doc.company_tax_id %}<div>Tax no. {{ doc.company_tax_id }}</div>{% endif %}',
     "", T + "Branch.test_every_layout_prints_the_tax_so_the_lines_add_up_to_the_total"),
    ("a price whose item cannot be read is left out", C, 'if it is None:', "if False:",
     T + "Catalogue.test_a_price_whose_item_the_key_cannot_read_is_left_out_and_said"),
    ("a redirect that changes scheme is refused", C, " or new.scheme != old.scheme:", ":",
     T + "Redirects.test_a_scheme_change_is_refused_and_a_plain_http_shop_is_not_accepted"),
    ("a plain http shop is refused", C, 'if not self.base.startswith("https://") and', "if False and",
     T + "Redirects.test_a_scheme_change_is_refused_and_a_plain_http_shop_is_not_accepted"),
    ("an empty list says so", C, '"<p>No prices on this list.</p></body></html>\\n"', '"</body></html>\\n"',
     T + "Catalogue.test_an_empty_list_says_so"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s29-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(kit, "tools", "manifest"), os.path.join(tmp, "r", "tools", "manifest"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        cmd = [sys.executable, "-m", "unittest", test]
        base = subprocess.run(cmd, cwd=os.path.join(dest, "tests"), capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.normpath(os.path.join(dest, path))
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(src.replace(anchor, mutant))
        if f.endswith(".py"):
            py_compile.compile(f, doraise=True)
        p = subprocess.run(cmd, cwd=os.path.join(dest, "tests"), capture_output=True, text=True, timeout=120)
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
