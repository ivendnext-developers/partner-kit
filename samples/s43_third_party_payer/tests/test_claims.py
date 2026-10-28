"""S43's claims (claims.py) and data sets (dataset.py): a claim from a booked sale, the claims file, the claim's flow,
the remittance, and a second payer of another kind that loads and answers with no code change.

    python3 -m unittest discover -s samples/s43_third_party_payer/tests -p 'test_*.py'
"""

import csv
import io
import os
import sys
import unittest
from decimal import Decimal

SAMPLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SAMPLE)
import claims as K  # noqa: E402
import copay as C  # noqa: E402
import dataset  # noqa: E402

GEN = dataset.load("datasets/generic_insurer.json")
PAYER = {"code": "GEN-INS", "needs_member_number": 1, "needs_prescription": 1}
MEMBER = {"name": "M1", "customer": "C1", "plan": "Generic Silver", "member_number": "GEN-000123", "card_serial": "",
          "policy_number": "POL-9", "active": 1}


def plan_from(ds, title):
    """The plan as the service resolves it: the data set's plan, its formulary's rows in place of the name."""
    recs = dataset.records(ds)
    p = next(r for r in recs if r["doctype"].endswith("Plan") and r["title"] == title)
    p = dict(p, name=title)
    forms = {r["title"]: r["rows"] for r in recs if r["doctype"].endswith("Formulary")}
    p["formulary"] = forms.get(p.get("formulary"), [])
    return p


def booked(answer, **kw):
    """A sale as the payer door books it (payer.md §4b): each line's payer share is the coverage answer's."""
    s = {"doctype": "POS Invoice", "name": "PHD-26-0001", "posting_date": "2026-10-23", "store": "Pharmacy Dispensary",
         "customer": "C1", "claim_ref": answer["claim_ref"], "payer": "GEN-INS", "plan": answer["plan"],
         "member": "M1", "prescription": "RX-77", "prescriber": "Dr A", "prescriber_licence": "L-1",
         "lines": [dict(l, qty=l.get("covered_qty"), amount=str(Decimal(l["payer_share"]) + Decimal(l["patient_share"])),
                        gtin="0612345678901", uom="Nos") for l in answer["lines"]]}
    s.update(kw)
    return s


SALE = {"sale_ref": "PHD-26-0001", "customer": "C1", "date": "2026-10-23", "precision": 2,
        "lines": [dict(line_id="1", item_code="PHD-AMOX-500", item_group="Prescription Medicines", qty=2,
                       amount=240, discount=0),
                  dict(line_id="2", item_code="PHD-PARA-500", item_group="Over-the-Counter Medicines", qty=2,
                       amount=50, discount=0)]}
PRICES = {"PHD-AMOX-500": 120, "PHD-PARA-500": 25}


def answer(**kw):
    return C.coverage(dict(SALE, **kw), plan_from(GEN, "Generic Silver"), MEMBER, False, PRICES,
                      {"title": "Generic Insurer", "active": 1})


class DataSets(unittest.TestCase):
    def test_every_data_set_passes_its_check(self):
        for name in os.listdir(os.path.join(SAMPLE, "datasets")):
            self.assertEqual(dataset.check(dataset.load(os.path.join("datasets", name))), [], name)

    def test_the_generic_insurer_answers_a_sale(self):
        a = answer()
        self.assertEqual(a["answer"], "cover")
        # silver: 20% of the covered amount before the discount; OTC extra-item pay 2 a unit
        self.assertEqual((a["totals"]["payer_share"], a["totals"]["patient_share"]), ("228.80", "61.20"))

    def test_a_company_paying_for_its_staff_loads_and_answers_with_no_code_change(self):
        corp = dataset.load("datasets/corporate_account.json")
        p = plan_from(corp, "Acme Staff 70")
        member = dict(MEMBER, plan="Acme Staff 70")
        a = C.coverage(dict(SALE, lines=SALE["lines"] + [dict(line_id="3", item_code="SHAMPOO", item_group="Health",
                                                               qty=1, amount=3000, discount=0)]),
                       p, member, False, None, {"title": "Acme Ltd (staff purchases)", "active": 1})
        self.assertEqual(a["answer"], "cover")
        # every item covered; 3,290 is over the 2,000 limit: 70% of 2,000 is the company's, the rest the employee's
        self.assertEqual((a["totals"]["payer_share"], a["totals"]["patient_share"]), ("1400.00", "1890.00"))

    def test_a_broken_data_set_is_refused_in_words(self):
        bad = dict(GEN, plans=[dict(GEN["plans"][0], formulary="Nope", copay_percent=150, colour="red")])
        msgs = dataset.check(bad)
        self.assertTrue(any("formulary the data set does not have" in m for m in msgs))
        self.assertTrue(any("between 0 and 100" in m for m in msgs))
        self.assertTrue(any("keys the format does not know" in m for m in msgs))


class BuildClaim(unittest.TestCase):
    def test_a_claim_carries_the_booked_lines_the_payer_pays_part_of(self):
        c = K.build_claim(booked(answer()), PAYER, MEMBER)
        self.assertEqual((c["name"], c["status"], c["payer_share"]), ("GEN-INS-PHD-26-0001", "Ready", "228.80"))
        self.assertEqual([l["line_id"] for l in c["lines"]], ["1", "2"])
        self.assertEqual(c["member_number"], "GEN-000123")

    def test_a_line_the_payer_pays_nothing_of_is_not_on_the_claim(self):
        a = answer()
        a["lines"][1].update(payer_share="0", patient_share="50.00")
        self.assertEqual([l["line_id"] for l in K.build_claim(booked(a), PAYER, MEMBER)["lines"]], ["1"])

    def test_a_claim_missing_what_its_payer_needs_is_incomplete(self):
        c = K.build_claim(booked(answer(), prescription=None), PAYER, dict(MEMBER, member_number=None))
        self.assertEqual(c["status"], "Incomplete")
        self.assertEqual(c["incomplete_reason"], "the member number; the prescription")

    def test_gtin_dose_and_frequency_are_asked_only_where_the_payer_needs_them(self):
        payer = dict(PAYER, needs_gtin=1, needs_dose_frequency=1)
        a = answer()
        sale = booked(a)
        sale["lines"][0]["gtin"] = ""
        c = K.build_claim(sale, payer, MEMBER)
        self.assertIn("the GTIN of line 1 (PHD-AMOX-500)", c["incomplete_reason"])
        self.assertIn("the dose and frequency of line 2 (PHD-PARA-500)", c["incomplete_reason"])
        self.assertEqual(K.build_claim(booked(a), PAYER, MEMBER)["status"], "Ready")


class ClaimsFile(unittest.TestCase):
    def test_one_row_per_line_of_each_ready_claim(self):
        ready = K.build_claim(booked(answer()), PAYER, MEMBER)
        inc = K.build_claim(booked(answer(sale_ref="X2"), claim_ref="GEN-INS-X2", prescription=None), PAYER, MEMBER)
        rows = list(csv.DictReader(io.StringIO(K.claims_file([ready, inc], PAYER))))
        self.assertEqual([(r["claim_ref"], r["line"]) for r in rows], [("GEN-INS-PHD-26-0001", "1"),
                                                                       ("GEN-INS-PHD-26-0001", "2")])
        self.assertEqual(sum(Decimal(r["payer_share"]) for r in rows), Decimal("228.80"))

    def test_a_cell_never_runs_as_a_formula(self):
        c = K.build_claim(booked(answer(), prescriber="=HYPERLINK(1)"), PAYER, MEMBER)
        self.assertIn("'=HYPERLINK(1)", K.claims_file([c], PAYER))

    def test_a_claim_is_returned_when_the_payer_is_owed_nothing_whatever_the_units(self):
        c = K.build_claim(booked(answer()), PAYER, MEMBER)
        lines = [{"line_id": l["line_id"], "qty": "1", "payer_back": l["payer_share"]} for l in c["lines"]]
        K.apply_return(c, {"lines": lines})                 # a box of ten back counted as one: the money decides
        self.assertEqual((c["payer_share"], c["status"]), ("0.00", "Returned"))

    def test_a_returned_line_leaves_the_file(self):
        c = K.build_claim(booked(answer()), PAYER, MEMBER)
        split = C.return_split(c["lines"], [{"line_id": "2", "qty": 2}])
        K.apply_return(c, split)
        rows = list(csv.DictReader(io.StringIO(K.claims_file([c], PAYER))))
        self.assertEqual([r["line"] for r in rows], ["1"])
        self.assertEqual(c["payer_share"], rows[0]["payer_share"])


class Flow(unittest.TestCase):
    def claim(self):
        return K.build_claim(booked(answer()), PAYER, MEMBER)

    def test_submitted_rejected_corrected_resubmitted_paid(self):
        c = self.claim()
        for to, why in ((K.SUBMITTED, {}), (K.REJECTED, {"reason": "member number unknown"}), (K.READY, {}),
                        (K.filed_as(c), {}), (K.PAID, {})):
            K.move(c, to, **why)
        self.assertEqual((c["status"], c["resubmissions"], c["rejection_reason"]), ("Paid", 1, "member number unknown"))

    def test_a_rejected_claim_billed_back_to_the_patient_owes_the_whole_payer_share(self):
        c = self.claim()
        K.move(c, K.SUBMITTED)
        K.move(c, K.REJECTED, reason="not covered on the date")
        K.move(c, K.BILLED)
        self.assertEqual((c["status"], c["billed_back"]), ("Billed to patient", "228.80"))

    def test_a_short_paid_claim_bills_back_only_the_difference(self):
        c = self.claim()
        K.move(c, K.SUBMITTED)
        c["received"] = "200.00"
        K.move(c, K.SHORT)
        K.move(c, K.BILLED)
        self.assertEqual(c["billed_back"], "28.80")

    def test_moves_the_flow_does_not_allow_are_refused_in_words(self):
        c = self.claim()
        with self.assertRaisesRegex(ValueError, "Ready cannot become Paid"):
            K.move(c, K.PAID)
        K.move(c, K.SUBMITTED)
        with self.assertRaisesRegex(ValueError, "keeps the payer's reason"):
            K.move(c, K.REJECTED)
        with self.assertRaisesRegex(ValueError, "not a claim status"):
            K.move(c, "Lost")

    def test_an_incomplete_claim_becomes_ready_only_once_complete(self):
        c = K.build_claim(booked(answer(), prescription=None), PAYER, MEMBER)
        with self.assertRaisesRegex(ValueError, "still lacks: the prescription"):
            K.move(c, K.READY, payer=PAYER)
        c["prescription"] = "RX-77"
        self.assertEqual(K.move(c, K.READY, payer=PAYER)["status"], "Ready")


class Settle(unittest.TestCase):
    def claim(self):
        c = K.build_claim(booked(answer()), PAYER, MEMBER)
        return K.move(c, K.SUBMITTED)

    def test_two_lines_of_one_claim_summed_pay_it(self):
        c = self.claim()
        self.assertEqual(K.settle(c, Decimal("228.80")), "Paid")
        self.assertEqual(c["received"], "228.80")

    def test_part_then_the_rest(self):
        c = self.claim()
        self.assertEqual(K.settle(c, 100), "Short paid")
        self.assertEqual(K.settle(c, 50), "Short paid (still 78.80 due)")
        self.assertEqual(K.settle(c, "78.80"), "Paid")
        self.assertEqual(c["received"], "228.80")

    def test_a_rejection_keeps_its_reason_and_records_nothing_received(self):
        c = self.claim()
        self.assertEqual(K.settle(c, 0, True, "card expired"), "Rejected")
        self.assertEqual((c["rejection_reason"], c["received"]), ("card expired", "0"))

    def test_money_on_a_claim_the_flow_cannot_move_is_kept_and_flagged(self):
        c = K.build_claim(booked(answer()), PAYER, MEMBER)          # Ready: never filed
        self.assertEqual(K.settle(c, 10), "Short paid recorded on a claim that is Ready: check it")
        self.assertEqual(c["received"], "10")

    def test_more_than_was_due_is_said(self):
        c = self.claim()
        self.assertEqual(K.settle(c, 300), "Paid (paid more than was due)")


class Remittance(unittest.TestCase):
    def test_expected_against_received(self):
        a = K.build_claim(booked(answer()), PAYER, MEMBER)
        b = K.build_claim(booked(answer(sale_ref="S2"), claim_ref="GEN-INS-S2", name="S2"), PAYER, MEMBER)
        c = K.build_claim(booked(answer(sale_ref="S3"), claim_ref="GEN-INS-S3", name="S3"), PAYER, MEMBER)
        got = K.match_remittance([{"claim_ref": a["claim_ref"], "paid": "228.80"},
                                  {"claim_ref": b["claim_ref"], "paid": "200"},
                                  {"claim_ref": c["claim_ref"], "paid": "0", "rejected": 1, "reason": "expired"},
                                  {"claim_ref": "GEN-INS-NOPE", "paid": "10"}],
                                 {x["claim_ref"]: x for x in (a, b, c)})
        self.assertEqual([g["result"] for g in got], ["Paid", "Short paid", "Rejected", "Unmatched"])
        self.assertEqual(got[1]["difference"], "28.80")

    def test_a_payment_over_what_is_due_is_flagged(self):
        a = K.build_claim(booked(answer()), PAYER, MEMBER)
        self.assertEqual(K.match_remittance([{"claim_ref": a["claim_ref"], "paid": "300"}],
                                            {a["claim_ref"]: a})[0]["result"], "Over paid")


if __name__ == "__main__":
    unittest.main()
