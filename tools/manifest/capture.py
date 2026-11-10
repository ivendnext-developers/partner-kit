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
   in a workflow's condition, a notification's message, a print format, a property setter, a list's columns. A role made in
   Desk takes the prefix too (`Store Approver` becomes `ACME RULES Store Approver`), as a role an app brings must.
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
from validate import DOCPERM_RIGHTS, REFUSED_KINDS, RIGHTS, field_prefix, validate  # noqa: E402

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
    "Workspace": [],
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
}
# the types whose records come one by one, with their child rows; the rest come whole from the list
WITH_CHILDREN = {"Workflow", "Notification", "DocType", "Report", "Workspace", "Dashboard", "Document Naming Rule"}
# the types whose `module` marks an app's record: Desk itself sets the module of a person's print format, report and record
# type (from the record type it is for), so those are judged by their standard mark and the install records alone
MODULE_MARKS = {"Custom Field", "Property Setter", "Notification", "Workspace", "Number Card", "Dashboard Chart",
                "Dashboard", "List View Settings", "Document Naming Rule", "Webhook", "Translation", "Role"}
# a person's own records only: the hosting asks the site for these alone (`owner` set and not Administrator)
PERSON_FILTER = [["owner", "is", "set"], ["owner", "!=", "Administrator"]]
INSTALL = "Retail Extension Install"  # each installed app's record: `items`, every record it made, by kind and name

# the install record's kinds, as the record types they made
ITEM_TYPES = {"custom_field": "Custom Field", "property_setter": "Property Setter", "workflow": "Workflow",
              "notification": "Notification", "print_format": "Print Format", "naming_rule": "Document Naming Rule",
              "list_settings": "List View Settings", "doctype": "DocType", "workspace": "Workspace", "report": "Report",
              "number_card": "Number Card", "dashboard_chart": "Dashboard Chart", "dashboard": "Dashboard",
              "webhook": "Webhook", "role": "Role"}

# the words for what the manifest cannot carry (the rest are the checker's own)
WORDS = {
    "script": REFUSED_KINDS,
    "report_kind": "a {kind} runs code on the site; the manifest takes a Report Builder report",
    "builder_print": "made in the Print Format Builder, which the manifest does not carry: make it as an HTML print "
                     "format (Custom Format) and capture again",
    "their_role": "a right for {role}, one of the customer's own roles: the customer gives it in Role Permissions Manager",
    "nothing": "Nothing made in Desk to capture on {site}: a record counts when a person signed in as themselves made it, "
               "not as Administrator. Made it as Administrator? Make your own user with System Manager in Desk, sign in as "
               "it, make the set-up again, then capture.",
    "off": "it is switched off on {site}: switch it on there to capture it",
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
                      "date_changed", "value_changed", "send_to_all_assignees", "attach_print", "print_format"),
    "naming_rules": ("document_type", "prefix", "prefix_digits", "priority"),
    "doctypes": ("name", "description", "autoname", "naming_rule", "istable", "issingle", "is_submittable",
                 "title_field", "search_fields", "show_title_field_in_link", "sort_field", "sort_order",
                 "track_changes", "editable_grid", "quick_entry"),
    "number_cards": ("name", "document_type", "function", "aggregate_function_based_on", "filters_json", "color",
                     "is_public"),
    "dashboard_charts": ("name", "document_type", "chart_type", "based_on", "value_based_on", "group_by_type",
                         "group_by_based_on", "timespan", "time_interval", "type", "filters_json", "color",
                         "is_public"),
}
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
    return [_kept(r, CHILD_KEEP[kind]) for r in rec.get(key) or [] if isinstance(r, dict)]


def _json(v, default):
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v or "null") or default
    except (TypeError, ValueError):
        return default


# ── 1. only what a person made ──

def made_by_person(records: dict, installs: list) -> dict:
    """``records`` ({record type: [records]}) less everything the product or an installed app made."""
    by_apps = {(ITEM_TYPES.get(i.get("kind")), i.get("name")) for inst in installs or [] for i in _json(inst.get("items"), [])
               if isinstance(i, dict)}
    out = {}
    for dt, rows in (records or {}).items():
        keep = []
        for r in rows or []:
            if not isinstance(r, dict) or r.get("owner") in (None, "", "Administrator") \
                    or (dt in MODULE_MARKS and r.get("module")):
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

    for r in records.get("Custom Field", []):
        add("custom_fields", _kept(r, KEEP["custom_fields"]), ("Custom Field", r["name"]))
    for r in records.get("Property Setter", []):
        if r.get("property") == "field_order":
            out.append({"type": "Property Setter", "name": r["name"], "reason": WORDS["field_order"]})
            continue
        add("property_setters", _kept(r, KEEP["property_setters"]) | {"value": r.get("value")}, ("Property Setter", r["name"]))
    for r in records.get("Workflow", []):
        if not r.get("is_active"):
            out.append({"type": "Workflow", "name": r["name"], "reason": WORDS["off"].format(site=site or "the site")})
            continue
        add("workflows", {"name": r["name"], "document_type": r.get("document_type"),
                          **({"send_email_alert": 1} if r.get("send_email_alert") else {}),
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
    roles = {r["name"] for r in records.get("Role", [])}
    for p in records.get("Custom DocPerm", []):
        rights = [k for k in RIGHTS if p.get(k)]
        if p.get("role") in roles:
            add("role_rights", {"doctype": p.get("parent"), "role": p["role"], "rights": rights}, ("Role", p["role"]))
        elif rights:
            out.append({"type": "Custom DocPerm", "name": f"{p.get('parent')}: {p.get('role')}",
                        "reason": WORDS["their_role"].format(role=p.get("role"))})
    for r in records.get("Workspace", []):
        add("workspaces", _workspace(r), ("Workspace", r["name"]))
    for r in records.get("Report", []):
        if r.get("report_type") != "Report Builder":
            out.append({"type": "Report", "name": r["name"], "reason": WORDS["report_kind"].format(
                kind=str(r.get("report_type") or "report").lower())})
            continue
        add("reports", _report(r), ("Report", r["name"]))
    for r in records.get("Number Card", []):
        add("number_cards", _kept(r, KEEP["number_cards"]), ("Number Card", r["name"]))
    for r in records.get("Dashboard Chart", []):
        add("dashboard_charts", _kept(r, KEEP["dashboard_charts"]), ("Dashboard Chart", r["name"]))
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
    return e, out


# ── 3. renamed to your app ──

def rename_to(entries: dict, prefix: str) -> tuple[dict, list]:
    """The entries with each field made in Desk (`custom_…`, or any name without the app's prefix on a customer's record
    type) and each role made in Desk under the app's prefix, wherever a string names them; and one line per rename."""
    fp, own = field_prefix(prefix), {d.get("name") for d in entries.get("doctypes") or []}
    fields, lines = {}, []
    for c in entries.get("custom_fields") or []:
        fn = c.get("fieldname") or ""
        if c.get("dt") in own or fn.startswith(fp):
            continue
        new = fp + re.sub(r"^custom_", "", fn)
        fields[fn] = new
        lines.append(f"{c.get('dt')}: {fn} is {new}")
    roles = {}
    for r in entries.get("role_rights") or []:
        old = r.get("role") or ""
        if old and not old.startswith(prefix + " ") and old not in roles:
            roles[old] = f"{prefix} {old}"
            lines.append(f"the role {old} is {roles[old]}")
    if not fields and not roles:
        return entries, lines
    field_re = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(f) for f in sorted(fields, key=len, reverse=True))
                          + r")(?![A-Za-z0-9_])") if fields else None

    def one(s: str) -> str:
        if s in roles:  # a role is named by the whole value (a state's allow_edit, a recipient's role, a permission's role)
            return roles[s]
        return field_re.sub(lambda m: fields[m.group(1)], s) if field_re else s

    def walk(o):
        if isinstance(o, dict):
            return {k: (v if k == "_from" else walk(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return one(o) if isinstance(o, str) else o
    return walk(copy.deepcopy(entries)), lines


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


def capture(records: dict, installs: list, base: dict, site: str = "") -> dict:
    """Everything a person made on the site, as entries for the app whose manifest is ``base``:
    ``{"entries": {kind: [...]}, "items": [{"id", "kind", "type", "name"}], "left_out": [...], "renamed": [...]}``.
    Each entry and item carries an ``id`` (``Type/name``) to untick by."""
    entries, left = to_entries(made_by_person(records, installs), site)
    entries, renamed = rename_to(entries, base["prefix"])
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
    items = [{"id": f"{e['_from'][0]}/{e['_from'][1]}", "kind": kind, "type": e["_from"][0], "name": e["_from"][1]}
             for kind, rows in entries.items() for e in rows]
    return {"entries": entries, "items": items, "left_out": left, "renamed": renamed}


def write(base: dict, result: dict, skip=(), only=()) -> tuple[dict, list]:
    """``base`` with the captured entries added (an entry already there by the same key is replaced), less ``skip`` (ids,
    kinds or record types) and, when ``only`` names some, only those; and the ids written."""
    def wanted(kind, e):
        keys = {f"{e['_from'][0]}/{e['_from'][1]}", kind, e["_from"][0], e["_from"][1]}
        return not (keys & set(skip)) and (not only or keys & set(only))
    chosen = {k: [e for e in rows if wanted(k, e)] for k, rows in result["entries"].items()}
    chosen = {k: v for k, v in chosen.items() if v}
    m = copy.deepcopy(base)
    for kind, rows in chosen.items():
        key = _key_of(kind)
        new = [{k: v for k, v in r.items() if k != "_from"} for r in rows]
        mine = {tuple(r.get(x) for x in key) for r in new}
        m[kind] = [r for r in m.get(kind) or [] if tuple(r.get(x) for x in key) not in mine] + new
    return m, [f"{e['_from'][0]}/{e['_from'][1]}" for rows in chosen.values() for e in rows]


def _key_of(kind: str) -> tuple:
    from validate import KEYED  # noqa: PLC0415
    return {"property_setters": ("doc_type", "field_name", "property")}.get(kind) or KEYED.get(kind, ("name",))[:2]


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
