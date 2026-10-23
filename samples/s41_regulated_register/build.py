"""Build the Regulated stock register from its data sets: one app for any regulated stock, each market's (and each
vertical's) books a data set in datasets/, never code.

    python3 build.py                        # checks every data set, then writes manifest.json and door_declaration.json
    python3 build.py --sets ke_pharmacy --out ../my_register   # a shop's copy: only the named data sets' books

  manifest.json           what installs today: the Desk fields and the till's sale details that carry the register's
                          own columns (one per "own" detail of every data set), the approver role (through a report on
                          Stock Reconciliation, the counts the approver watches until the door's own count lands) and
                          the register's workspace.
  door_declaration.json   what installs once the register door (PB-4) is in the POS app: each book's declaration (the
                          manifest kind register_books), its print format on the register period, and a reminder before
                          each return's due date. Until then the shop's checker refuses the kind and the record types.
                          A shop's copy is built with --sets into a folder of its own (--out), never over this sample's
                          catalogue; its manifest still carries every data set's fields, so no build drops a field an
                          earlier one installed.

A data set is a JSON file: its books, which items each takes (by class or item group), its routing conditions (at most
three, all must hold, in the save-rule condition form), its columns and where each comes from, its numbering, balance,
correction mode and retention. check() below is the whole format: a data set it passes builds with no code change."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP, PREFIX, FPREFIX, VERSION = "pp_rsr", "PP RSR", "pp_rsr_", "0.1.3"
ROLE = "PP RSR Register Approver"
LINE, STATE, PERIOD = "Retail Register Line", "Retail Register State", "Retail Register Period"  # the door's record types
# The line's own columns (PB-4 spec §3.1). Routing and layouts may name only these, or a declared detail.
LINE_COLUMNS = (
    "number", "book", "register_store", "warehouse", "item", "item_name", "item_class", "batch_no", "expiry_date",
    "direction", "kind", "qty", "uom", "balance", "movement_date", "movement_time", "entered_at", "entry_date",
    "voucher_type", "voucher_no", "counterparty", "counterparty_address", "reference_no", "authority_no",
    "authority_issuer", "authority_issuer_licence", "authority_date", "dispenser", "dispenser_name", "dispenser_licence",
    "booked_late", "incomplete", "below_zero", "correction_of", "correction_of_number", "correction_note", "signed_by",
    "signed_by_name", "remarks", "period", "prev_hash", "line_hash",
)
# the line's number and tick-box columns: a condition on one compares as a number (the save-rule form does the same)
NUMERIC_COLUMNS = ("number", "qty", "balance", "booked_late", "incomplete", "below_zero", "correction_of_number")
# the line's date and time columns, and a declared Date detail: the condition form compares a date as text or as the
# number 0, so a condition on one only asks whether it is set (PB-4 spec §2)
DATE_COLUMNS = ("expiry_date", "movement_date", "movement_time", "entered_at", "entry_date", "authority_date")
SET_OPS = ("is set", "is not set")
DETAIL_SLOTS = 6
# a data set may name, per document type, the field a line column is read from where the door's default does not fit
SOURCE_TYPES = ("Purchase Receipt", "Purchase Invoice", "Subcontracting Receipt", "Stock Entry", "Sales Invoice",
                "Delivery Note", "POS Invoice")
SOURCE_COLUMNS = ("counterparty", "counterparty_address", "reference_no")
OPERATORS = ("=", "!=", ">", ">=", "<", "<=", "is set", "is not set")  # the save-rule form; never "in" (count_per_day's only)
NUMBER_OPS = (">", ">=", "<", "<=")
CORRECTIONS = {
    "reversing_line": "an error is re-entered on the next line, the original unmarked",
    "dated_note": "a dated note gives the correct particulars; the entry is never altered",
    "signed_strike_through": "a single strike-through, signed by its author",
    "signed_amendment": "a signed amendment beside the entry",
}
MEDIA = ("system_of_record", "printed_book", "official_book")  # the system · its signed printed pages · the authority's own book
DETAIL_TYPES = ("Data", "Date", "Small Text")
# a detail's sources: this app's own field (own), the till's sale detail and the Desk's field of another app, or one value
# of a record (PB-4 spec §2.2): the record named by the moving document's customer (match customer: a Customer; a receipt
# or a stock entry has none, so the column is empty), the one record of another type whose Link field `customer` names
# that customer (match customer_link: a record the customer's own readers cannot read, such as the counter-rules app's
# patient record; none, the column is empty), or by the line's dispenser (match user: a record named by its user)
DETAIL_KEYS = ("label", "type", "own", "till", "pos_sale_detail", "desk_field", "record")
LOOKUP_KEYS, LOOKUP_MATCH = ("doctype", "match", "field"), ("user", "customer", "customer_link")
PERIOD_MONTHS = (1, 2, 3, 4, 6, 12)  # a period starts on 1 January, and every period_months after it (PB-4 spec §7)
NAME_MAX = 61  # the shop's name rule for a print format or a reminder (tools/manifest/validate.py)
_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PLAIN = re.compile(r"^[^<>{}%]*$")  # text printed or shown in Desk: no markup, no template syntax
# insert_after on each record type: the last field before its Connections tab (read on the bench, 2026-10-22)
DESK_TYPES = (("Sales Invoice", "remarks"), ("Delivery Note", "instructions"))


def _read(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return f.read()


def datasets(folder="datasets"):
    return [json.loads(_read(os.path.join(folder, n))) for n in sorted(os.listdir(os.path.join(HERE, folder)))
            if n.endswith(".json")]


def _text(v):
    return isinstance(v, str) and bool(v.strip()) and bool(_PLAIN.match(v))


def check(ds):
    """Every way a data set can be wrong, in words; [] = it builds."""
    bad = []
    if ds.get("format") != 1:
        bad.append("format: 1")
    for k in ("id",):
        if not (isinstance(ds.get(k), str) and _ID.match(ds[k])):
            bad.append(f"{k}: lower-case letters, digits and _")
    for k in ("title", "notice", "jurisdiction", "vertical"):
        if not _text(ds.get(k)):
            bad.append(f"{k}: plain text")
    if ds.get("certified") not in (0, 1):
        bad.append("certified: 0 or 1 (0 until a partner certifies the layouts for the country)")
    if not (isinstance(ds.get("sources"), list) and ds["sources"] and all(_text(s) for s in ds["sources"])):
        bad.append("sources: the instruments, as plain text")
    details = ds.get("details") or {}
    if len(details) > DETAIL_SLOTS:
        bad.append(f"details: at most {DETAIL_SLOTS} (the line's detail slots)")
    for key, d in details.items():
        if not (_ID.match(key) and isinstance(d, dict) and _text(d.get("label")) and d.get("type") in DETAIL_TYPES):
            bad.append(f"details.{key}: a key, a plain label and a type of {', '.join(DETAIL_TYPES)}")
        elif d.get("till", 1) not in (0, 1) or d.get("own", 0) not in (0, 1):
            bad.append(f"details.{key}: own and till are 0 or 1")
        elif set(d) - set(DETAIL_KEYS):
            bad.append(f"details.{key}: {', '.join(sorted(set(d) - set(DETAIL_KEYS)))} is not a key of a detail")
        elif "record" in d and not _lookup_ok(d["record"]):
            bad.append(f"details.{key}.record: the record's type, match (user, customer_link, or customer for a Customer) and field")
        elif "record" in d and (d.get("own") or "pos_sale_detail" in d or "desk_field" in d or "till" in d):
            bad.append(f"details.{key}: a detail read from a record has no other source and no till")
        elif d.get("own") and ("pos_sale_detail" in d or "desk_field" in d):
            bad.append(f"details.{key}: an own detail's sources are this app's: it names no other")
        elif not (_text(d.get("pos_sale_detail", "x")) and _ID.match(d.get("desk_field", "xx") or "")):
            bad.append(f"details.{key}: a sale detail's name in plain text, a Desk field's name in lower case")
    dl = (ds.get("authority") or {}).get("dispenser_licence")
    if dl is not None and (not _lookup_ok(dl) or dl.get("match") == "customer_link"):
        bad.append("authority.dispenser_licence: the record's type, match (user or customer) and field")
    known = set(LINE_COLUMNS) | {f"detail:{k}" for k in details}
    looked_up = {f"detail:{k}" for k, d in details.items() if isinstance(d, dict) and "record" in d}
    dated = set(DATE_COLUMNS) | {f"detail:{k}" for k, d in details.items() if isinstance(d, dict) and d.get("type") == "Date"}
    cf = ds.get("columns_from", {})
    if not (isinstance(cf, dict) and all(dt in SOURCE_TYPES and isinstance(m, dict)
                                         and all(c in SOURCE_COLUMNS and _ID.match(f or "") for c, f in m.items())
                                         for dt, m in cf.items())):
        bad.append("columns_from: {document type: {line column: the document's field}}, for "
                   f"{', '.join(SOURCE_COLUMNS)} on {', '.join(SOURCE_TYPES)}")
    books = ds.get("books")
    if not (isinstance(books, list) and books):
        return bad + ["books: at least one"]
    ids = [b.get("id") for b in books]
    if len(set(ids)) != len(ids):
        bad.append("books: an id twice")
    for b in books:
        w = f"books.{b.get('id')}"
        if not (isinstance(b.get("id"), str) and _ID.match(b["id"])):
            bad.append(f"{w}.id: lower-case letters, digits and _")
        for k in ("title", "cite"):
            if not _text(b.get(k)):
                bad.append(f"{w}.{k}: plain text")
        has_classes, has_groups = bool(b.get("classes")), bool(b.get("item_groups"))
        if has_classes == has_groups:
            bad.append(f"{w}: its items are classes or item groups, one of the two")
        cs = b.get("class_source")
        if has_classes and not _class_source_ok(cs):
            bad.append(f"{w}: classes need the book's class_source: an Item field, or an Item table with its class "
                       "field, its from-date field and the axis")
        if "form" in b and not _text(b["form"]):
            bad.append(f"{w}.form: plain text")
        for k in ("classes", "item_groups"):
            if b.get(k) is not None and not (isinstance(b[k], list) and all(_text(x) for x in b[k])):
                bad.append(f"{w}.{k}: a list of names")
        conds = b.get("conditions", [])
        if not isinstance(conds, list) or len(conds) > 3:
            bad.append(f"{w}.conditions: at most 3, all of which must hold")
            conds = []
        for i, c in enumerate(conds):
            op = c.get("operator") if isinstance(c, dict) else None
            if op not in OPERATORS:
                bad.append(f"{w}.conditions[{i}]: the operator is one of {', '.join(OPERATORS)}")
            if not isinstance(c, dict) or c.get("field") not in known:
                bad.append(f"{w}.conditions[{i}]: a condition reads a column of the line")
            elif c["field"] in looked_up:
                bad.append(f"{w}.conditions[{i}]: {c['field']} is read from a record: the door does not route on it")
            elif c["field"] in dated and op not in SET_OPS:
                bad.append(f"{w}.conditions[{i}]: {c['field']} is a date or a time: a condition on it is is set or "
                           "is not set")
            elif op in NUMBER_OPS and not isinstance(c.get("value"), (int, float)):
                bad.append(f"{w}.conditions[{i}]: {op} compares a number (a date is not one)")
            elif op in ("=", "!=") and not isinstance(c.get("value"), (str, int, float)):
                bad.append(f"{w}.conditions[{i}]: = and != need a value")
        if b.get("numbering") not in ("book_store", "book_store_item"):
            bad.append(f"{w}.numbering: book_store or book_store_item")
        if b.get("balance") not in (0, 1):
            bad.append(f"{w}.balance: 0 or 1")
        if b.get("per_item_pages") and b.get("numbering") != "book_store_item":
            bad.append(f"{w}: a page per item numbers per item (book_store_item)")
        if b.get("correction") not in CORRECTIONS:
            bad.append(f"{w}.correction: one of {', '.join(CORRECTIONS)}")
        if b.get("medium") not in MEDIA:
            bad.append(f"{w}.medium: one of {', '.join(MEDIA)}")
        if not (isinstance(b.get("retention_years"), int) and 1 <= b["retention_years"] <= 30):
            bad.append(f"{w}.retention_years: 1 to 30")
        if "loss_count_hours" in b and not (_whole(b["loss_count_hours"]) and b["loss_count_hours"] > 0):
            bad.append(f"{w}.loss_count_hours: a whole number above 0")
        if "period_months" in b or "return_due_days" in b:
            if not (_whole(b.get("period_months")) and b["period_months"] in PERIOD_MONTHS):
                bad.append(f"{w}.period_months: one of {', '.join(map(str, PERIOD_MONTHS))} (a period starts on "
                           "1 January, and every period_months after it)")
            if not (_whole(b.get("return_due_days")) and 0 <= b["return_due_days"] <= 366):
                bad.append(f"{w}.return_due_days: the days after the period's last day its return is due, 0 to 366 "
                           "(0: due on that day, where the law names no day)")
            if len(reminder_name(ds, b)) > NAME_MAX:
                bad.append(f"{w}: its reminder's name, '{reminder_name(ds, b)}', is over {NAME_MAX} characters: "
                           "shorten the data set's or the book's id")
        if "in_colour" in b and not (isinstance(b["in_colour"], str) and _COLOUR.match(b["in_colour"])):
            bad.append(f"{w}.in_colour: #rrggbb")
        if "medium_note" in b and not _text(b["medium_note"]):
            bad.append(f"{w}.medium_note: plain text")
        cols = b.get("columns")
        if not (isinstance(cols, list) and cols):
            bad.append(f"{w}.columns: at least one")
            cols = []
        for i, c in enumerate(cols):
            if not (isinstance(c, dict) and _text(c.get("label")) and isinstance(c.get("value"), list) and c["value"]):
                bad.append(f"{w}.columns[{i}]: a plain label and a list of the line's columns")
                continue
            for v in c["value"]:
                if v not in known:
                    bad.append(f"{w}.columns[{i}]: '{v}' is not a column of the line or a declared detail")
            if c.get("when") not in (None, "In", "Out"):
                bad.append(f"{w}.columns[{i}].when: In or Out")
        for r in b.get("required", []):
            if r not in known:
                bad.append(f"{w}.required: '{r}' is not a column of the line or a declared detail")
    return bad


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _lookup_ok(r):
    return isinstance(r, dict) and set(r) == set(LOOKUP_KEYS) and _text(r["doctype"]) and r["match"] in LOOKUP_MATCH \
        and (r["match"] == "customer") == (r["doctype"] == "Customer") and _ID.match(r["field"] or "") is not None


def _class_source_ok(cs):
    if not isinstance(cs, dict):
        return False
    if set(cs) == {"item_field"}:
        return _ID.match(cs["item_field"] or "") is not None
    # an Item table of dated schedule rows; optionally the Item Group's own field, read where the item has no row
    return set(cs) - {"group_field"} == {"item_table", "class_field", "from_field", "axis"} and all(
        _ID.match(cs.get(k) or "") for k in ("item_table", "class_field", "from_field")
        + (("group_field",) if "group_field" in cs else ())) and _text(cs["axis"])


def slots(ds):
    """detail key -> the line's detail slot, in the order the data set declares them."""
    return {k: f"detail_{i}" for i, k in enumerate(ds.get("details") or {}, 1)}


def _col(ds, name):
    return slots(ds)[name[7:]] if name.startswith("detail:") else name


def book_ref(ds, b):
    return f"{ds['id']}.{b['id']}"


def reminder_name(ds, b):
    """The return's reminder: the ids, not the titles (two data sets may share a title), with a space between, which
    an id never holds, so no two books share one; the shop's name rule takes no dot."""
    return f"{PREFIX} Return due {ds.get('id')} {b.get('id')}"


def book_data(ds, b):
    """The book as its print reads it: every detail named by its slot."""
    cols = [{**c, "value": [_col(ds, v) for v in c["value"]]} for c in b["columns"]]
    fields = sorted({"number", "direction", "kind", "correction_of_number", "correction_note", "signed_by_name",
                     "dispenser_name", "entry_date", "entered_at", "booked_late", "remarks"} | {v for c in cols for v in c["value"]})
    out = {"ref": book_ref(ds, b), "title": b["title"], "form": b.get("form", ""), "cite": b["cite"],
           "data_set_title": ds["title"], "certified": ds["certified"], "notice": ds["notice"], "columns": cols,
           "fields": fields, "correction": b["correction"], "correction_words": CORRECTIONS[b["correction"]],
           "retention_years": b["retention_years"], "medium_note": b.get("medium_note", ""),
           "per_item_pages": b.get("per_item_pages", 0), "medium": b["medium"], "balance": b["balance"]}
    if b.get("in_colour"):
        out["in_colour"] = b["in_colour"]
    return out


def _literal(v):
    """A Jinja literal of a JSON value (Jinja's words for true, false and none)."""
    if isinstance(v, bool) or v is None:
        return {True: "true", False: "false", None: "none"}[v]
    if isinstance(v, dict):
        return "{" + ", ".join(f"{json.dumps(k)}: {_literal(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_literal(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def book_html(ds, b):
    return "{%- set book = " + _literal(book_data(ds, b)) + " -%}\n" + _read("layouts/register.html")


def _all_checked(sets):
    for ds in sets:
        bad = check(ds)
        if bad:
            raise SystemExit(f"data set {ds.get('id')}: " + "; ".join(bad))
    ids = [ds["id"] for ds in sets]
    if len(set(ids)) != len(ids):
        raise SystemExit("two data sets with one id")


def sale_detail(key):
    """The till's sale detail for an own column: the prefix and the key in words (a name takes letters, digits and spaces)."""
    return f"{PREFIX} {key.replace('_', ' ').title()}"


def own_details(sets):
    """The register's own columns across every data set: one Desk field and one sale detail each, the first type wins
    (two data sets naming one key must agree on its type)."""
    out = {}
    for ds in sets:
        for k, d in (ds.get("details") or {}).items():
            if d.get("own"):
                if k in out and (out[k]["type"], out[k].get("till", 1)) != (d["type"], d.get("till", 1)):
                    raise SystemExit(f"detail {k}: two data sets give it two types, or one keeps it off the till")
                out.setdefault(k, d)
    return out


def build_manifest(sets=None):
    sets = datasets() if sets is None else sets
    _all_checked(sets)
    own = own_details(sets)
    fields = []
    for dt, after in DESK_TYPES:
        fields.append({"dt": dt, "fieldname": f"{FPREFIX}section", "fieldtype": "Section Break", "label": "Register details",
                       "insert_after": after, "collapsible": 1,
                       "description": "For the regulated stock register: copied into the register's line when this "
                                      "document is submitted."})
        prev = f"{FPREFIX}section"
        for k, d in own.items():
            fields.append({"dt": dt, "fieldname": FPREFIX + k, "fieldtype": d["type"], "label": d["label"],
                           "insert_after": prev})
            prev = FPREFIX + k
    return {
        "manifest_version": 2, "app": APP, "prefix": PREFIX, "title": "Regulated stock register", "version": VERSION,
        "publisher": "Partner Programme sample",
        "description": "A legal register for regulated stock (controlled medicine, liquor, tobacco, duty-free), its books "
                       "declared per market as data. This version adds the register's own columns to the Desk sale and "
                       "delivery and to the till's sale details, the approver role and the register's workspace. The "
                       "books themselves are written by the register door in the POS app, once it is there.",
        "custom_fields": fields,
        "sale_attributes": [{"name": sale_detail(k)} for k, d in own.items() if d.get("till", 1)],
        "reports": [{
            "name": f"{PREFIX} Stock counts to watch", "ref_doctype": "Stock Reconciliation", "report_type": "Report Builder",
            "columns": ["name", "posting_date", "purpose", "set_warehouse", "docstatus"],
            "filters": [["docstatus", "!=", 2]], "order_by": "posting_date desc", "roles": [ROLE],
        }],
        "workspaces": [{
            "name": f"{PREFIX} Regulated stock register",
            "blocks": [
                {"type": "header", "data": {"text": "<span class=\"h4\">Regulated stock register</span>", "col": 12}},
                {"type": "paragraph", "data": {"text": (
                    "Open tasks. Until the register door is in your POS app, the books are kept as before: fill the "
                    "Register details on each Desk sale and delivery of a regulated item, and the till's sale details "
                    "for each counter sale. Before a stock count of a regulated item, check it with your Register "
                    "Approver: search Desk for Stock counts to watch. Print the day's register pages at each day's "
                    "close and keep them at the store, for an outage."), "col": 12}},
                {"type": "shortcut", "data": {"shortcut_name": "Stock counts", "col": 3}},
                {"type": "shortcut", "data": {"shortcut_name": "Sales invoices", "col": 3}},
                {"type": "shortcut", "data": {"shortcut_name": "Delivery notes", "col": 3}},
                {"type": "shortcut", "data": {"shortcut_name": "Purchase receipts", "col": 3}},
            ],
            "shortcuts": [
                {"type": "DocType", "link_to": "Stock Reconciliation", "label": "Stock counts"},
                {"type": "DocType", "link_to": "Sales Invoice", "label": "Sales invoices"},
                {"type": "DocType", "link_to": "Delivery Note", "label": "Delivery notes"},
                {"type": "DocType", "link_to": "Purchase Receipt", "label": "Purchase receipts"},
            ],
        }],
    }


def _sources(key, d):
    """Where the door reads a detail. None of the three: the column prints empty, for the shop to write in."""
    if d.get("own"):
        return {**({"pos_sale_detail": sale_detail(key)} if d.get("till", 1) else {}), "desk_field": FPREFIX + key}
    return {k: d[k] for k in ("pos_sale_detail", "desk_field", "record") if k in d}


def declaration(ds, b):
    """One book as the door's manifest kind register_books takes it (PB-4 spec §2)."""
    d = {"book": book_ref(ds, b), "title": b["title"], "data_set": ds["id"], "cite": b["cite"],
         "certified": ds["certified"], "numbering": b["numbering"], "balance": b["balance"],
         "correction": b["correction"], "retention_years": b["retention_years"], "count_role": ROLE,
         "conditions": [{**c, "field": _col(ds, c["field"])} for c in b.get("conditions", [])],
         "required": [_col(ds, r) for r in b.get("required", [])],
         "columns": [{"label": c["label"], "value": [_col(ds, v) for v in c["value"]]} for c in b["columns"]],
         "details": {slots(ds)[k]: {"label": x["label"], **_sources(k, x)} for k, x in (ds.get("details") or {}).items()},
         "authority": ds.get("authority", {}), "columns_from": ds.get("columns_from", {}), "enabled": 1}
    if b.get("classes"):
        d["items"] = {"classes": b["classes"]}
        d["class_source"] = b["class_source"]
    else:
        d["items"] = {"item_groups": b["item_groups"]}
    for k in ("period_months", "return_due_days", "loss_count_hours"):
        if k in b:
            d[k] = b[k]
    return d


def build_declaration(sets=None):
    sets = datasets() if sets is None else sets
    _all_checked(sets)
    books = [(ds, b) for ds in sets for b in ds["books"]]
    return {
        "waits_for": "PB-4, the register door in the POS app",
        "version": "0.2.0",
        "data_sets": [ds["id"] for ds in sets],
        "register_books": [declaration(ds, b) for ds, b in books],
        "print_formats": [{"name": f"{PREFIX} {ds['title'].split(':')[0]} {b['title']}", "doc_type": PERIOD,
                           "print_format_type": "Jinja", "html": book_html(ds, b)} for ds, b in books],
        "notifications": [{"name": reminder_name(ds, b), "document_type": PERIOD,
                           "event": "Days Before", "date_changed": "return_due", "days_in_advance": 7,
                           "channel": "System Notification",
                           "subject": "The {{ doc.book }} return for {{ doc.register_store }} is due on {{ doc.return_due }}",
                           "recipients": [{"receiver_by_role": ROLE}]}
                          for ds, b in books if b.get("period_months")],
    }


def chosen(ids, sets=None):
    """The data sets named, in the order given; an id no data set has is refused."""
    sets = datasets() if sets is None else sets
    by_id = {ds.get("id"): ds for ds in sets}
    unknown = [i for i in ids if i not in by_id]
    if unknown or not ids or len(set(ids)) != len(ids):
        raise SystemExit(f"--sets: {', '.join(unknown) or 'none named, or one named twice'}; the data sets are "
                         f"{', '.join(by_id)}")
    return [by_id[i] for i in ids]


def build_files(ids=None):
    """The manifest from every data set (a shop's update never drops a field an earlier version installed), and the
    declaration from the shop's own data sets (all, when none are named)."""
    sets = datasets()
    return build_manifest(sets), build_declaration(sets if ids is None else chosen(ids, sets))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and not (len(argv) == 4 and argv[0] == "--sets" and argv[2] == "--out"):
        raise SystemExit("usage: build.py [--sets id,id --out folder]")
    out = os.path.abspath(argv[3]) if argv else HERE
    if argv and out == HERE:
        raise SystemExit("--out: a shop's copy goes in a folder of its own, never over this sample's catalogue")
    m, d = build_files(argv[1].split(",") if argv else None)
    os.makedirs(out, exist_ok=True)
    for name, obj in (("manifest.json", m), ("door_declaration.json", d)):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
            f.write("\n")
    print(f"manifest.json: {len(m['custom_fields'])} fields, {len(m['sale_attributes'])} sale details; "
          f"door_declaration.json: {len(d['register_books'])} books, {len(d['print_formats'])} print formats")


if __name__ == "__main__":
    sys.exit(main())
