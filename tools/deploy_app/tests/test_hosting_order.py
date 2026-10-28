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
                   "address": "https://my-till-key.ivendnext.app",
                   "upload": {"image": "x/partner-apps/my-till-key", "github_role": "arn:aws:iam::1:role/partner-app-my-till-key-github"}},
                  {"order": "fedcba9876543210", "env": "sandbox", "id": "my-till-key-sandbox", "status": "waiting",
                   "waiting_for": ["IVN_POINT_SECRET"], "push_refused": "9.9.9", "address": "https://my-till-key-sandbox.ivendnext.app",
                   "upload": {"image": "x/partner-apps/my-till-key-sandbox",
                              "github_role": "arn:aws:iam::1:role/partner-app-my-till-key-sandbox-github"}}]}

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

    def test_each_copy_is_shown_with_where_it_stands_and_the_roles_to_set(self):
        with self.fake_send(self.ANSWER):
            code, out = self.order("--accept-schedule")
        self.assertIn("2 copies", out)
        self.assertIn("building (create)", out)
        self.assertIn("waiting for its secrets: IVN_POINT_SECRET", out)
        self.assertIn("version 9.9.9 was refused", out)
        self.assertIn("stops    at the end of the paid month (2026-12-27)", out)
        self.assertIn('IVN_HOSTING_ROLES to ["arn:aws:iam::1:role/partner-app-my-till-key-github",'
                      '"arn:aws:iam::1:role/partner-app-my-till-key-sandbox-github"]', out)

    def test_status_with_no_orders_says_so(self):
        with self.fake_send({"orders": []}):
            code, out = run("status", "--partner", "acme", "--key", str(self.key))
        self.assertEqual((code, out.strip()), (0, "no hosting orders yet"))

    def test_a_secret_names_its_copy(self):
        with self.fake_send({"order": "0123456789abcdef", "secret": "IVN_POINT_SECRET", "set": True}):
            run("secret", "--partner", "acme", "--order", "0123456789abcdef", "--env", "sandbox", "--name",
                "IVN_POINT_SECRET", "--key", str(self.key), stdin="v")
        self.assertEqual(self.body()["env"], "sandbox")


if __name__ == "__main__":
    unittest.main()
