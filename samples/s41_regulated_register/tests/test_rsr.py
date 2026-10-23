"""The Regulated stock register's laptop tests, before the register door exists: the manifest is the build of the data
sets and passes the kit's checks; a data set the format refuses is refused, case by case; Kenya's routing sends each
fixture line to the right books; each book renders from fixture lines shaped as the door's line (PB-4 spec §3.1), read
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
    from jinja2.sandbox import SandboxedEnvironment
except ImportError:
    if os.environ.get("RSR_REQUIRE_JINJA") or os.environ.get("S29_REQUIRE_JINJA"):
        raise
    jinja2 = None

NEED_JINJA = unittest.skipUnless(jinja2, "jinja2 is not installed: the rendering tests did not run")
KE = json.loads((SAMPLE / "datasets" / "ke_pharmacy.json").read_text(encoding="utf-8"))
LIQUOR = json.loads((HERE / "fixtures" / "liquor_one_book.json").read_text(encoding="utf-8"))


def line(n, **kw):
    """A line as the door writes it (PB-4 spec §3.1)."""
    base = dict(number=n, book="ke_pharmacy.poisons_book", register_store="Pharmacy Dispensary - ICG", item="PHD-TRAM-50",
                item_name="Tramadol 50 mg capsules", item_class="KE Part I Poison", direction="Out", kind="Sale", qty=10,
                uom="Nos", balance=None, movement_date="2026-10-20", entry_date="2026-10-20",
                entered_at="2026-10-20 10:00:00", counterparty="A. Buyer", counterparty_address="1 Moi Avenue, Nairobi",
                reference_no=None, authority_no=None, authority_issuer=None, dispenser_name="P. Pharmacist",
                booked_late=0, correction_of=None, correction_of_number=None, correction_note=None, signed_by_name=None, remarks=None,
                detail_1="Farmer", detail_2="Pest control", detail_3=None, detail_4=None, detail_5=None, detail_6=None)
    base.update(kw)
    return base


def stand_in(lines, states=()):
    """ivn_rows as the door's print would see it: filters of =, != and between, one sort field, pages of up to 200.
    It records each call so a test can see the print read nothing else."""
    calls = []

    def ivn_rows(dt, filters=None, fields=None, order_by=None, limit=50, start=0):
        calls.append((dt, filters, start, limit))
        assert 1 <= limit <= 200 and start >= 0
        rows = {"Retail Register Line": lines, "Retail Register State": list(states)}[dt]
        for f, op, v in filters or []:
            if op == "=":
                rows = [r for r in rows if r.get(f) == v]
            elif op == "between":
                rows = [r for r in rows if v[0] <= r.get(f) <= v[1]]
            elif op == "<":
                rows = [r for r in rows if r.get(f) < v]
            else:
                raise AssertionError(f"operator {op}")
        if order_by:
            key, _, way = order_by.partition(" ")
            rows = sorted(rows, key=lambda r: r[key], reverse=way == "desc")
        return [{k: r.get(k) for k in fields} if fields else dict(r) for r in rows[start:start + limit]]

    return ivn_rows, calls


def period(book, **kw):
    return {"book": book, "register_store": "Pharmacy Dispensary - ICG", "from_date": "2026-10-01",
            "to_date": "2026-10-31", "establishment": "Demo Chemists Ltd", "establishment_address": "1 Moi Avenue, Nairobi",
            **kw}


def render(ds, book_id, doc, lines, states=()):
    b = next(x for x in ds["books"] if x["id"] == book_id)
    ivn_rows, calls = stand_in(lines, states)
    env = SandboxedEnvironment(autoescape=False)  # the shop renders a print with autoescape off: the template escapes
    return env.from_string(build.book_html(ds, b)).render(doc=doc, ivn_rows=ivn_rows), calls


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
    return next(b for b in build.build_declaration()["register_books"] if b["book"] == ref)


class Manifest(unittest.TestCase):
    def test_the_files_are_the_build_of_the_data_sets(self):
        self.assertEqual(json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8")), build.build_manifest())
        self.assertEqual(json.loads((SAMPLE / "door_declaration.json").read_text(encoding="utf-8")), build.build_declaration())

    def test_the_manifest_passes_the_checker_and_the_shops_two_install_refusals(self):
        m = build.build_manifest()
        self.assertEqual(validate.validate(m), [])
        self.assertEqual(site_rules.refusals(m), [])

    def test_it_installs_only_parts_whose_record_types_exist_today(self):
        m = build.build_manifest()
        self.assertEqual(sorted(k for k in m if isinstance(m[k], list)),
                         ["custom_fields", "reports", "sale_attributes", "workspaces"])
        self.assertEqual({f["dt"] for f in m["custom_fields"]}, {"Sales Invoice", "Delivery Note"})
        self.assertEqual(m["reports"][0]["ref_doctype"], "Stock Reconciliation")
        self.assertNotIn("Retail Register", json.dumps(m))  # the door's record types install in the next version

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
        d = build.build_declaration()
        m = {"manifest_version": 2, "app": "pp_rsr", "prefix": "PP RSR", "title": "x", "version": "0.2.0",
             "publisher": "x", "description": "x", "print_formats": d["print_formats"]}
        self.assertEqual((validate.validate(m), validate.warnings(m)), ([], []))
        names = [p["name"] for p in d["print_formats"]]
        self.assertEqual(len(names), sum(len(ds["books"]) for ds in build.datasets()))  # one print per book of every set
        self.assertLessEqual({"PP RSR Kenya Poisons Book", "PP RSR Kenya Prescription Book", "PP RSR Kenya NPP Ledger Book",
                              "PP RSR Jordan Narcotics and psychotropics register",
                              "PP RSR Nigeria Part B morphine"}, set(names))
        self.assertTrue(all(p["doc_type"] == "Retail Register Period" for p in d["print_formats"]))

    def test_the_declaration_names_where_the_receipt_columns_come_from(self):
        d = declared("ke_pharmacy.npp_ledger")
        self.assertEqual(d["columns_from"]["Stock Entry"], {"reference_no": "custom_external_reference_no"})  # the ERP path
        self.assertEqual(d["columns_from"]["Purchase Receipt"], {"reference_no": "supplier_delivery_note"})  # no bill_no

    def test_the_declaration_names_every_detail_by_its_slot_and_its_sources(self):
        d = declared("ke_pharmacy.poisons_book")
        self.assertEqual(d["details"]["detail_1"], {"label": "Business, trade or occupation",
                                                    "pos_sale_detail": "PP RSR Occupation", "desk_field": "pp_rsr_occupation"})
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

    def test_a_date_comparison_is_refused(self):
        self.refused(lambda d: d["books"][0]["conditions"].append(
            {"field": "movement_date", "operator": ">", "value": "2026-01-01"}), "a date is not one")

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

    def test_a_page_per_item_numbered_per_book_is_refused(self):
        self.refused(lambda d: d["books"][2].__setitem__("numbering", "book_store"), "a page per item")

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
            self.assertIn("No entries you may read in this period. A print sent by e-mail", out)  # never just "none"
            self.assertEqual("Kept as the book: signed" in out, b["medium"] != "system_of_record", b["id"])

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
        self.assertEqual(out.count('class="item-page"'), 2)
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
        self.assertEqual([r[0] for r in rows], ["1", ""])  # entry 2 is a note under entry 1, not a row of its own
        self.assertEqual(rows[1][1], "Struck through by entry 2: sale cancelled. Signed Q. Manager, the entry&#39;s author "
                                     "being P. Pharmacist.")
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
        self.assertEqual(len([r for r in cells(out) if r[0]]), 1)

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
        self.assertIn("Amended by entry 2: address is 2 Moi Avenue. Signed X", out)

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
        self.assertIn("Entry 3: register count, -2, balance 33. Signed P. Pharmacist.", out)
        self.assertNotIn('style="color: #b00020"', out)  # an opening or a count is never a red receipt

    def test_the_period_says_whether_the_entry_chain_holds(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book", chain_status="holds, checked 2026-10-22"),
                        [line(1)])
        self.assertIn("Entry chain: holds, checked 2026-10-22", out)

    def test_a_late_line_says_when_it_was_entered(self):
        out, _ = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"),
                        [line(3, booked_late=1, entered_at="2026-10-21 08:15:00")])
        self.assertIn("Entered late, 2026-10-21 08:15:00.", out)

    def test_a_period_of_another_book_is_not_printed_in_this_layout(self):
        out, calls = render(KE, "poisons_book", period("ke_pharmacy.npp_ledger"), [line(1)])
        self.assertIn("Choose that book&#39;s print format", out.replace("'", "&#39;"))
        self.assertEqual(calls, [])

    def test_it_reads_only_this_book_store_and_dates_and_pages_by_200(self):
        lines = [line(n) for n in range(1, 451)] + [line(1, register_store="Other store"), line(9, entry_date="2026-09-30")]
        out, calls = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), lines)
        self.assertEqual([(c[2], c[3]) for c in calls], [(0, 200), (200, 200), (400, 200)])
        self.assertEqual(len(cells(out)), 450)
        self.assertIn("450 entries.", out)
        self.assertNotIn("stopped at its reading limit", out)

    def test_a_print_that_reaches_its_reading_limit_says_so(self):
        lines = [line(n) for n in range(1, 10_001)]
        out, calls = render(KE, "poisons_book", period("ke_pharmacy.poisons_book"), lines)
        self.assertEqual(len(calls), 50)
        self.assertIn("This print stopped at its reading limit", out)
        self.assertEqual({c[0] for c in calls}, {"Retail Register Line"})

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
        ivn_rows, _ = stand_in(lines)
        return SandboxedEnvironment().from_string(html).render(doc=doc or period("ke_pharmacy.poisons_book"), ivn_rows=ivn_rows)

    def test_without_escaping_a_value_prints_as_markup(self):
        html = self.mutant("{{ cell.s|e }}", "{{ cell.s }}")
        self.assertIn("<script>x()", self.run_(html, [line(1, counterparty="<script>x()</script>")]))

    def test_without_the_book_guard_another_books_period_prints_here(self):
        html = self.mutant("{%- if doc.book != book.ref -%}", "{%- if false -%}")
        out = self.run_(html, [line(1, book="ke_pharmacy.npp_ledger")], period("ke_pharmacy.npp_ledger"))
        self.assertIn("Tramadol", out)

    def test_without_the_correction_branch_a_cancel_prints_as_a_second_sale(self):
        html = self.mutant("{%- elif l.correction_of_number -%}", "{%- elif false -%}")
        out = self.run_(html, [line(1), line(2, kind="Correction", direction="In", correction_of_number=1)])
        self.assertIn("2", [r[0] for r in cells(out)])  # entry 2 printed as a sale of its own

    def test_without_the_paging_a_long_book_prints_200_lines(self):
        html = self.mutant("{%- for p in range(50) if ns.more -%}", "{%- for p in range(1) if ns.more -%}", times=2)
        out = self.run_(html, [line(n) for n in range(1, 451)])
        self.assertIn("200 entries.", out)


class Template(unittest.TestCase):
    def test_the_template_reads_other_records_only_through_ivn_rows(self):
        txt = re.sub(r"\{#.*?#\}", "", (SAMPLE / "layouts" / "register.html").read_text(encoding="utf-8"), flags=re.S)
        self.assertNotRegex(txt, r"get_all|get_list|get_value|get_doc|\.db\.|fr" r"appe|erp" r"next")  # split: no such word here
        calls = set(re.findall(r"\b(\w+)\(", " ".join(re.findall(r"\{[{%]-?(.*?)-?[}%]\}", txt, flags=re.S))))
        self.assertLessEqual(calls, {"ivn_rows", "page", "row", "note", "range", "namespace", "selectattr"})  # its own macros; selectattr is a filter

    def test_no_market_or_vertical_in_the_apps_code_or_names(self):
        words = re.compile(r"kenya|nigeria|\bKE\b|pharma|poison|drug|medic|liquor|tobacco|npp", re.I)
        self.assertFalse(words.findall((SAMPLE / "layouts" / "register.html").read_text(encoding="utf-8")))
        for py in ("build.py", "routing.py"):  # every name the code uses; its words to a reader may give examples
            with open(SAMPLE / py, encoding="utf-8") as f:
                idents = [t.string for t in tokenize.generate_tokens(f.readline) if t.type == tokenize.NAME]
            self.assertFalse([i for i in idents if words.search(i)], py)
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
        d = build.build_declaration(self.sets)
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
