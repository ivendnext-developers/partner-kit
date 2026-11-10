"""`ivn sites` (My sites): list, add with a key made on the site, use, label and remove; `ivn try --site` and
`ivn publish --to` take a label; `ivn publish --install` installs where the company holds the customer site's key.

    python3 -m unittest discover -s tools/ivn/tests
"""

import os
import unittest
import unittest.mock

import test_ivn as B  # noqa: I001  (first: it puts ivn on the path)

ACME_LIVE = "retail.acme.example"


class Stub(B.Stub):
    """The My sites doors, as the hosting answers them (selfserve/functions/accounts.py, myapps_try.py, myapps_pub.py)."""

    def __init__(self, tmp):
        super().__init__(tmp)
        self.labels, self.keys, self.default, self.installs = {}, {}, None, 0

    def sites(self, b):
        out = super().sites(b)
        for x in out["company"]:
            if x["site"] in self.labels:
                x["label"] = self.labels[x["site"]]
            if x["site"] in self.keys:
                x.update(route="own", press=True)
        out["company"].append({"site": ACME_LIVE, "key_address": ACME_LIVE, "press": True, "route": "own",
                               "label": "Acme live", "live": True})
        out["company"][0]["route"] = "ours"
        if self.default:
            out["default"] = self.default
        return out

    def sites_add(self, b):
        self.added = b
        if b.get("key"):
            self.keys[b["site"]] = (b["key"], b["secret"])
        return {**self.sites({}), "site": b["site"], "words": f"Added {b['site']}: Try installs there in one press, signed "
                                                              "in as admin@demo-retail.example." if b.get("key") else
                                                              f"Added {b['site']}: its administrator installs what you try "
                                                              "there, from the shelf key Try shows."}

    def sites_label(self, b):
        self.labels[b["site"]] = b["label"]
        return {**self.sites({}), "label": b["label"]}

    def sites_default(self, b):
        self.default = b["site"]
        return {**self.sites({}), "words": f"{b['site']} is your default: Try uses it."}

    def publish_status(self, b):
        out = super().publish_status(b)
        if out.get("done"):
            out["install_now"] = [{"site": ACME_LIVE, "label": "Acme live", "installed": False}]
        return out

    def try_start(self, b):
        self.asked_site = b.get("site")
        return super().try_start(b)

    def publish_install(self, b):
        if not b.get("sha"):
            return {"version": "1.0.0", "site": b["site"], "sha": "a" * 64, "button": "Install now",
                    "sections": [{"title": "New in Desk", "lines": ["Members: a new list"]}]}
        self.installs += 1
        done = self.installs > 1
        return {"version": "1.0.0", "site": b["site"], "step": "done" if done else "installing", "done": done,
                "words": f"Installed 1.0.0 on {b['site']}." if done else f"Installing on {b['site']}…"}

    ROUTES = {**B.Stub.ROUTES, "/v1/sites": sites, "/v1/sites/add": sites_add, "/v1/sites/label": sites_label,
              "/v1/sites/default": sites_default, "/v1/publish/status": publish_status, "/v1/try": try_start,
              "/v1/publish/install": publish_install}


class MySites(B.Base):
    def setUp(self):
        patch = unittest.mock.patch.object(B, "Stub", Stub)  # the stub's server reads its routes while each test runs
        patch.start()
        self.addCleanup(patch.stop)
        super().setUp()

    def test_the_list_says_each_sites_label_and_how_try_installs_there(self):
        self.stub.labels["shop.acme.example"] = "Acme test"
        rc, out = self.run_ivn("sites")
        self.assertEqual((rc, out.splitlines()), (0, [
            "acme.sandbox.ivend.co  one press, with our key · ivn try uses it",
            "Acme test · shop.acme.example  its administrator installs it from the shelf key ivn try prints",
            "Acme live · retail.acme.example  a customer's live site: ivn publish sends it the production copy"]))

    def test_add_reads_the_key_from_a_build_servers_variables_never_an_argument(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_SITE_KEY": "k1", "IVN_SITE_SECRET": "s1"}):
            rc, out = self.run_ivn("sites", "add", "shop.acme.example")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.stub.added, {"site": "shop.acme.example", "key": "k1", "secret": "s1"})
        self.assertIn("Added shop.acme.example: Try installs there in one press", out)
        self.assertNotIn("s1", out)  # the secret is never printed
        self.assertIn("shop.acme.example  one press, with your key", out)

    def test_add_without_a_key_keeps_the_shelf_route(self):
        rc, out = self.run_ivn("sites", "add", "other.acme.example")
        self.assertEqual((rc, self.stub.added), (0, {"site": "other.acme.example"}))
        self.assertIn("its administrator installs what you try there", out)

    def test_use_label_and_remove(self):
        rc, out = self.run_ivn("sites", "label", "shop.acme.example", "Acme test")
        self.assertEqual((rc, self.stub.labels), (0, {"shop.acme.example": "Acme test"}))
        rc, out = self.run_ivn("sites", "use", "Acme test")
        self.assertEqual(out.splitlines()[0], "Acme test is your default: Try uses it.")
        rc, out = self.run_ivn("sites", "remove", "shop.acme.example")
        self.assertEqual((rc, self.stub.removed), (0, "shop.acme.example"))
        self.assertIn("shop.acme.example is off your list, with the key you added for it. (ivn remove-site stops an app "
                      "reaching a site.)", out)

    def test_a_subcommand_without_its_site_says_how(self):
        rc, out = self.run_ivn("sites", "label", "shop.acme.example")
        self.assertEqual((rc, out.strip()), (1, B.ivn.WORDS["sites_usage"]))

    def test_try_and_publish_take_a_label_as_given(self):
        folder, _ = self.made()
        self.in_app(folder)
        rc, out = self.run_ivn("try", "--site", "Acme test")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.stub.asked_site, "Acme test")  # the hosting finds the site by its label

    def test_publish_install_shows_the_words_then_installs(self):
        folder, _ = self.made()
        self.in_app(folder)
        rc, out = self.run_ivn("publish", "--to", "Acme live", "--plan", "starter", "--install", stdin="1\n")
        self.assertEqual(rc, 0, out)
        self.assertIn("Installing 1.0.0 on retail.acme.example…\n  New in Desk\n    Members: a new list", out)
        self.assertIn("Installed 1.0.0 on retail.acme.example.", out)


if __name__ == "__main__":
    unittest.main()
