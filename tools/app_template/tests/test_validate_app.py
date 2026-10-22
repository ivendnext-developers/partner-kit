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


def bad(**changes):
    m = copy.deepcopy(GOOD)
    m.update(changes)
    return V.check_settings(m)


class Settings(unittest.TestCase):
    def test_the_shipped_template_is_ready(self):
        self.assertEqual(V.check_folder(HERE.parent), [])

    def test_each_refusal_names_its_reason(self):
        cases = [
            (bad(app="X"), "app:"), (bad(version="1.0"), "version:"), (bad(port=80), "port:"), (bad(port="8080"), "port:"),
            (bad(health="health"), "health:"), (bad(size="huge"), "size:"), (bad(region="usa"), "region:"), (bad(extra=1), "unknown key"),
            (bad(env=[{"name": "lower"}]), "capitals"), (bad(env=[{"name": "A_B"}, {"name": "A_B"}]), "twice"),
            (bad(env=[{"name": "API_TOKEN"}]), "looks like a secret"),
            (bad(env=[{"name": "API_TOKEN", "secret": False}]), "looks like a secret"),
            (bad(env=[{"name": "REGION_X", "value": "abc"}]), "never values"), (bad(env="x"), "env: a list"),
        ]
        for errors, word in cases:
            self.assertTrue(any(word in e for e in errors), (word, errors))

    def test_a_non_secret_name_needs_no_flag_and_a_secret_one_passes_when_marked(self):
        self.assertEqual(bad(env=[{"name": "LOG_LEVEL"}, {"name": "DB_PASSWORD", "secret": True, "required": True}]), [])

    def test_canary_local_mode_is_never_a_hosting_setting(self):
        for name in ("IVN_LOCAL", "IVN_LOCAL_LIBRARY_KEYS"):
            self.assertTrue(any("never for hosting" in e for e in bad(env=[{"name": name}])), name)
        self.assertEqual(bad(env=[{"name": "IVN_LOCALE"}]), [])

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
          "env": [{"name": "IVN_LIBRARY_APP", "required": True}]}

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
            (bad(**{**self.FN, "env": [{"name": "IVN_POINT_SECRET", "secret": True, "required": True}]}), "keeps no secret"),
            (bad(handler="service/app.lambda_handler"), "handler: only a function"),
            (bad(package=["service"]), "package: only a function"),
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
