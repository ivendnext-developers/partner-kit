"""J1 DEVSTART: `ivn new` with no sample (the blank app), `ivn doctor` and `ivn update`, against the suite's stand-ins (the
stub doors of test_ivn.py, a local git remote, a zip served as GitHub's archive), online and offline.

    python3 -m unittest discover -s tools/ivn/tests -p test_devstart.py
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_ivn import KIT, REVOKED, Base, Stub, ivn  # noqa: E402

sys.path.insert(0, str(KIT / "tools" / "manifest"))
import blank  # noqa: E402

GIT = shutil.which("git") is not None


def git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


class BlankNew(Base):
    def test_new_with_no_sample_makes_the_blank_app_through_the_same_door(self):
        rc, out = self.run_ivn("new", "acme_store_rules")
        self.assertEqual(rc, 0, out)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "Made. A blank app. CHECK GREEN · 1 tests run, 1 passed.")
        self.assertEqual(lines[-1], "Folder: apps/acme_store_rules/ (manifest.json, app.json, tests/). Read its README.md: "
                                    "what you can add, each kind with an example. Then: ivn check, ivn try")
        self.assertIn("/v1/new", self.stub.calls)
        folder = self.work / "apps" / "acme_store_rules"
        m = json.loads((folder / "manifest.json").read_text("utf-8"))
        self.assertEqual((m["prefix"], m["version"]), ("ACME STORE RULES", "1.0.0"))
        self.assertEqual([k for k, v in m.items() if isinstance(v, list)], [])

    def test_the_readme_examples_go_in_check_green_and_push(self):
        self.run_ivn("new", "acme_store_rules")
        folder = self.work / "apps" / "acme_store_rules"
        m = json.loads((folder / "manifest.json").read_text("utf-8"))
        ex = blank.examples(m["prefix"], m["app"])
        m["custom_fields"], m["notifications"] = ex["custom_fields"], ex["notifications"]
        (folder / "manifest.json").write_text(json.dumps(m, indent=1), "utf-8")
        self.in_app(folder)
        rc, out = self.run_ivn("check")
        self.assertEqual((rc, out.strip()), (0, "CHECK GREEN · 1 tests run, 1 passed"))
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 0, out)
        self.assertIn("Uploaded as 1.0.1", out)

    def test_a_sample_is_added_into_a_blank_app_later(self):
        self.run_ivn("new", "acme_store_rules")
        self.in_app(self.work / "apps" / "acme_store_rules")
        rc, out = self.run_ivn("add", "s11")
        self.assertEqual(rc, 0, out)
        self.assertIn("Added to a new draft 1.1.0", out)
        self.assertTrue(json.loads(pathlib.Path("manifest.json").read_text("utf-8")).get("workflows"))

    def test_from_still_makes_an_app_from_a_sample(self):
        _, out = self.made("s23")
        self.assertIn("Made. 1 sample, 1 app.", out)

    def test_new_offline_says_so_and_makes_nothing(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_HOSTING_URL": "http://127.0.0.1:9"}):
            rc, out = self.run_ivn("new", "acme_store_rules")
        self.assertEqual((rc, out.strip()), (1, ivn.WORDS["no_reach"]))
        self.assertFalse((self.work / "apps").exists())


class Doctor(Base):
    def setUp(self):
        super().setUp()
        p = unittest.mock.patch.object(ivn, "WHO_FILE", self.tmp / "home" / "who.json")
        p.start()
        self.addCleanup(p.stop)

    def test_one_screen_python_git_the_kit_signed_in_sites_and_next(self):
        rc, out = self.run_ivn("doctor")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"Python {ivn.platform_python()} ({sys.executable}): new enough", out)
        if GIT:
            self.assertRegex(out, r"git \d+\.\d+(\.\d+)?: new enough")
        self.assertIn(f"The kit: {ivn.KIT} (", out)
        self.assertIn("Signed in by IVN_TOKEN, a build server's token.", out)
        self.assertIn("Sites you can try on: acme.sandbox.ivend.co (one press), shop.acme.example", out)
        self.assertTrue(out.strip().splitlines()[-1].startswith("Next: ivn new <yourword>_first_app (a blank app)"), out)

    def test_a_person_signed_in_by_ivn_login_is_named(self):
        with unittest.mock.patch("webbrowser.open", return_value=True), unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": ""}):
            self.run_ivn("login")
            rc, out = self.run_ivn("doctor")
        self.assertIn("Signed in as acme-dev for Acme Retail Solutions (acme).", out)
        self.assertIn("Next: ivn new acme_first_app (a blank app)", out)
        self.assertEqual(json.loads((self.tmp / "home" / "who.json").read_text("utf-8"))["login"], "acme-dev")

    def test_next_is_never_a_new_app_where_apps_are_made_already(self):  # J6f F10
        for name in ("acme_gift_wrap", "acme_rules"):
            (self.tmp / "apps" / name).mkdir(parents=True, exist_ok=True)
            (self.tmp / "apps" / name / "app.json").write_text("{}", "utf-8")
        with unittest.mock.patch("pathlib.Path.cwd", return_value=self.tmp):
            rc, out = self.run_ivn("doctor")
        self.assertEqual(out.strip().splitlines()[-1],
                         "Next: cd apps/acme_gift_wrap, then ivn check and ivn try (your apps here: acme_gift_wrap, acme_rules)")
        with unittest.mock.patch.object(ivn, "_company_apps", return_value=["acme_rules"]):
            rc, out = self.run_ivn("doctor")  # none on this computer, one on our server
        self.assertEqual(out.strip().splitlines()[-1], "Next: ivn download acme_rules")

    def test_not_signed_in_says_so_and_next_is_login(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": ""}):
            rc, out = self.run_ivn("doctor")
        self.assertEqual(rc, 0)
        self.assertIn("Not signed in yet.", out)
        self.assertEqual(out.strip().splitlines()[-1], "Next: ivn login")

    def test_a_revoked_sign_in_is_said_and_next_is_login(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": REVOKED}):
            rc, out = self.run_ivn("doctor")
        self.assertIn("Signed out: this computer's sign-in was revoked or has expired. Run ivn login.", out)
        self.assertEqual(out.strip().splitlines()[-1], "Next: ivn login")

    def test_an_expired_sign_in_of_this_computer_is_never_also_called_signed_in(self):
        ivn.keep_token(REVOKED)
        ivn.keep_who({"login": "acme-dev", "name": "Acme", "company": "acme"})
        with unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": ""}):
            _, out = self.run_ivn("doctor")
        self.assertNotIn("Signed in as", out)
        self.assertIn("Signed out: this computer's sign-in was revoked or has expired. Run ivn login.", out)
        self.assertEqual(out.strip().splitlines()[-1], "Next: ivn login")

    def test_no_site_yet_gives_the_sandbox_link(self):
        with unittest.mock.patch.dict(Stub.ROUTES, {"/v1/sites": lambda s, b: {"company": [], "default": None}}):
            _, out = self.run_ivn("doctor")
        self.assertIn("Sites you can try on: none yet. Add one you administer with ivn sites add <address>, or request a "
                      "sandbox: https://developer.ivendnext.com/sandbox.html", out)

    def test_offline_still_says_everything_it_can(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_HOSTING_URL": "http://127.0.0.1:9"}):
            rc, out = self.run_ivn("doctor")
        self.assertEqual(rc, 0)
        self.assertIn("Python ", out)
        self.assertIn("Sites you can try on: could not reach iVendNext (no connection).", out)

    def test_in_an_app_next_is_check_then_try(self):
        self.made("s11")
        _, out = self.run_ivn("doctor")
        self.assertEqual(out.strip().splitlines()[-1], "Next: ivn check, then ivn try")

    def test_windows_says_whether_py_is_there(self):
        real = shutil.which
        with unittest.mock.patch.object(ivn, "ON_WINDOWS", True), \
                unittest.mock.patch.object(ivn.shutil, "which", lambda n: None if n == "py" else real(n)):
            _, out = self.run_ivn("doctor")
        self.assertIn("py, the Windows launcher the kit's own ivn.cmd runs: not found. The installer's ivn runs with the Python above", out)

    def test_an_older_python_is_said_in_one_line(self):
        with unittest.mock.patch.object(ivn, "MIN_PYTHON", (99, 0)):
            rc, out = self.run_ivn("doctor")
        self.assertEqual(rc, 1)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("ivn needs Python 99.0 or newer, and this is Python", out)


@unittest.skipUnless(GIT, "git is not on this computer")
class UpdateAClone(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.origin = self.tmp / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "-q", "-b", "main")
        (self.origin / "README.md").write_text("one\n")
        git(self.origin, "add", ".")
        git(self.origin, "commit", "-q", "-m", "one")
        git(self.tmp, "clone", "-q", str(self.origin), "kit")
        self.kit = self.tmp / "kit"
        p = unittest.mock.patch.object(ivn, "KIT", self.kit)
        p.start()
        self.addCleanup(p.stop)

    def run_ivn(self, *argv):
        out = io.StringIO()
        with unittest.mock.patch("sys.stdout", out):
            rc = ivn.main(list(argv))
        return rc, out.getvalue()

    def test_it_pulls_and_says_from_and_to(self):
        old = git(self.kit, "rev-parse", "--short=8", "HEAD")
        (self.origin / "README.md").write_text("two\n")
        git(self.origin, "commit", "-qam", "two")
        new = git(self.origin, "rev-parse", "--short=8", "HEAD")
        rc, out = self.run_ivn("update")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"Updating the kit in {self.kit} with git pull.", out)
        self.assertIn(f"The kit moved from {old} to {new}.", out)
        rc, out = self.run_ivn("update")
        self.assertIn(f"The kit is up to date: {new}.", out)

    def test_a_change_of_its_own_in_the_kit_stops_it_and_says_what_to_do(self):
        (self.origin / "README.md").write_text("two\n")
        git(self.origin, "commit", "-qam", "two")
        (self.kit / "README.md").write_text("mine\n")
        rc, out = self.run_ivn("update")
        self.assertEqual(rc, 1)
        self.assertIn("Not updated: git pull stopped", out)
        self.assertEqual((self.kit / "README.md").read_text(), "mine\n")


    def test_no_connection_says_to_check_it_and_leaves_the_kit_as_it_was(self):
        (self.origin / "README.md").write_text("two\n")
        git(self.origin, "commit", "-qam", "two")
        git(self.kit, "remote", "set-url", "origin", "https://127.0.0.1:9/partner-kit.git")
        rc, out = self.run_ivn("update")
        self.assertEqual(rc, 1)
        self.assertIn("otherwise check your connection", out)
        self.assertEqual((self.kit / "README.md").read_text(), "one\n")


class UpdateFromTheArchive(Base):
    def make_zip(self, files: dict, commit: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, body in files.items():
                z.writestr("partner-kit-main/" + name, body)
            z.comment = commit.encode()
        return buf.getvalue()

    def test_the_archive_is_written_over_the_kit_in_place_and_the_apps_stay(self):
        kit = self.tmp / "kit"
        (kit / "tools").mkdir(parents=True)
        (kit / "tools" / "old.py").write_text("old\n")
        (kit / "README.md").write_text("one\n")
        (kit / "apps" / "acme_x").mkdir(parents=True)
        (kit / "apps" / "acme_x" / "app.json").write_text("{}")
        (kit / ".kit-commit").write_text("aaaaaaaa11112222\n")
        (kit / ".kit-files").write_text("README.md\ntools/old.py\n")   # what the previous archive brought
        (kit / ".vscode").mkdir()
        (kit / ".vscode" / "settings.json").write_text("{}")             # the developer's own: never the archive's
        self.stub.objects["kit.zip"] = self.make_zip({"README.md": "two\n", "tools/new.py": "new\n"}, "bbbbbbbb33334444")
        with unittest.mock.patch.object(ivn, "KIT", kit), \
                unittest.mock.patch.dict(os.environ, {"IVN_KIT_ARCHIVE": self.stub.base + "/object/kit.zip"}):
            rc, out = self.run_ivn("update")
        self.assertEqual(rc, 0, out)
        self.assertIn("from GitHub's main", out)
        self.assertIn("The kit moved from aaaaaaaa to bbbbbbbb.", out)
        self.assertEqual((kit / "README.md").read_text(), "two\n")
        self.assertTrue((kit / "tools" / "new.py").is_file())
        self.assertFalse((kit / "tools" / "old.py").exists())
        self.assertTrue((kit / "apps" / "acme_x" / "app.json").is_file())
        self.assertTrue((kit / ".vscode" / "settings.json").is_file())
        self.assertEqual((kit / ".kit-files").read_text().split(), ["README.md", "tools/new.py"])

    def test_offline_leaves_the_kit_as_it_was(self):
        kit = self.tmp / "kit"
        kit.mkdir()
        (kit / "README.md").write_text("one\n")
        with unittest.mock.patch.object(ivn, "KIT", kit), \
                unittest.mock.patch.dict(os.environ, {"IVN_KIT_ARCHIVE": "http://127.0.0.1:9/kit.zip"}):
            rc, out = self.run_ivn("update")
        self.assertEqual(rc, 1)
        self.assertEqual((kit / "README.md").read_text(), "one\n")


if __name__ == "__main__":
    unittest.main()
