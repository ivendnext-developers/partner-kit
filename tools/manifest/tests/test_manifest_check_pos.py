# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_pos.py,
# at development 8851258321b3b8c1aae565ff88cd7ca1f0c0404d; two lines changed: the import (the kit's copy of the checker is
# validate.py) and the fixture folder. A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""The checker's POS changes (the package installer), stdlib only, no bench — the file the kit copies with
the checker so both refuse the same manifests (Partner row DEPLOY). Each rule: refused with its own words,
and its lawful neighbour accepted."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import (  # noqa: E402
    NOTIFY_CONDITION_REASON,
    NOTIFY_FIELD_REASON,
    VERSION_REASON,
    validate,
    version_key,
)

HERE = pathlib.Path(__file__).resolve().parent
FULL = json.loads((HERE / "fixtures/full_ok.json").read_text())


def planted(change):
    m = copy.deepcopy(FULL)
    change(m)
    return [r["reason"] for r in validate(m)]


def user_field(m, fieldname="owner_user"):
    m["doctypes"][1]["fields"].append(
        {"fieldname": fieldname, "fieldtype": "Link", "label": "Owner", "options": "User"}
    )


class PosChanges(unittest.TestCase):
    def test_the_fixture_itself_is_clean(self):
        self.assertEqual(validate(FULL), [])

    def test_the_version_is_required_as_major_minor_patch(self):
        for bad in (None, "1.0", "v1.0.0", "01.0.0", "1.0.0-beta", 1):

            def plant(m, bad=bad):
                m.pop("version") if bad is None else m.update(version=bad)

            self.assertIn(VERSION_REASON, planted(plant), bad)
        self.assertLess(version_key("1.9.0"), version_key("1.10.0"))

    def test_a_notification_or_recipient_condition_is_refused(self):
        self.assertEqual(
            planted(lambda m: m["notifications"][0].update(condition="doc.title")),
            [NOTIFY_CONDITION_REASON],
        )
        self.assertEqual(
            planted(lambda m: m["notifications"][0]["recipients"][0].update(condition="1")),
            [NOTIFY_CONDITION_REASON],
        )

    def test_a_recipient_field_must_be_a_link_to_user(self):
        def data_field(m):
            m["doctypes"][1]["fields"].append(
                {"fieldname": "contact", "fieldtype": "Data", "label": "Contact"}
            )
            m["notifications"][0]["recipients"].append({"receiver_by_document_field": "contact"})

        self.assertEqual(planted(data_field), [NOTIFY_FIELD_REASON])

        def user(m):
            user_field(m)
            m["notifications"][0]["recipients"].append(
                {"receiver_by_document_field": "owner_user"}
            )

        self.assertEqual(planted(user), [])
        for std in ("owner", "modified_by"):  # the framework fills these with a user itself
            self.assertEqual(
                planted(
                    lambda m, f=std: m["notifications"][0]["recipients"].append(
                        {"receiver_by_document_field": f}
                    )
                ),
                [],
            )

        def in_rows(m):  # 'field,table': the field on the table's rows
            m["doctypes"][0]["fields"].append(
                {"fieldname": "who", "fieldtype": "Link", "label": "Who", "options": "User"}
            )
            m["notifications"][0]["recipients"].append({"receiver_by_document_field": "who,lines"})

        self.assertEqual(planted(in_rows), [])

        def wrong_table(m):  # the table named is not the one holding the field
            user_field(m)
            m["notifications"][0]["recipients"].append(
                {"receiver_by_document_field": "owner_user,lines"}
            )

        self.assertEqual(planted(wrong_table), [NOTIFY_FIELD_REASON])

    def test_the_framework_under_its_other_names_is_refused_in_a_message(self):
        for word in ("iVendFramework.get_all('Customer')", "FrappeClient('x')", "FRAPPE.db"):
            self.assertTrue(
                planted(lambda m, w=word: m["notifications"][0].update(message="{{ " + w + " }}")),
                word,
            )

    def test_a_webhook_condition_on_its_own_record_type_stays_allowed(self):
        # measured: the framework evaluates a webhook condition with the record and the date
        # helpers only (webhook.get_context), never the database — unlike a notification's
        self.assertEqual(validate(FULL), [])
        self.assertTrue(FULL["webhooks"][0].get("condition"))


if __name__ == "__main__":
    unittest.main()
