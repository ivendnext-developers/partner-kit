"""Roles the framework gives every user by itself may not appear in a manifest. Stdlib only:
python3 -m unittest discover -s tools/manifest/tests -v

`All` is held by every signed-in user (website customers included), `Desk User` by every staff user, `Administrator` is the built-in superuser
(framework `permissions.py` AUTOMATIC_ROLES; a row for one reaches users the shop's administrator never chose for the partner's records).
The checker already refused `Guest`; this is the same refusal for the rest, at the five places a manifest names a role the shop's users hold
(a notification's `receiver_by_role` is the sixth, tested in test_validate_notification_role.py). The database finds a role without regard to case or a trailing space,
so a role written `all` or `Guest ` is stored as the real one (measured on our test bench): the spellings are refused too."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

V1 = json.loads((HERE / "fixtures/full_ok.json").read_text())
V2 = json.loads((HERE / "fixtures/full_v2_ok.json").read_text())
NINE = ("read", "write", "create", "delete", "report", "export", "share", "print", "email")
AUTOMATIC = ("All", "Desk User", "Administrator")
SPELLED = ("all", "ALL", "All ", "desk user", "administrator")   # the same roles, as the database finds them (ar_case.json)


def row(role):
    return {"role": role, **{x: 0 for x in NINE}, "read": 1}


def permission_row(role):
    m = copy.deepcopy(V1)
    m["doctypes"][1].setdefault("permissions", []).append(row(role))
    return validate(m)


def report_role(role):
    m = copy.deepcopy(V2)
    m["reports"][0]["roles"].append(role)
    return validate(m)


def chart_role(role):
    m = copy.deepcopy(V2)
    m["dashboard_charts"][0]["roles"] = [role]
    return validate(m)


def state_role(role):
    m = copy.deepcopy(V2)
    m["workflows"][0]["states"][0]["allow_edit"] = role
    return validate(m)


def transition_role(role):
    m = copy.deepcopy(V2)
    m["workflows"][0]["transitions"][0]["allowed"] = role
    return validate(m)


SITES = {"a permission row": permission_row, "a report's roles": report_role, "a chart's roles": chart_role,
         "a workflow state's allow_edit": state_role, "a workflow transition's allowed": transition_role}


class AutomaticRoles(unittest.TestCase):
    def test_the_fixtures_themselves_are_clean(self):
        self.assertEqual(validate(copy.deepcopy(V1)), [])
        self.assertEqual(validate(copy.deepcopy(V2)), [])

    def test_a_role_every_user_holds_is_refused_once_at_each_place_a_role_is_named(self):
        for site, make in SITES.items():
            for role in AUTOMATIC:
                with self.subTest(site=site, role=role):
                    r = make(role)
                    self.assertEqual(len(r), 1, r)
                    self.assertIn("by itself", r[0]["reason"])
                    self.assertNotIn("not signed in", r[0]["reason"])

    def test_the_same_roles_written_in_another_case_or_with_a_trailing_space_are_refused_too(self):
        for site, make in SITES.items():
            for role in SPELLED:
                with self.subTest(site=site, role=role):
                    r = make(role)
                    self.assertEqual(len(r), 1, r)
                    self.assertIn("by itself", r[0]["reason"])

    def test_a_role_with_an_accent_or_a_hidden_character_is_refused_at_each_place(self):
        # measured on our test bench: the database stored these as All, Guest, Desk User, Administrator
        for site, make in SITES.items():
            for role in ("\u00c0ll", "Gu\u00e8st", "D\u00e9sk User", "Admin\u00efstrator", "Al\u200bl", "A\x01ll", " Retail Manager"):
                with self.subTest(site=site, role=role):
                    r = make(role)
                    self.assertEqual(len(r), 1, r)
                    self.assertIn("plain letters", r[0]["reason"])

    def test_the_visitor_role_in_another_spelling_is_refused_at_each_place(self):
        for site, make in SITES.items():
            for role in ("guest", "GUEST", "Guest "):
                with self.subTest(site=site, role=role):
                    r = make(role)
                    self.assertEqual(len(r), 1, r)
                    self.assertNotIn("by itself", r[0]["reason"])

    def test_the_visitor_row_still_gets_its_one_visitor_refusal(self):
        r = permission_row("Guest")
        self.assertEqual(len(r), 1, r)
        self.assertIn("not signed in", r[0]["reason"])

    def test_a_role_the_shop_hands_out_still_passes_at_each_place(self):
        for site, make in SITES.items():
            with self.subTest(site=site):
                self.assertEqual(make("Retail Manager"), [])


if __name__ == "__main__":
    unittest.main()
