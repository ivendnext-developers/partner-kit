"""S16's manifest: the app's own role, which the install makes, reads and creates pick tasks and nothing else, and the feed
whose user a service serving many shops receives when its site connects.

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

    def test_a_task_line_shows_the_items_name_and_the_order_lines_unit(self):
        line = next(d for d in self.m["doctypes"] if d["name"] == f"{self.m['prefix']} Pick Task Line")
        shown = [f["fieldname"] for f in line["fields"] if f.get("in_list_view")]
        self.assertEqual(shown, ["stop", "item_code", "item_name", "qty", "uom", "warehouse"])
        # the grid shows a column only while the widths add up to ten or less: every one of the six is shown
        self.assertLessEqual(sum(f["columns"] for f in line["fields"] if f.get("in_list_view")), 10)
        action, = self.m["desk_actions"]
        self.assertIn("items(item_code, item_name, qty, uom, warehouse)", action["send_fields"])   # the service is sent both

    def test_the_english_words_cover_every_name_the_store_sees(self):   # Desk shows people's words, never the code
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        names = {d["name"] for d in m.get("doctypes", [])}
        for key in ("print_formats", "reports", "registered_applications", "sale_attributes", "workspaces",
                    "number_cards", "notifications", "dashboard_charts"):
            names |= {x["name"] for x in m.get(key, [])}
        for wf in m.get("workflows", []):
            names |= {wf["name"]} | {s["state"] for s in wf["states"]} | {t["action"] for t in wf["transitions"]}
        for d in m.get("doctypes", []):
            names |= {p["role"] for p in d.get("permissions", []) if not p["role"].endswith(" Integration")}
        (en,) = [t["words"] for t in m["translations"] if t["language"] == "en"]
        self.assertEqual(sorted(n for n in names if n.startswith(m["prefix"]) and n not in en), [])
        self.assertTrue(all(w and not w.startswith(m["prefix"]) for w in en.values()))


if __name__ == "__main__":
    unittest.main()
