"""The settings record drives the shop's rules (service/settings_sync.py): the values are copied into the records they
name, a replay writes nothing, and a notification's role rows are kept."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(os.path.dirname(HERE), "service")]
import settings_sync as S  # noqa: E402

LINKS = [{"from": "max_redemption_percent", "record_type": "Retail Save Rule", "record": "PP LYL Redemption cap", "field": "value"},
         {"from": "approver_emails", "record_type": "Notification", "record": "PP LYL Big redemption", "recipients": True}]


class Shop:
    def __init__(self):
        self.db = {("Retail Save Rule", "PP LYL Redemption cap"): {"value": "50"},
                   ("Notification", "PP LYL Big redemption"): {"recipients": [{"receiver_by_role": "Sales Manager"}, {"cc": "old@shop.example"},
                                                                              {"receiver_by_role": "Accounts Manager", "cc": "audit@shop.example"}]}}
        self.writes = []

    def get(self, dt, name):
        return dict(self.db[(dt, name)])

    def update(self, dt, name, body):
        self.writes.append((dt, name, body))
        self.db[(dt, name)].update(body)


class Sync(unittest.TestCase):
    def test_the_values_reach_the_records_they_name_and_a_replay_writes_nothing(self):
        t = Shop()
        settings = {"max_redemption_percent": 30, "approver_emails": "a@shop.example\nb@shop.example"}
        done = S.sync(t, settings, LINKS)
        self.assertEqual([(d, n) for d, n, _ in done], [("Retail Save Rule", "PP LYL Redemption cap"), ("Notification", "PP LYL Big redemption")])
        self.assertEqual(t.db[("Retail Save Rule", "PP LYL Redemption cap")]["value"], 30)
        rec = t.db[("Notification", "PP LYL Big redemption")]["recipients"]
        self.assertEqual(rec, [{"receiver_by_role": "Sales Manager"}, {"receiver_by_role": "Accounts Manager", "cc": "audit@shop.example"},
                               {"cc": "a@shop.example"}, {"cc": "b@shop.example"}], "a row with a role and a cc is a person's, and kept")
        self.assertEqual(S.sync(t, settings, LINKS), [], "a replayed event wrote again")

    def test_a_link_to_a_record_that_is_not_there_says_so(self):
        with self.assertRaises(LookupError):
            S.plan({"x": 1}, [{"from": "x", "record_type": "Retail Save Rule", "record": "gone", "field": "value"}], {})


if __name__ == "__main__":
    unittest.main()
