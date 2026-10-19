"""selfcheck --self-test: every check fires on its own planted defect, and a clean app passes every check.

The pattern of mPOS's ``ci/check_foreign_apps.py --self-test`` (ivendnext/iVendNext_PWA @ 05bb4dab): plant a real
defect in a temporary directory (the working tree is never touched), assert the check's verdict AND that its words
name the defect, then prove the clean control stays silent. A check nobody has seen fail is a check nobody has tested.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

import lint_engine_patch
import lint_outbound
import selfcheck

CLEAN = {
    "pp_tst/hooks.py": 'app_name = "pp_tst"\napp_license = "proprietary"\nrequired_apps = ["ivendnext/frappe", "ivendnext/erpnext"]\n'
                       'doc_events = {"POS Invoice": {"on_submit": "pp_tst.events.on_submit"}}\n',
    "pp_tst/modules.txt": "PP TST\n",
    "pp_tst/events.py": "import frappe\nfrom erpnext.stock.get_item_details import get_item_details\n\n\n"
                        "def on_submit(doc, method=None):\n    try:\n        record(doc)\n    except Exception:\n"
                        "        frappe.log_error(title='pp_tst')\n\n\ndef record(doc):\n"
                        "    frappe.flags.pp_tst_seen = True\n    return doc.name\n\n\n"
                        "def on_cancel(doc, method=None):\n    frappe.throw('not on a submit path: allowed')\n\n\n"
                        "def unused():\n    frappe.throw('never called: allowed')\n",
    "pp_tst/pp_tst/doctype/pp_tst_thing/pp_tst_thing.json": json.dumps({"doctype": "DocType", "name": "PP TST Thing"}),
    "pp_tst/public/js/sale.js": "// frm.set_value('rate', 1) is a comment\nconst r = frm.doc.rate;\n"
                                "frm.set_value('pp_tst_note', 'hello');\n",
}


def hooks_with(extra: str) -> dict:
    return {"pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"] + extra}


# (check id, label, files to add/replace, expected status, needle in the findings)
PLANTS = [
    ("required_apps", "required_apps commented out",
     {"pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"].replace('required_apps =', '# required_apps =')}, "FAIL",
     "no literal required_apps"),
    ("required_apps", "the upstream org qualifying a platform app",
     {"pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"].replace('"ivendnext/erpnext"]', '"frappe/erpnext"]')}, "FAIL",
     "names the org 'frappe'"),
    ("required_apps", "a platform app imported but not declared",
     {"pp_tst/x.py": "from ivendnext_mpos.api import app_button\n"}, "FAIL", "imports 'ivendnext_mpos'"),
    ("required_apps", "another, non-platform app declared",
     {"pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"].replace('"ivendnext/erpnext"]', '"ivendnext/erpnext", "ivendnext/acme_tools"]')}, "REVIEW",
     "not a platform app"),
    ("required_apps", "a bare name (the install would ask GitHub)",
     {"pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"].replace('"ivendnext/frappe"', '"frappe"')}, "FAIL", "is a bare name"),
    ("framework_alias", "an import of the framework's alias",
     {"pp_tst/x.py": "def f():\n    import ivendframework as _ivf\n    return _ivf\n"}, "FAIL", "ivendframework"),
    ("runtime_patches", "an attribute assignment on a platform module", {"pp_tst/x.py": lint_engine_patch.CANARY},
     "FAIL", "attribute assignment on engine-bound"),
    ("runtime_patches", "a setattr on a platform module", {"pp_tst/x.py": lint_engine_patch.CANARY_SETATTR},
     "FAIL", "setattr on engine-bound"),
    ("runtime_patches", "the framework's ERP module patched",
     {"pp_tst/x.py": "import erpnext.controllers.taxes_and_totals as t\nt.calculate_taxes_and_totals = None\n"},
     "FAIL", "engine-bound 't'"),
    ("runtime_patches", "a patch below the framework's state (frappe.local.db.sql = …)",
     {"pp_tst/x.py": "import frappe\ndef f(q):\n    frappe.local.db.sql = q\n"}, "FAIL", "frappe.local.db.sql"),
    ("runtime_patches", "an ERP module's `session` attribute reassigned",
     {"pp_tst/x.py": "import erpnext.accounts.utils as u\nu.session = None\n"}, "FAIL", "engine-bound 'u'"),
    ("outbound", "a call to a URL with no host declared",
     {"pp_tst/x.py": "import requests\ndef f():\n    return requests.get('https://api.partner.example/x')\n"},
     "FAIL", "no partner_outbound_hosts declared"),
    ("outbound", "a declared host: transport becomes REVIEW",
     {**hooks_with('partner_outbound_hosts = ["api.partner.example"]\n'),
      "pp_tst/x.py": "import requests\ndef f():\n    return requests.get('https://api.partner.example/x')\n"},
     "REVIEW", "imports transport module 'requests'"),
    ("outbound", "a URL to a host the app did not declare",
     {**hooks_with('partner_outbound_hosts = ["api.partner.example"]\n'),
      "pp_tst/x.py": "import requests\ndef f():\n    return requests.post('https://collector.elsewhere.example/up')\n"},
     "FAIL", "'collector.elsewhere.example' is not in partner_outbound_hosts"),
    ("outbound", "mail through the shop's own account",
     {"pp_tst/x.py": "import frappe\ndef f():\n    frappe.sendmail(recipients=['a@b.example'])\n"}, "REVIEW",
     "frappe.sendmail"),
    ("overrides", "override_doctype_class",
     hooks_with('override_doctype_class = {"POS Invoice": "pp_tst.x.MyPOSInvoice"}\n'), "FAIL",
     "override_doctype_class"),
    ("overrides", "override_whitelisted_methods",
     hooks_with('override_whitelisted_methods = {"a.b": "pp_tst.x.b"}\n'), "FAIL", "override_whitelisted_methods"),
    ("overrides", "extend_doctype_class (a class mixed into a platform record type's)",
     hooks_with('extend_doctype_class = {"Sales Invoice": ["pp_tst.x.Mixin"]}\n'), "FAIL", "extend_doctype_class"),
    ("overrides", "regional_overrides",
     hooks_with('regional_overrides = {"India": {"a.b": "pp_tst.x.b"}}\n'), "FAIL", "regional_overrides"),
    ("overrides", "an override built with a spread (any override is refused)",
     hooks_with('BASE = {}\noverride_doctype_class = {**BASE, "POS Invoice": "pp_tst.x.C"}\n'), "FAIL",
     "sets `override_doctype_class` = a value the check cannot read"),
    ("overrides", "an override added to an empty one by a subscript write",
     hooks_with('override_whitelisted_methods = {}\noverride_whitelisted_methods["a.b"] = "pp_tst.x.b"\n'), "REVIEW",
     "could not read `override_whitelisted_methods` (built from a name, changed or used after it is set, set in a block, or imported), so it cannot tell whether rule 2"),
    ("outbound", "a host list built with a spread, no call made",
     hooks_with('BASE = ["api.partner.example"]\npartner_outbound_hosts = [*BASE]\n'), "REVIEW",
     "could not read `partner_outbound_hosts`"),
    ("outbound", "a host list the check cannot read, a call made: still FAIL, and why it is told",
     {**hooks_with('from pp_tst.conf import partner_outbound_hosts\n'),
      "pp_tst/x.py": "import requests\ndef f():\n    return requests.get('https://api.partner.example/x')\n"},
     "FAIL", "a line above judges only what it could read of the list"),
    ("site_scripts", "a desk script hook imported from another module (the check cannot read it)",
     hooks_with('from pp_tst.common import *\n'), "REVIEW", "sets `app_include_js` in a way the check cannot read"),
    ("site_scripts", "a Server Script named in the fixtures list", hooks_with('fixtures = ["Custom Field", "Server Script"]\n'),
     "FAIL", "names 'Server Script': that record is your code running inside the shop's site (rule 3"),
    ("site_scripts", "a Server Script named in the fixtures list with a filter",
     hooks_with('fixtures = [{"dt": "Server Script", "filters": [["name", "like", "PP TST%"]]}]\n'), "FAIL",
     "names 'Server Script'"),
    ("site_scripts", "a Client Script fixture file",
     {"pp_tst/fixtures/client_script.json": json.dumps([{"doctype": "Client Script", "name": "PP TST x"}])}, "FAIL",
     "fixtures/client_script.json holds 'Client Script' records: that is your JavaScript running in every Desk user's"),
    ("site_scripts", "Server Script records in a fixture file with another name",
     {"pp_tst/fixtures/extras.json": json.dumps([{"doctype": "Server Script", "name": "PP TST y"}])}, "FAIL",
     "fixtures/extras.json holds 'Server Script' records"),
    ("site_scripts", "doctype_js on a record type that is not a sales one, the script not even shipped",
     hooks_with('doctype_js = {"Item": "public/js/item.js"}\n'), "FAIL",
     "doctype_js['Item'] -> public/js/item.js: that is your JavaScript running in every Desk user's browser"),
    ("site_scripts", "doctype_list_js on a list view", hooks_with('doctype_list_js = {"Item": "public/js/item_list.js"}\n'),
     "FAIL", "doctype_list_js['Item']"),
    ("site_scripts", "page_js on the till's own page", hooks_with('page_js = {"point-of-sale": "public/js/pos.js"}\n'),
     "FAIL", "page_js['point-of-sale']"),
    ("site_scripts", "app_include_js (loaded on every Desk page)", hooks_with('app_include_js = "pp_tst.bundle.js"\n'),
     "FAIL", "app_include_js -> pp_tst.bundle.js"),
    ("site_scripts", "a Custom Script (the older name) named in the fixtures list", hooks_with('fixtures = ["Custom Script"]\n'),
     "FAIL", "names 'Custom Script'"),
    ("site_scripts", "a Client Script named with the doctype key", hooks_with('fixtures = [{"doctype": "Client Script"}]\n'),
     "FAIL", "names 'Client Script'"),
    ("site_scripts", "a fixture file holding ONE Server Script record, not a list",
     {"pp_tst/fixtures/one.json": json.dumps({"doctype": "Server Script", "name": "PP TST z"})}, "FAIL",
     "fixtures/one.json holds 'Server Script' records"),
    ("site_scripts", "a Server Script standard record in the app's module folder",
     {"pp_tst/pp_tst/server_script/pp_tst_x/pp_tst_x.json": json.dumps({"doctype": "Server Script", "name": "pp_tst_x"})},
     "FAIL", "pp_tst/server_script/pp_tst_x/pp_tst_x.json holds 'Server Script' records"),
    ("site_scripts", "a Client Script standard record in the app's module folder",
     {"pp_tst/pp_tst/client_script/pp_tst_y/pp_tst_y.json": json.dumps({"doctype": "Client Script", "name": "pp_tst_y"})},
     "FAIL", "pp_tst/client_script/pp_tst_y/pp_tst_y.json holds 'Client Script' records"),
    ("site_scripts", "doctype_tree_js on a tree view", hooks_with('doctype_tree_js = {"Item": "public/js/t.js"}\n'),
     "FAIL", "doctype_tree_js['Item']"),
    ("site_scripts", "doctype_calendar_js on a calendar view",
     hooks_with('doctype_calendar_js = {"Item": "public/js/c.js"}\n'), "FAIL", "doctype_calendar_js['Item']"),
    ("site_scripts", "a country script beside the app's own record type",
     {"pp_tst/pp_tst/doctype/pp_tst_thing/regional/India.js": "frappe.ui.form.on('PP TST Thing', {});\n"}, "FAIL",
     "regional/India.js: a script beside your record type"),
    ("site_scripts", "a Web Page named in the fixtures list (the manifest checker refuses it too)",
     hooks_with('fixtures = ["Web Page"]\n'), "FAIL", "names 'Web Page': that record is partner markup or script"),
    ("site_scripts", "a Web Template record in a fixture file",
     {"pp_tst/fixtures/wt.json": json.dumps([{"doctype": "Web Template", "name": "PP TST card"}])}, "FAIL",
     "fixtures/wt.json holds 'Web Template' records"),
    ("site_scripts", "a Custom HTML Block record in a fixture file",
     {"pp_tst/fixtures/chb.json": json.dumps([{"doctype": "Custom HTML Block", "name": "PP TST block"}])}, "FAIL",
     "fixtures/chb.json holds 'Custom HTML Block' records"),
    ("site_scripts", "a script print format (type JS)",
     {"pp_tst/fixtures/pf.json": json.dumps([{"doctype": "Print Format", "name": "PP TST pf", "print_format_type": "JS"}])},
     "FAIL", "fixtures/pf.json holds 'Print Format (JS)' records"),
    ("site_scripts", "a Web Page standard record in the app's module folder",
     {"pp_tst/pp_tst/web_page/pp_tst_p/pp_tst_p.json": json.dumps({"doctype": "Web Page", "name": "pp_tst_p"})}, "FAIL",
     "pp_tst/web_page/pp_tst_p/pp_tst_p.json holds 'Web Page' records"),
    ("site_scripts", "a list-view script beside the app's own record type",
     {"pp_tst/pp_tst/doctype/pp_tst_thing/pp_tst_thing_list.js": "frappe.listview_settings['PP TST Thing'] = {};\n"},
     "FAIL", "pp_tst_thing_list.js: a script beside your record type"),
    ("site_scripts", "a calendar-view script beside the app's own record type",
     {"pp_tst/pp_tst/doctype/pp_tst_thing/pp_tst_thing_calendar.js": "frappe.views.calendar['PP TST Thing'] = {};\n"},
     "FAIL", "pp_tst_thing_calendar.js: a script beside your record type"),
    ("site_scripts", "a hook set in a chained assignment (the check cannot read it)",
     hooks_with('extra = app_include_js = ["a.js"]\n'), "REVIEW", "sets `app_include_js` in a way the check cannot read"),
    ("site_scripts", "a forbidden script AND an unreadable hook: the verdict is FAIL and both are told",
     hooks_with('fixtures = ["Server Script"]\napp_include_js = ["a.js"] + ["b.js"]\n'), "FAIL",
     "sets `app_include_js` in a way the check cannot read"),
    ("site_scripts", "a script beside the app's own record type",
     {"pp_tst/pp_tst/doctype/pp_tst_thing/pp_tst_thing.js": "frappe.ui.form.on('PP TST Thing', {});\n"}, "FAIL",
     "a script beside your record type loads into its Desk form"),
    ("site_scripts", "a script list built by a sum (the check cannot read it)",
     hooks_with('app_include_js = ["a.js"] + ["b.js"]\n'), "REVIEW", "sets `app_include_js` in a way the check cannot read"),
    ("site_scripts", "a fixtures list extended with += (the check cannot read it)",
     hooks_with('fixtures = ["Custom Field"]\nfixtures += ["Server Script"]\n'), "REVIEW",
     "sets `fixtures` in a way the check cannot read"),
    ("channel_hook", "a hook on set_missing_values",
     hooks_with('doc_events = {"POS Invoice": {"set_missing_values": "pp_tst.x.f"}}\n'), "FAIL",
     "set_missing_values"),
    ("channel_hook", "a hook on calculate_taxes_and_totals",
     hooks_with('doc_events = {"*": {"calculate_taxes_and_totals": "pp_tst.x.f"}}\n'), "FAIL",
     "calculate_taxes_and_totals"),
    ("money_validate", "a validate hook on a money record",
     hooks_with('doc_events = {"Sales Invoice": {"validate": "pp_tst.x.f"}}\n'), "REVIEW", "a second reviewer"),
    ("throw_at_submit", "frappe.throw in the on_submit handler",
     {**hooks_with('doc_events = {"POS Invoice": {"on_submit": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "import frappe\ndef f(doc, method=None):\n    frappe.throw('no')\n"}, "FAIL", "x.py:3"),
    ("throw_at_submit", "`from frappe import throw` two calls down, in another module",
     {**hooks_with('doc_events = {"POS Invoice": {"before_submit": ["pp_tst.x.f"]}}\n'),
      "pp_tst/x.py": "from pp_tst.y import g\ndef f(doc, method=None):\n    g(doc)\n",
      "pp_tst/y.py": "from frappe import throw\ndef g(doc):\n    h(doc)\ndef h(doc):\n    throw('no')\n"}, "FAIL",
     "y.py:5"),
    ("throw_at_submit", "the alias imported inside the function (ivendframework.throw)",
     {**hooks_with('doc_events = {"POS Invoice": {"validate": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "def f(doc, method=None):\n    import ivendframework as _ivf\n    _ivf.throw('no')\n"},
     "FAIL", "x.py:3"),
    ("throw_at_submit", "a throw on every record type's submit (\"*\")",
     {**hooks_with('doc_events = {"*": {"on_submit": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "import pp_tst.y as y\ndef f(doc, method=None):\n    y.g()\n",
      "pp_tst/y.py": "import frappe\ndef g():\n    frappe.throw('no')\n"}, "FAIL", "y.py:3"),
    ("throw_at_submit", "a refusal through a relative import (`from .y import g`)",
     {**hooks_with('doc_events = {"POS Invoice": {"on_submit": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "from .y import g\ndef f(doc, method=None):\n    g()\n",
      "pp_tst/y.py": "import frappe\ndef g():\n    frappe.throw('no')\n"}, "FAIL", "y.py:3"),
    ("throw_at_submit", "msgprint with raise_exception, on before_save",
     {**hooks_with('doc_events = {"POS Invoice": {"before_save": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "import frappe\ndef f(doc, method=None):\n    frappe.msgprint('no', raise_exception=True)\n"},
     "FAIL", "x.py:3"),
    ("throw_at_submit", "a refusal on the merged Sales Invoice's submit (it would fail the day's close)",
     {**hooks_with('doc_events = {"Sales Invoice": {"on_submit": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "import frappe\ndef f(doc, method=None):\n    frappe.throw('no')\n"}, "FAIL", "Sales Invoice"),
    ("throw_at_submit", "a bare raise reachable at submit",
     {**hooks_with('doc_events = {"POS Invoice": {"on_submit": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "import frappe\ndef f(doc, method=None):\n    raise frappe.ValidationError('no')\n"},
     "REVIEW", "a `raise` at"),
    ("throw_at_submit", "a handler the walk cannot resolve",
     {**hooks_with('doc_events = {"POS Invoice": {"on_submit": "pp_tst.x.h"}}\n'),
      "pp_tst/x.py": "class A:\n    def run(self, doc, method=None):\n        pass\nh = A().run\n"},
     "REVIEW", "cannot find this handler"),
    ("server_money", "a validate hook that changes a line's rate (the money kit's trap)",
     {**hooks_with('doc_events = {"POS Invoice": {"validate": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "def f(doc, method=None):\n    doc.items[0].rate = doc.items[0].rate - 1\n"
                     "    doc.calculate_taxes_and_totals()\n"}, "FAIL", "writes `rate`"),
    ("server_money", "a before_save hook that sets a discount, two calls down",
     {**hooks_with('doc_events = {"Sales Invoice": {"before_save": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "from pp_tst.y import g\ndef f(doc, method=None):\n    g(doc)\n",
      "pp_tst/y.py": "def g(doc):\n    doc.set('discount_amount', 10)\n"}, "FAIL", "sets `discount_amount`"),
    ("server_money", "a submit hook that re-totals the sale",
     {**hooks_with('doc_events = {"POS Invoice": {"on_submit": "pp_tst.x.f"}}\n'),
      "pp_tst/x.py": "def f(doc, method=None):\n    doc.run_method('calculate_taxes_and_totals')\n"}, "FAIL",
     "re-prices or re-totals"),
    # an unreadable doc_events is a REVIEW on every check that reads it, never a pass
    ("channel_hook", "doc_events built with a spread (the check cannot read it)",
     hooks_with('COMMON = {}\ndoc_events = {**COMMON, "POS Invoice": {"set_missing_values": "pp_tst.x.f"}}\n'),
     "REVIEW", "hooks.py:6: the self-check could not read `doc_events` (built from a name, changed or used after it is set, set in a block, or imported), so it cannot tell whether rule 1 is kept"),
    ("money_validate", "a validate hook added by a subscript write",
     hooks_with('doc_events["Sales Invoice"] = {"validate": "pp_tst.x.f"}\n'), "REVIEW",
     "hooks.py:5: the self-check could not read `doc_events`"),
    ("throw_at_submit", "doc_events imported from another module",
     hooks_with('from pp_tst.common import doc_events\n'), "REVIEW",
     "could not read `doc_events`"),
    ("throw_at_submit", "doc_events written through globals()",
     hooks_with('globals()["doc_events"] = {"POS Invoice": {"on_submit": "pp_tst.x.f"}}\n'), "REVIEW",
     "could not read `doc_events`"),
    ("channel_hook", "doc_events set as an attribute of the module",
     hooks_with('import sys\nsys.modules[__name__].doc_events = {"*": {"set_missing_values": "pp_tst.x.f"}}\n'), "REVIEW",
     "hooks.py:6: the self-check could not read `doc_events`"),
    ("server_money", "doc_events extended with .update()",
     hooks_with('doc_events.update({"POS Invoice": {"validate": "pp_tst.x.f"}})\n'), "REVIEW",
     "could not read `doc_events`"),
    ("throw_at_submit", "a refusal AND an unreadable doc_events: FAIL, and both are told",
     {**hooks_with('doc_events = {"POS Invoice": {"on_submit": "pp_tst.x.f"}}\ndoc_events.update({})\n'),
      "pp_tst/x.py": "import frappe\ndef f(doc, method=None):\n    frappe.throw('no')\n"}, "FAIL",
     "could not read `doc_events`"),
    ("browser_money", "a rate raised with += in the browser",
     {**hooks_with('doctype_js = {"Sales Invoice": "public/js/inc.js"}\n'),
      "pp_tst/public/js/inc.js": "function f(row) { row.rate += 5; }\n"}, "FAIL", "writes `rate`"),
    ("browser_money", "a sales-form script the check cannot find",
     hooks_with('doctype_js = {"POS Invoice": "public/js/nowhere.js"}\n'), "REVIEW", "cannot find this script"),
    ("browser_money", "a doctype_js list whose second file sets a discount over two lines (and a commented line)",
     {**hooks_with('# doctype_js = {"POS Invoice": "public/js/sale.js"}\n'
                   'doctype_js = {"POS Invoice": ["public/js/sale.js", "public/js/disc.js"]}\n'),
      "pp_tst/public/js/disc.js": "frm.set_value(\n  \"additional_discount_percentage\",\n  10\n);\n"},
     "FAIL", "disc.js:1 writes `additional_discount_percentage`"),
    ("browser_money", "an app-wide bundle importing a file that assigns a rate",
     {**hooks_with('app_include_js = ["pp_tst.bundle.js"]\n'),
      "pp_tst/public/js/pp_tst.bundle.js": 'import "./pricer.js";\n',
      "pp_tst/public/js/pricer.js": "function f(row) { row.rate = 0; }\n"}, "FAIL", "pricer.js:1 writes `rate`"),
    ("names", "a record type that clashes with the platform's own",
     {"pp_tst/pp_tst/doctype/location/location.json": json.dumps({"doctype": "DocType", "name": "Location"})},
     "FAIL", "'Location' has the same name as the platform's own"),
    ("names", "a record type without the prefix",
     {"pp_tst/pp_tst/doctype/gadget/gadget.json": json.dumps({"doctype": "DocType", "name": "Gadget"})}, "FAIL",
     "without the app's prefix"),
    ("names", "a module without the prefix", {"pp_tst/modules.txt": "PP TST\nGadgets\n"}, "FAIL",
     "module 'Gadgets'"),
    ("names", "a field on another record type without the field prefix",
     {"pp_tst/fixtures/custom_field.json": json.dumps([{"doctype": "Custom Field", "dt": "Item",
                                                        "fieldname": "custom_colour"}])}, "FAIL", "Item.custom_colour"),
    ("names", "a fixture file holding ONE custom field, not a list",
     {"pp_tst/fixtures/custom_field.json": json.dumps({"doctype": "Custom Field", "dt": "Item", "fieldname": "colour"})},
     "FAIL", "Item.colour (fixtures/custom_field.json)"),
    ("names", "custom fields in a fixture file with another name",
     {"pp_tst/fixtures/fields.json": json.dumps([{"doctype": "Custom Field", "dt": "Item", "fieldname": "colour"}])},
     "FAIL", "Item.colour (fixtures/fields.json)"),
    ("names", "a custom field kept as the module's own record",
     {"pp_tst/pp_tst/custom_field/item-colour/item-colour.json":
      json.dumps({"doctype": "Custom Field", "name": "Item-colour", "dt": "Item", "fieldname": "colour"})},
     "FAIL", "Item.colour (pp_tst/custom_field/item-colour/item-colour.json)"),
    ("names", "a custom field in the module's customisations file",
     {"pp_tst/pp_tst/custom/item.json": json.dumps({"doctype": "Item", "sync_on_migrate": 1, "property_setters": [],
                                                   "custom_fields": [{"dt": "Item", "fieldname": "colour"}]})},
     "FAIL", "Item.colour (pp_tst/custom/item.json)"),
    ("guest", "an endpoint open without sign-in, not declared",
     {"pp_tst/x.py": "import frappe\n@frappe.whitelist(allow_guest=True)\ndef ping():\n    return 1\n"}, "FAIL",
     "`ping` is open to anyone"),
    ("sql_writes", "a raw UPDATE",
     {"pp_tst/x.py": "import frappe\ndef f():\n    frappe.db.sql('UPDATE `tabItem` SET disabled=1')\n"}, "FAIL",
     "(UPDATE)"),
    ("sql_writes", "a raw DELETE in an f-string",
     {"pp_tst/x.py": "import frappe\ndef f(n):\n    frappe.db.sql(f\"delete from `tabItem` where name='{n}'\")\n"},
     "FAIL", "(DELETE)"),
    ("sql_writes", "a raw schema change", {"pp_tst/x.py": "import frappe\nfrappe.db.sql_ddl('alter table x')\n"},
     "FAIL", "db.sql_ddl"),
    ("secrets", "an AWS key", {"pp_tst/conf.py": 'KEY = "AKIA' + "ABCDEFGHIJKLMNOP" + '"\n'}, "FAIL",
     "an AWS access key"),
    ("secrets", "a private key", {"pp_tst/k.txt": "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIE\n"}, "FAIL",
     "a private key"),
    ("secrets", "a hard-coded password", {"pp_tst/conf.py": 'password = "' + "s3cr3tVa1ue99" + '"\n'}, "FAIL",
     "a hard-coded secret"),
    ("licence", "a licence template left unfilled", {"license.txt": "Copyright (c) <year> <copyright holders>\n"},
     "REVIEW", "template placeholder"),
    ("licence", "no licence at all",
     {"pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"].replace('app_license = "proprietary"\n', '')}, "REVIEW",
     "no licence file"),
]
# a guest endpoint that IS declared, a placeholder secret, a SELECT, a declared-host URL, data fixtures: must all stay silent
CLEAN_EXTRAS = {
    "pp_tst/hooks.py": CLEAN["pp_tst/hooks.py"] + 'partner_guest_methods = ["pp_tst.web.status"]\n'
                       'from pp_tst.consts import APP_TITLE as app_title\npartner_outbound_hosts = ["api.partner.example"]\n'
                       'fixtures = ["Custom Field", {"dt": "Property Setter", "filters": []}, {"dt": ["Server Script"]}]\n',
    "pp_tst/fixtures/custom_field.json": json.dumps([{"doctype": "Custom Field", "dt": "Item",
                                                     "fieldname": "pp_tst_note"}]),
    "pp_tst/fixtures/property_setter.json": json.dumps([{"doctype": "Property Setter", "doc_type": "Item",
                                                         "field_name": "description", "dt": "Item",
                                                         "fieldname": "description"}]),
    "pp_tst/pp_tst/custom/item.json": json.dumps({"doctype": "Item", "custom_fields": [
        {"dt": "Item", "fieldname": "pp_tst_size"}, {"dt": "PP TST Thing", "fieldname": "any"}], "property_setters": []}),
    "pp_tst/pp_tst/custom_field/item-pp_tst_grade/item-pp_tst_grade.json":
        json.dumps({"doctype": "Custom Field", "dt": "Item", "fieldname": "pp_tst_grade"}),
    "pp_tst/pp_tst/custom/broken.json": "[1, 2",
    # custom fields the shop never installs: below the top of fixtures/, and a `custom` folder that is not a module
    "pp_tst/fixtures/old/cf.json": json.dumps([{"doctype": "Custom Field", "dt": "Item", "fieldname": "colour"}]),
    "pp_tst/public/custom/item.json": json.dumps({"doctype": "Item", "custom_fields": [{"dt": "Item", "fieldname": "c"}]}),
    "pp_tst/web.py": "import frappe\n@frappe.whitelist(allow_guest=True)\ndef status():\n"
                     "    return frappe.db.sql('select 1')\n",
    "pp_tst/conf.py": 'api_key = "your_api_key_here"\n',
    # shapes beside a record type that load nothing into a form, or only comments: must stay silent
    "pp_tst/pp_tst/doctype/pp_tst_thing/pp_tst_thing.js": "// Copyright (c) 2026\n// frappe.ui.form.on('PP TST Thing', {\n"
                                                         "// \trefresh(frm) {\n// \t},\n// });\n",
    "pp_tst/pp_tst/doctype/pp_tst_thing/test_pp_tst_thing.js": "frappe.ui.form.on('PP TST Thing', {});\n",
    "pp_tst/public/js/doctype/pp_tst_thing/pp_tst_thing.js": "function helper() { return 1; }\n",
    "pp_tst/node_modules/lib/doctype/y/y.json": "{}",
    "pp_tst/node_modules/lib/doctype/y/y.js": "frappe.ui.form.on('Y', {});\n",
    "pp_tst/fixtures/server_script.json": json.dumps([{"doctype": "Custom Field", "dt": "Item",
                                                       "fieldname": "pp_tst_colour"}]),
    # odd inputs that must neither crash the check nor be called a script
    "pp_tst/fixtures/broken.json": "{not json",
    "pp_tst/fixtures/odd.json": json.dumps([1, "x", {"doctype": ["Server Script"]}, {"name": "no doctype"}]),
    "pp_tst/fixtures/folder.json/inner.txt": "a folder named like a fixture file",
    "pp_tst/fixtures/print_format.json": json.dumps([{"doctype": "Print Format", "name": "PP TST jinja",
                                                       "print_format_type": "Jinja"}]),
    "pp_tst/node_modules/lib/server_script/z/z.json": json.dumps({"doctype": "Server Script", "name": "z"}),
    "pp_tst/pp_tst/doctype/pp_tst_thing/folder.js/inner.txt": "a folder named like a script",
}


def _make(td: str, files: dict) -> str:
    for rel, body in files.items():
        p = pathlib.Path(td) / "pp_tst_app" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return str(pathlib.Path(td) / "pp_tst_app")


def main() -> int:
    bad = 0
    # 1. every check's plants
    for cid, label, files, want, needle in PLANTS:
        with tempfile.TemporaryDirectory() as td:
            out = selfcheck.run(_make(td, {**CLEAN, **files}))
            r = next((x for x in out["results"] if x["id"] == cid), {"status": "no such check", "findings": []})
            ok = r["status"] == want and any(needle in f for f in r["findings"])
            bad += not ok
            print(f"  {'fires ' if ok else 'MISSED'} {cid:16s} {label}" + ("" if ok else f"  -> {r}"))
    # 2. the clean control (with the allowed shapes) passes EVERY check
    with tempfile.TemporaryDirectory() as td:
        out = selfcheck.run(_make(td, {**CLEAN, **CLEAN_EXTRAS}))
        noisy = [r for r in out["results"] if r["status"] != "PASS"]
        bad += bool(noisy)
        print(f"  {'silent' if not noisy else 'NOISY '} clean control: all {len(out['results'])} checks PASS"
              + ("" if not noisy else f"  -> {noisy}"))
    # 3. the copied lints' own fixtures still behave as at their source
    for label, src in lint_outbound.FIXTURES.items():
        hit = bool(lint_outbound.scan_source(src, "f.py"))
        bad += not hit
        print(f"  {'fires ' if hit else 'MISSED'} outbound fixture: {label}")
    for label, src in lint_outbound.CLEAN_FIXTURES.items():
        quiet = not lint_outbound.scan_source(src, "f.py")
        bad += not quiet
        print(f"  {'silent' if quiet else 'NOISY '} outbound clean fixture: {label}")
    known_miss = lint_engine_patch.find_patches(
        "from ivendnext_pos.x import m\ndef _m():\n    return m\n_m().f = None\n", "indirect.py")
    bad += bool(known_miss)
    print(f"  {'silent' if not known_miss else 'WIDENED'} runtime_patches: the stated bound (an indirection) stays a "
          f"miss — if this fires, update the bound in lint_engine_patch.py")
    quiet = not lint_engine_patch.find_patches(lint_engine_patch.CLEAN, "clean.py")
    bad += not quiet
    print(f"  {'silent' if quiet else 'NOISY '} runtime_patches clean sample (incl. frappe.flags)")
    # 4. the manifest arm, and the default path reading a real app
    with tempfile.TemporaryDirectory() as td:
        m = pathlib.Path(td) / "m.json"
        m.write_text(json.dumps({"manifest_version": 1, "app": "pp_tst", "prefix": "PP TST",
                                 "server_scripts": [{"name": "x"}]}), encoding="utf-8")
        out = selfcheck.run(_make(td, CLEAN), manifest=str(m))
        r = next(x for x in out["results"] if x["id"] == "manifest")
        ok = r["status"] == "FAIL"
        bad += not ok
        print(f"  {'fires ' if ok else 'MISSED'} manifest         a server script in the manifest")
    real = pathlib.Path(selfcheck.HERE).parent.parent / "samples" / "s3_price_audit" / "pp_pda"
    if real.exists():
        out = selfcheck.run(str(real))
        r = next(x for x in out["results"] if x["id"] == "required_apps")
        ok = r["status"] == "PASS" and out["app"] == "pp_pda"
        bad += not ok
        print(f"  {'reads ' if ok else 'BROKEN'} default path: a real app's hooks.py is parsed (S3)")
    print(f"selfcheck self-test {'GREEN' if not bad else 'RED'}: {len(PLANTS)} plants across "
          f"{len({p[0] for p in PLANTS})} checks + the manifest arm, a clean control, the copied lints' fixtures"
          + ("" if not bad else f" — {bad} failure(s)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
