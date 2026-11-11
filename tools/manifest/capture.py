"""Capture from a site: what a person made in Desk on an iVendNext site becomes your app's manifest.

A consultant's first move on a customer's project is often clicks, not code: a few fields, a workflow, a notification and a
print format, made in Desk on a test site. Capture reads them and writes them into an app, so the same set-up installs on
the customer's live site, and on the next customer's, as an app.

    ivn capture --site acme-test.example.com              # into the app in this folder
    ivn capture --site acme-test.example.com --new acme_rules
    My apps: an app's page, Capture from a site; or New app, From a site

The site is read with the key our hosting keeps for it (yours, added on My sites, or ours where the site is granted to your
company); nothing is written to it, and our server keeps none of its records past the request that reads them
(`READ_TYPES` is all it reads). This file then does the rest, the same on your laptop and on My apps:

1. **Only what a person made** (`made_by_person`). A record counts when a person signed in as themselves made it (its
   `owner` is a user other than `Administrator`: the product and its installs make their records as `Administrator`), when
   it carries no standard mark (`is_system_generated`, `is_standard`, `standard`, `custom` on a record type), no `module`
   (an app's records carry their module), and when no installed app's install record names it. A Workflow carries no mark of
   its own, so the install records decide it.
2. **Into the manifest's kinds** (`to_entries`), each as the recipe's table has it (`recipes/manifest.md`).
3. **Renamed to your app** (`rename_to`). A field made in Desk is named `custom_…`; the checker wants your app's prefix on a
   field you add to a customer's record type, so `custom_gift_wrap` becomes `acme_rules_gift_wrap` everywhere it is named:
   in a workflow's condition, a notification's message, a print format, a property setter, a list's columns, a list mark,
   a till field rule. A role made in Desk takes the prefix too (`Store Approver` becomes `ACME RULES Store Approver`), as a
   role an app brings must. A name the site also uses for another record type's field (the product's own, or another
   app's) is left as it is in the entries about that record type; a name past 64 characters is shortened; and a field or
   role you untick keeps its own name wherever the entries you keep name it.
4. **Left out, with the checker's reason** (`capture`). The shop's own checker (`validate.py`) and the install's own stops
   (`site_rules.py`) run on the result; an entry they refuse is left out, in their words, and so is everything the manifest
   cannot carry (a client or server script, a query or script report, a right for one of the customer's own roles).

Exit codes of the command: 0 written · 1 refused · 2 usage.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from site_rules import refusals as site_refusals  # noqa: E402
from validate import DOCPERM_RIGHTS, REFUSED_KINDS, RIGHTS, app_for, field_prefix, validate  # noqa: E402, F401

# What the hosting reads on the site, by record type, and only these: the configuration a person makes in Desk. The filter
# is the site's own query (`/api/resource/<type>`); every record then comes whole, with its child rows.
READ_TYPES = {
    "Custom Field": [["is_system_generated", "=", 0]],
    "Property Setter": [["is_system_generated", "=", 0]],
    "Workflow": [],
    "Notification": [["is_standard", "=", 0]],
    "Print Format": [["standard", "=", "No"]],
    "Document Naming Rule": [],
    "List View Settings": [],
    "DocType": [["custom", "=", 1]],
    "Role": [],
    "Custom DocPerm": [],
    "Workspace": [["public", "=", 1]],  # a person's private workspace is theirs, never an app's
    "Report": [["is_standard", "=", "No"]],
    "Number Card": [["is_standard", "=", 0]],
    "Dashboard Chart": [["is_standard", "=", 0]],
    "Dashboard": [["is_standard", "=", 0]],
    "Webhook": [],
    "Translation": [],
    "Client Script": [],
    "Server Script": [],
    "Web Page": [],
    "Web Template": [],
    # the retail kinds a person makes in Desk (J3b)
    "Retail Label Layout": [],
    "Retail List Mark": [],
    "Retail Scan Source": [],
    "Retail Register Book": [["source_app", "is", "not set"]],  # a book an app brought names its app
    "Retail Save Rule": [],
    "Sale Attribute": [],
    "Retail POS Theme Field": [],  # a till theme's field rules: rows of the theme, read as rows
    "Retail POS Theme": [],  # a theme saved as new (the shipped ones stay as they ship): no kind carries it, so it is said
    "DocType Link": [["custom", "=", 1]],  # a Connections link made in Customize Form
    "DocType Action": [["custom", "=", 1]],  # Customize Form's own buttons and document states: no kind carries them
    "DocType State": [["custom", "=", 1]],
}
# a child row is read through its parent: the record door asks for the parent's type (`parent=`)
PARENT = {"Retail POS Theme Field": "Retail POS Theme", "DocType Link": "Customize Form", "DocType Action": "Customize Form",
          "DocType State": "Customize Form"}
# rows a person adds to a record the product made: a row takes its parent's owner, so the install records alone judge them
# (a new site's till themes carry no field rules)
ANY_OWNER = {"Retail POS Theme Field"}
# the types whose records come one by one: with their child rows, or a print format's HTML (a list of a chain's print formats
# would pass the 1 MB the hosting reads of one answer); the rest come whole from the list
WITH_CHILDREN = {"Workflow", "Notification", "DocType", "Report", "Workspace", "Dashboard", "Document Naming Rule",
                 "Retail List Mark", "Retail Save Rule", "Print Format"}
# the types whose `module` marks an app's record: Desk itself sets the module of a person's print format, report and record
# type (from the record type it is for), so those are judged by their standard mark and the install records alone
MODULE_MARKS = {"Custom Field", "Property Setter", "Notification", "Workspace", "Number Card", "Dashboard Chart",
                "Dashboard", "List View Settings", "Document Naming Rule", "Webhook", "Translation", "Role"}
# a person's own records only: the hosting asks the site for these alone (`owner` set and not Administrator)
PERSON_FILTER = [["owner", "is", "set"], ["owner", "!=", "Administrator"]]
FIELD_MAX = 64  # a field's name, as a column of the record type's table: *"Fieldname is limited to 64 characters"*


def reads() -> list[dict]:
    """What the hosting asks the site for, one list call each: ``{"doctype", "filters", "parent", "whole"}``. ``whole``:
    each record is then read one by one, with its child rows (the list gives no child rows)."""
    return [{"doctype": dt, "filters": [*flt, *([] if dt in ANY_OWNER else PERSON_FILTER)], "parent": PARENT.get(dt),
             "whole": dt in WITH_CHILDREN} for dt, flt in READ_TYPES.items()]
INSTALL = "Retail Extension Install"  # each installed app's record: `items`, every record it made, by kind and name

# the install record's kinds, as the record types they made
ITEM_TYPES = {"custom_field": "Custom Field", "property_setter": "Property Setter", "workflow": "Workflow",
              "notification": "Notification", "print_format": "Print Format", "naming_rule": "Document Naming Rule",
              "list_settings": "List View Settings", "doctype": "DocType", "workspace": "Workspace", "report": "Report",
              "number_card": "Number Card", "dashboard_chart": "Dashboard Chart", "dashboard": "Dashboard",
              "webhook": "Webhook", "role": "Role", "docperm": "Custom DocPerm", "translation": "Translation",
              "label_layout": "Retail Label Layout", "list_mark": "Retail List Mark", "scan_source": "Retail Scan Source",
              "register_book": "Retail Register Book", "save_rule": "Retail Save Rule", "sale_attribute": "Sale Attribute",
              "field_rule": "Retail POS Theme Field", "doctype_link": "DocType Link"}

# the words for what the manifest cannot carry (the rest are the checker's own)
WORDS = {
    "script": REFUSED_KINDS,
    "report_kind": "a {kind} runs code on the site; the manifest takes a Report Builder report",
    "builder_print": "made in the Print Format Builder, which the manifest does not carry: make it as an HTML print "
                     "format (Custom Format) and capture again",
    "their_role": "rights for the site's own roles ({roles}): the customer gives them in Role Permissions Manager",
    "role_level": "a right for {role} at level {level} or only on records its user made: the customer gives it in Role "
                  "Permissions Manager",
    "nothing": "Nothing made in Desk to capture on {site}: a record counts when a person signed in as themselves made it, "
               "not as Administrator. Made it as Administrator? Make your own user with System Manager in Desk, sign in as "
               "it, make the set-up again, then capture.",
    "off": "it is switched off on {site}: switch it on there to capture it",
    "row_setter": "a change to one of {dt}'s own {rows} (a row of that site's, by its own row name): the manifest changes a "
                  "record type or a field, so make it again in Customize Form on the customer's site",
    "row_order": "the order of {dt}'s {rows} on that site, by that site's own row names: the links an app adds keep Desk's "
                 "own order",
    "child_link": "a Connections link to a child table's rows: the manifest's links list records of a record type; make it "
                  "in Customize Form on the customer's site",
    "no_kind": "a Customize Form {what}: the manifest carries none. Make it there again on the customer's site{instead}",
    "sale_check": "a sale detail checked by a pattern or filled with a default: the manifest's sale detail carries "
                  "neither, so it would install unchecked. Make it on the customer's site by hand",
    "theme": "a till theme: the manifest carries none, only the field rules on it. On the site you install on, make a theme "
             "named {name} first (POS Studio, Save as a new theme), then install: its field rules go on it",
    "field_order": "the whole order of the form's fields on that site: it would fix the customer's form to this layout. "
                   "Each captured field keeps its place by its Insert After",
}

KEEP = {  # the fields each kind carries, in the recipe's terms (the rest of a site's record is the site's own bookkeeping)
    "custom_fields": ("dt", "fieldname", "fieldtype", "label", "insert_after", "options", "default", "description",
                      "reqd", "hidden", "read_only", "bold", "collapsible", "depends_on", "mandatory_depends_on",
                      "read_only_depends_on", "fetch_from", "fetch_if_empty", "in_list_view", "in_standard_filter",
                      "allow_on_submit", "length", "precision", "print_hide", "translatable", "unique", "non_negative"),
    "property_setters": ("doc_type", "field_name", "property", "property_type", "value"),
    "print_formats": ("name", "doc_type", "html", "css", "print_format_type", "default_print_language"),
    "notifications": ("name", "document_type", "event", "channel", "subject", "message", "condition", "days_in_advance",
                      "date_changed", "value_changed", "send_to_all_assignees", "attach_print", "print_format",
                      "set_property_after_alert"),
    "naming_rules": ("document_type", "prefix", "prefix_digits", "priority"),
    "doctypes": ("name", "description", "autoname", "naming_rule", "istable", "issingle", "is_submittable",
                 "title_field", "search_fields", "show_title_field_in_link", "sort_field", "sort_order",
                 "track_changes", "editable_grid", "quick_entry"),
    "number_cards": ("name", "document_type", "function", "aggregate_function_based_on", "color", "is_public"),
    "dashboard_charts": ("name", "document_type", "chart_type", "based_on", "value_based_on", "group_by_type",
                         "group_by_based_on", "timespan", "time_interval", "type", "color", "is_public"),
    # the retail kinds, as the POS install writes them back (`manifest_install.py`)
    "label_layouts": ("label_name", "kind", "width_mm", "height_mm", "per_row", "template"),
    "list_marks": ("record_type", "label", "colour", "sequence"),
    "scan_sources": ("source_name", "record_type", "barcode_field", "sequence", "capture_as", "item_from", "batch_from",
                     "serial_from", "status_field", "warehouse_field"),
    "register_books": ("book", "title", "data_set", "cite", "medium", "numbering", "balance", "correction",
                       "retention_years", "period_months", "return_due_days", "count_role", "count_witness",
                       "loss_count_hours"),
    "save_rules": ("rule_name", "record_type", "child_table", "kind", "field", "mode", "sequence", "message",
                   "pattern_class", "pattern", "min_length", "max_length", "formula", "source_table", "source",
                   "source_b", "factor", "offset", "decimals", "operator", "judge_on_change", "value_from_type",
                   "value_from_name", "value_field", "roles_field", "action", "scope_field", "day_field", "cap"),
    "field_rules": ("surface", "field", "action", "label", "language", "sequence"),
}
# a register book's declarations, kept on the record as JSON text (`register_book.record_of`), and its `items` as item_scope
BOOK_JSON = {"item_scope": "items", "class_source": "class_source", "conditions": "conditions", "required": "required",
             "columns": "columns", "details": "details", "authority": "authority", "columns_from": "columns_from"}
# a save rule's lists, kept on the record one per line (`manifest_install._apply_v2`)
RULE_LINES = ("bypass_roles", "states", "locked_fields", "scope_fields")
FIELD_KEEP = KEEP["custom_fields"][1:] + ("permlevel", "columns", "in_global_search", "search_index", "no_copy")
CHILD_KEEP = {
    "states": ("state", "doc_status", "allow_edit", "update_field", "update_value", "is_optional_state", "message"),
    "transitions": ("state", "action", "next_state", "allowed", "allow_self_approval", "condition"),
    "recipients": ("receiver_by_role", "receiver_by_document_field", "cc", "bcc", "condition"),
    "conditions": ("field", "condition", "value"),
}
ALL_RIGHTS = tuple(dict.fromkeys((*RIGHTS, *DOCPERM_RIGHTS, "submit", "cancel", "amend", "select")))


def _kept(rec: dict, keys) -> dict:
    """The record's own values under ``keys``: set ones only (a site answers every field, most of them empty)."""
    return {k: rec[k] for k in keys if rec.get(k) not in (None, "", 0, "0", [], {})}


def _rows(rec: dict, key: str, kind: str) -> list:
    return [{**_kept(r, CHILD_KEEP[kind]), **({"value": r["value"]} if kind == "conditions" and r.get("value") is not None
                                              else {})}
            for r in rec.get(key) or [] if isinstance(r, dict)]


def _conditions(rec: dict) -> list:
    """A list mark's or a save rule's conditions (Retail Save Rule Condition): field, operator, and the value as it is."""
    return [{"field": r.get("field"), "operator": r.get("operator") or "=",
             **({"value": r["value"]} if r.get("value") is not None else {})}
            for r in rec.get("conditions") or [] if isinstance(r, dict) and r.get("field")]


def _json(v, default):
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v or "null") or default
    except (TypeError, ValueError):
        return default


# ── 1. only what a person made ──

def installed(installs: list) -> set:
    """{(record type, name)} of every record an installed app made, by its install record's items (a translation item
    names its rows)."""
    out = set()
    for inst in installs or []:
        for i in _json(inst.get("items"), []):
            if not isinstance(i, dict):
                continue
            t = ITEM_TYPES.get(i.get("kind"))
            out |= {(t, n) for n in [i.get("name"), *(i.get("rows") or [])] if n}
    return out


def made_by_person(records: dict, installs: list) -> dict:
    """``records`` ({record type: [records]}) less everything the product or an installed app made."""
    by_apps = installed(installs)
    out = {}
    for dt, rows in (records or {}).items():
        keep = []
        for r in rows or []:
            if not isinstance(r, dict) or (dt not in ANY_OWNER and r.get("owner") in (None, "", "Administrator")) \
                    or (dt in MODULE_MARKS and r.get("module")) or (dt == "Retail Register Book" and r.get("source_app")):
                continue
            if (dt, r.get("name")) in by_apps:
                continue
            keep.append(r)
        if keep:
            out[dt] = keep
    return out


# ── 2. into the manifest's kinds ──

def _report(r: dict) -> dict:
    spec = _json(r.get("json"), {})
    # Report View keeps its columns as `fields` ([field, record type]); an older report as `columns`
    columns = [c[0] if isinstance(c, list) else c for c in spec.get("fields") or spec.get("columns") or []
               if not isinstance(c, list) or len(c) < 2 or c[1] == r.get("ref_doctype")]
    out = {"name": r["name"], "ref_doctype": r.get("ref_doctype"), "columns": columns}
    filters = [f[1:4] if isinstance(f, list) and len(f) >= 4 else f for f in spec.get("filters") or []]
    if filters:  # Desk's [record type, field, op, value, flag] rows, as the manifest's [field, op, value]
        out["filters"] = filters
    if spec.get("order_by"):  # Desk keeps it as the query writes it (`tabPurchase Order`.`modified` desc): one field
        out["order_by"] = re.sub(r"`tab[^`]+`\.`([^`]+)`", r"\1", str(spec["order_by"])).strip()
    if spec.get("add_totals_row") or r.get("add_total_row"):
        out["add_total_row"] = 1
    roles = [x.get("role") for x in r.get("roles") or [] if isinstance(x, dict) and x.get("role")]
    return {**out, **({"roles": roles} if roles else {})}


def _workspace(r: dict) -> dict:
    blocks = [{"type": b.get("type"), "data": {k: v for k, v in (b.get("data") or {}).items() if k != "id"}}
              for b in _json(r.get("content"), []) if isinstance(b, dict) and b.get("type")]
    shortcuts = [_kept(s, ("type", "link_to", "label", "url", "doc_view", "color", "format", "stats_filter"))
                 for s in r.get("shortcuts") or [] if isinstance(s, dict)]
    return {"name": r["name"], "blocks": blocks, "shortcuts": shortcuts}


def _doctype(r: dict) -> dict:
    out = _kept(r, KEEP["doctypes"])
    out["fields"] = [_kept(f, ("fieldname", *FIELD_KEEP)) for f in r.get("fields") or [] if isinstance(f, dict)]
    out["permissions"] = [{"role": p["role"], **{k: 1 for k in ALL_RIGHTS if p.get(k)},
                           **({"permlevel": p["permlevel"]} if p.get("permlevel") else {})}
                          for p in r.get("permissions") or [] if isinstance(p, dict) and p.get("role")]
    return out


def to_entries(records: dict, site: str = "") -> tuple[dict, list]:
    """({kind: [entries]}, [what cannot be carried, each {"type", "name", "reason"}])."""
    e, out = {}, []

    def add(kind, entry, source):
        entry["_from"] = source  # the record it came from, for the list a person unticks (dropped before writing)
        e.setdefault(kind, []).append(entry)

    # the state field Desk makes for a workflow (`workflow_state`): the target's own workflow makes it again, under its own
    # name, so it is never taken (nor renamed where a notification or a print names the state)
    states = {(w.get("document_type"), w.get("workflow_state_field") or "workflow_state") for w in records.get("Workflow", [])}
    for r in records.get("Custom Field", []):
        if (r.get("dt"), r.get("fieldname")) in states and r.get("options") == "Workflow State":
            continue
        add("custom_fields", _kept(r, KEEP["custom_fields"]), ("Custom Field", r["name"]))
    rows_of = {"DocType Link": "Connections links", "DocType Action": "form buttons", "DocType State": "document states"}
    for r in records.get("Property Setter", []):
        if r.get("property") == "field_order":
            out.append({"type": "Property Setter", "name": r["name"], "reason": WORDS["field_order"]})
            continue
        if r.get("row_name") or r.get("doctype_or_field") in rows_of:  # Customize Form's change to a link, button or state
            out.append({"type": "Property Setter", "name": r["name"], "reason": WORDS["row_setter"].format(
                dt=r.get("doc_type"), rows=rows_of.get(r.get("doctype_or_field"), "Connections links, buttons or states"))})
            continue
        if r.get("property") in ("links_order", "actions_order", "states_order"):
            out.append({"type": "Property Setter", "name": r["name"], "reason": WORDS["row_order"].format(
                dt=r.get("doc_type"), rows={"links_order": "Connections links", "actions_order": "form buttons",
                                            "states_order": "document states"}[r["property"]])})
            continue
        add("property_setters", _kept(r, KEEP["property_setters"]) | {"value": r.get("value")}, ("Property Setter", r["name"]))
    for r in records.get("Workflow", []):
        if not r.get("is_active"):
            out.append({"type": "Workflow", "name": r["name"], "reason": WORDS["off"].format(site=site or "the site")})
            continue
        add("workflows", {"name": r["name"], "document_type": r.get("document_type"),
                          **({"send_email_alert": 1} if r.get("send_email_alert") else {}),
                          **({"override_status": 1} if r.get("override_status") else {}),
                          "states": _rows(r, "states", "states"),
                          # every step says whether its raiser may take it: a silent one takes Desk's own default (1)
                          "transitions": [{**t, "allow_self_approval": 1 if src.get("allow_self_approval") else 0}
                                          for t, src in zip(_rows(r, "transitions", "transitions"), r.get("transitions") or [])]},
            ("Workflow", r["name"]))
    for r in records.get("Notification", []):
        if not r.get("enabled"):
            out.append({"type": "Notification", "name": r["name"], "reason": WORDS["off"].format(site=site or "the site")})
            continue
        n = _kept(r, KEEP["notifications"])
        if r.get("set_property_after_alert"):  # the value it sets, as it is ("0" is a value)
            n["property_value"] = r.get("property_value") or ""
        n["recipients"] = _rows(r, "recipients", "recipients")
        add("notifications", n, ("Notification", r["name"]))
    for r in records.get("Print Format", []):
        if not r.get("html"):  # made in the Print Format Builder (its layout, no HTML)
            out.append({"type": "Print Format", "name": r["name"], "reason": WORDS["builder_print"]})
            continue
        add("print_formats", _kept(r, KEEP["print_formats"]), ("Print Format", r["name"]))
    for r in records.get("Document Naming Rule", []):
        n = _kept(r, KEEP["naming_rules"])
        if r.get("conditions"):
            n["conditions"] = _rows(r, "conditions", "conditions")
        add("naming_rules", n, ("Document Naming Rule", r["name"]))
    for r in records.get("List View Settings", []):
        fields = [f.get("fieldname") if isinstance(f, dict) else f for f in _json(r.get("fields"), [])]
        add("list_settings", {"doctype": r["name"], **({"fields": [f for f in fields if f]} if fields else {})},
            ("List View Settings", r["name"]))
    for r in records.get("DocType", []):
        add("doctypes", _doctype(r), ("DocType", r["name"]))
    roles, theirs = {r["name"] for r in records.get("Role", [])}, {}
    for p in records.get("Custom DocPerm", []):
        rights = [k for k in DOCPERM_RIGHTS if p.get(k)]
        if p.get("role") in roles and (p.get("permlevel") or p.get("if_owner")):
            out.append({"type": "Custom DocPerm", "name": f"{p.get('parent')}: {p.get('role')}",
                        "reason": WORDS["role_level"].format(role=p.get("role"), level=p.get("permlevel") or 0)})
        elif p.get("role") in roles:
            add("role_rights", {"doctype": p.get("parent"), "role": p["role"], "rights": rights}, ("Role", p["role"]))
        elif rights:  # Role Permissions Manager copies every standard row the first time: one line per record type
            theirs.setdefault(p.get("parent"), []).append(p.get("role"))
    for dt, rs in theirs.items():
        out.append({"type": "Custom DocPerm", "name": dt, "reason": WORDS["their_role"].format(roles=", ".join(sorted(set(rs))))})
    for r in records.get("Workspace", []):
        add("workspaces", _workspace(r), ("Workspace", r["name"]))
    for r in records.get("Report", []):
        if r.get("report_type") != "Report Builder":
            out.append({"type": "Report", "name": r["name"], "reason": WORDS["report_kind"].format(
                kind=str(r.get("report_type") or "report").lower())})
            continue
        add("reports", _report(r), ("Report", r["name"]))
    for dt, kind in (("Number Card", "number_cards"), ("Dashboard Chart", "dashboard_charts")):
        for r in records.get(dt, []):  # Desk's filters_json rows, as the manifest's [field, op, value]
            f = [x[1:4] if isinstance(x, list) and len(x) >= 4 else x for x in _json(r.get("filters_json"), [])]
            add(kind, {**_kept(r, KEEP[kind]), **({"filters": f} if f else {})}, (dt, r["name"]))
    for r in records.get("Dashboard", []):
        add("dashboards", {"name": r["name"], "charts": [c.get("chart") for c in r.get("charts") or [] if c.get("chart")],
                           "cards": [c.get("card") for c in r.get("cards") or [] if c.get("card")]}, ("Dashboard", r["name"]))
    for r in records.get("Webhook", []):
        add("webhooks", {"name": r["name"], "doctype": r.get("webhook_doctype"), "event": r.get("webhook_docevent"),
                         "url": r.get("request_url")}, ("Webhook", r["name"]))
    words = {}
    for r in records.get("Translation", []):
        if r.get("language") and r.get("source_text"):
            words.setdefault(r["language"], {})[r["source_text"]] = r.get("translated_text") or ""
    for lang, w in sorted(words.items()):
        add("translations", {"language": lang, "words": w}, ("Translation", lang))
    for dt, kind in (("Client Script", "client_scripts"), ("Server Script", "server_scripts"), ("Web Page", "web_pages"),
                     ("Web Template", "web_templates")):
        for r in records.get(dt, []):
            out.append({"type": dt, "name": r["name"], "reason": REFUSED_KINDS[kind]})
    _retail(records, add, out, site)
    return e, out


def _retail(records: dict, add, out: list, site: str) -> None:
    """The retail kinds a person makes in Desk, each as the POS install writes it, read back into the manifest's shape."""
    def off(dt, r, name):
        out.append({"type": dt, "name": name, "reason": WORDS["off"].format(site=site or "the site")})

    for r in records.get("Retail Label Layout", []):
        if not r.get("enabled"):
            off("Retail Label Layout", r, r["name"]); continue
        add("label_layouts", _kept(r, KEEP["label_layouts"]), ("Retail Label Layout", r["name"]))
    for r in records.get("Retail List Mark", []):
        if not r.get("enabled"):
            off("Retail List Mark", r, r.get("label") or r["name"]); continue
        add("list_marks", {**_kept(r, KEEP["list_marks"]), "conditions": _conditions(r)},
            ("Retail List Mark", f"{r.get('record_type')}: {r.get('label')}"))  # its own name is a row id
    for r in records.get("Retail Scan Source", []):
        if not r.get("enabled"):
            off("Retail Scan Source", r, r["name"]); continue
        values = [x.strip() for x in str(r.get("available_values") or "").splitlines() if x.strip()]
        add("scan_sources", {**_kept(r, KEEP["scan_sources"]), **({"available_values": values} if values else {})},
            ("Retail Scan Source", r["name"]))
    for r in records.get("Retail Register Book", []):  # installed on or off as it declares, so a book off is still a book
        b = _kept(r, KEEP["register_books"])
        b["enabled"], b["certified"] = int(bool(r.get("enabled"))), int(bool(r.get("certified")))
        for field, key in BOOK_JSON.items():
            v = _json(r.get(field), None)
            if v not in (None, "", [], {}):
                b[key] = v
        add("register_books", b, ("Retail Register Book", r["name"]))  # its register stores are the shop's own setup
    for r in records.get("Retail Save Rule", []):
        if not r.get("enabled"):
            off("Retail Save Rule", r, r["name"]); continue
        rule = _kept(r, KEEP["save_rules"])
        if r.get("value") not in (None, ""):  # a threshold of 0 is a threshold
            rule["value"] = r["value"]
        for k in RULE_LINES:
            lines = [x.strip() for x in str(r.get(k) or "").splitlines() if x.strip()]
            if lines:
                rule[k] = lines
        if r.get("conditions"):
            rule["conditions"] = _conditions(r)
        add("save_rules", rule, ("Retail Save Rule", r["name"]))
    for r in records.get("Sale Attribute", []):
        if not r.get("active"):
            off("Sale Attribute", r, r["name"]); continue
        if r.get("regex_pattern") or r.get("default_value") or r.get("validation_type") not in (None, "", "No Validation",
                                                                                                 "DocType"):
            out.append({"type": "Sale Attribute", "name": r["name"], "reason": WORDS["sale_check"]}); continue
        a = {"name": r.get("attribute_name") or r["name"], **_kept(r, ("sequence", "required"))}
        if r.get("validation_type") == "DocType" and r.get("doctype_name"):
            a.update(validation_type="DocType", doctype_name=r["doctype_name"])
        add("sale_attributes", a, ("Sale Attribute", r["name"]))  # a required one: the checker says why it cannot be
    for r in records.get("Retail POS Theme Field", []):
        rule = {"theme": r.get("parent"), **_kept(r, KEEP["field_rules"])}
        add("field_rules", rule, ("Retail POS Theme Field",  # a language's own words are a rule of their own
                                  f"{r.get('parent')}: {r.get('action')} {r.get('field')} on {r.get('surface')}"
                                  + (f" ({r['language']})" if r.get("language") else "")))
    for r in records.get("Retail POS Theme", []):
        out.append({"type": "Retail POS Theme", "name": r["name"], "reason": WORDS["theme"].format(name=r["name"])})
    for r in records.get("DocType Link", []):
        name = f"{r.get('parent')}: {r.get('link_doctype')} ({r.get('link_fieldname')})"
        if r.get("is_child_table") or r.get("table_fieldname"):
            out.append({"type": "DocType Link", "name": name, "reason": WORDS["child_link"]}); continue
        add("links", {"doctype": r.get("parent"), "link_doctype": r.get("link_doctype"),
                      "link_fieldname": r.get("link_fieldname"), **_kept(r, ("group",))}, ("DocType Link", name))
    for dt, what, instead in (("DocType Action", "form button", ""),
                              ("DocType State", "document state", ", or show it with a list mark")):
        for r in records.get(dt, []):
            out.append({"type": dt, "name": f"{r.get('parent')}: {r.get('label') or r.get('title') or r['name']}",
                        "reason": WORDS["no_kind"].format(what=what, instead=instead)})


# ── 3. renamed to your app ──

# the record type each entry is about, by its kind: a name the site also uses for a field of another record type (the
# product's own, or another app's) is left as it is in the entries about that record type
DT_KEY = {"custom_fields": "dt", "property_setters": "doc_type", "print_formats": "doc_type", "notifications": "document_type",
          "workflows": "document_type", "naming_rules": "document_type", "list_settings": "doctype", "reports": "ref_doctype",
          "number_cards": "document_type", "dashboard_charts": "document_type", "list_marks": "record_type",
          "scan_sources": "record_type", "save_rules": "record_type", "role_rights": "doctype", "links": "link_doctype"}
# a till field rule names a field of the record the till screen shows; a label layout's `{item.<field>}` an Item's
SURFACE_DT = {"customer_create": "Customer", "customer_card": "Customer", "item_result": "Item", "cart_line": "Item",
              "receipt_preview": "Item"}  # the till's own table (pos_fields.SURFACES); sale details and totals name none


def _about(kind: str, entry: dict):
    if kind == "field_rules":
        return SURFACE_DT.get(entry.get("surface"))
    if kind == "label_layouts":
        return "Item"
    return entry.get(DT_KEY[kind]) if kind in DT_KEY else None


def _short(name: str, taken: set) -> str:
    """``name`` within FIELD_MAX characters, and not one of ``taken``."""
    if len(name) <= FIELD_MAX and name not in taken:
        return name
    base, n = name[:FIELD_MAX].rstrip("_"), 1
    while base in taken:
        n += 1
        base = name[:FIELD_MAX - len(str(n)) - 1].rstrip("_") + f"_{n}"
    return base


def rename_to(entries: dict, prefix: str, others=None, keep=()) -> tuple[dict, list]:
    """The entries with each field made in Desk (`custom_…`, or any name without the app's prefix on a customer's record
    type) and each role made in Desk under the app's prefix, wherever a string names them; and one line per rename.
    ``others``: {field name: the record types where the site has a field of that name a person did not make}; in an entry
    about one of those record types the name is the other field's, so it stays. ``keep``: names that stay as they are
    everywhere (a field or role you unticked, or the checker left out: the site you install on keeps its own)."""
    fp, own, others, keep = field_prefix(prefix), {d.get("name") for d in entries.get("doctypes") or []}, others or {}, set(keep)
    fields, lines = {}, []
    taken = {c.get("fieldname") for c in entries.get("custom_fields") or []}
    for c in entries.get("custom_fields") or []:
        fn = c.get("fieldname") or ""
        if c.get("dt") in own or fn.startswith(fp) or fn in keep or fn in fields:
            continue
        new = _short(fp + re.sub(r"^custom_", "", fn), taken | set(fields.values()))
        fields[fn] = new
        lines.append(f"{c.get('dt')}: {fn} is {new}" + (f" (shortened to {FIELD_MAX} characters)"
                                                         if len(fp + re.sub(r'^custom_', '', fn)) > FIELD_MAX else ""))
    roles = {}
    for r in entries.get("role_rights") or []:
        old = r.get("role") or ""
        if old and old not in keep and not old.startswith(prefix + " ") and old not in roles:
            roles[old] = f"{prefix} {old}"
            lines.append(f"the role {old} is {roles[old]}")
    if not fields and not roles:
        return entries, lines
    cache = {}

    def pattern(dt):
        names = tuple(sorted((f for f in fields if not (dt and dt in others.get(f, ()))), key=len, reverse=True))
        if names not in cache:
            cache[names] = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(f) for f in names)
                                      + r")(?![A-Za-z0-9_])") if names else None
        return cache[names]

    def walk(o, rx):
        if isinstance(o, dict):
            return {k: (v if k == "_from" else walk(v, rx)) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v, rx) for v in o]
        if not isinstance(o, str):
            return o
        if o in roles:  # a role is named by the whole value (a state's allow_edit, a recipient's role, a permission's role)
            return roles[o]
        return rx.sub(lambda m: fields[m.group(1)], o) if rx else o
    return {kind: [walk(e, pattern(_about(kind, e))) for e in copy.deepcopy(rows)] if isinstance(rows, list) else rows
            for kind, rows in entries.items()}, lines


# ── 4. checked, and left out with the checker's reason ──

_WHERE = re.compile(r"^([a-z_]+)\[(\d+)\]")


def _manifest(base: dict, entries: dict) -> dict:
    """``base`` with the entries in, each replacing an entry of the same key already there (a second capture)."""
    m = copy.deepcopy(base)
    for kind, rows in entries.items():
        key = _key_of(kind)
        mine = {tuple(r.get(x) for x in key) for r in rows}
        m[kind] = [r for r in m.get(kind) or [] if tuple(r.get(x) for x in key) not in mine] \
            + [{k: v for k, v in r.items() if k != "_from"} for r in rows]
    return m


def capture(records: dict, installs: list, base: dict, site: str = "", others=None) -> dict:
    """Everything a person made on the site, as entries for the app whose manifest is ``base``:
    ``{"entries": {kind: [...]}, "items": [{"id", "kind", "type", "name"}], "left_out": [...], "renamed": [...]}``.
    Each entry and item carries an ``id`` (``Type/name``) to untick by. ``others``: the site's fields named like a person's
    (``others_of``), so a name the product or another app also uses stays theirs where it is theirs."""
    raw, left = to_entries(made_by_person(records, installs), site)
    others = others_of(others, records)
    entries, renamed = rename_to(raw, base["prefix"], others)
    entries = _checked(entries, base, left)
    items = [{"id": f"{e['_from'][0]}/{e['_from'][1]}", "kind": kind, "type": e["_from"][0], "name": e["_from"][1]}
             for kind, rows in entries.items() for e in rows]
    return {"entries": entries, "items": items, "left_out": left, "renamed": renamed, "_raw": raw, "_others": others}


def _checked(entries: dict, base: dict, left: list) -> dict:
    """``entries`` less what the checker or the install refuses, each added to ``left`` in their words."""
    for _ in range(50):  # each pass leaves out what the checker or the install refuses, in their words
        m = _manifest(base, entries)
        bad = [*validate(m), *site_refusals(m)]
        drop = {}
        for b in bad:
            hit = _WHERE.match(b.get("where") or "")
            if not hit or hit.group(1) not in entries:
                continue
            kept = len(m.get(hit.group(1)) or []) - len(entries[hit.group(1)])  # the app's own entries come first
            i = int(hit.group(2)) - kept
            if 0 <= i < len(entries[hit.group(1)]):
                drop.setdefault((hit.group(1), i), b["reason"])
        if not drop:
            break
        for (kind, i), why in sorted(drop.items(), key=lambda x: -x[0][1]):
            gone = entries[kind].pop(i)
            left.append({"type": gone["_from"][0], "name": gone["_from"][1], "reason": why})
        entries = {k: v for k, v in entries.items() if v}
    return entries


def peek(records: dict, installs: list, site: str = "", others=None) -> dict:
    """What a site holds to capture before the app it goes into has a name (My apps' *From a site* reads first, as
    `ivn capture --new` does, so a site with nothing never leaves an empty app): the list, and what is left out. The
    renames are said once the app is named, at *Capture*."""
    r = capture(records, installs, {"manifest_version": 2, "app": "your_app", "prefix": "YOUR APP", "version": "1.0.0"},
                site, others)
    return {"items": r["items"], "left_out": r["left_out"]}


def others_of(fields, records: dict) -> dict:
    """{field name: record types} from the site's answer ``fields`` ([record type, field name] of every Custom Field named
    like one a person made), less the person's own fields."""
    mine = {(r.get("dt"), r.get("fieldname")) for r in records.get("Custom Field") or [] if isinstance(r, dict)}
    out = {}
    for f in fields or []:
        if isinstance(f, (list, tuple)) and len(f) == 2 and tuple(f) not in mine:
            out.setdefault(f[1], set()).add(f[0])
    return out


def person_fieldnames(records: dict) -> list:
    """The names of the fields a person made: the hosting asks the site which other record types use them too."""
    return sorted({r.get("fieldname") for r in records.get("Custom Field") or [] if isinstance(r, dict) and r.get("fieldname")})


def write(base: dict, result: dict, skip=(), only=()) -> tuple[dict, list]:
    """``base`` with the captured entries added (an entry already there by the same key is replaced), less ``skip`` (ids,
    kinds or record types) and, when ``only`` names some, only those; and the ids written. A field or role not written
    (unticked, or left out by the checker) keeps its own name wherever a written entry names it, and ``result["renamed"]``
    then says only the renames written."""
    def wanted(kind, e):
        keys = {f"{e['_from'][0]}/{e['_from'][1]}", kind, e["_from"][0], e["_from"][1]}
        return not (keys & set(skip)) and (not only or keys & set(only))
    chosen = {k: [e for e in rows if wanted(k, e)] for k, rows in result["entries"].items()}
    chosen = {k: v for k, v in chosen.items() if v}
    if "_raw" in result:  # renamed again from the site's names, with what is not written keeping its own
        ids = {e["_from"] for rows in chosen.values() for e in rows}
        raw = {k: [e for e in rows if e["_from"] in ids] for k, rows in result["_raw"].items()}
        written = {e.get("fieldname") for e in raw.get("custom_fields") or []}
        others, keep = {k: set(v) for k, v in (result.get("_others") or {}).items()}, set()
        for e in result["_raw"].get("custom_fields") or []:
            if e["_from"] in ids:
                continue
            if e.get("fieldname") in written:  # the same name written on another record type: theirs only about this one
                others.setdefault(e.get("fieldname"), set()).add(e.get("dt"))
            else:
                keep.add(e.get("fieldname"))
        keep |= {e.get("role") for e in result["_raw"].get("role_rights") or [] if e["_from"] not in ids}
        renamed, result["renamed"] = rename_to({k: v for k, v in raw.items() if v}, base["prefix"], others, keep - {None})
        chosen = _checked(renamed, base, result["left_out"])  # an entry that writes a field not written is left out
    m = copy.deepcopy(base)
    for kind, rows in chosen.items():
        key = _key_of(kind)
        new = [{k: v for k, v in r.items() if k != "_from"} for r in rows]
        mine = {tuple(r.get(x) for x in key) for r in new}
        m[kind] = [r for r in m.get(kind) or [] if tuple(r.get(x) for x in key) not in mine] + new
    return m, [f"{e['_from'][0]}/{e['_from'][1]}" for rows in chosen.values() for e in rows]


# what a second capture replaces an entry by: the record's own identity, as the install keys it (`extension_package.KEYS`),
# so an entry whose record type or table changed on the site replaces the one before, never stands beside it
KEY_OF = {"custom_fields": ("dt", "fieldname"), "property_setters": ("doc_type", "field_name", "property"),
          "list_settings": ("doctype",), "naming_rules": ("document_type", "prefix"),
          "links": ("doctype", "link_doctype", "link_fieldname"), "scan_sources": ("source_name",),
          "label_layouts": ("label_name",), "list_marks": ("record_type", "label"), "register_books": ("book",),
          "save_rules": ("rule_name",), "translations": ("language",), "role_rights": ("doctype", "role"),
          "field_rules": ("theme", "surface", "field", "action", "language")}


def _key_of(kind: str) -> tuple:
    return KEY_OF.get(kind, ("name",))  # the rest are named records


def lines(result: dict, site: str) -> list[str]:
    """What it found, grouped by record type, then the renames and what is left out, in plain lines."""
    if not result["items"] and not result["left_out"]:
        return [WORDS["nothing"].format(site=site)]
    out, by = [], {}
    for it in result["items"]:
        by.setdefault(it["type"], []).append(it["name"])
    for t, names in by.items():
        out.append(f"{t}: {', '.join(names)}")
    out += [f"Renamed: {x}" for x in result["renamed"]]
    out += [f"Left out: {x['type']} {x['name']}: {x['reason']}" for x in result["left_out"]]
    return out
