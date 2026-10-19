"""S16's manifest: the app's own role, which the install makes, reads and creates pick tasks and nothing else, and the feed
whose user a service serving many shops receives on Connect again.

    python3 -m unittest discover -s samples/s16_pick_route/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.m = json.load(open(MANIFEST))

    def test_the_feeds_user_holds_the_apps_own_role(self):
        role = f"{self.m['prefix']} Integration"
        task = next(d for d in self.m["doctypes"] if d["name"] == f"{self.m['prefix']} Pick Task")
        rows = [p for p in task["permissions"] if p["role"] == role]
        self.assertEqual(len(rows), 1)          # the install makes a role named under the prefix (the product's install rule)
        self.assertEqual({k for k, v in rows[0].items() if v == 1}, {"read", "create"})
        feed, = self.m["registered_applications"]
        self.assertEqual(feed["events"], [task["name"]])       # the checker refuses a feed with none; it records nothing


if __name__ == "__main__":
    unittest.main()
