"""The blank app: what *New app* makes when no sample is named (``combine([], prefix, into)``, ``ivn new <name>``, My apps'
*Start blank*). One maker, so the page and the command make the same folder.

The folder holds a ``manifest.json`` with the app's name, prefix and version and no entries; ``app.json``; one test that
runs the kit's checker on the manifest; and a ``README.md`` listing each kind the manifest takes, with a one-line example
under the app's own names and its recipe. It is laid out as an app made from samples is (``service/``, ``dispatch.json``,
the kit's helpers), so *Add a sample* adds into it later, and the hosting treats it as any app with no service of its own.

``app.json`` holds ``"samples": []`` and ``"blank"``: the hashes of what was written, in the samples record's form, so
*Add a sample* can tell what the developer changed. Standard library only.
"""
from __future__ import annotations

import json

SITE = "https://developer.ivendnext.com"

# (kind, what it is, the example under the app's names, or the sample that brings it, the recipe page)
# The examples are checked by the kit's own checker, together and one by one (tests/test_blank.py).
KINDS = (
    ("custom_fields", "a field on one of your customer's record types (its name starts with your app's name)",
     {"dt": "Customer", "fieldname": "{p}_loyalty_tier", "fieldtype": "Data", "label": "Loyalty tier",
      "insert_after": "customer_name"}, "recipes/manifest.html"),
    ("property_setters", "a display change on a record type or a field: relabel, hide or require it",
     {"doc_type": "Supplier", "field_name": "tax_id", "property": "reqd", "value": "1", "property_type": "Check"},
     "recipes/configure_no_code.html"),
    ("workflows", "states and transitions, with the role per transition: an approval",
     {"name": "{P} PO Approval", "document_type": "Purchase Order", "send_email_alert": 0,
      "states": [{"state": "Draft", "allow_edit": "Purchase User"}, {"state": "Approved", "allow_edit": "Purchase Manager"}],
      "transitions": [{"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Purchase Manager"}]},
     "recipes/approvals.html"),
    ("notifications", "an e-mail or in-app alert to your customer's own people when a record changes",
     {"name": "{P} New supplier", "document_type": "Supplier", "event": "New", "channel": "System Notification",
      "subject": "New supplier {{ doc.supplier_name }}", "recipients": [{"receiver_by_role": "Purchase Manager"}]},
     "recipes/stock_alerts.html"),
    ("print_formats", "a print template for your records or your customer's",
     {"name": "{P} Delivery Slip", "doc_type": "Delivery Note", "html": "<h2>{{ doc.name }}</h2><p>{{ doc.customer_name }}</p>"},
     "recipes/print_pack.html"),
    ("naming_rules", "a numbering rule: a prefix and digits",
     {"document_type": "{P} Visit", "prefix": "{W}-VIS-.YYYY.-", "prefix_digits": 5}, "recipes/manifest.html"),
    ("list_settings", "the columns of a Desk list",
     {"doctype": "Purchase Order", "fields": ["supplier", "transaction_date", "grand_total"]}, "recipes/manifest.html"),
    ("doctypes", "a record type of your own; child tables allowed",
     {"name": "{P} Visit", "fields": [{"fieldname": "customer", "fieldtype": "Link", "label": "Customer",
                                       "options": "Customer", "reqd": 1, "in_list_view": 1}],
      "permissions": [{"role": "Sales User", "read": 1, "write": 1, "create": 1}]}, "recipes/manifest.html"),
    ("workspaces", "a Desk page with headers and shortcuts",
     {"name": "{P} Visits", "blocks": [{"type": "shortcut", "data": {"shortcut_name": "Visits", "col": 4}}],
      "shortcuts": [{"type": "DocType", "link_to": "{P} Visit", "label": "Visits"}]}, "recipes/manifest.html"),
    ("reports", "a Report Builder report: columns, filters, order, roles",
     {"name": "{P} Suppliers by group", "ref_doctype": "Supplier", "columns": ["supplier_name", "supplier_group"],
      "roles": ["Purchase Manager"]}, "recipes/shop_reports.html"),
    ("number_cards", "a count, sum or average over a record type",
     {"name": "{P} Visits", "document_type": "{P} Visit"}, "recipes/shop_reports.html"),
    ("dashboard_charts", "a chart over time, or grouped",
     {"name": "{P} Visits by customer", "document_type": "{P} Visit", "chart_type": "Group By",
      "group_by_based_on": "customer", "group_by_type": "Count", "type": "Bar"}, "recipes/shop_reports.html"),
    ("dashboards", "your charts and cards on one page",
     {"name": "{P} Visits", "charts": ["{P} Visits by customer"], "cards": ["{P} Visits"]}, "recipes/shop_reports.html"),
    ("links", "your records listed under one of your customer's records (the Connections panel)",
     {"doctype": "Customer", "link_doctype": "{P} Visit", "link_fieldname": "customer", "group": "Visits"},
     "recipes/manifest.html"),
    ("save_rules", "a rule checked on every save of a record type",
     {"rule_name": "{P} supplier needs a tax id", "record_type": "Supplier", "kind": "required_when", "field": "tax_id",
      "mode": "refuse", "conditions": [{"field": "supplier_type", "operator": "=", "value": "Company"}]},
     "recipes/save_rules.html"),
    ("role_rights", "a right for one of your own roles on any record type",
     {"doctype": "Item", "role": "{P} Buyer", "rights": ["read"]}, "recipes/manifest.html"),
    ("records", "default rows the install makes if they are missing",
     {"doctype": "Customer Group", "name": "{P} Gold", "values": {"customer_group_name": "{P} Gold",
                                                                   "parent_customer_group": "All Customer Groups", "is_group": 0}},
     "recipes/manifest.html"),
    ("field_rules", "hide, relabel, require or show a field on one of your customer's till themes",
     {"theme": "{P} Till", "surface": "customer_create", "field": "email", "action": "hide"}, "recipes/field_rules.html"),
    ("sale_attributes", "an optional sale detail a till key can fill",
     {"name": "Gift wrap"}, "recipes/required_sale_details.html"),
    ("label_layouts", "the label the till prints for an item",
     {"label_name": "{P} Shelf Label", "kind": "html", "width_mm": 50, "height_mm": 30, "per_row": 1,
      "template": "<div>{item_name}</div><div>{barcode_svg}</div>"}, "contracts/pages/label_layout.html"),
    ("list_marks", "a coloured label on a row of a Desk list", "s14", "contracts/pages/list_mark.html"),
    ("translations", "your own words in a language",
     {"language": "fr", "words": {"Visits": "Visites"}}, "contracts/pages/package_install.html"),
    ("webhooks", "a signed call to your service when a record changes", "s2", "recipes/webhook_receiver.html"),
    ("registered_applications", "your service's event-feed registration", "s52", "recipes/event_feed.html"),
    ("remote_keys", "a till key that calls your service", "s52", "contracts/pages/remote_till_key.html"),
    ("extension_subscriptions", "your service for one extension point: a check, a page, a Desk button, a price",
     "s18", "recipes/rule_guard.html"),
    ("desk_actions", "a button on a Desk record, answered by your service", "s44", "recipes/desk_action.html"),
    ("app_user_rights", "the till rights your app's own user needs (an open check, a station ticket)", "s55",
     "contracts/pages/package_install.html"),
    ("scan_sources", "a table of your customer's own unit codes the till's scan reads", "s19", "recipes/unit_codes.html"),
    ("register_books", "the books of a regulated-stock register", "s41", "recipes/regulated_register.html"),
    ("fiscal_readers", "one outside fiscal service's result on the sale", None, "guide/07_manifests.html"),
    ("extension_modules", "a certified module for the check before payment or pricing", None, "guide/07_manifests.html"),
)


def fill(value, prefix: str, app: str):
    """An example under the app's own names: ``{P}`` its prefix, ``{W}`` the prefix's first word, ``{p}`` its name."""
    text = json.dumps(value, ensure_ascii=False)
    text = text.replace("{W}", prefix.split()[0]).replace("{P}", prefix).replace("{p}", app)
    return json.loads(text)


def examples(prefix: str, app: str) -> dict:
    """{kind: [the example]} for every kind whose example is a line of the manifest."""
    return {k: [fill(ex, prefix, app)] for k, _, ex, _ in KINDS if isinstance(ex, dict)}


def manifest(prefix: str, app: str) -> dict:
    return {"manifest_version": 2, "app": app, "prefix": prefix, "title": prefix.title(), "version": "1.0.0",
            "publisher": prefix.split()[0], "description": ""}


def readme(prefix: str, app: str) -> str:
    rows = []
    for kind, what, ex, page in KINDS:
        if isinstance(ex, dict):
            how = "`" + json.dumps(fill(ex, prefix, app), ensure_ascii=False) + "`"
        elif ex:
            how = f"needs a service: start from sample {ex.upper()}, `ivn add {ex}`"
        else:
            how = "needs a service and a certificate: read its chapter"
        label = "the recipe" if page.startswith("recipes/") else "the guide" if page.startswith("guide/") else "the reference"
        rows.append(f"| `{kind}` | {what} | {how} | [{label}]({SITE}/{page}) |")
    table = "\n".join(rows)
    return f"""# {prefix}

A blank app: nothing in it yet. Its names start with `{prefix}` and `{app}`. It is the folder you start from when no sample of the iVendNext partner kit matches your customer's need.

## What is in this folder

| Folder or file | What it is |
|---|---|
| `manifest.json` | what the site installs: add your entries here, one list per kind |
| `app.json` | the app's name, version, settings and card |
| `tests/test_manifest.py` | the kit's checker on your manifest: it passes now, and after each change it says what is wrong |
| `service/` | the app's one service, for when you add a sample that runs code; leave it as it is |
| `LICENSE`, `THIRD_PARTY.md` | your app's licence, and the notices of the kit's helpers in `service/_kit/` |

## Add what you need

Each kind below is one list in `manifest.json`. Copy the example into its list, change the words, then run `ivn check`. A kind that needs a service starts from a sample: `ivn add <sample>` adds it into this app and keeps what you wrote. The full rules for each kind are in [the manifest recipe]({SITE}/recipes/manifest.html).

For example, a field and a notification: in `manifest.json`, put a comma after `"description": ""`, then add these two lines before the closing brace.

```json
  "custom_fields": [{json.dumps(fill(KINDS[0][2], prefix, app), ensure_ascii=False)}],
  "notifications": [{json.dumps(fill(KINDS[3][2], prefix, app), ensure_ascii=False)}]
```

Several examples below name the record type `{prefix} Visit`: add the `doctypes` line first when you use them.

| Kind | What it is | Example | Read more |
|---|---|---|---|
{table}

## Try it

```
ivn check
ivn try
```

`ivn check` runs the kit's checker and this folder's tests. `ivn try` uploads it and installs it on your sandbox. Without a terminal, My apps does both: **Upload a new version**, then **Try**.

## What to leave alone

Names already installed at a site; the `blank` record in `app.json` (what was written, for *Add a sample*; it goes when you add one); `service/`.

## Change it with your AI assistant

Open your copy of the kit in it. It reads AGENTS.md, which knows this folder.
"""


TEST = '''"""The kit's checker on this app's manifest (``tools/manifest/validate.py`` and ``site_rules.py``, copied into
``tests/_kit/``): it passes on a blank app, and after a change it names each entry it refuses and why.

    python3 -m unittest discover -s tests          (from the app's folder)
"""
import json
import pathlib
import sys
import unittest

APP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tests" / "_kit" / "tools" / "manifest"))
from site_rules import refusals  # noqa: E402
from validate import validate  # noqa: E402


class TheManifest(unittest.TestCase):
    def test_the_kits_checker_accepts_it(self):
        manifest = json.loads((APP / "manifest.json").read_text(encoding="utf-8"))
        found = [f"{r['where']} {r.get('name') or ''}: {r['reason']}" for r in validate(manifest) + refusals(manifest)]
        self.assertEqual(found, [], "\\n".join(found))


if __name__ == "__main__":
    unittest.main()
'''


def third_party(commit: str) -> str:
    return ("# Third-party components this app ships\n\n"
            f"- `service/_kit/` and `tests/_kit/`: the iVendNext partner kit's helpers at {commit}, Copyright 2026 CitiXsys, "
            "under the Apache License, Version 2.0; `service/_kit/ed25519.py` is adapted from the reference code of RFC 8032, "
            "Copyright (c) 2017 IETF Trust and the persons identified as authors of the code, IETF Trust's BSD licence (the "
            "text is in that file's header)\n")
