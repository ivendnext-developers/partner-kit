"""S1's manifest: the install gives the app's own role every right the pass and the Warranty key use, so the retailer's
administrator grants none. Stdlib only:  python3 -m unittest discover -s samples/s1_warranty/tests -p 'test_manifest.py'"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")


class ManifestTest(unittest.TestCase):
    def test_the_apps_role_gets_the_reads_and_the_comment_it_needs(self):
        m = json.load(open(MANIFEST, encoding="utf-8"))
        role = f"{m['prefix']} Integration"
        got = {(r["doctype"], tuple(sorted(r["rights"]))) for r in m.get("role_rights", []) if r["role"] == role}
        self.assertEqual(got, {("Sales Invoice", ("read",)), ("POS Invoice", ("read",)),
                               ("Serial and Batch Bundle", ("read",)), ("Item", ("read",)),
                               ("Comment", ("create", "read"))})
        self.assertEqual([r for r in m["role_rights"] if r["role"] != role], [])   # no other role is given anything


if __name__ == "__main__":
    unittest.main()
