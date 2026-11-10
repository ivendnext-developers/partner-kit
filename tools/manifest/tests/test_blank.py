"""The blank app (``tools/manifest/blank.py``): what New app makes with no sample, for a need no sample matches.

    python3 -m unittest discover -s tools/manifest/tests -p test_blank.py
"""
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
KIT = pathlib.Path(os.environ.get("PARTNER_KIT") or HERE.parents[2]).resolve()
sys.path.insert(0, str(HERE.parent))
import blank  # noqa: E402
import combine  # noqa: E402
import site_rules  # noqa: E402
import validate  # noqa: E402

PREFIX, APP = "ACME STORE", "acme_store"


def refusals(m: dict) -> list:
    return [f"{r['where']}: {r['reason']}" for r in validate.validate(m) + site_rules.refusals(m)]


class TheBlankApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = io.StringIO()
        cls.folder = combine.combine([], PREFIX, cls.tmp.name, test=True, out=out)
        cls.said = out.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_its_manifest_has_the_name_prefix_and_version_and_no_entries(self):
        m = json.loads((self.folder / "manifest.json").read_text("utf-8"))
        self.assertEqual((m["app"], m["prefix"], m["version"], m["manifest_version"]), (APP, PREFIX, "1.0.0", 2))
        self.assertEqual([k for k, v in m.items() if isinstance(v, list)], [])

    def test_its_app_json_has_no_samples_and_records_what_was_written(self):
        aj = json.loads((self.folder / "app.json").read_text("utf-8"))
        self.assertEqual(aj["samples"], [])
        self.assertIn("README.md", aj["blank"]["files"])
        self.assertIn("tests/test_manifest.py", aj["blank"]["files"])

    def test_its_one_test_runs_the_kits_checker_and_passes(self):
        self.assertEqual(sorted(p.name for p in (self.folder / "tests").glob("test_*.py")), ["test_manifest.py"])
        ok, n, log = combine.run_tests(self.folder)
        self.assertTrue(ok, log)
        self.assertEqual(n, 1)
        self.assertEqual(combine.kit_check(self.folder)[0], 0)

    def test_its_test_fails_on_a_refused_entry_and_names_it(self):
        with tempfile.TemporaryDirectory() as d:
            f = combine.combine([], "ACME BAD", d)
            m = json.loads((f / "manifest.json").read_text("utf-8"))
            m["custom_fields"] = [{"dt": "Customer", "fieldname": "tier", "fieldtype": "Data", "label": "Tier"}]
            (f / "manifest.json").write_text(json.dumps(m), "utf-8")
            ok, _, log = combine.run_tests(f)
            self.assertFalse(ok)
            self.assertIn("custom_fields[0]", log)

    def test_it_says_what_it_made_and_where_to_read_next(self):
        self.assertTrue(self.said.startswith("Made. A blank app. CHECK GREEN · 1 tests run, 1 passed."), self.said)
        self.assertIn("README.md", self.said)

    def test_the_readme_lists_every_kind_the_checker_takes(self):
        text = (self.folder / "README.md").read_text("utf-8")
        listed = re.findall(r"^\| `([a-z_]+)` \|", text, re.M)
        self.assertEqual(sorted(listed), sorted(set(validate.KINDS) | {"app_user_rights"}))
        for kind, _, _, page in blank.KINDS:   # each link is a page the site builds (recipes, guide) or a kit file on GitHub
            url = blank.link(page)
            if url.startswith(blank.SITE + "/"):
                self.assertRegex(page, r"^(recipes|guide)/[a-z0-9_]+\.html$", kind)
                self.assertTrue((KIT / page.replace(".html", ".md")).is_file(), f"{kind}: {page} has no page in the kit")
            else:
                self.assertTrue(url.startswith(blank.KIT_ON_GITHUB + "/contracts/pages/"), kind)
                self.assertTrue((KIT / page).is_file(), f"{kind}: {page} is not in the kit")
            self.assertIn(f"]({url})", text)

    def test_the_readme_lists_every_kind_of_the_manifest_recipes_table(self):
        recipe = (KIT / "recipes" / "manifest.md").read_text("utf-8")
        table = set(re.findall(r"^   \| `([a-z_]+)`", recipe, re.M))
        self.assertLessEqual(table, {k for k, *_ in blank.KINDS})

    def test_each_example_passes_the_checker_on_its_own_and_all_together(self):
        base = blank.manifest(PREFIX, APP)
        ex = blank.examples(PREFIX, APP)
        self.assertEqual(refusals(dict(base, **ex)), [])
        for kind, rows in ex.items():   # an example may name the record type example (a link, a chart)
            with self.subTest(kind=kind):
                self.assertEqual(refusals(dict(base, **{"doctypes": ex["doctypes"], kind: rows})), [])

    def test_the_readmes_two_lines_paste_into_the_manifest_as_it_says_and_check_green(self):
        text = (self.folder / "README.md").read_text("utf-8")
        lines = re.search(r"```json\n(.*?)\n```", text, re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            f = combine.combine([], PREFIX, d)
            m = (f / "manifest.json").read_text("utf-8").rstrip()
            pasted = m[:-1].rstrip() + ",\n" + lines + "\n}"   # a comma after the last line, the two lines, the brace
            self.assertEqual(sorted(json.loads(pasted))[:2], ["app", "custom_fields"])
            (f / "manifest.json").write_text(pasted, "utf-8")
            self.assertEqual(combine.kit_check(f)[0], 0)
            self.assertTrue(combine.run_tests(f)[0])

    def test_the_examples_take_the_apps_own_names(self):
        ex = blank.examples("ZED SHOP", "zed_shop")
        self.assertEqual(ex["custom_fields"][0]["fieldname"], "zed_shop_loyalty_tier")
        self.assertEqual(ex["naming_rules"][0]["prefix"], "ZED-VIS-.YYYY.-")
        self.assertNotRegex(json.dumps(ex), r"\{[PWp]\}")


class AddASampleToABlankApp(unittest.TestCase):
    def test_a_sample_goes_in_and_the_developers_entries_stay(self):
        with tempfile.TemporaryDirectory() as d:
            f = combine.combine([], PREFIX, d)
            m = json.loads((f / "manifest.json").read_text("utf-8"))
            ex = blank.examples(PREFIX, APP)
            m["custom_fields"], m["notifications"] = ex["custom_fields"], ex["notifications"]
            (f / "manifest.json").write_text(json.dumps(m, indent=1), "utf-8")
            out = io.StringIO()
            combine.add("s11", f, test=True, out=out)
            self.assertIn("1.1.0", out.getvalue())
            self.assertNotIn("kept", out.getvalue())
            m = json.loads((f / "manifest.json").read_text("utf-8"))
            aj = json.loads((f / "app.json").read_text("utf-8"))
            self.assertEqual(m["custom_fields"], ex["custom_fields"])
            self.assertEqual(m["notifications"], ex["notifications"])
            self.assertTrue(m["workflows"])
            self.assertNotIn("blank", aj)
            self.assertEqual([r["name"] for r in aj["samples"]], ["s11_approvals"])
            out = io.StringIO()
            combine.add("s27", f, test=True, out=out)      # a second sample: as into any app
            self.assertNotIn("kept", out.getvalue())

    def test_a_readme_the_developer_changed_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            f = combine.combine([], PREFIX, d)
            (f / "README.md").write_text("# Ours\n", "utf-8")
            added = combine.add("s11", f)
            self.assertEqual((f / "README.md").read_text("utf-8"), "# Ours\n")
            self.assertIn("README.md", added.kept_files)


if __name__ == "__main__":
    unittest.main()
