"""The one-line installer for macOS and Linux (``site/install.sh``, served as developer.ivendnext.com/install.sh), run from a
fresh home: the kit by git clone and, with no git, by GitHub's archive; ivn on the PATH for good, the start file's line
written once; ivn doctor at the end; a second run updates in place. Its stand-ins are this repository (cloned over
``file://``) and its own archive (``git archive``, which carries the commit as GitHub's does).

    python3 -m unittest discover -s tools/ivn/tests -p test_install.py
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = pathlib.Path(__file__).resolve().parents[3]
INSTALL = KIT / "site" / "install.sh"
MARK = "# the ivn command (iVendNext partner kit)"
POSIX = os.name != "nt" and shutil.which("sh") and shutil.which("curl")
IN_GIT = shutil.which("git") and (KIT / ".git").exists()


@unittest.skipUnless(POSIX and IN_GIT, "a POSIX shell, curl and this kit as a git checkout are needed")
class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.head = subprocess.run(["git", "-C", str(KIT), "rev-parse", "--short=8", "HEAD"], capture_output=True,
                                   text=True, check=True).stdout.strip()

    def env(self, **more) -> dict:
        py = pathlib.Path(sys.executable).parent
        return {"HOME": str(self.home), "SHELL": "/bin/zsh", "PATH": f"{py}:/usr/bin:/bin:/usr/sbin:/sbin",
                "IVN_KIT_REPO": KIT.as_uri(), "IVN_HOSTING_URL": "http://127.0.0.1:9", "LANG": "C.UTF-8", **more}

    def run_install(self, env: dict) -> str:
        with open(INSTALL, "rb") as f:   # as `curl … | sh` runs it: the script on standard input
            r = subprocess.run(["sh"], stdin=f, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_a_fresh_home_gets_the_kit_ivn_for_good_and_doctor(self):
        out = self.run_install(self.env())
        kit = self.home / ".ivendnext" / "kit"
        self.assertIn("Nothing of iVendNext goes on this computer: your sites are ours, in the cloud.", out)
        self.assertIn(f"Fetching the kit into {kit} with git.", out)
        self.assertTrue((kit / ".git").is_dir())
        launcher = self.home / ".local" / "bin" / "ivn"
        self.assertTrue(os.access(launcher, os.X_OK))
        rc = (self.home / ".zshrc").read_text()
        self.assertEqual(rc.count(MARK), 1)
        self.assertIn(f'export PATH="{self.home}/.local/bin:$PATH"', rc)
        self.assertIn("Python ", out)                       # ivn doctor's screen
        self.assertIn("Not signed in yet.", out)
        self.assertIn("Next: ivn login", out)
        self.assertIn("Open a new terminal window", out)
        # the next day: a new window reads the start file, and ivn is found
        r = subprocess.run(["sh", "-c", f'. "{self.home}/.zshrc"; command -v ivn && ivn doctor'], env=self.env(),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(launcher), r.stdout)
        self.assertIn("Next: ivn login", r.stdout)
        # again: the kit is updated in place, the start file's line is not written twice
        out = self.run_install(self.env())
        self.assertIn(f"Updating the kit in {kit}.", out)
        self.assertIn(f"The kit is up to date: {self.head}.", out)
        self.assertEqual((self.home / ".zshrc").read_text().count(MARK), 1)
        self.assertIn("has the ivn line already", out)

    def test_bash_on_linux_and_a_path_that_has_the_folder_already(self):
        env = self.env(SHELL="/bin/bash")
        env["PATH"] = f"{self.home}/.local/bin:" + env["PATH"]
        out = self.run_install(env)
        rc = self.home / (".bash_profile" if sys.platform == "darwin" else ".bashrc")
        self.assertEqual(rc.read_text().count(MARK), 1)
        self.assertNotIn("Open a new terminal window", out)

    def test_with_no_git_the_archive_is_fetched_and_updated_in_place(self):
        zipped = self.tmp / "main.zip"
        subprocess.run(["git", "-C", str(KIT), "archive", "--format=zip", "--prefix=partner-kit-main/", "-o", str(zipped),
                        "HEAD"], check=True)
        bare = self.tmp / "bin"                       # a PATH with no git on it
        bare.mkdir()
        for tool in ("sh", "curl", "mkdir", "rm", "mv", "mktemp", "chmod", "cat", "grep", "dirname", "basename", "uname"):
            found = shutil.which(tool)
            if found:
                (bare / tool).symlink_to(found)
        (bare / "python3").symlink_to(sys.executable)
        env = self.env(PATH=str(bare), IVN_KIT_ARCHIVE=zipped.as_uri())
        out = self.run_install(env)
        kit = self.home / ".ivendnext" / "kit"
        self.assertIn("as GitHub's archive", out)
        self.assertFalse((kit / ".git").exists())
        self.assertTrue(os.access(kit / "tools" / "ivn" / "ivn", os.X_OK))
        self.assertTrue((kit / ".kit-commit").read_text().strip().startswith(self.head))
        self.assertIn("tools/ivn/ivn.py", (kit / ".kit-files").read_text().split())
        (kit / "my_notes.md").write_text("mine\n")                       # the developer's own file in the kit's folder
        self.assertIn("git: not found", out)            # doctor names what is missing
        out = self.run_install(env)
        self.assertIn(f"The kit is up to date: {self.head}.", out)
        self.assertEqual((kit / "my_notes.md").read_text(), "mine\n")


if __name__ == "__main__":
    unittest.main()
