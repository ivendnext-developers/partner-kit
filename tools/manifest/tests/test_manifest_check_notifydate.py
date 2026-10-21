# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_notifydate.py,
# at development 7d47d331a203fd8b2794f83270a4190b3c1908e8; changed: the import, the fixture folder, a note on how the file is copied (removed), and one refused message that named the framework's own date helper (now another helper: the call is refused either way).
# A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""A notification on a shop's own record type: only Days Before or Days After a date, to a role, with plain text and
{{ doc.<field> }} only. Stdlib only.

The framework's save runs only the notifications whose event is that save's own (New, Save, Submit, Cancel, Value
Change, a method); the two date events match none and are sent by the daily scheduler. Everything else on a shop's
type stays refused. The installer checks what the checker has no meta for (a table or single-record type, and
date_changed a Date or Datetime field): test_manifest_notifydate.py."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent

V1 = json.loads((HERE / "fixtures/full_ok.json").read_text())
EXPIRY = {
    "name": "PP TST Batch Expiry",
    "document_type": "Batch",
    "event": "Days Before",
    "days_in_advance": 30,
    "date_changed": "expiry_date",
    "channel": "Email",
    "subject": "Batch {{ doc.name }} of {{ doc.item }} expires on {{ doc.expiry_date }}",
    "message": "Batch {{doc.name}} ({{ doc.item_name }}) expires on {{ doc.expiry_date }}. Check the shelf.",
    "recipients": [{"receiver_by_role": "Stock Manager"}],
}


def with_expiry(**change):
    m = copy.deepcopy(V1)
    n = dict(EXPIRY, **change)
    for k in [k for k, v in change.items() if v is None]:
        n.pop(k)
    m["notifications"].append(n)
    return validate(m)


def reasons(r):
    return " | ".join(x["reason"] for x in r)


class DateNotificationOnAShopType(unittest.TestCase):
    def test_days_before_on_a_batch_expiry_by_role_passes_by_email_and_by_the_bell(self):
        self.assertEqual(with_expiry(), [])
        self.assertEqual(with_expiry(channel="System Notification"), [])
        self.assertEqual(with_expiry(event="Days After", days_in_advance=1), [])
        self.assertEqual(with_expiry(days_in_advance=365), [])

    def test_any_other_event_on_a_shop_type_is_still_refused(self):
        for event in ("New", "Save", "Submit", "Cancel", "Value Change"):
            with self.subTest(event=event):
                r = with_expiry(event=event)
                self.assertEqual(len(r), 1, r)
                self.assertIn("may only be Days Before or Days After a date", r[0]["reason"])
                self.assertIn("runs inside every save of it", r[0]["reason"])

    def test_days_in_advance_is_one_to_365(self):
        for days in (0, 366, -1, None, True, 1.5, "30"):
            with self.subTest(days=days):
                r = with_expiry(days_in_advance=days)
                self.assertEqual(len(r), 1, r)
                self.assertIn(
                    "days_in_advance is a whole number of days from 1 to 365", r[0]["reason"]
                )

    def test_date_changed_is_a_field_name(self):
        for value in (None, "", "Expiry Date", 7):
            with self.subTest(value=value):
                r = with_expiry(date_changed=value)
                self.assertEqual(len(r), 1, r)
                self.assertIn("date_changed names the record's date field", r[0]["reason"])

    def test_setting_a_field_after_it_is_sent_is_refused(self):
        r = with_expiry(set_property_after_alert="disabled", property_value="1")
        self.assertEqual(len(r), 1, r)
        self.assertIn("saves the shop's record from the scheduler", r[0]["reason"])
        r = with_expiry(property_value="1")
        self.assertEqual(len(r), 1, r)

    def test_a_condition_is_refused(self):
        r = with_expiry(condition="doc.batch_qty > 0")
        self.assertIn("a manifest carries none", reasons(r))

    def test_a_recipient_by_a_field_of_the_shop_record_is_refused_even_owner(self):
        for field in ("owner", "modified_by", "supplier"):
            with self.subTest(field=field):
                r = with_expiry(recipients=[{"receiver_by_document_field": field}])
                self.assertEqual(len(r), 1, r)
                self.assertIn("goes to a role", r[0]["reason"])

    def test_a_filters_key_is_refused_this_framework_has_no_filters_condition(self):
        r = with_expiry(filters=[["batch_qty", ">", 0]])
        self.assertEqual(len(r), 1, r)
        self.assertIn("keys a manifest notification may not set: ['filters']", r[0]["reason"])

    def test_a_message_with_a_call_a_filter_a_block_or_a_comment_is_refused(self):
        for text in (
            "{{ doc.get_formatted('expiry_date') }}",
            "{{ doc.expiry_date | string }}",
            "{{ formatdate(doc.expiry_date) }}",
            "{% if doc.batch_qty %}left{% endif %}",
            "{# note #}",
            "{{ nowdate() }}",
            "{{ doc }}",
            "{{ doc.__class__ }}",
            "{{ doc.item.upper }}",
            "{{- doc.name -}}",
            "templates/emails/new_message.html",  # read as a template file (guess_is_path)
            "see the list in stock.txt",
        ):
            for key in ("subject", "message"):
                with self.subTest(text=text, key=key):
                    r = with_expiry(**{key: text})
                    self.assertTrue(r, text)
                    self.assertIn("plain text and {{ doc.<field> }} only", reasons(r))

    def test_a_sentence_ending_in_a_full_stop_or_on_two_lines_is_plain_text(self):
        self.assertEqual(
            with_expiry(message="Batch {{ doc.name }} expires. Check stock.txt\nand the shelf."),
            [],
        )
        self.assertEqual(with_expiry(subject="Expiry on {{ doc.expiry_date }}."), [])

    def test_the_message_rule_is_only_for_a_shop_type_the_apps_own_keeps_its_rules(self):
        m = copy.deepcopy(V1)
        m["notifications"][0]["message"] = "{% if doc.title %}{{ doc.title }}{% endif %}"
        self.assertEqual(validate(m), [])


if __name__ == "__main__":
    unittest.main()
