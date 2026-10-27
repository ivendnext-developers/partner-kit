"""deploy-app: the template plans; every refusal fires; nothing it prints carries a value. No cloud, no network."""
import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import deploy_app  # noqa: E402

TEMPLATE = HERE.parents[1] / "app_template"
IMAGE = "416648266684.dkr.ecr.us-east-1.amazonaws.com/partner-apps/my-till-key:1.0.0"


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = deploy_app.main(list(argv))
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.app = self.tmp / "app"
        shutil.copytree(TEMPLATE, self.app, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        (self.app / "LICENSE").write_text("Apache License, Version 2.0\n", "utf-8")  # the builder fills the template's

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def settings(self, **change):
        m = json.loads((self.app / "app.json").read_text())
        m.update(change)
        (self.app / "app.json").write_text(json.dumps(m))

    def refused(self, *extra, image=IMAGE, plan="starter"):
        code, out = run(str(self.app), "--image", image, "--plan", plan, "--partner", "acme", *extra)
        self.assertEqual(code, 1, out)
        self.assertIn("nothing planned", out)
        return out


class Plans(Base):
    def test_the_template_plans_with_its_address_and_block(self):
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme")
        self.assertEqual(code, 0, out)
        self.assertIn("https://my-till-key.ivendnext.app", out)
        self.assertIn('module "app_my_till_key"', out)
        self.assertIn('secret_names = ["IVN_POINT_SECRET"]', out)
        self.assertIn("Nothing was changed", out)

    def test_the_optional_secret_is_not_wired_until_used(self):
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme", "--json")
        d = json.loads(out)
        self.assertEqual(d["secrets_to_supply"], ["IVN_POINT_SECRET"])
        self.assertEqual(d["secrets_added_when_used"], ["IVN_POINT_SECRET_PREVIOUS"])
        self.assertNotIn("IVN_POINT_SECRET_PREVIOUS", d["infrastructure_block"])

    def test_an_app_that_serves_many_shops_gets_its_table(self):
        self.settings(shops=True)
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme", "--json")
        d = json.loads(out)
        self.assertIn("  shops        = true\n", d["infrastructure_block"])
        self.assertTrue(any("shops table" in c for c in d["creates"]))
        self.settings(shops=False)
        d = json.loads(run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme", "--json")[1])
        self.assertNotIn("shops", d["infrastructure_block"])
        self.settings(shops="yes")
        self.assertIn("shops: true or false", self.refused())

    def test_a_staging_copy_gets_its_own_address(self):
        self.settings(app="stock-sync")
        code, out = run(str(self.app), "--image", IMAGE.replace("my-till-key", "stock-sync"), "--plan", "standard",
                        "--partner", "acme", "--env", "staging", "--json")
        self.assertEqual(code, 0, out)
        d = json.loads(out)
        self.assertEqual(d["address"], "https://stock-sync-staging.ivendnext.app")
        self.assertIn('env          = "staging"', d["infrastructure_block"])

    def test_the_plan_enforces_what_plans_json_says(self):
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "managed", "--partner", "acme", "--json")
        d = json.loads(out)
        self.assertEqual(d["enforced"], deploy_app.PLANS["plans"]["managed"]["enforced"])
        self.assertEqual(d["enforced"]["instances"], 2)

    def test_a_customer_tag_reaches_the_block(self):
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "managed", "--partner", "citixsys-cd", "--customer", "acme-stores")
        self.assertEqual(code, 0, out)
        self.assertIn('customer     = "acme-stores"', out)
        self.assertIn("for citixsys-cd (customer acme-stores)", out)

    def test_it_prints_the_exact_put_live_order(self):
        self.settings(app="stock-sync")
        _, out = run(str(self.app), "--image", IMAGE.replace("my-till-key", "stock-sync"), "--plan", "standard",
                     "--partner", "acme", "--env", "staging", "--json")
        d = json.loads(out)
        self.assertEqual(d["put_live"][0], "tofu apply -exclude=module.app_stock_sync_staging.aws_ecs_service.this")
        self.assertIn('module "app_stock_sync_staging"', d["infrastructure_block"])

    def test_no_price_appears(self):
        _, out = run(str(self.app), "--image", IMAGE, "--plan", "managed", "--partner", "acme", "--json")
        self.assertNotRegex(out, r"\$|USD|price")


class Refuses(Base):
    def test_latest(self):
        self.assertIn("never 'latest'", self.refused(image=IMAGE.replace(":1.0.0", ":latest")))

    def test_a_tag_other_than_the_version(self):
        self.assertIn("app's version", self.refused(image=IMAGE.replace(":1.0.0", ":1.0.1")))

    def test_a_digest_instead_of_the_version_tag(self):
        self.assertIn("image:", self.refused(image=IMAGE.rsplit(":", 1)[0] + "@sha256:" + "a" * 64))

    def test_a_staging_copy_on_a_plan_without_one(self):
        self.assertIn("not on the starter plan", self.refused("--env", "staging"))

    def test_a_bad_customer_name(self):
        self.assertIn("customer:", self.refused("--customer", "Acme Stores"))

    def test_a_size_that_is_not_a_word_is_refused_not_a_crash(self):
        self.settings(size={})
        self.assertIn("size: one of", self.refused())

    def test_a_version_in_non_western_digits(self):
        self.settings(version="\u0661.\u0660.\u0660")
        self.assertIn("version:", self.refused(image=IMAGE.replace(":1.0.0", ":\u0661.\u0660.\u0660")))

    def test_an_untagged_image(self):
        self.assertIn("image:", self.refused(image=IMAGE.rsplit(":", 1)[0]))

    def test_a_size_the_plan_does_not_allow(self):
        self.settings(size="large")
        self.assertIn("not on the starter plan", self.refused())

    def test_an_unknown_plan(self):
        self.assertIn("plan: one of", self.refused(plan="gold"))

    def test_a_region_not_served(self):
        self.settings(region="de")
        self.assertIn("not served yet", self.refused())

    def test_a_reserved_name(self):
        self.settings(app="admin")
        self.assertIn("reserved", self.refused(image=IMAGE.replace("my-till-key", "admin")))

    def test_a_name_ending_in_an_environment(self):
        self.settings(app="shop-staging")
        self.assertIn("environment's name", self.refused())

    def test_a_bad_partner_name(self):
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "Acme Ltd")
        self.assertEqual(code, 1)
        self.assertIn("partner:", out)

    def test_what_the_template_checker_refuses(self):
        (self.app / "Dockerfile").write_text((self.app / "Dockerfile").read_text().replace("USER app", ""))
        self.assertIn("not root", self.refused())

    def test_a_value_in_the_settings_file(self):
        self.settings(env=[{"name": "IVN_POINT_SECRET", "secret": True, "required": True, "value": "x"}])
        self.assertIn("never values", self.refused())

    def test_usage_errors_exit_2(self):
        code, _ = run(str(self.app))
        self.assertEqual(code, 2)


class PlansData(unittest.TestCase):
    def test_every_plan_has_enforced_sizes_that_exist(self):
        for name, p in deploy_app.PLANS["plans"].items():
            self.assertTrue(set(p["enforced"]["sizes"]) <= set(deploy_app.PLANS["sizes"]), name)
            self.assertGreaterEqual(p["enforced"]["instances"], 1, name)
            self.assertTrue(set(p["enforced"]["envs"]) <= set(deploy_app.PLANS["envs"]), name)
            self.assertIn("prod", p["enforced"]["envs"], name)
            self.assertIn(p["enforced"]["log_days"], (1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365), name)



class LicenceIntake(Base):
    """The hosting intake runs the licence check with the hosted rule."""

    def test_the_templates_unfilled_licence_is_refused(self):
        shutil.copy(TEMPLATE / "LICENSE", self.app / "LICENSE")
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme")
        self.assertEqual(code, 1)
        self.assertIn("placeholder", out)

    def test_a_hosted_agpl_component_needs_its_published_source(self):
        with (self.app / "THIRD_PARTY.md").open("a", encoding="utf-8") as f:
            f.write("- some-engine 2.1, AGPL-3.0\n")
        code, out = run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme")
        self.assertEqual(code, 1)
        self.assertIn("AGPL component", out)
        (self.app / "THIRD_PARTY.md").write_text("- some-engine 2.1, AGPL-3.0, source https://example.org/se\n", "utf-8")
        self.assertEqual(run(str(self.app), "--image", IMAGE, "--plan", "starter", "--partner", "acme")[0], 0)


class ContainerUnchanged(Base):
    """An app that says nothing about `runs` gets exactly the block and steps it got before functions existed."""

    def test_the_template_block_and_steps_are_pinned(self):
        m = json.loads((self.app / "app.json").read_text())
        d = deploy_app.describe(m, IMAGE, "starter", "acme", "prod")
        self.assertEqual(d["infrastructure_block"], (
            'module "app_my_till_key" {\n  source       = "../modules/app"\n  name         = "my-till-key"\n'
            '  partner      = "acme"\n  plan         = "starter"\n  env          = "prod"\n  size         = "small"\n'
            '  image_tag    = "1.0.0"\n  port         = 8080\n  health       = "/health"\n'
            '  secret_names = ["IVN_POINT_SECRET"]\n  platform     = local.platform\n}\n'))
        self.assertEqual(d["put_live"], ["tofu apply -exclude=module.app_my_till_key.aws_ecs_service.this",
                                         "copy the image into the app's registry with its version tag, and put each secret's value",
                                         "tofu apply   (only the service is left to create)"])
        self.assertNotIn("runs", d)
        self.assertEqual(d["includes"], deploy_app.PLANS["plans"]["starter"]["includes"])


class Functions(unittest.TestCase):
    """A press-only app (app.json "runs": "function") is planned as a function paid per call: S18 is the kit's one."""
    KIT = HERE.parents[2]
    S18 = KIT / "samples" / "s18_rule_guard"

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.zip = self.tmp / "rule-guard-1.0.0.zip"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def plan(self, *extra):
        return run(str(self.S18), "--zip", str(self.zip), "--root", str(self.KIT), "--plan", "starter",
                   "--partner", "citixsys", *extra)

    def test_s18_plans_as_a_function_with_its_block(self):
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("https://rule-guard.ivendnext.app", out)
        self.assertIn('source      = "../modules/function"', out)
        self.assertIn('handler     = "samples/s18_rule_guard/service/app.lambda_handler"', out)
        self.assertIn("run only when called", out)
        self.assertNotIn("container", out.split("Nothing was changed")[1])
        self.assertNotIn("image", out.split("Nothing was changed")[1])

    def test_the_package_holds_the_handler_and_the_template_and_no_dot_file(self):
        import zipfile
        dot = self.S18 / "service" / ".env.test-only"
        dot.write_text("PP_POINT_SECRET=never-in-a-package\n")
        try:
            self.assertEqual(self.plan()[0], 0)
        finally:
            dot.unlink()
        names = zipfile.ZipFile(self.zip).namelist()
        self.assertIn("samples/s18_rule_guard/service/app.py", names)
        self.assertIn("tools/app_template/service/shops.py", names)
        self.assertIn("samples/s18_rule_guard/rule.py", names)
        self.assertFalse([n for n in names if "/." in n or "__pycache__" in n or n.startswith("samples/s18_rule_guard/tests")])

    def test_the_package_is_the_same_bytes_each_time(self):
        self.assertEqual(self.plan()[0], 0)
        first = self.zip.read_bytes()
        self.assertEqual(self.plan()[0], 0)
        self.assertEqual(first, self.zip.read_bytes())

    def test_a_function_takes_no_image_and_needs_its_zip(self):
        code, out = run(str(self.S18), "--image", IMAGE, "--zip", str(self.zip), "--root", str(self.KIT),
                        "--plan", "starter", "--partner", "citixsys")
        self.assertEqual(code, 1)
        self.assertIn("a function is not an image", out)
        code, out = run(str(self.S18), "--root", str(self.KIT), "--plan", "starter", "--partner", "citixsys")
        self.assertEqual(code, 1)
        self.assertIn("a function needs --zip", out)

    def test_a_scheduled_function_prints_its_schedule_and_timeout(self):
        code, out = run(str(self.KIT / "samples" / "s25_gift_on_spend"), "--zip", str(self.zip), "--root", str(self.KIT),
                        "--plan", "starter", "--partner", "citixsys")
        self.assertEqual(code, 0, out)
        self.assertIn('  timeout     = 120\n  schedule    = { pass = "rate(1 minute)" }\n', out)
        self.assertIn("run only when called or on its schedule", out)
        self.assertIn("a schedule pass: the function runs rate(1 minute) (UTC)", out)

    def test_a_press_only_function_prints_no_schedule(self):
        out = self.plan()[1]
        self.assertNotIn("schedule    =", out)
        self.assertNotIn("timeout     =", out)

    def test_the_package_paths_must_exist_from_the_root(self):
        code, out = run(str(self.S18), "--zip", str(self.zip), "--plan", "starter", "--partner", "citixsys")
        self.assertEqual(code, 1)
        self.assertIn("give --root", out)


if __name__ == "__main__":
    unittest.main()
