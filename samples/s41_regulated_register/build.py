"""Build the Regulated stock register from its data sets: one app for any regulated stock, each market's (and each
vertical's) books a data set in datasets/, never code.

    python3 build.py                        # checks every data set, then writes manifest.json
    python3 build.py --sets ke_pharmacy --out ../my_register   # a shop's copy: only the named data sets' books

  manifest.json           everything the app installs, on the POS app's register door: the Desk fields and the till's
                          sale details that carry the register's own columns (one per "own" detail of every data set),
                          each book's declaration (the manifest kind register_books), its print format on the register
                          period, a purchaser's slip where a book asks for one, a reminder before each return's due date,
                          the register's lists, its open-tasks cards and the register's workspace.
                          This sample's catalogue installs every data set's books switched off: the shop switches its
                          own market's on. A shop's copy, built with --sets into a folder of its own (--out), holds only
                          its own markets' books, switched on; its manifest still carries every data set's fields, so no
                          build drops a field an earlier one installed.

A data set is a JSON file: its books, which items each takes (by class or item group), its routing conditions (at most
three, all must hold, in the save-rule condition form), its columns and where each comes from, its numbering, balance,
correction mode and retention. check() below is the format: a data set it passes builds with no code change, and the
build runs the shop's own checker (tools/manifest/validate.py) on the manifest before it writes it. What only the shop's
site can know (a field, a sale detail or a record type it names) the door checks at install."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP, PREFIX, FPREFIX, VERSION = "pp_rsr", "PP RSR", "pp_rsr_", "0.2.0"
ROLE = "PP RSR Register Approver"
LINE, STATE, PERIOD = "Retail Register Line", "Retail Register State", "Retail Register Period"  # the door's record types
# The line's own columns (the door's REGISTER_LINE_COLUMNS). Routing and layouts may name only these, or a declared detail.
LINE_COLUMNS = (
    "number", "book", "register_store", "warehouse", "item", "item_name", "item_class", "batch_no", "expiry_date",
    "direction", "kind", "qty", "uom", "balance", "movement_date", "movement_time", "entered_at", "entry_date",
    "voucher_type", "voucher_no", "counterparty", "counterparty_address", "reference_no", "authority_no",
    "authority_issuer", "authority_issuer_licence", "authority_date", "dispenser", "dispenser_name", "dispenser_licence",
    "booked_late", "incomplete", "below_zero", "correction_of", "correction_of_number", "correction_note", "signed_by",
    "signed_by_name", "remarks", "period",
)
# the line's number and tick-box columns: a condition on one compares as a number (the save-rule form does the same)
NUMERIC_COLUMNS = ("number", "qty", "balance", "booked_late", "incomplete", "below_zero", "correction_of_number")
# the line's date and time columns, and a declared Date detail: the condition form compares a date as text or as the
# number 0, so a condition on one only asks whether it is set (the door's rule)
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
# the system · its signed printed pages · the authority's own book · the authority's own system, this one its working copy
MEDIA = ("system_of_record", "printed_book", "official_book", "regulator_system")
# Age: whole years at the movement's date, worked out by the door from a date of birth its record lookup reads
DETAIL_TYPES = ("Data", "Date", "Small Text", "Age")
# a detail's sources: this app's own field (own), the till's sale detail and the Desk's field of another app, or one value
# of a record (the door's lookup): the record named by the moving document's customer (match customer: a Customer; a receipt
# or a stock entry has none, so the column is empty), the one record of another type whose Link field `customer` names
# that customer (match customer_link: a record the customer's own readers cannot read, such as the counter-rules app's
# patient record; none, the column is empty), or by the line's dispenser (match user: a record named by its user)
# person: 1 says the detail names a person (the one supplied, or a third), whose details the door erases once the book's
# retention has passed; not given, the door counts only a detail read from the customer's records, or an Age, a person's
DETAIL_KEYS = ("label", "type", "own", "till", "pos_sale_detail", "desk_field", "record", "person")
LOOKUP_KEYS, LOOKUP_MATCH = ("doctype", "match", "field"), ("user", "customer", "customer_link")
PERIOD_MONTHS = (1, 2, 3, 4, 6, 12)  # a period starts on 1 January, and every period_months after it (the door's)
NAME_MAX = 61  # the shop's name rule for a print format or a reminder (tools/manifest/validate.py)
_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_LANG = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")  # a print's language, as the shop names it (ar, pt-BR)
# a column may print the balance before its line, which the door's print works out (never routed on, never required)
PRINTED_ONLY = ("balance_before",)
# every key a data set, a book, a column and a condition may carry: an unknown one (a typo, a key a later version dropped)
# is refused, never silently left out of the book
SET_KEYS = ("format", "id", "title", "jurisdiction", "vertical", "sources", "certified", "notice", "details", "authority",
            "columns_from", "books", "print_language")
BOOK_KEYS = ("id", "title", "form", "cite", "classes", "item_groups", "class_source", "conditions", "numbering", "balance",
             "correction", "retention_years", "medium", "medium_note", "loss_count_hours", "period_months",
             "return_due_days", "in_colour", "required", "columns", "purchaser_slip")
COLUMN_KEYS = ("label", "value", "when", "mark", "group")
CONDITION_KEYS = ("field", "operator", "value")
AUTHORITY_KEYS = ("pos_sale_details", "desk_fields", "dispenser_licence")
AUTHORITY_COLUMNS = ("authority_no", "authority_issuer", "authority_issuer_licence", "authority_date")
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
    if set(ds) - set(SET_KEYS):
        bad.append(f"{', '.join(sorted(set(ds) - set(SET_KEYS)))}: not a key of a data set")
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
    if "print_language" in ds and not (isinstance(ds["print_language"], str) and _LANG.match(ds["print_language"])):
        bad.append("print_language: a language code, such as ar or pt-BR (the books print in it, right to left in Arabic)")
    details = ds.get("details") or {}
    if len(details) > DETAIL_SLOTS:
        bad.append(f"details: at most {DETAIL_SLOTS} (the line's detail slots)")
    for key, d in details.items():
        if not (_ID.match(key) and isinstance(d, dict) and _text(d.get("label")) and d.get("type") in DETAIL_TYPES):
            bad.append(f"details.{key}: a key, a plain label and a type of {', '.join(DETAIL_TYPES)}")
        elif d.get("till", 1) not in (0, 1) or d.get("own", 0) not in (0, 1) or d.get("person", 0) not in (0, 1):
            bad.append(f"details.{key}: own, till and person are 0 or 1")
        elif d["type"] == "Age" and "record" not in d:
            bad.append(f"details.{key}: an Age is worked out from a date of birth a record lookup reads (record)")
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
    auth = ds.get("authority") or {}
    if not isinstance(auth, dict) or set(auth) - set(AUTHORITY_KEYS):
        bad.append(f"authority: its sources go under {', '.join(AUTHORITY_KEYS)}")
        auth = {}
    for k in ("pos_sale_details", "desk_fields"):
        if not (isinstance(auth.get(k, {}), dict) and set(auth.get(k, {})) <= set(AUTHORITY_COLUMNS)):
            bad.append(f"authority.{k}: maps {', '.join(AUTHORITY_COLUMNS)} to their sources")
    dl = auth.get("dispenser_licence")
    if dl is not None and (not _lookup_ok(dl) or dl.get("match") != "user"):
        bad.append("authority.dispenser_licence: a record named by the line's dispensing user: its type, match user and field")
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
        if set(b) - set(BOOK_KEYS):
            bad.append(f"{w}: {', '.join(sorted(set(b) - set(BOOK_KEYS)))} is not a key of a book")
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
            if isinstance(c, dict) and set(c) - set(CONDITION_KEYS):
                bad.append(f"{w}.conditions[{i}]: a condition is a field, an operator and a value")
            if op not in OPERATORS:
                bad.append(f"{w}.conditions[{i}]: the operator is one of {', '.join(OPERATORS)}")
            if not isinstance(c, dict) or c.get("field") not in known:
                bad.append(f"{w}.conditions[{i}]: a condition reads a column of the line")
            elif c["field"] in looked_up:
                bad.append(f"{w}.conditions[{i}]: {c['field']} is read from a record: the door does not route on it")
            elif c["field"] in dated and op not in SET_OPS:
                bad.append(f"{w}.conditions[{i}]: {c['field']} is a date or a time: a condition on it is is set or "
                           "is not set")
            elif isinstance(c.get("value"), bool):
                bad.append(f"{w}.conditions[{i}]: a tick-box column compares 0 or 1, never true or false")
            elif op in NUMBER_OPS and not isinstance(c.get("value"), (int, float)):
                bad.append(f"{w}.conditions[{i}]: {op} compares a number (a date is not one)")
            elif op in ("=", "!=") and not isinstance(c.get("value"), (str, int, float)):
                bad.append(f"{w}.conditions[{i}]: = and != need a value")
        if b.get("numbering") not in ("book_store", "book_store_item"):
            bad.append(f"{w}.numbering: book_store or book_store_item")
        if b.get("balance") not in (0, 1):
            bad.append(f"{w}.balance: 0 or 1")
        if b.get("purchaser_slip", 0) not in (0, 1):
            bad.append(f"{w}.purchaser_slip: 0 or 1 (1: a slip the purchaser signs, printed from the sale)")
        for n in [print_name(ds, b)] + slip_names(ds, b):
            if len(n) > NAME_MAX:
                bad.append(f"{w}: its print's name, '{n}', is over {NAME_MAX} characters: shorten the data set's or "
                           "the book's id")
        if b.get("correction") not in CORRECTIONS:
            bad.append(f"{w}.correction: one of {', '.join(CORRECTIONS)}")
        if b.get("medium") not in MEDIA:
            bad.append(f"{w}.medium: one of {', '.join(MEDIA)}")
        if not (isinstance(b.get("retention_years"), int) and 1 <= b["retention_years"] <= 30):
            bad.append(f"{w}.retention_years: 1 to 30")
        if "loss_count_hours" in b and not (_whole(b["loss_count_hours"]) and b["loss_count_hours"] > 0
                                            and b.get("balance") == 1):
            bad.append(f"{w}.loss_count_hours: a whole number above 0, on a book that keeps a balance (a count needs one)")
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
                if v not in known and not (v in PRINTED_ONLY and b.get("balance") == 1):
                    bad.append(f"{w}.columns[{i}]: '{v}' is not a column of the line or a declared detail"
                               + (" (balance_before: a book that keeps a balance)" if v in PRINTED_ONLY else ""))
            if c.get("when") not in (None, "In", "Out"):
                bad.append(f"{w}.columns[{i}].when: In or Out")
            if set(c) - set(COLUMN_KEYS):
                bad.append(f"{w}.columns[{i}]: {', '.join(sorted(set(c) - set(COLUMN_KEYS)))} is not a key of a column")
            if "group" in c and not _text(c["group"]):
                bad.append(f"{w}.columns[{i}].group: plain text (the band printed over the column)")
        sourced = {f"detail:{k}" for k, d in details.items() if isinstance(d, dict)
                   and (d.get("own") or {"pos_sale_detail", "desk_field", "record"} & set(d))}
        for r in b.get("required", []):
            if r not in known:
                bad.append(f"{w}.required: '{r}' is not a column of the line or a declared detail")
            elif r.startswith("detail:") and r not in sourced:
                bad.append(f"{w}.required: {r} has no source to fill it")
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


def print_name(ds, b):
    """A book's print format: named by the data set's and the book's ids, never by its title, so a corrected book
    (a new id, the old book kept switched off with its lines) never takes the old book's print."""
    return f"{PREFIX} {ds.get('id')} {b.get('id')}"


def slip_names(ds, b):
    """A book's purchaser's slip: one print format on the till's sale, one on the Desk's (a print format has one type)."""
    if not b.get("purchaser_slip"):
        return []
    return [f"{print_name(ds, b)} slip {where}" for where in ("till", "Desk")]


def _market(ds):
    return str(ds.get("title", "")).split(":")[0]


def reminder_name(ds, b):
    """The return's reminder: the ids, not the titles (two data sets may share a title), with a space between, which
    an id never holds, so no two books share one; the shop's name rule takes no dot."""
    return f"{PREFIX} Return due {ds.get('id')} {b.get('id')}"


def book_data(ds, b):
    """The book as its layout reads it: what the door's print (ivn_register_print) does not carry, every detail named by
    its slot. The rows, the pages, the official book's sheets, the balance before a line and the period's close come
    from the door."""
    cols = [{**c, "value": [_col(ds, v) for v in c["value"]]} for c in b["columns"]]
    out = {"ref": book_ref(ds, b), "title": b["title"], "form": b.get("form", ""), "cite": b["cite"],
           "data_set_title": ds["title"], "certified": ds["certified"], "notice": ds["notice"], "columns": cols,
           "groups": any(c.get("group") for c in cols), "correction_words": CORRECTIONS[b["correction"]],
           # the door writes "Entered late." into a late line's remarks: a book printing remarks says it already
           "prints_remarks": any("remarks" in c["value"] for c in cols),
           "medium_note": b.get("medium_note", "")}
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


def _sources(key, d):
    """Where the door reads a detail. None of the three: the column prints empty, for the shop to write in."""
    if d.get("own"):
        return {**({"pos_sale_detail": sale_detail(key)} if d.get("till", 1) else {}), "desk_field": FPREFIX + key}
    return {k: d[k] for k in ("pos_sale_detail", "desk_field", "record") if k in d}


def _detail(key, d):
    """A detail slot as the door takes it: its label, its source, and its type and person where they are the door's."""
    out = {"label": d["label"], **_sources(key, d)}
    if d["type"] in ("Date", "Age"):  # the door routes a Date as a date and works an Age out; Data is its default
        out["type"] = d["type"]
    if "person" in d:
        out["person"] = d["person"]
    return out


def declaration(ds, b):
    """One book as the door's manifest kind register_books takes it. Every book installs switched off: the shop switches
    its own market's on, and an update never switches a book (the door's rule), so no build ever flips one."""
    d = {"book": book_ref(ds, b), "title": b["title"], "data_set": ds["id"], "cite": b["cite"],
         "certified": ds["certified"], "medium": b["medium"], "numbering": b["numbering"], "balance": b["balance"],
         "correction": b["correction"], "retention_years": b["retention_years"], "count_role": ROLE,
         "conditions": [{**c, "field": _col(ds, c["field"])} for c in b.get("conditions", [])],
         "required": [_col(ds, r) for r in b.get("required", [])],
         "columns": [{**{k: c[k] for k in ("label", "group", "when", "mark") if k in c},
                      "value": [_col(ds, v) for v in c["value"]]} for c in b["columns"]],
         "details": {slots(ds)[k]: _detail(k, x) for k, x in (ds.get("details") or {}).items()},
         "authority": ds.get("authority", {}), "columns_from": ds.get("columns_from", {}), "enabled": 0}
    if b.get("classes"):
        d["items"] = {"classes": b["classes"]}
        d["class_source"] = b["class_source"]
    else:
        d["items"] = {"item_groups": b["item_groups"]}
    for k in ("period_months", "return_due_days", "loss_count_hours"):
        if k in b:
            d[k] = b[k]
    return d


def print_format(ds, b):
    pf = {"name": print_name(ds, b), "doc_type": PERIOD, "print_format_type": "Jinja",
          "html": book_html(ds, b)}
    if ds.get("print_language"):
        pf["default_print_language"] = ds["print_language"]
    return pf


def slips(ds, b):
    """The purchaser's slip of a book that asks for one (purchaser_slip: 1): the sale's entries in that book, read through
    ivn_rows, with a line for the purchaser's signature. The till prints no slip of its own: print it from the sale in
    Desk, on the till's sale (POS Invoice) or the Desk's (Sales Invoice)."""
    data = {"ref": book_ref(ds, b), "title": b["title"], "form": b.get("form", ""), "cite": b["cite"],
            "certified": ds["certified"]}
    html = "{%- set book = " + _literal(data) + " -%}\n" + _read("layouts/purchaser_slip.html")
    return [{"name": n, "doc_type": dt, "print_format_type": "Jinja", "html": html}
            for n, dt in zip(slip_names(ds, b), ("POS Invoice", "Sales Invoice"))]


def reminder(ds, b):
    return {"name": reminder_name(ds, b), "document_type": PERIOD, "event": "Days Before", "date_changed": "return_due",
            "days_in_advance": 7, "channel": "System Notification",
            "subject": "The {{ doc.book }} return for {{ doc.register_store }} is due on {{ doc.return_due }}",
            "recipients": [{"receiver_by_role": ROLE}]}


# The register's lists and open tasks, on the door's record types: the book's count role reads and reports on each
# (the door gives it those rights when a book naming it is switched on), so these need no rights of their own.
LISTS = [
    {"name": f"{PREFIX} Register entries", "ref_doctype": LINE, "report_type": "Report Builder",
     "columns": ["number", "book", "register_store", "entry_date", "movement_date", "item_name", "kind", "direction", "qty",
                 "uom", "balance", "voucher_type", "voucher_no", "booked_late", "incomplete", "below_zero"],
     "order_by": "entry_date desc", "roles": [ROLE]},
    {"name": f"{PREFIX} Losses and disposals", "ref_doctype": LINE, "report_type": "Report Builder",
     "columns": ["number", "book", "register_store", "entry_date", "item_name", "kind", "qty", "uom", "balance", "voucher_no",
                 "remarks"],
     "filters": [["kind", "in", ["Loss", "Disposal"]]], "order_by": "entry_date desc", "roles": [ROLE]},
    {"name": f"{PREFIX} Counts due after a loss", "ref_doctype": STATE, "report_type": "Report Builder",
     "columns": ["book", "register_store", "item", "item_name", "balance", "last_loss_at", "count_due_by"],
     "filters": [["count_due_by", "is", "set"]], "order_by": "count_due_by asc", "roles": [ROLE]},
    {"name": f"{PREFIX} Periods open", "ref_doctype": PERIOD, "report_type": "Report Builder",
     "columns": ["book", "register_store", "from_date", "to_date", "return_due", "status"],
     "filters": [["status", "=", "Open"]], "order_by": "return_due asc", "roles": [ROLE]},
]
CARDS = [
    {"name": f"{PREFIX} Entries entered late", "document_type": LINE, "filters": [["booked_late", "=", 1]], "color": "#b26b00"},
    {"name": f"{PREFIX} Entries incomplete", "document_type": LINE, "filters": [["incomplete", "=", 1]], "color": "#8a1c1c"},
    {"name": f"{PREFIX} Entries below zero", "document_type": LINE, "filters": [["below_zero", "=", 1]], "color": "#8a1c1c"},
    {"name": f"{PREFIX} Counts due after a loss", "document_type": STATE, "filters": [["count_due_by", "is", "set"]],
     "color": "#8a1c1c"},
    {"name": f"{PREFIX} Periods open", "document_type": PERIOD,
     "filters": [["status", "=", "Open"]], "color": "#b26b00"},
]
CHART = {"name": f"{PREFIX} Register entries a day", "document_type": LINE, "chart_type": "Count", "based_on": "entry_date",
         "timespan": "Last Month", "time_interval": "Daily", "type": "Bar", "roles": [ROLE]}
DASHBOARD = {"name": f"{PREFIX} Register", "charts": [CHART["name"]], "cards": [c["name"] for c in CARDS]}

WORKSPACE_TEXT = (
    f"Open tasks: search Desk for the dashboard {PREFIX} Register, whose cards count the entries entered late, incomplete "
    f"or below zero, the counts due after a loss and the periods not yet signed off (a return is sent for each); each "
    f"card opens its list. The saved lists: {PREFIX} Register entries, {PREFIX} Losses and disposals, {PREFIX} Counts "
    f"due after a loss and {PREFIX} Periods open (search Desk for each; filter a list by book, store and dates). The "
    "books are on Retail Register Book: switch on your market's books, map their register stores before the first sale, "
    "and count each item's opening balance before its first receipt or sale. At each sale of a book that asks for it, "
    "print the purchaser's slip from the sale for the purchaser to sign. Each day at close, print the day's pages of "
    "each book (Print book on the book, today's dates) and keep them at the store, for an outage. Once a book's "
    "retention has passed, Erase persons' details on the book erases a person's details from the entries then due "
    "and says what still waits; it has no preview.")


def build_manifest(sets=None, books=None):
    """The app's manifest: the Desk fields and sale details of every data set (a shop's update never drops a field an
    earlier version installed); the books, prints and reminders of `books` (every data set's, when none are named),
    each installed switched off."""
    sets = datasets() if sets is None else sets
    _all_checked(sets)
    books = sets if books is None else books
    _all_checked(books)
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
    pairs = [(ds, b) for ds in books for b in ds["books"]]
    return {
        "manifest_version": 2, "app": APP, "prefix": PREFIX, "title": "Regulated stock register", "version": VERSION,
        "publisher": "Partner Programme sample",
        "description": "A legal register for regulated stock (controlled medicine, liquor, tobacco, duty-free), its books "
                       "declared per market as data and kept by the POS app's register door: one line for each sale or "
                       "receipt of a regulated item, written in the same save, numbered without a gap, never edited, with "
                       "a running balance where the law keeps one. It installs each market's books, their prints, a "
                       "reminder before each return, the register's lists and open-tasks cards, the register's own columns "
                       "on the Desk sale and delivery and the till's sale details, and the approver role. It reads the "
                       "pharmacy counter app's drug schedules, prescriptions and patients: install that app first.",
        "custom_fields": fields,
        "sale_attributes": [{"name": sale_detail(k)} for k, d in own.items() if d.get("till", 1)],
        "register_books": [declaration(ds, b) for ds, b in pairs],
        "print_formats": [print_format(ds, b) for ds, b in pairs] + [s for ds, b in pairs for s in slips(ds, b)],
        "notifications": [reminder(ds, b) for ds, b in pairs if b.get("period_months")],
        "reports": [{
            "name": f"{PREFIX} Stock counts to watch", "ref_doctype": "Stock Reconciliation", "report_type": "Report Builder",
            "columns": ["name", "posting_date", "purpose", "set_warehouse", "docstatus"],
            "filters": [["docstatus", "!=", 2]], "order_by": "posting_date desc", "roles": [ROLE],
        }] + LISTS,
        "number_cards": CARDS,
        "dashboard_charts": [CHART],
        "dashboards": [DASHBOARD],
        "workspaces": [{
            "name": f"{PREFIX} Regulated stock register",
            "blocks": [
                {"type": "header", "data": {"text": "<span class=\"h4\">Regulated stock register</span>", "col": 12}},
                {"type": "paragraph", "data": {"text": WORKSPACE_TEXT, "col": 12}},
            ] + [{"type": "shortcut", "data": {"shortcut_name": s["label"], "col": 3}} for s in SHORTCUTS],
            "shortcuts": SHORTCUTS,
        }],
    }


# Desk makes a workspace before the manifest's own reports, so a shortcut links a record type's list, never a report.
SHORTCUTS = [
    {"type": "DocType", "link_to": "Retail Register Book", "label": "Register books"},
    {"type": "DocType", "link_to": LINE, "label": "Register entries", "doc_view": "Report Builder"},
    {"type": "DocType", "link_to": "Retail Register Count", "label": "Register counts"},
    {"type": "DocType", "link_to": PERIOD, "label": "Register periods"},
    {"type": "DocType", "link_to": "Stock Reconciliation", "label": "Stock counts"},
    {"type": "DocType", "link_to": "Sales Invoice", "label": "Sales invoices"},
    {"type": "DocType", "link_to": "Delivery Note", "label": "Delivery notes"},
    {"type": "DocType", "link_to": "Purchase Receipt", "label": "Purchase receipts"},
]


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
    """This sample's catalogue (every data set's books), or a shop's own copy (only its data sets' books). Either way the
    manifest carries every data set's fields, and every book installs switched off."""
    sets = datasets()
    return build_manifest(sets, None if ids is None else chosen(ids, sets))


def refusals(m):
    """The shop's own checker on the manifest, where the kit's copy is beside this sample (tools/manifest); [] elsewhere."""
    kit = os.path.join(HERE, "..", "..", "tools", "manifest")
    if not os.path.exists(os.path.join(kit, "validate.py")):
        return []
    sys.path.insert(0, kit)
    import validate  # noqa: E402  (the kit's copy of the shop's checker)
    return validate.validate(m)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and not (len(argv) == 4 and argv[0] == "--sets" and argv[2] == "--out"):
        raise SystemExit("usage: build.py [--sets id,id --out folder]")
    out = os.path.abspath(argv[3]) if argv else HERE
    if argv and out == HERE:
        raise SystemExit("--out: a shop's copy goes in a folder of its own, never over this sample's catalogue")
    m = build_files(argv[1].split(",") if argv else None)
    refused = refusals(m)
    if refused:
        raise SystemExit("the shop's checker refuses this manifest: " + "; ".join(f"{r['where']}: {r['reason']}" for r in refused))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"manifest.json: {len(m['custom_fields'])} fields, {len(m['sale_attributes'])} sale details, "
          f"{len(m['register_books'])} books, {len(m['print_formats'])} print formats")


if __name__ == "__main__":
    sys.exit(main())
