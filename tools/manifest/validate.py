# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/business_logic/manifest_check.py,
# at development 60147699cce4f7bd35f73e111649ce108eb2dcc2. The shop's own checker (the install screen runs it) is the source;
# this copy lets you check a manifest before you send it, and refuses the same manifests in the same words. Everything
# below this header equals the source, except seventeen comments reworded in plain words (they named the product's
# internal row and lane ids, a train, or the framework's own readers). A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""The companion manifest — the VALIDATOR. Pure Python: no framework import, no network.

A partner's own data (record types, fields, print formats, notifications, workspaces, sale details, webhooks)
ships as one ``manifest.json``. This file decides, before anything touches a shop, whether every element is
one a manifest may carry, and names the reason for every refusal. The shop's installer (``manifest_install.py``, which
the install screen runs inside the shop's site) calls the same ``validate()`` again before it installs anything.

    python3 tools/manifest/validate.py samples/s2_bins/manifest.json      # exit 0 = valid; 1 = refused

Shape (every key optional except ``manifest_version``, ``app``, ``prefix`` and ``version``)::

    {"manifest_version": 1 | 2, "app": "pp_bln", "prefix": "PP BLN", "title": "...", "version": "0.1.0",
     "allowed_urls": ["https://partner.example/webhook"],
     "doctypes": [...], "custom_fields": [...], "property_setters": [...], "print_formats": [...],
     "notifications": [...], "workspaces": [...], "sale_attributes": [...], "webhooks": [...],
     # v2: "reports", "number_cards", "dashboard_charts", "dashboards", "list_settings", "workflows",
     #              "naming_rules", "links", "registered_applications", "remote_keys"
     # v2 (the declaration records of the shipped extension points): "extension_subscriptions", "desk_actions",
     #              "save_rules",
     #              "fiscal_readers"
     # v2 (2026-10-08): "scan_sources", "field_rules"; the check and capture extension points are two more
     #              `point`s of "extension_subscriptions"
     # v2: "label_layouts", "list_marks"
     # v2: "extension_modules" (a module our certify service signed, and the "wasm" service that runs it)
     # v2: "register_books" (the books of a regulated-stock register, installed as Retail Register Book)
    }

The rules, in plain words, are in ``recipes/manifest.md``.

⚠ The script check (``_SCRIPT_RE``) is a TRIPWIRE, not a control: it reads the manifest's text, and a print format
is a template whose OUTPUT is not escaped, so a determined author can still assemble markup at render time, or
point an image at an outside address. The shop's administrator decides, from a summary
the installer writes (``extension_package.summary``), where every print format is listed as a template that runs
when printed; this validator catches the honest mistakes and the obvious attempts. It reads text, not
entities (`java&#115;cript:` in a link passes), and its inline-handler arm also refuses a plain word such as
`Online=1` in a label or description (a bound, never loosened — that widens the sink).

⚠ The print-format rules are a TRIPWIRE too. A print format may not name the framework's raw
SQL (``db.sql``), its query builder or its outside fetchers (``make_*_request``), and an address it loads (``src``,
``href``, ``srcset``, ``poster``, ``background``, ``action``, ``formaction``, ``url(``, ``@import``) may hold
template syntax only as one whole ``{{ a.b }}`` reference. Name matching
cannot stop the raw SQL reached by indexing (``db["sql"]``), the ``attr`` filter with a built name, ``render_template`` on a built string, a
whole tag printed from a string, a ``<meta http-equiv=refresh>``, or an address set with ``{% set %}`` and printed as
``{{ u }}`` — six known evasions, each a known-pass canary in ``test_template_readers.py``. The framework's other
template helpers (``get_all``, ``get_doc``, ``db.get_value``) read without the viewer's rights and are only WARNED
(``PRINT_READER_WARNING``); since version 2.1.0 a row or value read (the framework's own ``get_all``, ``get_list``,
``db.get_value`` …) whose quoted record type is one ``ivn_rows`` serves is refused (``PRINT_SERVED_TYPES``;
the framework's own types, such as Address, child tables and whole-record reads have no replacement and stay
warned). ``ivn_rows`` and ``ivn_value`` apply the rights.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
import unicodedata

MANIFEST_VERSION = 2  # v2 reads every v1 manifest unchanged
VERSIONS = (1, 2)
KINDS_V1 = (
    "doctypes",
    "custom_fields",
    "property_setters",
    "print_formats",
    "notifications",
    "workspaces",
    "sale_attributes",
    "webhooks",
)
# v2: the screen kinds (native screens first), approvals by workflow, the feed registration, the remote till key
KINDS_V2 = (
    "reports",
    "number_cards",
    "dashboard_charts",
    "dashboards",
    "list_settings",
    "workflows",
    "naming_rules",
    "links",
    "registered_applications",
    "remote_keys",
    # the declaration records of the shipped extension points (2026-10-06); a module before the service that runs it
    "extension_modules",
    "extension_subscriptions",
    "desk_actions",
    "save_rules",
    "fiscal_readers",
    # the declaration records of the scan, field, check and capture extension points (2026-10-08)
    "scan_sources",
    "field_rules",
    # P-LABEL's layout record
    "label_layouts",
    # P-LISTMARK's list mark
    "list_marks",
    # The regulated-stock register books (the register door)
    "register_books",
)
KINDS = KINDS_V1 + KINDS_V2
# The declaration records of extension points that have NOT shipped: kind -> (the extension point, its spec). Each is
# REFUSED, with the extension point it waits on, until that extension point has shipped on the site; its installer is
# written when the extension point is. None waits today: P-RECEIPT shipped (2026-10-10) with no manifest kind, so
# `receipt_blocks` is refused for good (REFUSED_KINDS).
POINT_KINDS: dict[str, tuple[str, str]] = {}
# Kinds refused for another reason a partner reads.
WAITING_KINDS = {
    "point_subscriptions": "the kind is called 'extension_subscriptions' now (the record is Retail Extension Subscription)",
}
TOP_KEYS = {
    "manifest_version",
    "app",
    "prefix",
    "title",
    "version",
    "publisher",
    "description",
    "allowed_urls",
    *KINDS,
}
STD_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}

# Kinds a manifest may NOT carry, each with the reason a partner reads.
REFUSED_KINDS = {
    "server_scripts": "a server script runs partner code inside the shop's own saves; partners use a till key "
    "or a connected app instead",
    "client_scripts": "a client script runs partner code in the browser of every Desk user who opens the form",
    "web_pages": "a web page is published on the shop's own web address and can carry script or pass itself "
    "off as the shop",
    "web_templates": "a web template puts partner markup on every web page that uses it",
    "receipt_blocks": "a shop's own receipt lines are the register's Receipt Header and Footer, two fields the shop "
    "or a partner sets on the register; a tax authority's QR and seal reach the receipt through fiscal_readers",
}

# Field types a manifest's own fields may use. HTML and Button are left out on purpose (HTML shows its own
# markup in Desk; a Button needs a script to do anything).
FIELD_TYPES = {
    "Data",
    "Int",
    "Float",
    "Currency",
    "Percent",
    "Check",
    "Select",
    "Link",
    "Dynamic Link",
    "Date",
    "Datetime",
    "Time",
    "Small Text",
    "Text",
    "Long Text",
    "Text Editor",
    "Table",
    "Table MultiSelect",  # each choice is a row of the manifest's own child type holding one link
    "Section Break",
    "Column Break",
    "Tab Break",
    "Read Only",
    "Attach",
    "Attach Image",
    "Barcode",
    "Phone",
    "Rating",
    "Duration",
}
REFUSED_FIELD_TYPES = {
    "HTML": "an HTML field shows its own markup in Desk, which can carry script",
    "Button": "a button does nothing without a script, and a manifest carries none",
}
# The nine rights the framework's permission record switches ON by default (its permission record's definition file; every other
# right defaults 0). Re-read that file on a framework update: a new default-ON right must join this list.
RIGHTS = ("read", "write", "create", "delete", "report", "export", "share", "print", "email")
# Roles the framework gives users by itself (its permission module's automatic roles; `Guest` is refused on its own, below): `All` goes to every
# signed-in user, website customers included, `Desk User` to every staff user, `Administrator` is the superuser. A manifest names none of them.
AUTOMATIC_ROLES = ("All", "Desk User", "Administrator")
AUTOMATIC_REASON = (
    "a manifest may not name All, Desk User or Administrator: the framework gives those to users by itself (All to every "
    "signed-in user, website customers included, Desk User to every staff user), so naming one puts users the shop's "
    "administrator never chose behind it"
)


def _norm(role: str) -> str:
    # measured on the bench: the database finds a role without regard to case or a trailing space, so `all` or `Guest ` is stored
    # as the real role; compare the same way.
    return role.strip().casefold()


# ... and without regard to accents either (`Àll`, `Guèst` were stored as All, Guest; measured), and the same collation ignores hidden
# characters. A Python compare cannot follow it, so a role name is plain ASCII: the shop's roles are (Retail Manager, System Manager).
_PLAIN_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")
PLAIN_ROLE_REASON = (
    "a role name is plain letters (a to z, no accents), digits, spaces, hyphens or underscores: the database finds a "
    "role without regard to accents or hidden characters, so any other spelling could be stored as a role you did not name"
)


def _odd(role) -> bool:
    return isinstance(role, str) and not _PLAIN_ROLE.match(role)


def _guest(role) -> bool:
    return isinstance(role, str) and _norm(role) == "guest"


def _automatic(role) -> bool:
    return isinstance(role, str) and _norm(role) in {_norm(r) for r in AUTOMATIC_ROLES}


DOCTYPE_KEYS = {
    "name",
    "istable",
    "issingle",
    "fields",
    "permissions",
    "autoname",
    "naming_rule",
    "title_field",
    "sort_field",
    "sort_order",
    "search_fields",
    "track_changes",
    "description",
    "quick_entry",
    "show_title_field_in_link",
}
REFUSED_DOCTYPE_KEYS = {
    "is_submittable": "a submittable record type joins the shop's accounting and stock lifecycle; a manifest's "
    "record types hold the partner's own data only",
    "issubmittable": None,  # same reason (alias), filled below
    "is_virtual": "a virtual record type needs partner code to read its data",
    "module": "the installer chooses the module, so the uninstall can find everything",
    "custom": "the installer marks every record type as custom",
    "is_tree": "a tree record type is not supported by this installer yet",
}
REFUSED_DOCTYPE_KEYS["issubmittable"] = REFUSED_DOCTYPE_KEYS["is_submittable"]
FIELD_KEYS = {
    "fieldname",
    "fieldtype",
    "label",
    "options",
    "reqd",
    "default",
    "in_list_view",
    "in_standard_filter",
    "mandatory_depends_on",
    "read_only_depends_on",
    "bold",
    "read_only",
    "hidden",
    "unique",
    "description",
    "insert_after",
    "length",
    "precision",
    "non_negative",
    "search_index",
    "in_preview",
    "allow_on_submit",
    "fetch_from",
    "depends_on",
    "collapsible",
    "columns",
    "set_only_once",
    "translatable",
}
ENGINE_GUARDED_PROPS = {
    "reqd": "making a field mandatory on a shop's own record type can stop its saves, a till sale included",
    "read_only": "making a field read-only on a shop's own record type can stop a person or the till setting it",
    "hidden": "hiding a field on a shop's own record type can hide a value the shop or the engine needs",
}
# Enforced by the server on every save of the record (a till sale included): on the shop's own record types a field
# the manifest adds may not carry them, and a property setter may not set them.
SAVE_ENFORCED = {"default", "unique", "non_negative", "length", "set_only_once", "precision"}
SAVE_ENFORCED_REASON = (
    "is enforced on every save of a shop's own record type, a till sale included, so a "
    "manifest may not set it there"
)
# A field the manifest adds names the roles that change it (``write_roles``, who read it too) and,
# optionally, the roles that read it (``read_roles``; left out: every role that reads the record type when
# the app installs). The installer puts the field at a permission level of its own on that record type,
# with one permission row per role (``manifest_install._apply_limits``); the till shows, searches and
# carries offline a Customer field only for a user who reads it, and an Item field above level 0 never.
LIMIT_KEYS = ("read_roles", "write_roles")
# fields that hold no value of their own to read or change
LIMIT_NO_VALUE = {
    "Section Break",
    "Column Break",
    "Tab Break",
    "Table",
    "Table MultiSelect",
    "Read Only",
}
LIMIT_WRITE_REASON = (
    "a field limited to roles names write_roles, the roles that change it (they read it too); "
    "read_roles, the roles that read it, is optional (left out: every role that reads the record type)"
)
LIMIT_REQUIRED_REASON = (
    "a field only some roles may change cannot be mandatory: every other role's saves would fail"
)
LIMIT_FETCH_REASON = (
    "copies {0}, a field only some roles read, into a field every role that reads this record "
    "reads (fetch_from)"
)
LIMIT_TEMPLATE_REASON = (
    "names {0}, a field only some roles read: a template prints or sends what it names to whoever "
    "prints or receives it, whatever their roles"
)
# What a property setter MAY change on a shop's own record type (on the manifest's own added field): display only.
ENGINE_DISPLAY_PROPS = {
    "bold",
    "in_list_view",
    "in_standard_filter",
    "label",
    "description",
    "columns",
    "collapsible",
    "in_preview",
    "depends_on",
    "documentation_url",
}
OWN_DOCTYPE_SETTER_HINTS = {
    "title_field": "the name of one of this record type's fields",
    "sort_field": "the name of one of this record type's fields",
    "sort_order": "ASC or DESC",
    "search_fields": "names of this record type's fields, separated by commas",
    "track_changes": "0 or 1",
    "quick_entry": "0 or 1",
    "show_title_field_in_link": "0 or 1",
}
NOTIFY_KEYS = {
    "name",
    "document_type",
    "event",
    "channel",
    "subject",
    "message",
    "recipients",
    "condition",
    "days_in_advance",
    "date_changed",
    "value_changed",
    "set_property_after_alert",
    "property_value",
    "attach_print",  # the manifest's own print format, on its own record types only
    "print_format",
}
# P-MANIFEST4: the framework's two other attachment keys (on its later versions) mail a file a field names
ATTACH_FILE_KEYS = ("attach_files", "from_attach_field")
ATTACH_FILE_REASON = "a file named by a field can be any private file on the site, and it is mailed with no rights check"
ATTACH_PRINT_REASON = (
    "a notification attaches a print only on the manifest's own record types, and only one of the manifest's own "
    "print formats for that record type, named in print_format"
)
ATTACH_READER_REASON = (
    "an attached print is rendered with no rights applied, so its print format may not use the framework, "
    "its reading helpers or another template (it would mail whatever they read); show the record's own "
    "fields, formatted with doc.get_formatted"
)
# a template another app ships runs with this print's context (and may read through the framework)
_TEMPLATE_LOAD_RE = re.compile(r"\{%[-+]?\s*(include|import|from|extends)\b")
# A settings record (issingle) of the manifest's own — one record, no list, its values in the shared Singles
# table. What it may carry, and the only places that may name it (anything else that names a record type would
# read a table it does not have: a list, a report, a date notification's daily read, a webhook, a link).
SINGLE_KEYS = {"name", "issingle", "fields", "permissions", "description", "track_changes"}
SINGLE_SETTER_PROPS = {"description", "track_changes"}
SINGLE_FIELD_KEYS = {"unique", "search_index"}  # the framework clears both on a single's fields
SINGLE_RIGHTS = ("report", "export")  # the framework strips both from a single's permission rows
# kind -> the keys of its elements that may name a single; None: the whole element (a setter's value never names a
# record type). A save rule's value_from reads a single by its own name (P-MANIFEST4 §3B); its
# record type, field and conditions still may not name one.
SINGLE_NAMERS = {"property_setters": None, "save_rules": ("value_from_type", "value_from_name")}
SINGLE_REASON = (
    "is a settings record (one record, no list): only a property setter, a workspace shortcut "
    "or a save rule's value_from may name it"
)
NOTIFY_CHANNELS = {"Email", "System Notification"}
NOTIFY_EVENTS = {"New", "Save", "Submit", "Cancel", "Days Before", "Days After", "Value Change"}
WORKSPACE_BLOCKS = {"header", "paragraph", "spacer", "shortcut", "card"}
SHORTCUT_TYPES = {"DocType", "Report", "URL"}

_APP_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]*( [A-Z][A-Z0-9]*){0,2}$")
# a prefix's first word becomes the start of its fields' names (``field_prefix``): never a word
# the engine starts the names of flags it reads with — some are no field anywhere (``ignore_party``,
# ``for_shopping_cart``, ``include_expired_batches``), so a field named so acts on the line pricer
RESERVED_PREFIX_WORDS = frozenset(
    {
        "IS",
        "IGNORE",
        "FOR",
        "REDEEM",
        "HAS",
        "UPDATE",
        "SKIP",
        "ALLOW",
        "APPLY",
        "SET",
        "DONT",
        "BASE",
        "INCLUDE",
        "NO",
        "DO",
        "POST",
        "REMOVE",
        "PRICING",
        "PRICE",
        "FREE",
        "RECALLED",  # the engine's recalled_invoice (discount_limits.py)
        "NOT",  # ivend_loyality's not_valid_for_loyalty on a sale's line
    }
)
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-]{0,60}$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/\-]*)?$")
# A help address. Desk writes a record type's `documentation` into the empty list's Need Help? link and a
# field's `documentation_url` into its help icon, unchecked — so the value is https only, with no quote, space,
# `<` or `>` (the quote-safe shape of _URL_RE, plus a #heading), matched whole (a `$` lets a newline through).
_HELP_URL_RE = re.compile(
    r"https://[A-Za-z0-9.\-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/\-]*)?(#[A-Za-z0-9._~\-]*)?"
)
HELP_PROPS = {"documentation", "documentation_url"}
HELP_REASON = (
    "a help address is an https address written only in letters A to Z or a to z (no accents), digits and . _ ~ / -, "
    "with an optional #heading (no query, quote, space, < or >), because Desk shows it as a link"
)


def help_address_ok(value) -> bool:
    return isinstance(value, str) and _HELP_URL_RE.fullmatch(value) is not None


# What a property setter may change on the manifest's OWN record type. Record-type level: what the
# manifest's record type may carry itself, less its structure (name, fields, permissions, naming — the checks
# the manifest runs on those do not run on a setter), plus its help address. Field level: how a field is
# shown and used, never its type, options or name (an HTML type or markup options would step round
# REFUSED_FIELD_TYPES) — change those in the record type itself. A setter's value never meets the
# framework's own record-type save, so its shape is checked here.
OWN_DOCTYPE_SETTER_PROPS = (
    DOCTYPE_KEYS
    - {"name", "istable", "issingle", "fields", "permissions", "autoname", "naming_rule"}
) | {"documentation"}
OWN_FIELD_SETTER_PROPS = (FIELD_KEYS - {"fieldname", "fieldtype", "options", "insert_after"}) | {
    "documentation_url"
}
_FLAG_RE = re.compile(r"[01]")
OWN_DOCTYPE_SETTER_VALUES = {
    "title_field": _FIELD_RE,
    "sort_field": _FIELD_RE,
    "sort_order": re.compile(r"ASC|DESC"),
    "search_fields": re.compile(r"[a-z][a-z0-9_]*(\s*,\s*[a-z][a-z0-9_]*)*"),
    "track_changes": _FLAG_RE,
    "quick_entry": _FLAG_RE,
    "show_title_field_in_link": _FLAG_RE,
}
# Script in markup: a script, frame or object element, an inline event handler, or a javascript: address.
# What leaves the shop. A manifest may hold templates that read the shop's data (the framework gives every template
# get_all, get_doc, db.get_value — verified); that is fine where the output stays with the shop's
# staff, and a leak wherever it leaves: a webhook body sent to the partner, an address a print format loads (an image
# URL can carry data out), a notification sent to an address the manifest names.
_OUTSIDE_URL_RE = re.compile(r"(https?:)?//[A-Za-z0-9]", re.I)
_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
# the framework is reachable by its other names too (the pattern names them)
_SHOP_DATA_RE = re.compile(r"\b(frappe|ivendframework|frappeclient)\b", re.I)
# in a print format, the framework's raw SQL, its query builder and its outside fetchers are
# refused (a TRIPWIRE: the six known evasions in the module's opening note pass)
_PRINT_RAW_RE = re.compile(
    r"\bdb\s*\.\s*(sql\w*|multisql)\b|\bqb\s*[.\[]|\bmake_\w*request\b", re.I
)
# an address a print loads (an attribute that names one, url(...), @import "...") and its value
_ADDRESS_RE = re.compile(
    r"""\b(?:src|href|srcset|poster|background|action|formaction)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]*))"""
    r"""|url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\)|@import\s*(?:"([^"]*)"|'([^']*)')""",
    re.I,
)
# the framework's template helpers that READ records without the viewer's rights (a print using one
# is warned, naming ivn_rows; formatting helpers such as its value formatter are not readers) — and
# this app's receipt_partner_code, which prints a partner's code with no rights check
_PRINT_READER_RE = re.compile(
    r"\b(get_all|get_list|get_doc|get_cached_doc|get_last_doc|get_mapped_doc|get_value"
    r"|get_single_value|get_cached_value|get_print|attach_print|get_fullname|get_system_settings"
    r"|run_script|db\.\w+|frappe\s*\.\s*call|frappeclient|receipt_partner_code)\b",
    re.I,
)
# the one template form an address may be: a whole plain dotted reference, `{{ row.image }}`
_PLAIN_REFERENCE_RE = re.compile(r"\s*\{\{\s*[A-Za-z_]\w*(\.[A-Za-z_]\w*)*\s*\}\}\s*\Z")
PRINT_READER_WARNING = (
    "this print format reads through the framework's own helpers, which skip the viewer's rights (a share-key "
    "visitor sees what they return): read other records through ivn_rows and ivn_value. The checker refuses "
    "a row or value read of a record type ivn_rows serves"
)
# Since 2.1.0: the framework's ROW and VALUE readers called on the framework (its `get_all(`,
# `get_list(`, `db.get_value(` / `get_all(` / `get_list(`) whose record type is a quoted first
# argument or a quoted `doctype=`; group 1 or 2 is the type. ivn_rows / ivn_value replace exactly these.
# ⚠ A whole-record reader (get_doc …: its child rows have no ivn_rows door), a render, a map or a count, an
# alias (its `db` object given another name with `{% set %}`), a subscript (`['get_all']` on its object) or a built name stays warned.
_PRINT_TYPED_READ_RE = re.compile(
    r"\bfrappe\s*\.\s*(?:get_all|get_list|db\s*\.\s*(?:get_value|get_all|get_list))"
    r"""\s*\(\s*(?:doctype\s*=\s*)?(?:'([^'\\]*)'|"([^"\\]*)")"""
)
# The record types ivn_rows serves (template_readers._record_type_refusal is None), read on a test site
# running version 2.1.0. ⚠ Pinned by test_template_readers: every name here is
# served (no read without a replacement is refused), and every type THIS app ships that ivn_rows serves is
# here (a pack that adds one regenerates the list in the same change). A type the engine adds later is
# only warned until the list is regenerated from the site.
PRINT_SERVED_TYPES = frozenset(
    "|".join(
        (
            "Account|Account Closing Balance|Accounting Dimension|Accounting Dimension Filter",
            "Accounting Period|Activity Cost|Activity Type|Advance Payment Ledger Entry",
            "Appointment|Apriori Recommendation Data|Asset|Asset Activity|Asset Capitalization",
            "Asset Category|Asset Depreciation Schedule|Asset Maintenance|Asset Maintenance Log",
            "Asset Maintenance Team|Asset Movement|Asset Repair|Asset Shift Allocation",
            "Asset Shift Factor|Asset Value Adjustment|Authorization Rule|BOM|BOM Creator",
            "BOM Update Log|Balance Stock|Bank|Bank Account|Bank Account Subtype",
            "Bank Account Type|Bank Guarantee|Bank Statement Import|Bank Transaction|Barcode Mask",
            "Batch|Bin|Bisect Nodes|Blanket Order|Branch|Brand|Budget|Bulk Transaction Log Detail",
            "Button Group Panel|Button Panel Control|Call Log|Campaign|Card View Control",
            "Card View Group Control|Cash Drawer Log|Cashier Closing|Cheque Print Template",
            "Closing Stock Balance|Code List|Common Code|Communication Medium|Company|Competitor",
            "Contract|Contract Template|Control Panel Settings|Cost Center|Cost Center Allocation",
            "Coupon|Coupon Code|Coupon Ledger|Currency Exchange|Custom Display Control|Customer",
            "Customer Feedback Question|Customer Group|Customs Tariff Number|Data Grid Control",
            "Delivery Note|Delivery Trip|Department|Designation|Downtime Entry|Driver|Dunning",
            "Dunning Type|Email Campaign|Email Digest|Employee|Employee Group",
            "Exchange Rate Revaluation|Feedback Submission|Finance Book|Fiscal Year",
            "Form Number Card|Fulfillment Plan|GL Entry|Gift Card|Gift Card Balance",
            "Gift Card Master|Holiday List|Homepage Section|Import Supplier Invoice",
            "Incoming Call Settings|Incoterm|Industry Type|Information Control|Input Control",
            "Installation Note|Integration Sync Log|Interface Profile|Inventory Dimension",
            "Invoice Discounting|Issue|Issue Priority|Issue Type|Item|Item Alternative",
            "Item Attribute|Item Group|Item Label Printing|Item Manufacturer|Item Price",
            "Item Tax Template|Ivend Font|Job Card|Journal Entry|Journal Entry Template",
            "Landed Cost Voucher|Lead|Lead Source|Ledger Health|Ledger Merge|Location",
            "Look Up Control|Lower Deduction Certificate|Loyalty Point Entry|Loyalty Program",
            "Maintenance Schedule|Maintenance Visit|Manager Override Log|Manufacturer",
            "Market Segment|Material Request|Media Control|Mode of Payment|Monthly Distribution",
            "Non Conformance|Operation|Opportunity|Opportunity Lost Reason|Opportunity Type",
            "POS Closing Entry|POS Command|POS Interface Custom Theme|POS Invoice",
            "POS Invoice Merge Log|POS Opening Entry|POS Profile|POS Shift Profile|POS Terminal",
            "POS Transaction Mode|Packing Slip|Page Config|Party Link|Party Specific Item",
            "Party Type|Payment Entry|Payment Gateway Account|Payment Ledger Entry|Payment Order",
            "Payment Request|Payment Template|Payment Term|Payment Terms Template",
            "Period Closing Voucher|Pick List|Plant Floor|Price List|Pricing Rule|Print Heading",
            "Process Deferred Accounting|Process Payment Reconciliation",
            "Process Payment Reconciliation Log|Process Statement Of Accounts",
            "Process Subscription|Product Bundle|Production Plan|Project|Project Template",
            "Project Type|Project Update|Promotion Bonus Buys Master|Promotion Log",
            "Promotional Scheme|Prospect|Purchase Invoice|Purchase Order|Purchase Receipt",
            "Purchase Taxes and Charges Template|Putaway Rule|Quality Action|Quality Feedback",
            "Quality Feedback Template|Quality Goal|Quality Inspection",
            "Quality Inspection Parameter|Quality Inspection Parameter Group",
            "Quality Inspection Template|Quality Meeting|Quality Procedure|Quality Review",
            "Question List|Quotation|Quotation Lost Reason|Reason Code Master",
            "Registered Application|Repost Accounting Ledger|Repost Payment Ledger",
            "Reprint Transaction Log|Request for Quotation|Retail Badge Credential|Retail Coupon Draw",
            "Retail Desk Action|Retail Device Trust|Retail Extension Install",
            "Retail Extension Module|Retail Fiscal Reader|Retail Fiscal Regime Config",
            "Retail Floor Place|Retail Floor Section",
            "Retail Item Availability|Retail Kitchen Order|Retail Kitchen Station",
            "Retail Label Layout|Retail Layaway Plan|Retail List Mark",
            "Retail Open Check|Retail Open Check Claim|Retail Open Check Event",
            "Retail Option Group|Retail Override Request|Retail PIN Event|Retail POS Theme",
            "Retail Permission|Retail Provisional Series|Retail Register Book",
            "Retail Register Count|Retail Register Erasure|Retail Register Line",
            "Retail Register Period|Retail Register Sequence|Retail Register State",
            "Retail Save Rule",
            "Retail Save Rule Count|Retail Scan Source|Retail UX Metric|Routing|SMS Log",
            "Sale Attribute|Sales Invoice|Sales Order|Sales Partner|Sales Partner Type",
            "Sales Person|Sales Stage|Sales Taxes and Charges Template|Serial No",
            "Serial and Batch Bundle|Service Level Agreement|Session Lock|Share Transfer",
            "Share Type|Shareholder|Shipment|Shipment Parcel Template|Shipping Rule",
            "South Africa VAT Settings|Status Bar Control|Stock Entry|Stock Entry Type",
            "Stock Ledger Entry|Stock Reconciliation|Stock Reservation Entry|Store Expense",
            "Store Expense Type|Subcontracting BOM|Subcontracting Order|Subcontracting Receipt",
            "Subscription|Subscription Plan|Supplier|Supplier Group|Supplier Quotation",
            "Supplier Scorecard|Supplier Scorecard Criteria|Supplier Scorecard Period",
            "Supplier Scorecard Standing|Supplier Scorecard Variable|Surcharge|Task|Task Type",
            "Tax Category|Tax Rule|Tax Withholding Category|Team|Telephony Call Type",
            "Terms and Conditions|Territory|Thermal Label|Timesheet|Transaction Deletion Record",
            "Transaction Item Attribute|Transaction Promotion Detail|UAE VAT Settings|UOM",
            "UOM Category|UOM Conversion Factor|Unreconcile Payment|User Face Maps|Vehicle|Video",
            "Voice Call Settings|Warehouse|Warehouse Type|Warranty Claim|Work Order|Workstation",
            "Workstation Type",
        )
    ).split("|")
)
# on this framework a notification's condition is evaluated on the server WITH
# its database (notification get_context), as a workflow transition's would be, so a manifest carries none
NOTIFY_CONDITION_REASON = (
    "a notification condition is an expression evaluated on the server with the shop's database; a "
    "manifest carries none (send on the event, and filter in your own service)"
)
NOTIFY_FIELD_REASON = (
    "a notification sent to a field of the record goes to a user of the shop: that field is a Link to "
    "User on the manifest's own record type (any other field can be given an address the manifest chose)"
)
# P-NOTIFYDATE: the two date events match no save event (the framework's save runs only the notifications
# whose event is the save's own); the daily scheduler sends them. So on a shop's own record type a manifest may ship
# those two, and nothing that would read more than the record or write back into it from the scheduler.
DATE_EVENTS = {"Days Before", "Days After"}
NOTIFY_SHOP_EVENT_REASON = (
    "on a shop's own record type a notification may only be Days Before or Days After a date: any other event "
    "runs inside every save of it, and an error in it stops that save (a till sale included)"
)
# every template helper a shop's apps register is a template global in a notification too, so a list of refused
# names fails by omission: on a shop's type the text allows only plain text and {{ doc.<field> }}
_DOC_PLACEHOLDER_RE = re.compile(r"\{\{\s*doc\.([a-z][a-z0-9_]*)\s*\}\}")
_TEMPLATE_RE = re.compile(r"\{[{%#]|[}%#]\}")
# the framework renders a one-line text ending in one of these as a template FILE of any installed app
# (its path test), so such a message would run that file with the notification's context
_TEMPLATE_PATH_EXTS = ("html", "css", "scss", "py", "md", "json", "js", "xml", "txt")


def _template_path(text: str) -> bool:
    return "\n" not in text and "." in text and text.rsplit(".")[-1] in _TEMPLATE_PATH_EXTS


def doc_placeholders(text) -> list:
    """The fields a subject or message names as {{ doc.<field> }} (the installer checks each is the record type's)."""
    return _DOC_PLACEHOLDER_RE.findall(text) if isinstance(text, str) else []


def _date_notification(v, w: str, name, n: dict):
    """A Days Before / Days After notification on a shop's own record type (the installer checks the record type
    itself: a table or single-record type, and date_changed a Date or Datetime field of it)."""
    days = n.get("days_in_advance")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        v.refuse(w, name, "days_in_advance is a whole number of days from 1 to 365")
    if not (isinstance(n.get("date_changed"), str) and _FIELD_RE.match(n["date_changed"])):
        v.refuse(w, name, "date_changed names the record's date field")
    if n.get("set_property_after_alert") or "property_value" in n:
        v.refuse(
            w,
            name,
            "on a shop's own record type a notification may not set a field after it is sent: that saves the "
            "shop's record from the scheduler, running every rule of that save",
        )
    for k in ("subject", "message"):
        text = n.get(k)
        if isinstance(text, str) and (
            _TEMPLATE_RE.search(_DOC_PLACEHOLDER_RE.sub("", text)) or _template_path(text)
        ):
            v.refuse(
                f"{w}.{k}",
                name,
                "on a shop's own record type a notification's subject and message are plain text and "
                "{{ doc.<field> }} only: no call, no filter, no {% %} block, and no one-line text ending "
                "in a file name (it would be read as a template file)",
            )
    for j, rcp in enumerate(n.get("recipients") or []):
        if isinstance(rcp, dict) and rcp.get("receiver_by_document_field"):
            v.refuse(
                f"{w}.recipients[{j}]",
                name,
                "on a shop's own record type a notification goes to a role: the manifest cannot know who the "
                "shop writes into a field of its record",
            )


def _recipient_field_is_user(v, doctype, value) -> bool:
    """The framework reads 'field' or 'field,table' (the field on the table's rows),
    so the field named must be a Link to User — the one kind whose value is a shop user, whatever a default, a
    fetch, a property setter, a workflow or the notification itself writes into it."""
    parts = [x.strip() for x in str(value).split(",")]
    if (
        parts[0] in ("owner", "modified_by") and len(parts) == 1
    ):  # set by the framework: always a user
        return True
    fields = {
        d.get("name"): {
            f.get("fieldname"): f for f in d.get("fields") or [] if isinstance(f, dict)
        }
        for d in v.m.get("doctypes") or []
        if isinstance(d, dict)
    }
    holder = fields.get(doctype) or {}
    if len(parts) == 2:
        table = holder.get(parts[1]) or {}
        holder = (
            fields.get(table.get("options")) or {} if table.get("fieldtype") == "Table" else {}
        )
    f = holder.get(parts[0]) or {}
    return len(parts) in (1, 2) and f.get("fieldtype") == "Link" and f.get("options") == "User"


_SCRIPT_RE = re.compile(r"<\s*(script|iframe|object|embed)\b|\bon[a-z]+\s*=|javascript\s*:", re.I)
# A field's display condition may name a field ("my_field"); "eval:…" is JavaScript the form runs in every viewer's
# browser — a client script by another name. Refused wherever a condition can be set.
DEPENDS_KEYS = {"depends_on", "mandatory_depends_on", "read_only_depends_on"}
# The one form allowed: a field name, or doc.<field> compared with a plain literal, joined by && / || — no call, no
# bracket, no parenthesis, no quote or backslash inside a string. Enough for "show this when that equals X" (S1 uses it).
_COND_TERM = r"doc\.[a-z][a-z0-9_]*(\s*(==|!=|===|!==)\s*('[^'\\\n]*'|\"[^\"\\\n]*\"|-?\d+(\.\d+)?|true|false|null))?"
_COND_RE = re.compile(
    rf"^(eval:\s*{_COND_TERM}(\s*(&&|\|\|)\s*{_COND_TERM})*\s*|[a-z][a-z0-9_]*)$"
)
EVAL_REASON = (
    "a display condition other than a field name or doc.<field> compared with a plain value is JavaScript "
    "that runs in the browser of everyone who opens the form"
)


# the version is required and compared as major.minor.patch, so an update can refuse
# a lower or equal one. The samples use "0.1.0".
_VERSION_RE = re.compile(r"^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$")
VERSION_REASON = "the version is required, as major.minor.patch (for example '0.1.0')"


def version_key(version: str) -> tuple:
    """'1.10.0' → (1, 10, 0): compared as numbers, never as text."""
    return tuple(int(x) for x in version.split("."))


def field_prefix(prefix: str) -> str:
    """'PP BLN' → 'pp_bln_': the prefix a manifest's fields carry on the shop's own record types."""
    return prefix.lower().replace(" ", "_") + "_"


def app_for(prefix: str) -> str:
    return prefix.lower().replace(" ", "_")


class _V:
    def __init__(self, m: dict):
        self.m, self.out = m, []
        self.prefix = m.get("prefix") if isinstance(m.get("prefix"), str) else ""
        self.fprefix = field_prefix(self.prefix) if self.prefix else "\0"
        self.own = {d.get("name") for d in m.get("doctypes") or [] if isinstance(d, dict)}
        self.tables = {
            d.get("name")
            for d in m.get("doctypes") or []
            if isinstance(d, dict) and d.get("istable")
        }
        self.own_fields = {
            (c.get("dt"), c.get("fieldname"))
            for c in m.get("custom_fields") or []
            if isinstance(c, dict)
        }
        self.urls = (
            set(m.get("allowed_urls") or []) if isinstance(m.get("allowed_urls"), list) else set()
        )
        self.results = _result_fields(m) if isinstance(m.get("fiscal_readers"), list) else set()

    def refuse(self, where: str, name, reason: str):
        self.out.append(
            {"where": where, "name": name if isinstance(name, str) else None, "reason": reason}
        )

    def named(self, where: str, name) -> bool:
        """Every name a manifest creates starts with its prefix — site names are shared and carry no owner."""
        if not isinstance(name, str) or not _NAME_RE.match(name):
            self.refuse(where, name, "the name is missing or uses characters a name may not use")
            return False
        if not self.prefix or not name.startswith(self.prefix + " "):
            self.refuse(
                where,
                name,
                f"every name a manifest creates must start with its prefix "
                f"'{self.prefix}' (names on a site are shared and carry no owner)",
            )
            return False
        return True

    def no_script(self, where: str, name, text):
        if isinstance(text, str) and _SCRIPT_RE.search(text):
            self.refuse(
                where, name, "markup carrying script runs in the browser of everyone who views it"
            )

    def list_of(self, key: str) -> list:
        v = self.m.get(key)
        if v is None:
            return []
        if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
            self.refuse(key, None, f"'{key}' must be a list of objects")
            return []
        return v


def _fields(
    v: _V, where: str, owner: str, fields: list, engine: bool, single: bool = False, limits=False
):
    for i, f in enumerate(fields):
        w = where if single else f"{where}[{i}]"
        if not isinstance(f, dict):
            v.refuse(w, None, "a field must be an object")
            continue
        fn, ft = f.get("fieldname"), f.get("fieldtype")
        extra = (
            set(f)
            - FIELD_KEYS
            - {"dt"}
            - (FISCAL_FIELD_KEYS if (owner, fn) in v.results else set())
            - (set(LIMIT_KEYS) if limits else set())
        )
        if extra:
            v.refuse(w, fn, f"keys a field may not carry here: {sorted(extra)}")
        if not isinstance(fn, str) or not _FIELD_RE.match(fn):
            v.refuse(w, fn, "a field name must be lower-case letters, digits and underscores")
        elif engine and not fn.startswith(v.fprefix):
            v.refuse(
                w, fn, f"a field added to a shop's own record type must start with '{v.fprefix}'"
            )
        if ft in REFUSED_FIELD_TYPES:
            v.refuse(w, fn, REFUSED_FIELD_TYPES[ft])
        elif ft not in FIELD_TYPES:
            v.refuse(w, fn, f"'{ft}' is not a field type a manifest may use")
        if ft == "Table" and f.get("options") not in v.tables:
            v.refuse(
                w, fn, "a table field must point at one of the manifest's own child record types"
            )
        if ft == "Table MultiSelect" and not (
            f.get("options") in v.tables
            and any(
                x.get("fieldtype") == "Link" and x.get("in_list_view")
                for x in _own_doctype(v, f.get("options"))
            )
        ):  # the framework's own rule, refused first in our words, and Desk's: a form
            # save drops every row none of whose fields is shown in the list (its form's save)
            v.refuse(
                w,
                fn,
                "a multi-select field points at one of the manifest's own child record types that has a "
                "Link field shown in the list (in_list_view: 1): each choice is a row holding one link, and "
                "Desk drops, when it saves, a row with no field shown in the list",
            )
        if engine and f.get("reqd"):
            v.refuse(w, fn, ENGINE_GUARDED_PROPS["reqd"])
        if engine:
            for k in sorted(set(f) & SAVE_ENFORCED):
                v.refuse(w, fn, f"'{k}' {SAVE_ENFORCED_REASON}")
        for k in sorted(set(f) & DEPENDS_KEYS):
            if not isinstance(f[k], str) or not _COND_RE.match(f[k].strip()):
                v.refuse(w, fn, EVAL_REASON)
        v.no_script(w, fn, f.get("description"))
        v.no_script(w, fn, f.get("label"))  # Desk writes a field's label raw too


def _doctypes(v: _V):
    for i, d in enumerate(v.list_of("doctypes")):
        w, name = f"doctypes[{i}]", d.get("name")
        v.named(w, name)
        for k in sorted(set(d) & set(REFUSED_DOCTYPE_KEYS)):
            if k in ("is_submittable", "issubmittable", "is_virtual") and not d.get(k):
                continue  # an explicit 0 is harmless
            v.refuse(f"{w}.{k}", name, REFUSED_DOCTYPE_KEYS[k])
        v.no_script(f"{w}.description", name, d.get("description"))  # the empty list shows it raw
        extra = set(d) - DOCTYPE_KEYS - set(REFUSED_DOCTYPE_KEYS)
        if extra:
            v.refuse(w, name, f"keys a record type may not carry here: {sorted(extra)}")
        if d.get("issingle"):
            _single(v, w, name, d)
        fields = d.get("fields")
        if not isinstance(fields, list) or not fields:
            v.refuse(w, name, "a record type needs at least one field")
        else:
            _fields(v, f"{w}.fields", name, fields, engine=False)
        for j, p in enumerate(d.get("permissions") or []):
            if not isinstance(p, dict) or not isinstance(p.get("role"), str):
                v.refuse(f"{w}.permissions[{j}]", name, "a permission row needs a role")
            elif _guest(p["role"]):
                v.refuse(
                    f"{w}.permissions[{j}]",
                    name,
                    "a manifest may not open its records to visitors who " "are not signed in",
                )
            elif _automatic(p["role"]):
                v.refuse(f"{w}.permissions[{j}]", name, AUTOMATIC_REASON)
            elif _odd(p["role"]):
                v.refuse(f"{w}.permissions[{j}]", name, PLAIN_ROLE_REASON)
            else:
                left = [r for r in RIGHTS if r not in p]
                if (
                    left
                ):  # the framework stores a right a row leaves out as ON (measured), so every row states all nine
                    v.refuse(
                        f"{w}.permissions[{j}]",
                        name,
                        f"a permission row leaves out {', '.join(left)}: a right left out is "
                        f"switched ON, so write all nine rights as 0 or 1",
                    )
                elif any(p[r] not in (0, 1) for r in RIGHTS):
                    v.refuse(
                        f"{w}.permissions[{j}]", name, "every right in a permission row is 0 or 1"
                    )


def _single(v: _V, w: str, name, d: dict):
    """A settings record of the manifest's own (``issingle: 1``)."""
    if d["issingle"] != 1:
        v.refuse(f"{w}.issingle", name, "issingle is 0 or 1")
    extra = set(d) - SINGLE_KEYS
    if extra:
        v.refuse(
            w,
            name,
            f"a settings record carries only {', '.join(sorted(SINGLE_KEYS))}, not {sorted(extra)} "
            "(it is one record: not a table of rows, with no list, naming or search)",
        )
    for j, f in enumerate(d.get("fields") if isinstance(d.get("fields"), list) else []):
        for k in sorted(set(f) & SINGLE_FIELD_KEYS if isinstance(f, dict) else ()):
            v.refuse(
                f"{w}.fields[{j}]",
                name,
                f"a settings record's field carries no '{k}': it has one record",
            )
    for j, p in enumerate(d.get("permissions") if isinstance(d.get("permissions"), list) else []):
        if isinstance(p, dict) and any(p.get(r) for r in SINGLE_RIGHTS):
            v.refuse(
                f"{w}.permissions[{j}]",
                name,
                "a settings record has no list to report on or export: report and export are 0",
            )


def _fold(name: str) -> str:
    return " ".join(name.split()).casefold()


def _singles(v: _V):
    """A settings record is named only where SINGLE_NAMERS allows (and by a workspace shortcut that opens its
    form). Every other kind is read whole, so a kind or a key added later is covered without a list to keep.
    """
    declared = sorted(
        d["name"]
        for d in v.m.get("doctypes") or []
        if isinstance(d, dict) and isinstance(d.get("name"), str) and d.get("issingle")
    )
    singles = {_fold(n) for n in declared}
    if not singles:
        return

    def names(x) -> bool:
        if isinstance(x, dict):
            return any(names(y) for y in x.values())
        if isinstance(x, list):
            return any(names(y) for y in x)
        return isinstance(x, str) and _fold(x) in singles  # the database finds a name in any case

    for kind in KINDS:
        items = v.m.get(kind)
        for i, el in enumerate(items if isinstance(items, list) else []):
            w = f"{kind}[{i}]"
            if not isinstance(el, dict) or SINGLE_NAMERS.get(kind, ()) is None:
                continue
            if (
                kind == "doctypes"
            ):  # the single's own declaration names itself; a field's options may not
                hits = [
                    f
                    for f in el.get("fields") or []
                    if isinstance(f, dict) and names(f.get("options"))
                ]
            elif (
                kind == "workspaces"
            ):  # a shortcut opens the form; any other view is a list it has not got
                hits = [
                    s
                    for s in el.get("shortcuts") or []
                    if isinstance(s, dict)
                    and names(s.get("link_to"))
                    and (s.get("type") != "DocType" or s.get("doc_view"))
                ]
            else:
                hits = (
                    [el]
                    if names({k: x for k, x in el.items() if k not in SINGLE_NAMERS.get(kind, ())})
                    else []
                )
            if hits:
                v.refuse(w, el.get("name"), f"'{', '.join(declared)}' {SINGLE_REASON}")


def _custom_fields(v: _V):
    for i, c in enumerate(v.list_of("custom_fields")):
        w, dt = f"custom_fields[{i}]", c.get("dt")
        if not isinstance(dt, str) or not dt:
            v.refuse(
                w, c.get("fieldname"), "a custom field must name the record type it is added to"
            )
            continue
        _fields(v, w, dt, [c], engine=dt not in v.own, single=True, limits=True)
        _limits(v, w, dt, c)


def _limits(v: _V, w: str, dt: str, c: dict):
    """``read_roles`` / ``write_roles`` on a field the manifest adds."""
    fn = c.get("fieldname")
    given = [k for k in LIMIT_KEYS if k in c]
    if not given:
        return
    for k in given:
        roles = c[k]
        if (
            not isinstance(roles, list)
            or not roles
            or any(not isinstance(r, str) or not r.strip() for r in roles)
            or len({_norm(r) for r in roles}) != len(roles)
        ):
            v.refuse(w, fn, f"{k} is a list of role names, each named once")
            continue
        for r in roles:
            if _guest(r):
                v.refuse(
                    w, fn, "a manifest may not open its records to visitors who are not signed in"
                )
            elif _automatic(r):
                v.refuse(w, fn, AUTOMATIC_REASON)
            elif _odd(r):
                v.refuse(w, fn, PLAIN_ROLE_REASON)
    if "write_roles" not in c:
        v.refuse(w, fn, LIMIT_WRITE_REASON)
    if c.get("reqd") or c.get("mandatory_depends_on"):
        v.refuse(w, fn, LIMIT_REQUIRED_REASON)
    if c.get("fieldtype") in LIMIT_NO_VALUE:
        v.refuse(w, fn, "a layout or table field holds no value to limit to roles")
    if (dt, fn) in v.results:
        v.refuse(
            w,
            fn,
            "a fiscal reader's result field sits at the reader's writer_level; its writer role is the "
            "reader's",
        )


def _limited_in_templates(v: _V):
    """Nothing else the manifest ships may name a field it limits to readers (a field
    everyone reads but only some change may be printed): a print format, a notification, a
    report, a number card or a chart on that record type prints, sends or counts it for whoever
    looks, and a ``fetch_from`` copies it into a field everyone reads."""
    read_limited = {
        (c.get("dt"), c.get("fieldname"))
        for c in v.m.get("custom_fields") or []
        if isinstance(c, dict) and "read_roles" in c and isinstance(c.get("fieldname"), str)
    }
    if not read_limited:
        return
    names = {fn for _, fn in read_limited}
    # on ANY record type: a template on a sale can read the customer's field (fieldnames carry the
    # manifest's prefix, so a hit is the manifest's own field)
    for kind in ("print_formats", "notifications", "reports", "number_cards", "dashboard_charts"):
        for i, x in enumerate(v.m.get(kind) or []):
            if not isinstance(x, dict):
                continue
            text = json.dumps(x)
            for fn in sorted(names):
                if re.search(rf"\b{re.escape(fn)}\b", text):
                    v.refuse(f"{kind}[{i}]", x.get("name"), LIMIT_TEMPLATE_REASON.format(fn))
    fields = [(f"custom_fields[{i}]", c) for i, c in enumerate(v.m.get("custom_fields") or [])]
    for i, d in enumerate(v.m.get("doctypes") or []):
        if isinstance(d, dict) and isinstance(d.get("fields"), list):
            fields += [(f"doctypes[{i}].fields[{j}]", f) for j, f in enumerate(d["fields"])]
    for w, f in fields:
        source = f.get("fetch_from") if isinstance(f, dict) else None
        if isinstance(source, str) and source.rpartition(".")[2].strip() in names:
            v.refuse(w, f.get("fieldname"), LIMIT_FETCH_REASON.format(source.rpartition(".")[2]))


def _property_setters(v: _V):
    for i, p in enumerate(v.list_of("property_setters")):
        w, dt, fn, prop = (
            f"property_setters[{i}]",
            p.get("doc_type"),
            p.get("field_name"),
            p.get("property"),
        )
        label = f"{dt}-{fn or ''}-{prop}"
        if not isinstance(dt, str) or not isinstance(prop, str) or "value" not in p:
            v.refuse(w, label, "a property setter needs doc_type, property and value")
            continue
        if prop in DEPENDS_KEYS and not _COND_RE.match(str(p["value"]).strip()):
            v.refuse(w, label, EVAL_REASON)
            continue
        if prop in HELP_PROPS and not help_address_ok(p["value"]):
            v.refuse(w, label, HELP_REASON)
            continue
        # Desk writes several setter values raw (a field's description and label, a record type's
        # description), so every setter is checked as the text the installer stores, str(value)
        if _SCRIPT_RE.search(str(p["value"])):
            v.no_script(w, label, str(p["value"]))
            continue
        if dt in v.own:
            _own_setter(v, w, label, dt, fn, prop, p["value"])
            continue
        if prop in ENGINE_GUARDED_PROPS:
            v.refuse(w, label, ENGINE_GUARDED_PROPS[prop])
        elif not (isinstance(fn, str) and fn.startswith(v.fprefix) and (dt, fn) in v.own_fields):
            v.refuse(
                w,
                label,
                "on a shop's own record type a manifest may only change the fields it adds itself",
            )
        elif prop in SAVE_ENFORCED:
            v.refuse(w, label, f"'{prop}' {SAVE_ENFORCED_REASON}")
        elif prop not in ENGINE_DISPLAY_PROPS:
            v.refuse(
                w,
                label,
                f"on a shop's own record type a manifest may only change how its own field is shown, "
                f"not '{prop}'",
            )


def _own_setter(v: _V, w: str, label: str, dt: str, fn, prop: str, value):
    """A property setter on the manifest's own record type: no more than the manifest could set there."""
    single = dt in {
        d.get("name")
        for d in v.m.get("doctypes") or []
        if isinstance(d, dict) and d.get("issingle")
    }
    if fn:
        if prop not in OWN_FIELD_SETTER_PROPS or single and prop in SINGLE_FIELD_KEYS:
            v.refuse(
                w,
                label,
                f"on its own record type's field a property setter may only change how the field "
                f"is shown; change '{prop}' in the record type itself",
            )
        return
    if prop in REFUSED_DOCTYPE_KEYS:
        v.refuse(w, label, REFUSED_DOCTYPE_KEYS[prop])
    elif single and prop not in SINGLE_SETTER_PROPS:  # no more than the settings record may carry
        v.refuse(
            w,
            label,
            f"on a settings record a property setter may set only {', '.join(sorted(SINGLE_SETTER_PROPS))}",
        )
    elif prop not in OWN_DOCTYPE_SETTER_PROPS:
        v.refuse(
            w,
            label,
            f"on its own record type a property setter may not change '{prop}': it may set "
            f"{', '.join(sorted(OWN_DOCTYPE_SETTER_PROPS))}",
        )
    elif prop in OWN_DOCTYPE_SETTER_VALUES:
        text, names = str(value), _own_fields(v, dt)
        named = re.split(r"\s*,\s*", text) if prop == "search_fields" else [text]
        if not OWN_DOCTYPE_SETTER_VALUES[prop].fullmatch(text) or (
            prop in ("title_field", "sort_field", "search_fields")
            and any(x not in names for x in named)
        ):
            v.refuse(
                w,
                label,
                f"'{value}' is not a value '{prop}' may take: {OWN_DOCTYPE_SETTER_HINTS[prop]}",
            )


def _print_formats(v: _V):
    for i, p in enumerate(v.list_of("print_formats")):
        w, name = f"print_formats[{i}]", p.get("name")
        v.named(w, name)
        if not isinstance(p.get("doc_type"), str):
            v.refuse(w, name, "a print format must name its record type")
        lang = p.get("default_print_language")
        if lang is not None and not (isinstance(lang, str) and _LANG_RE.match(lang)):
            # the language it prints in (§15 R-6: the core sets the page's direction from it); the
            # site's own Language record is checked at install
            v.refuse(w, name, "default_print_language is a language code, such as ar or pt-BR")
        if p.get("print_format_type", "Jinja") != "Jinja":
            v.refuse(
                w,
                name,
                "only template print formats; a script print format runs in the viewer's browser",
            )
        for k in ("html", "css"):
            v.no_script(f"{w}.{k}", name, p.get(k))
            outside = isinstance(p.get(k), str) and _OUTSIDE_URL_RE.search(p[k])
            if outside:
                v.refuse(
                    f"{w}.{k}",
                    name,
                    "a print format may not load anything from outside the shop: an address in a "
                    "receipt can carry the shop's data out; embed images as files or data: URIs",
                )
            if isinstance(p.get(k), str) and _PRINT_RAW_RE.search(p[k]):
                v.refuse(
                    f"{w}.{k}",
                    name,
                    "a print format may not run raw database queries or fetch from outside: read other "
                    "records through ivn_rows and ivn_value, with the viewer's rights",
                )
            if (
                not outside and isinstance(p.get(k), str) and _templated_address(p[k])
            ):  # one reason an address
                v.refuse(
                    f"{w}.{k}",
                    name,
                    "an address a print format loads may hold only a whole {{ a.b }} reference, never a "
                    "template built around it: a built address can carry the viewer's data out",
                )
            for rt in _served_reads(p.get(k)):
                v.refuse(
                    f"{w}.{k}",
                    name,
                    f"a print format may not read {rt} through the framework's own helpers, which skip "
                    "the viewer's rights (a share-key visitor would see what they return): read it "
                    "through ivn_rows or ivn_value, or show the printed record's own fields",
                )


def _served_reads(text) -> list[str]:
    """The record types ivn_rows serves that a print reads through a framework helper, once each."""
    served = {t.casefold(): t for t in PRINT_SERVED_TYPES}
    out = []
    for m in _PRINT_TYPED_READ_RE.finditer(text if isinstance(text, str) else ""):
        rt = served.get((m.group(1) if m.group(1) is not None else m.group(2)).strip().casefold())
        if rt and rt not in out:
            out.append(rt)
    return out


def _templated_address(text: str) -> bool:
    for m in _ADDRESS_RE.finditer(text):
        value = next((g for g in m.groups() if g is not None), "")
        templated = "{{" in value or "{%" in value or "{#" in value
        if templated and not _PLAIN_REFERENCE_RE.match(value):
            return True
    return False


def _print_format_warnings(m: dict) -> list[dict]:
    pfs = m.get("print_formats")
    out = []
    for i, p in enumerate(pfs if isinstance(pfs, list) else []):
        for k in ("html", "css"):
            if isinstance(p, dict) and isinstance(p.get(k), str) and _PRINT_READER_RE.search(p[k]):
                out.append(
                    {
                        "what": "framework_reader",
                        "where": f"print_formats[{i}].{k}",
                        "text": PRINT_READER_WARNING,
                    }
                )
    return out


def _notifications(v: _V):
    for i, n in enumerate(v.list_of("notifications")):
        w, name = f"notifications[{i}]", n.get("name")
        v.named(w, name)
        if n.get("channel", "Email") not in NOTIFY_CHANNELS:
            v.refuse(
                w,
                name,
                "a notification may only use e-mail or the in-app bell; other channels send to an "
                "outside service",
            )
        if n.get("event") not in NOTIFY_EVENTS:
            v.refuse(
                w, name, f"'{n.get('event')}' is not an event a manifest notification may use"
            )
        shop = n.get("document_type") not in v.own
        if shop and n.get("event") not in DATE_EVENTS:
            v.refuse(w, name, NOTIFY_SHOP_EVENT_REASON)
        elif shop:
            _date_notification(v, w, name, n)
        for k in ATTACH_FILE_KEYS:
            if k in n:
                v.refuse(f"{w}.{k}", name, ATTACH_FILE_REASON)
        extra = set(n) - NOTIFY_KEYS - set(ATTACH_FILE_KEYS)
        if extra:
            v.refuse(w, name, f"keys a manifest notification may not set: {sorted(extra)}")
        if "attach_print" in n or "print_format" in n:
            _attach_print(v, w, name, n, shop)
        v.no_script(f"{w}.message", name, n.get("message"))
        for k in ("subject", "message"):
            if isinstance(n.get(k), str) and _SHOP_DATA_RE.search(n[k]):
                v.refuse(
                    f"{w}.{k}",
                    name,
                    "a notification shows its own record's fields only; it may not read the shop's "
                    "other data (it can be sent out of the shop)",
                )
        if "condition" in n:
            v.refuse(w, name, NOTIFY_CONDITION_REASON)
        for j, rcp in enumerate(n.get("recipients") or []):
            if isinstance(rcp, dict) and "condition" in rcp:
                v.refuse(f"{w}.recipients[{j}]", name, NOTIFY_CONDITION_REASON)
                continue
            if isinstance(rcp, dict) and rcp.get("receiver_by_document_field") and not shop:
                if not _recipient_field_is_user(
                    v, n.get("document_type"), rcp["receiver_by_document_field"]
                ):
                    v.refuse(f"{w}.recipients[{j}]", name, NOTIFY_FIELD_REASON)
            if not isinstance(rcp, dict) or set(rcp) - {
                "receiver_by_role",
                "receiver_by_document_field",
            }:
                v.refuse(
                    f"{w}.recipients[{j}]",
                    name,
                    "a notification goes to the shop's own people — by role, or by a "
                    "field of the record — never to an address the manifest names",
                )
            elif rcp.get("receiver_by_role"):  # falsy = the framework ignores it too
                _roles(
                    v, f"{w}.recipients[{j}]", name, [rcp["receiver_by_role"]]
                )  # the sixth place a role is named


def _attach_print(v: _V, w: str, name, n: dict, shop: bool):
    """A notification on the manifest's own record type may attach one of its own print formats for
    that record type; the format reads no framework helper, because the attached print is rendered with no rights.
    """
    if n.get("attach_print") not in (0, 1, None):
        v.refuse(f"{w}.attach_print", name, "attach_print is 0 or 1")
    pf = next(
        (
            p
            for p in v.m.get("print_formats") or []
            if isinstance(p, dict)
            and p.get("name") == n.get("print_format")
            and p.get("doc_type") == n.get("document_type")
        ),
        None,
    )
    if shop or pf is None and (n.get("attach_print") or "print_format" in n):
        v.refuse(f"{w}.print_format", name, ATTACH_PRINT_REASON)
    elif pf and any(
        isinstance(pf.get(k), str)
        and (
            _SHOP_DATA_RE.search(pf[k])
            or _PRINT_READER_RE.search(pf[k])
            or _TEMPLATE_LOAD_RE.search(pf[k])
        )
        for k in ("html", "css")
    ):
        v.refuse(f"{w}.print_format", name, ATTACH_READER_REASON)


_ICON_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
# Desk runs a shortcut's stats_filter as JavaScript (utils.process_filter_expression, new Function)
# and writes its label, format and color raw — so a shortcut carries these keys only, and a plain label
SHORTCUT_KEYS = {"type", "link_to", "url", "label", "doc_view"}
# the framework's Workspace Shortcut doc_view options (workspace_shortcut.json at 83a8bd1d09), blank allowed
SHORTCUT_VIEWS = ("", "List", "Report Builder", "Dashboard", "Tree", "New", "Calendar", "Kanban")


def _workspaces(v: _V):
    for i, ws in enumerate(v.list_of("workspaces")):
        w, name = f"workspaces[{i}]", ws.get("name")
        v.named(w, name)
        # Desk writes the icon into an unquoted attribute and an href, raw
        icon = ws.get("icon")
        if "icon" in ws and not (
            isinstance(icon, str) and len(icon) <= 40 and _ICON_RE.fullmatch(icon)
        ):
            v.refuse(
                f"{w}.icon",
                name,
                "a workspace icon is an icon's name: lower-case letters, digits and -",
            )
        for j, b in enumerate(ws.get("blocks") or []):
            bw = f"{w}.blocks[{j}]"
            kind = b.get("type") if isinstance(b, dict) else None
            if kind == "custom_block":
                v.refuse(
                    bw,
                    name,
                    "a custom block carries script that runs in the browser of everyone who opens "
                    "the workspace, administrators included",
                )
            elif kind not in WORKSPACE_BLOCKS:
                v.refuse(bw, name, f"'{kind}' is not a workspace block a manifest may use")
            else:
                v.no_script(bw, name, json.dumps(b.get("data") or {}))
        for j, s in enumerate(ws.get("shortcuts") or []):
            sw = f"{w}.shortcuts[{j}]"
            target = (
                (s.get("url") if s.get("type") == "URL" else s.get("link_to"))
                if isinstance(s, dict)
                else None
            )
            if not isinstance(s, dict) or s.get("type") not in SHORTCUT_TYPES or not target:
                v.refuse(
                    sw,
                    name,
                    "a shortcut needs a label, a type (record type, report or address) and a target "
                    "(link_to, or url for an address)",
                )
            elif s["type"] == "URL" and target not in v.urls:
                v.refuse(sw, name, "a shortcut may only open an address the manifest lists")
            elif set(s) - SHORTCUT_KEYS:
                v.refuse(
                    sw,
                    name,
                    "a shortcut carries only type, link_to, url, label and doc_view (a stats "
                    "filter, for one, runs as script in every viewer's browser)",
                )
            elif not (isinstance(s.get("label"), str) and s["label"].strip()) or set(
                s["label"]
            ) & set('<>"&'):
                v.refuse(sw, name, 'a shortcut needs a label in plain text, with no <, >, " or &')
            elif "doc_view" in s and s["doc_view"] not in SHORTCUT_VIEWS:
                v.refuse(sw, name, f"a shortcut's doc_view is one of: {', '.join(SHORTCUT_VIEWS)}")


def _sale_attributes(v: _V):
    for i, a in enumerate(v.list_of("sale_attributes")):
        w, name = f"sale_attributes[{i}]", a.get("name")
        v.named(w, name)
        if a.get("required"):
            v.refuse(
                w,
                name,
                "a required sale detail would stop every sale on every till that does not fill it",
            )


def _webhooks(v: _V):
    for i, h in enumerate(v.list_of("webhooks")):
        w, name = f"webhooks[{i}]", h.get("name")
        v.named(w, name)
        if not isinstance(h.get("doctype"), str) or not isinstance(h.get("event"), str):
            v.refuse(w, name, "a webhook must name its record type and event")
        if h.get("url") not in v.urls:
            v.refuse(
                w, name, "a webhook may only call an address the manifest lists in allowed_urls"
            )
        if h.get("condition") and h.get("doctype") not in v.own:
            v.refuse(
                w,
                name,
                "a webhook condition on a shop's own record type is evaluated inside every save of it, "
                "a till sale included, and an error in it stops that save; filter in your own service",
            )
        if "secret" in h or "webhook_secret" in h:
            v.refuse(
                w,
                name,
                "a manifest carries no secret; the installer makes one and hands it to the partner",
            )
        if "json" in h:
            v.refuse(
                w,
                name,
                "a webhook sends the fixed, thin body only (record type, name, event, time): your service "
                "reads the record with its own key, which is what the shop granted it",
            )
        extra = set(h) - {
            "name",
            "doctype",
            "event",
            "url",
            "condition",
            "timeout",
            "json",
            "secret",
            "webhook_secret",
        }
        if extra:
            v.refuse(w, name, f"keys a webhook may not carry: {sorted(extra)}")


# ── v2 kinds ─────────────────────────────────────────────────────────────────


def _keys(v: _V, w: str, name, obj: dict, allowed: set):
    extra = set(obj) - allowed
    if extra:
        v.refuse(w, name, f"keys this kind may not carry: {sorted(extra)}")


def _own_doctype(v: _V, dt: str) -> list:
    """The fields a manifest gives its own record type ``dt``."""
    d = next(
        (d for d in v.m.get("doctypes") or [] if isinstance(d, dict) and d.get("name") == dt), None
    )
    return [f for f in (d or {}).get("fields") or [] if isinstance(f, dict)]


def _own_fields(v: _V, dt: str) -> set:
    return {f.get("fieldname") for f in _own_doctype(v, dt)} | STD_FIELDS


def _filters(v: _V, w: str, name, filters, field_re=_FIELD_RE):
    """Filters are data: [[field, operator, value], …]. Operators from a fixed list; values plain scalars."""
    ops = {"=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "is", "between"}
    if filters is None:
        return
    if not isinstance(filters, list) or any(
        not isinstance(f, list)
        or len(f) != 3
        or f[1] not in ops
        or not isinstance(f[0], str)
        or not field_re.match(f[0])
        or isinstance(f[2], (dict, list))
        and f[1] not in ("in", "not in", "between")
        for f in filters
    ):
        v.refuse(w, name, "filters are a list of [field, operator, value] with a plain operator")


# P-REPORTCOLS: a report's column or filter is `field` or `table.field` — one table of the record type
_COLUMN_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}(\.[a-z][a-z0-9_]{0,62})?$")
NUMBER_TYPES = {
    "Int",
    "Float",
    "Currency",
    "Percent",
    "Duration",
}  # what Desk's totals row adds
ONE_TABLE_REASON = "a column from a table is table.field, one table per report: two tables multiply each other's rows"


def report_names(r: dict) -> list:
    """The field names a report's columns and filters read, as written."""
    filters = r.get("filters") if isinstance(r.get("filters"), list) else []
    return [
        c
        for c in (r.get("columns") if isinstance(r.get("columns"), list) else [])
        + [f[0] for f in filters if isinstance(f, list) and f]
        if isinstance(c, str)
    ]


def report_tables(r: dict) -> set:
    """The tables a report reads rows from (more than one is refused)."""
    return {c.split(".")[0] for c in report_names(r) if "." in c}


def report_table_refusals(r: dict, dt: str, fields: list, rows) -> list:
    """What a report reading one table owes, one rule for both homes: the checker passes a package's
    own record type, the installer the shop's. ``fields`` are the record type's fields (fieldname, fieldtype,
    options, permlevel); ``rows`` the names of the table's row fields, or None when they are checked elsewhere.
    Desk's report screen names a row column by its record type alone (its field list for the report), so it joins
    rows by parent and record type: rows two tables share would mix, a record type with a - is not read as a
    row column, and the table field's own permission level is not checked."""
    if len(report_tables(r)) != 1:
        return []
    (t,) = report_tables(r)
    by = {f.get("fieldname"): f for f in fields if isinstance(f, dict)}
    if (by.get(t) or {}).get("fieldtype") != "Table":
        return [f"{t} is not a table of {dt}"]
    rows_dt, out = by[t].get("options") or "", []
    if any(
        f.get("fieldtype") == "Table" and f.get("options") == rows_dt and n != t
        for n, f in by.items()
    ):
        out.append(
            f"{t}'s rows share their record type with another table of {dt}: Desk's report screen "
            "joins rows by their record type, so it would mix them"
        )
    if "-" in rows_dt:
        out.append(
            f"Desk's report screen cannot show a column from {rows_dt}: a record type with a - in its name"
        )
    if by[t].get("permlevel") not in (
        None,
        0,
        "0",
        "",
    ):  # a malformed level is refused by its own rule
        out.append(
            f"{t} of {dt} sits behind a permission level, which Desk's report screen does not check "
            "for a table's rows: leave its rows out"
        )
    if rows is not None:
        missing = {c.split(".")[1] for c in report_names(r) if "." in c} - set(rows) - STD_FIELDS
        out += [f"{f} is not a field of {t}'s rows" for f in sorted(missing)]
    if r.get("add_total_row"):
        out += [
            f"with a table's rows and a totals row, {c} of the document would be added once per line: "
            "leave it out or drop the totals row"
            for c in report_names({"columns": r.get("columns")})
            if "." not in c and (by.get(c) or {}).get("fieldtype") in NUMBER_TYPES
        ]
    return out


REPORT_KEYS = {
    "name",
    "ref_doctype",
    "columns",
    "filters",
    "order_by",
    "roles",
    "add_total_row",
    "report_type",
}


def _reports(v: _V):
    for i, r in enumerate(v.list_of("reports")):
        w, name = f"reports[{i}]", r.get("name")
        v.named(w, name)
        _keys(v, w, name, r, REPORT_KEYS)
        kind = r.get("report_type", "Report Builder")
        if kind == "Query Report":
            v.refuse(
                w,
                name,
                "a query report is SQL text run against the shop's whole database; use Report Builder",
            )
        elif kind == "Script Report":
            v.refuse(w, name, "a script report is Python run inside the shop; use Report Builder")
        elif kind != "Report Builder":
            v.refuse(w, name, f"'{kind}' is not a report type a manifest may use")
        if not isinstance(r.get("ref_doctype"), str):
            v.refuse(w, name, "a report must name its record type (ref_doctype)")
        cols = r.get("columns")
        if (
            not isinstance(cols, list)
            or not cols
            or any(not isinstance(c, str) or not _COLUMN_RE.match(c) for c in cols)
        ):
            v.refuse(w, name, "columns is a list of field names (a table's column is table.field)")
        elif r.get("ref_doctype") in v.own and {c for c in cols if "." not in c} - _own_fields(
            v, r["ref_doctype"]
        ):
            plain = {c for c in cols if "." not in c}
            v.refuse(
                w,
                name,
                f"columns not on {r['ref_doctype']}: {sorted(plain - _own_fields(v, r['ref_doctype']))}",
            )
        _filters(v, w, name, r.get("filters"), _COLUMN_RE)
        if len(report_tables(r)) > 1:
            v.refuse(w, name, ONE_TABLE_REASON)
        elif (
            r.get("ref_doctype") in v.own
        ):  # the shop's record types: at install (manifest_install)
            fields = _own_doctype(v, r["ref_doctype"])
            t = next(iter(report_tables(r)), None)
            rows_dt = next((f.get("options") for f in fields if f.get("fieldname") == t), None)
            rows = _own_fields(v, rows_dt) if rows_dt in v.own else None
            for why in report_table_refusals(r, r["ref_doctype"], fields, rows):
                v.refuse(w, name, why)
        ob = r.get("order_by")
        if ob is not None and not (
            isinstance(ob, str) and re.match(r"^[a-z][a-z0-9_]{0,62}( (asc|desc))?$", ob)
        ):
            v.refuse(w, name, "order_by is one field name, optionally followed by asc or desc")
        _roles(v, w, name, r.get("roles"))


def _roles(v: _V, w, name, roles):
    if roles is None:
        return
    if not isinstance(roles, list) or any(not isinstance(x, str) for x in roles):
        v.refuse(w, name, "roles is a list of role names")
    elif any(_guest(x) for x in roles):
        v.refuse(w, name, "a manifest may not open anything to visitors who are not signed in")
    elif any(_automatic(x) for x in roles):
        v.refuse(w, name, AUTOMATIC_REASON)
    elif any(_odd(x) for x in roles):
        v.refuse(w, name, PLAIN_ROLE_REASON)


CARD_KEYS = {
    "name",
    "document_type",
    "function",
    "aggregate_function_based_on",
    "filters",
    "color",
    "type",
    "is_public",
    "show_percentage_stats",
    "stats_time_interval",
}
CARD_FUNCTIONS = {"Count", "Sum", "Average", "Minimum", "Maximum"}


def _number_cards(v: _V):
    for i, c in enumerate(v.list_of("number_cards")):
        w, name = f"number_cards[{i}]", c.get("name")
        v.named(w, name)
        _keys(v, w, name, c, CARD_KEYS)
        kind = c.get("type", "Document Type")
        if kind == "Custom":
            v.refuse(
                w,
                name,
                "a custom number card calls a server method; a manifest's card counts records",
            )
        elif kind != "Document Type":
            v.refuse(
                w,
                name,
                f"'{kind}' number cards are not supported by this installer; use 'Document Type'",
            )
        if not isinstance(c.get("document_type"), str):
            v.refuse(w, name, "a number card must name its record type")
        fn = c.get("function", "Count")
        if fn not in CARD_FUNCTIONS:
            v.refuse(w, name, f"'{fn}' is not a number-card function")
        if (
            fn in CARD_FUNCTIONS
            and fn != "Count"
            and not isinstance(c.get("aggregate_function_based_on"), str)
        ):
            v.refuse(
                w,
                name,
                "a Sum/Average/Minimum/Maximum card names its field (aggregate_function_based_on)",
            )
        _named_fields(v, w, name, c, ("aggregate_function_based_on",))
        _filters(v, w, name, c.get("filters"))


CHART_KEYS = {
    "name",
    "document_type",
    "chart_type",
    "based_on",
    "value_based_on",
    "group_by_based_on",
    "group_by_type",
    "aggregate_function_based_on",
    "timespan",
    "time_interval",
    "type",
    "filters",
    "color",
    "number_of_groups",
    "is_public",
    "roles",
}


def _named_fields(v: _V, w, name, obj, keys):
    """A field a card or chart reads: a plain field name, and on the manifest's own type one of its fields."""
    dt = obj.get("document_type")
    for k in keys:
        f = obj.get(k)
        if f is None:
            continue
        if (
            not isinstance(f, str)
            or not _FIELD_RE.match(f)
            or (dt in v.own and f not in _own_fields(v, dt))
        ):
            v.refuse(w, name, f"{k} must be a field of {dt}")


def _dashboard_charts(v: _V):
    for i, c in enumerate(v.list_of("dashboard_charts")):
        w, name = f"dashboard_charts[{i}]", c.get("name")
        v.named(w, name)
        _keys(v, w, name, c, CHART_KEYS)
        ct = c.get("chart_type")
        if ct == "Custom":
            v.refuse(
                w,
                name,
                "a custom chart's data comes from a server method; a manifest's chart reads records",
            )
        elif ct == "Report":
            v.refuse(
                w,
                name,
                "a report chart is not supported by this installer; chart the record type directly",
            )
        elif ct not in ("Count", "Sum", "Average", "Group By"):
            v.refuse(w, name, "chart_type is Count, Sum, Average or Group By")
        if not isinstance(c.get("document_type"), str):
            v.refuse(w, name, "a chart must name its record type")
        if ct in ("Count", "Sum", "Average") and not isinstance(c.get("based_on"), str):
            v.refuse(w, name, "a time-series chart names its date field (based_on)")
        if ct == "Group By" and not isinstance(c.get("group_by_based_on"), str):
            v.refuse(w, name, "a group-by chart names its field (group_by_based_on)")
        _named_fields(
            v,
            w,
            name,
            c,
            ("based_on", "value_based_on", "group_by_based_on", "aggregate_function_based_on"),
        )
        if c.get("type", "Line") not in ("Line", "Bar", "Percentage", "Pie", "Donut"):
            v.refuse(w, name, "type is Line, Bar, Percentage, Pie or Donut")
        _filters(v, w, name, c.get("filters"))
        _roles(v, w, name, c.get("roles"))


def _dashboards(v: _V):
    charts = {c.get("name") for c in v.m.get("dashboard_charts") or [] if isinstance(c, dict)}
    cards = {c.get("name") for c in v.m.get("number_cards") or [] if isinstance(c, dict)}
    for i, d in enumerate(v.list_of("dashboards")):
        w, name = f"dashboards[{i}]", d.get("name")
        v.named(w, name)
        _keys(v, w, name, d, {"name", "charts", "cards"})
        if not isinstance(d.get("charts"), list) or not d["charts"]:
            v.refuse(w, name, "a dashboard holds at least one chart")
        for k, own in (("charts", charts), ("cards", cards)):
            for x in d.get(k) or []:
                if not isinstance(x, str) or x not in own:
                    v.refuse(
                        w,
                        name,
                        f"a dashboard may only hold the manifest's own {k}: '{x}' is not one",
                    )


LIST_KEYS = {
    "doctype",
    "fields",
    "disable_count",
    "disable_sidebar_stats",
    "disable_comment_count",
    "disable_auto_refresh",
    "total_fields",
}


def _list_settings(v: _V):
    for i, ls in enumerate(v.list_of("list_settings")):
        w, dt = f"list_settings[{i}]", ls.get("doctype")
        _keys(v, w, dt, ls, LIST_KEYS)
        if dt not in v.own:
            v.refuse(
                w,
                dt,
                "a record type has one list setting, the shop's own; a manifest sets it on its own record "
                "types only (show its own fields on a shop's list with in_list_view instead)",
            )
            continue
        flds = ls.get("fields") or []
        if not isinstance(flds, list) or set(flds) - _own_fields(v, dt):
            v.refuse(w, dt, "fields is a list of the record type's own field names")


WF_KEYS = {"name", "document_type", "states", "transitions", "send_email_alert", "override_status"}
WF_STATE_KEYS = {
    "state",
    "allow_edit",
    "update_field",
    "update_value",
    "style",
    "message",
    "doc_status",
}
WF_TRANSITION_KEYS = {"state", "action", "next_state", "allowed", "allow_self_approval"}
_STATE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 \-]{0,60}$")


def _workflows(v: _V):
    for i, wf in enumerate(v.list_of("workflows")):
        w, name = f"workflows[{i}]", wf.get("name")
        v.named(w, name)
        _keys(v, w, name, wf, WF_KEYS)
        dt = wf.get("document_type")
        if dt not in v.own:
            v.refuse(
                w,
                name,
                "a workflow on a shop's own record type changes how every user and the till save it; a "
                "manifest's workflows run on its own record types (approvals by workflow)",
            )
            continue
        if dt in v.tables:
            v.refuse(w, name, "a workflow runs on a record type, not a child table")
            continue
        states = wf.get("states")
        if not isinstance(states, list) or len(states) < 2:
            v.refuse(w, name, "a workflow has at least two states")
            continue
        names = set()
        for j, st in enumerate(states):
            sw = f"{w}.states[{j}]"
            if not isinstance(st, dict):
                v.refuse(sw, name, "a state is an object")
                continue
            _keys(v, sw, name, st, WF_STATE_KEYS)
            if not isinstance(st.get("state"), str) or not _STATE_RE.match(st["state"]):
                v.refuse(sw, name, "a state needs a plain name")
            names.add(st.get("state"))
            if st.get("doc_status", 0) not in (0, "0"):
                v.refuse(
                    sw,
                    name,
                    "a manifest's workflow never submits or cancels: every state keeps the record a draft "
                    "(its record types are not submittable)",
                )
            if not isinstance(st.get("allow_edit"), str):
                v.refuse(sw, name, "a state names the role that may edit in it (allow_edit)")
            elif _guest(st["allow_edit"]):
                v.refuse(
                    sw, name, "a manifest may not open anything to visitors who are not signed in"
                )
            elif _automatic(st["allow_edit"]):
                v.refuse(sw, name, AUTOMATIC_REASON)
            elif _odd(st["allow_edit"]):
                v.refuse(sw, name, PLAIN_ROLE_REASON)
            if (
                st.get("update_field")
                and st["update_field"] not in _own_fields(v, dt or "") - STD_FIELDS
            ):
                v.refuse(
                    sw,
                    name,
                    "update_field must be one of the record type's own fields (never a standard one "
                    "such as docstatus or owner)",
                )
        trs = wf.get("transitions")
        if not isinstance(trs, list) or not trs:
            v.refuse(w, name, "a workflow has at least one transition")
            trs = []
        for j, t in enumerate(trs):
            tw = f"{w}.transitions[{j}]"
            if not isinstance(t, dict):
                v.refuse(tw, name, "a transition is an object")
                continue
            if "condition" in t:
                v.refuse(
                    tw,
                    name,
                    "a transition condition is an expression evaluated on the server; a manifest "
                    "carries none (use a role per transition)",
                )
            _keys(v, tw, name, t, WF_TRANSITION_KEYS | {"condition"})
            for k in ("state", "next_state"):
                if t.get(k) not in names:
                    v.refuse(tw, name, f"{k} '{t.get(k)}' is not one of the workflow's states")
            if not isinstance(t.get("action"), str) or not _STATE_RE.match(t["action"]):
                v.refuse(tw, name, "a transition needs a plain action name")
            if not isinstance(t.get("allowed"), str) or _guest(t.get("allowed")):
                v.refuse(tw, name, "a transition names the role allowed to take it (not Guest)")
            elif _automatic(t["allowed"]):
                v.refuse(tw, name, AUTOMATIC_REASON)
            elif _odd(t["allowed"]):
                v.refuse(tw, name, PLAIN_ROLE_REASON)


NAMING_KEYS = {"document_type", "prefix", "prefix_digits", "priority", "conditions"}


def _naming_rules(v: _V):
    for i, n in enumerate(v.list_of("naming_rules")):
        w, dt = f"naming_rules[{i}]", n.get("document_type")
        _keys(v, w, dt, n, NAMING_KEYS)
        if dt not in v.own:
            v.refuse(
                w,
                dt,
                "numbering a shop's own records — a sale's number included — is the shop's (and its "
                "fiscal rules'); a manifest numbers its own record types only",
            )
        if not isinstance(n.get("prefix"), str) or not re.match(
            r"^[A-Z0-9][A-Z0-9.\-/]{0,30}$", n["prefix"]
        ):
            v.refuse(w, dt, "prefix is upper-case letters, digits and . - / (e.g. 'WRC-.YYYY.-')")
        if (
            not isinstance(n.get("prefix_digits", 5), int)
            or not 1 <= n.get("prefix_digits", 5) <= 10
        ):
            v.refuse(w, dt, "prefix_digits is 1 to 10")
        for j, c in enumerate(n.get("conditions") or []):
            if (
                not isinstance(c, dict)
                or c.get("field") not in _own_fields(v, dt or "")
                or c.get("condition") not in ("=", "!=", ">", "<", ">=", "<=")
                or not isinstance(c.get("value"), str)
            ):
                v.refuse(
                    f"{w}.conditions[{j}]",
                    dt,
                    "a condition is {field (own), condition (= != > < >= <=), value}",
                )


def _links(v: _V):
    for i, ln in enumerate(v.list_of("links")):
        w, dt = f"links[{i}]", ln.get("doctype")
        _keys(v, w, dt, ln, {"doctype", "link_doctype", "link_fieldname", "group"})
        own_dt = ln.get("link_doctype")
        if own_dt not in v.own or own_dt in v.tables:
            v.refuse(
                w,
                dt,
                "a Connections link lists the manifest's own records under a record (link_doctype is one "
                "of the manifest's own record types)",
            )
            continue
        d = next(d for d in v.m["doctypes"] if d.get("name") == own_dt)
        f = next(
            (f for f in d.get("fields") or [] if f.get("fieldname") == ln.get("link_fieldname")),
            None,
        )
        if not f or f.get("fieldtype") != "Link" or f.get("options") != dt:
            v.refuse(w, dt, f"link_fieldname must be a Link field on {own_dt} pointing at {dt}")


def _registered_applications(v: _V):
    for i, r in enumerate(v.list_of("registered_applications")):
        w, name = f"registered_applications[{i}]", r.get("name")
        v.named(w, name)
        _keys(
            v,
            w,
            name,
            r,
            {"name", "description", "events", "user", "application_user", "enable", "enabled"},
        )
        ev = r.get("events")
        if not isinstance(ev, list) or not ev or any(not isinstance(x, str) for x in ev):
            v.refuse(w, name, "events is a list of the record types the application follows")
        for k in ("user", "application_user", "enable", "enabled"):
            if k in r:
                v.refuse(
                    w,
                    name,
                    "the install makes the user the application reads as and the shop switches it on; "
                    "a manifest installs the registration switched off",
                )
        # The app's own user serves one feed (the feed's door: one user, one registration)
        if i:
            v.refuse(
                w,
                name,
                "an app has one event feed: list every record type it follows in the first one's events",
            )


REMOTE_KEYS = {
    "key",
    "label",
    "endpoint_url",
    "returns_message",
    "returns_sale_attributes",
    "timeout_seconds",
    "partner_name",
}


# What the shop does and a manifest never does (the remote till key's words, kept for every kind that calls out):
SHOP_SWITCHES = {"enabled", "consent_given", "consent_by", "consent_on"}
SHOP_CONSENT = {"consent_fields", "consent_url"}


def _installed_off(v: _V, w: str, name, obj: dict, what: str = "key"):
    """A record that calls a partner's service carries no switch, consent or secret of its own. POS
    CHANGE: a till key's consent is stamped by the site from the shop's install consent."""
    if SHOP_SWITCHES & set(obj):
        v.refuse(
            w,
            name,
            "the site stamps the key's consent from the shop's consent to the install, and a store "
            "switches it on in POS Studio; a manifest never sets it"
            if what == "key"
            else f"the shop's administrator ticks the consent and switches the {what} on; a "
            "manifest installs it switched off, consent not given",
        )
    if "secret" in obj:
        v.refuse(
            w,
            name,
            "a manifest carries no secret; the installer makes one and hands it to the partner",
        )
    if SHOP_CONSENT & set(obj):
        v.refuse(
            w,
            name,
            "what the till sends and the consent text are the POS app's own, stamped by the server when "
            "the shop ticks consent; a manifest declares neither",
        )


def _endpoint(v: _V, w: str, name, url):
    if not isinstance(url, str) or url not in v.urls or not url.startswith("https://"):
        v.refuse(
            w, name, "endpoint_url must be an https address the manifest lists in allowed_urls"
        )


def _remote_keys(v: _V):
    for i, k in enumerate(v.list_of("remote_keys")):
        w, key = f"remote_keys[{i}]", k.get("key")
        _installed_off(v, w, key, k)
        _keys(v, w, key, k, REMOTE_KEYS | SHOP_SWITCHES | SHOP_CONSENT | {"secret"})
        if not isinstance(key, str) or not re.match(r"^[a-z][a-z0-9_]{0,39}$", key):
            v.refuse(w, key, "key is lower-case letters, digits and underscores")
        if not isinstance(k.get("label"), str) or not 1 <= len(k["label"]) <= 24:
            v.refuse(w, key, "label is 1 to 24 characters (it is a till button)")
        _endpoint(v, w, key, k.get("endpoint_url"))
        t = k.get("timeout_seconds", 3)
        if not isinstance(t, (int, float)) or not 0 < t <= 5:
            v.refuse(w, key, "timeout_seconds is above 0 and at most 5 (a cashier is waiting)")


# ── the shipped extension points ─────────────────────────────────────────────
# The product validates every record when the installer inserts it (its own `validate`), and a refusal there is
# reported word for word; these checks refuse EARLY, in words a partner reads, only what the kit itself decides: what is
# switched on, what carries a secret, which address, which role, which record a declaration points at.

# Each extension point on this product and its own time-to-answer maximum (ivendnext_mpos partner_point.POINTS
# `timeout_max`). An extension point the product adds needs a row here before a manifest names it.
SUB_POINTS = {
    "desk_action": 10,
    "page": 10,
    "check": 10,
    "capture": 10,
    "doccheck": 10,
    "fulfil": 10,
    "price": 10,
    # A payer answers in at most 5 seconds (the cashier waits at the tender)
    "payer": 5,
}
# each extension point's answers when its service is down (`Point.down_answers`, the first the product's default)
DOWN_ANSWERS = {
    "desk_action": ("refuse",),
    "page": ("refuse",),
    "check": ("allow_and_flag", "refuse", "ask"),
    "capture": ("allow_and_flag", "refuse"),
    "doccheck": ("allow_and_flag", "refuse", "ask"),
    # P-FULFIL: fixed — a paid sale is never undone, the receipt waits
    "fulfil": ("wait",),
    # a pricing module that cannot answer takes nothing off: the shop's own price
    "price": ("no_adjustment",),
    # Fixed — a payer service that cannot answer means no cover
    "payer": ("no_cover",),
}
# The extension points a partner's sandboxed module may answer (the product's points that take a module), and those that
# take a module only (a price cannot wait on a network). A module a till runs is at most 256 KB. An extension point the
# product opens to modules needs a row here before a manifest names a module for it.
MODULE_POINTS = ("check", "price")
MODULE_ONLY = ("price",)
TILL_MODULE_MAX = 256 * 1024
MODULE_KEYS = {
    "key",
    "point",
    "version",
    "metered",
    "sha256",
    "certificate",
    "wasm",
    "partner_name",
}
# P-CHECK (partner_check.PER_SCOPE_MAX, SCOPE_SECONDS_MAX): a manifest's checks answer every POS Profile (a
# manifest names no scope), so they all share each one; the product checks it again, with the site's other checks, when
# the shop switches one on
CHECKS_MAX, CHECK_SECONDS_MAX = 3, 10
# P-CAPTURE (partner_capture.EVENTS, TIMEOUTS, GROUPS_MAX): one service per event; a scan or a quantity change answers in
# at most 3 seconds
CAPTURE_EVENTS = {
    "scan": ({"event", "item_groups", "item_field"}, 3),
    "customer_add": ({"event"}, 10),
    "customer_select": ({"event"}, 10),
    "qty_change": ({"event", "item_groups", "item_field"}, 3),
}
CAPTURE_GROUPS_MAX = 50
SUB_KEYS = {
    "key",
    "point",
    "partner_name",
    "label",
    "endpoint_url",
    "timeout_seconds",
    "sequence",
    "transport",
    "down_answer",
}
PAGE_KEYS = {
    "page_placement",
    "page_roles",
    "page_send_user",
    "page_send_sale",
    "page_returns_message",
    "page_returns_sale_attributes",
    "page_height",
}
SWITCHED_OFF = "the shop switches it on; a manifest installs it switched off"


def _strings(v: _V, w, name, obj, key):
    x = obj.get(key)
    if x is not None and (not isinstance(x, list) or any(not isinstance(s, str) for s in x)):
        v.refuse(w, name, f"{key} is a list of plain values")


def _objects(v: _V, w, name, obj, key):
    x = obj.get(key)
    if x is not None and (not isinstance(x, list) or any(not isinstance(s, dict) for s in x)):
        v.refuse(w, name, f"{key} is a list of objects")


def _base64(text) -> bytes | None:
    if not isinstance(text, str):
        return None
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def _partner(m: dict, x: dict):
    """The partner name the installer gives a module or a service: its own, else the publisher's, else the prefix."""
    return x.get("partner_name") or m.get("publisher") or m.get("prefix")


def _extension_modules(v: _V):
    """A module our certify service signed. Its bytes, its point, its version and the meters are checked here; the
    signature is checked by the shop when it installs the module (it is our certify service's, and the shop holds
    the key)."""
    seen, owners = set(), set()
    for i, e in enumerate(v.list_of("extension_modules")):
        w, key = f"extension_modules[{i}]", e.get("key")
        _keys(v, w, key, e, MODULE_KEYS)
        # the shop finds a partner's modules by name, trimmed and in any case
        partner = _partner(v.m, e)
        if not isinstance(partner, str) or not partner.strip():
            v.refuse(
                w,
                key,
                "the module's partner name (its partner_name, else the publisher, else the prefix) is "
                "plain text",
            )
        elif (e.get("point"), partner.strip().casefold()) in owners:
            v.refuse(
                w,
                key,
                "a manifest carries one module per partner and extension point: a newer version "
                "replaces the older one when it is added",
            )
        else:
            owners.add((e.get("point"), partner.strip().casefold()))
        if not isinstance(key, str) or not re.match(r"^[a-z][a-z0-9_]{0,39}$", key):
            v.refuse(
                w,
                key,
                "key is lower-case letters, digits and underscores (a service names its module by it)",
            )
        elif key in seen:
            v.refuse(w, key, "a module key is used twice")
        seen.add(key)
        if e.get("point") not in MODULE_POINTS:
            v.refuse(
                w,
                key,
                f"the extension point {e.get('point')} runs no module; a module answers one of: "
                f"{', '.join(MODULE_POINTS)}",
            )
        version = e.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            v.refuse(
                w, key, "version is a whole number from 1 (the version the certificate names)"
            )
        if e.get("metered") is not True:
            v.refuse(w, key, "metered is true: a module a till runs must carry the kit's meters")
        signature = _base64(e.get("certificate"))
        if signature is None or len(signature) != 64:
            v.refuse(
                w,
                key,
                "certificate is our certify service's signature, in base64, as its certificate file "
                "gives it (the shop checks it when it installs the module)",
            )
        b = _base64(e.get("wasm"))
        if b is None:
            v.refuse(w, key, "wasm is the module's bytes in base64")
        elif len(b) > TILL_MODULE_MAX:
            v.refuse(
                w,
                key,
                f"the module is {len(b)} bytes; a module a till runs is at most {TILL_MODULE_MAX} bytes",
            )
        elif hashlib.sha256(b).hexdigest() != e.get("sha256"):
            v.refuse(w, key, "sha256 is not the SHA-256 of the module's bytes (wasm)")


def _module_service(v: _V, w: str, key, s: dict):
    """A service a module this manifest carries answers: it runs inside the shop, so it has no address."""
    point = s.get("point")
    if not isinstance(_partner(v.m, s), str) or not _partner(v.m, s).strip():
        v.refuse(
            w,
            key,
            "the service's partner name (its partner_name, else the publisher) is plain text",
        )
        return
    if "endpoint_url" in s:
        v.refuse(
            w, key, "a module's service runs inside the shop and has no address (endpoint_url)"
        )
    modules = {}
    for e in v.m.get("extension_modules") or []:
        if isinstance(e, dict):
            modules.setdefault(e.get("key"), e)  # a key used twice is refused once, at its module
    e = modules.get(s.get("module"))
    if point not in MODULE_POINTS:
        v.refuse(w, key, f"the {point} extension point runs no module")
    elif e is None:
        v.refuse(
            w,
            key,
            "module names no module of this manifest (the key of one of its extension_modules)",
        )
    elif e.get("point") != point:
        v.refuse(w, key, f"its module {s['module']} is for the {e.get('point')} extension point")
    elif _partner(v.m, e) != _partner(v.m, s):
        v.refuse(
            w,
            key,
            f"its module {s['module']} is another partner's (a module's service takes its module's "
            "partner_name)",
        )


def _extension_subscriptions(v: _V):
    seen = set()
    for i, s in enumerate(v.list_of("extension_subscriptions")):
        w, key = f"extension_subscriptions[{i}]", s.get("key")
        _installed_off(v, w, key, s, "service")
        if "scope" in s:
            v.refuse(
                w,
                key,
                "the shop chooses which stores' tills a service answers (scope); a manifest's service "
                "answers every store until the shop narrows it",
            )
        point = s.get("point")
        transport = s.get("transport", "remote")
        if transport not in ("remote", "wasm"):
            v.refuse(
                w,
                key,
                "transport is remote (a partner's https address) or wasm (a module this manifest "
                "carries)",
            )
        elif transport == "remote" and "module" in s:
            v.refuse(
                w, key, "the service names a module, so its transport is wasm (it has no address)"
            )
        elif transport == "remote" and point in MODULE_ONLY:
            v.refuse(
                w,
                key,
                f"the {point} extension point takes a module only (a price cannot wait on a network)",
            )
        elif transport == "wasm":
            _module_service(v, w, key, s)
        if "max_discount_percent" in s:
            v.refuse(
                w,
                key,
                "the most a module may take off a line is the shop's to set: a manifest's service is "
                "installed at 0 and the shop raises it",
            )
        if s.get("may_approve"):
            v.refuse(
                w,
                key,
                "the shop decides whether a manager may approve past a check (it needs the shop's own "
                "approvers); a manifest installs it off",
            )
        _keys(
            v,
            w,
            key,
            s,
            SUB_KEYS
            | PAGE_KEYS
            | SHOP_SWITCHES
            | SHOP_CONSENT
            | {"secret", "scope", "module", "may_approve", "max_discount_percent"}
            # a document check names its record type and fields there (the product checks them); a pricing
            # module reads its own configuration there
            | (
                {"settings"}
                if point in ("check", "capture", "doccheck", "fulfil", "price", "payer")
                else set()
            ),
        )
        if not isinstance(key, str) or not re.match(r"^[a-z][a-z0-9_]{0,39}$", key):
            v.refuse(
                w,
                key,
                "key is lower-case letters, digits and underscores (a Desk action names its service by it)",
            )
        elif key in seen:
            v.refuse(w, key, "a subscription key is used twice")
        seen.add(key)
        if point not in SUB_POINTS:
            v.refuse(
                w,
                key,
                f"point is one of the extension points on this product: {', '.join(SUB_POINTS)}",
            )
        elif point != "page" and PAGE_KEYS & set(s):
            v.refuse(w, key, "the page_… settings belong to a page subscription")
        if not isinstance(s.get("label"), str) or not 1 <= len(s["label"].strip()) <= 40:
            v.refuse(w, key, "label is 1 to 40 characters")
        if transport != "wasm":
            _endpoint(v, w, key, s.get("endpoint_url"))
        top = SUB_POINTS.get(point, 10)
        if point == "check" and "settings" in s:
            v.refuse(
                w, key, "a check takes no settings: what it is sent is the extension point's own"
            )
        if point == "capture":
            top = _capture_settings(v, w, key, s.get("settings"))
        if point == "fulfil":
            _fulfil_settings(v, w, key, s.get("settings"))
        if point == "payer":
            _payer_settings(v, w, key, s.get("settings"))
        if not _seconds(s.get("timeout_seconds", min(3, top)), top):
            v.refuse(
                w,
                key,
                f"timeout_seconds is above 0 and at most {top} (the extension point's own limit)",
            )
        down = s.get("down_answer")
        if down is not None and point in DOWN_ANSWERS and down not in DOWN_ANSWERS[point]:
            # the product's own sentence (partner_point.validate_subscription)
            v.refuse(
                w,
                key,
                f"When the service is down, this extension point can only: {', '.join(DOWN_ANSWERS[point])}.",
            )
        _roles(v, w, key, s.get("page_roles"))
    subs = [s for s in v.m.get("extension_subscriptions") or [] if isinstance(s, dict)]
    checks = [s for s in subs if s.get("point") == "check"]
    if len(checks) > CHECKS_MAX:
        v.refuse(
            "extension_subscriptions",
            None,
            f"At most {CHECKS_MAX} checks may answer one POS Profile.",
        )
    elif (
        all(_seconds(s.get("timeout_seconds", 3), SUB_POINTS["check"]) for s in checks)
        and sum(s.get("timeout_seconds", 3) for s in checks) > CHECK_SECONDS_MAX
    ):  # a bad one is refused on its own
        v.refuse(
            "extension_subscriptions",
            None,
            f"The checks of one POS Profile may take at most {CHECK_SECONDS_MAX} seconds together.",
        )
    events = {}
    for s in subs:
        ev = (
            (s.get("settings") or {}).get("event")
            if s.get("point") == "capture" and isinstance(s.get("settings"), dict)
            else None
        )
        if ev in CAPTURE_EVENTS and ev in events:
            v.refuse(
                "extension_subscriptions",
                s.get("key"),
                f"{events[ev]} already answers {ev} for these POS Profiles. One service answers each.",
            )
        events.setdefault(ev, s.get("key"))


def _seconds(t, top) -> bool:
    return isinstance(t, (int, float)) and not isinstance(t, bool) and 0 < t <= top


def _capture_settings(v: _V, w, key, settings) -> int:
    """P-CAPTURE's settings, in the product's own sentences (``partner_capture.validate_subscription``); the most
    seconds the event allows. What needs the site (an item group, an Item field) the product checks at insert.
    """
    event = settings.get("event") if isinstance(settings, dict) else None
    if event not in CAPTURE_EVENTS:
        v.refuse(
            w,
            key,
            "Name the event in the settings: scan, customer_add, customer_select or qty_change.",
        )
        return 10
    known, top = CAPTURE_EVENTS[event]
    if set(settings) - known:
        v.refuse(
            w,
            key,
            f"The settings of a {event} capture may only carry: {', '.join(sorted(known))}.",
        )
    elif event in ("scan", "qty_change"):
        groups, field = settings.get("item_groups") or [], settings.get("item_field") or ""
        if not isinstance(groups, list) or any(not isinstance(g, str) for g in groups):
            v.refuse(w, key, "item_groups must be a list of item group names.")
        elif len(groups) > CAPTURE_GROUPS_MAX:
            v.refuse(w, key, f"A {event} capture names at most {CAPTURE_GROUPS_MAX} item groups.")
        elif not isinstance(field, str):
            v.refuse(w, key, "item_field must be the name of one field on Item.")
        elif not groups and not field:
            v.refuse(
                w,
                key,
                f"Say which items a {event} capture asks about: item groups, an item field, or both.",
            )
    return top


def _payer_settings(v: _V, w, key, settings) -> None:
    """The payer's settings a manifest may carry: the prescription's sale details and the
    bill-back role (``partner_payer.validate_subscription``; the site's sale details and
    roles are checked by the product at insert). The clearing mode is the shop's: its
    account is on the shop's own books."""
    if settings is None:
        return
    if not isinstance(settings, dict):
        v.refuse(w, key, "The extension point's settings must be a JSON object.")
        return
    if "clearing_mode" in settings:
        v.refuse(
            w,
            key,
            "the clearing mode is the shop's to pick (its account is on the shop's books): a "
            "manifest installs the payer service without one",
        )
    if set(settings) - {"prescription", "bill_back_role", "clearing_mode"}:
        v.refuse(
            w,
            key,
            "The settings of a payer service may only carry: bill_back_role, clearing_mode, "
            "prescription.",
        )
    rx = settings.get("prescription") or {}
    if not isinstance(rx, dict) or set(rx) - {"reference", "prescriber", "prescriber_licence"}:
        v.refuse(
            w,
            key,
            "prescription names up to three sale details: reference, prescriber, "
            "prescriber_licence.",
        )
    elif any(not isinstance(n, str) or not n.strip() for n in rx.values()):
        v.refuse(w, key, "each prescription detail is the name of one sale detail")
    role = settings.get("bill_back_role")
    if role is not None and (not isinstance(role, str) or not role.strip()):
        v.refuse(w, key, "bill_back_role is the name of one role")
    elif role is not None:
        _roles(v, w, key, [role])


def _fulfil_settings(v: _V, w, key, settings) -> None:
    """P-FULFIL's settings: the scan capture's filter, in the product's own sentences
    (``partner_fulfil.validate_subscription``); the site's item groups and fields are
    checked by the product at insert."""
    if not isinstance(settings, dict):
        settings = {}
    groups, field = settings.get("item_groups") or [], settings.get("item_field") or ""
    if set(settings) - {"item_groups", "item_field"}:
        v.refuse(
            w, key, "The settings of a fulfil service may only carry: item_field, item_groups."
        )
    elif not isinstance(groups, list) or any(not isinstance(g, str) for g in groups):
        v.refuse(w, key, "item_groups must be a list of item group names.")
    elif len(groups) > CAPTURE_GROUPS_MAX:
        v.refuse(w, key, f"A fulfil service names at most {CAPTURE_GROUPS_MAX} item groups.")
    elif not isinstance(field, str):
        v.refuse(w, key, "item_field must be the name of one field on Item.")
    elif not groups and not field:
        v.refuse(
            w, key, "Say which items a fulfil service makes: item groups, an item field, or both."
        )


# a Desk action's input types: the product's own list (ivendnext_mpos desk_action.INPUT_TYPES, pinned equal by a POS
# test); any other type is refused when the installer inserts the action, after the shop consented. The action's other
# rules (its placement, the label, menu and confirm lengths) and an input's (its field name, label, choices, link
# target, how many) are the product's own, refused at install
DESK_INPUT_TYPES = ("Data", "Int", "Float", "Date", "Select", "Link", "Check", "Small Text")
DESK_KEYS = {
    "record_type",
    "label",
    "group",
    "placement",
    "service",
    "roles",
    "on_draft",
    "on_submitted",
    "on_cancelled",
    "states",
    "conditions",
    "inputs",
    "confirm_text",
    "send_fields",
}


def _desk_actions(v: _V):
    services = {
        s.get("key")
        for s in v.m.get("extension_subscriptions") or []
        if isinstance(s, dict) and s.get("point") == "desk_action"
    }
    for i, a in enumerate(v.list_of("desk_actions")):
        w, label = f"desk_actions[{i}]", a.get("label")
        if "enabled" in a:
            v.refuse(w, label, SWITCHED_OFF)
        _keys(v, w, label, a, DESK_KEYS | {"enabled"})
        if not isinstance(a.get("record_type"), str):
            v.refuse(w, label, "a Desk action names its record type")
        if a.get("service") not in services:
            v.refuse(
                w,
                label,
                "service is the key of one of the manifest's own extension_subscriptions for the "
                "desk_action extension point (the installer makes the subscription first)",
            )
        _roles(v, w, label, a.get("roles"))
        _strings(v, w, label, a, "states")
        _objects(v, w, label, a, "conditions")
        _objects(v, w, label, a, "inputs")
        for j, inp in enumerate(a.get("inputs") if isinstance(a.get("inputs"), list) else []):
            t = inp.get("fieldtype") if isinstance(inp, dict) else None
            if t is not None and t not in DESK_INPUT_TYPES:
                v.refuse(
                    f"{w}.inputs[{j}]",
                    label,
                    f"an input's fieldtype is one of {', '.join(DESK_INPUT_TYPES)}",
                )


RULE_KEYS = {
    "rule_name",
    "record_type",
    "child_table",
    "kind",
    "field",
    "mode",
    "sequence",
    "message",
    "pattern_class",
    "pattern",
    "min_length",
    "max_length",
    "formula",
    "source",
    "source_b",
    "source_table",  # sum_rows / count_rows
    "factor",
    "offset",
    "decimals",
    "operator",
    "value",
    "bypass_roles",
    "conditions",
    "states",
    "locked_fields",
    "action",
    "scope_fields",
    # count_per_day: the field counted per, the day field, the cap
    "scope_field",
    "day_field",
    "cap",
    # threshold: judged only when new or changed; the limit and one role that may
    # pass it read from a settings record
    "judge_on_change",
    "value_from_type",
    "value_from_name",
    "value_field",
    "roles_field",
}


def _save_rules(v: _V):
    for i, r in enumerate(v.list_of("save_rules")):
        w, name = f"save_rules[{i}]", r.get("rule_name")
        v.named(w, name)
        if "enabled" in r:
            v.refuse(w, name, SWITCHED_OFF)
        _keys(v, w, name, r, RULE_KEYS | {"enabled"})
        if not isinstance(r.get("record_type"), str):
            v.refuse(w, name, "a save rule names its record type")
        _roles(v, w, name, r.get("bypass_roles"))
        v.no_script(
            f"{w}.message", name, r.get("message")
        )  # the product shows it as the refusal, unescaped
        _strings(v, w, name, r, "states")
        _strings(v, w, name, r, "locked_fields")
        _strings(v, w, name, r, "scope_fields")
        _objects(v, w, name, r, "conditions")


# ── the scan and field declarations ──────────────────────────────────────────
# P-SCAN: a Retail Scan Source is data, read by the till's scan on a miss (ivendnext_mpos business_logic/scan_source.py
# validate_source). The product's own sentences where the kit can tell from the manifest alone (a source over
# the manifest's own table); a shop table's fields the product checks at insert, and that refusal comes back word for word.
SCAN_KEYS = {
    "source_name",
    "record_type",
    "barcode_field",
    "item_from",
    "batch_from",
    "serial_from",
    "status_field",
    "available_values",
    "warehouse_field",
    "capture_as",
    "sequence",
}
SCAN_LINKS = {
    "item_from": "Item",
    "batch_from": "Batch",
    "serial_from": "Serial No",
    "warehouse_field": "Warehouse",
}


def _scan_sources(v: _V):
    for i, src in enumerate(v.list_of("scan_sources")):
        w, name = f"scan_sources[{i}]", src.get("source_name")
        v.named(w, name)
        if "enabled" in src:
            v.refuse(w, name, SWITCHED_OFF)
        _keys(v, w, name, src, SCAN_KEYS | {"enabled"})
        dt, code, item = src.get("record_type"), src.get("barcode_field"), src.get("item_from")
        if not all(isinstance(x, str) and x for x in (dt, code, item)):
            v.refuse(
                w,
                name,
                "a scan source names the table its codes are kept in (record_type), the code field "
                "(barcode_field) and the field linking to Item (item_from)",
            )
            continue
        _strings(v, w, name, src, "available_values")
        mine = next(
            (d for d in v.m.get("doctypes") or [] if isinstance(d, dict) and d.get("name") == dt),
            None,
        )
        if mine is not None:
            fields = {
                f.get("fieldname"): f for f in mine.get("fields") or [] if isinstance(f, dict)
            }

            def field(fn):
                if fn not in fields:
                    v.refuse(w, name, f"{dt} has no field {fn}.")
                return fields.get(fn)

            if code != "name" and (f := field(code)) and not f.get("unique"):
                v.refuse(w, name, f"Set {code} unique on {dt} first, so one code names one unit.")
            for k, target in SCAN_LINKS.items():
                fn = src.get(k)
                if (
                    fn
                    and fn != "parent"
                    and (f := field(fn))
                    and (f.get("fieldtype") != "Link" or f.get("options") != target)
                ):
                    v.refuse(w, name, f"{fn} must link to {target}.")
            if src.get("status_field"):
                field(src["status_field"])
        if src.get("status_field") and not src.get("available_values"):
            v.refuse(w, name, "Name at least one status a unit can be sold in.")
        if src.get("capture_as") and not src.get("status_field"):
            v.refuse(
                w,
                name,
                "Recording the code needs a status field, so a returned unit can be sold again.",
            )


# P-FIELDS: rows of a till theme's field rules (Retail POS Theme Field on a named Retail POS Theme; ivendnext_mpos
# business_logic/pos_fields.py SURFACES, validate_field_rules), in the product's own sentences. A rule has no
# switch: it reaches every till on that theme at its next start, which the install's todo says. ⚠ A copy of the product's
# allow-lists — a defect here is a defect there: report it with a Kit defect issue.
FIELD_SURFACES = {
    "customer_create": (
        None,
        {
            "customer_name": ("relabel",),
            "phone": ("hide", "relabel", "require"),
            "email": ("hide", "relabel", "require"),
            "more_details": ("hide",),
        },
    ),
    "customer_card": (
        "Customer",
        {
            "phone": ("hide",),
            "member_since": ("hide", "relabel"),
            "lifetime": ("hide", "relabel"),
            "visits": ("hide", "relabel"),
            "points": ("hide", "relabel"),
        },
    ),
    "cart_line": (
        "Item",
        {
            "item_name": ("relabel",),
            "qty": ("relabel",),
            # v3: the line's money figures, relabel only (list_price: shown)
            "price": ("relabel",),
            "discount": ("relabel",),
            "amount": ("relabel",),
        },
    ),
    "item_result": ("Item", {"item_code": ("hide", "relabel")}),
    "sale_details": (
        None,
        None,
    ),  # its fields are the shop's active sale details: hide or relabel (the product checks)
    # the receipt, show only — up to three Item fields under each line
    "receipt_preview": ("Item", {}),
    # v3: the online basket's totals words, relabel only
    "totals": (
        None,
        {
            "discount": ("relabel",),
            "charges": ("relabel",),
            "delivery": ("relabel",),
            "tax": ("relabel",),
            "grand_total": ("relabel",),
        },
    ),
}
# v3: the figure `show` draws beside the line (no Item field, no cap), and every
# rule whose label sits beside money — its label carries no digit, % or currency sign. ⚠ The
# checker runs without the site, so it reads the symbol characters only; the product also
# refuses the site's own letter signs (the rand's R) at save.
FIELD_SHOWN_FIGURES = {("cart_line", "list_price")}
FIELD_MONEY = {("cart_line", f) for f in ("price", "discount", "amount", "list_price")} | {
    ("totals", f) for f in FIELD_SURFACES["totals"][1]
}
FIELD_MONEY_LABEL = "A money label can't carry a digit, a % or a currency sign: the figure beside it is the till's."


def _money_label(label: str) -> bool:
    return any(
        c == "%" or unicodedata.category(c) == "Sc" or unicodedata.category(c).startswith("N")
        for c in label
    )


# the product's words for a receipt rule other than show (pos_fields.validate_field_rules)
FIELD_RECEIPT_ONLY_SHOW = (
    "On the receipt a rule can only show an item field. Money, tax and the receipt's own "
    "lines print as they are."
)
FIELD_ACTIONS = ("hide", "relabel", "require", "show")
FIELD_LABEL_MAX, FIELD_SHOW_MAX = 40, 3
# ``show`` on ``customer_create`` asks for one of the app's own Customer fields at
# customer add and edit (pos_fields.INPUT_SURFACE / INPUT_MAX); the product checks the field
FIELD_INPUT_SURFACE, FIELD_INPUT_MAX = "customer_create", 3
FIELD_RULE_KEYS = {"theme", "surface", "field", "action", "label", "language", "sequence"}


def _field_rules(v: _V):
    actions, seen, shown = {}, set(), {}
    for i, r in enumerate(v.list_of("field_rules")):
        w = f"field_rules[{i}]"
        theme, surface, field, action = (
            r.get("theme"),
            r.get("surface"),
            r.get("field"),
            r.get("action"),
        )
        _keys(v, w, field, r, FIELD_RULE_KEYS)
        if not isinstance(theme, str) or not theme.strip():
            v.refuse(
                w,
                field,
                "a field rule names its till theme (theme): the shop's Retail POS Theme it is added to",
            )
            continue
        v.no_script(f"{w}.label", field, r.get("label"))
        if surface not in FIELD_SURFACES:
            v.refuse(w, field, f"{surface} is not a till screen field rules apply to.")
            continue
        if action not in FIELD_ACTIONS:
            v.refuse(w, field, f"{action} is not a field action.")
            continue
        if not isinstance(field, str) or not field.strip():
            v.refuse(w, field, "Name the field each rule applies to.")
            continue
        if actions.setdefault((theme, surface, field), action) != action:
            v.refuse(w, field, f"{field} on {surface} has two different rules. Keep one.")
            continue
        key = (theme, surface, field, r.get("language") if action in ("relabel", "show") else None)
        if key in seen:
            v.refuse(w, field, f"{field} on {surface} has the same rule twice.")
            continue
        seen.add(key)
        label = r.get("label")
        if isinstance(label, str) and len(label.strip()) > FIELD_LABEL_MAX:
            v.refuse(w, field, f"A label is at most {FIELD_LABEL_MAX} characters.")
        elif action == "relabel" and not (isinstance(label, str) and label.strip()):
            v.refuse(w, field, f"Give {field} its new label.")
        elif isinstance(label, str) and (surface, field) in FIELD_MONEY and _money_label(label):
            v.refuse(w, field, FIELD_MONEY_LABEL)
        doctype, named = FIELD_SURFACES[surface]
        if action == "show" and (surface, field) in FIELD_SHOWN_FIGURES:
            continue
        if action == "show" and doctype and (surface, field) in FIELD_MONEY:
            v.refuse(w, field, f"{field} on {surface} can't take this rule.")
            continue
        if action == "show" and surface == FIELD_INPUT_SURFACE:
            shown.setdefault((theme, FIELD_INPUT_SURFACE), set()).add(field)
            continue
        if action == "show":
            if not doctype:
                v.refuse(w, field, f"Nothing more can be shown on {surface}.")
            else:
                shown.setdefault((theme, doctype), set()).add(field)
            continue
        if surface == "receipt_preview":
            v.refuse(w, field, FIELD_RECEIPT_ONLY_SHOW)
            continue
        if named is None:
            allowed = ("hide", "relabel")
        else:
            allowed = named.get(field, ())
        if action not in allowed:
            if action == "hide" and "relabel" in allowed:
                v.refuse(w, field, f"{field} can't be hidden: the sale needs it.")
            else:
                v.refuse(w, field, f"{field} on {surface} can't take this rule.")
    for (theme, doctype), fields in shown.items():
        if doctype == FIELD_INPUT_SURFACE:
            if len(fields) > FIELD_INPUT_MAX:
                v.refuse(
                    "field_rules",
                    theme,
                    f"Up to {FIELD_INPUT_MAX} customer fields can be asked for. This theme "
                    f"asks for {len(fields)}.",
                )
            continue
        if len(fields) > FIELD_SHOW_MAX:
            v.refuse(
                "field_rules",
                theme,
                f"Up to {FIELD_SHOW_MAX} more {doctype} fields can be shown. This theme "
                f"shows {len(fields)}.",
            )


FISCAL_DT = "POS Invoice"
OUTSIDE_SERVICE = "Outside service"  # ivendnext_mpos fiscal_app_reader.OUTSIDE_SERVICE
FISCAL_KEYS = {
    "source",
    "status_field",
    "ref_field",
    "qr_field",
    "signature_field",  # the authority's seal, beside its QR
    "status_map",
    "writer_role",
    "writer_level",
    "writer_users",
}
# signature_field joins the result keys, optional like qr_field
RESULT_KEYS = ("status_field", "ref_field", "qr_field", "signature_field")
OPTIONAL_RESULT_KEYS = ("qr_field", "signature_field")
# the QR and seal fields hold text (fiscal_app_reader.MARK_TEXT_TYPES,
# less Code: FIELD_TYPES lets no manifest make a Code field)
MARK_TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text")
FISCAL_FIELD_KEYS = {"permlevel", "no_copy"}  # set on a reader's result fields only


def _result_fields(m) -> set:
    return {
        (FISCAL_DT, r.get(k))
        for r in m.get("fiscal_readers") or []
        if isinstance(r, dict)
        for k in RESULT_KEYS
        if r.get(k)
    }


def _fiscal_readers(v: _V):
    readers = v.list_of("fiscal_readers")
    if len(readers) > 1:
        v.refuse(
            "fiscal_readers",
            None,
            "one fiscal reader per site: the reader is named by its source, and a "
            "manifest's source is the outside service",
        )
    own = {
        c.get("fieldname"): c
        for c in v.m.get("custom_fields") or []
        if isinstance(c, dict) and c.get("dt") == FISCAL_DT
    }
    for i, r in enumerate(readers[:1]):
        w, role = f"fiscal_readers[{i}]", r.get("writer_role")
        if "enabled" in r:
            v.refuse(
                w,
                role,
                "the shop switches the reader on once its writer rule holds; a manifest installs it "
                "switched off",
            )
        if "companies" in r:
            v.refuse(
                w,
                role,
                "the reader serves the shop's own company (one per site); the installer names it",
            )
        if r.get("source", OUTSIDE_SERVICE) != OUTSIDE_SERVICE:
            v.refuse(
                w,
                role,
                f"a manifest carries no code, so its reader reads an outside service ('{OUTSIDE_SERVICE}'); "
                "an installed fiscal app declares its own reader",
            )
        _keys(v, w, role, r, FISCAL_KEYS | {"enabled", "companies"})
        v.named(f"{w}.writer_role", role)
        level = r.get("writer_level")
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 9:
            v.refuse(
                w,
                role,
                "writer_level is the result fields' own permission level, 1 to 9 (at level 0 anyone who "
                "may edit a sale writes them)",
            )
            level = None
        for k in RESULT_KEYS:
            fn = r.get(k)
            if fn is None and k in OPTIONAL_RESULT_KEYS:
                continue
            if fn not in own:
                v.refuse(
                    w,
                    role,
                    f"{k} names the manifest's own field on {FISCAL_DT} (custom_fields): the installer "
                    "makes the result fields before the reader",
                )
            elif level is not None and own[fn].get("permlevel") != level:
                v.refuse(w, role, f"{k} '{fn}' must sit at writer_level {level} (its permlevel)")
            elif k in OPTIONAL_RESULT_KEYS and own[fn].get("fieldtype") not in MARK_TEXT_TYPES:
                v.refuse(
                    w,
                    role,
                    f"{k} '{fn}' is a field of type {own[fn].get('fieldtype')}: the receipt prints the QR and "
                    f"the seal from text, so the field is one of {', '.join(MARK_TEXT_TYPES)}",
                )
        sm = r.get("status_map")
        if (
            not isinstance(sm, list)
            or not sm
            or any(not isinstance(x, dict) or set(x) != {"source_value", "status"} for x in sm)
        ):
            v.refuse(w, role, "status_map is a list of {source_value, status} rows")
        users = r.get("writer_users", [])
        if (
            not isinstance(users, list)
            or len(set(map(str, users))) != len(users)
            or any(
                not isinstance(u, str) or not re.match(r"^[a-z][a-z0-9_]{0,19}$", u) for u in users
            )
        ):
            v.refuse(
                w,
                role,
                "writer_users is a list of short keys (lower-case letters, digits, underscores); the "
                "installer makes one integration user per key, with no API key (the shop makes it)",
            )


# ── P-LABEL's layout record ─────────────────────────────────────────────────
# A Retail Label Layout is data, filled on the server (ivendnext_mpos business_logic/label_print.py validate_layout).
# ⚠ A copy of the product's rules — a defect here is a defect there: report it with a Kit defect issue. The product runs
# the record's own validate at insert as well, and that refusal comes back word for word.
LABEL_KINDS = ("html", "zpl")
LABEL_PLACEHOLDERS = (
    "item_code",
    "item_name",
    "barcode",
    "barcode_svg",
    "price",
    "currency",
    "uom",
    "batch_no",
    "expiry_date",
    "manufacturing_date",
    "weight",
    "unit_price",
    "store",
)
# A template may name up to three of the item's fields and one line detail; whether the
# field exists, has a type the till shows and the detail is an active attribute is the product's
# check at insert (it reads the site)
LABEL_ITEM_FIELDS_MAX, LABEL_LINE_DETAILS_MAX = 3, 1
LABEL_UNKNOWN_TOKEN_PATTERN = (
    r"\{(?!(?:"
    + "|".join(LABEL_PLACEHOLDERS)
    + r"|item\.[a-z][a-z0-9_]{0,139}|detail\.[^{}]+)\})[^{}]*\}"
)
LABEL_SIZE_MM, LABEL_PER_ROW_MAX, LABEL_TEMPLATE_MAX = (10, 150), 10, 20000
LABEL_KEYS = {"label_name", "kind", "width_mm", "height_mm", "per_row", "template"}
_LABEL_TOKEN_RE = re.compile(r"\{([^{}]*)\}")


def _label_ci(word: str) -> str:
    return "".join(f"[{c.upper()}{c.lower()}]" for c in word)


LABEL_ACTIVE_PATTERN = (
    r"<\s*/?\s*(?:"
    + "|".join(
        _label_ci(t)
        for t in (
            "script",
            "iframe",
            "frameset",
            "frame",
            "object",
            "embed",
            "link",
            "meta",
            "base",
            "form",
        )
    )
    + r")\b"
    r"|" + _label_ci("javascript") + r"\s*:"
    r"|(?<![A-Za-z0-9_-])" + _label_ci("on") + r"[A-Za-z]+\s*="
)


def _label_layouts(v: _V):
    import html as _html

    for i, lay in enumerate(v.list_of("label_layouts")):
        w, name = f"label_layouts[{i}]", lay.get("label_name")
        v.named(w, name)
        if "enabled" in lay:
            v.refuse(w, name, SWITCHED_OFF)
        _keys(v, w, name, lay, LABEL_KEYS | {"enabled"})
        if lay.get("kind", "html") not in LABEL_KINDS:
            v.refuse(w, name, f"a label layout's kind is one of {', '.join(LABEL_KINDS)}")
        t = lay.get("template")
        if not isinstance(t, str) or not t.strip():
            v.refuse(w, name, "A label layout needs a template.")
            continue
        if len(t) > LABEL_TEMPLATE_MAX:
            v.refuse(w, name, f"A label template holds at most {LABEL_TEMPLATE_MAX} characters.")
        if "{{" in t or "{%" in t:
            v.refuse(w, name, "A label template takes placeholders like {item_name}, not code.")
            continue
        if lay.get("kind") == "zpl":
            if not (t.strip().startswith("^XA") and t.strip().endswith("^XZ")):
                v.refuse(w, name, "A zpl label template starts with ^XA and ends with ^XZ.")
            if "{barcode_svg}" in t:
                v.refuse(
                    w,
                    name,
                    "A zpl label template draws its barcode with the printer's own barcode command over "
                    "{barcode}, not {barcode_svg}.",
                )
        unknown = sorted({x[1:-1] for x in re.findall(LABEL_UNKNOWN_TOKEN_PATTERN, t)})
        if unknown:
            v.refuse(
                w, name, f"{', '.join('{' + x + '}' for x in unknown)} is not a label placeholder."
            )
        tokens = _LABEL_TOKEN_RE.findall(t)
        fields = {x for x in tokens if x.startswith("item.")}
        details = {x for x in tokens if x.startswith("detail.")}
        if len(fields) > LABEL_ITEM_FIELDS_MAX:
            v.refuse(
                w, name, f"A label prints at most {LABEL_ITEM_FIELDS_MAX} of the item's fields."
            )
        if len(details) > LABEL_LINE_DETAILS_MAX:
            v.refuse(w, name, "A label prints one line detail.")
        if re.search(LABEL_ACTIVE_PATTERN, re.sub(r"[\t\r\n]", "", _html.unescape(t))):
            v.refuse(
                w, name, "A label template cannot hold scripts, frames, forms or event handlers."
            )
        lo, hi = LABEL_SIZE_MM
        for key in ("width_mm", "height_mm"):
            n = lay.get(key)
            if not isinstance(n, (int, float)) or isinstance(n, bool) or not lo <= n <= hi:
                v.refuse(w, name, f"{key} must be between {lo} and {hi} mm.")
        per = lay.get("per_row", 1)
        if not isinstance(per, int) or isinstance(per, bool) or not 1 <= per <= LABEL_PER_ROW_MAX:
            v.refuse(w, name, f"Labels per row must be between 1 and {LABEL_PER_ROW_MAX}.")


# ── P-LISTMARK's list mark ──────────────────────────────────────────────────
# A Retail List Mark is data the POS app's Desk script draws as a list row's label (ivendnext_mpos
# business_logic/list_mark.py validate_mark). ⚠ A copy of the product's rules that need no site — a defect here is a
# defect there: report it with a Kit defect issue. The rules that read the site (the record type is not submitted and
# has no workflow; it has each field, none a password or long text) are the product's own, refused at install word
# for word.
LIST_MARK_COLOURS = ("green", "blue", "orange", "red", "gray", "purple")
LIST_MARK_OPERATORS = ("=", "!=", ">", ">=", "<", "<=", "is set", "is not set")
LIST_MARK_LABEL_MAX, LIST_MARK_CONDITIONS_MAX, LIST_MARKS_MAX = 24, 3, 5
LIST_MARK_KEYS = {"record_type", "label", "colour", "sequence", "conditions"}
_LIST_MARK_MARKUP_RE = re.compile("[<>&\"'`]")


def _list_mark_conditions(v: _V, w: str, label, conds):
    if not isinstance(conds, list) or not 1 <= len(conds) <= LIST_MARK_CONDITIONS_MAX:
        v.refuse(w, label, f"Give one to {LIST_MARK_CONDITIONS_MAX} conditions.")
        return
    for j, c in enumerate(conds):
        cw = f"{w}.conditions[{j}]"
        if not isinstance(c, dict):
            v.refuse(cw, label, "a condition is an object: field, operator, value")
            continue
        _keys(v, cw, label, c, {"field", "operator", "value"})
        if not isinstance(c.get("field"), str) or not c["field"]:
            v.refuse(cw, label, "a condition names its field")
        if c.get("operator") not in LIST_MARK_OPERATORS:
            v.refuse(
                cw, label, f"a condition's operator is one of {', '.join(LIST_MARK_OPERATORS)}"
            )
        value = c.get("value")
        if value is not None and (
            not isinstance(value, (str, int, float)) or isinstance(value, bool)
        ):
            v.refuse(cw, label, "a condition's value is a plain value")
        elif c.get("operator") in (">", ">=", "<", "<="):
            try:
                float(value)
            except (TypeError, ValueError):
                v.refuse(cw, label, f"A condition with {c['operator']} needs a number.")


def _list_marks(v: _V):
    per: dict[str, int] = {}
    seen: set = set()
    for i, mk in enumerate(v.list_of("list_marks")):
        w, label = f"list_marks[{i}]", mk.get("label")
        if "enabled" in mk:
            v.refuse(w, label, SWITCHED_OFF)
        _keys(v, w, label, mk, LIST_MARK_KEYS | {"enabled"})
        dt = mk.get("record_type")
        if not isinstance(dt, str) or not dt:
            v.refuse(w, label, "a list mark names its record type")
        elif dt != dt.strip():
            # the record stores it trimmed; the uninstall matches it as written
            v.refuse(w, label, "The record type has no space before or after it.")
        else:
            per[dt] = per.get(dt, 0) + 1
        if isinstance(dt, str) and isinstance(label, str):
            if (dt, label) in seen:
                # an update matches a mark by its record type and label: one OR is one label
                v.refuse(w, label, "two marks on one record type need two labels")
            seen.add((dt, label))
        if isinstance(label, str) and label != label.strip():
            # the record stores it trimmed; the uninstall matches the label as written
            v.refuse(w, label, "The label has no space before or after it.")
        elif not isinstance(label, str) or not 1 <= len(label.strip()) <= LIST_MARK_LABEL_MAX:
            v.refuse(w, label, f"The label must be 1 to {LIST_MARK_LABEL_MAX} characters.")
        elif _LIST_MARK_MARKUP_RE.search(label):
            v.refuse(w, label, "The label is plain text: it cannot hold < > & \" ' or `.")
        if mk.get("colour") not in LIST_MARK_COLOURS:
            v.refuse(w, label, f"Choose one of the colours: {', '.join(LIST_MARK_COLOURS)}.")
        seq = mk.get("sequence", 10)
        if not isinstance(seq, int) or isinstance(seq, bool):
            v.refuse(w, label, "sequence is a whole number")
        _list_mark_conditions(v, w, label, mk.get("conditions"))
    for dt, n in per.items():
        if n > LIST_MARKS_MAX:
            v.refuse("list_marks", dt, f"{dt} holds at most {LIST_MARKS_MAX} marks.")


# ── The register books ──────────────────────────────────
# A book is data the register door reads (ivendnext_mpos business_logic/register_book.py, which imports the
# column vocabulary below, so the checker and the door read one list). The door checks every name a book reads
# against the site when the book is saved (VR-28); its refusal comes back word for word. Here: the shape.
REGISTER_LINE_COLUMNS = (
    "number",
    "book",
    "register_store",
    "warehouse",
    "item",
    "item_name",
    "item_class",
    "batch_no",
    "expiry_date",
    "direction",
    "kind",
    "qty",
    "uom",
    "balance",
    "movement_date",
    "movement_time",
    "period",
    "entered_at",
    "entry_date",
    "voucher_type",
    "voucher_no",
    "counterparty",
    "counterparty_address",
    "reference_no",
    "authority_no",
    "authority_issuer",
    "authority_issuer_licence",
    "authority_date",
    "dispenser",
    "dispenser_name",
    "dispenser_licence",
    "booked_late",
    "incomplete",
    "below_zero",
    "correction_of",
    "correction_of_number",
    "correction_note",
    "signed_by",
    "signed_by_name",
    "remarks",
)
REGISTER_DETAILS = tuple(f"detail_{i}" for i in range(1, 7))
REGISTER_COLUMNS = REGISTER_LINE_COLUMNS + REGISTER_DETAILS
# a date or time column routes only on "is set" / "is not set": the condition form compares a date as text
# for = and != and as the number 0 for > … <=, so any other comparison never or always holds
REGISTER_DATE_COLUMNS = (
    "expiry_date",
    "movement_date",
    "movement_time",
    "entered_at",
    "entry_date",
    "authority_date",
)
REGISTER_OPERATORS = ("=", "!=", ">", ">=", "<", "<=", "is set", "is not set")
REGISTER_CONDITIONS_MAX = 3
REGISTER_NUMBERING = ("book_store", "book_store_item")
REGISTER_CORRECTIONS = (
    "reversing_line",
    "dated_note",
    "signed_strike_through",
    "signed_amendment",
)
REGISTER_PERIOD_MONTHS = (1, 2, 3, 4, 6, 12)
# what a book is kept on (§15 R-18): its printed pages · this system · the authority's own numbered
# book · the authority's own system, the shop's lines then a working register
REGISTER_MEDIA = ("printed_book", "system_of_record", "official_book", "regulator_system")
# what a print may show beside the line's own columns, worked out when it prints (never routed on,
# never required): the balance before a line (§15 R-9)
REGISTER_PRINT_COLUMNS = ("balance_before",)
BOOK_KEYS = {
    "book",
    "title",
    "data_set",
    "cite",
    "certified",
    "enabled",
    "medium",
    "numbering",
    "balance",
    "correction",
    "retention_years",
    "period_months",
    "return_due_days",
    "count_role",
    "count_witness",
    "loss_count_hours",
    "items",
    "class_source",
    "conditions",
    "required",
    "columns",
    "details",
    "authority",
    "columns_from",
}
_BOOK_RE = re.compile(r"^[a-z][a-z0-9_]{0,60}(\.[a-z][a-z0-9_]{0,60})?$")
_DATA_SET_RE = re.compile(r"^[a-z][a-z0-9_]{0,60}$")


def _flag(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v in (0, 1)


def _register_condition_refusals(conds, details: dict) -> list[str]:
    if not isinstance(conds, list) or len(conds) > REGISTER_CONDITIONS_MAX:
        return [f"Give at most {REGISTER_CONDITIONS_MAX} conditions."]
    out = []
    for c in conds:
        if not isinstance(c, dict) or set(c) - {"field", "operator", "value"}:
            out.append("a condition is an object: field, operator, value")
            continue
        field, op = c.get("field"), c.get("operator")
        if field not in REGISTER_COLUMNS:
            out.append(f"a condition names {field}, which is not a register column")
        if op not in REGISTER_OPERATORS:
            out.append(f"a condition's operator is one of {', '.join(REGISTER_OPERATORS)}")
            continue
        dated = field in REGISTER_DATE_COLUMNS or (details.get(field) or {}).get("type") == "Date"
        if dated and op not in ("is set", "is not set"):
            out.append(f'{field} is a date: a condition on it uses "is set" or "is not set"')
        elif op not in ("is set", "is not set") and (
            c.get("value") is None or isinstance(c.get("value"), (bool, dict, list))
        ):
            out.append(f"The condition on {field} needs a plain value.")
        elif op in (">", ">=", "<", "<="):
            try:
                float(c.get("value"))
            except (TypeError, ValueError):
                out.append(f"A condition with {op} needs a number.")
    return out


def _register_books(v: _V):
    seen: set = set()
    for i, b in enumerate(v.list_of("register_books")):
        w, name = f"register_books[{i}]", b.get("book")
        if "register_stores" in b:
            v.refuse(
                w,
                name,
                "register_stores is the shop's own setup, mapped on its Desk; a manifest does not carry it",
            )
        _keys(v, w, name, b, BOOK_KEYS | {"register_stores"})
        if not isinstance(name, str) or not _BOOK_RE.match(name):
            v.refuse(w, name, "book is the book's id: lower-case words, optionally data_set.book")
        elif name in seen:
            v.refuse(w, name, "two books with one id")
        seen.add(name)
        if not isinstance(b.get("data_set"), str) or not _DATA_SET_RE.match(b["data_set"]):
            v.refuse(w, name, "data_set is the id of the set of books, lower-case words")
        for key in ("title", "cite", "count_role"):
            if not isinstance(b.get(key), str) or not b[key].strip():
                v.refuse(w, name, f"a book names its {key}")
            v.no_script(f"{w}.{key}", name, b.get(key))
        for key in ("enabled", "certified", "balance"):
            if not _flag(b.get(key)):
                v.refuse(w, name, f"{key} is 0 or 1")
        if "count_witness" in b and not _flag(b["count_witness"]):
            v.refuse(w, name, "count_witness is 0 or 1")
        if b.get("numbering") not in REGISTER_NUMBERING:
            v.refuse(w, name, f"numbering is {' or '.join(REGISTER_NUMBERING)}")
        if "medium" in b and b["medium"] not in REGISTER_MEDIA:
            v.refuse(w, name, f"medium is one of {', '.join(REGISTER_MEDIA)}")
        if b.get("correction") not in REGISTER_CORRECTIONS:
            v.refuse(w, name, f"correction is one of {', '.join(REGISTER_CORRECTIONS)}")
        if (
            not isinstance(b.get("retention_years"), int)
            or isinstance(b.get("retention_years"), bool)
            or b["retention_years"] < 1
        ):
            v.refuse(w, name, "retention_years is a whole number of years, at least 1")
        if ("period_months" in b) != ("return_due_days" in b):
            v.refuse(w, name, "period_months and return_due_days: both or neither")
        elif "period_months" in b and (
            b["period_months"] not in REGISTER_PERIOD_MONTHS
            or not isinstance(b["return_due_days"], int)
            or b["return_due_days"] < 0
        ):
            v.refuse(
                w,
                name,
                "a period is 1, 2, 3, 4, 6 or 12 months, its return due 0 or more days after",
            )
        items = b.get("items")
        if (
            not isinstance(items, dict)
            or len(items) != 1
            or set(items) - {"classes", "item_groups"}
        ):
            v.refuse(w, name, "items names classes or item_groups, one of the two")
        elif not isinstance(next(iter(items.values())), list) or not next(iter(items.values())):
            v.refuse(w, name, "items lists at least one class or item group")
        elif "classes" in items and not isinstance(b.get("class_source"), dict):
            v.refuse(w, name, "a book that takes classes names its class_source")
        details = b.get("details") if isinstance(b.get("details"), dict) else {}
        if "details" in b and not isinstance(b["details"], dict):
            v.refuse(w, name, "details maps detail_1 … detail_6 to a label and a source")
        for slot, d in details.items():
            if slot not in REGISTER_DETAILS or not isinstance(d, dict):
                v.refuse(w, name, f"{slot} is not a detail slot (detail_1 … detail_6)")
            else:
                v.no_script(f"{w}.details.{slot}", name, d.get("label"))
        for r in _register_condition_refusals(b.get("conditions", []), details):
            v.refuse(f"{w}.conditions", name, r)
        req = b.get("required", [])
        if not isinstance(req, list) or any(k not in REGISTER_COLUMNS for k in req):
            v.refuse(w, name, "required lists register columns")
        else:
            for k in req:
                d = details.get(k) if isinstance(details.get(k), dict) else {}
                if k in REGISTER_DETAILS and not (
                    d.get("pos_sale_detail") or d.get("desk_field") or d.get("record")
                ):
                    v.refuse(w, name, f"{k} is required but has no source to fill it.")
        cols = b.get("columns")
        if not isinstance(cols, list) or not cols:
            v.refuse(w, name, "a book prints at least one column")
        else:
            for col in cols:
                if (
                    not isinstance(col, dict)
                    or not isinstance(col.get("label"), str)
                    or not isinstance(col.get("value"), list)
                    or not col["value"]
                    or any(
                        k not in REGISTER_COLUMNS + REGISTER_PRINT_COLUMNS for k in col["value"]
                    )
                    or not isinstance(col.get("group", "-"), str)
                    or not col.get("group", "-").strip()
                ):
                    v.refuse(w, name, "a column is a label and the register columns it prints")
                    break
                v.no_script(f"{w}.columns", name, col.get("label"))
        for key in ("authority", "columns_from", "class_source"):
            if key in b and not isinstance(b[key], dict):
                v.refuse(w, name, f"{key} is an object")


def warnings(m) -> list[dict]:
    """What installs but needs the shop before it works, each ``{what, where, text}``. The product refuses a fiscal
    reader at ENABLE, not at insert (its writer rule runs only on an enabled reader), so the kit names it here.
    """
    out = []
    if not isinstance(m, dict):
        return out
    # print formats warn with or without fiscal readers
    pf = _print_format_warnings(m)
    if not isinstance(m.get("fiscal_readers"), list):
        return pf
    own = {
        c.get("fieldname"): c
        for c in m.get("custom_fields") or []
        if isinstance(c, dict) and c.get("dt") == FISCAL_DT
    }
    for i, r in enumerate(x for x in m["fiscal_readers"] if isinstance(x, dict)):
        w = f"fiscal_readers[{i}]"

        def warn(what, text):
            out.append({"what": what, "where": w, "text": text})

        level = r.get("writer_level")
        if level == 1:
            warn(
                "level_one",
                "Accounts Manager writes POS Invoice at level 1 on our test shop (the fiscal reader "
                "extension point reads that from iVendNext's own permission rows), so the shop could "
                "not switch this reader on there: use a level no other role writes",
            )
        for k in RESULT_KEYS:
            f = own.get(r.get(k))
            if not f:
                continue
            if not f.get("no_copy"):
                warn(
                    "no_copy",
                    f"{f['fieldname']} is not No Copy: the product refuses to switch the reader on (a copied "
                    "sale would carry another sale's result)",
                )
            if not f.get("allow_on_submit"):
                warn(
                    "allow_on_submit",
                    f"{f['fieldname']} is not allow-on-submit: the service cannot write it once the "
                    "sale is submitted, so no receipt is ever cleared",
                )
        if not r.get("writer_users"):
            warn(
                "no_writer_user",
                "no integration user: the shop gives the writer role to its service's user and lists "
                "that user in the reader's writer users",
            )
        warn(
            "level_zero",
            f"the writer role gets read and write at level {level} on POS Invoice only, and the "
            "integration users no API key: the service can reach nothing until the shop grants the role "
            "read, write and submit at level 0 (with them it can change any level-0 field a submitted "
            "sale still allows and submit a draft sale) and generates each user's API key",
        )
    return out + pf


def validate(m) -> list[dict]:
    """Every refusal, each ``{where, name, reason}``. An empty list means the manifest may be installed."""
    if not isinstance(m, dict):
        return [{"where": "", "name": None, "reason": "a manifest is a JSON object"}]
    v = _V(m)
    if m.get("manifest_version") not in VERSIONS:
        v.refuse(
            "manifest_version",
            None,
            f"this installer reads manifest_version {' or '.join(map(str, VERSIONS))}",
        )
    if not isinstance(m.get("prefix"), str) or not _PREFIX_RE.match(m["prefix"]):
        v.refuse(
            "prefix", m.get("prefix"), "the prefix is one to three upper-case words, e.g. 'PP BLN'"
        )
    elif m["prefix"].split()[0] in RESERVED_PREFIX_WORDS:
        v.refuse(
            "prefix",
            m["prefix"],
            f"a prefix cannot start with {m['prefix'].split()[0]}: the system reads fields whose "
            "names start that way",
        )
    if (
        not isinstance(m.get("app"), str)
        or not _APP_RE.match(m["app"])
        or (v.prefix and m["app"] != app_for(v.prefix))
    ):
        v.refuse(
            "app",
            m.get("app"),
            "the app name is the prefix in lower case with underscores, e.g. 'pp_bln'",
        )
    if not isinstance(m.get("version"), str) or not _VERSION_RE.match(m["version"]):
        v.refuse(
            "version",
            m.get("version") if isinstance(m.get("version"), str) else None,
            VERSION_REASON,
        )
    for k in m:
        if k in REFUSED_KINDS:
            v.refuse(k, None, REFUSED_KINDS[k])
        elif k in WAITING_KINDS:
            v.refuse(k, None, WAITING_KINDS[k])
        elif k in POINT_KINDS:
            point, spec = POINT_KINDS[k]
            v.refuse(
                k,
                None,
                f"'{k}' is a declaration the '{point}' extension point reads; it is refused until the "
                f"'{point}' extension point has shipped on this site ({spec})",
            )
        elif k in KINDS_V2 and m.get("manifest_version") != 2:
            v.refuse(k, None, f"'{k}' needs manifest_version 2")
        elif k not in TOP_KEYS:
            v.refuse(k, None, f"'{k}' is not a kind a manifest may carry")
    if "allowed_urls" in m and (
        not isinstance(m["allowed_urls"], list)
        or any(not isinstance(u, str) or not _URL_RE.match(u) for u in m["allowed_urls"])
    ):
        v.refuse("allowed_urls", None, "allowed_urls is a list of plain http(s) addresses")
    v2 = (
        (
            _reports,
            _number_cards,
            _dashboard_charts,
            _dashboards,
            _list_settings,
            _workflows,
            _naming_rules,
            _links,
            _registered_applications,
            _remote_keys,
            _extension_modules,
            _extension_subscriptions,
            _desk_actions,
            _save_rules,
            _fiscal_readers,
            _scan_sources,
            _field_rules,
            _label_layouts,
            _list_marks,
            _register_books,
        )
        if m.get("manifest_version") == 2
        else ()
    )
    for check in (
        _doctypes,
        _custom_fields,
        _property_setters,
        _print_formats,
        _notifications,
        _workspaces,
        _sale_attributes,
        _webhooks,
        *v2,
        _singles,
        _limited_in_templates,
    ):
        check(v)
    return v.out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: validate.py <manifest.json>")
    manifest = json.load(open(sys.argv[1]))
    refusals = validate(manifest)
    for wn in [] if refusals else warnings(manifest):
        print(f"WARNING {wn['where']}: {wn['text']}")
    for r in refusals:
        print(f"REFUSED {r['where']}{' (' + r['name'] + ')' if r['name'] else ''}: {r['reason']}")
    print("VALID" if not refusals else f"{len(refusals)} refusal(s)")
    sys.exit(1 if refusals else 0)
