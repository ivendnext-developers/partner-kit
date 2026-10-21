# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/business_logic/manifest_check.py,
# at development 4c3f11b550f19a30b00f66f2c18a7b56c96e4aba. The shop's own checker (the install screen runs it) is the source;
# this copy lets you check a manifest before you send it, and refuses the same manifests in the same words. Everything
# below this header equals the source, except ten comments reworded in plain words (they named the product's
# internal lane ids). A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
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
     # v2: "label_layouts"
    }

The rules, in plain words, are in ``recipes/manifest.md``.

⚠ The script check (``_SCRIPT_RE``) is a TRIPWIRE, not a control: it reads the manifest's text, and a print format
is a template whose OUTPUT is not escaped, so a determined author can still assemble markup at render time, or
point an image at an outside address. The shop's administrator decides, from a summary
the installer writes (``extension_package.summary``), where every print format is listed as a template that runs
when printed; this validator catches the honest mistakes and the obvious attempts. It reads text, not
entities (`java&#115;cript:` in a link passes), and its inline-handler arm also refuses a plain word such as
`Online=1` in a label or description (dated 2026-10-15: a bound, never loosened — that widens the sink).
"""

from __future__ import annotations

import json
import re
import sys

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
    # the declaration records of the shipped extension points (2026-10-06)
    "extension_subscriptions",
    "desk_actions",
    "save_rules",
    "fiscal_readers",
    # the declaration records of the scan, field, check and capture extension points (2026-10-08)
    "scan_sources",
    "field_rules",
    # P-LABEL's layout record
    "label_layouts",
)
KINDS = KINDS_V1 + KINDS_V2
# The declaration records of extension points that have NOT shipped: kind -> (the extension point, its spec). Each is
# REFUSED, with the extension point it waits on, until that extension point has shipped on the site; its installer is
# written when the extension point is. None waits today: P-RECEIPT shipped (2026-10-10) with no manifest kind, so
# `receipt_blocks` is refused for good (REFUSED_KINDS).
POINT_KINDS: dict[str, tuple[str, str]] = {}
# Kinds refused for another reason a partner reads.
WAITING_KINDS = {
    # modules run at the extension points that take one (check and price today), but nothing installs one, or a
    # service one answers, from a manifest yet: the shop adds both in iVendNext Desk, and the reason below says so
    "extension_modules": "a package cannot install a sandboxed module, or a service a module answers, yet. "
    "Modules run at the extension points that take one; the shop adds the module and its service in "
    "iVendNext Desk (guide chapter 8)",
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
# The nine rights the framework's permission record switches ON by default (frappe/core/doctype/docperm/docperm.json; every other
# right defaults 0). Re-read that file on a framework update: a new default-ON right must join this list.
RIGHTS = ("read", "write", "create", "delete", "report", "export", "share", "print", "email")
# Roles the framework gives users by itself (frappe/permissions.py AUTOMATIC_ROLES; `Guest` is refused on its own, below): `All` goes to every
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
    "issingle": "a single-record type has no table of its own; this installer installs and removes ordinary "
    "record types only",
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
}
NOTIFY_CHANNELS = {"Email", "System Notification"}
NOTIFY_EVENTS = {"New", "Save", "Submit", "Cancel", "Days Before", "Days After", "Value Change"}
WORKSPACE_BLOCKS = {"header", "paragraph", "spacer", "shortcut", "card"}
SHORTCUT_TYPES = {"DocType", "Report", "URL"}

_APP_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]*( [A-Z][A-Z0-9]*){0,2}$")
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
    DOCTYPE_KEYS - {"name", "istable", "fields", "permissions", "autoname", "naming_rule"}
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
# frappe.get_all / get_doc / db.get_value — verified); that is fine where the output stays with the shop's
# staff, and a leak wherever it leaves: a webhook body sent to the partner, an address a print format loads (an image
# URL can carry data out), a notification sent to an address the manifest names.
_OUTSIDE_URL_RE = re.compile(r"(https?:)?//[A-Za-z0-9]", re.I)
# the framework is reachable by its other names too (iVendFramework, FrappeClient)
_SHOP_DATA_RE = re.compile(r"\b(frappe|ivendframework|frappeclient)\b", re.I)
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


def _fields(v: _V, where: str, owner: str, fields: list, engine: bool, single: bool = False):
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


def _custom_fields(v: _V):
    for i, c in enumerate(v.list_of("custom_fields")):
        w, dt = f"custom_fields[{i}]", c.get("dt")
        if not isinstance(dt, str) or not dt:
            v.refuse(
                w, c.get("fieldname"), "a custom field must name the record type it is added to"
            )
            continue
        _fields(v, w, dt, [c], engine=dt not in v.own, single=True)


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
    if fn:
        if prop not in OWN_FIELD_SETTER_PROPS:
            v.refuse(
                w,
                label,
                f"on its own record type's field a property setter may only change how the field "
                f"is shown; change '{prop}' in the record type itself",
            )
        return
    if prop in REFUSED_DOCTYPE_KEYS:
        v.refuse(w, label, REFUSED_DOCTYPE_KEYS[prop])
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
        if p.get("print_format_type", "Jinja") != "Jinja":
            v.refuse(
                w,
                name,
                "only template print formats; a script print format runs in the viewer's browser",
            )
        for k in ("html", "css"):
            v.no_script(f"{w}.{k}", name, p.get(k))
            if isinstance(p.get(k), str) and _OUTSIDE_URL_RE.search(p[k]):
                v.refuse(
                    f"{w}.{k}",
                    name,
                    "a print format may not load anything from outside the shop: an address in a "
                    "receipt can carry the shop's data out; embed images as files or data: URIs",
                )


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
        if n.get("document_type") not in v.own:
            v.refuse(
                w,
                name,
                "a notification on a shop's own record type runs inside every save of it, and an "
                "error in it stops that save (a till sale included); notify on your own types only",
            )
        extra = set(n) - NOTIFY_KEYS
        if extra:
            v.refuse(w, name, f"keys a manifest notification may not set: {sorted(extra)}")
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
            if isinstance(rcp, dict) and rcp.get("receiver_by_document_field"):
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


def _own_fields(v: _V, dt: str) -> set:
    d = next(
        (d for d in v.m.get("doctypes") or [] if isinstance(d, dict) and d.get("name") == dt), None
    )
    return {
        f.get("fieldname") for f in (d or {}).get("fields") or [] if isinstance(f, dict)
    } | STD_FIELDS


def _filters(v: _V, w: str, name, filters):
    """Filters are data: [[field, operator, value], …]. Operators from a fixed list; values plain scalars."""
    ops = {"=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "is", "between"}
    if filters is None:
        return
    if not isinstance(filters, list) or any(
        not isinstance(f, list)
        or len(f) != 3
        or f[1] not in ops
        or not isinstance(f[0], str)
        or not _FIELD_RE.match(f[0])
        or isinstance(f[2], (dict, list))
        and f[1] not in ("in", "not in", "between")
        for f in filters
    ):
        v.refuse(w, name, "filters are a list of [field, operator, value] with a plain operator")


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
            or any(not isinstance(c, str) or not _FIELD_RE.match(c) for c in cols)
        ):
            v.refuse(w, name, "columns is a list of field names")
        elif r.get("ref_doctype") in v.own and set(cols) - _own_fields(v, r["ref_doctype"]):
            v.refuse(
                w,
                name,
                f"columns not on {r['ref_doctype']}: {sorted(set(cols) - _own_fields(v, r['ref_doctype']))}",
            )
        _filters(v, w, name, r.get("filters"))
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
                    "the shop chooses the user the application reads as and switches it on; a manifest "
                    "installs the registration switched off",
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
SUB_POINTS = {"desk_action": 10, "page": 10, "check": 10, "capture": 10, "doccheck": 10}
# each extension point's answers when its service is down (`Point.down_answers`, the first the product's default)
DOWN_ANSWERS = {
    "desk_action": ("refuse",),
    "page": ("refuse",),
    "check": ("allow_and_flag", "refuse", "ask"),
    "capture": ("allow_and_flag", "refuse"),
    "doccheck": ("allow_and_flag", "refuse", "ask"),
}
# P-CHECK (partner_check.PER_SCOPE_MAX, SCOPE_SECONDS_MAX): a manifest's checks answer every POS Profile (a
# manifest names no scope), so they all share each one; the product checks it again, with the site's other checks, when
# the shop switches one on
CHECKS_MAX, CHECK_SECONDS_MAX = 3, 10
# P-CAPTURE (partner_capture.EVENTS, TIMEOUTS, GROUPS_MAX): one service per event; a scan answers in at most 3 seconds
CAPTURE_EVENTS = {
    "scan": ({"event", "item_groups", "item_field"}, 3),
    "customer_add": ({"event"}, 10),
    "customer_select": ({"event"}, 10),
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
        if "module" in s or s.get("transport", "remote") != "remote":
            v.refuse(
                w,
                key,
                "a manifest's service is a partner's https address: "
                + WAITING_KINDS["extension_modules"],
            )
        if s.get("may_approve"):
            v.refuse(
                w,
                key,
                "the shop decides whether a manager may approve past a check (it needs the shop's own "
                "approvers); a manifest installs it off",
            )
        point = s.get("point")
        _keys(
            v,
            w,
            key,
            s,
            SUB_KEYS
            | PAGE_KEYS
            | SHOP_SWITCHES
            | SHOP_CONSENT
            | {"secret", "scope", "module", "may_approve"}
            # a document check names its record type and fields there (the product checks them)
            | ({"settings"} if point in ("check", "capture", "doccheck") else set()),
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
        _endpoint(v, w, key, s.get("endpoint_url"))
        top = SUB_POINTS.get(point, 10)
        if point == "check" and "settings" in s:
            v.refuse(
                w, key, "a check takes no settings: what it is sent is the extension point's own"
            )
        if point == "capture":
            top = _capture_settings(v, w, key, s.get("settings"))
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
        v.refuse(w, key, "Name the event in the settings: scan, customer_add or customer_select.")
        return 10
    known, top = CAPTURE_EVENTS[event]
    if set(settings) - known:
        v.refuse(
            w,
            key,
            f"The settings of a {event} capture may only carry: {', '.join(sorted(known))}.",
        )
    elif event == "scan":
        groups, field = settings.get("item_groups") or [], settings.get("item_field") or ""
        if not isinstance(groups, list) or any(not isinstance(g, str) for g in groups):
            v.refuse(w, key, "item_groups must be a list of item group names.")
        elif len(groups) > CAPTURE_GROUPS_MAX:
            v.refuse(w, key, f"A scan capture names at most {CAPTURE_GROUPS_MAX} item groups.")
        elif not isinstance(field, str):
            v.refuse(w, key, "item_field must be the name of one field on Item.")
        elif not groups and not field:
            v.refuse(
                w,
                key,
                "Say which items a scan capture asks about: item groups, an item field, or both.",
            )
    return top


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
    "cart_line": ("Item", {"item_name": ("relabel",), "qty": ("relabel",)}),
    "item_result": ("Item", {"item_code": ("hide", "relabel")}),
    "sale_details": (
        None,
        None,
    ),  # its fields are the shop's active sale details: hide or relabel (the product checks)
    # the receipt, show only — up to three Item fields under each line
    "receipt_preview": ("Item", {}),
}
# the product's words for a receipt rule other than show (pos_fields.validate_field_rules)
FIELD_RECEIPT_ONLY_SHOW = (
    "On the receipt a rule can only show an item field. Money, tax and the receipt's own "
    "lines print as they are."
)
FIELD_ACTIONS = ("hide", "relabel", "require", "show")
FIELD_LABEL_MAX, FIELD_SHOW_MAX = 40, 3
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
        doctype, named = FIELD_SURFACES[surface]
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
        unknown = sorted({x for x in _LABEL_TOKEN_RE.findall(t) if x not in LABEL_PLACEHOLDERS})
        if unknown:
            v.refuse(
                w, name, f"{', '.join('{' + x + '}' for x in unknown)} is not a label placeholder."
            )
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


def warnings(m) -> list[dict]:
    """What installs but needs the shop before it works, each ``{what, where, text}``. The product refuses a fiscal
    reader at ENABLE, not at insert (its writer rule runs only on an enabled reader), so the kit names it here.
    """
    out = []
    if not isinstance(m, dict) or not isinstance(m.get("fiscal_readers"), list):
        return out
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
    return out


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
            _extension_subscriptions,
            _desk_actions,
            _save_rules,
            _fiscal_readers,
            _scan_sources,
            _field_rules,
            _label_layouts,
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
