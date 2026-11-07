"""The manifest's rights for the app's own roles (`role_rights`) and default rows (`records`): what the checker
accepts, what it refuses, and in whose words. The checker is a copy of the shop's own, so the words are the shop's.

    python3 -m unittest discover -s tools/manifest/tests -v

A manifest that carries either kind installs on a site at POS build 2.1.0.691 or later; on an earlier site the install
warns the kind as unknown and skips it (`warnings`), and gives the feed's user no read."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate, warnings  # noqa: E402

BASE = json.loads((HERE / "fixtures" / "installready_v2_ok.json").read_text())


def reasons(m):
    return [r["reason"] for r in validate(m)]


class Accepted(unittest.TestCase):
    def test_a_right_for_the_apps_own_role_and_a_default_row_pass_with_no_warning(self):
        self.assertEqual((validate(BASE), warnings(BASE)), ([], []))

    def test_a_default_row_by_name_and_a_value_on_the_apps_own_settings_pass(self):
        m = copy.deepcopy(BASE)
        m["records"].append({"doctype": "Customer Group", "name": "PP IRD Plus", "values": {"parent_customer_group": "All Customer Groups"}})
        self.assertEqual(validate(m), [])


class RoleRightsRefused(unittest.TestCase):
    def test_a_role_the_retailer_owns_is_refused_in_the_shops_words(self):
        m = copy.deepcopy(BASE)
        m["role_rights"][0]["role"] = "Sales User"
        self.assertEqual(reasons(m), ["Name a role of your own (it starts with PP IRD); "
                                      "the retailer gives their own roles rights in Role Permissions Manager."])

    def test_a_right_the_permissions_row_does_not_take_is_refused(self):
        m = copy.deepcopy(BASE)
        m["role_rights"][0]["rights"] = ["read", "approve"]
        out = reasons(m)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("rights lists each right the role gets, once, by the name a permissions row takes"))


class RecordsRefused(unittest.TestCase):
    def test_one_of_the_tills_own_records_is_refused_in_the_shops_words(self):
        m = copy.deepcopy(BASE)
        m["records"] = [{"doctype": "Coupon Code", "values": {"coupon_name": "PP IRD 10", "coupon_type": "Promotional"}}]
        self.assertEqual(reasons(m), ["Coupon Code is one of the till's own records, "
                                      "which the till writes as it sells; the retailer makes these."])

    def test_a_document_that_posts_is_refused(self):
        m = copy.deepcopy(BASE)
        m["records"] = [{"doctype": "Purchase Invoice", "values": {"supplier": "Anyone"}}]
        self.assertEqual(reasons(m), ["A document that posts is the retailer's to make."])


if __name__ == "__main__":
    unittest.main()
