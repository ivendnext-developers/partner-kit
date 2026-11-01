"""This app's tests: each sample's own tests under the app's names, and the app's one service.

    python3 -m unittest discover -s tests          (from the app's folder; or -s apps/<app>/tests from your repository)

Written by New app (the kit's ``tools/manifest/start.py``). Each sample's own tests sit in ``tests/<tag>/`` and run, one
sample at a time, in a scratch folder laid out as the sample was in the kit (its code from ``service/<tag>/``, its
manifest and app.json as this app names them, the kit's helpers it tests with from ``tests/_kit/``), so they need
nothing outside this folder. Standard library only.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

APP = pathlib.Path(__file__).resolve().parents[1]
SERVICE = APP / "service"
DISPATCH = json.loads((SERVICE / "dispatch.json").read_text(encoding="utf-8"))
MOUNTS = DISPATCH["mounts"]
SECRET = "the-app-test-secret"
SITE = "shop-a.example.com"


def scratch_sample(tag: str, root: pathlib.Path) -> pathlib.Path:
    """A folder laid out as the sample was in the kit: <root>/service/<tag>/ with its tests, manifest and app.json."""
    for name in ("service", "tools"):
        (root / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(SERVICE / "_kit", root / "service" / "_kit")
    kit_tools = APP / "tests" / "_kit" / "tools"
    if kit_tools.is_dir():
        shutil.copytree(kit_tools, root / "tools", dirs_exist_ok=True)
    shutil.copytree(SERVICE / "_kit", root / "tools" / "app_template" / "service", dirs_exist_ok=True)
    part = root / "service" / tag
    if (SERVICE / tag).is_dir():
        shutil.copytree(SERVICE / tag, part, ignore=shutil.ignore_patterns("__pycache__"))
    part.mkdir(parents=True, exist_ok=True)
    own = APP / "tests" / tag
    shutil.copytree(own, part / "tests", ignore=shutil.ignore_patterns("__pycache__", "_manifest.json", "_app.json", "_README.md",
                                                                      "_manifest_path"))
    for name in ("manifest.json", "app.json", "README.md"):
        if (own / f"_{name}").is_file():
            at = name
            if name == "manifest.json" and (own / "_manifest_path").is_file():     # kept beside its code (S3: outside/)
                at = (own / "_manifest_path").read_text(encoding="utf-8").strip()
            (part / at).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(own / f"_{name}", part / at)
    # the sample's own view: in an app of several samples its code names the app's one Integration role; its own tests
    # (written for the sample alone) read its own role, so the scratch copy names that one
    app_role, own_role = f"{DISPATCH.get('prefix')} Integration", f"{MOUNTS[tag]['prefix']} Integration"
    if app_role != own_role:
        for f in part.rglob("*"):
            if f.is_file() and f.suffix in (".py", ".json", ".md", ".txt"):
                text = f.read_text(encoding="utf-8")
                fixed = re.sub(rf"(?<![A-Za-z0-9]){re.escape(app_role)}(?![A-Za-z0-9])", own_role, text)
                if fixed != text:
                    f.write_text(fixed, encoding="utf-8")
    return part


class EachSample(unittest.TestCase):
    """Each sample's own tests, under the app's names."""

    def test_each_samples_own_tests_pass_under_the_apps_names(self):
        for tag in MOUNTS:
            if not (APP / "tests" / tag).is_dir():
                continue
            with self.subTest(sample=MOUNTS[tag]["sample"]), tempfile.TemporaryDirectory() as d:
                part = scratch_sample(tag, pathlib.Path(d))
                env = {k: v for k, v in os.environ.items() if not k.startswith(("IVN_", "LIBRARY_", "PP_"))}
                env.update(PARTNER_KIT=d, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH="")
                r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(part / "tests"), "-p", "test_*.py"],
                                   cwd=d, env=env, capture_output=True, text=True, timeout=900)
                ran = re.findall(r"^Ran (\d+) tests?", r.stderr, re.M)
                print(f"\nSAMPLE {MOUNTS[tag]['sample']} ran={ran[-1] if ran else 0} ok={r.returncode == 0}", file=sys.stderr)
                self.assertEqual(r.returncode, 0, r.stderr[-3000:])


def sign(body: bytes, secret=SECRET) -> dict:
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "X-iVendNext-Site": SITE,
            "X-iVendNext-Test": "1", "X-iVendNext-Request-Id": "t-1"}


def event(path: str, body: bytes, headers: dict, method="POST") -> dict:
    return {"httpMethod": method, "path": path, "headers": headers, "body": base64.b64encode(body).decode(),
            "isBase64Encoded": True}


class TheService(unittest.TestCase):
    """The one service: each connection point answers a signed test call without running its part's code."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        store = pathlib.Path(cls.tmp.name) / "shops.json"
        app = DISPATCH["app"]
        names = {}
        for m in MOUNTS.values():
            for p in (m.get("points") or {}).values():
                names[f"{app}:sub:{p['key']}"] = SECRET
                names[f"{app}:{p['key']}"] = SECRET
        store.write_text(json.dumps({SITE: {"site": SITE, "url": f"https://{SITE}", "secrets": names, "previous": {}}}))
        cls.env = {k: os.environ.get(k) for k in ("IVN_LIBRARY_APP", "IVN_SHOPS_FILE", "PP_STATE")}
        os.environ.update(IVN_LIBRARY_APP=app, IVN_SHOPS_FILE=str(store), PP_STATE=cls.tmp.name)
        sys.path.insert(0, str(SERVICE))
        import app as service  # noqa: E402
        cls.service = service

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        cls.tmp.cleanup()

    def call(self, path, headers=None, body=b"{}", method="POST"):
        with redirect_stdout(io.StringIO()) as log:
            out = self.service.lambda_handler(event(path, body, headers if headers is not None else sign(body), method))
        return out["statusCode"], json.loads(out["body"]), log.getvalue()

    def test_the_parts_that_read_the_feed_are_handed_by_one_reader(self):
        readers = (DISPATCH.get("feed") or {}).get("parts") or {}
        if not readers:
            self.skipTest("no part of this app reads the site's feed")
        self.assertIsNotNone(self.service.HUB)             # every part's poll is handed: none marks the others' events done
        self.assertIs(sys.modules[self.service.HANDOFF_MODULE].HUB, self.service.HUB)
        self.assertEqual(set(self.service.HUB.reads), set(readers))
        self.assertEqual(DISPATCH["feed"]["schedule"], "feed")

    def test_health(self):
        self.assertEqual(self.call("/health", {}, b"", "GET")[:2], (200, {"status": "ok"}))

    def test_every_connection_point_answers_a_signed_test_call(self):
        points = [(path, p) for m in MOUNTS.values() for path, p in (m.get("points") or {}).items()]
        for path, p in points:
            with self.subTest(point=p["key"]):
                status, out, log = self.call(path)
                self.assertEqual((status, out), (200, {"test": "ok", "point": p["key"]}))
                self.assertIn('"outcome": "test"', log)

    def test_a_mis_signed_test_call_is_refused(self):
        for m in MOUNTS.values():
            for path, p in (m.get("points") or {}).items():
                with self.subTest(point=p["key"]):
                    self.assertNotEqual(self.call(path, sign(b"{}", "not-the-secret"))[0], 200)

    def test_a_route_no_part_has_is_404(self):
        self.assertEqual(self.call("/nothing/here")[0], 404)
        for tag in MOUNTS:
            self.assertNotEqual(self.call(f"/{tag}/no_such_point")[0], 200)


class TheFolder(unittest.TestCase):
    def test_the_readme_says_what_is_in_it_and_how_to_run_it(self):
        text = (APP / "README.md").read_text(encoding="utf-8")
        for section in ("What is in this folder", "What you can change safely", "What to leave alone",
                        "Run it on your laptop", "Run it on your own server", "Change it with your AI assistant"):
            self.assertIn(f"## {section}", text)
        for tag in MOUNTS:
            where = f"service/{tag}/" if (SERVICE / tag).is_dir() else f"tests/{tag}/"
            self.assertIn(f"`{where}`", text)

    def test_its_licence_and_third_party_notices(self):
        self.assertTrue((APP / "LICENSE").is_file())
        third = (APP / "THIRD_PARTY.md").read_text(encoding="utf-8")
        for m in MOUNTS.values():
            self.assertIn(m["sample"], third)

    def test_the_kits_helpers_are_marked_as_copies(self):
        for f in (SERVICE / "_kit").rglob("*.py"):
            self.assertTrue(f.read_text(encoding="utf-8").startswith("# COPY of the iVendNext partner kit's"), f.name)


if __name__ == "__main__":
    unittest.main()
