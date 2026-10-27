"""deploy_app order | status | secret | cancel: the same checks as planning, a request signed over the hosting's own
domain (never the library upload's), the Schedule accepted out loud, and a secret's value never printed. No network:
the send is replaced."""
import contextlib
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
        m["env"].append({"name": "LOG_LEVEL", "secret": False, "required": False})  # one plain setting
        (self.app / "app.json").write_text(json.dumps(m))
        self.key = self.tmp / "signing.key"
        HO.publish.keygen(self.key)
        self.sent = []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fake_send(self, answer):
        def send(data):
            self.sent.append(json.loads(data))
            return 200, answer
        return mock.patch.object(HO, "send", send)

    def body(self, i=-1):
        env = self.sent[i]
        return json.loads(HO.publish.unb64u(env["body"]))

    def order(self, *extra):
        return run("order", str(self.app), "--plan", "starter", "--partner", "acme", "--github", "acme/points",
                   "--key", str(self.key), *extra)


class Order(Base):
    ANSWER = {"order": "0123456789abcdef", "id": "my-till-key", "plan": "starter", "status": "pending", "kind": "card",
              "address": "https://my-till-key.ivendnext.app", "checkout_url": "https://checkout.stripe.com/c/x",
              "upload": {"image": "x/partner-apps/my-till-key", "github_role": "arn:role"}, "secrets": ["IVN_POINT_SECRET"]}

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
        self.assertEqual(p["github"], {"repo": "acme/points", "branch": "main"})
        self.assertNotIn("value", json.dumps(p["app"]))  # names and shapes only

    def test_the_github_subject_must_name_the_same_repository(self):
        with self.fake_send(self.ANSWER):
            self.assertEqual(self.order("--accept-schedule", "--github-subject", "repo:zeta@1/points@2")[0], 1)
            self.assertEqual(self.order("--accept-schedule", "--github-subject", "repo:acme@101/points@202")[0], 0)
        self.assertEqual(self.body()["github"]["subject"], "repo:acme@101/points@202")

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


if __name__ == "__main__":
    unittest.main()
