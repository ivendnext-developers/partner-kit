"""S11 is one workflow on the customer's Purchase Order and nothing else: no service, no record type, no key.

    python3 -m unittest discover -s samples/s11_approvals/tests -p 'test_*.py'

The kit's checker takes the manifest, and these tests hold what the page promises: approving submits the order, the amount
decides who may act, and mail is on. An app made from this sample keeps these tests, so change the amount here when you change
it in the manifest.
"""
import json
import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools" / "manifest"))
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text("utf-8"))
FLOW = MANIFEST["workflows"][0]


def moves(state):
    return {t["action"]: t for t in FLOW["transitions"] if t["state"] == state}


class Manifest(unittest.TestCase):
    def test_the_checker_takes_it(self):
        self.assertEqual(validate.validate(MANIFEST), [])

    def test_it_is_only_a_workflow_on_the_customers_purchase_order(self):
        self.assertEqual(FLOW["document_type"], "Purchase Order")
        kinds = set(MANIFEST) - {"manifest_version", "app", "prefix", "title", "version", "publisher", "description"}
        self.assertEqual(kinds, {"workflows"})

    def test_mail_goes_to_whoever_acts_next(self):
        self.assertEqual(FLOW["send_email_alert"], 1)


class TheFlow(unittest.TestCase):
    def test_approving_submits_and_cancelling_cancels(self):
        status = {s["state"]: s["doc_status"] for s in FLOW["states"]}
        self.assertEqual(status[moves("Draft")["Approve"]["next_state"]], 1)
        self.assertEqual(status[moves("Approved")["Cancel"]["next_state"]], 2)

    def test_the_approver_acts_over_the_amount_and_the_buyer_at_or_under_it(self):
        draft = moves("Draft")
        limit = re.fullmatch(r"doc\.grand_total > (\d+)", draft["Approve"]["condition"]).group(1)
        self.assertEqual(draft["Approve"]["allowed"], "Purchase Manager")
        self.assertEqual(draft["Reject"]["condition"], f"doc.grand_total > {limit}")
        self.assertEqual(draft["Submit"]["allowed"], "Purchase User")
        self.assertEqual(draft["Submit"]["condition"], f"doc.grand_total <= {limit}")

    def test_a_rejected_order_goes_back_to_the_buyer(self):
        self.assertEqual(moves("Rejected")["Review"]["next_state"], "Draft")
        self.assertEqual(moves("Rejected")["Review"]["allowed"], "Purchase User")


if __name__ == "__main__":
    unittest.main()
