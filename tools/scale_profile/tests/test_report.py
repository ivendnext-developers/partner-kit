"""test_report.py — the scale-profile kit's report (report.py): the profile table, the measured figures, the list of what
was NOT measured (printed every time), and its two guards — a missing field is refused in words, and a peak hour above
the measured one-till rate is warned about.

    python3 -m unittest discover -s tools/scale_profile/tests -p "test_*.py"

The report is run as a partner runs it, as a command. SCALE_REPORT names another copy of report.py to test (how a
broken copy is shown to fail); by default it is the kit's own.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
REPORT = os.environ.get("SCALE_REPORT") or str(HERE / "report.py")
EXAMPLE = HERE / "profile.example.json"
MEASURED = HERE / "measured_2026-10-04.json"

NOT_MEASURED = ["## NOT measured", "**Concurrency:**", "**Many stores:**", "**A catalogue of", "**Offline drains:**",
                "**The production box:**", "No load test exists anywhere else"]
WARNING = "The profile's peak hour is above what was measured"


def run(profile, measured=MEASURED):
    return subprocess.run([sys.executable, REPORT, str(profile), str(measured)], capture_output=True, text=True)


class Report(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, data):
        path = pathlib.Path(self.tmp.name) / name
        path.write_text(json.dumps(data))
        return path

    def profile(self, **change):
        p = json.loads(EXAMPLE.read_text())
        p.update(change)
        return p

    def test_profile_table_and_measured_figures(self):
        r = run(EXAMPLE)
        self.assertEqual(r.returncode, 0, r.stderr)
        # 40 stores × 4 tills = 160 tills; × 180 = 28,800 sales a day; 18% of that = 5,184 in the peak hour
        self.assertIn("| 40 | 160 | 25,000 | 28,800 | 5,184 | 3 |", r.stdout)
        self.assertIn("120 of 120 sales booked", r.stdout)
        self.assertIn("preview p50 81.4 ms / p95 92.6 ms; booking p50 568.4 ms / p95 606.1 ms", r.stdout)
        self.assertIn("about **5,177 sales an hour**", r.stdout)

    def test_not_measured_is_printed_every_time(self):
        small = self.write("small.json", self.profile(stores=1, tills_per_store=1, sales_per_till_per_day=10))
        for profile in (EXAMPLE, small):
            r = run(profile)
            self.assertEqual(r.returncode, 0, r.stderr)
            for line in NOT_MEASURED:
                self.assertIn(line, r.stdout, f"{profile.name}: missing {line!r}")

    def test_missing_profile_field_is_refused_in_words(self):
        p = self.profile()
        del p["tills_per_store"]
        r = run(self.write("no_tills.json", p))
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stderr)
        self.assertIn("tills_per_store", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_missing_measurement_field_is_refused_in_words(self):
        m = json.loads(MEASURED.read_text())
        del m["db_bytes_per_sale"]           # read after the first lines are printed: only the buffer keeps them back
        r = run(EXAMPLE, self.write("no_bytes.json", m))
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stderr)
        self.assertIn("db_bytes_per_sale", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.stdout, "", "a refusal leaves no half report")

    def test_peak_above_measured_is_warned(self):
        r = run(EXAMPLE)                      # 5,184 in the peak hour against 5,177 measured
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(WARNING, r.stdout)
        self.assertIn("5,184 sales against about 5,177", r.stdout)

    def test_peak_within_measured_is_not_warned(self):
        r = run(self.write("small.json", self.profile(stores=1)))       # 130 in the peak hour
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(WARNING, r.stdout)


if __name__ == "__main__":
    unittest.main()
