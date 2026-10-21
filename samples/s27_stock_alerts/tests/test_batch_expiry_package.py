"""S27's batch-expiry reminder (``batch_expiry_package.json``, POS build 2.0.0.654 on): valid for the kit's checker with no
warning; the product's own accepted shape (``contracts/extension_contracts/samples/package_manifest/accepted/
06_a_batch_expiry_reminder.json``) for its notification; and the checker refuses what the reminder must never do.

    python3 -m unittest discover -s samples/s27_stock_alerts/tests -p 'test_*.py'
"""

import copy
import json
import sys
import unittest
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent.parent
KIT = SAMPLE.parent.parent
sys.path.insert(0, str(KIT / "tools" / "manifest"))
import validate  # noqa: E402

PKG = json.loads((SAMPLE / "batch_expiry_package.json").read_text())
PRODUCT = KIT / "contracts" / "extension_contracts" / "samples" / "package_manifest" / "accepted" / "06_a_batch_expiry_reminder.json"


class BatchExpiryPackage(unittest.TestCase):
    def test_the_kits_checker_finds_it_valid_with_no_warning(self):
        self.assertEqual((validate.validate(PKG), validate.warnings(PKG)), ([], []))

    def test_a_separate_app_with_one_reminder_before_a_batchs_expiry_to_a_role(self):
        self.assertEqual((PKG["app"], PKG["prefix"]), ("pp_exp", "PP EXP"))
        self.assertEqual(set(PKG) - {"manifest_version", "app", "prefix", "title", "version", "publisher", "description"},
                         {"notifications"})
        (n,) = PKG["notifications"]
        self.assertEqual((n["document_type"], n["event"], n["date_changed"]), ("Batch", "Days Before", "expiry_date"))
        self.assertTrue(1 <= n["days_in_advance"] <= 365)
        self.assertEqual([list(r) for r in n["recipients"]], [["receiver_by_role"]])

    @unittest.skipUnless(PRODUCT.is_file(), "the contracts folder is missing from this copy of the kit")
    def test_its_notification_is_the_products_accepted_shape(self):
        product = json.loads(PRODUCT.read_text())["payload"]["notifications"][0]
        self.assertEqual(PKG["notifications"][0], product)

    def test_the_checker_refuses_what_a_reminder_on_a_shop_record_may_not_do(self):
        for change in ({"event": "Save"}, {"recipients": [{"receiver_by_document_field": "owner"}]},
                       {"message": "{% for b in ivn_rows('Batch') %}{{ b.name }}{% endfor %}"}, {"days_in_advance": 400}):
            bad = copy.deepcopy(PKG)
            bad["notifications"][0].update(change)
            self.assertTrue(validate.validate(bad), change)


if __name__ == "__main__":
    unittest.main()
