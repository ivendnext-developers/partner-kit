"""deploy_app order | push | back | status | secret | cancel: the same checks as planning, a request signed over the
hosting's own domain (never the library upload's), the Schedule accepted out loud, a secret's value never printed, and a
version uploaded as one zip of the app's folder (no GitHub). No network: the send and the upload are replaced."""
import contextlib
import http.client
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import deploy_app  # noqa: E402
import hosting_order as HO  # noqa: E402

TEMPLATE = HERE.parents[1] / "app_template"


def run(*argv, stdin=""):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()), \
            mock.patch("sys.stdin", io.StringIO(stdin)):
        code = deploy_app.main(list(argv))
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.app = self.tmp / "app"
        shutil.copytree(TEMPLATE, self.app, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        (self.app / "LICENSE").write_text("Apache License, Version 2.0\n", "utf-8")
        m = json.loads((self.app / "app.json").read_text())
        m["env"].append({"name": "LOG_LEVEL", "secret": False, "purpose": "How much the app writes to its log",
                         "required": False, "together": []})  # one plain setting
        (self.app / "app.json").write_text(json.dumps(m))
        self.key = self.tmp / "signing.key"
        HO.publish.keygen(self.key)
        self.sent, self.paths = [], []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fake_send(self, answer):
        def send(data, path=""):
            self.sent.append(json.loads(data))
            self.paths.append(path)
            return 200, answer
        return mock.patch.object(HO, "send", send)

    def body(self, i=-1):
        env = self.sent[i]
        return json.loads(HO.publish.unb64u(env["body"]))

    def order(self, *extra):
        return run("order", str(self.app), "--plan", "starter", "--partner", "acme", "--key", str(self.key), *extra)


class Order(Base):
    ANSWER = {"order": "0123456789abcdef", "id": "my-till-key", "plan": "starter", "status": "pending", "kind": "card",
              "address": "https://my-till-key.ivendnext.app", "checkout_url": "https://checkout.stripe.com/c/x",
              "secrets": ["IVN_POINT_SECRET"]}

    def test_the_schedule_must_be_accepted(self):
        with self.fake_send(self.ANSWER):
            code, out = self.order()
        self.assertEqual(code, 1)
        self.assertIn("--accept-schedule", out)
        self.assertEqual(self.sent, [])

    def test_an_order_is_signed_over_the_hostings_own_domain(self):
        with self.fake_send(self.ANSWER):
            code, out = self.order("--accept-schedule", "--set", "LOG_LEVEL=info")
        self.assertEqual(code, 0, out)
        self.assertIn("https://checkout.stripe.com/c/x", out)
        env, body = self.sent[0], HO.publish.unb64u(self.sent[0]["body"])
        public = HO.ed25519.public_key(HO.publish.load_key(str(self.key)))
        self.assertTrue(HO.ed25519.verify(public, HO.DOMAIN + body, HO.publish.unb64u(env["sig"])))
        self.assertFalse(HO.ed25519.verify(public, HO.publish.DOMAIN + body, HO.publish.unb64u(env["sig"])))
        p = self.body()
        self.assertEqual((p["cmd"], p["schedule_version"], p["plain_env"]), ("order", HO.SCHEDULE_VERSION, {"LOG_LEVEL": "info"}))
        self.assertNotIn("github", p)  # EASY2: an order names no repository
        self.assertNotIn("value", json.dumps(p["app"]))  # names and shapes only

    def test_the_github_options_are_gone(self):
        for extra in (("--github", "acme/points"), ("--github-subject", "repo:acme@101/points@202"), ("--branch", "main")):
            with self.fake_send(self.ANSWER):
                self.assertEqual(self.order("--accept-schedule", *extra)[0], 2, extra)
        self.assertEqual(self.sent, [])

    def test_the_planning_checks_still_refuse(self):
        m = json.loads((self.app / "app.json").read_text())
        m["size"] = "large"
        (self.app / "app.json").write_text(json.dumps(m))
        with self.fake_send(self.ANSWER):
            code, out = self.order("--accept-schedule")
        self.assertEqual(code, 1)
        self.assertIn("size", out)
        self.assertEqual(self.sent, [])

    def test_a_setting_app_json_does_not_name_or_a_secret_is_refused(self):
        for s in ("NOPE=1", "IVN_POINT_SECRET=x"):
            with self.fake_send(self.ANSWER):
                code, out = self.order("--accept-schedule", "--set", s)
            self.assertEqual(code, 1, s)
        self.assertEqual(self.sent, [])

    def test_an_invoice_names_where_it_goes(self):
        with self.fake_send(self.ANSWER):
            self.assertEqual(self.order("--accept-schedule", "--invoice")[0], 1)
            self.assertEqual(self.order("--accept-schedule", "--invoice", "--email", "ap@acme.example")[0], 0)
        self.assertTrue(self.body()["invoice"])

    def test_a_refusal_is_printed_and_exits_1(self):
        with self.fake_send({"refused": "not_open", "words": "only our own teams for now"}):
            code, out = self.order("--accept-schedule")
        self.assertEqual(code, 1)
        self.assertIn("not_open", out)


class Settings(unittest.TestCase):
    def test_the_scratch_flag_is_sent(self):  # the hosting builds the folder only from what the order carries
        self.assertIs(HO.app_settings({"app": "a", "version": "1.0.0", "scratch": True})["scratch"], True)


class ScheduledFunction(Base):
    def test_an_app_on_a_schedule_is_refused_before_anything_is_sent(self):
        m = json.loads((self.app / "app.json").read_text())
        m.update(runs="function", handler="service/app.lambda_handler", package=["service"], shops=True,
                 schedule={"pass": "rate(1 minute)"}, timeout=120,
                 env=[e for e in m["env"] if not e.get("secret")])
        (self.app / "app.json").write_text(json.dumps(m))
        with self.fake_send({"order": "x"}):
            code, out = self.order("--accept-schedule")
        self.assertEqual((code, self.sent), (1, []))
        self.assertIn("put live by CitiXsys, not ordered online yet", out)


class Secret(Base):
    def test_the_value_is_sent_signed_and_never_printed(self):
        with self.fake_send({"order": "0123456789abcdef", "secret": "IVN_POINT_SECRET", "set": True}):
            code, out = run("secret", "--partner", "acme", "--order", "0123456789abcdef", "--name", "IVN_POINT_SECRET",
                            "--key", str(self.key), stdin="hunter2-value\n")
        self.assertEqual(code, 0)
        self.assertNotIn("hunter2-value", out)
        self.assertEqual(self.body()["value"], "hunter2-value")

    def test_status_and_cancel(self):
        with self.fake_send({"orders": [Order.ANSWER]}):
            code, out = run("status", "--partner", "acme", "--key", str(self.key))
        self.assertEqual(code, 0)
        self.assertIn("my-till-key", out)
        with self.fake_send({"order": "0123456789abcdef", "status": "live", "stops_at": 1}):
            code, out = run("cancel", "--partner", "acme", "--order", "0123456789abcdef", "--key", str(self.key))
        self.assertIn("end of the paid month", out)


class PlanningUnchanged(Base):
    def test_plan_mode_still_changes_nothing_and_points_at_order(self):
        code, out = run(str(self.app), "--image", "r.example/x/my-till-key:1.0.0", "--plan", "starter", "--partner", "acme")
        self.assertEqual(code, 0, out)
        self.assertIn("Nothing was changed", out)
        self.assertIn("deploy_app.py order", out)


class Copies(Base):
    """One order runs the plan's copies at one price (HOSTCOPIES): the order names them, each is checked, and each is
    shown with where it stands."""

    ANSWER = {"order": "0123456789abcdef", "id": "my-till-key", "plan": "starter", "status": "pending", "kind": "card",
              "checkout_url": "https://checkout.stripe.com/c/x", "secrets": ["IVN_POINT_SECRET"], "stops_at": 1798353203,
              "copies": [
                  {"order": "0123456789abcdef", "env": "prod", "id": "my-till-key", "status": "building", "building": "create",
                   "address": "https://my-till-key.ivendnext.app"},
                  {"order": "fedcba9876543210", "env": "sandbox", "id": "my-till-key-sandbox", "status": "waiting",
                   "waiting_for": ["IVN_POINT_SECRET"], "push_refused": "9.9.9", "address": "https://my-till-key-sandbox.ivendnext.app"}],
              "versions": ["1.0.1"], "build": {"version": "1.0.2", "state": "failed", "lines": ["step 1", "ERROR: boom"],
                                               "words": "1.0.2 did not build. The last 50 lines of the build are below. "
                                                        "Your sites still run 1.0.1."}}

    def test_an_order_names_the_plans_copies(self):
        with self.fake_send(self.ANSWER):
            code, out = self.order("--accept-schedule")
        self.assertEqual((code, self.body()["copies"]), (0, ["prod", "sandbox"]), out)
        self.assertNotIn("env", self.body())

    def test_fewer_copies_and_the_older_one_copy_form(self):
        with self.fake_send(self.ANSWER):
            self.order("--accept-schedule", "--copies", "sandbox")
            self.order("--accept-schedule", "--env", "sandbox")
        self.assertEqual([self.body(0)["copies"], self.body(1)["copies"]], [["sandbox"], ["sandbox"]])

    def test_a_copy_the_plan_does_not_run_or_one_named_twice_is_refused_before_sending(self):
        for copies in ("prod,staging", "prod,prod"):
            with self.fake_send(self.ANSWER):
                code, out = self.order("--accept-schedule", "--copies", copies)
            self.assertEqual(code, 1, out)
        self.assertEqual(self.sent, [])

    def test_each_copy_is_shown_with_where_it_stands_and_the_last_build(self):
        with self.fake_send(self.ANSWER):
            code, out = self.order("--accept-schedule")
        self.assertIn("2 copies", out)
        self.assertIn("building (create)", out)
        self.assertIn("waiting for its secrets: IVN_POINT_SECRET", out)
        self.assertIn("version 9.9.9 was refused", out)
        self.assertIn("stops    at the end of the paid month (2026-12-27)", out)
        self.assertNotIn("github", out.lower())
        self.assertIn("versions 1.0.1", out)
        self.assertIn("build    1.0.2 did not build. The last 50 lines of the build are below. Your sites still run 1.0.1.", out)
        self.assertIn("           | ERROR: boom", out)

    def test_status_with_no_orders_says_so(self):
        with self.fake_send({"orders": []}):
            code, out = run("status", "--partner", "acme", "--key", str(self.key))
        self.assertEqual((code, out.strip()), (0, "no hosting orders yet"))

    def test_a_secret_names_its_copy(self):
        with self.fake_send({"order": "0123456789abcdef", "secret": "IVN_POINT_SECRET", "set": True}):
            run("secret", "--partner", "acme", "--order", "0123456789abcdef", "--env", "sandbox", "--name",
                "IVN_POINT_SECRET", "--key", str(self.key), stdin="v")
        self.assertEqual(self.body()["env"], "sandbox")


class Push(Base):
    """`push`: the app's folder zipped, the upload's address asked for (signed, at /v1/upload), and the zip PUT there."""

    ANSWER = {"order": "0123456789abcdef", "version": "1.0.0",
              "upload": {"url": "https://ivn-selfserve-work-1.s3.us-east-1.amazonaws.com/uploads/my-till-key/1.0.0.zip?X=1",
                         "method": "PUT", "headers": {"Content-Type": "application/zip", "If-None-Match": "*"}}}

    def push(self, status=200, answer=None):
        self.put_calls = []

        def put(url, headers, data):
            self.put_calls.append((url, headers, data))
            return status
        with self.fake_send(answer or self.ANSWER), mock.patch.object(HO, "put", put):
            return run("push", str(self.app), "--partner", "acme", "--order", "0123456789abcdef", "--key", str(self.key))

    def test_the_folder_is_zipped_signed_and_uploaded_to_the_address_answered(self):
        (self.app / ".env.local").write_text("IVN_POINT_SECRET=local-test\n")
        (self.app / ".dockerignore").write_text("tests\n")
        (self.app / ".git").mkdir()
        (self.app / ".git" / "HEAD").write_text("ref: x\n")
        (self.app / "service" / "__pycache__").mkdir(exist_ok=True)
        (self.app / "service" / "__pycache__" / "x.pyc").write_bytes(b"x")
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertIn("UPLOADED 1.0.0", out)
        self.assertEqual(self.paths, ["/v1/upload"])
        p = self.body()
        self.assertEqual((p["cmd"], p["order"], p["version"]), ("upload", "0123456789abcdef", "1.0.0"))
        url, headers, data = self.put_calls[0]
        self.assertEqual((p["size"], headers["If-None-Match"]), (len(data), "*"))
        import zipfile
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertIn("app.json", names)
        self.assertIn("Dockerfile", names)
        self.assertIn(".dockerignore", names)  # a container's build may need it
        self.assertFalse([n for n in names if n.startswith((".env", ".git/")) or "__pycache__" in n], names)
        self.assertEqual(HO.folder_zip(self.app), data)  # the same bytes for the same files

    def test_a_folder_over_the_limit_is_refused_in_the_specs_words_before_anything_is_sent(self):
        with mock.patch.dict(HO.LIMITS, {"container": 10}):
            code, out = self.push()
        self.assertEqual(code, 1)
        self.assertRegex(out, r"REFUSED: Not kept: this upload is [0-9.]+ MB; a function's package can be at most 50 MB, "
                              r"a container's image at most 1,024 MB\. Nothing was built\.")
        self.assertEqual((self.sent, self.put_calls), ([], []))

    def test_the_hostings_refusal_and_a_version_uploaded_already(self):
        code, out = self.push(answer={"refused": "not_newer", "words": "the version must be higher than 1.0.0"})
        self.assertEqual(code, 1)
        self.assertIn("higher than 1.0.0", out)
        self.assertEqual(self.put_calls, [])
        code, out = self.push(status=412)
        self.assertEqual(code, 1)
        self.assertIn("raise app.json's \"version\"", out)

    def test_an_address_that_is_not_ours_gets_nothing(self):
        with self.assertRaises(HO.Stop):
            HO.put("https://evil.example/x", {}, b"zip")
        with self.assertRaises(HO.Stop):
            HO.put("http://ivn-selfserve-work-1.s3.us-east-1.amazonaws.com/x", {}, b"zip")

    def test_a_folder_the_template_checker_refuses_is_not_uploaded(self):
        (self.app / "Dockerfile").unlink()
        code, out = self.push()
        self.assertEqual(code, 1)
        self.assertEqual(self.sent, [])


    def test_a_functions_zip_is_its_app_json_and_its_package_from_root(self):
        kit = HERE.parents[2]
        fn = self.tmp / "kit" / "apps" / "acme_rlg"
        fn.mkdir(parents=True)
        (self.tmp / "kit" / "lib").mkdir()
        (self.tmp / "kit" / "lib" / "helper.py").write_text("X = 1\n")
        (fn / "service").mkdir()
        (fn / "service" / "app.py").write_text("def lambda_handler(e, c):\n    return 1\n")
        (fn / "README.md").write_text("# not in the package\n")
        (fn / "app.json").write_text(json.dumps({"app": "acme-rlg", "version": "1.1.1", "runs": "function",
                                                 "handler": "apps/acme_rlg/service/app.lambda_handler",
                                                 "package": ["lib", "apps/acme_rlg/service"]}))
        import zipfile
        names = zipfile.ZipFile(io.BytesIO(HO.folder_zip(fn, self.tmp / "kit"))).namelist()
        self.assertEqual(names, ["app.json", "apps/acme_rlg/service/app.py", "lib/helper.py"])
        m, bad = HO.push_checks(fn)  # without --root its package paths are not in its folder
        self.assertTrue(any("--root" in b for b in bad), bad)
        self.assertTrue(kit.exists())

    def test_save_writes_the_zip_and_sends_nothing(self):
        out_zip = self.tmp / "v.zip"
        with self.fake_send(self.ANSWER):
            code, out = run("push", str(self.app), "--partner", "acme", "--save", str(out_zip))
        self.assertEqual(code, 0, out)
        self.assertEqual((self.sent, out_zip.read_bytes()), ([], HO.folder_zip(self.app)))
        self.assertIn("Nothing was sent", out)


class Back(Base):
    def test_back_names_the_earlier_version_and_builds_nothing(self):
        with self.fake_send({"order": "0123456789abcdef", "version": "1.0.3", "from": "1.0.1", "built": False}):
            code, out = run("back", "--partner", "acme", "--order", "0123456789abcdef", "--to", "1.0.1", "--key", str(self.key))
        self.assertEqual(code, 0, out)
        self.assertEqual((self.body()["cmd"], self.body()["to"]), ("back", "1.0.1"))
        self.assertNotIn("version", self.body())
        self.assertIn("1.0.3 holds 1.0.1's content", out)
        with self.fake_send({}):
            self.assertEqual(run("back", "--partner", "acme", "--order", "x", "--to", "1.0.1", "--key", str(self.key))[0], 1)


def cut_answer(*args, **kwargs):
    """What ``urlopen`` / ``opener.open`` give back when the answer starts and the connection closes before its end: reading it
    raises ``http.client.IncompleteRead``, an ``HTTPException`` that is not an ``OSError``."""
    class Answer:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *n):
            raise http.client.IncompleteRead(b"")
    return Answer()


class AnswerCutShort(unittest.TestCase):
    """An answer cut short (``http.client.IncompleteRead``) is handled on the path a refused connection already takes."""

    def test_a_hosting_answer_cut_short_is_nothing_known_to_be_done_never_a_crash(self):
        with mock.patch.object(HO.urllib.request, "urlopen", cut_answer):
            with self.assertRaises(HO.Stop) as e:
                HO.send(b"{}")
        self.assertIn("could not be reached (IncompleteRead); nothing is known to be done", str(e.exception))


if __name__ == "__main__":
    unittest.main()
