"""S11 is one workflow on the customer's Purchase Order. An app made from it keeps these tests, so they hold what the sample
promises and leave what you change alone: the amount, the roles, and anything you add to the manifest.

    python3 -m unittest discover -s samples/s11_approvals/tests -p 'test_*.py'
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
STATUS = {s["state"]: s["doc_status"] for s in FLOW["states"]}


def moves(state):
    return {t["action"]: t for t in FLOW["transitions"] if t["state"] == state}


class S11(unittest.TestCase):
    def test_the_checker_takes_it(self):
        self.assertEqual(validate.validate(MANIFEST), [])

    def test_approving_submits_and_cancelling_cancels(self):
        self.assertEqual(STATUS[moves("Draft")["Approve"]["next_state"]], 1)
        self.assertEqual(STATUS[moves("Approved")["Cancel"]["next_state"]], 2)

    def test_the_person_who_raised_an_order_may_submit_it_but_not_approve_it(self):
        self.assertEqual(moves("Draft")["Submit"]["allow_self_approval"], 1)
        self.assertFalse(moves("Draft")["Approve"].get("allow_self_approval"))

    def test_every_state_a_move_names_is_a_state(self):
        for t in FLOW["transitions"]:
            self.assertIn(t["state"], STATUS)
            self.assertIn(t["next_state"], STATUS)

    def test_the_amount_is_the_same_on_each_action_that_names_one(self):
        amounts = {n for t in FLOW["transitions"] for n in re.findall(r"\d[\d.]*", t.get("condition") or "")}
        self.assertLessEqual(len(amounts), 1, amounts)


if __name__ == "__main__":
    unittest.main()
