"""The contracts folder holds together: every schema names the draft the checker reads, every accepted sample passes its
schema, every refused sample fails it (except the ones marked ``beyond_schema``, which only the shop's stored state can
refuse), and the checker can fail (a planted defect is caught). Standard library only.

    python3 -m unittest discover -s tools/contracts/tests
"""

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "contracts"))
import check  # noqa: E402

BASE = ROOT / "contracts" / "extension_contracts"
SCHEMAS = sorted(BASE.glob("*.v1.schema.json"))
SAMPLES = sorted(BASE.glob("samples/*/*/*.json"))


def sample(path):
    s = json.loads(path.read_text("utf-8"))
    return s, path.parent.name            # (the sample, "accepted" | "refused")


class ContractsTest(unittest.TestCase):
    def test_the_folder_is_not_empty(self):
        self.assertTrue(check.available())
        self.assertEqual(len(SCHEMAS), 15)
        self.assertGreaterEqual(len(SAMPLES), 100)

    def test_every_schema_names_its_draft_and_has_three_samples_each_way(self):
        mod = check._checker()
        for path in SCHEMAS:
            point = path.name.split(".")[0]
            schema = json.loads(path.read_text("utf-8"))
            self.assertEqual(schema["$schema"], mod.DRAFT, path.name)
            self.assertTrue(schema["$id"].endswith("/" + path.name), path.name)
            found = [sample(p) for p in SAMPLES if p.parent.parent.name == point]
            for outcome in ("accepted", "refused"):
                counted = [s for s, o in found if o == outcome and not s.get("beyond_schema")]
                self.assertGreaterEqual(len(counted), 3, f"{point}: three {outcome} samples")
            self.assertLessEqual({s["contract"] for s, _ in found}, set(schema["$defs"]), point)

    def test_every_sample_matches_or_fails_its_schema(self):
        for path in SAMPLES:
            s, outcome = sample(path)
            errs = check.errors(s["extension_point"], s["contract"], s["payload"])
            label = f"{s['extension_point']}/{outcome}/{path.name}"
            if outcome == "accepted" or s.get("beyond_schema"):
                self.assertEqual(errs, [], label)
            else:
                self.assertTrue(errs, f"{label}: the schema lets a refused sample through")
                self.assertTrue(s.get("expect_refusal"), f"{label}: names no refusal")

    def test_the_check_can_fail(self):
        """A planted defect in an accepted sample turns the same check red."""
        s, _ = sample(BASE / "samples" / "desk_action" / "accepted" / "01_message.json")
        self.assertEqual(check.errors("desk_action", "answer", s["payload"]), [])
        bad = copy.deepcopy(s["payload"])
        bad["message"]["level"] = "shout"
        self.assertTrue(check.errors("desk_action", "answer", bad))
        bad = copy.deepcopy(s["payload"])
        bad["unknown_key"] = 1
        self.assertTrue(check.errors("desk_action", "answer", bad))


if __name__ == "__main__":
    unittest.main()
