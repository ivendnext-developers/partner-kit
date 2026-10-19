"""The licence check: a filled licence and a third-party list pass; each missing or unfilled file is refused; a hosted
app's AGPL component needs its published source on its line.

    python3 -m unittest discover -s tools/check/tests
"""

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import licence  # noqa: E402


class Licence(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp())
        (self.repo / ".git").mkdir()
        self.app = self.repo / "library"
        self.app.mkdir()
        (self.repo / "LICENSE").write_text("Apache License, Version 2.0\n", "utf-8")
        (self.repo / "THIRD_PARTY.md").write_text("- left-pad 1.3.0, MIT\n", "utf-8")

    def test_a_filled_repository_passes_from_a_subfolder(self):
        self.assertEqual(licence.check(self.app), [])
        self.assertEqual(licence.check(self.app, hosted=True), [])

    def test_no_licence_file_is_refused(self):
        (self.repo / "LICENSE").unlink()
        self.assertIn("no licence file", " ".join(licence.check(self.app)))

    def test_an_empty_licence_is_refused(self):
        (self.repo / "LICENSE").write_text("  \n", "utf-8")
        self.assertIn("LICENSE is empty", " ".join(licence.check(self.app)))

    def test_the_templates_placeholder_is_refused(self):
        (self.repo / "LICENSE").write_text("Replace this file with your app's licence.\n", "utf-8")
        self.assertIn("placeholder", " ".join(licence.check(self.app)))

    def test_no_third_party_list_is_refused(self):
        (self.repo / "THIRD_PARTY.md").unlink()
        self.assertIn("no list of third-party components", " ".join(licence.check(self.app)))

    def test_an_empty_third_party_list_is_refused(self):
        (self.repo / "THIRD_PARTY.md").write_text("\n", "utf-8")
        self.assertIn("THIRD_PARTY.md is empty", " ".join(licence.check(self.app)))

    def test_a_notice_file_serves_as_the_list(self):
        (self.repo / "THIRD_PARTY.md").unlink()
        (self.repo / "NOTICE").write_text("Third-party code: none\n", "utf-8")
        self.assertEqual(licence.check(self.app), [])

    def test_the_search_stops_at_the_repository_root(self):
        outer = self.repo / "outer"
        outer.mkdir()
        inner = outer / "inner_repo"
        (inner / ".git").mkdir(parents=True)
        bad = " ".join(licence.check(inner))
        self.assertIn("no licence file", bad)
        self.assertIn("no list of third-party components", bad)

    def test_agpl_without_its_source_is_refused_only_when_hosted(self):
        (self.repo / "THIRD_PARTY.md").write_text("- some-engine 2.1, AGPL-3.0\n", "utf-8")
        self.assertEqual(licence.check(self.app), [])
        self.assertIn("AGPL component", " ".join(licence.check(self.app, hosted=True)))

    def test_agpl_with_its_published_source_is_accepted_when_hosted(self):
        (self.repo / "THIRD_PARTY.md").write_text(
            "- some-engine 2.1, GNU Affero GPL 3.0, source https://example.org/some-engine\n", "utf-8")
        self.assertEqual(licence.check(self.app, hosted=True), [])

    def test_prose_around_the_list_is_not_a_component(self):
        (self.repo / "THIRD_PARTY.md").write_text(
            "# Components\n\nAn AGPL component needs its source address.\n\n- left-pad 1.3.0, MIT\n", "utf-8")
        self.assertEqual(licence.check(self.app, hosted=True), [])

    def test_a_prose_notice_is_read_line_by_line(self):
        (self.repo / "THIRD_PARTY.md").unlink()
        (self.repo / "NOTICE").write_text("Third-party code:\nsome-engine, under the Affero GPL.\n", "utf-8")
        self.assertIn("AGPL component", " ".join(licence.check(self.app, hosted=True)))

    def test_the_templates_prose_with_none_passes_when_hosted(self):
        text = (pathlib.Path(__file__).resolve().parents[2] / "app_template" / "THIRD_PARTY.md").read_text("utf-8")
        (self.repo / "THIRD_PARTY.md").write_text(text.split("\n- ")[0] + "\nNone\n", "utf-8")
        self.assertEqual(licence.check(self.app, hosted=True), [])

    def test_a_heading_alone_lists_nothing(self):
        (self.repo / "THIRD_PARTY.md").write_text("# Third-party components\n", "utf-8")
        self.assertIn("THIRD_PARTY.md is empty", " ".join(licence.check(self.app)))

    def test_a_folder_in_no_repository_is_searched_alone(self):
        (self.repo / ".git").rmdir()
        self.assertIn("no licence file", " ".join(licence.check(self.app)))
        (self.app / "LICENSE").write_text("MIT\n", "utf-8")
        (self.app / "THIRD_PARTY.md").write_text("None\n", "utf-8")
        self.assertEqual(licence.check(self.app), [])

    def test_the_command_exits_by_its_verdict(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(licence.main([str(self.app)]), 0)
            (self.repo / "LICENSE").unlink()
            self.assertEqual(licence.main([str(self.app), "--hosted"]), 1)
            self.assertEqual(licence.main([]), 2)
        self.assertIn("REFUSED: no licence file", out.getvalue())


if __name__ == "__main__":
    unittest.main()
