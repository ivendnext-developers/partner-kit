"""The settings-file and Dockerfile checker:  python3 -m unittest discover -s tools/app_template/tests -p 'test_*.py' -v"""
import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import validate_app as V  # noqa: E402

GOOD = json.loads((HERE.parent / "app.json").read_text())
DOCKERFILE = (HERE.parent / "Dockerfile").read_text()


def setting(name, **keys):
    """One setting as the kit writes it: every setting says its purpose."""
    return {"name": name, "purpose": f"What to put in {name}", **keys}


def bad(**changes):
    m = copy.deepcopy(GOOD)
    m.update(changes)
    return V.check_settings(m)


class Settings(unittest.TestCase):
    def test_a_setting_may_say_what_it_is(self):  # the hosting page shows it under the setting's box
        self.assertEqual(bad(env=[setting("REGION_X", about="The region your app reports in.")]), [])

    def test_a_container_may_ask_for_a_scratch_folder(self):
        self.assertEqual(bad(scratch=True), [])

    def test_the_shipped_template_is_ready(self):
        self.assertEqual(V.check_folder(HERE.parent), [])

    def test_each_refusal_names_its_reason(self):
        cases = [
            (bad(app="X"), "app:"), (bad(version="1.0"), "version:"), (bad(port=80), "port:"), (bad(port="8080"), "port:"),
            (bad(health="health"), "health:"), (bad(size="huge"), "size:"), (bad(region="usa"), "region:"), (bad(extra=1), "unknown key"),
            (bad(env=[setting("lower")]), "capitals"), (bad(env=[setting("A_B"), setting("A_B")]), "twice"),
            (bad(env=[setting("API_TOKEN")]), "looks like a secret"),
            (bad(env=[setting("API_TOKEN", secret=False)]), "looks like a secret"),
            (bad(env=[setting("REGION_X", value="abc")]), "never values"), (bad(env="x"), "env: a list"),
            (bad(env=[setting("REGION_X", about="two\nlines")]), "about is one line"),
            (bad(env=[setting("REGION_X", about=3)]), "about is one line"),
            (bad(env=[setting("REGION_X", purpose="two\nlines")]), "its purpose is one line"),
            (bad(env=[setting("REGION_X", required="yes")]), "required is true or false"),
            (bad(scratch="yes"), "scratch:"),
        ]
        for errors, word in cases:
            self.assertTrue(any(word in e for e in errors), (word, errors))

    def test_a_non_secret_name_needs_no_flag_and_a_secret_one_passes_when_marked(self):
        self.assertEqual(bad(env=[setting("LOG_LEVEL"), setting("DB_PASSWORD", secret=True, required=True)]), [])

    def test_canary_local_mode_is_never_a_hosting_setting(self):
        for name in ("IVN_LOCAL", "IVN_LOCAL_LIBRARY_KEYS"):
            self.assertTrue(any("never for hosting" in e for e in bad(env=[setting(name)])), name)
        self.assertEqual(bad(env=[setting("IVN_LOCALE")]), [])

    def test_canary_a_setting_with_no_purpose_is_refused(self):  # the line the Settings screen shows
        want = ("the setting PP_STATE in app.json has no purpose: the line the Settings screen shows")
        for entry in ({"name": "PP_STATE", "required": True}, {"name": "PP_STATE", "purpose": ""},
                      {"name": "PP_STATE", "purpose": "   "}, {"name": "PP_STATE", "purpose": 3}):
            self.assertTrue(any(e.startswith(want) for e in bad(env=[entry])), entry)
        self.assertEqual(bad(env=[setting("PP_STATE", required=True, together=[])]), [])

    def test_settings_set_together_name_each_other_in_the_same_list(self):
        pair = [setting("WALLET_SITE", together=["WALLET_MERCHANT"]), setting("WALLET_MERCHANT", together=["WALLET_SITE"])]
        self.assertEqual(bad(env=pair), [])
        cases = [
            ([setting("WALLET_SITE", together="WALLET_MERCHANT"), setting("WALLET_MERCHANT")], "together is a list"),
            ([setting("WALLET_SITE", together=[3])], "together is a list"),
            ([setting("WALLET_SITE", together=[{"name": "X"}])], "together is a list"),
            ([setting("WALLET_SITE", together=["WALLET_MERCHANT"])], "not another setting in its env list"),
            ([setting("WALLET_SITE", together=["WALLET_SITE"])], "not another setting in its env list"),
            ([setting("WALLET_SITE", together=["WALLET_MERCHANT"]), setting("WALLET_MERCHANT")], "names WALLET_SITE too"),
        ]
        for env, want in cases:
            got = bad(env=env)
            self.assertTrue(any(want in e and "WALLET_SITE" in e for e in got), (want, got))

    def test_every_settings_file_in_the_kit_says_each_settings_purpose(self):
        kit = HERE.parents[2]
        files = sorted(kit.glob("samples/*/app.json")) + sorted(kit.glob("samples/*/live/app.json")) + [HERE.parent / "app.json"]
        self.assertGreater(len(files), 30)
        for f in files:
            m = json.loads(f.read_text("utf-8"))
            self.assertEqual(V.check_settings(m), [], f)
            for e in m["env"]:
                self.assertTrue(isinstance(e.get("required"), bool) and isinstance(e.get("together"), list), (f, e))

    def test_not_an_object(self):
        self.assertEqual(V.check_settings([]), ["app.json is not a JSON object"])


class Dockerfile(unittest.TestCase):
    def test_the_shipped_dockerfile_passes(self):
        self.assertEqual(V.check_dockerfile(DOCKERFILE, 8080), [])

    def test_root_no_health_check_wrong_port_and_a_baked_in_secret_are_refused(self):
        no_user = DOCKERFILE.replace("USER app\n", "")
        self.assertTrue(any("not root" in e for e in V.check_dockerfile(no_user, 8080)))
        self.assertTrue(any("not root" in e for e in V.check_dockerfile(DOCKERFILE.replace("USER app", "USER root"), 8080)))
        no_hc = "\n".join(l for l in DOCKERFILE.splitlines() if "HEALTHCHECK" not in l and "CMD python3 -c" not in l)
        self.assertTrue(any("HEALTHCHECK" in e for e in V.check_dockerfile(no_hc, 8080)))
        self.assertTrue(any("EXPOSE" in e for e in V.check_dockerfile(DOCKERFILE, 9090)))
        baked = DOCKERFILE + "\nENV IVN_POINT_SECRET=abc123\n"
        self.assertTrue(any("secret-looking" in e for e in V.check_dockerfile(baked, 8080)))

    def test_a_missing_file_is_a_refusal_not_a_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(V.check_folder(d), ["app.json is missing"])
            (pathlib.Path(d) / "app.json").write_text("{not json")
            self.assertTrue(V.check_folder(d)[0].startswith("app.json is not valid JSON"))
            (pathlib.Path(d) / "app.json").write_text(json.dumps(GOOD))
            self.assertEqual(V.check_folder(d), ["Dockerfile is missing"])


if __name__ == "__main__":
    unittest.main()


class FunctionForm(unittest.TestCase):
    """`runs`: an app that says nothing is a container, as before; a function names its handler and package, serves
    many shops and keeps no secret of its own (chapter 14b)."""
    FN = {"runs": "function", "handler": "service/app.lambda_handler", "package": ["service"], "shops": True,
          "env": [setting("IVN_LIBRARY_APP", required=True)]}

    def test_a_function_with_its_handler_and_package_is_ready(self):
        self.assertEqual(bad(**self.FN), [])

    def test_saying_nothing_is_a_container_and_container_is_accepted(self):
        self.assertEqual(bad(), [])
        self.assertEqual(bad(runs="container"), [])

    def test_each_function_refusal_names_its_reason(self):
        cases = [
            (bad(runs="lambda"), "runs:"),
            (bad(**{**self.FN, "handler": "service/app"}), "handler:"),
            (bad(**{**self.FN, "handler": "../x/app.lambda_handler"}), "handler:"),
            (bad(**{**self.FN, "package": []}), "package:"),
            (bad(**{**self.FN, "package": ["../secrets"]}), "package:"),
            (bad(**{**self.FN, "package": ["/etc"]}), "package:"),
            (bad(**{**self.FN, "shops": False}), "shops:"),
            (bad(**{**self.FN, "scratch": True}), "scratch:"),
            (bad(**{**self.FN, "env": [setting("IVN_POINT_SECRET", secret=True, required=True)]}), "keeps no secret"),
            (bad(handler="service/app.lambda_handler"), "handler: only a function"),
            (bad(package=["service"]), "package: only a function"),
        ]
        for got, want in cases:
            self.assertTrue(any(want in b for b in got), (want, got))

    def test_a_schedule_and_a_timeout_are_a_functions_and_checked(self):
        fn = {**self.FN, "schedule": {"pass": "rate(1 minute)", "daily": "cron(0 2 * * ? *)"}, "timeout": 120}
        self.assertEqual(bad(**fn), [])
        cases = [
            (bad(**{**fn, "schedule": {"pass": "every minute"}}), "schedule:"),
            (bad(**{**fn, "schedule": {"Pass": "rate(1 minute)"}}), "schedule:"),
            (bad(**{**fn, "schedule": {"twelve-chars": "rate(1 minute)"}}), "schedule:"),
            (bad(**{**fn, "schedule": {"pass": "rate(0 minutes)"}}), "schedule:"),
            (bad(**{**fn, "schedule": ["rate(1 minute)"]}), "schedule:"),
            (bad(**{**fn, "timeout": 901}), "timeout:"),
            (bad(**{**fn, "timeout": 0}), "timeout:"),
            (bad(**{**fn, "timeout": True}), "timeout:"),
            (bad(schedule={"pass": "rate(1 minute)"}), "schedule: only a function"),
            (bad(timeout=60), "timeout: only a function"),
        ]
        for got, want in cases:
            self.assertTrue(any(want in b for b in got), (want, got))

    def test_a_function_needs_no_dockerfile(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "app.json").write_text(json.dumps({**GOOD, **self.FN}))
            self.assertEqual(V.check_folder(d), [])
            (pathlib.Path(d) / "app.json").write_text(json.dumps(GOOD))
            self.assertEqual(V.check_folder(d), ["Dockerfile is missing"])
