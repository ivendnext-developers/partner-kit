"""One app from several samples, Add a sample, and the newer-version notice (tools/manifest/combine.py):

    python3 -m unittest discover -s tools/manifest/tests -p 'test_combine.py' -v

Each refusal's words are fixed (M01-M05, M34, M35). Each app is made in a scratch folder; the samples are
the kit's own, except where a refusal needs a pair the kit does not have (two modules at one extension point, two samples
answering the same route): those are made from the kit's samples in a scratch samples folder.
"""
import copy
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
KIT = pathlib.Path(os.environ.get("PARTNER_KIT") or HERE.parents[2]).resolve()
sys.path.insert(0, str(HERE.parent))
import combine  # noqa: E402
import rename  # noqa: E402
import start  # noqa: E402

PREFIX = "ACME HK"


def tree(folder: pathlib.Path) -> dict:
    """{path: sha256} of every file: a byte compare of a whole folder."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def scratch_sample(samples: pathlib.Path, src: str, name: str, prefix: str, edit=None) -> None:
    """A copy of a kit sample under another name and prefix, in a scratch samples folder."""
    shutil.copytree(KIT / "samples" / src, samples / name, ignore=shutil.ignore_patterns("__pycache__", "screenshots"))
    mp = samples / name / "manifest.json"
    m, _ = rename.rename(json.loads(mp.read_text(encoding="utf-8")), prefix)
    if edit:
        edit(m)
    mp.write_text(json.dumps(m, indent=1), encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.into = pathlib.Path(self.tmp.name)

    def make(self, samples, prefix=PREFIX, **kw):
        out = io.StringIO()
        folder = combine.combine(samples, prefix, self.into, out=out, **kw)
        return folder, out.getvalue()

    def manifest(self, folder):
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    def app_json(self, folder):
        return json.loads((folder / "app.json").read_text(encoding="utf-8"))

    def check(self, folder):
        r = subprocess.run([sys.executable, "-I", str(KIT / "tools" / "check" / "check.py"), str(folder)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("CHECK GREEN", r.stdout)


class Combine(Base):
    @classmethod
    def setUpClass(cls):
        cls.ctmp = tempfile.TemporaryDirectory()
        out = io.StringIO()
        cls.app = combine.combine(["s23_till_guard", "s22_customer_loyalty"], PREFIX, pathlib.Path(cls.ctmp.name), test=True,
                                  out=out)
        cls.out = out.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.ctmp.cleanup()

    def test_two_samples_make_one_app_with_the_rows_summary_lines_and_its_tests_run_green(self):
        lines = self.out.splitlines()
        self.assertRegex(lines[0], r"^Made\. 2 samples, 1 app\. CHECK GREEN · (\d+) tests run, \1 passed\.$")
        self.assertGreater(int(re.search(r"(\d+) tests run", lines[0]).group(1)), 200)   # both samples' own tests ran
        self.assertEqual(lines[1], "What is in it: Till guard rules (tgr: a check at Pay, a capture on scan), Customer-owned "
                                   "loyalty (lyl: members, cash back, a till key, a wallet). One service, one feed, one app "
                                   "user.")
        self.assertEqual(self.app.name, "acme_hk")

    def test_each_samples_names_take_its_tag(self):
        m = self.manifest(self.app)
        names = {d["name"] for d in m["doctypes"]}
        self.assertIn("ACME HK TGR Settings", names)
        self.assertTrue(any(n.startswith("ACME HK LYL ") for n in names))
        self.assertTrue(all(n.startswith(("ACME HK TGR ", "ACME HK LYL ")) for n in names), names)
        keys = {s["key"] for s in m["extension_subscriptions"]}
        self.assertEqual(keys, {"tgr_guard", "tgr_on_scan"})
        self.assertEqual([k["key"] for k in m["remote_keys"]], ["acme_hk_lyl_member"])
        for f in m.get("custom_fields") or []:
            self.assertTrue(f["fieldname"].startswith(("acme_hk_tgr_", "acme_hk_lyl_")), f["fieldname"])
        self.assertEqual((m["prefix"], m["app"]), ("ACME HK", "acme_hk"))

    def test_one_integration_role_holds_every_samples_rights(self):
        m = self.manifest(self.app)
        roles = {r for s in json.dumps(m).split('"') for r in [s] if r.endswith(" Integration")}
        self.assertEqual(roles, {"ACME HK Integration"})
        rows = [p for d in m["doctypes"] for p in d.get("permissions") or [] if p.get("role", "").endswith("Integration")]
        self.assertTrue(rows and all(p["role"] == "ACME HK Integration" for p in rows))
        self.assertTrue({d["name"] for d in m["doctypes"] if any(p["role"] == "ACME HK Integration"
                                                                 for p in d.get("permissions") or [])}
                        & {"ACME HK TGR Settings"})

    def test_canary_no_tagged_integration_role_is_written(self):
        text = (self.app / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("ACME HK TGR Integration", text)
        self.assertNotIn("ACME HK LYL Integration", text)
        for p in (self.app / "service").rglob("*.py"):
            self.assertNotRegex(p.read_text(encoding="utf-8"), r"ACME HK (TGR|LYL) Integration", p.name)

    def test_one_feed_with_the_union_of_the_events(self):
        feeds = self.manifest(self.app)["registered_applications"]
        self.assertEqual(len(feeds), 1)
        self.assertEqual(feeds[0]["name"], "ACME HK Feed")
        self.assertIn("ACME HK TGR Settings", feeds[0]["events"])
        self.assertIn("Customer", feeds[0]["events"])

    def test_one_service_mounts_each_sample_under_its_tag_and_fills_its_prefix_setting(self):
        d = json.loads((self.app / "service" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertEqual(set(d["mounts"]), {"tgr", "lyl"})
        self.assertEqual(d["mounts"]["tgr"]["prefix_setting"], "TGR_PREFIX")
        self.assertEqual(d["mounts"]["tgr"]["prefix"], "ACME HK TGR")
        paths = [p for m in d["mounts"].values() for p in m["points"]]
        self.assertEqual(len(paths), len(set(paths)))
        for tag, m in d["mounts"].items():
            self.assertTrue(all(p.startswith(f"/{tag}/") for p in m["points"]), m["points"])
        aj = self.app_json(self.app)
        self.assertEqual((aj["runs"], aj["handler"], aj["package"]), ("function", "service/app.lambda_handler", ["service"]))
        names = [e["name"] for e in aj["env"]]
        self.assertNotIn("TGR_PREFIX", names)
        self.assertNotIn("LYL_PREFIX", names)
        self.assertEqual(aj["schedule"], {"feed": "rate(1 minute)"})      # the app's one reader runs S22's pass
        self.assertEqual(d["feed"], {"schedule": "feed", "parts": {"lyl": {"pass": "pass", "reads": [
            "Customer", "POS Invoice", "Purchase Receipt"]}}})

    def test_every_setting_carries_purpose_required_and_together(self):
        for e in self.app_json(self.app)["env"]:
            self.assertTrue(isinstance(e.get("purpose"), str) and e["purpose"].strip(), e)
            self.assertIsInstance(e.get("required"), bool)
            self.assertIsInstance(e.get("together"), list)

    def test_the_kits_check_is_green(self):
        self.check(self.app)

    def test_the_readme_says_what_is_in_the_folder_and_how_to_run_it(self):
        text = (self.app / "README.md").read_text(encoding="utf-8")
        for s in ("What is in this folder", "What you can change safely", "What to leave alone", "Run it on your laptop",
                  "Run it on your own server", "Change it with your AI assistant"):
            self.assertIn(f"\n## {s}\n", text)
        what = text.split("## What is in this folder", 1)[1].split("\n## ", 1)[0]
        for row in ("| `service/tgr/` | Till guard rules, the check at Pay and the capture on scan |",
                    "| `service/lyl/` | Customer-owned loyalty |",
                    "| `manifest.json` | the lists, fields, keys and points the site installs |",
                    "| `app.json` | the app's name, version, settings and card |"):
            self.assertIn(row, what)
        server = text.split("## Run it on your own server", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`ivn package` writes `package.zip` for your own function host", server)
        for e in self.app_json(self.app)["env"]:
            self.assertIn(f"`{e['name']}`: {e['purpose']}", server)
        self.assertIn("Give it a public https address and put that address on Where the service runs.", server)
        self.assertIn("Nothing to install: the samples use Python's standard library.", text)
        self.assertIn("python3 -m unittest discover -s apps/acme_hk/tests", text)
        self.assertIn("python3 apps/acme_hk/service/app.py --local", text)
        self.assertIn("It reads test values from .env.local, which New app wrote for you; put your own outside keys there. "
                      "It answers on http://localhost:8000.", text)
        self.assertIn("Change it with your AI assistant: open your copy of the kit in it. It reads AGENTS.md, which knows "
                      "this folder.", text)
        self.assertIn("names already installed at a site; the samples record in `app.json`; `service/_kit/`".lower(),
                      text.lower())

    def test_licence_and_third_party_notices(self):
        self.assertEqual((self.app / "LICENSE").read_bytes(), (KIT / "tools" / "app_template" / "LICENSE").read_bytes())
        third = (self.app / "THIRD_PARTY.md").read_text(encoding="utf-8")
        self.assertIn("s23_till_guard", third)
        self.assertIn("s22_customer_loyalty", third)
        readme = (self.app / "README.md").read_text(encoding="utf-8")
        self.assertIn("`LICENSE`, `THIRD_PARTY.md`", readme)

    def test_the_samples_record_lives_in_app_json(self):
        rec = self.app_json(self.app)["samples"]
        self.assertEqual([r["name"] for r in rec], ["s23_till_guard", "s22_customer_loyalty"])
        for r in rec:
            self.assertTrue(set(r) >= {"name", "version", "kit_commit", "files", "entries"})
            for path, h in r["files"].items():
                self.assertEqual(hashlib.sha256((self.app / path).read_bytes()).hexdigest(), h, path)
        self.assertEqual(rec[0]["version"], json.loads((KIT / "samples/s23_till_guard/app.json").read_text())["version"])
        self.assertIn("manifest:title", rec[0]["entries"])

    def test_env_local_holds_test_values_only(self):
        text = (self.app / ".env.local").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^IVN_TEST_SECRET=[0-9a-f]{48}$")
        self.assertIn(".env.local", (self.app / ".gitignore").read_text())

    def test_the_kits_helpers_are_copied_with_a_copy_header(self):
        for p in (self.app / "service" / "_kit").rglob("*"):
            if p.is_file():
                self.assertTrue(p.read_text(encoding="utf-8").startswith("# COPY of the iVendNext partner kit's"), p)
        for p in (KIT / "tools" / "app_template" / "service").glob("*.py"):
            copy_ = self.app / "service" / "_kit" / p.name
            if p.name in ("app.py", "core.py"):               # the template's example service is not a helper
                self.assertFalse(copy_.exists())
                continue
            text = copy_.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# COPY of the iVendNext partner kit's tools/app_template/service/" + p.name))
            self.assertTrue(text.endswith(p.read_text(encoding="utf-8")))

    def test_the_folder_moved_outside_the_kit_runs_its_tests_and_its_local_service(self):
        with tempfile.TemporaryDirectory() as d:
            moved = pathlib.Path(d) / "elsewhere" / "acme_hk"
            shutil.copytree(self.app, moved)
            for p in moved.rglob("*"):
                if p.is_file() and p.suffix in (".py", ".json", ".md"):
                    self.assertNotIn(str(KIT), p.read_text(encoding="utf-8"), p)
            env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
            r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=moved, env=env,
                               capture_output=True, text=True, timeout=1800)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertEqual(len(re.findall(r"SAMPLE \S+ ran=\d+ ok=True", r.stderr)), 2, r.stderr[-1000:])
            sys.path.insert(0, str(HERE))
            import local_call  # noqa: E402
            answers = local_call.call_every_point(moved)
            self.assertTrue(answers)
            for path, signed, mis in answers:
                self.assertEqual(signed[0], 200, path)
                self.assertEqual(signed[1]["test"], "ok")
                self.assertEqual(mis[0], 401, path)


class Refusals(Base):
    def test_m01_two_samples_capture_at_the_scan(self):
        with self.assertRaises(combine.Refused) as e:
            self.make(["s20_capture", "s23_till_guard"])
        self.assertEqual(e.exception.code, "M01")
        self.assertEqual(e.exception.text,
                         "These samples both capture at the scan: S20 Warranty capture and a member code and S23 Till guard "
                         "rules. A till event takes one capture. Untick one of them, or take S23's scan rule into S20's code "
                         "by hand after the app is made.")
        self.assertFalse((self.into / "apps" / "acme_hk").exists())

    def test_m34_a_sample_that_answers_the_till_from_its_own_server(self):
        with self.assertRaises(combine.Refused) as e:
            self.make(["s1_warranty", "s23_till_guard"])
        self.assertEqual(e.exception.code, "M34")
        self.assertEqual(e.exception.text,
                         "S1 Warranty terms answers the till from its own server, with no hosting order (app.json) the app's "
                         "one service can run. Untick it, or copy it by hand as its README says.")
        self.assertFalse((self.into / "apps").exists())                  # nothing is made

    def test_m35_a_sample_with_no_manifest_of_its_own(self):
        with self.assertRaises(combine.Refused) as e:
            self.make(["s5_config_pack", "s23_till_guard"])
        self.assertEqual(e.exception.code, "M35")
        self.assertEqual(e.exception.text,
                         "S5 the configuration pack: reasons, IMEI, a line detail, member pricing has no manifest of its "
                         "own: it cannot be made into an app. Copy it by hand as its README says.")
        self.assertFalse((self.into / "apps").exists())

    def test_m02_four_checks_at_pay(self):
        with self.assertRaises(combine.Refused) as e:
            self.make(["s23_till_guard", "s32_coupon_rules", "s42_optical_prescriptions", "s46_payment_method_rules"])
        self.assertRegex(e.exception.text, r"^This app would run 4 checks at Pay: .+\. A sale runs at most 3 checks, 10 "
                                           r"seconds together\. Untick one\.$")
        for n in ("S23", "S32", "S42", "S46"):
            self.assertIn(n, e.exception.text)

    def test_m03_two_modules_at_one_extension_point(self):
        samples = self.into / "samples"
        samples.mkdir()
        for name, prefix in (("s91_mod_a", "PP MDA"), ("s92_mod_b", "PP MDB")):
            scratch_sample(samples, "s57_donation_intake", name, prefix,
                           lambda m: m.__setitem__("extension_modules", [{"key": "price_rule", "point": "pricing"}]))
        with self.assertRaises(combine.Refused) as e:
            self.make(["s91_mod_a", "s92_mod_b"], samples_dir=samples)
        self.assertEqual(e.exception.text, "S91 Donation intake with a donor receipt and S92 Donation intake with a donor "
                                           "receipt both add a module at the same extension point (pricing). A partner may "
                                           "add one module per extension point. Untick one.")

    def test_the_app_runs_all_the_time_when_any_sample_does(self):
        samples = self.into / "samples"
        samples.mkdir()
        shutil.copytree(KIT / "samples" / "s22_customer_loyalty", samples / "s22_customer_loyalty",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(KIT / "samples" / "s23_till_guard", samples / "s23_till_guard",
                        ignore=shutil.ignore_patterns("__pycache__"))
        aj = json.loads((samples / "s23_till_guard" / "app.json").read_text(encoding="utf-8"))
        aj["runs"] = "container"
        for k in ("handler", "package"):
            aj.pop(k)
        (samples / "s23_till_guard" / "app.json").write_text(json.dumps(aj, indent=1), encoding="utf-8")
        folder, _ = self.make(["s23_till_guard", "s22_customer_loyalty"], samples_dir=samples)
        app = self.app_json(folder)
        self.assertEqual(app["runs"], "container")
        self.assertNotIn("handler", app)
        self.assertNotIn("schedule", app)
        self.assertTrue((folder / "Dockerfile").is_file())
        self.assertIn("docker build -t acme_hk .", (folder / "README.md").read_text(encoding="utf-8"))
        self.check(folder)

    def test_canary_two_samples_on_the_same_route_are_mounted_apart(self):
        samples = self.into / "samples"
        samples.mkdir()
        shutil.copytree(KIT / "samples" / "s2_bins", samples / "s2_bins", ignore=shutil.ignore_patterns("__pycache__"))
        scratch_sample(samples, "s2_bins", "s93_bins_again", "PP BLY")
        folder, _ = self.make(["s2_bins", "s93_bins_again"], samples_dir=samples)
        d = json.loads((folder / "service" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertEqual(set(d["mounts"]["bln"]["points"]), {"/bln/point/where_is_it"})
        self.assertEqual(set(d["mounts"]["bly"]["points"]), {"/bly/point/where_is_it"})
        urls = [k["endpoint_url"] for k in self.manifest(folder)["remote_keys"]]
        self.assertEqual(len(urls), len(set(urls)))


class Add(Base):
    def test_add_from_one_keeps_the_first_samples_names_and_tags_the_added_one(self):
        folder, _ = self.make(["s23_till_guard"])
        before = self.manifest(folder)
        self.assertIn("ACME HK Settings", {d["name"] for d in before["doctypes"]})
        result = combine.add("s22_customer_loyalty", folder)
        after = self.manifest(folder)
        for section in ("doctypes", "custom_fields", "extension_subscriptions"):
            for item in before.get(section) or []:
                self.assertIn(item, after[section])
        names = {d["name"] for d in after["doctypes"]} - {d["name"] for d in before["doctypes"]}
        self.assertTrue(names and all(n.startswith("ACME HK LYL ") for n in names), names)
        self.assertEqual(result.version, "1.1.0")
        self.assertEqual(self.app_json(folder)["version"], "1.1.0")
        self.assertEqual([r["name"] for r in self.app_json(folder)["samples"]], ["s23_till_guard", "s22_customer_loyalty"])
        self.assertEqual(len(after["registered_applications"]), 1)
        self.check(folder)

    def edited_app(self):
        folder, _ = self.make(["s23_till_guard", "s11_approvals"])
        mine = folder / "service" / "tgr" / "guard.py"
        mine.write_text(mine.read_text(encoding="utf-8") + "\n# our own rule, added by hand\n", encoding="utf-8")
        m = self.manifest(folder)
        m["title"] = "Acme's own till rules"
        (folder / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        return folder, mine

    def test_add_with_edits_kept(self):
        folder, mine = self.edited_app()
        edited = mine.read_bytes()
        result = combine.add("s22_customer_loyalty", folder)
        self.assertEqual(mine.read_bytes(), edited)
        self.assertEqual(self.manifest(folder)["title"], "Acme's own till rules")
        self.assertIn("service/tgr/guard.py", result.kept_files)
        self.assertIn("manifest:title", result.kept_entries)
        lines = result.lines(self.manifest(folder))
        self.assertEqual(lines[0], "Added to a new draft 1.1.0, on no site yet.")
        self.assertEqual(lines[1], "Your changes are kept: service/tgr/guard.py and the app's title.")
        self.check(folder)

    def test_m04_refused_when_the_sample_must_change_an_entry_you_changed(self):
        folder, _ = self.make(["s23_till_guard", "s11_approvals"])
        m = self.manifest(folder)
        m["registered_applications"][0]["description"] = "our own words for the feed"
        (folder / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        before = tree(folder)
        with self.assertRaises(combine.Refused) as e:
            combine.add("s22_customer_loyalty", folder)
        self.assertEqual(e.exception.text, "Not added: S22 must change the entry manifest:registered_applications:ACME HK "
                                           "Feed, which you changed. Nothing in your app was changed. Put that entry back "
                                           "as it was, or add S22's part by hand.")
        self.assertEqual(e.exception.page, "Not added: S22 must change the entry what the app reads from the site (new "
                                           "sales and customers), which you changed. Nothing in your app was changed. Ask "
                                           "your developer to put that entry back, or to add S22's part by hand.")
        self.assertEqual(tree(folder), before)

    def test_m05_refused_when_your_code_uses_a_name_the_sample_needs(self):
        folder, _ = self.make(["s23_till_guard", "s11_approvals"])
        (folder / "service" / "ours.py").write_text('MEMBERS = "ACME HK LYL Member"\n', encoding="utf-8")
        before = tree(folder)
        with self.assertRaises(combine.Refused) as e:
            combine.add("s22_customer_loyalty", folder)
        self.assertEqual(e.exception.text, "Not added: S22 needs the name ACME HK LYL Member, which your own code already "
                                           "uses. Nothing in your app was changed. Rename yours, then add S22 again.")
        self.assertEqual(tree(folder), before)

    def test_kept_files_are_named_and_the_samples_copy_saved(self):
        folder, _ = self.make(["s23_till_guard", "s22_customer_loyalty"])
        mine = folder / "service" / "lyl" / "service" / "app.py"
        mine.write_text(mine.read_text(encoding="utf-8") + "\n# our change\n", encoding="utf-8")
        edited = mine.read_bytes()
        result = combine.add("s22_customer_loyalty", folder)
        self.assertEqual(mine.read_bytes(), edited)
        self.assertIn("service/lyl/service/app.py", result.kept_files)
        version = json.loads((KIT / "samples/s22_customer_loyalty/app.json").read_text())["version"]
        saved = folder / ".samples" / f"s22-{version}" / "service" / "lyl" / "service" / "app.py"
        self.assertTrue(saved.is_file())
        rec = next(r for r in self.app_json(folder)["samples"] if r["name"] == "s22_customer_loyalty")
        self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), rec["files"]["service/lyl/service/app.py"])
        self.assertNotEqual(saved.read_bytes(), edited)
        self.assertIn(f".samples/s22-{version}/", " ".join(result.lines()))
        self.check(folder)

    def test_canary_add_never_overwrites_a_changed_file_or_entry(self):
        """Taking S22 again over an app that has it: S22's own file and S22's own entry, both changed, are kept."""
        folder, _ = self.make(["s23_till_guard", "s22_customer_loyalty"])
        mine = folder / "service" / "lyl" / "service" / "app.py"
        mine.write_text(mine.read_text(encoding="utf-8") + "\n# our change\n", encoding="utf-8")
        edited = mine.read_bytes()
        m = self.manifest(folder)
        dt = next(d for d in m["doctypes"] if d["name"].startswith("ACME HK LYL "))
        dt["track_changes"] = not dt.get("track_changes")
        (folder / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        result = combine.add("s22_customer_loyalty", folder)
        self.assertEqual(mine.read_bytes(), edited)
        after = next(d for d in self.manifest(folder)["doctypes"] if d["name"] == dt["name"])
        self.assertEqual(after, dt)
        self.assertIn(f"manifest:doctypes:{dt['name']}", result.kept_entries)

    def test_a_refusal_by_the_kits_check_changes_nothing(self):
        folder, _ = self.make(["s23_till_guard", "s11_approvals"])
        aj = self.app_json(folder)
        aj["env"].append({"name": "OUR_OWN", "required": False, "together": []})      # no purpose: the check refuses
        (folder / "app.json").write_text(json.dumps(aj, indent=1), encoding="utf-8")
        before = tree(folder)
        with self.assertRaises(combine.Refused) as e:
            combine.add("s22_customer_loyalty", folder)
        self.assertTrue(e.exception.text.startswith("Not added: the kit's check refused the result."), e.exception.text)
        self.assertEqual(tree(folder), before)

    def test_an_app_without_a_samples_record_is_refused_in_words(self):
        folder, _ = self.make(["s23_till_guard"])
        aj = self.app_json(folder)
        aj.pop("samples")
        (folder / "app.json").write_text(json.dumps(aj), encoding="utf-8")
        with self.assertRaises(combine.Refused) as e:
            combine.add("s22_customer_loyalty", folder)
        self.assertIn("no samples record", e.exception.text)


class ReviewFolds(Base):
    """What the leaf review found, each held by a test."""

    def test_taking_the_first_sample_again_keeps_its_untagged_names(self):
        folder, _ = self.make(["s23_till_guard"])
        combine.add("s22_customer_loyalty", folder)
        before = {s["key"] for s in self.manifest(folder)["extension_subscriptions"]}
        combine.add("s23_till_guard", folder)
        m = self.manifest(folder)
        self.assertEqual({s["key"] for s in m["extension_subscriptions"]}, before)
        self.assertIn("ACME HK Settings", {d["name"] for d in m["doctypes"]})
        self.assertFalse([d for d in m["doctypes"] if d["name"].startswith("ACME HK TGR ")])
        self.check(folder)

    def test_add_gives_the_limits_words_over_the_whole_app(self):
        folder, _ = self.make(["s23_till_guard"])
        before = tree(folder)
        with self.assertRaises(combine.Refused) as e:
            combine.add("s20_capture", folder)
        self.assertEqual(e.exception.code, "M01")
        self.assertTrue(e.exception.text.startswith("These samples both capture at the scan: S20 "))
        folder2, _ = self.make(["s32_coupon_rules", "s42_optical_prescriptions", "s46_payment_method_rules"], prefix="ACME CK")
        with self.assertRaises(combine.Refused) as e:
            combine.add("s23_till_guard", folder2)
        self.assertEqual(e.exception.code, "M02")
        self.assertTrue(e.exception.text.startswith("This app would run 4 checks at Pay: "))
        self.assertEqual(tree(folder), before)

    def test_a_sample_whose_service_has_no_hosting_order_is_refused_in_words(self):
        with self.assertRaises(combine.Refused) as e:
            self.make(["s23_till_guard", "s28_merge_and_history"])
        self.assertEqual(e.exception.code, "M34")
        self.assertIn("S28 ", e.exception.text)

    def test_a_sample_whose_titles_repeat_is_one_app(self):
        for sample, prefix in (("s41_regulated_register", "ACME RR"), ("s55_front_of_house", "ACME FH")):
            with self.subTest(sample):
                folder, _ = self.make([sample], prefix=prefix)
                self.check(folder)

    def test_a_setting_raised_by_an_added_sample_is_recorded(self):
        folder, _ = self.make(["s23_till_guard"])
        combine.add("s25_gift_on_spend", folder)
        rec = {i for r in self.app_json(folder)["samples"] for i in r["entries"]}
        self.assertIn("app.json:timeout", rec)
        combine.add("s32_coupon_rules", folder)
        self.check(folder)

    def test_a_newer_kit_refreshes_its_helpers_and_nothing_is_refused(self):
        folder, _ = self.make(["s23_till_guard", "s22_customer_loyalty"])
        real = combine.kit_commit
        self.addCleanup(setattr, combine, "kit_commit", real)
        combine.kit_commit = lambda kit=None: "f00dcafe0000"
        result = combine.add("s11_approvals", folder)
        self.assertEqual(result.kept_files, [])
        self.assertIn("at f00dcafe0000.", (folder / "service" / "_kit" / "shops.py").read_text(encoding="utf-8").split("\n")[0])
        held = {p for r in self.app_json(folder)["samples"] for p in r["files"]}
        for p in (folder / "service" / "_kit").rglob("*.py"):
            self.assertIn(p.relative_to(folder).as_posix(), held)

    def test_an_entry_and_a_file_you_removed_stay_removed_and_are_named(self):
        folder, _ = self.make(["s23_till_guard", "s22_customer_loyalty"])
        m = self.manifest(folder)
        gone = m["reports"].pop(0)["name"]
        (folder / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        removed = folder / "service" / "lyl" / "service" / "receipts.py"
        removed.unlink()
        result = combine.add("s22_customer_loyalty", folder)
        self.assertNotIn(gone, {r["name"] for r in self.manifest(folder)["reports"]})
        self.assertIn(f"manifest:reports:{gone}", result.kept_entries)
        self.assertFalse(removed.exists())
        self.assertIn("service/lyl/service/receipts.py", result.kept_files)

    def test_add_never_writes_through_a_link(self):
        folder, _ = self.make(["s23_till_guard"])
        outside = self.into / "elsewhere.md"
        outside.write_text("mine\n", encoding="utf-8")
        (folder / "README.md").unlink()
        (folder / "README.md").symlink_to(outside)
        with self.assertRaises(combine.Refused) as e:
            combine.add("s22_customer_loyalty", folder)
        self.assertEqual(e.exception.code, "link")
        self.assertEqual(outside.read_text(encoding="utf-8"), "mine\n")

    def test_one_part_never_finds_anothers_modules(self):
        folder, _ = self.make(["s23_till_guard", "s22_customer_loyalty"])
        probe = (
            "import json, os, sys\n"
            f"sys.path.insert(0, {str(folder / 'service')!r})\n"
            "os.environ.update(IVN_LIBRARY_APP='acme_hk', IVN_SHOPS_FILE=os.path.join(sys.argv[1], 's.json'), PP_STATE=sys.argv[1])\n"
            "import app\n"
            "for path in ('/tgr/check', '/lyl/member'):\n"
            "    app.lambda_handler({'httpMethod': 'POST', 'path': path, 'headers': {}, 'body': '{}'})\n"
            "own = [n for n in ('guard', 'loyalty', 'worker', 'money', 'shop') if n in sys.modules]\n"
            "print(json.dumps({'left': own, 'parts': sorted(app._parts)}))\n")
        r = subprocess.run([sys.executable, "-I", "-c", probe, self.tmp.name], capture_output=True, text=True, timeout=120)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out, {"left": [], "parts": ["lyl", "tgr"]}, r.stderr[-1500:])

    def test_the_one_sample_command_makes_an_app_folder_add_can_extend(self):
        rc = start.main(["s23_till_guard", "--prefix", "ACME HK", "--into", str(self.into)])
        self.assertEqual(rc, 0)
        folder = self.into / "apps" / "acme_hk"
        self.assertTrue((folder / "service" / "dispatch.json").is_file())
        self.assertEqual(start.main(["--add", "s22_customer_loyalty", "--into", str(folder)]), 0)
        self.assertEqual([r["name"] for r in self.app_json(folder)["samples"]], ["s23_till_guard", "s22_customer_loyalty"])


class OneReader(Base):
    """Two samples that each read the site's feed (S22 and S25): one registration, read once by the app, each event handed
    to every part that registered its record type, and marked done only when every one of them has handled it. The run
    itself is one_reader.py, in a process of its own, with each part's real code and its own sample's fake shop."""

    @classmethod
    def setUpClass(cls):
        cls.ctmp = tempfile.TemporaryDirectory()
        cls.app = combine.combine(["s22_customer_loyalty", "s25_gift_on_spend"], PREFIX, pathlib.Path(cls.ctmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.ctmp.cleanup()

    def drive(self, scenario: str, app=None) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("IVN_", "LIBRARY_", "PP_"))}
        with tempfile.TemporaryDirectory() as state:
            r = subprocess.run([sys.executable, str(HERE / "one_reader.py"), str(app or self.app), state, scenario],
                               capture_output=True, text=True, timeout=600, env=dict(env, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_one_feed_registration_and_one_reader_for_both_parts(self):
        feeds = self.manifest(self.app)["registered_applications"]
        self.assertEqual([(f["name"], f["events"]) for f in feeds],
                         [("ACME HK Feed", ["Customer", "POS Invoice", "Purchase Receipt"])])
        self.assertEqual(self.app_json(self.app)["schedule"], {"feed": "rate(1 minute)"})
        d = json.loads((self.app / "service" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertEqual(d["feed"], {"schedule": "feed", "parts": {
            "lyl": {"pass": "pass", "reads": ["Customer", "POS Invoice", "Purchase Receipt"]},
            "gcs": {"pass": "pass", "reads": ["POS Invoice"]}}})
        self.assertEqual(d["schedules"], {})
        self.check(self.app)

    def test_one_sale_reaches_both_parts_from_one_read(self):
        out = self.drive("handed")
        self.assertEqual((out["readers"], out["handoff"]), (["gcs", "lyl"], True))
        first, second = out["runs"]
        self.assertEqual(first["reads"], 1)                               # the feed is read once a run, for both parts
        self.assertEqual(first["earned"], ["POS Invoice:S1:earn"])        # S22's part: cash back on the sale
        self.assertEqual(first["cards"], ["S1:1"])                        # S25's part: a gift card for the same sale
        self.assertIn("C2", first["members"])                             # a new customer: S22's alone (S25 reads no Customer)
        self.assertEqual(first["marked"], ["e1", "e2"])
        self.assertEqual((first["loyalty_calls"], first["gift_card_calls"]), (1, 1))
        self.assertEqual((second["loyalty_calls"], second["gift_card_calls"]), (1, 1))     # nothing handed twice
        self.assertEqual(second["notes"], {})

    def test_a_part_that_fails_leaves_the_event_and_the_other_part_is_not_run_twice(self):
        first, second = self.drive("fails-once")["runs"]
        self.assertEqual(first["marked"], ["e2"])                         # the sale is not done: S25 has not handled it
        self.assertEqual(first["notes"], {"e1": ["gcs: RuntimeError: the gift card service did not answer"]})
        self.assertEqual((first["earned"], first["cards"]), (["POS Invoice:S1:earn"], []))
        self.assertEqual(second["marked"], ["e2", "e1"])                  # done once both parts have handled it
        self.assertEqual(second["cards"], ["S1:1"])
        self.assertEqual(second["gift_card_calls"], 2)                    # S25 tried again
        self.assertEqual(second["loyalty_calls"], 1)                      # S22 not run again for the same sale
        self.assertEqual((first["waiting_record"], second["waiting_record"]), ([{"e1": ["lyl"]}], []))

    def test_a_part_that_handled_an_event_is_not_run_again_in_a_new_copy_of_the_function(self):
        first, second = self.drive("new-copy")["runs"]                  # run 2 starts with every seen-list gone
        self.assertEqual((first["marked"], first["waiting_record"]), (["e2"], [{"e1": ["lyl"]}]))
        self.assertEqual((second["loyalty_calls"], second["gift_card_calls"]), (1, 2))
        self.assertEqual((second["marked"], second["cards"], second["waiting_record"]), (["e2", "e1"], ["S1:1"], []))

    def test_each_part_opens_the_shop_with_its_own_code(self):
        log = self.drive("unreachable")["log"]
        errors = [line["error"].split()[0] for line in log if "site" in line]
        self.assertEqual(errors, ["FeedError", "FeedError"])              # each part reached the feed: none failed to open
        self.assertEqual(log[-1]["feed"], {"done": 0, "waiting": 0, "errors": 0})


class AddToAnAppMadeBefore(Base):
    """An app made before the one reader: its reading part has a schedule of its own (lyl-pass) and no feed entry."""

    def older_app(self):
        folder, _ = self.make(["s22_customer_loyalty"])
        aj, dp = self.app_json(folder), json.loads((folder / "service" / "dispatch.json").read_text(encoding="utf-8"))
        aj["schedule"] = {"lyl-pass": aj["schedule"].pop("feed")}
        dp.pop("feed")
        dp["schedules"] = {"lyl-pass": ["lyl", "pass"]}
        entries = aj["samples"][0]["entries"]
        for gone in ("app.json:schedule:feed", "dispatch:feed"):
            entries.pop(gone)
        entries["app.json:schedule:lyl-pass"] = combine.sha("rate(1 minute)")
        entries["dispatch:schedule:lyl-pass"] = combine.sha(["lyl", "pass"])
        (folder / "app.json").write_text(combine.dump(aj), encoding="utf-8")
        (folder / "service" / "dispatch.json").write_text(combine.dump(dp), encoding="utf-8")
        return folder

    def test_adding_a_second_reader_takes_the_first_into_the_one_reader(self):
        folder = self.older_app()
        combine.add("s25_gift_on_spend", folder)
        d = json.loads((folder / "service" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertEqual(set(d["feed"]["parts"]), {"lyl", "gcs"})
        self.assertEqual((self.app_json(folder)["schedule"], d["schedules"]), ({"feed": "rate(1 minute)"}, {}))
        self.check(folder)

    def test_a_reader_the_kit_no_longer_has_is_refused_and_nothing_changes(self):
        folder = self.older_app()
        samples = self.into / "samples"
        samples.mkdir()
        shutil.copytree(KIT / "samples" / "s25_gift_on_spend", samples / "s25_gift_on_spend",
                        ignore=shutil.ignore_patterns("__pycache__"))
        before = tree(folder)
        with self.assertRaises(combine.Refused) as e:
            combine.add("s25_gift_on_spend", folder, samples_dir=samples)
        self.assertEqual(e.exception.code, "reader_unknown")
        self.assertTrue(e.exception.text.startswith("Not added: S22 reads the site's feed on its own"))
        self.assertEqual(tree(folder), before)


class ReadersUnderTheirNames(Base):
    """Each reading sample's own tests stay green under the app's names, and S3 and S52 combine with another reader."""

    def test_s22_and_s25_tests_pass_under_the_apps_names(self):
        folder, out = self.make(["s22_customer_loyalty", "s25_gift_on_spend"], test=True)
        self.assertRegex(out.splitlines()[0], r"^Made\. 2 samples, 1 app\. CHECK GREEN · (\d+) tests run, \1 passed\.$")

    def test_s52_combines_with_another_reader(self):
        folder, out = self.make(["s22_customer_loyalty", "s52_phone_plans"], test=True)
        self.assertRegex(out.splitlines()[0], r"^Made\. 2 samples, 1 app\. CHECK GREEN · (\d+) tests run, \1 passed\.$")
        d = json.loads((folder / "service" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertEqual(d["feed"]["parts"]["tel"], {"pass": "pass", "reads": ["POS Invoice"]})
        self.assertEqual(set(d["feed"]["parts"]), {"lyl", "tel"})
        self.assertEqual(self.app_json(folder)["schedule"], {"feed": "rate(1 minute)"})

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "S3's own tests include one no root user can pass (a folder root can always write)")
    def test_s3_tests_pass_under_the_apps_names(self):
        folder, out = self.make(["s3_price_audit", "s25_gift_on_spend"], test=True)
        self.assertRegex(out.splitlines()[0], r"^Made\. 2 samples, 1 app\. CHECK GREEN · (\d+) tests run, \1 passed\.$")
        self.assertEqual((folder / "tests" / "pdo" / "_manifest_path").read_text(encoding="utf-8"), "outside/manifest.json\n")

    def test_s3_combines_with_another_reader_and_its_part_runs(self):
        folder, _ = self.make(["s3_price_audit", "s25_gift_on_spend"])
        d = json.loads((folder / "service" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertEqual(d["feed"]["parts"]["pdo"], {"pass": "pass", "reads": ["POS Invoice", "Sales Invoice"]})
        self.assertEqual(set(d["feed"]["parts"]), {"pdo", "gcs"})
        self.assertTrue((folder / "service" / "pdo" / "outside" / "app.py").is_file())      # its code, kept in outside/
        self.assertFalse((folder / "service" / "pdo" / "outside" / "manifest.json").exists())
        self.check(folder)
        log = OneReader.drive(self, "unreachable", folder)["log"]       # each part opens the shop and reaches its feed
        self.assertEqual(sorted(line["error"].split()[0] for line in log if "site" in line), ["FeedError", "FeedError"])


class ThreeSamples(Base):
    def test_three_samples_with_a_manifest_only_one(self):
        folder, out = self.make(["s23_till_guard", "s22_customer_loyalty", "s57_donation_intake"])
        self.assertTrue(out.startswith("Made. 3 samples, 1 app. CHECK GREEN"))
        names = {d["name"] for d in self.manifest(folder)["doctypes"]}
        self.assertTrue(any(n.startswith("ACME HK DON ") for n in names))
        self.check(folder)
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=folder, capture_output=True,
                           text=True, timeout=1800, env={"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(len(re.findall(r"SAMPLE \S+ ran=\d+ ok=True", r.stderr)), 3, r.stderr[-1500:])


class Newer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = pathlib.Path(self.tmp.name)
        (self.app / "app.json").write_text(json.dumps({"samples": [
            {"name": "s22_customer_loyalty", "version": "1.3.0"}, {"name": "s23_till_guard", "version": "1.3.0"}]}))

    def index(self, s22="1.4.0"):
        return {"samples": [
            {"name": "s22_customer_loyalty", "title": "Customer-owned loyalty", "version": s22, "versions": [
                {"version": "1.4.0", "lines": ["A wallet top-up is refused above the member's limit."]},
                {"version": "1.3.0", "lines": ["Cash back on returns."]}]},
            {"name": "s23_till_guard", "title": "Till guard rules", "version": "1.3.0",
             "versions": [{"version": "1.3.0", "lines": ["x"]}]}]}

    def test_a_raised_version_is_reported_with_its_lines(self):
        found = combine.newer(self.app, self.index())
        self.assertEqual(len(found), 1)
        n = found[0]
        self.assertEqual(n.text(), "A newer version of S22 Customer-owned loyalty is available: 1.4.0 (yours is 1.3.0).")
        self.assertEqual(n.lines, [("1.4.0", ["A wallet top-up is refused above the member's limit."])])

    def test_an_app_that_is_up_to_date_reports_nothing(self):
        self.assertEqual(combine.newer(self.app, self.index(s22="1.3.0")), [])

    def test_it_reads_a_published_index_file_and_never_changes_the_app(self):
        p = self.app / "samples.json"
        p.write_text(json.dumps(self.index()))
        before = (self.app / "app.json").read_bytes()
        self.assertEqual(len(combine.newer(self.app, str(p))), 1)
        self.assertEqual((self.app / "app.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
