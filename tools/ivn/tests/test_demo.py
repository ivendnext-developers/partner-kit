"""`ivn demo` (DEMOPACKS): the demo packs on a sandbox of ours, from the same doors as My sites: list, load, reset,
refresh, remove and the pack's logins.

    python3 -m unittest discover -s tools/ivn/tests
"""

import unittest

import test_ivn as B  # noqa: I001  (first: it puts ivn on the path)

OURS = "acme.sandbox.ivend.co"
PACKS = [{"id": "travel-retail", "title": "Travel retail", "about": "An airport chain.", "company": "Corvane Travel Retail"},
         {"id": "multi-category", "title": "Multi-category retail", "about": "One department store with a department for each retail industry.",
          "company": "Demo Retail", "default": True}]
LOGINS = [{"user": "cashier1@demo-retail.example", "username": "cashier1", "password": "Demo-abc", "role": "Cashier", "name": "Cashier 1"},
          {"user": "manager@demo-retail.example", "username": "manager", "password": "Demo-xyz", "role": "Store manager", "name": "Store Manager"}]


class Stub(B.Stub):
    """The demo doors, as the hosting answers them (selfserve/functions/myapps_demo.py)."""

    def __init__(self, tmp):
        super().__init__(tmp)
        self.loaded, self.job, self.demo_polls, self.runs, self.fail, self.yours = set(), None, 0, [], None, []
        self.stopped, self.away = False, False

    def sites(self, b):
        return {"company": [{"site": OURS, "key_address": OURS, "press": True, "route": "ours", "ours": True}], "default": getattr(self, "default", OURS)}

    def demo(self, b):
        if not b.get("site"):
            return {"packs": PACKS}
        if b["site"] != OURS:
            raise B.Refuse("demo_not_ours", f"Demo data is offered on the sandboxes we hand out, and {b['site']} is not one of yours: "
                                            "nothing is loaded there. Request a sandbox on My sites, then load a pack on it.")
        rows = [{**p, "loaded": p["id"] in self.loaded, "can": ["reset", "refresh", "remove"] if p["id"] in self.loaded else ["load"]} for p in PACKS]
        if self.stopped:  # the last load stopped part-way: the door says so on the pack and offers Load again
            rows[0].update(loaded=True, can=["load", "remove"], words="The last load of Multi-category retail stopped part-way. Press Load to run it again.")
        out = {"site": OURS, "packs": rows, "yours": self.yours}
        if self.job and self.demo_polls < 3 and self.away:
            out["running"] = {"site": OURS, "pack": self.job["pack"], "verb": self.job["verb"], "title": "Multi-category retail", "by": "nw-dev", "step": "running"}
        return out

    def demo_run(self, b):
        self.demo({"site": b["site"]})
        if b["verb"] != "load" and b["pack"] not in self.loaded:
            raise B.Refuse("demo_not_loaded", f"Multi-category retail is not on {OURS} yet. Load it first.")
        self.runs.append((b["site"], b["pack"], b["verb"]))
        self.job, self.demo_polls = b, 0
        return {"site": OURS, "pack": b["pack"], "verb": b["verb"], "step": "running", "lines": [f"Loading Multi-category retail on {OURS}. This takes a few minutes."]}

    def demo_status(self, b):
        self.demo_polls += 1
        j = self.job
        lines = [f"Loading Multi-category retail on {OURS}. This takes a few minutes.", "Company", "Stores"][:1 + self.demo_polls]
        if self.demo_polls < 3:
            return {"site": OURS, "pack": j["pack"], "verb": j["verb"], "step": "running", "lines": lines}
        if self.fail:
            return {"site": OURS, "pack": j["pack"], "verb": j["verb"], "step": "stopped", "lines": lines, "stop": self.fail}
        if j["verb"] == "remove":
            self.loaded.discard(j["pack"])
            return {"site": OURS, "step": "done", "done": True, "lines": lines + [f"Multi-category retail is off {OURS}."]}
        self.loaded.add(j["pack"])
        return {"site": OURS, "step": "done", "done": True, "lines": lines + [f"Multi-category retail is loaded on {OURS}. Its logins are below."],
                "logins": LOGINS, "logins_words": "Sign in at the till with a till ID and its password. These are test logins on your sandbox."}

    def demo_logins(self, b):
        if b["pack"] not in self.loaded:
            raise B.Refuse("demo_not_loaded", f"Multi-category retail is not on {OURS} yet. Load it first.")
        return {"site": OURS, "pack": b["pack"], "logins": LOGINS}

    ROUTES = {**B.Stub.ROUTES, "/v1/sites": sites, "/v1/demo": demo, "/v1/demo/run": demo_run, "/v1/demo/status": demo_status, "/v1/demo/logins": demo_logins}


class Demo(B.Base):
    def setUp(self):
        super().setUp()
        self.stub.__class__ = Stub
        Stub.__init__(self.stub, self.tmp)
        self.stub.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        patch = unittest.mock.patch.object(B.Stub, "ROUTES", Stub.ROUTES)
        patch.start()
        self.addCleanup(patch.stop)
        self.index({"samples": []})

    def test_the_packs_are_listed_the_one_to_start_with_first(self):
        code, out = self.run_ivn("demo")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], f"Demo data on {OURS}:")
        self.assertEqual(lines[1], "multi-category  Multi-category retail · start with this one")
        self.assertEqual(lines[2], "    One department store with a department for each retail industry.")
        self.assertEqual(lines[3], "travel-retail  Travel retail")
        self.assertEqual(lines[-1], "Next: ivn demo load multi-category")                      # an empty sandbox: the one line to type

    def test_a_job_started_elsewhere_is_followed_to_its_end(self):
        # the developer pressed Load on My sites, or closed the terminal: `ivn demo` picks the running job up
        self.stub.job, self.stub.away = {"site": OURS, "pack": "multi-category", "verb": "load"}, True
        code, out = self.run_ivn("demo")
        self.assertEqual(code, 0)
        self.assertIn("Running now: Multi-category retail (load), started by nw-dev.", out)
        self.assertIn(f"Multi-category retail is loaded on {OURS}. Its logins:", out)
        self.assertIn("  cashier1  Demo-abc  Cashier  cashier1@demo-retail.example", out)

    def test_a_load_that_stopped_earlier_is_said_with_the_command_that_runs_it_again(self):
        self.stub.stopped = True
        code, out = self.run_ivn("demo")
        self.assertEqual(code, 0)
        self.assertIn("    The last load of Multi-category retail stopped part-way. Run ivn demo load again.", out)
        self.assertNotIn("Next: ivn demo load", out)

    def test_load_follows_the_job_and_ends_with_the_logins_and_what_to_run_next(self):  # ⭐ one command
        code, out = self.run_ivn("demo", "load", "multi-category")
        self.assertEqual(code, 0)
        self.assertEqual(self.stub.runs, [(OURS, "multi-category", "load")])
        lines = out.splitlines()
        self.assertEqual(lines[:4], [f"Loading Multi-category retail on {OURS}. This takes a few minutes.", "Company", "Stores",
                                     f"Multi-category retail is loaded on {OURS}. Its logins:"])   # a terminal has no "below"
        self.assertIn("  cashier1  Demo-abc  Cashier  cashier1@demo-retail.example", lines)
        self.assertIn("  manager   Demo-xyz  Store manager  manager@demo-retail.example", lines)
        self.assertTrue(lines[-1].startswith("Next: ivn demo reset multi-category before a demo"))
        code, out = self.run_ivn("demo", "list")
        self.assertIn("multi-category  Multi-category retail · loaded", out)

    def test_reset_refresh_and_remove_each_run_one_job(self):
        self.stub.loaded = {"multi-category"}
        for verb in ("reset", "refresh", "remove"):
            self.assertEqual(self.run_ivn("demo", verb, "multi-category")[0], 0)
        self.assertEqual([r[2] for r in self.stub.runs], ["reset", "refresh", "remove"])
        self.assertEqual(self.stub.loaded, set())

    def test_a_pack_not_loaded_is_refused_in_the_doors_words(self):
        code, out = self.run_ivn("demo", "reset", "multi-category")
        self.assertEqual((code, out.strip()), (1, f"Multi-category retail is not on {OURS} yet. Load it first."))

    def test_a_site_of_your_own_is_refused_when_named_and_only_lists_the_packs_when_it_is_your_default(self):
        code, out = self.run_ivn("demo", "load", "multi-category", "--site", "shop.customer.example")
        self.assertEqual(code, 1)
        self.assertIn("Request a sandbox on My sites", out)
        self.assertEqual(self.stub.runs, [])
        self.stub.default = "shop.customer.example"
        code, out = self.run_ivn("demo")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("The demo packs. Load one on a sandbox of ours with ivn demo load <pack>:"))

    def test_a_job_that_stops_says_what_to_run(self):
        self.stub.fail = "It stopped. Nothing else was changed after the last line above. Press Load to run it again: every step reads before it writes."
        code, out = self.run_ivn("demo", "load", "multi-category")
        self.assertEqual(code, 1)
        self.assertIn("Run ivn demo load again: every step reads before it writes.", out)

    def test_the_logins_again_and_what_is_yours(self):
        self.stub.loaded, self.stub.yours = {"multi-category"}, ["Acme Test Co"]
        code, out = self.run_ivn("demo", "logins", "multi-category")
        self.assertEqual(code, 0)
        self.assertIn("cashier1  Demo-abc", out)
        self.assertIn("Your own on this site, never touched by a pack: Acme Test Co.", self.run_ivn("demo")[1])

    def test_a_verb_without_a_pack_says_the_usage(self):
        code, out = self.run_ivn("demo", "load")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("ivn demo [list | load <pack>"))


if __name__ == "__main__":
    unittest.main()
