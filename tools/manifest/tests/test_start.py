"""tools/manifest/start.py: a sample becomes the partner's own app in one command — stdlib only:
    python3 -m unittest discover -s tools/manifest/tests -p "test_start.py" -v

Three samples of different kinds are started under a made-up prefix in a repository made from the kit (a manifest and
code; a hosting order and a service; a print format). Each must leave no name of the sample, pass the kit's checks and
run its own tests under the new names. The refusals, "nothing outside the new folder is written" and a canary (a rewrite
broken on purpose must make the leftover check red) follow."""

import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
KIT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import start  # noqa: E402

PREFIX = "ACME TST"
KINDS = [("s11_approvals", "a manifest and code"), ("s16_pick_route", "a hosting order and a service"),
         ("s4_receipt_pack", "a print format"), ("s34_po_check", "a container recipe")]


def fingerprint(*roots) -> dict:
    out = {}
    for root in roots:
        for p in sorted(pathlib.Path(root).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def repository(d: str) -> pathlib.Path:
    """A repository made from the kit: it holds the kit's tools and contracts (linked, so nothing is copied)."""
    root = pathlib.Path(d)
    (root / "tools").symlink_to(KIT / "tools")
    (root / "contracts").symlink_to(KIT / "contracts")
    return root


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, {"PYTHONDONTWRITEBYTECODE": "1"}):
        rc = start.main(list(args))
    return rc, out.getvalue()


class Started(unittest.TestCase):
    def test_three_kinds_of_sample_become_yours_with_no_old_name_left(self):
        for sample, kind in KINDS:
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as d:
                repo = repository(d)
                rc, out = run(sample, "--prefix", PREFIX, "--into", str(repo), "--test")
                self.assertEqual(rc, 0, out)
                target = repo / "apps" / "acme_tst"
                old = start.old_names(json.loads(start.manifest_of(KIT / "samples" / sample).read_text()), sample)
                left = [p for p in start.texts(target) for l in p.read_text().splitlines() if old.search(l)]
                self.assertEqual(left, [])
                self.assertFalse((target / "screenshots").exists())
                self.assertNotIn("screenshots/", (target / "README.md").read_text())
                self.assertNotIn(start.START_LINE, (target / "README.md").read_text())
                files = re.search(r"(\d+) file\(s\) written, (\d+) name\(s\)", out)
                ran = re.search(r"copied tests: ran (\d+), OK", out)
                green = re.search(r"checks over apps/acme_tst: (CHECK GREEN.*)", out)
                self.assertTrue(files and ran and green, out)
                self.assertGreater(int(ran.group(1)), 5)
                print(f"\n{sample} ({kind}): {files.group(1)} files, {files.group(2)} renames, 0 old names left, "
                      f"{green.group(1)}, copied tests ran {ran.group(1)} OK")

    def test_the_hosting_order_and_the_series_are_yours(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            self.assertEqual(run("s16_pick_route", "--prefix", PREFIX, "--into", str(repo))[0], 0)
            a = (repo / "apps" / "acme_tst" / "app.json").read_text()
            self.assertIn("apps/acme_tst/", a)
            self.assertNotIn("samples/", a)
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            self.assertEqual(run("s11_approvals", "--prefix", PREFIX, "--into", str(repo))[0], 0)
            self.assertIn("ACME-TST-.YYYY.-", (repo / "apps" / "acme_tst" / "manifest.json").read_text())


class Container(unittest.TestCase):
    def test_a_container_recipe_builds_your_app_not_ours(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            self.assertEqual(run("s34_po_check", "--prefix", PREFIX, "--into", str(repo))[0], 0)
            recipe = (repo / "apps" / "acme_tst" / "Dockerfile").read_text()
            self.assertIn("apps/acme_tst/service/app.py", recipe)
            self.assertNotIn("samples/s34_po_check", recipe)

    def test_canary_a_recipe_left_naming_our_folder_turns_the_check_red(self):
        real = start.rewrite
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            with mock.patch.object(start, "rewrite", lambda t, m, p, s, a: real(t, m, p, s, a).replace(f"apps/{a}/", f"samples/{s}/")):
                rc, out = run("s34_po_check", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1, out)
            self.assertIn("Dockerfile", out)


class Refused(unittest.TestCase):
    def refused(self, *args, repo=None, words=""):
        with tempfile.TemporaryDirectory() as d:
            rc, out = run(*args, "--into", str(repo or repository(d)))
            self.assertEqual(rc, 1, out)
            self.assertIn("REFUSED", out)
            self.assertIn(words, out)
            return d

    def test_a_word_that_is_ours_or_that_the_shop_reads_is_refused(self):
        self.refused("s11_approvals", "--prefix", "PP MINE", words="is ours")
        self.refused("s11_approvals", "--prefix", "IVENDNEXT MINE", words="is ours")
        self.refused("s11_approvals", "--prefix", "FREE BINS", words="a word the shop reads")

    def test_a_short_name_or_word_the_library_would_not_hold_is_refused(self):
        self.refused("s11_approvals", "--prefix", "Acme Bins", words="upper-case words")
        self.refused("s11_approvals", "--prefix", "ACME-BINS", words="upper-case words")
        self.refused("s11_approvals", "--prefix", "A BINS", words="not a first word")
        self.refused("s11_approvals", "--prefix", "PP APR", words="the app's own")

    def test_a_sample_that_builds_its_manifests_or_does_not_exist_is_refused(self):
        self.refused("s5_config_pack", "--prefix", PREFIX, words="no manifest.json of its own")
        self.refused("s99_nothing", "--prefix", PREFIX, words="no sample called")
        self.refused("../tools", "--prefix", PREFIX, words="no sample called")

    def test_a_target_that_exists_is_refused_and_left_as_it_was(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            (repo / "apps" / "acme_tst").mkdir(parents=True)
            (repo / "apps" / "acme_tst" / "mine.txt").write_text("keep")
            rc, out = run("s11_approvals", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1)
            self.assertIn("exists already", out)
            self.assertEqual((repo / "apps" / "acme_tst" / "mine.txt").read_text(), "keep")

    def test_a_folder_that_is_not_made_from_the_kit_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            self.refused("s11_approvals", "--prefix", PREFIX, repo=pathlib.Path(d), words="not a repository made from the kit")
            self.assertFalse((pathlib.Path(d) / "apps").exists())


class Layouts(unittest.TestCase):
    def test_a_file_in_the_apps_folder_beside_the_new_one_is_never_touched(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            (repo / "apps").mkdir()
            (repo / "apps" / "app.json").write_text('{"app": "mine", "handler": "samples/s2_bins/x.py"}')
            self.assertEqual(run("s11_approvals", "--prefix", PREFIX, "--into", str(repo))[0], 0)
            self.assertEqual((repo / "apps" / "app.json").read_text(), '{"app": "mine", "handler": "samples/s2_bins/x.py"}')

    def test_a_sample_with_a_second_package_of_its_own_prefix_is_refused_whole(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            rc, out = run("s27_stock_alerts", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1, out)
            self.assertIn("a second package with its own prefix", out)
            self.assertFalse((repo / "apps").exists())

    def test_links_to_the_other_samples_still_resolve_from_the_copy(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            self.assertEqual(run("s32_coupon_rules", "--prefix", PREFIX, "--into", str(repo))[0], 0)
            text = (repo / "apps" / "acme_tst" / "README.md").read_text()
            self.assertNotIn("](../s", text)


class Writes(unittest.TestCase):
    def test_nothing_is_written_outside_the_new_folder(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            kit_before = fingerprint(KIT / "samples", KIT / "tools", KIT / "contracts")
            self.assertEqual(run("s16_pick_route", "--prefix", PREFIX, "--into", str(repo), "--test")[0], 0)
            self.assertEqual(fingerprint(KIT / "samples", KIT / "tools", KIT / "contracts"), kit_before)
            self.assertEqual(sorted(p.name for p in repo.iterdir()), ["apps", "contracts", "tools"])
            self.assertEqual(sorted(p.name for p in (repo / "apps").iterdir()), ["acme_tst"])

    def test_a_refusal_after_the_copy_removes_it(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            with mock.patch.object(start.rename, "main", lambda argv: (print("REFUSED: a stand-in refusal"), 1)[1]):
                rc, out = run("s11_approvals", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1)
            self.assertIn("stand-in refusal", out)
            self.assertEqual(sorted(p.name for p in repo.iterdir()), ["contracts", "tools"])      # no apps/, no half-made copy


class Canary(unittest.TestCase):
    def test_a_rewrite_that_misses_one_name_turns_the_leftover_check_red(self):
        real = start.rewrite

        def broken(text, m, prefix, sample, app):
            return real(text, m, prefix, sample, app).replace(prefix, m["prefix"], 1)      # puts one old name back

        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            with mock.patch.object(start, "rewrite", broken):
                rc, out = run("s11_approvals", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1, out)
            self.assertIn("a name of the sample is still in the copy", out)
            self.assertFalse((repo / "apps").exists())


class ReadsAnotherSample(unittest.TestCase):
    """partner-feedback#40: S41's tests read the counter-rules app it works with (S39). Started into apps/, they find it in
    the repository's samples/, and with no samples/ they say so and skip those checks: never a file that is not there."""

    def test_s41_started_beside_the_kits_samples_runs_its_checks_against_s39(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            (repo / "samples").symlink_to(KIT / "samples")
            rc, out = run("s41_regulated_register", "--prefix", PREFIX, "--into", str(repo), "--test")
            self.assertEqual(rc, 0, out)
            t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
                               cwd=repo / "apps" / "acme_tst", capture_output=True, text=True,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(t.returncode, 0, t.stderr[-1500:])
            self.assertRegex(t.stderr, r"counter_rules_app_installs.*\.\.\. ok")
            self.assertRegex(t.stderr, r"customers_linked_record.*\.\.\. ok")

    def test_s41_started_with_no_samples_skips_the_s39_checks_and_passes(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            rc, out = run("s41_regulated_register", "--prefix", PREFIX, "--into", str(repo), "--test")
            self.assertEqual(rc, 0, out)
            self.assertRegex(out, r"copied tests: ran \d+, OK")

class WebAddressNames(unittest.TestCase):
    """partner-feedback#39: a sample writes its prefix as a web address does (a stand-in retailer's path,
    ``/api/resource/PP%20RFR%20Settings/Default``); the copy must take the new prefix there too, or its tests fail."""

    def samples(self):
        out = []
        for d in sorted((KIT / "samples").iterdir()):
            try:
                m = json.loads(start.manifest_of(d).read_text(encoding="utf-8"))
            except (start.Refused, OSError, ValueError):
                continue
            if " " in m["prefix"] and any(m["prefix"].replace(" ", "%20") in p.read_text(encoding="utf-8")
                                          for p in start.texts(d)):
                out.append((d.name, m))
        return out

    def test_every_sample_with_its_prefix_in_a_web_address_starts_and_passes_its_own_tests(self):
        found = self.samples()
        self.assertGreaterEqual(len(found), 15)     # S23, S24, S32, S36-S38, S42, S44-S51 when this was written
        for sample, m in found:
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as d:
                repo = repository(d)
                rc, out = run(sample, "--prefix", PREFIX, "--into", str(repo), "--test")
                self.assertEqual(rc, 0, out)
                self.assertRegex(out, r"copied tests: ran \d+, OK")
                text = "".join(p.read_text(encoding="utf-8") for p in start.texts(repo / "apps" / "acme_tst"))
                self.assertNotIn(m["prefix"].replace(" ", "%20"), text)
                self.assertIn("ACME%20TST", text)

    def test_canary_a_rewrite_that_leaves_the_web_address_spelling_turns_the_leftover_check_red(self):
        real = start.rewrite

        def broken(text, m, prefix, sample, app):
            return real(text, m, prefix, sample, app).replace(prefix.replace(" ", "%20"), m["prefix"].replace(" ", "%20"))

        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            with mock.patch.object(start, "rewrite", broken):
                rc, out = run("s51_refund_rules", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1, out)
            self.assertIn("a name of the sample is still in the copy", out)
            self.assertIn("PP%20RFR", out)
            self.assertFalse((repo / "apps").exists())


class SharedNames(unittest.TestCase):
    """A role or a till theme named with our first word alone ("PP Integration", "PP Partner Till") is renamed wherever the
    copy names it, the manifest's own sentences included, so the manifest and the code agree (S24's tests read it)."""

    def test_a_role_and_a_theme_named_in_the_description_follow(self):
        for sample, old, new in (("s24_price_checker", "PP Integration", "ACME TST Integration"),
                                 ("s21_field_rules", "PP Partner Till", "ACME TST Partner Till")):
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as d:
                repo = repository(d)
                rc, out = run(sample, "--prefix", PREFIX, "--into", str(repo), "--test")
                self.assertEqual(rc, 0, out)
                m = json.loads((repo / "apps" / "acme_tst" / "manifest.json").read_text(encoding="utf-8"))
                self.assertIn(new, m["description"])
                self.assertNotIn(old, json.dumps(m))

    def test_canary_a_rewrite_that_leaves_a_role_turns_the_leftover_check_red(self):
        real = start.rewrite

        def broken(text, m, prefix, sample, app):
            return real(text, m, prefix, sample, app).replace("ACME TST Integration", "PP Integration")

        with tempfile.TemporaryDirectory() as d:
            repo = repository(d)
            with mock.patch.object(start, "rewrite", broken):
                rc, out = run("s24_price_checker", "--prefix", PREFIX, "--into", str(repo))
            self.assertEqual(rc, 1, out)
            self.assertIn("PP Integration", out)
            self.assertFalse((repo / "apps").exists())


if __name__ == "__main__":
    unittest.main()
