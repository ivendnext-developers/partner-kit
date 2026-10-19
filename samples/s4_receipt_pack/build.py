"""Build manifest.json from receipt.html and logo.png (the logo is inlined as a data address, so the receipt has
no outside fetch).   python3 build.py        # rewrites manifest.json; then validate it:
                     python3 ../../tools/manifest/validate.py manifest.json
To use your own logo: replace logo.png (a small PNG, under 20 kB) and run this again."""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, "receipt.html"), encoding="utf-8").read()
logo = base64.b64encode(open(os.path.join(HERE, "logo.png"), "rb").read()).decode()
manifest = {
    "manifest_version": 1, "app": "pp_rcp", "prefix": "PP RCP", "title": "UAE tax invoice receipt",
    "version": "0.1.2", "publisher": "Partner Programme sample",
    "description": "A till receipt laid out as a UAE tax invoice: the company's tax registration number and address, "
                   "an inline logo, one line per item with its VAT rate, the taxable value at each rate, and Arabic "
                   "beside English. It adds one field to the till sale that copies the Company's tax ID when the sale "
                   "is saved. Set it on a POS Profile by configuration (recipe).",
    "custom_fields": [{
        "dt": "POS Invoice", "fieldname": "pp_rcp_company_tax_id", "fieldtype": "Data", "label": "Company tax ID (receipt)",
        "read_only": 1, "fetch_from": "company.tax_id", "insert_after": "company_address",
        "description": "Copied from the Company's tax ID when the sale is saved; the receipt prints it. A sale saved "
                       "before this package was installed has none.",
    }],
    "print_formats": [{
        "name": "PP RCP UAE Tax Invoice", "doc_type": "POS Invoice", "print_format_type": "Jinja",
        "html": html.replace("@@LOGO@@", logo),
    }],
}
with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=1)
print("manifest.json written,", len(manifest["print_formats"][0]["html"]), "characters of template")
