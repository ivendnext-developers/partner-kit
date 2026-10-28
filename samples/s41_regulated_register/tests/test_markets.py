"""The markets after Kenya, each a data set with no code change: Jordan (Forms 8 and 9), Nigeria (the First Schedule's
Parts A and B, one register per class), the UAE's Abu Dhabi (PH 17, PH 20), Ghana (the Dangerous Drugs Record), Saudi
Arabia (a register per drug), Egypt (the received and dispensed book) and Mexico (the libros de control). Each routing test names the clause it follows; each book
renders from lines shaped as the door's line (the register books page, §5), through the stand-in print reader of test_rsr.

    python3 -m unittest discover -s samples/s41_regulated_register/tests -p 'test_*.py'
"""
import copy
import json
import re
import unittest
from pathlib import Path

from test_rsr import KE, NEED_JINJA, cells, line, period, render  # first: it puts the sample on the path

import build  # noqa: E402
import routing  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((SAMPLE / "datasets" / f"{name}.json").read_text(encoding="utf-8"))


JO, NG, AE, GH, SA, MX, EG = (load(n) for n in ("jo_pharmacy", "ng_pharmacy", "ae_abu_dhabi_pharmacy", "gh_pharmacy",
                                                "sa_pharmacy", "mx_pharmacy", "eg_pharmacy"))
MARKETS = (JO, NG, AE, GH, SA, MX, EG)


def enters(ds, item_class, **kw):
    return routing.books_for(ds, line(1, item_class=item_class, **kw))


def heads(html):
    """The printed headers, a column under a band read as "band: label" (Jordan's received and dispensed halves)."""
    thead = re.search(r"<thead>(.*?)</thead>", html, flags=re.S).group(1)
    rows = re.findall(r"<tr>(.*?)</tr>", thead, flags=re.S)
    labels = [h.replace("&#39;", "'") for h in re.findall(r"<th>(.*?)</th>", rows[-1])]
    if len(rows) == 1:
        return labels
    bands = [text for span, text in re.findall(r'<th(?: colspan="(\d+)")?>(.*?)</th>', rows[0], flags=re.S)
             for _ in range(int(span or 1))]
    return [f"{b}: {lab}" if b else lab for b, lab in zip(bands, labels)]


class EveryMarket(unittest.TestCase):
    def test_each_data_set_passes_the_format(self):
        for ds in MARKETS:
            self.assertEqual(build.check(ds), [], ds["id"])

    def test_each_is_uncertified_and_says_so_in_its_own_words(self):
        for ds in MARKETS:
            self.assertEqual(ds["certified"], 0, ds["id"])
            self.assertTrue(ds["notice"].startswith("A starting point, not certified for the country."), ds["id"])

    def test_no_book_is_kept_by_the_system_alone_where_no_law_says_it_may_be(self):
        # KE alone cites electronic records (NPP s. 8.1); JO, MX and SA only an approved or verified system
        for ds in MARKETS:
            for b in ds["books"]:
                self.assertIn(b["medium"], ("printed_book", "official_book"), f"{ds['id']}.{b['id']}")

    def test_an_uncited_correction_takes_the_strictest_mode(self):
        # the door's correction modes: EG, GH, JO and MX are uncited and take a reversing line; NG, AE and SA follow their clause
        want = {"jo_pharmacy": "reversing_line", "gh_pharmacy": "reversing_line", "mx_pharmacy": "reversing_line",
                "ae_abu_dhabi_pharmacy": "reversing_line", "ng_pharmacy": "dated_note", "sa_pharmacy": "signed_amendment",
                "eg_pharmacy": "reversing_line"}
        for ds in MARKETS:
            self.assertEqual({b["correction"] for b in ds["books"]}, {want[ds["id"]]}, ds["id"])

    def test_the_retention_is_the_cited_one(self):
        got = {f"{ds['id']}.{b['id']}": b["retention_years"] for ds in MARKETS for b in ds["books"]}
        self.assertEqual(got["jo_pharmacy.form_9"], 5)  # Instructions Art. 7(c); Law 12/2013 Art. 74
        self.assertEqual(got["jo_pharmacy.form_8"], 2)  # Instructions Art. 7(b); Law 23/2016 Art. 25(a)(2)
        self.assertEqual({v for k, v in got.items() if k.startswith("ng_")}, {2})  # reg. 26
        # DOH s. 7.4 keeps the record 5 years; the UAE keeps health data 25 (Law 2/2019 Art. 20), and the door keeps a
        # person's details as long as the entry (the register books page, §8)
        self.assertEqual({got["ae_abu_dhabi_pharmacy.ph_17"], got["ae_abu_dhabi_pharmacy.ph_20"]}, {25})
        self.assertEqual(got["sa_pharmacy.drug_register"], 10)  # Art. 22(6)
        self.assertEqual(got["eg_pharmacy.received_dispensed"], 10)  # Law 182/1960 Art. 31

    def test_a_period_and_its_return_only_where_the_law_names_one(self):
        got = {f"{ds['id']}.{b['id']}": (b.get("period_months"), b.get("return_due_days"))
               for ds in MARKETS + (KE,) for b in ds["books"] if "period_months" in b or "return_due_days" in b}
        self.assertEqual(got, {"ae_abu_dhabi_pharmacy.ph_17": (1, 0),  # DOH s. 4.6: monthly; no due day stated
                               "ae_abu_dhabi_pharmacy.ph_20": (3, 0),  # quarterly for narcotics
                               "sa_pharmacy.drug_register": (6, 0),  # Art. 16(2): every six months; no day stated
                               "eg_pharmacy.received_dispensed": (6, 15)})  # Art. 23: first 15 days of January and July

    def test_no_market_adds_a_till_detail_of_its_own(self):
        # every own column of a data set is a Desk field and a till detail in every shop: the markets after Kenya add
        # one Desk-only column (Nigeria's ingredients) and reuse Kenya's prescriber's address
        own = build.own_details(build.datasets())
        self.assertEqual([k for k in own if k not in load("ke_pharmacy")["details"]], ["rx_ingredients"])
        self.assertEqual(own["rx_ingredients"].get("till"), 0)

    def test_a_book_that_takes_more_than_sales_requires_no_column_on_the_desk(self):
        # the door: a person's Desk submit with a required column empty is refused, so a book that takes an
        # issue, a disposal or a transfer (a stock entry: no customer, no address) must require nothing, or the
        # regulator-witnessed disposal itself would be refused
        for ds in MARKETS:
            for b in ds["books"]:
                takes = [k for k in ("Issue", "Disposal", "Transfer")
                         if b["id"] in routing.books_for(ds, line(1, item_class=b.get("classes", [None])[0], kind=k))]
                if takes:
                    self.assertEqual(b.get("required", []), [], f"{ds['id']}.{b['id']} takes {takes}")


class JordanRouting(unittest.TestCase):
    """Instructions 2025 Art. 7(c)(1): Form 9 for narcotics and psychotropics (Law 23/2016 Art. 2: Schedules 1-9), every
    receipt (الوارد) and issue (الصادر), a page per drug; Art. 7(b): Form 8 for Schedule 10 preparations."""

    def test_a_receipt_and_a_sale_of_a_schedule_1_to_9_drug_enter_form_9(self):
        for n in (1, 4, 5, 9):
            self.assertEqual(enters(JO, f"JO Schedule {n}", direction="In", kind="Receipt"), ["form_9"], n)
            self.assertEqual(enters(JO, f"JO Schedule {n}", authority_no="RX-1"), ["form_9"], n)

    def test_every_issue_of_form_9_stock_enters_it_not_only_a_sale(self):
        for kind in ("Transfer", "Loss", "Disposal", "Issue"):
            self.assertEqual(enters(JO, "JO Schedule 2", kind=kind), ["form_9"], kind)

    def test_a_schedule_10_preparation_enters_form_8_only(self):
        self.assertEqual(enters(JO, "JO Schedule 10"), ["form_8"])
        self.assertEqual(enters(JO, "JO Schedule 10", direction="In", kind="Receipt"), ["form_8"])

    def test_a_precursor_or_an_unscheduled_item_enters_no_book(self):
        for cls in ("JO Schedule 11", "JO Schedule 12", None):
            self.assertEqual(enters(JO, cls), [], cls)


class NigeriaRouting(unittest.TestCase):
    """reg. 18(1)(a): every supply purchased or otherwise obtained (Part A) and every dealing (Part B), in the First
    Schedule's form; reg. 18(1)(b): a separate register or part for each class; reg. 18(1)(d): one per premises."""

    def test_a_receipt_enters_part_a_of_its_class_only(self):
        self.assertEqual(enters(NG, "NG Morphine", direction="In", kind="Receipt"), ["part_a_morphine"])

    def test_a_sale_enters_part_b_of_its_class_only(self):
        self.assertEqual(enters(NG, "NG Morphine"), ["part_b_morphine"])
        self.assertEqual(enters(NG, "NG Indian hemp", authority_no="RX-9"), ["part_b_hemp"])

    def test_a_drug_part_iii_applies_to_by_order_has_its_register(self):
        # reg. 18(1)(a): 'any of the drugs'; the 1950 Order applies Part III to amidone, a later one to pethidine
        self.assertEqual(enters(NG, "NG Other Part III drugs"), ["part_b_other"])
        self.assertEqual(enters(NG, "NG Other Part III drugs", direction="In", kind="Receipt"), ["part_a_other"])

    def test_codeine_has_no_retail_register(self):
        # Modified Form Regulations reg. 3(2) replaces regs 11-19 for codeine and dionin; reg. 9 exempts a retailer
        self.assertNotIn("NG Codeine and dionine", {c for b in NG["books"] for c in b["classes"]})

    def test_every_dealing_out_enters_part_b_not_only_a_sale(self):
        # Part B's title: sold or supplied; reg. 18(1)(a): all dealings. A disposal, an issue, a move to another
        # premises (its own register, reg. 18(1)(d)), a loss and stock consumed into a preparation all leave it
        for kind in ("Issue", "Disposal", "Transfer", "Loss", "Repack"):
            self.assertEqual(enters(NG, "NG Diamorphine", kind=kind), ["part_b_diamorphine"], kind)

    def test_a_return_to_the_supplier_with_no_original_is_a_supply_out(self):
        self.assertEqual(enters(NG, "NG Cocaine and ecgonine", kind="Return"), ["part_b_cocaine"])

    def test_a_transfer_in_from_another_premises_is_obtained(self):
        self.assertEqual(enters(NG, "NG Medical opium", direction="In", kind="Transfer"), ["part_a_opium"])

    def test_a_preparation_made_is_obtained(self):
        # a repack's output may leave the class (an exempt preparation) or stay in it: each side is booked, so no
        # unit leaves or enters the register unseen
        self.assertEqual(enters(NG, "NG Morphine", direction="In", kind="Repack"), ["part_a_morphine"])

    def test_each_class_keeps_its_own_register(self):
        classes = {b["classes"][0] for b in NG["books"]}
        self.assertEqual(len(classes), 7)  # reg. 18(1)(b)(i)-(vii)
        for cls in classes:
            got = enters(NG, cls)
            self.assertEqual(len(got), 1, cls)
            self.assertEqual(next(b for b in NG["books"] if b["id"] == got[0])["classes"], [cls])

    def test_an_exempt_or_unlisted_drug_enters_none(self):
        self.assertEqual(enters(NG, None), [])
        self.assertEqual(enters(NG, "NG Second Schedule preparation"), [])  # reg. 25: the exemptions


class AbuDhabiRouting(unittest.TestCase):
    """DOH Standard s. 3.6.3: PH 20 records narcotic purchasing and dispensing; s. 3.6.1: PH 17 the SCD and CD
    (psychotropic) transactions within the pharmacy; s. 7.1: separate registers."""

    def test_a_narcotic_receipt_and_sale_enter_ph_20(self):
        self.assertEqual(enters(AE, "AE Narcotic", direction="In", kind="Receipt"), ["ph_20"])
        self.assertEqual(enters(AE, "AE Narcotic", authority_no="RX-1"), ["ph_20"])

    def test_a_psychotropic_or_semi_controlled_drug_enters_ph_17(self):
        self.assertEqual(enters(AE, "AE Psychotropic"), ["ph_17"])
        self.assertEqual(enters(AE, "AE Semi-controlled", direction="In", kind="Receipt"), ["ph_17"])

    def test_a_disposal_or_return_is_a_transaction_of_the_register(self):
        # s. 8.3: expired stock documented in the register; s. 8.11: returned to the supplier or destroyed
        for kind in ("Disposal", "Return", "Loss", "Issue"):
            self.assertEqual(enters(AE, "AE Narcotic", kind=kind), ["ph_20"], kind)


class GhanaRouting(unittest.TestCase):
    """Act 489 s. 34(2): recorded before any Class A supply; the Act sets no entry for Class B or for a receipt."""

    def test_a_class_a_supply_enters_the_record(self):
        self.assertEqual(enters(GH, "GH Class A", authority_no="RX-1"), ["dangerous_drugs_record"])
        self.assertEqual(enters(GH, "GH Class A"), ["dangerous_drugs_record"])

    def test_every_supply_out_enters_not_only_a_sale(self):
        # s. 34(2): 'before any person supplies': an issue to a clinic and a disposal are supplies
        for kind in ("Issue", "Disposal"):
            self.assertEqual(enters(GH, "GH Class A", kind=kind), ["dangerous_drugs_record"], kind)
        self.assertEqual(enters(GH, "GH Class A", kind="Loss"), [])  # a theft is no supply by the shop

    def test_a_receipt_a_transfer_or_a_class_b_sale_enters_none(self):
        self.assertEqual(enters(GH, "GH Class A", direction="In", kind="Receipt"), [])
        self.assertEqual(enters(GH, "GH Class A", kind="Transfer"), [])
        self.assertEqual(enters(GH, "GH Class B"), [])


class SaudiRouting(unittest.TestCase):
    """Executive Regulation Art. 22(1): a register for each drug containing a narcotic or psychotropic; (3) receipts
    (c, d) and dispensing (f, h) in the same register."""

    def test_a_receipt_and_a_dispensing_enter_the_drugs_register(self):
        for cls in ("SA Narcotic", "SA Psychotropic"):
            self.assertEqual(enters(SA, cls, direction="In", kind="Receipt"), ["drug_register"], cls)
            self.assertEqual(enters(SA, cls, authority_no="RX-1"), ["drug_register"], cls)

    def test_every_movement_out_enters_not_only_a_dispensing(self):
        for kind in ("Loss", "Disposal", "Transfer", "Issue"):
            self.assertEqual(enters(SA, "SA Narcotic", kind=kind), ["drug_register"], kind)

    def test_its_register_is_per_drug_with_a_balance(self):
        b = SA["books"][0]
        self.assertEqual((b["numbering"], b["balance"]), ("book_store_item", 1))  # the door prints a page per drug


class MexicoRouting(unittest.TestCase):
    """RIS Art. 159: the libro de control in sections by class (LGS Art. 226 I-III) and by product, for control and
    balance; Art. 124 VII: entries and exits."""

    def test_an_entry_and_an_exit_enter_the_section_of_its_fraccion(self):
        for n in ("I", "II", "III"):
            fid = f"fraccion_{n.lower()}"
            self.assertEqual(enters(MX, f"MX Fraccion {n}", direction="In", kind="Receipt"), [fid], n)
            self.assertEqual(enters(MX, f"MX Fraccion {n}", authority_no="F-0001"), [fid], n)

    def test_every_exit_enters_not_only_a_dispensing(self):
        for kind in ("Loss", "Disposal", "Transfer", "Issue"):
            self.assertEqual(enters(MX, "MX Fraccion II", kind=kind), ["fraccion_ii"], kind)

    def test_a_fraccion_iv_to_vi_medicine_enters_none(self):
        for n in ("IV", "V", "VI"):
            self.assertEqual(enters(MX, f"MX Fraccion {n}"), [], n)


class EgyptRouting(unittest.TestCase):
    """Law 182/1960 Art. 18: every narcotic received, on the day it arrives, and every one dispensed, in one book."""

    def test_a_receipt_and_a_dispensing_of_a_narcotic_enter_the_book(self):
        self.assertEqual(enters(EG, "EG Schedule 1", direction="In", kind="Receipt"), ["received_dispensed"])
        self.assertEqual(enters(EG, "EG Schedule 1", authority_no="RX-1"), ["received_dispensed"])

    def test_every_movement_out_enters_not_only_a_dispensing(self):
        for kind in ("Loss", "Disposal", "Transfer", "Issue"):
            self.assertEqual(enters(EG, "EG Schedule 1", kind=kind), ["received_dispensed"], kind)

    def test_a_schedule_2_preparation_enters_none(self):
        # Art. 1: the narcotics of Schedule 1, the preparations of Schedule 2 excepted
        self.assertEqual(enters(EG, "EG Schedule 2"), [])


class RoutingCanaries(unittest.TestCase):
    """A routing written the easy way, once: the real tests above must then fail."""

    def fails(self, mutate, test):
        global NG, GH
        saved = NG, GH
        NG, GH = copy.deepcopy(NG), copy.deepcopy(GH)
        mutate(NG, GH)
        try:
            with self.assertRaises(AssertionError):
                test()
        finally:
            NG, GH = saved

    def test_part_b_on_kind_sale_alone_misses_a_disposal(self):
        def m(ng, gh):
            for b in ng["books"]:
                if b["id"].startswith("part_b_"):
                    b["conditions"] = [{"field": "kind", "operator": "=", "value": "Sale"}]
        self.fails(m, NigeriaRouting("test_every_dealing_out_enters_part_b_not_only_a_sale")
                   .test_every_dealing_out_enters_part_b_not_only_a_sale)

    def test_parts_without_their_direction_put_a_receipt_in_part_b(self):
        def m(ng, gh):
            for b in ng["books"]:
                b["conditions"] = []
        self.fails(m, NigeriaRouting("test_a_receipt_enters_part_a_of_its_class_only")
                   .test_a_receipt_enters_part_a_of_its_class_only)

    def test_ghana_on_kind_sale_alone_misses_an_issue(self):
        def m(ng, gh):
            gh["books"][0]["conditions"] = [{"field": "kind", "operator": "=", "value": "Sale"}]
        self.fails(m, GhanaRouting("test_every_supply_out_enters_not_only_a_sale").test_every_supply_out_enters_not_only_a_sale)


def row(**kw):
    return line(1, **kw)


# Each book's printed headers, copied from its source (the form image, or the clause's own words and order), never
# from the data set: a dropped, moved or reworded column fails here.
HEADS = {
    "jo_pharmacy.form_9": ["التاريخ", "الوارد: رقم الفاتورة", "الوارد: الكمية", "الوارد: المستودع", "الوارد: ملاحظات",
                           "الوارد: التاريخ", "الصادر: رقم الوصفة الخاصة", "الصادر: التاريخ", "الصادر: الكمية",
                           "الصادر: اسم الطبيب", "الصادر: اسم المريض", "الرصيد"],  # p. 29
    "jo_pharmacy.form_8": ["التاريخ", "رقم الفاتورة", "الكمية الواردة", "الكمية المصروفة",
                           "الجهة المصروف لها (الطبيب / المريض / صيدلية القسم / صيدلية المستشفى / مستودع)",
                           "توقيع الصيدلي المسؤول", "الرصيد", "الملاحظات"],  # p. 28
    "ng_pharmacy.part_a": ["Name of substance purchased or otherwise obtained", "Date on which supply received",
                           "Name of person, body or firm from whom obtained",
                           "Address of person, body or firm for whom obtained", "Amount obtained",
                           "Form in which obtained"],  # p. 36, as printed
    "ng_pharmacy.part_b": ["Name of substance sold or supplied", "Date on which the transaction was effected",
                           "Name of person, body or firm to whom sold or supplied",
                           "Address of person, body or firm to whom sold or supplied",
                           "Authority of person, body or firm to be in possession of the substance",
                           "Amount sold or supplied", "Form in which sold or supplied",
                           "When sale is in a prescription specify the ingredients of the prescription"],  # p. 37
    "ae_abu_dhabi_pharmacy": ["Prescription reference number",
                              "Product, strength and formulation (brand and generic name, s. 7.7)", "Dose", "Quantity",
                              "Balance", "Name and license number of the prescribing physician",
                              "Name and license number of the dispensing pharmacist", "Patient's name and address",
                              "Patient identifier (s. 7.2.1)", "Date issued", "Source of the medicine", "Receiving date",
                              "Invoice reference number"],  # s. 3.6, and s. 7.2.1's patient identifier
    "gh_pharmacy.dangerous_drugs_record": [
        "Name and quantity of the drug supplied",
        "Name, address, and signature or thumbprint of the person to whom it is supplied",
        "Signature of the person who supplies the drug", "Date of supply"],  # s. 34(2)(a)-(d)
    "sa_pharmacy.drug_register": ["(ب) الرصيد السابق", "(ج) الكمية الواردة", "(ج) رقم التشغيل", "(ج) تاريخ الصلاحية", "(د) الجهة الوارد منها",
                                  "(د) تاريخ الورود", "(هـ) المجموع الكلي", "(و) الكمية المصروفة", "(و) رقم التشغيل",
                                  "(و) تاريخ الصرف", "(و) اسم من صرفها وتوقيعه", "(ح) اسم المريض", "(ح) عمره",
                                  "(ح) رقم الهوية", "(ح) الملف الطبي", "(ح) رقم الوصفة", "(ح) اسم من وصفها",
                                  "(ط) الكمية الباقية"],  # Art. 22(3)
    "eg_pharmacy.received_dispensed": ["أولا الوارد: تاريخ الورود", "أولا الوارد: اسم البائع وعنوانه", "نوع الجوهر المخدر",
                                       "أولا الوارد: كميته", "ثانيا المصروف (ا): اسم وعنوان محرر التذكرة",
                                       "ثانيا المصروف (ب): اسم المريض بالكامل ولقبه", "ثانيا المصروف (ب): سنه",
                                       "ثانيا المصروف (ب): عنوانه", "ثانيا المصروف (ج): التاريخ الذى صرف فيه الدواء",
                                       "ثانيا المصروف (ج): رقم القيد فى دفتر التذاكر الطبية",
                                       "ثانيا المصروف (ج): كمية الجواهر المخدرة"],  # Art. 18
    "mx_pharmacy": ["Fecha de entrada", "Entrada: cantidad", "Número de folio de la receta médica especial",
                    "Fecha en que fue emitida", "Nombre del medicamento prescrito", "Cantidad", "Dosificación", "Saldo",
                    "Nombre, domicilio y número de cédula profesional del médico que prescribe",
                    "Fecha del descargo del medicamento"],  # RIS Art. 124 VII (entries), Art. 117 I-IV
}


def expected_heads(ref):
    return HEADS.get(ref) or HEADS.get(ref.rsplit("_", 1)[0]) or HEADS[ref.split(".")[0]]


def page_state(ref, item="PHD-TRAM-50", item_name="Tramadol 50 mg capsules"):
    """The door's state row a page-per-drug print lists its drugs from."""
    return [{"book": ref, "register_store": "Pharmacy Dispensary - ICG", "item": item, "item_name": item_name}]


@NEED_JINJA
class EveryBookPrints(unittest.TestCase):
    def test_every_book_prints_its_sources_columns_in_order(self):
        for ds in MARKETS:
            for b in ds["books"]:
                ref = f"{ds['id']}.{b['id']}"
                cls = b["classes"][0]
                out, _ = render(ds, b["id"], period(ref), [row(book=ref, item_class=cls)], page_state(ref))
                place = ["Line in the book"] if b["medium"] == "official_book" else []  # the door's place column
                self.assertEqual(heads(out), ["No."] + place + expected_heads(ref), ref)
                self.assertIn("A starting point, not certified for the country.", out, ref)
                self.assertIn("Kept as the book: signed", out, ref)

    def test_every_pinned_layout_is_used(self):
        refs = [f"{ds['id']}.{b['id']}" for ds in MARKETS for b in ds["books"]]
        for key in HEADS:
            self.assertTrue(any(r == key or r.startswith(key) for r in refs), key)


@NEED_JINJA
class JordanLayouts(unittest.TestCase):
    def test_form_9_puts_a_receipt_in_the_in_half_and_a_dispensing_in_the_out_half(self):
        b = "jo_pharmacy.form_9"
        common = dict(book=b, item="PHD-MORPH-10", item_name="Morphine 10 mg", item_class="JO Schedule 1")
        lines = [row(**common, direction="In", kind="Receipt", qty=50, balance=50, counterparty="Drug Store Co.",
                     reference_no="INV-9"),
                 line(2, **common, qty=2, balance=48, authority_no="SRX-7", authority_date="2026-10-19",
                      authority_issuer="Dr. Haddad", counterparty="Patient A", movement_date="2026-10-21",
                      entry_date="2026-10-21")]
        out, _ = render(JO, "form_9", period(b), lines, page_state(b, "PHD-MORPH-10", "Morphine 10 mg"))
        rows = cells(out)
        self.assertEqual(rows[0], ["1", "", "2026-10-20", "INV-9", "50", "Drug Store Co.", "", "2026-10-20",
                                   "", "", "", "", "", "50"])  # the second cell: the line in JFDA's book (none set)
        self.assertEqual(rows[1], ["2", "", "2026-10-21", "", "", "", "", "", "SRX-7", "2026-10-19", "2",
                                   "Dr. Haddad", "Patient A", "48"])  # the out date is the special prescription's
        self.assertIn("النموذج رقم (9)", out)

    def test_a_note_on_an_issue_never_prints_in_the_in_half(self):
        b = "jo_pharmacy.form_9"
        out, _ = render(JO, "form_9", period(b), [row(book=b, item_class="JO Schedule 2", kind="Loss",
                                                      remarks="Loss or theft", balance=0)], page_state(b))
        self.assertNotIn("Loss or theft", cells(out)[0])

    def test_form_8_prints_no_invoice_number_on_a_dispensing(self):
        # the column is the supplier's or the stock movement's number (reference_no, the door's line); the notice says so
        b = "jo_pharmacy.form_8"
        out, _ = render(JO, "form_8", period(b), [row(book=b, item_class="JO Schedule 10", balance=4,
                                                      counterparty="Patient J")], page_state(b))
        self.assertEqual(cells(out)[0], ["1", "", "2026-10-20", "", "", "10", "Patient J", "P. Pharmacist", "4", ""])

    def test_form_8_prints_an_issues_reference_and_signs_the_pharmacist_line(self):
        b = "jo_pharmacy.form_8"
        out, _ = render(JO, "form_8", period(b), [row(book=b, item_class="JO Schedule 10", kind="Transfer",
                                                      reference_no="STE-4", counterparty="Ward pharmacy",
                                                      balance=9)], page_state(b))
        self.assertEqual(cells(out)[0], ["1Transfer", "", "2026-10-20", "STE-4", "", "10", "Ward pharmacy", "P. Pharmacist",
                                         "9", ""])  # a non-sale entry names its kind
        self.assertIn('class="cell mark"', out)

    def test_a_jordan_correction_is_a_reversing_line_never_a_strike(self):
        b = "jo_pharmacy.form_9"
        common = dict(book=b, item_class="JO Schedule 2")
        lines = [row(**common, balance=5), line(2, **common, kind="Correction", direction="In", qty=10, balance=15,
                                                  correction_of_number=1, signed_by_name="P. Pharmacist")]
        out, _ = render(JO, "form_9", period(b), lines, page_state(b))
        self.assertIn("Entry 2 reverses entry 1", out)
        self.assertNotIn('class="struck"', out)

    def test_an_official_book_says_it_is_printed_into_the_regulators_book(self):
        out, _ = render(JO, "form_8", period("jo_pharmacy.form_8"), [])
        self.assertIn("Received from JFDA", out)


@NEED_JINJA
class NigeriaLayouts(unittest.TestCase):
    def test_part_a_prints_a_receipt(self):
        b = "ng_pharmacy.part_a_morphine"
        out, _ = render(NG, "part_a_morphine", period(b),
                        [row(book=b, item_class="NG Morphine", direction="In", kind="Receipt", item_name="Morphine 10 mg",
                             uom="Ampoule", counterparty="Wholesale Ltd", counterparty_address="2 Broad St, Lagos")])
        self.assertEqual(cells(out)[0], ["1", "Morphine 10 mg", "2026-10-20", "Wholesale Ltd", "2 Broad St, Lagos",
                                         "10", "Ampoule"])

    def test_part_b_prints_a_supply_with_the_authority_to_possess_and_the_ingredients(self):
        b = "ng_pharmacy.part_b_morphine"
        out, _ = render(NG, "part_b_morphine", period(b),
                        [row(book=b, item_class="NG Morphine", item_name="Morphine 10 mg", authority_no="RX-5",
                             authority_issuer="Dr. Okafor", detail_1="morphine sulphate 10 mg", uom="Ampoule")])
        self.assertEqual(cells(out)[0], ["1", "Morphine 10 mg", "2026-10-20", "A. Buyer", "1 Moi Avenue, Nairobi",
                                         "RX-5 · Dr. Okafor", "10", "Ampoule", "morphine sulphate 10 mg"])

    def test_the_door_s_own_words_never_print_as_the_buyer(self):
        b = "ng_pharmacy.part_b_morphine"
        out, _ = render(NG, "part_b_morphine", period(b),
                        [row(book=b, item_class="NG Morphine", remarks="below zero", booked_late=1,
                             entered_at="2026-10-21 08:00:00")])
        self.assertEqual(cells(out)[0][3], "A. Buyer")

    def test_a_nigerian_correction_is_a_dated_note_and_the_entry_stands(self):
        b = "ng_pharmacy.part_b_morphine"
        lines = [row(book=b, item_class="NG Morphine"),
                 line(2, book=b, item_class="NG Morphine", kind="Correction", direction="In", correction_of_number=1,
                      signed_by_name="P. Pharmacist", correction_note="address is 3 Broad St", entry_date="2026-10-22")]
        out, _ = render(NG, "part_b_morphine", period(b), lines)
        self.assertIn("Note dated 2026-10-22 to entry 1: address is 3 Broad St P. Pharmacist (entry 2).", out)  # reg. 18(1)(f)
        self.assertNotIn('class="struck"', out)
        self.assertEqual([r[0] for r in cells(out)], ["1", "2"])
        self.assertIn('<tr class="note"><td class="no">2</td>', out)


@NEED_JINJA
class FieldListLayouts(unittest.TestCase):
    def test_abu_dhabi_puts_a_dispensing_and_a_receipt_in_section_3_6s_columns(self):
        b = "ae_abu_dhabi_pharmacy.ph_20"
        out, _ = render(AE, "ph_20", period(b), [
            row(book=b, item_class="AE Narcotic", authority_no="RX-3", authority_issuer="Dr. Ali",
                authority_issuer_licence="DOH-1", dispenser_licence="PH-9", detail_1="1 tablet twice daily",
                detail_2="784-1980-1234567-1", balance=30),
            line(2, book=b, item_class="AE Narcotic", direction="In", kind="Receipt", counterparty="Supplier LLC",
                 reference_no="INV-2", balance=40)])
        self.assertEqual(cells(out)[0], ["1", "", "RX-3", "Tramadol 50 mg capsules", "1 tablet twice daily", "10 · Nos", "30",
                                         "Dr. Ali · DOH-1", "P. Pharmacist · PH-9", "A. Buyer · 1 Moi Avenue, Nairobi",
                                         "784-1980-1234567-1", "2026-10-20", "", "", ""])
        self.assertEqual(cells(out)[1], ["2", "", "", "Tramadol 50 mg capsules", "", "10 · Nos", "40", "", "", "", "", "",
                                         "Supplier LLC", "2026-10-20", "INV-2"])

    def test_ghana_prints_section_34s_four_particulars_with_two_signatures(self):
        b = "gh_pharmacy.dangerous_drugs_record"
        out, _ = render(GH, "dangerous_drugs_record", period(b), [row(book=b, item_class="GH Class A")])
        self.assertEqual(cells(out)[0], ["1", "Tramadol 50 mg capsules · 10 · Nos", "A. Buyer · 1 Moi Avenue, Nairobi",
                                         "P. Pharmacist", "2026-10-20"])
        self.assertEqual(out.count('class="cell mark"'), 2)

    def test_saudi_prints_batch_and_expiry_on_a_receipt_and_the_patient_on_a_dispensing(self):
        b = "sa_pharmacy.drug_register"
        common = dict(book=b, item="PHD-MORPH-10", item_name="Morphine sulfate injection 10 mg/ml 1 ml",
                      item_class="SA Narcotic", detail_1="45", detail_2="1012345678", detail_3="MRN-9")  # the ID from the customer
        lines = [row(**common, direction="In", kind="Receipt", qty=20, balance=20, batch_no="B-77",
                     expiry_date="2027-06-30", counterparty="NUPCO"),
                 line(2, **common, qty=1, balance=19, batch_no="B-77", authority_no="RX-11", authority_issuer="Dr. Saad",
                      counterparty="Patient S")]
        st = page_state(b, "PHD-MORPH-10", common["item_name"])
        out, _ = render(SA, "drug_register", period(b), lines, st)
        # (ب) the balance before the entry, which the door works out (the door's balance_before)
        self.assertEqual(cells(out)[0], ["1", "0", "20", "B-77", "2027-06-30", "NUPCO", "2026-10-20", "20", "", "", "", "", "",
                                         "", "", "", "", "", "20"])
        self.assertEqual(cells(out)[1], ["2", "20", "", "", "", "", "", "", "1", "B-77", "2026-10-20", "P. Pharmacist",
                                         "Patient S", "45", "1012345678", "MRN-9", "RX-11", "Dr. Saad", "19"])
        fix = line(3, **common, kind="Correction", direction="In", qty=0, balance=19, correction_of_number=2,
                   signed_by_name="X", correction_note="patient file 123")
        self.assertIn("Amended by entry 3", render(SA, "drug_register", period(b), lines + [fix], st)[0])

    def test_egypt_prints_article_18s_two_halves(self):
        b = "eg_pharmacy.received_dispensed"
        out, _ = render(EG, "received_dispensed", period(b),
                        [row(book=b, item_class="EG Schedule 1", direction="In", kind="Receipt", qty=10,
                             counterparty="Pharco", counterparty_address="Cairo"),
                         line(2, book=b, item_class="EG Schedule 1", qty=1, authority_issuer="Dr. Farid",
                              detail_1="Giza", detail_2="54", detail_3="331", counterparty="M. Hassan",
                              counterparty_address="Alexandria")])
        self.assertEqual(cells(out)[0], ["1", "", "2026-10-20", "Pharco · Cairo", "Tramadol 50 mg capsules", "10 · Nos",
                                         "", "", "", "", "", "", ""])
        self.assertEqual(cells(out)[1], ["2", "", "", "", "Tramadol 50 mg capsules", "", "Dr. Farid · Giza", "M. Hassan", "54",
                                         "Alexandria", "2026-10-20", "331", "1 · Nos"])

    def test_mexico_prints_article_117s_data_on_a_dispensing(self):
        b = "mx_pharmacy.fraccion_ii"
        out, _ = render(MX, "fraccion_ii", period(b),
                        [row(book=b, item_name="Clonazepam 2 mg", item_class="MX Fraccion II", authority_no="F-0042",
                             authority_date="2026-10-18", authority_issuer="Dra. Ruiz", authority_issuer_licence="CP 123456",
                             detail_1="1 diaria", detail_2="Av. Juárez 10", balance=28)], page_state(b))
        self.assertEqual(cells(out)[0], ["1", "", "", "", "F-0042", "2026-10-18", "Clonazepam 2 mg", "10", "1 diaria", "28",
                                         "Dra. Ruiz · Av. Juárez 10 · CP 123456", "2026-10-20"])

if __name__ == "__main__":
    unittest.main()
