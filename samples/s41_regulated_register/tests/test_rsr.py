"""The Regulated stock register's laptop tests, before the register door exists: the manifest is the build of the data
sets and passes the kit's checks; a data set the format refuses is refused, case by case; Kenya's routing sends each
fixture line to the right books; each book renders from fixture lines shaped as the door's line (the register books page, §5), read
through a stand-in ivn_rows; and a second data set, a one-book liquor register, loads, adds its own column and renders
with no code change. The rendering tests need jinja2 (the kit's CI installs it; RSR_REQUIRE_JINJA makes them fail, not
skip, without it).

    python3 -m unittest discover -s samples/s41_regulated_register/tests -p 'test_*.py'
"""
import copy
import json
import os
import re
import sys
import tokenize
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent
sys.path.insert(0, str(SAMPLE))
sys.path.insert(0, str(SAMPLE.parents[1] / "tools" / "manifest"))
import build  # noqa: E402
import routing  # noqa: E402
import site_rules  # noqa: E402
import validate  # noqa: E402

try:
    import jinja2
    from jinja2 import DebugUndefined
    from jinja2.sandbox import SandboxedEnvironment
except ImportError:
    if os.environ.get("RSR_REQUIRE_JINJA") or os.environ.get("S29_REQUIRE_JINJA"):
        raise
    jinja2 = None

NEED_JINJA = unittest.skipUnless(jinja2, "jinja2 is not installed: the rendering tests did not run")
KE = json.loads((SAMPLE / "datasets" / "ke_pharmacy.json").read_text(encoding="utf-8"))
LIQUOR = json.loads((HERE / "fixtures" / "liquor_one_book.json").read_text(encoding="utf-8"))


def line(n, **kw):
    """A line as the door writes it (the register books page, §5)."""
    base = dict(number=n, book="ke_pharmacy.poisons_book", register_store="Pharmacy Dispensary - ICG", item="PHD-TRAM-50",
                item_name="Tramadol 50 mg capsules", item_class="KE Part I Poison", direction="Out", kind="Sale", qty=10,
                uom="Nos", balance=None, movement_date="2026-10-20", entry_date="2026-10-20",
                entered_at="2026-10-20 10:00:00", counterparty="A. Buyer", counterparty_address="1 Moi Avenue, Nairobi",
                reference_no=None, authority_no=None, authority_issuer=None, dispenser_name="P. Pharmacist",
                booked_late=0, correction_of=None, correction_of_number=None, correction_note=None, signed_by_name=None, remarks=None,
                detail_1="Farmer", detail_2="Pest control", detail_3=None, detail_4=None, detail_5=None, detail_6=None)
    base.update(kw)
    return base


def _q(v):
    return ("%.3f" % float(v)).rstrip("0").rstrip(".")


MEDIUM_WORDS = {  # the door's words for what a book is kept on
    "system_of_record": "This system is the register: a print of it is a copy.",
    "official_book": "Print each entry into the regulator's own book at the page and line shown.",
    "regulator_system": "A working register: the regulator's own system is the record of law, and this print is the "
                        "shop's copy.",
}


def _shown(ln, decl):
    ln = dict(ln)
    if decl["balance"] and ln.get("balance") is not None:
        ln["balance_before"] = ln["balance"] - (ln["qty"] if ln["direction"] == "In" else -ln["qty"])
        ln["balance_before_text"] = _q(ln["balance_before"])
    ln["erased"] = bool(ln.get("erased"))
    # the door's plain text of the stored address (the core stores it with <br> line breaks), one line each
    ln["address_lines"] = [x for x in re.split(r"<br\s*/?>|\n", ln.get("counterparty_address") or "") if x.strip()]
    ln["qty_text"] = _q(ln.get("qty") or 0)
    ln["balance_text"] = _q(ln["balance"]) if ln.get("balance") is not None else ""
    return ln


def _page(decl, lines, item_name, brought):
    """One page's rows as the door makes them: each line a row or a note by its kind and the book's correction mode."""
    fixes = {ln["correction_of_number"]: ln for ln in lines if ln.get("correction_of_number")}
    numbers = {ln["number"] for ln in lines}
    mode, rows = decl["correction"], []
    signed = lambda n: f"Signed {n}." if n else ""  # noqa: E731
    row = lambda ln, struck=False: {"kind": "row", "line": ln, "struck": struck, "text": ""}  # noqa: E731
    note = lambda ln, text: {"kind": "note", "line": ln, "struck": False, "text": text}  # noqa: E731
    for ln in lines:
        ln, n = _shown(ln, decl), ln["number"]
        if ln["kind"] in ("Opening", "Count"):
            text = (f"Entry {n}: opening balance {_q(ln['qty'])} {ln['uom'] or ''}." if ln["kind"] == "Opening" else
                    f"Entry {n}: count, {'+' if ln['direction'] == 'In' else '-'}{_q(ln['qty'])} {ln['uom'] or ''}.")
            if ln.get("balance") is not None and decl["balance"]:
                text += f" Balance {_q(ln['balance'])}."
            rows.append(note(ln, f"{text} {signed(ln.get('signed_by_name'))} {ln.get('remarks') or ''}".strip()))
        elif ln.get("correction_of_number"):
            of, cn = ln["correction_of_number"], ln.get("correction_note") or ""
            if mode == "reversing_line":
                rows += [row(ln), note(ln, f"Entry {n} reverses entry {of}." + (f" {cn}" if cn else "")
                                       + f" {signed(ln.get('signed_by_name'))}")]
            elif mode == "dated_note":
                rows.append(note(ln, f"Note dated {ln['entry_date']} to entry {of}: {cn or ln.get('remarks') or ''} "
                                     f"{ln.get('signed_by_name') or ''} (entry {n})."))
            elif of not in numbers:
                verb = "strikes through" if mode == "signed_strike_through" else "amends"
                rows.append(note(ln, f"Entry {n} {verb} entry {of}, not printed here." + (f" {cn}" if cn else "")
                                     + f" {signed(ln.get('signed_by_name'))}"))
        else:
            fix = fixes.get(n)
            rows.append(row(ln, bool(fix) and mode == "signed_strike_through"))
            if fix and mode in ("signed_strike_through", "signed_amendment"):
                by, author = fix.get("signed_by_name") or "", ln.get("dispenser_name") or ""
                text = (f"Struck through by entry {fix['number']}." if mode == "signed_strike_through"
                        else f"Amended by entry {fix['number']}.")
                if fix.get("correction_note"):
                    text += " " + fix["correction_note"]
                text += " " + signed(by)
                if author and author != by:
                    text += f" The entry's author: {author}."
                rows.append(note(fix, text))
    return {"item_name": item_name, "brought": brought, "brought_text": _q(brought) if brought is not None else "",
            "rows": rows}


def official_place(starts, number):
    """The door's official_place: where entry `number` lands in the authority's book, (volume, page, line)."""
    start = None
    for st in starts:
        if number >= st["from"]:
            start = st
    if not start:
        return None
    i = start["line"] - 1 + number - start["from"]
    return start["volume"], start["page"] + i // start["lines"], i % start["lines"] + 1


def _sheets(page, starts):
    """The door's _sheets: each entry one row (its own note rides in it), a sheet per page of the authority's book, blank
    rows for the lines before; entries before the shop's first start print apart, at no place."""
    rows = []
    for r in page["rows"]:
        last = rows[-1] if rows else None
        if last and r["kind"] == "note" and last["kind"] == "row" and last["line"]["number"] == r["line"]["number"]:
            last["note"] = f"{last.get('note', '')} {r['text']}".strip()
            continue
        rows.append(dict(r))
    rows.sort(key=lambda r: (str(r["line"].get("sequence") or ""), r["line"]["number"]))
    head = {k: v for k, v in page.items() if k != "rows"}
    sheets, key = [], object()
    for r in rows:
        seq = str(r["line"].get("sequence") or "")
        place = official_place(starts.get(seq, []), r["line"]["number"])
        if not sheets or (seq, place[:2] if place else None) != key:
            key = (seq, place[:2] if place else None)
            sheets.append({**head, "place": "Volume {0}, page {1}".format(*key[1]) if key[1] else None, "rows": []})
            head["brought"], head["brought_text"] = None, ""
        sheet = sheets[-1]
        if place:
            at = sheet["rows"][-1]["place_line"] if sheet["rows"] else 0
            sheet["rows"] += [{"kind": "blank", "line": {}, "struck": False, "text": "", "place_line": k}
                              for k in range(at + 1, place[2])]
            r["place_line"] = place[2]
        sheet["rows"].append(r)
    return sheets or [{**head, "place": None, "rows": []}]


def door_print(decl, doc, lines, states=(), starts=None, **extra):
    """A stand-in for the register door's ivn_register_print(doc), the dict every book's print renders: a COPY of its
    shape and row rules (repo ivendnext/iVendNext_PWA, business_logic/register_print.py ivn_register_print, _page and
    _shown at development 60147699c), with the door's words in English and no official book's sheets, which the door
    works out from the shop's own page starts (`starts`, {sequence: [start]}, as the door reads them); the period's close
    and the drugs' balances brought forward come in `extra`. A defect here is a defect there: report it with the Kit
    defect form."""
    calls.append(doc["book"])
    where = [ln for ln in lines if ln["book"] == doc["book"] and ln["register_store"] == doc["register_store"]
             and doc["from_date"] <= ln["entry_date"] <= doc["to_date"]]
    by_number = lambda ln: ln["number"]  # noqa: E731
    out = {"book": {"title": decl["title"], "certified": decl["certified"], "balance": decl["balance"],
                    "correction": decl["correction"], "retention_years": decl["retention_years"],
                    "medium": decl["medium"], "medium_words": MEDIUM_WORDS.get(decl["medium"], "")},
           "pages": [], "count": 0, "cut": False, "items_cut": False, "brought_cut": False, "from": doc["from_date"],
           "to": doc["to_date"], "signed": True, "total": len(where), "persons_hidden": False}
    official = decl["medium"] == "official_book"
    one_run = official and decl["numbering"] == "book_store"  # an official book numbered per store: one run
    if (decl["balance"] or (official and decl["numbering"] == "book_store_item")) and not one_run:
        for st in sorted(states, key=lambda s: s["item"]):
            ls = sorted((ln for ln in where if ln["item"] == st["item"]), key=by_number)
            before = sorted((ln for ln in lines if ln["book"] == doc["book"] and ln["item"] == st["item"]
                             and ln["register_store"] == doc["register_store"] and ln["entry_date"] < doc["from_date"]),
                            key=by_number)
            brought = before[-1]["balance"] if before else None
            if ls or brought:
                out["pages"].append(_page(decl, ls, st["item_name"], brought))
            out["count"] += len(ls)
    else:
        out["pages"].append(_page(decl, sorted(where, key=by_number), None, None))
        out["count"] = len(where)
    if not out["pages"]:
        out["pages"].append(_page(decl, [], None, None))
    if official:
        out["pages"] = [sheet for page in out["pages"] for sheet in _sheets(page, starts or {})]
    if one_run and decl["balance"] and extra.get("brought_items"):
        out["pages"][0]["brought_items"] = extra.pop("brought_items")
    return {**out, **extra}


calls = []


def period(book, **kw):
    return {"book": book, "register_store": "Pharmacy Dispensary - ICG", "from_date": "2026-10-01",
            "to_date": "2026-10-31", "establishment": "Demo Chemists Ltd", "establishment_address": "1 Moi Avenue, Nairobi",
            **kw}


def shop_env():
    """The shop renders a print in a sandbox with autoescape off (the template escapes) and DebugUndefined: a key the
    reader may not read prints as the framework's own debug text unless the template guards it."""
    return SandboxedEnvironment(autoescape=False, undefined=DebugUndefined)


def render(ds, book_id, doc, lines, states=(), rtl=False, html=None, **extra):
    """The book's print in K3's layout, over the door's print (door_print), as the shop renders it: autoescape off (the
    template escapes), the translator the identity, the direction asked."""
    b = next(x for x in ds["books"] if x["id"] == book_id)
    decl = build.declaration(ds, b)
    calls.clear()
    env = shop_env()
    out = env.from_string(html or build.book_html(ds, b)).render(
        doc=doc, ivn_register_print=lambda d: door_print(decl, d, lines, states, **extra),
        _=lambda s, **k: s, is_rtl=lambda: rtl)
    return out, list(calls)


def cells(html):
    """The rows of the printed table, each a list of its cells' text."""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if tds:
            out.append([re.sub(r"<[^>]+>", "", t).strip() for t in tds])
    return out


def declared(ref):
    """One book's declaration, by its data set and id (the data sets build in file-name order)."""
    return next(b for b in build.build_manifest()["register_books"] if b["book"] == ref)


class Manifest(unittest.TestCase):
    def test_the_manifest_is_the_build_of_the_data_sets(self):
        m = json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m, build.build_manifest())
        self.assertEqual(m["version"], "0.2.0")
        self.assertFalse((SAMPLE / "door_declaration.json").exists())  # 0.2.0 installs the books: one file
        # the catalogue: every data set's books, switched off (the shop switches its own market's on)
        self.assertEqual({b["data_set"] for b in m["register_books"]}, {ds["id"] for ds in build.datasets()})
        self.assertEqual({b["enabled"] for b in m["register_books"]}, {0})

    def test_the_manifest_passes_the_checker_and_the_shops_two_install_refusals(self):
        m = build.build_manifest()
        self.assertEqual(validate.validate(m), [])
        self.assertEqual(site_rules.refusals(m), [])

    def test_it_installs_the_books_their_prints_reminders_lists_and_open_tasks(self):
        m = build.build_manifest()
        self.assertEqual(sorted(k for k in m if isinstance(m[k], list)),
                         ["custom_fields", "dashboard_charts", "dashboards", "notifications", "number_cards",
                          "print_formats", "register_books", "reports", "sale_attributes", "workspaces"])
        self.assertEqual({f["dt"] for f in m["custom_fields"]}, {"Sales Invoice", "Delivery Note"})
        self.assertEqual([r["name"] for r in m["reports"]],
                         ["PP RSR Stock counts to watch", "PP RSR Register entries", "PP RSR Losses and disposals",
                          "PP RSR Counts due after a loss", "PP RSR Periods open"])
        self.assertEqual({c["document_type"] for c in m["number_cards"]},
                         {"Retail Register Line", "Retail Register State", "Retail Register Period"})
        self.assertEqual(m["dashboards"][0]["cards"], [c["name"] for c in m["number_cards"]])
        self.assertEqual(m["reports"][2]["filters"], [["kind", "in", ["Loss", "Disposal"]]])
        self.assertEqual(m["reports"][3]["filters"], [["count_due_by", "is", "set"]])  # the count a loss makes due

    def test_the_workspace_says_what_no_manifest_kind_can_carry(self):
        text = build.build_manifest()["workspaces"][0]["blocks"][1]["data"]["text"]
        self.assertIn("Each day at close, print the day's pages of each book", text)  # the daily print (no reminder kind)
        self.assertIn("Erase persons' details", text)  # entries due for erasure (a date no filter can carry)
        self.assertIn("PP RSR Register entries", text)  # the lists, which a workspace cannot link

    def test_the_approver_role_is_made_by_the_report_and_named_with_the_prefix(self):
        # the shop's install makes an app's own roles from a report's roles, never from a workspace
        self.assertEqual(build.build_manifest()["reports"][0]["roles"], ["PP RSR Register Approver"])
        self.assertTrue(build.ROLE.startswith(build.PREFIX + " "))

    def test_every_own_column_is_a_desk_field_on_both_documents_and_a_sale_detail(self):
        m = build.build_manifest()
        own = build.own_details(build.datasets())  # every data set's own columns, once each, in data set order
        self.assertLessEqual({k for k, d in KE["details"].items() if d.get("own")}, set(own))
        for dt in ("Sales Invoice", "Delivery Note"):
            names = [f["fieldname"] for f in m["custom_fields"] if f["dt"] == dt]
            self.assertEqual(names, ["pp_rsr_section"] + [f"pp_rsr_{k}" for k in own])
        self.assertEqual([a["name"] for a in m["sale_attributes"]],
                         [build.sale_detail(k) for k, d in own.items() if d.get("till", 1)])
        self.assertLessEqual({"PP RSR Occupation", "PP RSR Purpose", "PP RSR Prescriber Address"},
                             {a["name"] for a in m["sale_attributes"]})
        self.assertNotIn("PP RSR Certificate Date", [a["name"] for a in m["sale_attributes"]])  # till: 0 keeps it off the till
        self.assertFalse(any(f.get("reqd") for f in m["custom_fields"]))  # Desk's refusal is the door's (VR-24)

    def test_no_report_or_workspace_names_a_field_this_manifest_adds(self):
        m = build.build_manifest()
        self.assertFalse([c for r in m["reports"] for c in r["columns"] if c.startswith("pp_rsr_")])
        self.assertFalse([s for w in m["workspaces"] for s in w["shortcuts"] if s["type"] != "DocType"])

    def test_the_book_prints_pass_the_checker_with_no_warning(self):
        d = build.build_manifest()
        m = {"manifest_version": 2, "app": "pp_rsr", "prefix": "PP RSR", "title": "x", "version": "0.2.0",
             "publisher": "x", "description": "x", "print_formats": d["print_formats"]}
        self.assertEqual((validate.validate(m), validate.warnings(m)), ([], []))
        names = [p["name"] for p in d["print_formats"]]
        slips = [n for n in names if " slip " in n]
        self.assertEqual(slips, ["PP RSR ke_pharmacy poisons_book slip till", "PP RSR ke_pharmacy poisons_book slip Desk"])
        self.assertEqual(len(names) - len(slips), sum(len(ds["books"]) for ds in build.datasets()))  # a print per book
        # named by ids, never titles: a corrected book (a new id, the old kept with its entries) never takes the old one's
        self.assertLessEqual({"PP RSR ke_pharmacy poisons_book", "PP RSR ke_pharmacy prescription_book",
                              "PP RSR ke_pharmacy npp_ledger", "PP RSR jo_pharmacy form_9",
                              "PP RSR ng_pharmacy part_b_morphine"}, set(names))
        self.assertTrue(all(p["doc_type"] == "Retail Register Period" for p in d["print_formats"] if " slip " not in p["name"]))
        self.assertEqual([p["doc_type"] for p in d["print_formats"] if " slip " in p["name"]], ["POS Invoice", "Sales Invoice"])
        arabic = {p["name"] for p in d["print_formats"] if p.get("default_print_language") == "ar"}
        self.assertEqual({n.split()[2] for n in arabic}, {"jo_pharmacy", "sa_pharmacy", "eg_pharmacy",
                                                          "ae_abu_dhabi_pharmacy"})  # their print language

    def test_every_reminder_passes_the_shops_checker_and_none_shares_a_name(self):
        d = build.build_manifest()
        m = {"manifest_version": 2, "app": "pp_rsr", "prefix": "PP RSR", "title": "x", "version": "0.2.0",
             "publisher": "x", "description": "x", "notifications": d["notifications"]}
        self.assertEqual(validate.validate(m), [])
        names = [n["name"] for n in d["notifications"]]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(len(names), sum(1 for ds in build.datasets() for b in ds["books"] if b.get("period_months")))
        self.assertTrue(all(n["date_changed"] == "return_due" and n["document_type"] == "Retail Register Period"
                            for n in d["notifications"]))

    def test_the_old_reminder_name_is_one_the_shop_refuses(self):
        # canary: the 0.1.2 build named it by book_ref, whose dot the shop's name rule refuses
        m = {"manifest_version": 2, "app": "pp_rsr", "prefix": "PP RSR", "title": "x", "version": "0.2.0",
             "publisher": "x", "description": "x",
             "notifications": [{**build.build_manifest()["notifications"][0], "name": "PP RSR Return due a.b"}]}
        self.assertTrue(validate.validate(m))

    def test_a_shop_builds_its_own_markets_and_keeps_every_field(self):
        m = build.build_files(["ke_pharmacy"])
        whole = build.build_manifest()
        for k in ("custom_fields", "sale_attributes"):  # the fields never narrow: an update may not drop one
            self.assertEqual(m[k], whole[k])
        self.assertEqual({b["data_set"] for b in m["register_books"]}, {"ke_pharmacy"})
        self.assertEqual({b["enabled"] for b in m["register_books"]}, {0})  # switched off too: no build flips a book
        self.assertEqual((len(m["register_books"]), len(m["print_formats"])), (3, 5))  # three books, the slip twice
        self.assertEqual(m["notifications"], [])
        self.assertEqual(validate.validate(m), [])
        two = build.build_files(["sa_pharmacy", "ae_abu_dhabi_pharmacy"])
        self.assertEqual([b["book"] for b in two["register_books"]],
                         ["sa_pharmacy.drug_register", "ae_abu_dhabi_pharmacy.ph_20", "ae_abu_dhabi_pharmacy.ph_17"])
        self.assertEqual(len(two["notifications"]), 3)
        for bad in (["xx_pharmacy"], [], ["ke_pharmacy", "nope"], ["ke_pharmacy", "ke_pharmacy"]):
            with self.assertRaises(SystemExit):
                build.build_files(bad)
        for argv in (["--set", "ke_pharmacy"], ["--sets", "ke_pharmacy"], ["--sets", "ke_pharmacy", "--out", str(SAMPLE)]):
            with self.assertRaises(SystemExit):  # a shop's copy never lands on the sample's catalogue
                build.main(argv)

    def test_a_shops_copy_is_written_to_its_own_folder(self):
        import tempfile
        before = (SAMPLE / "manifest.json").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            build.main(["--sets", "eg_pharmacy", "--out", tmp])
            m = json.loads(Path(tmp, "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([b["book"] for b in m["register_books"]], ["eg_pharmacy.received_dispensed"])
            self.assertEqual(sorted(os.listdir(tmp)), ["manifest.json"])
        self.assertEqual((SAMPLE / "manifest.json").read_bytes(), before)

    def test_no_build_drops_a_field_or_sale_detail_the_installed_version_has(self):
        # 0.1.2's Desk fields and sale details (partner-kit 45f228c4): a shop's update refuses a dropped field
        v012 = ["pp_rsr_section", "pp_rsr_occupation", "pp_rsr_purpose", "pp_rsr_certificate_date",
                "pp_rsr_certificate_by", "pp_rsr_signed_order_date", "pp_rsr_prescriber_address", "pp_rsr_rx_ingredients"]
        m = build.build_manifest()
        for dt in ("Sales Invoice", "Delivery Note"):
            got = {f["fieldname"]: f["fieldtype"] for f in m["custom_fields"] if f["dt"] == dt}
            self.assertLessEqual(set(v012), set(got), dt)
            self.assertEqual(got["pp_rsr_certificate_date"], "Date")  # nor changes a field's type
        self.assertLessEqual({"PP RSR Occupation", "PP RSR Purpose", "PP RSR Prescriber Address"},
                             {a["name"] for a in m["sale_attributes"]})

    def test_a_detail_read_from_the_customers_linked_record_is_declared_with_its_record(self):
        # since K1 0.1.2 (PH-B1d) the patient's ID is on the counter-rules app's patient record, which links to the Customer
        rec = {"doctype": "PP RXC Patient", "match": "customer_link", "field": "id_number"}
        self.assertEqual(declared("sa_pharmacy.drug_register")["details"]["detail_2"], {"label": "رقم الهوية", "record": rec})
        self.assertEqual(declared("ae_abu_dhabi_pharmacy.ph_17")["details"]["detail_2"],
                         {"label": "Patient identifier", "record": rec})
        # the record and field it names are K1's today, the record linking its customer by a field named customer (the
        # door refuses a lookup of a field that does not exist)
        k1 = json.loads((SAMPLE.parent / "s39_pharmacy_counter" / "manifest.json").read_text(encoding="utf-8"))
        pat = next(d for d in k1["doctypes"] if d["name"] == "PP RXC Patient")
        got = {f["fieldname"]: f for f in pat["fields"]}
        self.assertEqual(got["id_number"]["fieldtype"], "Data")
        self.assertEqual((got["customer"]["fieldtype"], got["customer"]["options"], got["customer"].get("unique")),
                         ("Link", "Customer", 1))
        self.assertFalse([b for b in build.build_manifest()["register_books"]
                          if "pp_rxc_id_number" in json.dumps(b)])

    def test_every_authority_source_is_a_sale_detail_and_a_desk_field_the_counter_rules_app_installs(self):
        # the door refuses a declaration naming a sale detail the shop does not have (at install): every authority source
        # is K1's, and the prescription's date (K1 0.1.3, PH-B1e) is named where the book prints it (Jordan, Mexico)
        k1 = json.loads((SAMPLE.parent / "s39_pharmacy_counter" / "manifest.json").read_text(encoding="utf-8"))
        details = {a["name"] for a in k1["sale_attributes"]}
        for ds in build.datasets():          # the authority's sources are the data set's, every book of it
            a = ds.get("authority") or {}
            self.assertLessEqual(set(a.get("pos_sale_details", {}).values()), details, ds["id"])
            for dt in ("Sales Invoice", "Delivery Note"):
                fields = {f["fieldname"]: f["fieldtype"] for f in k1["custom_fields"] if f["dt"] == dt}
                self.assertLessEqual(set(a.get("desk_fields", {}).values()), set(fields), ds["id"])
            prints_it = any("authority_date" in c["value"] for b in ds["books"] for c in b["columns"])
            self.assertEqual(prints_it, "authority_date" in a.get("pos_sale_details", {}), ds["id"])
            self.assertEqual(prints_it, "authority_date" in a.get("desk_fields", {}), ds["id"])
            if prints_it:
                self.assertEqual((a["pos_sale_details"]["authority_date"], a["desk_fields"]["authority_date"]),
                                 ("PP RXC Rx Date", "pp_rxc_rx_date"))
                self.assertEqual(fields["pp_rxc_rx_date"], "Date")

    def test_a_detail_with_no_source_is_declared_with_none(self):
        # the door accepts it and leaves its slot empty for the shop to write in
        empty = sorted(f"{b['book']}:{d['label']}" for b in build.build_manifest()["register_books"]
                       for d in b["details"].values() if set(d) == {"label"})
        self.assertEqual(empty, ["eg_pharmacy.received_dispensed:رقم القيد فى دفتر التذاكر الطبية",
                                 "eg_pharmacy.received_dispensed:سنه", "sa_pharmacy.drug_register:الملف الطبي"])
        age = declared("sa_pharmacy.drug_register")["details"]["detail_1"]  # the door works the age out
        self.assertEqual(age, {"label": "عمر المريض", "type": "Age",
                               "record": {"doctype": "PP RXC Patient", "match": "customer_link", "field": "birth_date"}})

    def test_the_declaration_names_where_the_receipt_columns_come_from(self):
        d = declared("ke_pharmacy.npp_ledger")
        self.assertEqual(d["columns_from"]["Stock Entry"], {"reference_no": "custom_external_reference_no"})  # the ERP path
        self.assertEqual(d["columns_from"]["Purchase Receipt"], {"reference_no": "supplier_delivery_note"})  # no bill_no

    def test_the_declaration_names_every_detail_by_its_slot_and_its_sources(self):
        d = declared("ke_pharmacy.poisons_book")
        self.assertEqual(d["details"]["detail_1"], {"label": "Business, trade or occupation", "person": 1,
                                                    "pos_sale_detail": "PP RSR Occupation", "desk_field": "pp_rsr_occupation"})
        # the purchaser's occupation and purpose and the certificate's giver are a person's
        self.assertEqual([s for s, x in d["details"].items() if x.get("person")], ["detail_1", "detail_2", "detail_4"])
        self.assertEqual(d["details"]["detail_3"]["type"], "Date")  # the door routes it as a date
        self.assertEqual((d["medium"], declared("ke_pharmacy.npp_ledger")["medium"]), ("printed_book", "system_of_record"))
        self.assertEqual(d["required"], ["counterparty", "counterparty_address", "detail_1", "detail_2"])
        self.assertEqual(d["class_source"], {"item_table": "pp_rxc_schedules", "class_field": "schedule",
                                             "from_field": "effective_from", "group_field": "pp_rxc_schedule",
                                             "axis": "KE Poisons"})
        self.assertEqual(declared("ke_pharmacy.npp_ledger")["class_source"]["axis"], "KE Controlled")


class DataSetFormat(unittest.TestCase):
    """Each rule of the format, broken once: the check must name it (a canary for each)."""

    def refused(self, mutate, words):
        ds = copy.deepcopy(KE)
        mutate(ds)
        bad = build.check(ds)
        self.assertTrue(any(words in b for b in bad), f"{words!r} not in {bad}")
        with self.assertRaises(SystemExit):
            build.build_manifest([ds])

    def test_kenya_and_the_liquor_fixture_pass(self):
        self.assertEqual((build.check(KE), build.check(LIQUOR)), ([], []))

    def test_in_is_refused(self):
        self.refused(lambda d: d["books"][0]["conditions"].append({"field": "item_class", "operator": "in", "value": "a,b"}),
                     "the operator is one of")

    def test_four_conditions_are_refused(self):
        self.refused(lambda d: d["books"][0]["conditions"].extend([{"field": "qty", "operator": ">", "value": 0}] * 2),
                     "at most 3")

    def test_a_date_value_against_a_number_column_is_refused(self):
        self.refused(lambda d: d["books"][0]["conditions"].append(
            {"field": "qty", "operator": ">", "value": "2026-01-01"}), "a date is not one")

    def test_a_date_column_compared_with_a_number_is_refused(self):
        # the condition form reads a date as the number 0: expiry_date > 20260101 would pass the check and never hold
        self.refused(lambda d: d["books"][0]["conditions"].append(
            {"field": "expiry_date", "operator": ">", "value": 20260101}), "expiry_date is a date or a time")

    def test_every_comparison_on_a_date_or_time_column_is_refused(self):
        for col in build.DATE_COLUMNS:
            for op in ("=", "!=", ">", ">=", "<", "<="):
                self.refused(lambda d: d["books"][0]["conditions"].__setitem__(
                    0, {"field": col, "operator": op, "value": "2026-01-01" if op in ("=", "!=") else 1}),
                    f"{col} is a date or a time")

    def test_a_declared_date_detail_is_a_date_too(self):
        self.refused(lambda d: d["books"][0]["conditions"].__setitem__(
            0, {"field": "detail:certificate_date", "operator": "=", "value": "2026-01-01"}), "is a date or a time")

    def test_whether_a_date_is_set_may_route(self):
        ds = copy.deepcopy(KE)
        ds["books"][0]["conditions"][0] = {"field": "expiry_date", "operator": "is set"}
        ds["books"][1]["conditions"][0] = {"field": "detail:certificate_date", "operator": "is not set"}
        self.assertEqual(build.check(ds), [])

    def test_a_detail_with_a_key_the_format_does_not_have_is_refused(self):
        self.refused(lambda d: d["details"]["occupation"].__setitem__("lookup", {"doctype": "Customer"}),
                     "lookup is not a key of a detail")

    def test_a_record_lookup_takes_the_specs_three_keys(self):
        good = {"doctype": "Customer", "match": "customer", "field": "pp_rxc_id_number"}
        for broken in ({**good, "match": "supplier"}, {k: v for k, v in good.items() if k != "field"}, {**good, "match": "user"},
                       {**good, "doctype": "PP RXC Patient"}, {**good, "match": "customer_link"},
                       {**good, "filters": "x"}, {**good, "doctype": "<b>Customer</b>"}, {**good, "field": "Bad Field"}):
            self.refused(lambda d: d["details"].__setitem__("id_no", {"label": "ID", "type": "Data", "record": broken}),
                         "details.id_no.record")

    def test_a_detail_read_from_a_record_has_no_other_source(self):
        rec = {"doctype": "Customer", "match": "customer", "field": "pp_rxc_id_number"}
        self.refused(lambda d: d["details"]["occupation"].__setitem__("record", rec), "has no other source")
        self.refused(lambda d: d["details"].__setitem__("id_no", {"label": "ID", "type": "Data", "record": rec,
                                                                 "desk_field": "pp_rxc_id_number"}), "has no other source")

    def test_a_sale_detail_or_desk_field_of_another_app_is_a_name(self):
        self.refused(lambda d: d["details"].__setitem__("dose", {"label": "Dose", "type": "Data",
                                                                "desk_field": "Directions"}), "details.dose")
        self.refused(lambda d: d["details"].__setitem__("dose", {"label": "Dose", "type": "Data",
                                                                "pos_sale_detail": "{{ x }}"}), "details.dose")

    def test_an_own_detail_names_no_other_apps_source(self):
        self.refused(lambda d: d["details"]["occupation"].__setitem__("desk_field", "pp_rxc_occupation"),
                     "names no other")

    def test_a_record_detail_takes_no_till_and_no_route(self):
        rec = {"doctype": "Customer", "match": "customer", "field": "pp_rxc_id_number"}
        self.refused(lambda d: d["details"].update(occupation={"label": "ID", "type": "Data", "record": rec, "till": 0}),
                     "no till")

        def route_on_it(d):
            d["details"]["occupation"] = {"label": "ID", "type": "Data", "record": rec}
            d["books"][0]["conditions"][0] = {"field": "detail:occupation", "operator": "is set"}
        self.refused(route_on_it, "the door does not route on it")

    def test_the_dispensers_licence_is_a_record_lookup(self):
        self.refused(lambda d: d["authority"]["dispenser_licence"].__setitem__("match", "owner"),
                     "authority.dispenser_licence")
        self.refused(lambda d: d["authority"]["dispenser_licence"].__setitem__("match", "customer_link"),
                     "authority.dispenser_licence")  # the dispenser's licence is the user's, never the customer's

    def test_a_period_takes_a_month_count_that_divides_the_year_and_its_due_days(self):
        for months in (5, 0, 24, True, "6"):
            self.refused(lambda d: d["books"][0].update(period_months=months, return_due_days=0), "period_months")
        for days in (-1, 367, True, None, 1.5):
            self.refused(lambda d: d["books"][0].update(period_months=6, return_due_days=days), "return_due_days")
        self.refused(lambda d: d["books"][0].update(period_months=6), "return_due_days")  # say 0 where the law names no day
        self.refused(lambda d: d["books"][0].update(return_due_days=15), "period_months")  # a due day of no period

    def test_a_reminder_name_over_the_shops_length_is_refused(self):
        def long_ids(d):
            d["id"] = "a" * 30
            d["books"][0].update(id="b" * 20, period_months=1, return_due_days=0)
        self.refused(long_ids, "over 61 characters")

    def test_a_condition_on_something_not_on_the_line_is_refused(self):
        self.refused(lambda d: d["books"][0]["conditions"].__setitem__(0, {"field": "parent.customer", "operator": "is set"}),
                     "reads a column of the line")

    def test_a_column_that_is_not_on_the_line_is_refused(self):
        self.refused(lambda d: d["books"][0]["columns"][0]["value"].append("customer"), "is not a column of the line")

    def test_an_undeclared_detail_is_refused(self):
        self.refused(lambda d: d["books"][1]["columns"][0]["value"].append("detail:nothing"), "is not a column of the line")

    def test_classes_without_a_class_source_are_refused(self):
        self.refused(lambda d: d["books"][0].pop("class_source"), "class_source")

    def test_a_class_table_without_its_axis_is_refused(self):
        self.refused(lambda d: d["books"][2]["class_source"].pop("axis"), "class_source")

    def test_a_column_source_for_a_document_the_door_does_not_book_is_refused(self):
        self.refused(lambda d: d["columns_from"].__setitem__("Quotation", {"reference_no": "name"}), "columns_from")

    def test_a_column_source_for_a_column_routing_reads_is_refused(self):
        self.refused(lambda d: d["columns_from"]["Stock Entry"].__setitem__("authority_no", "remarks"), "columns_from")

    def test_markup_in_a_form_is_refused(self):
        self.refused(lambda d: d["books"][0].__setitem__("form", "<i>16</i>"), "form")

    def test_classes_and_groups_together_are_refused(self):
        self.refused(lambda d: d["books"][0].__setitem__("item_groups", ["Medicines"]), "one of the two")

    def test_an_unknown_correction_mode_is_refused(self):
        self.refused(lambda d: d["books"][0].__setitem__("correction", "edit"), "correction")

    def test_markup_in_a_label_is_refused(self):
        self.refused(lambda d: d["books"][0]["columns"][0].__setitem__("label", "<b>Date</b>"), "a plain label")

    def test_template_syntax_in_a_title_is_refused(self):
        self.refused(lambda d: d.__setitem__("title", "{{ doc.owner }}"), "title")

    def test_a_colour_that_is_not_a_colour_is_refused(self):
        self.refused(lambda d: d["books"][2].__setitem__("in_colour", "red;background:url(x)"), "in_colour")

    def test_the_balance_before_a_line_prints_only_in_a_book_that_keeps_a_balance(self):
        self.refused(lambda d: d["books"][0]["columns"].append({"label": "Before", "value": ["balance_before"]}),
                     "balance_before")
        ds = copy.deepcopy(KE)
        ds["books"][2]["columns"].append({"label": "Before", "value": ["balance_before"]})  # the NPP ledger keeps one
        self.assertEqual(build.check(ds), [])
        self.refused(lambda d: d["books"][0]["conditions"].append(
            {"field": "balance_before", "operator": "is set"}), "conditions")  # never routed on

    def test_a_columns_band_is_plain_text(self):
        self.refused(lambda d: d["books"][0]["columns"][0].__setitem__("group", "<b>in</b>"), "group")

    def test_a_person_flag_is_0_or_1_and_an_age_needs_its_record(self):
        self.refused(lambda d: d["details"]["occupation"].__setitem__("person", 2), "person")
        self.refused(lambda d: d["details"]["occupation"].__setitem__("type", "Age"), "an Age")

    def test_a_print_language_is_a_language_code(self):
        self.refused(lambda d: d.__setitem__("print_language", "Arabic"), "print_language")

    def test_a_purchaser_slip_is_0_or_1(self):
        self.refused(lambda d: d["books"][0].__setitem__("purchaser_slip", "yes"), "purchaser_slip")

    def test_seven_details_are_refused(self):
        self.refused(lambda d: d["details"].__setitem__("seventh", {"label": "x", "type": "Data"}), "at most 6")

    def test_a_retention_of_none_is_refused(self):
        self.refused(lambda d: d["books"][0].pop("retention_years"), "retention_years")

    def test_uncertified_is_stated(self):
        self.refused(lambda d: d.pop("certified"), "certified")


class KenyaRouting(unittest.TestCase):
    """Act s. 31(2): a supply on prescription goes to the Prescription Book and not the Poisons Book; the NPP ledger takes
    every movement of a controlled drug. One movement may enter several books; each book reads its own axis."""
    PETH = {"KE Poisons": "KE Part I Poison", "KE Controlled": "KE NPP"}  # one drug, two axes

    def enters(self, **kw):
        return routing.books_for(KE, line(1, **kw))

    def test_a_poison_sold_without_a_prescription_enters_the_poisons_book_only(self):
        self.assertEqual(self.enters(), ["poisons_book"])

    def test_a_poison_sold_on_prescription_enters_the_prescription_book_only(self):
        self.assertEqual(self.enters(authority_no="RX-0042"), ["prescription_book"])

    def test_a_drug_on_both_axes_sold_on_prescription_enters_the_prescription_book_and_the_ledger(self):
        self.assertEqual(self.enters(item_classes=self.PETH, authority_no="RX-0043"), ["prescription_book", "npp_ledger"])

    def test_a_drug_on_both_axes_sold_without_one_enters_the_poisons_book_and_the_ledger(self):
        self.assertEqual(self.enters(item_classes=self.PETH), ["poisons_book", "npp_ledger"])

    def test_a_controlled_drug_on_the_controlled_axis_only_never_enters_the_poisons_books(self):
        self.assertEqual(self.enters(item_classes={"KE Controlled": "KE NPP"}, item_class=None, authority_no="RX-1"),
                         ["npp_ledger"])

    def test_a_receipt_of_a_controlled_drug_enters_the_ledger_only(self):
        self.assertEqual(self.enters(item_classes=self.PETH, direction="In", kind="Receipt"), ["npp_ledger"])

    def test_no_outgoing_movement_but_a_sale_enters_a_sales_book(self):
        for kind in ("Transfer", "Issue", "Loss", "Disposal", "Repack"):
            self.assertEqual(self.enters(kind=kind), [], kind)
        self.assertEqual(self.enters(kind="Return", direction="Out"), [])  # a return to the supplier

    def test_a_receipt_of_a_poison_enters_no_book(self):
        self.assertEqual(self.enters(direction="In", kind="Receipt"), [])

    def test_an_item_of_no_listed_class_enters_no_book(self):
        self.assertEqual(self.enters(item_class=None), [])
        self.assertEqual(self.enters(item_class="KE Part II Poison"), [])

    def test_a_blank_prescription_number_is_not_set(self):
        self.assertEqual(self.enters(authority_no="   "), ["poisons_book"])

    def test_a_correction_goes_to_the_book_of_the_line_it_concerns(self):
        # a cancelled sale's correction is not a sale; routed, it would leave the Poisons Book
        self.assertEqual(self.enters(kind="Correction", direction="In", book="poisons_book", correction_of_number=1),
                         ["poisons_book"])

    def test_a_return_follows_the_books_its_sale_entered(self):
        self.assertEqual(self.enters(kind="Return", direction="In", original_books=["prescription_book", "npp_ledger"]),
                         ["prescription_book", "npp_ledger"])

    def test_a_number_column_compares_as_a_number_as_the_save_rule_form_does(self):
        self.assertTrue(routing.holds({"qty": "10"}, {"field": "qty", "operator": ">", "value": 5}))
        self.assertTrue(routing.holds({"qty": "1,000"}, {"field": "qty", "operator": "=", "value": 1000}))
        self.assertTrue(routing.holds({"kind": " Sale "}, {"field": "kind", "operator": "=", "value": "Sale"}))
        self.assertTrue(routing.holds({"authority_no": []}, {"field": "authority_no", "operator": "is not set"}))

    def test_the_routing_reads_the_save_rule_forms_own_words(self):
        self.assertEqual([(c["field"], c["operator"]) for b in KE["books"] for c in b["conditions"]],
                         [("kind", "="), ("authority_no", "is not set"), ("kind", "="), ("authority_no", "is set")])


@NEED_JINJA
class KenyaLayouts(unittest.TestCase):
    def test_the_poisons_book_prints_form_16s_columns_in_order(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), [line(1)])
        heads = re.findall(r"<th>(.*?)</th>", out)
        self.assertEqual(heads, ["No.", "Date of sale", "Name and quantity of poison supplied", "Purchaser&#39;s name",
                                 "Address", "Business, trade or occupation", "Purpose for which stated to be required",
                                 "Date of certificate (if any)", "Name and address of person giving certificate (if any)",
                                 "Signature of purchaser, or the date of a permitted signed order"])
        self.assertEqual(cells(out)[0][:7], ["1", "2026-10-20", "Tramadol 50 mg capsules · 10 · Nos", "A. Buyer",
                                             "1 Moi Avenue, Nairobi", "Farmer", "Pest control"])

    def test_every_book_says_it_is_not_certified_cites_its_law_and_names_the_establishment(self):
        for b in KE["books"]:
            out, _ = render(KE, b["id"], period(f"ke_pharmacy.{b['id']}"), [])
            self.assertIn("A starting point, not certified for the country.", out)
            self.assertIn(b["cite"].split(";")[0].replace("'", "&#39;"), out)
            self.assertIn("Demo Chemists Ltd, 1 Moi Avenue, Nairobi", out)  # Annex II's header
            self.assertIn("No entries in this period.", out)  # the door told it the book holds none in the range
            self.assertEqual("Kept as the book: signed" in out, b["medium"] in ("printed_book", "official_book"), b["id"])
            out, _ = render(KE, b["id"], period(f"ke_pharmacy.{b['id']}"), [], signed=False, total=None)
            self.assertIn("No entries you may read in this period. A print sent by e-mail", out)  # never just "none"

    def test_the_prescription_book_prints_the_prescriber_and_the_prescription(self):
        ln = line(7, book="ke_pharmacy.prescription_book", authority_no="RX-0042", authority_issuer="Dr. A. Daktari",
                  detail_6="Kenyatta Hospital, Nairobi")
        out, _ = render(KE, "prescription_book", period("ke_pharmacy.prescription_book"), [ln])
        self.assertEqual(cells(out)[0], ["7", "2026-10-20", "Tramadol 50 mg capsules · 10 · Nos",
                                         "A. Buyer · 1 Moi Avenue, Nairobi",
                                         "Dr. A. Daktari · Kenyatta Hospital, Nairobi · RX-0042"])

    def test_the_ledger_prints_a_page_per_drug_received_in_red_and_the_balance(self):
        b = "ke_pharmacy.npp_ledger"
        lines = [line(1, book=b, item="PHD-PETH-50", item_name="Pethidine 50 mg", item_class="KE NPP", direction="In",
                      kind="Receipt", qty=100, balance=100, counterparty="Kenya Medical Supplies", reference_no="INV-77"),
                 line(2, book=b, item="PHD-PETH-50", item_name="Pethidine 50 mg", item_class="KE NPP", qty=5, balance=95,
                      authority_no="RX-0043"),
                 line(1, book=b, item="PHD-MORPH-10", item_name="Morphine 10 mg", item_class="KE NPP", direction="In",
                      kind="Receipt", qty=20, balance=20, counterparty="Kenya Medical Supplies", reference_no="INV-78")]
        states = [{"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "PHD-MORPH-10", "item_name": "Morphine 10 mg"},
                  {"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "PHD-PETH-50", "item_name": "Pethidine 50 mg"}]
        out, _ = render(KE, "npp_ledger", period(b), lines, states)
        self.assertEqual(out.count('class="page"'), 2)
        self.assertLess(out.index("Morphine 10 mg"), out.index("Pethidine 50 mg"))
        peth = cells(out)[-2:]  # the second page: pethidine, in entry order
        self.assertEqual(peth[0][1:9], ["2026-10-20", "Kenya Medical Supplies", "100", "INV-77", "", "", "", "100"])
        self.assertEqual(peth[1][1:9], ["2026-10-20", "", "", "", "A. Buyer", "5", "RX-0043", "95"])
        self.assertIn('style="color: #b00020">100', out)  # received in red ink (s. 8.1(i))
        self.assertNotIn('style="color: #b00020">5', out)

    def test_a_cancelled_sale_is_struck_through_once_and_never_prints_as_a_second_sale(self):
        lines = [line(1), line(2, kind="Correction", direction="In", correction_of="L-1", correction_of_number=1,
                              signed_by_name="Q. Manager", correction_note="sale cancelled")]
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), lines)
        self.assertEqual(out.count('class="struck"'), 1)
        self.assertRegex(out, r'<tr class="struck">\s*<td class="no">1</td>')
        rows = cells(out)
        self.assertEqual([r[0] for r in rows], ["1", "2"])  # entry 2 is a note under entry 1, not a row of its own
        self.assertIn('<tr class="note"><td class="no">2</td>', out)
        self.assertEqual(rows[1][1], "Struck through by entry 2. sale cancelled Signed Q. Manager. The entry&#39;s author: "
                                     "P. Pharmacist.")  # the door's note, under its original
        self.assertNotIn('class="struck"><td>Struck', out)  # the note sits outside the struck cells
        self.assertIn("2 entries.", out)

    def test_a_cancelled_issue_in_the_ledger_never_prints_as_a_receipt(self):
        b = "ke_pharmacy.npp_ledger"
        lines = [line(1, book=b, item_class="KE NPP", qty=5, balance=95),
                 line(2, book=b, item_class="KE NPP", kind="Correction", direction="In", qty=5, balance=100,
                      correction_of="L-1", correction_of_number=1, signed_by_name="P. Pharmacist")]
        st = [{"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "PHD-TRAM-50", "item_name": "Tramadol"}]
        out, _ = render(KE, "npp_ledger", period(b), lines, st)
        self.assertNotIn('style="color: #b00020"', out)
        self.assertEqual(out.count('<tr class="note">'), 1)  # the correction is the note under its original, no row

    def test_a_reversing_line_and_a_dated_note_print_in_their_markets_way(self):
        for mode, want in (("reversing_line", "Entry 2 reverses entry 1"), ("dated_note", "Note dated 2026-10-20 to entry 1")):
            ds = copy.deepcopy(KE)
            ds["books"][0]["correction"] = mode
            lines = [line(1), line(2, kind="Correction", direction="In", correction_of_number=1, signed_by_name="X")]
            out, _ = render(ds, "poisons_book", period("ke_pharmacy.poisons_book"), lines)
            self.assertIn(want, out, mode)
            self.assertNotIn('class="struck"', out, mode)

    def test_a_signed_amendment_prints_beside_the_entry_without_striking_it(self):
        ds = copy.deepcopy(KE)
        ds["books"][0]["correction"] = "signed_amendment"
        lines = [line(1), line(2, kind="Correction", direction="In", qty=0, correction_of_number=1, signed_by_name="X",
                              correction_note="address is 2 Moi Avenue")]
        out, _ = render(ds, "poisons_book", period("ke_pharmacy.poisons_book"), lines)
        self.assertNotIn('class="struck"', out)
        self.assertIn("Amended by entry 2. address is 2 Moi Avenue Signed X.", out)

    def test_the_ledger_carries_its_balance_forward_and_prints_openings_and_counts_as_notes(self):
        b = "ke_pharmacy.npp_ledger"
        common = dict(book=b, item="PHD-PETH-50", item_name="Pethidine 50 mg", item_class="KE NPP")
        lines = [line(1, kind="Opening", direction="In", qty=40, balance=40, entry_date="2026-09-01",
                      signed_by_name="P. Pharmacist", **common),
                 line(2, qty=5, balance=35, entry_date="2026-09-15", **common),
                 line(3, kind="Count", direction="Out", qty=2, balance=33, signed_by_name="P. Pharmacist", **common),
                 line(1, book=b, item="PHD-MORPH-10", item_name="Morphine 10 mg", item_class="KE NPP", direction="In",
                      kind="Opening", qty=8, balance=8, entry_date="2026-09-01", signed_by_name="P. Pharmacist")]
        st = [{"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "PHD-MORPH-10", "item_name": "Morphine 10 mg"},
              {"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "PHD-PETH-50", "item_name": "Pethidine 50 mg"}]
        out, _ = render(KE, "npp_ledger", period(b), lines, st)
        self.assertIn("Balance brought forward: 35.", out)
        self.assertIn("Balance brought forward: 8.", out)  # no movement this month, still a page: the stock is held
        self.assertIn("Entry 3: count, -2 Nos. Balance 33. Signed P. Pharmacist.", out)
        self.assertNotIn('style="color: #b00020"', out)  # an opening or a count is never a red receipt

    def test_the_period_says_whether_the_entry_chain_holds(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book", chain_status="holds, checked 2026-10-22"),
                        [line(1)])
        self.assertIn("Entry chain: holds, checked 2026-10-22", out)

    def test_a_late_line_says_when_it_was_entered(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"),
                        [line(3, booked_late=1, entered_at="2026-10-21 08:15:00")])
        self.assertIn("Entered late. 2026-10-21 08:15:00", out)

    def test_a_period_of_another_book_is_not_printed_in_this_layout(self):
        out, calls = render(KE, "poisons_book", period("ke_pharmacy.npp_ledger"), [line(1)])
        self.assertIn("Choose that book&#39;s print format", out.replace("'", "&#39;"))
        self.assertEqual(calls, [])  # the door's print is never asked for another book

    def test_it_prints_only_this_book_store_and_dates_as_the_door_reads_them(self):
        lines = [line(n) for n in range(1, 451)] + [line(1, register_store="Other store"), line(9, entry_date="2026-09-30")]
        out, calls = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), lines)
        self.assertEqual(calls, ["ke_pharmacy.poisons_book"])  # one read: the door's print, which pages by itself
        self.assertEqual(len(cells(out)), 450)
        self.assertIn("450 entries.", out)
        self.assertNotIn("stopped at its reading limit", out)

    def test_a_print_says_what_the_door_could_not_read(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), [line(1)], cut=True, total=7,
                        persons_hidden=True)
        self.assertIn("This print holds 1 of the 7 entries in this period: it is not the whole book.", out)
        self.assertIn("This print stopped at its reading limit", out)
        self.assertIn("A person&#39;s details are not shown: your role may not read them.", out.replace("'", "&#39;"))

    def test_an_erased_entry_says_so_and_a_non_sale_entry_names_its_kind(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"),
                        [line(1, counterparty=None, counterparty_address=None, erased=True), line(2, kind="Loss")])
        self.assertIn("A person&#39;s details erased after the retention.", out.replace("'", "&#39;"))
        self.assertEqual([r[0] for r in cells(out)], ["1", "2Loss"])

    def test_the_door_s_words_go_through_the_translator_and_the_page_turns_right_to_left(self):
        ar = {"No.": "رقم", "Entry chain: {0}": "سلسلة القيود: {0}"}
        b = next(x for x in KE["books"] if x["id"] == "poisons_book")
        decl = build.declaration(KE, b)
        out = shop_env().from_string(build.book_html(KE, b)).render(
            doc=period("ke_pharmacy.poisons_book", chain_status="holds"),
            ivn_register_print=lambda d: door_print(decl, d, [line(1)]), _=lambda s, **k: ar.get(s, s), is_rtl=lambda: True)
        self.assertIn('dir="rtl"', out)
        self.assertIn("<th>رقم</th>", out)
        self.assertIn("سلسلة القيود: holds", out)

    def test_the_address_prints_as_the_door_gives_its_lines_never_its_stored_markup(self):
        # walk-found on :8117: the core stores an address with <br> breaks, and the layout printed them as text
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"),
                        [line(1, counterparty_address="1 Moi Avenue<br>Nairobi<br>Kenya<br>")])
        self.assertEqual(cells(out)[0][4], "1 Moi Avenue, Nairobi, Kenya")
        self.assertNotIn("&lt;br&gt;", out)

    def test_a_value_is_printed_as_text_never_as_markup(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"),
                        [line(1, counterparty="<script>x()</script>", detail_1="{{ 7*7 }}")])
        self.assertNotIn("<script>x()", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("{{ 7*7 }}", out)


@NEED_JINJA
class Canaries(unittest.TestCase):
    """Each guard in the template, removed once: the rendering must then show the harm (a canary for each)."""

    def mutant(self, old, new, times=1):
        b = next(x for x in KE["books"] if x["id"] == "poisons_book")
        html = build.book_html(KE, b)
        self.assertEqual(html.count(old), times, old)
        return html.replace(old, new)

    def run_(self, html, lines, doc=None):
        return render(KE, "poisons_book", doc or period("ke_pharmacy.poisons_book"), lines, html=html)[0]

    def test_without_escaping_a_value_prints_as_markup(self):
        html = self.mutant("{{ cell.s|e }}", "{{ cell.s }}")
        self.assertIn("<script>x()", self.run_(html, [line(1, counterparty="<script>x()</script>")]))

    def test_without_the_book_guard_another_books_period_prints_here(self):
        html = self.mutant("{%- if doc.book != book.ref -%}", "{%- if false -%}")
        html = html.replace("if doc.book == book.ref else {}", "")
        out = self.run_(html, [line(1, book="ke_pharmacy.npp_ledger")], period("ke_pharmacy.npp_ledger"))
        self.assertIn("Tramadol", out)

    def test_without_the_note_branch_a_cancel_prints_as_a_movement(self):
        html = self.mutant('{%- elif r.kind == "note" -%}', "{%- elif false -%}")
        out = self.run_(html, [line(1), line(2, kind="Correction", direction="In", correction_of_number=1)])
        self.assertNotIn('<tr class="note">', out)  # the strike-through's note printed as a row of its own

    def test_without_the_direction_a_sale_prints_in_the_received_half(self):
        b = "ke_pharmacy.npp_ledger"
        ds_book = next(x for x in KE["books"] if x["id"] == "npp_ledger")
        html = build.book_html(KE, ds_book)
        self.assertEqual(html.count("{%- if not c.when or c.when == l.direction -%}"), 1)
        html = html.replace("{%- if not c.when or c.when == l.direction -%}", "{%- if true -%}")
        st = [{"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "PHD-TRAM-50", "item_name": "Tramadol"}]
        good = render(KE, "npp_ledger", period(b), [line(1, book=b, qty=5, balance=95)], st)[0]
        bad = render(KE, "npp_ledger", period(b), [line(1, book=b, qty=5, balance=95)], st, html=html)[0]
        self.assertNotEqual(cells(good), cells(bad))


def rows_reader(lines):
    """ivn_rows on Retail Register Line as the slip reads it: filters of =, one sort field."""
    def ivn_rows(dt, filters=None, fields=None, order_by=None, limit=50, start=0):
        assert dt == "Retail Register Line" and limit <= 200
        rows = [r for r in lines if all(r.get(f) == v for f, op, v in filters or [] if op == "=")]
        assert all(op == "=" for _f, op, _v in filters or [])
        rows = sorted(rows, key=lambda r: r["number"])
        return [{k: r.get(k) for k in fields} for r in rows[start:start + limit]]
    return ivn_rows


@NEED_JINJA
class ReviewFolds(unittest.TestCase):
    """What the 0.2.0 review found, each pinned (lane pb32regkit)."""

    def test_a_reader_without_the_person_level_gets_empty_cells_never_the_frameworks_debug_text(self):
        # the framework leaves a column above the reader's level out of a list read: the door's rows lack those keys
        hidden = ("counterparty", "counterparty_address", "correction_note", "detail_1", "detail_2", "detail_3",
                  "detail_4", "detail_5", "detail_6")
        ln = {k: v for k, v in line(1).items() if k not in hidden}
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), [ln], persons_hidden=True)
        self.assertNotIn("no such element", out)
        self.assertEqual(cells(out)[0][3:7], ["", "", "", ""])
        self.assertIn("A person&#39;s details are not shown", out.replace("'", "&#39;"))

    def slip(self, doc, lines):
        b = next(x for x in KE["books"] if x["id"] == "poisons_book")
        html = build.slips(KE, b)[0]["html"]
        return shop_env().from_string(html).render(doc=doc, ivn_rows=rows_reader(lines), _=lambda s, **k: s,
                                                   is_rtl=lambda: False)

    def test_the_slip_lists_the_sales_entries_only_and_none_for_a_cancel_or_a_return(self):
        sale = {"doctype": "POS Invoice", "name": "S-1", "docstatus": 1, "company": "Demo Chemists Ltd",
                "posting_date": "2026-10-20", "customer_name": "A. Buyer"}
        lines = [line(9, voucher_type="POS Invoice", voucher_no="S-1", qty=1.0),
                 line(12, voucher_type="POS Invoice", voucher_no="S-1", kind="Correction", direction="In", qty=1.0,
                      correction_of_number=9)]
        out = self.slip(sale, lines)
        self.assertEqual([r[0] for r in cells(out)], ["9"])  # the cancel's correction never reads as received
        self.assertIn("<td>1 Nos</td>", out)  # the quantity as the book prints it, never 1.0
        self.assertIn("This sale was cancelled", self.slip({**sale, "docstatus": 2}, lines))
        self.assertNotIn("Signature of purchaser", self.slip({**sale, "docstatus": 2}, lines))
        self.assertIn("A return has no purchaser", self.slip({**sale, "is_return": 1}, lines))

    def test_a_late_entry_says_so_once_where_the_book_prints_its_remarks(self):
        b = "jo_pharmacy.form_9"
        from test_markets import JO, page_state  # noqa: E402
        ln = line(1, book=b, item_class="JO Schedule 2", direction="In", kind="Receipt", balance=10, booked_late=1,
                  entered_at="2026-10-21 08:00:00", remarks="Entered late.")
        out, _ = render(JO, "form_9", period(b), [ln], page_state(b))
        self.assertEqual(out.count("Entered late."), 1)

    def test_an_official_book_prints_each_entry_at_its_line_and_its_reversal_in_its_own_row(self):
        from test_markets import JO, page_state  # noqa: E402
        b = "jo_pharmacy.form_9"
        common = dict(book=b, item_class="JO Schedule 2", sequence="SEQ-1")
        lines = [line(1, **common, balance=5), line(2, **common, kind="Correction", direction="In", qty=10, balance=15,
                                                    correction_of_number=1, signed_by_name="P. Pharmacist")]
        starts = {"SEQ-1": [{"from": 1, "volume": 1, "page": 12, "line": 3, "lines": 20}]}
        out, _ = render(JO, "form_9", period(b), lines, page_state(b), starts=starts)
        self.assertIn("Volume 1, page 12", out)
        rows = cells(out)
        self.assertEqual([r[:2] for r in rows[:4]], [["", "1"], ["", "2"], ["1", "3"], ["2Correction", "4"]])  # blank lines 1-2
        self.assertIn("Entry 2 reverses entry 1.", rows[3][-1])  # one entry, one line of the book: its note rides in it
        self.assertNotIn('<tr class="note">', out)

    def test_a_signed_off_period_prints_its_close_and_its_seals(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book", name="P-1", status="Signed off"),
                        [line(1)], closing=True, sealed=["Pharmacy Dispensary - ICG entry 1: 9f86d081"],
                        signed_off="Signed off by P. Pharmacist on 01-11-2026.")
        self.assertIn("Sealed at sign-off: Pharmacy Dispensary - ICG entry 1: 9f86d081", out)
        self.assertIn("Signed off by P. Pharmacist on 01-11-2026.", out)
        self.assertIn("The period&#39;s close: signed", out.replace("'", "&#39;"))

    def test_an_official_book_kept_in_one_run_names_each_drugs_balance_brought_forward(self):
        from test_markets import AE  # noqa: E402
        b = "ae_abu_dhabi_pharmacy.ph_20"
        out, _ = render(AE, "ph_20", period(b), [line(1, book=b, item_class="AE Narcotic", balance=30)],
                        brought_items=[("Morphine 10 mg", "5")])
        self.assertIn("Balance brought forward: Morphine 10 mg 5.", out)


class FormatFolds(unittest.TestCase):
    """Each way a data set passed check() and was refused by the shop's checker or the door, now refused here."""

    def refused(self, change, words):
        ds = copy.deepcopy(KE)
        change(ds)
        self.assertTrue([b for b in build.check(ds) if words in b], (words, build.check(ds)))

    def test_an_unknown_key_is_refused_never_left_out(self):
        self.refused(lambda d: d["books"][2].__setitem__("per_item_pages", 1), "per_item_pages is not a key of a book")
        self.refused(lambda d: d["books"][0].__setitem__("period_month", 6), "period_month is not a key of a book")
        self.refused(lambda d: d.__setitem__("data_sets", []), "data_sets: not a key of a data set")
        self.refused(lambda d: d["books"][0]["columns"][0].__setitem__("colour", "red"), "colour is not a key of a column")

    def test_the_doors_own_refusals(self):
        self.refused(lambda d: d["books"][0].__setitem__("loss_count_hours", 24), "loss_count_hours")  # no balance
        self.refused(lambda d: d["books"][0]["conditions"].append({"field": "booked_late", "operator": "=", "value": True}),
                     "never true or false")
        self.refused(lambda d: d["books"][0]["conditions"].append(
            {"field": "kind", "operator": "=", "value": "Sale", "note": "x"}), "a field, an operator and a value")
        self.refused(lambda d: d["details"].__setitem__("free_text", {"label": "Free", "type": "Data"})
                     or d["books"][0]["required"].append("detail:free_text"), "has no source to fill it")
        self.refused(lambda d: d["authority"].__setitem__("permit", {}), "its sources go under")
        self.refused(lambda d: d["authority"]["pos_sale_details"].__setitem__("permit_no", "X"), "maps authority_no")
        self.refused(lambda d: d["books"][0]["columns"].append({"label": "Hash", "value": ["line_hash"]}),
                     "'line_hash' is not a column")
        self.refused(lambda d: d["books"][0].__setitem__("id", "a_very_long_book_identifier_that_runs_on_and_on"),
                     "over 61 characters")

    def test_every_name_still_fits_under_the_library_prefix(self):
        # the App library lists this app renamed to IVENDNEXT RSR (7 letters longer): every name the prefix starts must
        # still fit the shop's 61 characters, or the renamed copy is refused
        m = build.build_manifest()
        grow = len("IVENDNEXT RSR") - len(build.PREFIX)
        names = [p["name"] for p in m["print_formats"]] + [n["name"] for n in m["notifications"]]
        self.assertLessEqual(max(map(len, names)) + grow, build.NAME_MAX, max(names, key=len))

    def test_the_build_runs_the_shops_checker_before_it_writes(self):
        self.assertEqual(build.refusals(build.build_manifest()), [])
        m = build.build_manifest()
        m["print_formats"][0]["name"] = "PP RSR " + "x" * 70
        self.assertTrue(build.refusals(m))


class Template(unittest.TestCase):
    def test_the_book_reads_only_the_doors_print_and_the_slip_only_ivn_rows(self):
        def calls_in(name):
            txt = re.sub(r"\{#.*?#\}", "", (SAMPLE / "layouts" / name).read_text(encoding="utf-8"), flags=re.S)
            self.assertNotRegex(txt, r"get_all|get_list|get_value|get_doc|\.db\.|fr" r"appe|erp" r"next")  # split: no such word
            return set(re.findall(r"\b(\w+)\(", " ".join(re.findall(r"\{[{%]-?(.*?)-?[}%]\}", txt, flags=re.S))))
        # its own macro, the door's print, the translator, the page's direction, and filters and string methods
        self.assertLessEqual(calls_in("register.html"),
                             {"value", "ivn_register_print", "_", "is_rtl", "namespace", "format", "split", "strip", "map", "join"})
        self.assertNotIn("ivn_rows", calls_in("register.html"))  # every line, note and page is the door's
        self.assertLessEqual(calls_in("purchaser_slip.html"), {"ivn_rows", "_", "is_rtl", "format"})

    def test_no_market_or_vertical_in_the_apps_code_or_names(self):
        words = re.compile(r"kenya|nigeria|\bKE\b|pharma|poison|drug|medic|liquor|tobacco|npp", re.I)
        markets = re.compile(r"kenya|nigeria|ghana|egypt|saudi|emirat|dubai|abu_?dhabi|jordan|mexic|cameroon|rwanda|nairobi|"
                             r"lagos|accra|cairo|riyadh|amman|sfda|nafdac|mohap|cofepris|tatmeen|nphies|jfda|ppb", re.I)
        codes = re.compile(r"\b(KE|NG|GH|EG|SA|AE|UAE|JO|MX|KSA|CM|RW)\b")
        self.assertFalse(words.findall((SAMPLE / "layouts" / "register.html").read_text(encoding="utf-8")))
        for py in ("build.py", "routing.py"):  # every name the code uses; its words to a reader may give examples
            with open(SAMPLE / py, encoding="utf-8") as f:
                toks = list(tokenize.generate_tokens(f.readline))
            idents = [t.string for t in toks if t.type == tokenize.NAME]
            self.assertFalse([i for i in idents if words.search(i)], py)
            # and no market in the strings the code holds, as S39's test since its 0.1.1: a market's name, or its code as a
            # value the code compares (docstrings left out, and the trade's words: a description gives a reader examples)
            text = {tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}   # an f-string's text, 3.12+
            strings = [t.string for t in toks if t.type in text and not t.string.startswith(('"""', 'r"""'))]
            self.assertFalse([x for x in strings if markets.search(x) or codes.search(x)], py)
        m = build.build_manifest()
        names = [m["app"], m["prefix"], m["title"], build.ROLE] + [f["fieldname"] for f in m["custom_fields"]] + \
                [a["name"] for a in m["sale_attributes"]] + [r["name"] for r in m["reports"]] + [w["name"] for w in m["workspaces"]]
        self.assertFalse([n for n in names if words.search(n)], names)


class SecondDataSet(unittest.TestCase):
    """A one-book liquor stock register (by item group, every movement, a page per item, a running balance): it loads,
    builds and renders with no code change."""
    sets = [KE, LIQUOR]

    def test_it_builds_with_the_kenya_set_and_adds_its_own_column(self):
        m = build.build_manifest(self.sets)
        self.assertEqual(validate.validate(m), [])
        self.assertIn("pp_rsr_id_document", [f["fieldname"] for f in m["custom_fields"] if f["dt"] == "Sales Invoice"])
        self.assertIn("PP RSR Id Document", [a["name"] for a in m["sale_attributes"]])
        d = build.build_manifest(self.sets)
        self.assertEqual([b["book"] for b in d["register_books"]][-1], "example_liquor.stock_register")
        self.assertEqual(d["register_books"][-1]["items"], {"item_groups": ["Spirits"]})
        self.assertNotIn("class_source", d["register_books"][-1])

    def test_a_shared_column_kept_off_the_till_in_one_set_and_on_it_in_another_is_refused(self):
        other = copy.deepcopy(LIQUOR)
        other["id"] = "example_two"
        other["details"] = {"occupation": {"label": "Occupation", "type": "Data", "own": 1}}  # KE keeps it on the till
        KE2 = copy.deepcopy(KE)
        KE2["details"]["occupation"]["till"] = 0
        other["books"][0]["columns"][-2]["value"] = ["detail:occupation"]
        with self.assertRaises(SystemExit):
            build.build_manifest([KE2, other])

    def test_every_movement_of_its_items_enters_and_nothing_else(self):
        for kw in ({}, {"direction": "In", "kind": "Receipt"}, {"kind": "Transfer"}):
            self.assertEqual(routing.books_for(LIQUOR, line(1, item_group="Spirits", item_class=None, **kw)),
                             ["stock_register"])
        self.assertEqual(routing.books_for(LIQUOR, line(1, item_group="Beer")), [])

    @NEED_JINJA
    def test_its_book_renders_from_the_same_template_a_page_per_item_with_its_balance(self):
        b = "example_liquor.stock_register"
        lines = [line(1, book=b, item="WHISKY-70", item_name="Whisky 70 cl", direction="In", kind="Receipt", qty=12,
                      balance=12, counterparty="Distiller Ltd"),
                 line(2, book=b, item="WHISKY-70", item_name="Whisky 70 cl", qty=2, balance=10, detail_1="ID 12345")]
        st = [{"book": b, "register_store": "Pharmacy Dispensary - ICG", "item": "WHISKY-70", "item_name": "Whisky 70 cl"}]
        out, _ = render(LIQUOR, "stock_register", period(b), lines, st)
        self.assertEqual(cells(out), [["1", "2026-10-20", "12", "", "Distiller Ltd", "", "12"],
                                      ["2", "2026-10-20", "", "2", "A. Buyer", "ID 12345", "10"]])
        self.assertIn("A test data set, not any market&#39;s register", out.replace("'", "&#39;"))


if __name__ == "__main__":
    unittest.main()
