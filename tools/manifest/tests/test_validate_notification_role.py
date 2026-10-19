"""A notification's recipient role is refused the same way as the other five places a manifest names a role. Stdlib only:
python3 -m unittest discover -s tools/manifest/tests -v

Row 10i made the checker refuse `Guest`, `All`, `Desk User` and `Administrator` (and their odd spellings) at five places; a notification's
`recipients[].receiver_by_role` is the sixth. It reuses 10i's helper (`_roles`), so the rule is one rule: the same four roles, the same
spellings, the same plain-ASCII bound (what a notification to each of them reaches on our test bench)."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

V1 = json.loads((HERE / "fixtures/full_ok.json").read_text())
AUTOMATIC = ("All", "Desk User", "Administrator")
SPELLED = ("all", "ALL", "All ", "desk user", "administrator")   # as the database finds them (measured)
ODD = ("Àll", "Guèst", "Désk User", "Adminïstrator", "Al​l", "A\x01ll", " Retail Manager")


def notify_role(role):
    m = copy.deepcopy(V1)
    m["notifications"][0]["recipients"] = [{"receiver_by_role": role}]
    return validate(m)


class NotificationRecipientRole(unittest.TestCase):
    def test_the_fixture_itself_is_clean(self):
        self.assertEqual(validate(copy.deepcopy(V1)), [])

    def test_a_role_every_user_holds_is_refused_once(self):
        for role in AUTOMATIC:
            with self.subTest(role=role):
                r = notify_role(role)
                self.assertEqual(len(r), 1, r)
                self.assertIn("by itself", r[0]["reason"])
                self.assertIn("recipients[0]", r[0]["where"])

    def test_the_same_roles_in_another_case_or_with_a_trailing_space_are_refused_once(self):
        for role in SPELLED:
            with self.subTest(role=role):
                r = notify_role(role)
                self.assertEqual(len(r), 1, r)
                self.assertIn("by itself", r[0]["reason"])

    def test_the_visitor_role_is_refused_once_in_any_spelling(self):
        for role in ("Guest", "guest", "GUEST", "Guest "):
            with self.subTest(role=role):
                r = notify_role(role)
                self.assertEqual(len(r), 1, r)
                self.assertIn("not signed in", r[0]["reason"])

    def test_an_accent_or_a_hidden_character_is_refused_once(self):
        for role in ODD:
            with self.subTest(role=role):
                r = notify_role(role)
                self.assertEqual(len(r), 1, r)
                self.assertIn("plain letters", r[0]["reason"])

    def test_only_the_bad_recipient_is_refused_and_a_shop_role_still_passes(self):
        self.assertEqual(notify_role("Retail Manager"), [])
        m = copy.deepcopy(V1)
        m["notifications"][0]["recipients"] = [{"receiver_by_role": "Retail Manager"}, {"receiver_by_role": "All"},
                                               {"receiver_by_document_field": "owner"}]
        r = validate(m)
        self.assertEqual(len(r), 1, r)
        self.assertIn("recipients[1]", r[0]["where"])

    def test_an_empty_recipient_role_the_framework_ignores_is_not_refused(self):
        for empty in (None, ""):
            with self.subTest(empty=empty):
                m = copy.deepcopy(V1)
                m["notifications"][0]["recipients"] = [{"receiver_by_role": empty, "receiver_by_document_field": "owner"}]
                self.assertEqual(validate(m), [])


if __name__ == "__main__":
    unittest.main()
