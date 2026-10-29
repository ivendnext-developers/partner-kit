"""tools/manifest/rename.py: a copied app takes your prefix in one step, and nothing is written unless the shop's checker
passes — stdlib only:
    python3 -m unittest discover -s tools/manifest/tests -p "test_rename.py" -v

Every sample in the kit with a manifest is renamed here and checked with the shop's own checker, so a new sample that
the rename cannot make yours fails this test the day it is added."""

import io
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = pathlib.Path(__file__).resolve().parent
KIT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import rename  # noqa: E402
from site_rules import refusals as site  # noqa: E402
from validate import validate  # noqa: E402

S2 = KIT / "samples" / "s2_bins"


def strings(o):
    return re.findall(r'"((?:[^"\\]|\\.)*)"', json.dumps(o, ensure_ascii=False))


class EverySample(unittest.TestCase):
    def test_every_sample_renames_to_a_manifest_the_shop_accepts(self):
        found = sorted(KIT.glob("samples/**/manifest.json"))    # S3's sits in outside/
        self.assertGreater(len(found), 20)
        for p in found:
            with self.subTest(sample=p.parent.name):
                m = json.loads(p.read_text())
                new, left = rename.rename(m, "ACME TEST")
                self.assertEqual(left, [])
                self.assertEqual(validate(new) + site(new), [])
                self.assertEqual((new["app"], new["prefix"]), ("acme_test", "ACME TEST"))
                old_first = m["prefix"].split()[0]
                others = tuple(o + " " for o in rename.kit_prefixes() if o != m["prefix"])   # another app's names stay
                self.assertEqual([s for s in strings(new) if s.startswith(old_first + " ") and not s.startswith(others)],
                                 [])


class BinLocations(unittest.TestCase):
    def setUp(self):
        self.m = json.loads((S2 / "manifest.json").read_text())
        self.new, self.left = rename.rename(self.m, "ACME BINS")

    def test_record_types_fields_and_roles_take_the_prefix(self):
        self.assertIn("ACME BINS Bin", [d["name"] for d in self.new["doctypes"]])
        self.assertEqual([c["fieldname"] for c in self.new["custom_fields"]], ["acme_bins_default_bin"])
        roles = set(re.findall(r'"role": "([^"]+)"', json.dumps(self.new)))
        self.assertIn("ACME BINS Integration", roles)
        self.assertNotIn("PP Integration", roles)

    def test_a_link_to_an_own_record_type_follows_it(self):
        bin_ = next(d for d in self.new["doctypes"] if d["name"] == "ACME BINS Bin")
        self.assertIn("ACME BINS Aisle", [f.get("options") for f in bin_["fields"]])

    def test_the_outside_addresses_are_listed_for_you_to_replace(self):
        urls = rename.addresses(self.new)
        self.assertTrue(urls)
        self.assertTrue(all("docs.ivendnext.com" not in u for u in urls))


class AnotherSamplesNames(unittest.TestCase):
    """S41 reads the counter-rules app's (S39's) sale details and record types by their names ("PP RXC Rx Number"): they
    are that app's, installed by it, so a renamed S41 still names them as S39 installs them."""

    def setUp(self):
        self.m = json.loads((KIT / "samples" / "s41_regulated_register" / "manifest.json").read_text())
        self.s39 = json.loads((KIT / "samples" / "s39_pharmacy_counter" / "manifest.json").read_text())["prefix"]

    def test_the_other_apps_names_stay_and_the_own_roles_still_follow(self):
        theirs = sorted({s for s in strings(self.m) if s.startswith(self.s39 + " ")})
        self.assertTrue(theirs, "S41 no longer names S39's records: this test guards nothing")
        new, left = rename.rename(self.m, "ACME TEST")
        self.assertEqual(left, [])
        self.assertEqual(sorted({s for s in strings(new) if s.startswith(self.s39 + " ")}), theirs)
        self.assertEqual([s for s in strings(new) if s.startswith("ACME TEST RXC")], [])

    def test_a_role_named_with_the_first_word_alone_is_still_renamed(self):
        first = rename.role_start(self.m["prefix"])
        self.assertTrue(first.search("PP Integration"))
        self.assertFalse(first.search(self.s39 + " Rx Number"))
        self.assertFalse(first.search(self.m["prefix"] + " Book"))


class Refusals(unittest.TestCase):
    def test_a_prefix_starting_with_a_word_the_shop_reads_is_refused(self):
        self.assertIn("a word the shop reads", rename.refuse_prefix("FREE BINS", "PP BLN"))

    def test_a_prefix_not_in_upper_case_words_is_refused(self):
        self.assertIsNotNone(rename.refuse_prefix("acme bins", "PP BLN"))

    def test_the_apps_own_prefix_is_refused(self):
        self.assertIsNotNone(rename.refuse_prefix("PP BLN", "PP BLN"))

    def test_a_refused_prefix_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "manifest.json"
            p.write_text((S2 / "manifest.json").read_text())
            before = p.read_text()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(rename.main([str(p), "--prefix", "FREE BINS", "--write"]), 1)
            self.assertEqual(p.read_text(), before)

    def test_a_result_the_shop_would_refuse_is_never_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "manifest.json"
            m = json.loads((S2 / "manifest.json").read_text())
            m["doctypes"].append({"name": "Not Mine", "fields": []})       # a name without the prefix: the shop refuses
            p.write_text(json.dumps(m))
            before = p.read_text()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(rename.main([str(p), "--prefix", "ACME BINS", "--write"]), 1)
            self.assertEqual(p.read_text(), before)


class HyphenedNames(unittest.TestCase):
    def test_a_series_a_style_class_and_a_service_user_follow_in_the_case_they_were_written(self):
        m = {"app": "pp_stn", "prefix": "PP STN", "series": "PP-STN-.YYYY.-", "css": ".pp-stn-label { }", "user": "pp-stn-service@x"}
        new, left = rename.rename(m, "ACME BINS")
        self.assertEqual((new["series"], new["css"], new["user"]), ("ACME-BINS-.YYYY.-", ".acme-bins-label { }", "acme-bins-service@x"))
        self.assertEqual(left, [])

    def test_a_manifest_in_a_plain_folder_never_pulls_in_the_hosting_order_above_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "app.json").write_text('{"app": "mine", "handler": "samples/s2_bins/x.py"}')
            (root / "apps").mkdir()
            shutil.copy(S2 / "manifest.json", root / "apps" / "manifest.json")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(rename.main([str(root / "apps" / "manifest.json"), "--prefix", "ACME BINS", "--write"]), 0)
            self.assertEqual((root / "app.json").read_text(), '{"app": "mine", "handler": "samples/s2_bins/x.py"}')


class InACopyOfTheKit(unittest.TestCase):
    """Your app in its own folder of a repository made from the kit: the manifest and the hosting order both become yours."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        (root / "tools" / "app_template" / "service").mkdir(parents=True)
        (root / "tools" / "app_template" / "service" / "function.py").write_text("")
        self.app = root / "apps" / "acme_bins"
        shutil.copytree(S2, self.app, ignore=shutil.ignore_patterns("__pycache__", "screenshots"))
        with redirect_stdout(io.StringIO()) as self.out:
            self.rc = rename.main([str(self.app / "manifest.json"), "--prefix", "ACME BINS", "--write"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_manifest_is_written_yours(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(json.loads((self.app / "manifest.json").read_text())["app"], "acme_bins")

    def test_the_hosting_order_takes_your_address_and_your_folder(self):
        a = json.loads((self.app / "app.json").read_text())
        self.assertEqual(a["app"], "acme-bins")
        self.assertTrue(a["handler"].startswith("apps/acme_bins/service/"))
        self.assertEqual([p for p in a["package"] if "samples/s2_bins" in p], [])
        self.assertIn("apps/acme_bins/core.py", a["package"])

    def test_the_code_still_naming_the_old_app_is_listed(self):
        self.assertIn("service/bins.py:", self.out.getvalue())
        self.assertNotIn("\n  app.json:", self.out.getvalue())        # renamed itself, so never listed


if __name__ == "__main__":
    unittest.main()
