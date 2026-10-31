"""The one check command: a good project passes; each planted defect turns it red; a folder with nothing in it is not green.

    python3 -m unittest discover -s tools/check/tests

Every project here is built in a temporary folder from the kit's own samples, so the checks run against what the kit
publishes. The command is run as a person runs it (a subprocess), so its exit code and its verdict line are what is tested.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
CHECK = ROOT / "tools" / "check" / "check.py"
CONTRACT_SAMPLES = ROOT / "contracts" / "extension_contracts" / "samples"
GOOD_MANIFEST = json.loads((ROOT / "samples" / "s1_warranty" / "manifest.json").read_text("utf-8"))

HOOKS = ('app_name = "pp_tst"\napp_license = "proprietary"\nrequired_apps = ["ivendnext/frappe", "ivendnext/erpnext"]\n'
         'doc_events = {"Customer": {"on_update": "pp_tst.events.on_submit"}}\n')
EVENTS = ("import frappe\n\n\ndef on_submit(doc, method=None):\n    try:\n        return doc.name\n"
          "    except Exception:\n        frappe.log_error(title='pp_tst')\n")
OUTBOUND = "import requests\n\n\ndef push(x):\n    return requests.get('https://api.partner.example/x')\n"

# a module with one empty function; and one that adds two floats (a price point may not)
WASM_HEAD = b"\x00asm\x01\x00\x00\x00" + bytes([1, 4, 1, 0x60, 0, 0]) + bytes([3, 2, 1, 0])
WASM_OK = WASM_HEAD + bytes([10, 4, 1, 2, 0, 0x0B])
WASM_FLOAT = WASM_HEAD + bytes([10, 10, 1, 8, 0, 0x43, 0, 0, 0, 0, 0x1A, 0x0B])


def answer(point, outcome, name):
    s = json.loads((CONTRACT_SAMPLES / point / outcome / name).read_text("utf-8"))
    return s


def first(point, outcome):
    return sorted((CONTRACT_SAMPLES / point / outcome).glob("*.json"))[0].name


class Project:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def write(self, rel, content):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            content = json.dumps(content)
        p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return p

    def good(self):
        self.write("manifest.json", GOOD_MANIFEST)
        self.write("app/pp_tst/hooks.py", HOOKS)
        self.write("app/pp_tst/events.py", EVENTS)
        self.write("app/pp_tst/modules.txt", "PP TST\n")
        self.write("fn/price.wasm", WASM_OK)
        self.write("contract_samples/ok.json", answer("desk_action", "accepted", first("desk_action", "accepted")))
        self.write("contract_samples/no.contract.json",
                   answer("desk_action", "refused", first("desk_action", "refused")))
        return self

    def run(self, *flags):
        r = subprocess.run([sys.executable, str(CHECK), str(self.root), *flags], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def close(self):
        self._tmp.cleanup()


class CheckTest(unittest.TestCase):
    def project(self):
        p = Project()
        self.addCleanup(p.close)
        return p

    def test_a_good_project_passes_and_says_what_it_found(self):
        code, out = self.project().good().run()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"CHECK GREEN — 1 manifest, 1 app, 1 module, 2 answers")
        self.assertIn("refused as expected against desk_action", out)

    def test_planted_defect_a_refused_manifest_kind(self):
        p = self.project().good()
        p.write("manifest.json", {**GOOD_MANIFEST, "server_scripts": [{"name": "x", "script": "print(1)"}]})
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("a server script runs partner code", out)
        self.assertIn("CHECK RED: 1 refusal(s)", out)

    def test_planted_defect_a_report_on_a_field_its_own_manifest_adds(self):
        # the shop's install refuses it after the checker passes it (tools/manifest/site_rules.py; APPF run 5, S33)
        p = self.project().good()
        bad = {**GOOD_MANIFEST, "manifest_version": 2, "custom_fields": [{"dt": "Delivery Note", "fieldname": "pp_wrc_flag", "fieldtype": "Check",
                                                    "label": "Flag", "insert_after": "po_no"}],
               "reports": [{"name": "PP WRC Flags", "ref_doctype": "Delivery Note", "columns": ["name", "pp_wrc_flag"]}]}
        p.write("manifest.json", bad)
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("not fields of Delivery Note: ['pp_wrc_flag']", out)

    def test_planted_defect_a_sample_answer_that_breaks_its_schema(self):
        p = self.project().good()
        p.write("contract_samples/ok.json", {"extension_point": "desk_action", "contract": "answer",
                                              "payload": {"message": "Route assigned"}})     # a string, not an object
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("breaks the desk_action contract", out)
        self.assertIn("CHECK RED", out)

    def test_planted_defect_outbound_code_the_self_check_refuses(self):
        p = self.project().good()
        p.write("app/pp_tst/push.py", OUTBOUND)
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("self-check FAIL", out)
        self.assertIn("outbound", out)
        self.assertIn("CHECK RED", out)

    def test_planted_defect_floating_point_in_a_sandboxed_build(self):
        p = self.project().good()
        p.write("fn/price.wasm", WASM_FLOAT)
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("uses floating point", out)
        self.assertEqual(p.run("--server-only")[0], 0)          # a server-only point may use it

    def test_a_refused_answer_that_the_contract_accepts_is_a_defect_too(self):
        p = self.project().good()
        ok = answer("desk_action", "accepted", first("desk_action", "accepted"))
        p.write("contract_samples/no.contract.json", {**ok, "expect_refusal": "should have been turned away"})
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("expected to be refused", out)

    def test_an_unreadable_manifest_is_a_refusal_not_a_crash(self):
        p = self.project().good()
        p.write("manifest.json", "{not json")
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("manifest.json: the file is not valid JSON: something is missing or extra at line 1, column 2", out)

    def test_a_manifest_cut_short_names_the_place_in_plain_words(self):
        p = self.project().good()
        p.write("manifest.json", '{"app": "pp_broken", "version": "0.0.1", ')
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("the file is not valid JSON: something is missing or extra at line 1, column 42", out)
        self.assertNotIn("property name", out)
        self.assertNotIn("char 41", out)

    def test_an_app_always_carries_a_note_that_a_person_reviews_it(self):
        code, out = self.project().good().run()
        self.assertIn("A person reviews this app", out)

    def test_planted_defect_a_script_inside_the_shop_is_refused_and_the_note_stays(self):
        p = self.project().good()
        p.write("app/pp_tst/hooks.py", HOOKS + 'fixtures = ["Server Script"]\n')
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("self-check FAIL", out)
        self.assertIn("site_scripts", out)
        self.assertIn("CHECK RED", out)
        # the note is said on every app, red or green: it is about the app's Python, which no check here proves safe
        self.assertIn("A person reviews this app", out)
        # and the builder sees WHICH file and the words (rule, and what to do instead), not only the check's title
        self.assertIn("hooks.py fixtures names 'Server Script'", out)
        self.assertIn("Instead:", out)
        self.assertIn("CHECK RED: 1 refusal(s)", out)

    def test_an_answer_in_the_kits_own_nested_layout_is_found_and_judged(self):
        p = self.project().good()
        p.write("contract_samples/remote_till_key/mine.json",
                {"extension_point": "remote_till_key", "contract": "answer", "payload": {"title": "x"}})
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("mine.json", out)
        self.assertIn("CHECK RED", out)

    def test_a_manifest_with_any_name_ending_manifest_json_is_checked(self):
        p = self.project().good()
        p.write("acme_wrc_manifest.json", {**GOOD_MANIFEST, "server_scripts": [{"name": "x", "script": "print(1)"}]})
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("acme_wrc_manifest.json", out)

    def test_a_file_named_wasm_that_is_not_a_module_is_refused(self):
        for junk in (b"", b"\x00", b"not a module at all"):
            p = self.project().good()
            p.write("fn/price.wasm", junk)
            code, out = p.run()
            self.assertEqual(code, 1, out)
            self.assertIn("not a WebAssembly module", out)

    def test_a_truncated_module_is_refused_and_does_not_crash(self):
        p = self.project().good()
        p.write("fn/price.wasm", WASM_HEAD + bytes([10, 5, 1]))          # a code section that claims more than the file holds
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("CHECK RED", out)
        self.assertNotIn("Traceback", out)

    def test_a_linked_folder_is_named_not_silently_skipped(self):
        p = self.project().good()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (pathlib.Path(outside.name) / "manifest.json").write_text(json.dumps({"server_scripts": [1]}))
        os.symlink(outside.name, p.root / "linked")
        code, out = p.run()
        self.assertEqual(code, 0, out)
        self.assertIn("linked: a linked folder, not followed", out)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read any folder")
    def test_a_folder_that_cannot_be_read_is_a_refusal(self):
        p = self.project().good()
        p.write("hidden/manifest.json", {**GOOD_MANIFEST, "server_scripts": [1]})
        os.chmod(p.root / "hidden", 0)
        self.addCleanup(os.chmod, p.root / "hidden", 0o755)
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("a folder that cannot be read", out)

    def test_folders_named_tests_are_not_searched(self):
        p = self.project().good()
        p.write("tests/manifest.json", {**GOOD_MANIFEST, "server_scripts": [{"name": "x", "script": "print(1)"}]})
        self.assertEqual(p.run()[0], 0)

    def test_an_empty_folder_is_not_green(self):
        code, out = self.project().run()
        self.assertEqual(code, 2)
        self.assertIn("NOTHING FOUND", out)

    def test_a_missing_folder_is_not_green(self):
        r = subprocess.run([sys.executable, str(CHECK), "/nonexistent/folder"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_canary_a_setting_with_no_purpose_is_refused_then_green_with_it(self):
        p = self.project().good()
        settings = json.loads((ROOT / "samples" / "s22_customer_loyalty" / "app.json").read_text("utf-8"))
        state = next(e for e in settings["env"] if e["name"] == "PP_STATE")
        state.pop("purpose")
        p.write("service/app.json", settings)
        code, out = p.run()
        self.assertEqual(code, 1, out)
        self.assertIn("service/app.json: the setting PP_STATE in app.json has no purpose: the line the Settings screen shows",
                      out)
        state["purpose"] = "A folder the service may write to"
        p.write("service/app.json", settings)
        code, out = p.run()
        self.assertEqual(code, 0, out)
        self.assertIn("service/app.json: settings file valid", out)
        self.assertRegex(out, r"CHECK GREEN — 1 manifest, 1 app, 1 module, 2 answers, 1 settings file")

    def test_another_tools_app_json_is_left_alone(self):
        p = self.project().good()
        p.write("mobile/app.json", {"expo": {"name": "till helper"}})
        p.write("library/app.json", {"app": "pp_tst", "title": {"en": "A card"}, "category": "Stock"})   # the library's card
        code, out = p.run()
        self.assertEqual(code, 0, out)
        self.assertNotIn("mobile/app.json", out)
        self.assertNotIn("library/app.json", out)

    def test_the_kits_own_samples_pass(self):
        for name in ("s1_warranty", "s2_bins", "s5_config_pack", "s11_approvals"):
            r = subprocess.run([sys.executable, str(CHECK), str(ROOT / "samples" / name)], capture_output=True, text=True)
            self.assertIn(r.returncode, (0, 2), f"{name}: {r.stdout}")      # 2 = a sample with nothing checkable
            self.assertNotIn("RED", r.stdout, name)


if __name__ == "__main__":
    unittest.main()
