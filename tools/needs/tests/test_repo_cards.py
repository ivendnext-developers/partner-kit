"""The repository's own cards keep every rule: a bad card in needs/ fails CI. Stale cards are printed as a warning, never a failure.

    python3 -m unittest discover -s tools/needs/tests

.github/scripts/run_tests.py finds this folder by itself, so CI runs it with no edit to the workflow.
"""
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "needs"))
import needs  # noqa: E402


class RepoCards(unittest.TestCase):
    def test_every_card_in_the_repository_keeps_the_rules(self):
        cards = needs.load(ROOT)
        self.assertGreater(len(cards), 0, "needs/ holds no card")
        self.assertEqual(needs.check(ROOT), [])
        old = needs.stale(cards, 90)
        if old:
            print(f"\nWARNING (not a failure): {len(old)} card(s) checked more than 90 days ago: "
                  + ", ".join(c.id for c in old[:10]) + (" …" if len(old) > 10 else ""), file=sys.stderr)

    def test_a_planted_bad_card_in_a_copy_of_the_repository_fails(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(ROOT / "needs", tmp / "needs")
        for folder in ("recipes", "samples", "tools", "guide", "contracts"):
            os.symlink(ROOT / folder, tmp / folder)
        self.assertEqual(needs.check(tmp), [])
        bad = (tmp / "needs" / "till" / "line-quantity-cap.md")
        bad.write_text(bad.read_text("utf-8").replace("door: check-before-payment", "door: back-door"), "utf-8")
        self.assertTrue(any("unknown door 'back-door'" in b for b in needs.check(tmp)))


if __name__ == "__main__":
    unittest.main()
