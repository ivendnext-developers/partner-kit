"""Build the three manifests of S29 from the layout files, the logo and customers.json.

    python3 build.py        # writes branch_manifest.json, each_manifest.json and price_list_manifest.json, then check them:
                            # python3 ../../tools/manifest/validate.py branch_manifest.json

  branch_manifest.json   ONE sales-invoice print format whose body picks a layout by the customer on the invoice
                         (customers.json says which customer gets which layout); any other customer gets the plain layout.
  each_manifest.json     ONE print format per layout, and nobody picks by customer: the person printing or e-mailing an
                         invoice chooses the format in the print dialog.
  price_list_manifest.json ONE print format on the Price List itself (price_list/price_list.html), POS build 2.0.0.654 on:
                         its prices through ivn_rows and each item's photo through ivn_value, as the person printing may
                         read them. Its own app (pp_plr): it installs beside either invoice package.

Install ONE of them on a site, not both: they carry the same app name and prefix (their versions differ so that
switching from one to the other is an update). To use your own customers, edit
customers.json (the names must be the customers' record names exactly), your own logo (logo.png, a small PNG) and the
layout files, then run this again."""
import base64
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUTS = ("layout_a", "layout_b", "layout_c")  # in the order customers.json lists them; the plain layout is the default
_BAD_NAME = re.compile(r"^\s|\s$")  # json.dumps quotes the rest: a name with quotes or braces matches as itself


def _read(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return f.read()


def customers():
    """{layout: customer name}, checked: every layout named once, no two layouts for one customer, no name that is empty or
    starts or ends with a space (the shop would not match it). The name goes into the template through json.dumps, so a
    quote, a brace or a percent sign in it cannot break out of the string."""
    c = json.loads(_read("customers.json"))
    if set(c) != set(LAYOUTS):
        raise SystemExit(f"customers.json must name exactly these layouts: {', '.join(LAYOUTS)}")
    for k, name in c.items():
        if not isinstance(name, str) or not name or _BAD_NAME.search(name):
            raise SystemExit(f"customers.json: {k}: a customer's name, not empty and not starting or ending with a space")
    if len(set(c.values())) != len(c):
        raise SystemExit("customers.json: two layouts for one customer")
    return c


def _logo():
    with open(os.path.join(HERE, "logo.png"), "rb") as f:
        return base64.b64encode(f.read()).decode()


def _layout(key):
    return _read(f"layouts/{key}.html").replace("@@LOGO@@", _logo())


def branch_html():
    """One template: {% if doc.customer == "<A>" %} layout A {% elif … %} … {% else %} the plain layout {% endif %}."""
    c, out = customers(), []
    for i, key in enumerate(LAYOUTS):
        out.append(("{%- if" if i == 0 else "{%- elif") + f" doc.customer == {json.dumps(c[key], ensure_ascii=False)} -%}}\n")
        out.append(_layout(key))
    out.append("\n{%- else -%}\n" + _layout("layout_plain") + "\n{%- endif -%}\n")
    return "".join(out)


def _manifest(description, formats, version):
    return {
        "manifest_version": 1, "app": "pp_prt", "prefix": "PP PRT", "title": "Invoice layouts per customer",
        "version": version, "publisher": "Partner Programme sample", "description": description,
        "print_formats": [{"name": n, "doc_type": "Sales Invoice", "print_format_type": "Jinja", "html": h} for n, h in formats],
    }


def build_branch():
    return _manifest("One sales-invoice print format that picks the layout from the customer on the invoice, and prints a "
                     "plain layout for any other customer. Make it the invoice's default in Desk (a manifest cannot).",
                     [("PP PRT Branch Invoice", branch_html())], "0.1.3")


def build_each():
    names = {"layout_a": "PP PRT Invoice A", "layout_b": "PP PRT Invoice B", "layout_c": "PP PRT Invoice C",
             "layout_plain": "PP PRT Invoice Plain"}
    return _manifest("One sales-invoice print format for each layout. The person printing or e-mailing an invoice picks "
                     "the format; nothing picks it by customer.", [(n, _layout(k)) for k, n in names.items()], "0.1.4")


def build_price_list():
    return {
        "manifest_version": 1, "app": "pp_plr", "prefix": "PP PLR", "title": "A price list with photos",
        "version": "0.1.1", "publisher": "Partner Programme sample",
        "description": "One print format on the Price List: each general price of the list with the item's photo, read "
                       "through ivn_rows and ivn_value with the rights of the person printing (POS build 2.0.0.654 on). A "
                       "print sent from the e-mail queue shows no rows.",
        "print_formats": [{"name": "PP PLR Price List with Photos", "doc_type": "Price List", "print_format_type": "Jinja",
                           "html": _read("price_list/price_list.html")}],
    }


if __name__ == "__main__":
    for fname, m in (("branch_manifest.json", build_branch()), ("each_manifest.json", build_each()),
                     ("price_list_manifest.json", build_price_list())):
        with open(os.path.join(HERE, fname), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
        print(fname, "written:", ", ".join(f"{p['name']} ({len(p['html'])} characters)" for p in m["print_formats"]))
