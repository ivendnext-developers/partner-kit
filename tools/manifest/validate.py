# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/business_logic/manifest_check.py,
# at development 99b5d44fb7a39d290df054788a2bfe847bc700b4. The shop's own checker (the install screen runs it) is the source;
# this copy lets you check a manifest before you send it, and refuses the same manifests in the same words. Everything
# below this header equals the source. A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""The companion manifest — the VALIDATOR. Pure Python: no framework import, no network.

A partner's own data (record types, fields, print formats, notifications, workspaces, sale details, webhooks)
ships as one ``manifest.json``. Allow by default: a manifest may do what the shop's
administrator can do in Desk. It is refused only where it would book a wrong money, tax, stock or fiscal figure
(A), stop the till's own sale or customer saving (T), send the shop's data somewhere the consent does not show
(B), or let someone act as someone else, code in the shop's saves included (C); and where the installer cannot
read it (S). Every refusal is on one list, with its reason: ``docs/extending/what_an_app_may_not_do.md``
(``ci/check_gate_list.py`` fails the build on a refusal outside it). The framework and the product refuse the rest at
insert, in their own words. The shop's installer (``manifest_install.py``) calls ``validate()`` before it installs.

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
``db.get_value`` …) whose quoted record type is one ``ivn_rows`` serves is refused (``PRINT_SERVED_TYPES``,
and, since 2.1.0.668, the manifest's own served types; the framework's own types, such as Address, child tables and
whole-record reads have no replacement and stay warned, and so does another package's type: the check reads one
manifest, and which packages a site holds changes after it). ``ivn_rows`` and ``ivn_value`` apply the rights.
"""

from __future__ import annotations

import json
import re
import sys

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
    # the regulated-stock register books (the register door)
    "register_books",
    # the package's own words, one entry per language (the framework's Translation records)
    "translations",
)
KINDS = KINDS_V1 + KINDS_V2
# the manifest's own keys beside its kinds
TOP_KEYS = {"manifest_version", "app", "prefix", "title", "version", "publisher", "description"}
TOP_KEYS |= {"allowed_urls"}
STD_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}

# ── the till's own records: ONE list (save_rules and partner_doccheck read it from here) ──
# a sale the till booked and the day close (save rules only flag them; FLAG_ONLY)
TILL_SALE = frozenset({"POS Invoice", "POS Closing Entry", "POS Invoice Merge Log"})
# ... and the day's opening (never a document check's target; REFUSED_TARGETS)
TILL_DAY = TILL_SALE | {"POS Opening Entry"}
# what the back office writes for each sale or stock move (ENGINE_POSTED)
ENGINE_POSTED = frozenset(
    {"Serial and Batch Bundle", "Repost Item Valuation", "Stock Reservation Entry"}
)
# what the till's booking inserts (TILL_INSERTS)
TILL_INSERTS = frozenset(
    {"Sales Order", "Sales Invoice", "Delivery Note", "Payment Entry", "Journal Entry"}
)
# a new customer at the counter (api/customer.py, api/capture.py, api/fulfilment.py)
TILL_PARTIES = frozenset({"Customer", "Contact", "Address"})
# the engine's ledgers, written from code at every posting (A), the till's included
LEDGERS = frozenset(
    {"GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Advance Payment Ledger Entry"}
)
# a cash expense the till's Cash In Out submits (it posts to the books)
TILL_EXPENSE = frozenset({"Store Expense"})
# what the till writes inside its own saves: a manager's override, a sale's loyalty points and
# coupon count, a card terminal's log, a partner's code
TILL_WRITES = frozenset(
    {
        "Manager Override Log",
        "Loyalty Point Entry",
        "Coupon Code",
        "Retail Card Terminal Txn",
        "Retail Partner Code",
    }
)
TILL_RECORDS = (
    TILL_DAY | ENGINE_POSTED | TILL_INSERTS | TILL_PARTIES | LEDGERS | TILL_EXPENSE | TILL_WRITES
)
# record types that post to the ledgers (A: a default or precision there changes a posted figure)
POSTING = (
    TILL_DAY
    | TILL_INSERTS
    | LEDGERS
    | TILL_EXPENSE
    | {
        "Purchase Invoice",
        "Purchase Receipt",
        "Stock Entry",
        "Stock Reconciliation",
        "Landed Cost Voucher",
        "Asset",
        "Asset Capitalization",
        "Asset Value Adjustment",
        "Period Closing Voucher",
        "Invoice Discounting",
        "Exchange Rate Revaluation",
        "Subcontracting Receipt",
    }
)
# rows several of those share (a sale's or a purchase's own rows are named after it, e.g. POS Invoice Item)
SHARED_ROWS = frozenset(
    {
        "Sales Taxes and Charges",
        "Purchase Taxes and Charges",
        "Advance Taxes and Charges",
        "Payment Schedule",
        "Serial and Batch Entry",
        "Packed Item",
        "Sales Team",
        "Landed Cost Item",
        "Landed Cost Taxes and Charges",
        "Dynamic Link",
    }
)
# what stops a save when set on a field (T on the till's records)
SAVE_STOPPERS = {
    "reqd",
    "unique",
    "non_negative",
    "length",
    "set_only_once",
    "default",
    "precision",
    "options",
    "fieldtype",
}
POSTED_FIGURES = {"default", "precision"}  # A on a record type that posts
# a name that starts like one of those but is a master, never its rows (Customer Group)
MASTERS = {"Group", "Template", "Type", "Category", "Settings"}


def _within(dt, types) -> bool:
    """``dt`` is one of ``types`` or one of their rows (named after the record type, or a shared row)."""
    return isinstance(dt, str) and (
        dt in types
        or (dt in SHARED_ROWS and types is not LEDGERS)
        or any(dt.startswith(t + " ") and dt.rsplit(" ", 1)[1] not in MASTERS for t in types)
    )


def field_refusal(dt, props, own_field=False) -> str | None:
    """Why a field change on ``dt`` is refused (A or T), or None. ``props``: the field keys it sets;
    ``own_field``: a field the app adds (prefixed, so the engine never reads its default)."""
    props = set(props)
    if _within(dt, LEDGERS) and props & (POSTED_FIGURES | {"reqd"}):
        return (
            "the engine writes every ledger row from code: a required field, a default or a "
            "precision there changes the books"
        )
    if _within(dt, TILL_RECORDS) and props & SAVE_STOPPERS:
        return (
            f"{sorted(props & SAVE_STOPPERS)[0]} on {dt} can stop the till saving a sale or a new "
            "customer at the counter"
        )
    if _within(dt, POSTING) and props & POSTED_FIGURES and not own_field:
        return f"{dt} posts to the books: a default or a precision there changes a posted figure"
    return None


# Kinds a manifest may NOT carry, each with the reason a partner reads.
REFUSED_KINDS = {
    "server_scripts": "a server script runs partner code inside the shop's own saves; partners use a till key "
    "or a connected app instead",
    "client_scripts": "a client script runs partner code in the browser of every Desk user who opens the form",
    "web_pages": "a web page is published on the shop's own web address and can carry script or pass itself "
    "off as the shop",
    "web_templates": "a web template puts partner markup on every web page that uses it",
}
# S: what the installer reads each kind's entries by
KEYED = {
    "doctypes": ("name", "fields"),
    "custom_fields": ("dt", "fieldname"),
    "property_setters": ("doc_type", "property", "value"),
    "print_formats": ("name", "doc_type"),
    "notifications": ("name", "document_type"),
    "workspaces": ("name",),
    "sale_attributes": ("name",),
    "webhooks": ("name", "doctype", "event", "url"),
    "reports": ("name", "ref_doctype", "columns"),
    "number_cards": ("name", "document_type"),
    "dashboard_charts": ("name", "document_type", "chart_type"),
    "dashboards": ("name", "charts"),
    "list_settings": ("doctype",),
    "workflows": ("name", "document_type", "states", "transitions"),
    "naming_rules": ("document_type", "prefix"),
    "links": ("doctype", "link_doctype", "link_fieldname"),
    "registered_applications": ("name", "events"),
    "remote_keys": ("key", "label", "endpoint_url"),
    "extension_modules": ("key", "point", "sha256", "version"),
    "extension_subscriptions": ("key", "point"),
    "desk_actions": ("record_type", "service"),
    "save_rules": ("rule_name", "record_type"),
    "fiscal_readers": ("writer_role",),
    "scan_sources": ("source_name", "record_type"),
    "field_rules": ("theme", "field"),
    "label_layouts": ("label_name",),
    "list_marks": ("record_type", "label"),
    "register_books": ("book",),
    "translations": ("language",),
}
NUMBERING = {"autoname", "naming_rule"}  # a record type's own numbering, set by a property setter
RECIPIENT_KEYS = {
    "receiver_by_role",
    "receiver_by_document_field",
    "condition",
}  # condition: C below
ATTACH_FILE_KEYS = ("attach_files", "from_attach_field")
# a notification's condition: a field compared with a plain value, joined by and / or (no call)
_PLAIN_TERM = (
    r"doc\.[a-z][a-z0-9_]*(\s*(==|!=|<=|>=|<|>)\s*"
    r"('[^'\\\n]*'|\"[^\"\\\n]*\"|-?\d+(\.\d+)?|None|True|False))?"
)
_PLAIN_CONDITION_RE = re.compile(rf"(not\s+)?{_PLAIN_TERM}(\s+(and|or)\s+(not\s+)?{_PLAIN_TERM})*")
NOTIFY_CODE_REASON = (
    "a notification's condition, subject and message are evaluated with a Server Script's globals, "
    "database writes included, inside the save that sends it: compare the record's own fields "
    "(doc.grand_total > 50000) and show them ({{ doc.field }}), with no call"
)
SHORTCUT_SCRIPT_KEYS = {"stats_filter", "format", "color"}

REFUSED_FIELD_TYPES = {
    "HTML": "an HTML field shows its own markup in Desk, which can carry script",
}
# The nine rights the framework's permission record switches ON by default (its permission record's definition file; every other
# right defaults 0). Re-read that file on a framework update: a new default-ON right must join this list.
RIGHTS = ("read", "write", "create", "delete", "report", "export", "share", "print", "email")
# Roles the framework gives users by itself (its permission module's automatic roles; `Guest` is refused on its own, below): `All` goes to every
# signed-in user, website customers included, `Desk User` to every staff user, `Administrator` is the superuser. A manifest names none of them.
AUTOMATIC_ROLES = ("All", "Desk User", "Administrator")


def _norm(role: str) -> str:
    # measured on the bench: the database finds a role without regard to case or a trailing space, so `all` or `Guest ` is stored
    # as the real role; compare the same way.
    return role.strip().casefold()


# ... and without regard to accents either (`Àll`, `Guèst` were stored as All, Guest; measured), and the same collation ignores hidden
# characters. A Python compare cannot follow it, so a role name is plain ASCII: the shop's roles are (Retail Manager, System Manager).
_PLAIN_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")


def _odd(role) -> bool:
    return isinstance(role, str) and not _PLAIN_ROLE.match(role)


def _guest(role) -> bool:
    return isinstance(role, str) and _norm(role) == "guest"


def _automatic(role) -> bool:
    return isinstance(role, str) and _norm(role) in {_norm(r) for r in AUTOMATIC_ROLES}


PUBLIC_REASON = (
    "Guest and All open the app's records to people outside the shop's staff (visitors who are not "
    "signed in, and the shop's website customers): name a role of the shop's staff"
)


def _public(role) -> bool:
    return _guest(role) or isinstance(role, str) and _norm(role) == "all"


# A field the manifest adds names the roles that change it (``write_roles``, who read it too) and,
# optionally, the roles that read it (``read_roles``; left out: every role that reads the record type when
# the app installs). The installer puts the field at a permission level of its own on that record type,
# with one permission row per role (``manifest_install._apply_limits``); the till shows, searches and
# carries offline a Customer field only for a user who reads it, and an Item field above level 0 never.
LIMIT_KEYS = ("read_roles", "write_roles")
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
SINGLE_RIGHTS = ("report", "export")  # the framework strips both from a single's permission rows
NOTIFY_CHANNELS = {"Email", "System Notification"}

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
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/\-]*)?$")
# A help address. Desk writes a record type's `documentation` into the empty list's Need Help? link and a
# field's `documentation_url` into its help icon, unchecked — so the value is https only, with no quote, space,
# `<` or `>` (the quote-safe shape of _URL_RE, plus a #heading), matched whole (a `$` lets a newline through).
_HELP_URL_RE = re.compile(
    r"https://[A-Za-z0-9.\-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/\-]*)?(#[A-Za-z0-9._~\-]*)?"
)
HELP_PROPS = {"documentation", "documentation_url"}


def help_address_ok(value) -> bool:
    return isinstance(value, str) and _HELP_URL_RE.fullmatch(value) is not None


# Script in markup: a script, frame or object element, an inline event handler, or a javascript: address.
# What leaves the shop. A manifest may hold templates that read the shop's data (the framework gives every template
# get_all, get_doc, db.get_value — verified); that is fine where the output stays with the shop's
# staff, and a leak wherever it leaves: a webhook body sent to the partner, an address a print format loads (an image
# URL can carry data out), a notification sent to an address the manifest names.
_OUTSIDE_URL_RE = re.compile(r"(https?:)?//[A-Za-z0-9]", re.I)
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
    "a row or value read of a record type ivn_rows serves, and of this app's own; another app's is only warned"
)
# Since 2.1.0: the framework's row and value readers (the pattern below) whose record type is a quoted first
# argument or a quoted `doctype=`; group 1 or 2 is the type. ivn_rows / ivn_value replace exactly these.
# ⚠ A whole-record reader (get_doc …: its child rows have no ivn_rows door), a render, a map or a count, an
# alias of the framework's database object, a subscript or a built name stays warned.
_PRINT_TYPED_READ_RE = re.compile(
    r"\bfrappe\s*\.\s*(?:get_all|get_list|db\s*\.\s*(?:get_value|get_all|get_list))"
    r"""\s*\(\s*(?:doctype\s*=\s*)?(?:'([^'\\]*)'|"([^"\\]*)")"""
)
# The record types ivn_rows serves (template_readers._record_type_refusal is None), read on the CI site
# migrated to the 2.1.0 release. ⚠ Pinned by test_template_readers: every name here is
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
            "Retail Kitchen Ticket",
            "Retail Label Layout|Retail Layaway Plan|Retail List Mark",
            "Retail Open Check|Retail Open Check Claim|Retail Open Check Event",
            "Retail Option Group|Retail Override Request|Retail PIN Event|Retail POS Theme",
            "Retail Payer Record|Retail Permission|Retail Provisional Series|Retail Register Book",
            "Retail Register Count|Retail Register Erasure|Retail Register Line",
            "Retail Register Period|Retail Register Sequence|Retail Register State",
            "Retail Save Rule",
            "Retail Save Rule Count|Retail Scan Source|Retail Time Clock Entry|Retail UX Metric",
            "Routing|SMS Log",
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
# P-NOTIFYDATE: the two date events match no save event (the framework's save runs only the notifications
# whose event is the save's own); the daily scheduler sends them. So on a shop's own record type a manifest may ship
# those two, and nothing that would read more than the record or write back into it from the scheduler.
DATE_EVENTS = {"Days Before", "Days After"}


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
        self.urls = (
            set(m.get("allowed_urls") or []) if isinstance(m.get("allowed_urls"), list) else set()
        )
        self.results = _result_fields(m) if isinstance(m.get("fiscal_readers"), list) else set()

    def refuse(self, where: str, name, reason: str):
        self.out.append(
            {"where": where, "name": name if isinstance(name, str) else None, "reason": reason}
        )

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


def _keyed(v: _V):
    """S: an entry names what the installer reads it by (the framework and the product refuse the rest)."""
    for kind, keys in KEYED.items():
        items = v.m.get(kind)
        for i, el in enumerate(items if isinstance(items, list) else []):
            missing = [k for k in keys if isinstance(el, dict) and el.get(k) in (None, "", [])]
            if missing:
                v.refuse(
                    f"{kind}[{i}]",
                    el.get("name"),
                    f"an entry of {kind} names its {', '.join(missing)}: the installer reads it by them",
                )


def _numbered(dt) -> str | None:
    """A: the sale's own records are numbered by the shop's series, which the books and the tax authority read."""
    if dt in TILL_DAY | {"Sales Invoice"}:
        return (
            f"{dt} is numbered by the shop's own series, which its books and its tax authority "
            "read: a manifest numbers other record types"
        )
    return None


def _fields(v: _V, where: str, owner: str, fields: list, engine: bool, single: bool = False):
    for i, f in enumerate(fields):
        w = where if single else f"{where}[{i}]"
        if not isinstance(f, dict):
            v.refuse(w, None, "a field must be an object")
            continue
        fn, ft = f.get("fieldname"), f.get("fieldtype")
        if engine and isinstance(fn, str) and not fn.startswith(v.fprefix):
            v.refuse(
                w,
                fn,
                f"a field added to a shop's own record type starts with '{v.fprefix}': the engine "
                "reads fields named like its own flags",
            )
        if ft in REFUSED_FIELD_TYPES:
            v.refuse(w, fn, REFUSED_FIELD_TYPES[ft])
        why = engine and field_refusal(
            owner, {k for k, x in f.items() if x} - {"fieldtype", "options"}, own_field=True
        )
        if why:
            v.refuse(w, fn, why)
        for k in sorted(set(f) & DEPENDS_KEYS):
            if not isinstance(f[k], str) or not _COND_RE.match(f[k].strip()):
                v.refuse(w, fn, EVAL_REASON)
        v.no_script(w, fn, f.get("description"))
        v.no_script(w, fn, f.get("label"))  # Desk writes a field's label raw too


def _doctypes(v: _V):
    for i, d in enumerate(v.list_of("doctypes")):
        w, name = f"doctypes[{i}]", d.get("name")
        v.no_script(f"{w}.description", name, d.get("description"))  # the empty list shows it raw
        if isinstance(d.get("fields"), list):
            _fields(v, f"{w}.fields", name, d["fields"], engine=False)
        for j, p in enumerate(
            d.get("permissions") if isinstance(d.get("permissions"), list) else []
        ):
            if isinstance(p, dict):
                _roles(v, f"{w}.permissions[{j}]", name, [p.get("role")])


def _custom_fields(v: _V):
    for i, c in enumerate(v.list_of("custom_fields")):
        w, dt = f"custom_fields[{i}]", c.get("dt")
        _fields(v, w, dt, [c], engine=dt not in v.own, single=True)
        _limits(v, w, dt, c)


def _limits(v: _V, w: str, dt: str, c: dict):
    """``read_roles`` / ``write_roles`` on a field the manifest adds."""
    fn = c.get("fieldname")
    for k in LIMIT_KEYS:
        _roles(v, w, fn, c.get(k))
    if (dt, fn) in v.results and any(k in c for k in LIMIT_KEYS):
        v.refuse(
            w,
            fn,
            "a fiscal reader's result field sits at the reader's writer_level; its writer role is the "
            "reader's",
        )


def _property_setters(v: _V):
    for i, p in enumerate(v.list_of("property_setters")):
        w, dt, fn, prop = (
            f"property_setters[{i}]",
            p.get("doc_type"),
            p.get("field_name"),
            p.get("property"),
        )
        label = f"{dt}-{fn or ''}-{prop}"
        if prop in DEPENDS_KEYS and not _COND_RE.match(str(p.get("value")).strip()):
            v.refuse(w, label, EVAL_REASON)
        # Desk writes several setter values raw (a field's description and label, a record type's
        # description), so every setter is checked as the text the installer stores, str(value)
        v.no_script(w, label, str(p.get("value")))
        if dt in v.own:
            continue
        why = field_refusal(dt, {prop}) if fn else _numbered(dt) if prop in NUMBERING else None
        if why:
            v.refuse(w, label, why)


def _print_formats(v: _V):
    own = _own_served(v.m)
    for i, p in enumerate(v.list_of("print_formats")):
        w, name = f"print_formats[{i}]", p.get("name")
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
            for rt in _served_reads(p.get(k), own):
                v.refuse(
                    f"{w}.{k}",
                    name,
                    f"a print format may not read {rt} through the framework's own helpers, which skip "
                    "the viewer's rights (a share-key visitor would see what they return): read it "
                    "through ivn_rows or ivn_value, or show the printed record's own fields",
                )


def _own_served(m: dict) -> set[str]:
    """The manifest's own record types ivn_rows serves once installed — not a table, single
    or virtual type, nor one holding a password."""

    def listed(x):
        return x if isinstance(x, list) else []

    return {
        d["name"]
        for d in listed(m.get("doctypes"))
        if isinstance(d, dict)
        and isinstance(d.get("name"), str)
        and not any(d.get(k) for k in ("istable", "issingle", "is_virtual"))
        and not any(
            isinstance(f, dict) and f.get("fieldtype") == "Password"
            for f in listed(d.get("fields"))
        )
    }


def _served_reads(text, own=()) -> list[str]:
    """The record types ivn_rows serves (``own``: the manifest's own) that a print reads through a
    framework helper, once each."""
    served = {t.casefold(): t for t in (*PRINT_SERVED_TYPES, *own)}
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
        w, name, dt = f"notifications[{i}]", n.get("name"), n.get("document_type")
        if n.get("channel", "Email") not in NOTIFY_CHANNELS:
            v.refuse(
                w,
                name,
                "a notification uses e-mail or the in-app bell: another channel sends through an "
                "outside service the consent cannot name",
            )
        if _within(dt, TILL_RECORDS) and n.get("event") not in DATE_EVENTS:
            v.refuse(
                w,
                name,
                f"on {dt}, one of the till's own records, a notification is Days Before or Days After "
                "a date: any other event runs inside the till's save, and an error in it stops the sale",
            )
        v.no_script(f"{w}.message", name, n.get("message"))
        # its condition, subject and message are evaluated with a Server Script's globals (database
        # writes included), inside the save that sends it: a condition is a plain comparison only
        conditions = [n.get("condition")] + [
            r.get("condition") for r in n.get("recipients") or [] if isinstance(r, dict)
        ]
        if any(c and not _PLAIN_CONDITION_RE.fullmatch(str(c).strip()) for c in conditions):
            v.refuse(w, name, NOTIFY_CODE_REASON)
        for k in ("subject", "message"):
            if isinstance(n.get(k), str) and _SHOP_DATA_RE.search(n[k]):
                v.refuse(f"{w}.{k}", name, NOTIFY_CODE_REASON)
        # the framework sets this field after each alert and saves the record: the app's own field only
        prop = n.get("set_property_after_alert")
        if prop and (prop not in _own_fields(v, dt) - STD_FIELDS or (dt, prop) in v.results):
            v.refuse(
                w,
                name,
                "set_property_after_alert names one of the app's own fields: the record is saved after "
                "each alert, so a standard field (a discount, a status) would change a figure",
            )
        for k in ATTACH_FILE_KEYS:
            if k in n:
                v.refuse(
                    f"{w}.{k}",
                    name,
                    "a file named by a field can be any private file on the site, mailed with no "
                    "rights check to an address the consent does not show",
                )
        defaults = {f.get("fieldname") for f in _added_fields(v, dt) if f.get("default")}
        for j, rcp in enumerate(n.get("recipients") or []):
            if not isinstance(rcp, dict) or set(rcp) - RECIPIENT_KEYS:
                v.refuse(
                    f"{w}.recipients[{j}]",
                    name,
                    "a notification goes to the shop's own people, by role or by a field of the record "
                    "(the consent names both), never to an address the manifest names",
                )
            elif rcp.get("receiver_by_document_field") in defaults:
                v.refuse(
                    f"{w}.recipients[{j}]",
                    name,
                    "a recipient field the app gives a default would mail an address the consent does "
                    "not show: leave the default out and let the shop fill the field",
                )
            else:
                _roles(v, f"{w}.recipients[{j}]", name, [rcp.get("receiver_by_role")])


_ICON_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def _workspaces(v: _V):
    for i, ws in enumerate(v.list_of("workspaces")):
        w, name = f"workspaces[{i}]", ws.get("name")
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
            if isinstance(b, dict) and b.get("type") == "custom_block":
                v.refuse(
                    bw,
                    name,
                    "a custom block carries script that runs in the browser of everyone who opens "
                    "the workspace, administrators included",
                )
            elif isinstance(b, dict):
                v.no_script(bw, name, json.dumps(b.get("data") or {}))
        for j, s in enumerate(ws.get("shortcuts") or []):
            sw = f"{w}.shortcuts[{j}]"
            if isinstance(s, dict) and set(s) & SHORTCUT_SCRIPT_KEYS:
                v.refuse(
                    sw,
                    name,
                    "a shortcut carries no stats_filter, format or color: Desk runs the filter as "
                    "script in every viewer's browser and writes the other two raw",
                )
            label = s.get("label") if isinstance(s, dict) else None
            if isinstance(label, str) and set(label) & set('<>"&'):
                v.refuse(sw, name, 'a shortcut label is plain text, with no <, >, " or &')


def _sale_attributes(v: _V):
    for i, a in enumerate(v.list_of("sale_attributes")):
        if a.get("required"):
            v.refuse(
                f"sale_attributes[{i}]",
                a.get("name"),
                "a required sale detail would stop every sale on every till that does not fill it",
            )


def _webhooks(v: _V):
    for i, h in enumerate(v.list_of("webhooks")):
        w, name = f"webhooks[{i}]", h.get("name")
        if h.get("url") not in v.urls:
            v.refuse(
                w,
                name,
                "a webhook calls an address the manifest lists in allowed_urls: the consent shows the "
                "shop each one",
            )
        if "json" in h:
            v.refuse(
                w,
                name,
                "a webhook sends the thin body (record type, name, event, time): a body of its own is a "
                "template that can read any record without rights and send it to the address; your "
                "service reads the record with its own key",
            )
        if h.get("condition") and _within(h.get("doctype"), TILL_RECORDS):
            v.refuse(
                w,
                name,
                f"a webhook condition on {h.get('doctype')}, one of the till's own records, runs inside "
                "every save of it, and an error in it stops the sale; filter in your own service",
            )


# ── v2 kinds ─────────────────────────────────────────────────────────────────


def _own_doctype(v: _V, dt: str) -> list:
    """The fields a manifest gives its own record type ``dt``."""
    d = next(
        (d for d in v.m.get("doctypes") or [] if isinstance(d, dict) and d.get("name") == dt), None
    )
    return [f for f in (d or {}).get("fields") or [] if isinstance(f, dict)]


def _added_fields(v: _V, dt: str) -> list:
    """The fields a manifest gives ``dt``: its own record type's, or the ones it adds to the shop's."""
    added = [
        c for c in v.m.get("custom_fields") or [] if isinstance(c, dict) and c.get("dt") == dt
    ]
    return _own_doctype(v, dt) + added


def _own_fields(v: _V, dt: str) -> set:
    """The fields a manifest gives ``dt``: its own record type's, or the ones it adds to the shop's."""
    added = {
        c.get("fieldname")
        for c in v.m.get("custom_fields") or []
        if isinstance(c, dict) and c.get("dt") == dt
    }
    return {f.get("fieldname") for f in _own_doctype(v, dt)} | added | STD_FIELDS


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


def _reports(v: _V):
    for i, r in enumerate(v.list_of("reports")):
        w, name = f"reports[{i}]", r.get("name")
        kind = r.get("report_type", "Report Builder")
        if kind == "Query Report":
            v.refuse(
                w,
                name,
                "a query report is SQL text run against the shop's whole database; use Report Builder",
            )
        elif kind == "Script Report":
            v.refuse(w, name, "a script report is Python run inside the shop; use Report Builder")
        ob = r.get("order_by")
        if ob is not None and not (
            isinstance(ob, str) and re.match(r"^[a-z][a-z0-9_]{0,62}( (asc|desc))?$", ob)
        ):
            v.refuse(
                w,
                name,
                "order_by is one field name, optionally followed by asc or desc: it is written into "
                "the report's database query",
            )
        _roles(v, w, name, r.get("roles"))


def _roles(v: _V, w, name, roles):
    if isinstance(roles, list) and any(_public(x) for x in roles):
        v.refuse(w, name, PUBLIC_REASON)


def _dashboard_charts(v: _V):
    for i, c in enumerate(v.list_of("dashboard_charts")):
        _roles(v, f"dashboard_charts[{i}]", c.get("name"), c.get("roles"))


def _workflows(v: _V):
    for i, wf in enumerate(v.list_of("workflows")):
        w, name, dt = f"workflows[{i}]", wf.get("name"), wf.get("document_type")
        if _within(dt, TILL_RECORDS):
            v.refuse(
                w,
                name,
                f"a workflow on {dt}, one of the till's own records, would hold the till's sale or new "
                "customer for an approval nobody at the counter gives",
            )
            continue
        own = _own_fields(v, dt) - STD_FIELDS
        states, trs = wf.get("states"), wf.get("transitions")
        for j, st in enumerate(states if isinstance(states, list) else []):
            if not isinstance(st, dict):
                continue
            _roles(v, f"{w}.states[{j}]", name, [st.get("allow_edit")])
            if st.get("update_field") and st["update_field"] not in own:
                v.refuse(
                    f"{w}.states[{j}]",
                    name,
                    "update_field is one of the app's own fields: a workflow writes it and then submits, "
                    "so a standard field (a warehouse, a tax, a discount) would post a figure nobody chose",
                )
        for j, t in enumerate(trs if isinstance(trs, list) else []):
            if isinstance(t, dict):
                _roles(v, f"{w}.transitions[{j}]", name, [t.get("allowed")])


def _naming_rules(v: _V):
    for i, n in enumerate(v.list_of("naming_rules")):
        why = _numbered(n.get("document_type"))
        if why:
            v.refuse(f"naming_rules[{i}]", n.get("document_type"), why)


def _endpoint(v: _V, w: str, name, url):
    if not isinstance(url, str) or url not in v.urls or not url.startswith("https://"):
        v.refuse(
            w, name, "endpoint_url must be an https address the manifest lists in allowed_urls"
        )


def _remote_keys(v: _V):
    for i, k in enumerate(v.list_of("remote_keys")):
        _endpoint(v, f"remote_keys[{i}]", k.get("key"), k.get("endpoint_url"))


# ── the shipped extension points ─────────────────────────────────────────────
# The product validates every record when the installer inserts it (its own `validate`), and a refusal there is
# reported word for word; these checks refuse EARLY, in words a partner reads, only what the kit itself decides: what is
# switched on, what carries a secret, which address, which role, which record a declaration points at.

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
    # fixed — a payer service that cannot answer means no cover
    "payer": ("no_cover",),
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


def _extension_subscriptions(v: _V):
    for i, s in enumerate(v.list_of("extension_subscriptions")):
        w, key = f"extension_subscriptions[{i}]", s.get("key")
        if "max_discount_percent" in s:
            v.refuse(
                w,
                key,
                "the most a module may take off a line is the shop's to set: a manifest's service is "
                "installed at 0 and the shop raises it",
            )
        if s.get("transport", "remote") != "wasm":
            _endpoint(v, w, key, s.get("endpoint_url"))
        if s.get("point") == "payer":
            _payer_settings(v, w, key, s.get("settings"))
        _roles(v, w, key, s.get("page_roles"))


def _payer_settings(v: _V, w, key, settings) -> None:
    """The clearing mode is the shop's: its account is on the shop's own books."""
    if not isinstance(settings, dict):
        return
    if "clearing_mode" in settings:
        v.refuse(
            w,
            key,
            "the clearing mode is the shop's to pick (its account is on the shop's books): a "
            "manifest installs the payer service without one",
        )
    _roles(v, w, key, [settings.get("bill_back_role")])


def _desk_actions(v: _V):
    services = {
        s.get("key")
        for s in v.m.get("extension_subscriptions") or []
        if isinstance(s, dict) and s.get("point") == "desk_action"
    }
    for i, a in enumerate(v.list_of("desk_actions")):
        w, label = f"desk_actions[{i}]", a.get("label")
        if a.get("service") not in services:
            v.refuse(
                w,
                label,
                "service is the key of one of the manifest's own extension_subscriptions for the "
                "desk_action extension point (the installer makes the subscription first)",
            )
        _roles(v, w, label, a.get("roles"))


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
        _roles(v, w, name, r.get("bypass_roles"))
        v.no_script(
            f"{w}.message", name, r.get("message")
        )  # the product shows it as the refusal, unescaped


FISCAL_DT = "POS Invoice"
OUTSIDE_SERVICE = "Outside service"  # ivendnext_mpos fiscal_app_reader.OUTSIDE_SERVICE
# signature_field joins the result keys, optional like qr_field
RESULT_KEYS = ("status_field", "ref_field", "qr_field", "signature_field")
OPTIONAL_RESULT_KEYS = ("qr_field", "signature_field")
# the QR and seal fields hold text (fiscal_app_reader.MARK_TEXT_TYPES,
# less Code: FIELD_TYPES lets no manifest make a Code field)
MARK_TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text")


def _result_fields(m) -> set:
    return {
        (FISCAL_DT, r.get(k))
        for r in m.get("fiscal_readers") or []
        if isinstance(r, dict)
        for k in RESULT_KEYS
        if r.get(k)
    }


def _fiscal_readers(v: _V):
    own = {
        c.get("fieldname"): c
        for c in v.m.get("custom_fields") or []
        if isinstance(c, dict) and c.get("dt") == FISCAL_DT
    }
    for i, r in enumerate(v.list_of("fiscal_readers")):
        w, role = f"fiscal_readers[{i}]", r.get("writer_role")
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


# ── the register books ───────────────────────────────────────────────────────
# A book is data the register door reads (ivendnext_mpos business_logic/register_book.py, which imports the
# column vocabulary below, so the checker and the door read one list). The door checks every name a book reads
# against the site when the book is saved; its refusal comes back word for word. Here: the shape.
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
REGISTER_PERIOD_MONTHS = (1, 2, 3, 4, 6, 12)
# what a book is kept on: its printed pages · this system · the authority's own numbered
# book · the authority's own system, the shop's lines then a working register
REGISTER_MEDIA = ("printed_book", "system_of_record", "official_book", "regulator_system")
# what a print may show beside the line's own columns, worked out when it prints (never routed on,
# never required): the balance before a line
REGISTER_PRINT_COLUMNS = ("balance_before",)


def _translations(v: _V):
    for i, t in enumerate(v.list_of("translations")):
        words = t.get("words")
        for source, text in words.items() if isinstance(words, dict) else ():
            v.no_script(f"translations[{i}]", t.get("language"), source)
            v.no_script(f"translations[{i}]", t.get("language"), text)


def warnings(m) -> list[dict]:
    """What installs but needs the shop before it works, each ``{what, where, text}``. The product refuses a fiscal
    reader at ENABLE, not at insert (its writer rule runs only on an enabled reader), so the kit names it here.
    """
    out = []
    if not isinstance(m, dict):
        return out
    out += [
        {"what": "unknown_kind", "where": k, "text": f"'{k}' is not a kind this product installs"}
        for k in m
        if k not in KINDS and k not in TOP_KEYS and k not in REFUSED_KINDS
    ]
    # print formats warn with or without fiscal readers
    pf = _print_format_warnings(m)
    if not isinstance(m.get("fiscal_readers"), list):
        return out + pf
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
    if not isinstance(m.get("prefix"), str) or not _PREFIX_RE.match(m["prefix"]):
        v.refuse(
            "prefix",
            m.get("prefix"),
            "the prefix is one to three upper-case words, e.g. 'PP BLN' (the app's own fields start with it)",
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
    if "allowed_urls" in m and (
        not isinstance(m["allowed_urls"], list)
        or any(not isinstance(u, str) or not _URL_RE.match(u) for u in m["allowed_urls"])
    ):
        v.refuse(
            "allowed_urls",
            None,
            "allowed_urls is a list of plain http(s) addresses: the consent shows the shop each one",
        )
    _keyed(v)
    for check in (
        _doctypes,
        _custom_fields,
        _property_setters,
        _print_formats,
        _notifications,
        _workspaces,
        _sale_attributes,
        _webhooks,
        _reports,
        _dashboard_charts,
        _workflows,
        _naming_rules,
        _remote_keys,
        _extension_subscriptions,
        _desk_actions,
        _save_rules,
        _fiscal_readers,
        _translations,
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
