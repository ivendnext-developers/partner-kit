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
        if getattr(self, "sandbox", None):
            out["sandbox"] = self.sandbox
        if getattr(self, "back", None):
            out["company"][0]["back_words"] = self.back
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
            out["send"] = [*(out.get("send") or []), {"site": ACME_LIVE, "message": "shelf message for " + ACME_LIVE}]
            out["install_now"] = [{"site": ACME_LIVE, "key_address": ACME_LIVE, "label": "Acme live",
                                   "installed": bool(getattr(self, "publish_status_installed", False))}]
        return out

    def sites_remove(self, b):
        self.remove_body = b
        return super().sites_remove(b) if b.get("app") else {**self.sites({}), "removed": b["site"]}

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

    def capture_read(self, b):  # J3: the site's records a person made, as the hosting answers them (packed: J3b)
        self.captured_from = b["site"]
        if getattr(self, "empty_site", False):
            return {"site": "acme.sandbox.ivend.co", "installs": [], "records": {}}
        if getattr(self, "no_read", False):  # the site refuses the key every type
            raise B.Refuse("no_read", "acme.sandbox.ivend.co did not let the key read its set-up (it answered 403)", 409)
        import base64, gzip  # noqa: E401, PLC0415
        return {"site": "acme.sandbox.ivend.co", "packed": base64.b64encode(gzip.compress(B.json.dumps({
            "installs": [], "others": [["POS Invoice", "custom_gift_note"]], "records": self.recorded(),
            "unread": getattr(self, "unread", [])}).encode())).decode()}

    def recorded(self):
        return {
            "Custom Field": [{"name": "Purchase Order-custom_gift_note", "owner": "c@acme.example", "dt": "Purchase Order",
                              "fieldname": "custom_gift_note", "fieldtype": "Data", "label": "Gift note"}],
            "Notification": [{"name": "Gift note set", "owner": "c@acme.example", "enabled": 1, "document_type": "Purchase Order",
                              "event": "Save", "channel": "System Notification", "subject": "Gift note",
                              "message": "{{ doc.custom_gift_note }}", "recipients": [{"receiver_by_role": "Purchase User"}]}],
            "Client Script": [{"name": "PO colour", "owner": "c@acme.example"}],
            "Report": [{"name": "Gift notes at the till", "owner": "c@acme.example", "is_standard": "No",
                        "report_type": "Report Builder", "ref_doctype": "POS Invoice",
                        "json": B.json.dumps({"fields": [["custom_gift_note", "POS Invoice"]]})}]}

    ROUTES = {**B.Stub.ROUTES, "/v1/capture/read": capture_read, "/v1/sites": sites, "/v1/sites/add": sites_add, "/v1/sites/label": sites_label,
              "/v1/sites/default": sites_default, "/v1/sites/remove": sites_remove, "/v1/publish/status": publish_status, "/v1/try": try_start,
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

    def test_one_of_our_developers_with_no_sandbox_reads_get_a_sandbox_first(self):  # J6 F15
        self.stub.sandbox = "get"
        rc, out = self.run_ivn("sites")
        self.assertEqual(out.splitlines()[0], B.ivn.WORDS["get_sandbox_first"])

    def test_a_pool_sandbox_names_its_owner_and_the_date_it_goes_back(self):  # the page's words, as the hosting says
        self.stub.labels["acme.sandbox.ivend.co"] = "nw-dev's sandbox"
        self.stub.back = "Goes back to the pool on 2027-01-09 unless someone signs in to it."
        rc, out = self.run_ivn("sites")
        self.assertEqual(out.splitlines()[:2], [
            "nw-dev's sandbox · acme.sandbox.ivend.co  one press, with our key · ivn try uses it",
            "    Goes back to the pool on 2027-01-09 unless someone signs in to it."])

    def test_add_reads_the_key_from_a_build_servers_variables_never_an_argument(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_SITE_KEY": "k1", "IVN_SITE_SECRET": "s1"}):
            rc, out = self.run_ivn("sites", "add", "shop.acme.example")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.stub.added, {"site": "shop.acme.example", "key": "k1", "secret": "s1"})
        self.assertIn("Added shop.acme.example: Try installs there in one press", out)
        self.assertNotIn("s1", out)  # the secret is never printed
        self.assertIn("shop.acme.example  one press, with your key", out)

    def test_add_takes_its_label_at_once(self):
        rc, out = self.run_ivn("sites", "add", "live.acme.example", "--label", "Acme live")
        self.assertEqual((rc, self.stub.added), (0, {"site": "live.acme.example", "label": "Acme live"}))

    def test_add_without_a_key_keeps_the_shelf_route(self):
        rc, out = self.run_ivn("sites", "add", "other.acme.example")
        self.assertEqual((rc, self.stub.added), (0, {"site": "other.acme.example"}))
        self.assertIn("its administrator installs what you try there", out)

    def test_use_label_and_remove(self):
        rc, out = self.run_ivn("sites", "label", "shop.acme.example", "Acme test")
        self.assertEqual((rc, self.stub.labels), (0, {"shop.acme.example": "Acme test"}))
        rc, out = self.run_ivn("sites", "use", "Acme test")
        self.assertEqual(out.splitlines()[0], "Acme test is your default: Try uses it.")
        rc, out = self.run_ivn("sites", "remove", "other.acme.example")
        self.assertEqual((rc, self.stub.remove_body), (0, {"site": "other.acme.example", "mine": True}))
        out = out.replace("other.acme.example", "shop.acme.example")
        self.assertIn("shop.acme.example is off your list, with the key you added for it. (ivn remove-site stops an app "
                      "reaching a site.)", out)

    def test_removing_one_of_ours_says_it_stays(self):
        rc, out = self.run_ivn("sites", "remove", "acme.sandbox.ivend.co")
        self.assertIn("acme.sandbox.ivend.co is still on your list: it is one of our sandboxes", out)

    def test_publish_without_install_installs_nothing_and_a_done_site_is_skipped(self):
        folder, _ = self.made()
        self.in_app(folder)
        rc, out = self.run_ivn("publish", "--to", "Acme live", "--plan", "starter", stdin="1\n")
        self.assertEqual((rc, self.stub.installs), (0, 0))
        self.assertIn(B.ivn.WORDS["install_hint"].format(name=f"Acme live ({ACME_LIVE})", to="Acme live"), out)  # J6f F2
        self.assertNotIn("shelf message for " + ACME_LIVE, out)  # nothing to forward to its administrator
        self.stub.publish_status_installed = True
        rc, out = self.run_ivn("publish", "--to", "Acme live", "--plan", "starter", "--install", stdin="1\n")
        self.assertEqual((rc, self.stub.installs), (0, 0))
        self.assertNotIn("Installing", out)
        self.assertNotIn("your company holds its key", out)  # --install installs: no hint

    def test_capture_writes_what_was_made_in_desk_renamed_and_says_what_it_left_out(self):  # ⭐ J3
        folder, _ = self.made()
        self.in_app(folder)
        rc, out = self.run_ivn("capture", "--site", "Acme test")
        self.assertEqual((rc, self.stub.captured_from), (0, "Acme test"), out)
        self.assertIn("Custom Field: Purchase Order-custom_gift_note", out)
        self.assertIn("Left out: Client Script PO colour:", out)
        m = B.json.loads((folder / "manifest.json").read_text("utf-8"))
        fp = m["prefix"].lower().replace(" ", "_") + "_"
        self.assertIn(fp + "gift_note", [c["fieldname"] for c in m["custom_fields"]])
        self.assertIn("{{ doc." + fp + "gift_note }}", [n["message"] for n in m["notifications"]])
        self.assertEqual(m["reports"][0]["columns"], ["custom_gift_note"])  # POS Invoice's own field of that name stays
        self.assertNotIn("Not read by Capture yet", out)
        self.assertIn("CHECK GREEN", out)
        rc, out = self.run_ivn("capture", "--site", "Acme test", "--skip", "Notification", "--skip", "Custom Field", "--skip", "Report")
        self.assertEqual(rc, 1)
        self.assertIn(B.ivn.WORDS["capture_none"], out)

    def test_capture_new_on_a_site_with_nothing_makes_no_app(self):  # the critic: never an empty app left behind
        self.stub.empty_site = True
        news = []
        real = type(self.stub).ROUTES["/v1/new"]
        with B.unittest.mock.patch.dict(type(self.stub).ROUTES, {"/v1/new": lambda st, b: news.append(b) or real(st, b)}):
            rc, out = self.run_ivn("capture", "--site", "Acme test", "--new", "acme_po_rules")
            made_on_empty = list(news)
            self.stub.empty_site = False  # the same stub on a site with something: the app is made, so the spy sees it
            rc2, _ = self.run_ivn("capture", "--site", "Acme test", "--new", "acme_po_rules2")
        self.assertEqual((rc, made_on_empty), (0, []), out)
        self.assertEqual([b.get("name") for b in news], ["ACME PO RULES2"])  # only the site with something made an app
        self.assertIn("a new app (none was made)", out)
        self.assertIn(B.ivn.WORDS["capture_nothing"].format(folder="a new app (none was made)"), out)

    def test_capture_with_a_partners_own_key_reads_the_rest_and_names_what_it_may_not(self):  # ⭐ J6 F17
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.unread = ["Server Script", "Web Page"]
        rc, out = self.run_ivn("capture", "--site", "Acme test")
        self.assertEqual(rc, 0, out)
        self.assertIn("Left out: Server Script (all): not read: this key may not read it (Script Manager may)", out)
        self.assertIn("Website Manager may", out)
        self.assertIn("CHECK GREEN", out)

    def test_a_refused_capture_exits_1(self):  # J6 F17: the walk's transcript read 0
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.no_read = True
        rc, out = self.run_ivn("capture", "--site", "Acme test")
        self.assertEqual(rc, 1, out)
        self.assertIn("did not let the key read", out)

    def test_capture_new_with_another_companys_word_says_so_before_reading(self):  # ⭐ J6 F18
        asked = []
        refuse = lambda st, b: (_ for _ in ()).throw(B.Refuse("name_word", "Your company's apps start with ACME.", 409))
        with B.unittest.mock.patch.dict(type(self.stub).ROUTES, {"/v1/name": lambda st, b: asked.append(b) or refuse(st, b)}):
            rc, out = self.run_ivn("capture", "--site", "Acme test", "--new", "other_po_rules")
        self.assertEqual((rc, asked, getattr(self.stub, "captured_from", None)), (1, [{"app": "other_po_rules"}], None), out)
        self.assertIn("Your company's apps start with ACME.", out)

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
        self.assertIn("1.0.0 published to Acme live (retail.acme.example).", out)
        self.assertIn("Installing 1.0.0 on retail.acme.example…\n  New in Desk\n    Members: a new list", out)
        self.assertIn("Installed 1.0.0 on retail.acme.example.", out)


if __name__ == "__main__":
    unittest.main()
