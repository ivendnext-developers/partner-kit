"""The CI check that every extension point has a card (.github/scripts/chapter16_rows.py), green on the kit and red on a plant.

    python3 -m unittest discover -s tools/needs/tests
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github" / "scripts" / "chapter16_rows.py"


class Chapter16Rows(unittest.TestCase):
    def kit(self) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for name in ("tools", "recipes", "samples", "guide"):
            (tmp / name).symlink_to(ROOT / name)
        shutil.copytree(ROOT / "needs", tmp / "needs")
        shutil.copytree(ROOT / "contracts" / "pages", tmp / "contracts" / "pages")
        return tmp

    def run_on(self, root: pathlib.Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True)

    def test_green_on_the_kit(self):
        r = self.run_on(ROOT)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("each has a card", r.stdout)

    def test_a_planted_extension_point_with_no_card_is_red(self):
        kit = self.kit()
        (kit / "contracts" / "pages" / "planted.md").write_text("# Planted extension point\n", "utf-8")
        r = self.run_on(kit)
        self.assertEqual(r.returncode, 1)
        self.assertIn("planted.md (Planted extension point): no door mapped", r.stdout)

    def test_a_door_whose_only_card_is_removed_is_red(self):
        kit = self.kit()
        (kit / "needs" / "integrations" / "outside-fiscal-result.md").unlink()     # the only card on door fiscal-reader
        r = self.run_on(kit)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no Ready card has door fiscal-reader", r.stdout)


if __name__ == "__main__":
    unittest.main()
