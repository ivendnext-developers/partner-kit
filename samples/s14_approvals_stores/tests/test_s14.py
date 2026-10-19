"""Laptop tests of S14's service (approvals_stores.py), no bench: an in-memory shop that speaks the few record-API calls the service makes.

    python3 -m unittest discover -s samples/s14_approvals_stores/tests -p 'test_*.py'
"""
import csv
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2] / "tools" / "feed_client")]
import approvals_stores as A  # noqa: E402
import feed_client as F  # noqa: E402

DAY = "2026-10-04"
GW, SAN = "Store A", "Store B"


class Shop:
    """requests, price rows, approval rules and the Version log, with the calls the service makes. ``calls`` records every write."""

    def __init__(self):
        self.reqs, self.prices, self.versions, self.calls, self.n = {}, {}, [], [], 0
        self.prices["IP-1"] = {"name": "IP-1", "item_code": "SKU-1", "price_list": "Retail", "selling": 1, "price_list_rate": 100.0, "modified": f"{DAY} 08:00:00"}
        self.clock = 0
        self.rules = {"mgr-a@x": {"name": "mgr-a@x", "level": "Store", "store": GW, "limit_pct": 10.0},
                      "mgr-b@x": {"name": "mgr-b@x", "level": "Store", "store": SAN, "limit_pct": 10.0},
                      "ho@x": {"name": "ho@x", "level": "Head Office", "store": None, "limit_pct": None},
                      "both@x": {"name": "both@x", "level": "Store", "store": GW, "limit_pct": 10.0},
                      "hoboth@x": {"name": "hoboth@x", "level": "Head Office", "store": None, "limit_pct": None}}
        for k, r in self.rules.items():
            r["user"] = k

    def request(self, item="SKU-1", rate=105.0, state=A.REQUESTED, owner="req@x", store=GW, day=DAY):
        self.n += 1
        name = f"PP-APS-{self.n:05d}"
        self.reqs[name] = {"name": name, "item": item, "price_list": "Retail", "new_rate": rate, "store": store, "reason": "r", "workflow_state": state,
                           "owner": owner, "creation": f"{day} 09:00:0{self.n % 10}", "modified": f"{day} 09:00:0{self.n % 10}"}
        return name

    def change(self, name, who, **fields):
        ch = []
        for k, v in fields.items():
            ch.append([k, self.reqs[name].get(k), v])
            self.reqs[name][k] = v
        self.versions.append({"docname": name, "owner": who, "creation": f"{DAY} 10:{len(self.versions) // 60:02d}:{len(self.versions) % 60:02d}", "data": json.dumps({"changed": ch})})

    def store_ok(self, name, who="mgr-a@x"):
        self.change(name, who, workflow_state=A.STORE_OK)

    def ho_ok(self, name, who="ho@x"):
        self.change(name, who, workflow_state=A.HO_OK)

    def call(self, method, path, params=None, body=None):
        parts = [urllib.parse.unquote(p) for p in path.split("/")[3:]]
        params = params or {}
        if method == "GET" and parts == ["ivendnext_mpos.api.v1.get_docinfo"]:
            vs = sorted([v for v in self.versions if v["docname"] == params["name"]], key=lambda v: v["creation"], reverse=True)[:10]
            return {"docinfo": {"versions": [{"name": f"V{i}", **v} for i, v in enumerate(vs)]}}
        if method == "GET" and parts[0] == A.DT and len(parts) == 2:
            return {"data": dict(self.reqs[parts[1]])}
        if method == "GET":
            flt = json.loads(params.get("filters", "[]"))
            rows = {A.DT: list(self.reqs.values()), "Item Price": list(self.prices.values()), A.RULE: list(self.rules.values())}[parts[0]]
            for f, op, v in flt:
                rows = [r for r in rows if _ok(r.get(f), op, v)]
            return {"data": [dict(r) for r in sorted(rows, key=lambda r: (r.get("creation", ""), r.get("name", "")))]}
        if method == "PUT":
            self.calls.append(("PUT", parts, body))
            self.clock += 1
            self.prices[parts[1]].update(body, modified=f"{DAY} 12:{self.clock // 60:02d}:{self.clock % 60:02d}")        # after every approval in these tests
            return {"data": self.prices[parts[1]]}
        if path.endswith("apply_workflow"):
            name = json.loads(body["doc"])["name"]
            self.calls.append(("ACTION", body["action"], name))
            if self.reqs[name]["workflow_state"] not in A.APPLY_STATES:
                raise F.FeedError("417 not a valid action in this state")
            self.change(name, "applier@x", workflow_state=A.APPLIED)
            return {"message": {}}
        raise AssertionError((method, path))


def _ok(have, op, want):
    if op == "in":
        return have in want
    return {"=": have == want, ">=": str(have) >= str(want), "<=": str(have) <= str(want), "<": str(have) < str(want)}[op]


class T(unittest.TestCase):
    def setUp(self):
        self.shop = Shop()

    def run_apply(self):
        return A.apply_all(self.shop)

    def price(self):
        return self.shop.prices["IP-1"]["price_list_rate"]

    def why(self, rep, name):
        return [x["why"] for x in rep["not_applied"] if x["request"] == name][0]

    # ── the limit and the two steps ──────────────────────────────────────────────────────────────────────────
    def test_a_change_within_the_store_managers_limit_is_applied_once_and_a_second_run_changes_nothing(self):
        r = self.shop.request(rate=110.0)                      # exactly 10 % — the limit itself is within it
        self.shop.store_ok(r)
        rep = self.run_apply()
        self.assertEqual([x["request"] for x in rep["applied"]], [r])
        self.assertEqual((self.price(), self.shop.reqs[r]["workflow_state"]), (110.0, A.APPLIED))
        n = len(self.shop.calls)
        self.assertEqual(self.run_apply(), {"applied": [], "not_applied": [], "skipped": []})
        self.assertEqual(len(self.shop.calls), n)

    def test_a_change_above_the_store_limit_waits_for_head_office_and_nothing_is_written(self):
        r = self.shop.request(rate=111.0)                      # 11 %
        self.shop.store_ok(r)
        rep = self.run_apply()
        self.assertIn("above the store manager's limit", self.why(rep, r))
        self.assertEqual((self.price(), self.shop.calls, self.shop.reqs[r]["workflow_state"]), (100.0, [], A.STORE_OK))

    def test_the_head_office_approval_releases_the_over_limit_change(self):
        r = self.shop.request(rate=150.0)
        self.shop.store_ok(r)
        self.assertEqual(self.run_apply()["applied"], [])
        self.shop.ho_ok(r)
        rep = self.run_apply()
        self.assertEqual([x["request"] for x in rep["applied"]], [r])
        self.assertEqual(self.price(), 150.0)

    def test_head_office_may_approve_straight_from_requested(self):
        r = self.shop.request(rate=150.0)
        self.shop.ho_ok(r)
        self.assertEqual(len(self.run_apply()["applied"]), 1)

    def test_a_store_manager_who_writes_the_head_office_state_himself_is_not_believed(self):
        r = self.shop.request(rate=150.0)
        self.shop.store_ok(r)
        self.shop.ho_ok(r, who="mgr-a@x")                      # the shop accepts a state written straight in; the service checks who
        rep = self.run_apply()
        self.assertIn("not a head-office approver", self.why(rep, r))
        self.assertEqual((self.price(), self.shop.calls), (100.0, []))

    def test_a_store_approver_of_another_store_is_not_believed(self):
        r = self.shop.request(rate=105.0, store=GW)
        self.shop.store_ok(r, who="mgr-b@x")
        self.assertIn("not an approver for store", self.why(self.run_apply(), r))
        self.assertEqual(self.shop.calls, [])

    def test_an_approver_with_no_rule_row_is_not_believed_the_check_fails_closed(self):
        r = self.shop.request()
        self.shop.store_ok(r, who="nobody@x")
        self.assertIn("no approval rule", self.why(self.run_apply(), r))
        r2 = self.shop.request()
        self.shop.store_ok(r2)
        del self.shop.rules["mgr-a@x"]                          # the rule was taken away after the approval
        self.assertIn("no approval rule", self.why(self.run_apply(), r2))
        self.assertEqual(self.shop.calls, [])

    def test_a_rule_row_that_is_not_whole_gives_no_authority(self):
        r = self.shop.request()
        self.shop.rules["mgr-a@x"]["limit_pct"] = 0.0           # a blank limit is stored by the shop as 0, never as nothing
        self.shop.store_ok(r)
        self.assertIn("rule", self.why(self.run_apply(), r))
        self.assertEqual(self.shop.calls, [])
        self.shop.rules["mgr-a@x"]["limit_pct"] = None
        self.assertIn("rule", self.why(self.run_apply(), r))

    def test_a_rule_row_whose_name_is_not_its_person_gives_no_authority(self):
        r = self.shop.request()
        self.shop.rules["mgr-a@x"]["user"] = "someone-else@x"   # an administrator edited the Person field of an existing row
        self.shop.store_ok(r)
        self.assertIn("no approval rule", self.why(self.run_apply(), r))
        self.assertEqual(self.shop.calls, [])

    def test_a_limit_cannot_be_climbed_in_steps_one_approved_request_after_another(self):
        r1, r2 = self.shop.request(rate=110.0), self.shop.request(rate=120.0)      # +10 % and +20 % of the price both managers saw
        self.shop.store_ok(r1)
        self.shop.store_ok(r2)
        rep = self.run_apply()
        self.assertEqual([x["request"] for x in rep["applied"]], [r1])
        self.assertIn("the price changed after the store manager approved", self.why(rep, r2))
        self.assertEqual(self.price(), 110.0)

    def test_a_price_changed_by_anyone_after_a_store_approval_stops_it_but_not_a_head_office_one(self):
        a, b = self.shop.request(rate=105.0), self.shop.request(rate=150.0)
        self.shop.store_ok(a)
        self.shop.ho_ok(b)
        self.shop.prices["IP-1"].update(price_list_rate=101.0, modified=f"{DAY} 11:30:00")      # another role's edit, after both approvals
        rep = self.run_apply()
        self.assertIn("the price changed after the store manager approved", self.why(rep, a))
        self.assertEqual([x["request"] for x in rep["applied"]], [b], "head office named the price it wants: applied whatever the row holds")

    def test_a_store_approval_is_still_finished_after_a_kill_even_though_the_price_row_is_newer(self):
        r = self.shop.request(rate=105.0)
        self.shop.store_ok(r)
        self.shop.prices["IP-1"].update(price_list_rate=105.0, modified=f"{DAY} 12:59:59")     # the killed run wrote the price after the approval
        self.assertEqual(len(self.run_apply()["applied"]), 1)

    def test_a_price_at_or_below_nothing_cannot_be_inside_a_percentage(self):
        r = self.shop.request(rate=5.0)
        self.shop.prices["IP-1"]["price_list_rate"] = -10.0
        self.shop.store_ok(r)
        self.assertIn("above the store manager's limit", self.why(self.run_apply(), r))

    def test_a_price_of_nothing_cannot_be_inside_a_percentage(self):
        r = self.shop.request(rate=5.0)
        self.shop.prices["IP-1"]["price_list_rate"] = 0.0
        self.shop.store_ok(r)
        self.assertIn("above the store manager's limit", self.why(self.run_apply(), r))

    # ── S11's refusals, at each step ─────────────────────────────────────────────────────────────────────────
    def test_raised_and_approved_by_one_person_at_the_store_step_is_not_applied(self):
        r = self.shop.request(owner="both@x")
        self.shop.store_ok(r, who="both@x")
        self.assertIn("approved by the person who raised it", self.why(self.run_apply(), r))
        self.assertEqual(self.shop.calls, [])

    def test_raised_and_approved_by_one_person_at_the_head_office_step_is_not_applied(self):
        r = self.shop.request(owner="hoboth@x", rate=150.0)
        self.shop.store_ok(r)
        self.shop.ho_ok(r, who="hoboth@x")
        self.assertIn("approved by the person who raised it", self.why(self.run_apply(), r))
        self.assertEqual(self.shop.calls, [])

    def test_the_raiser_approving_at_an_earlier_step_still_stops_it_when_head_office_then_approves(self):
        r = self.shop.request(owner="both@x", rate=150.0)
        self.shop.store_ok(r, who="both@x")                    # the first step was the raiser's own; head office did not see that
        self.shop.ho_ok(r)
        self.assertIn("approved by the person who raised it", self.why(self.run_apply(), r))

    def test_a_price_changed_after_it_was_raised_is_not_applied_by_whoever_changed_it(self):
        a, b, c, d, e = (self.shop.request() for _ in range(5))
        self.shop.prices["IP-1"]["modified"] = f"{DAY} 08:00:00"
        self.shop.change(a, "mgr-a@x", new_rate=101.0)         # the approver sets the number, then approves it
        self.shop.store_ok(a)
        self.shop.change(b, "req@x", new_rate=102.0)           # between the approver's look and the click
        self.shop.store_ok(b)
        self.shop.store_ok(c)
        self.shop.change(c, "req@x", new_rate=1.0)             # after the approval
        self.shop.store_ok(d)
        self.shop.change(d, "req@x", item="SKU-2")
        self.shop.store_ok(e)
        self.shop.change(e, "req@x", price_list="Wholesale")    # moved after approval to another list the service also serves
        rep = self.run_apply()
        self.assertEqual(sorted(x["request"] for x in rep["not_applied"] if x["why"] == "changed after it was raised"), [a, b, c, d, e])
        self.assertEqual(self.shop.calls, [])

    def test_the_store_changed_after_it_was_raised_is_not_applied(self):
        r = self.shop.request(store=SAN)
        self.shop.store_ok(r, who="mgr-a@x")
        self.shop.change(r, "mgr-a@x", store=GW)               # moved into the approver's own store
        self.assertIn("changed after it was raised", self.why(self.run_apply(), r))
        self.assertEqual(self.shop.calls, [])

    def test_a_change_to_a_field_that_is_not_money_does_not_stop_it(self):
        r = self.shop.request()
        self.shop.store_ok(r)
        self.shop.change(r, "req@x", reason="typo")
        self.assertEqual(len(self.run_apply()["applied"]), 1)

    def test_no_recorded_approval_is_not_applied(self):
        r = self.shop.request(state=A.STORE_OK)
        self.assertIn("no version records the approval", self.why(self.run_apply(), r))

    def test_ten_or_more_versions_fail_safe_and_nine_are_applied(self):
        r, ok = self.shop.request(), self.shop.request()
        for x, n in ((r, 9), (ok, 8)):
            self.shop.store_ok(x)
            for i in range(n):
                self.shop.change(x, "req@x", reason=f"edit {i}")
        rep = self.run_apply()
        self.assertIn("10 or more recorded changes", self.why(rep, r))
        self.assertEqual([x["request"] for x in rep["applied"]], [ok])

    def test_no_price_row_or_two_rows_is_not_applied(self):
        r = self.shop.request(item="NO-SUCH")
        self.shop.store_ok(r)
        self.assertIn("0 selling price rows", self.why(self.run_apply(), r))
        self.shop.prices["IP-2"] = dict(self.shop.prices["IP-1"], name="IP-2")
        r2 = self.shop.request()
        self.shop.store_ok(r2)
        self.assertIn("2 selling price rows", self.why(self.run_apply(), r2))
        self.assertEqual(self.shop.calls, [])

    # ── acting once, and being killed ────────────────────────────────────────────────────────────────────────
    def test_only_approved_requests_are_touched(self):
        a, b, c = self.shop.request(rate=101), self.shop.request(rate=102, state=A.REJECTED), self.shop.request(rate=103)
        self.shop.store_ok(c)
        self.run_apply()
        self.assertEqual([self.shop.reqs[x]["workflow_state"] for x in (a, b, c)], [A.REQUESTED, A.REJECTED, A.APPLIED])

    def test_a_request_approved_and_then_rejected_is_left_alone(self):
        r = self.shop.request(rate=105.0)
        self.shop.store_ok(r)
        self.shop.change(r, "ho@x", workflow_state=A.REJECTED)          # head office's way out of an approved request
        self.assertEqual(self.run_apply(), {"applied": [], "not_applied": [], "skipped": []})
        self.assertEqual((self.price(), self.shop.calls, self.shop.reqs[r]["workflow_state"]), (100.0, [], A.REJECTED))

    def test_a_crash_between_the_price_and_the_action_is_finished_by_the_rerun_without_writing_the_price_again(self):
        r = self.shop.request(rate=105.0)
        self.shop.store_ok(r)
        self.shop.prices["IP-1"]["price_list_rate"] = 105.0
        rep = self.run_apply()
        self.assertEqual(rep["applied"][0]["wrote_price"], False)
        self.assertEqual([c[0] for c in self.shop.calls], ["ACTION"])

    def test_a_rerun_after_a_crash_still_applies_a_head_office_approved_over_limit_change(self):
        r = self.shop.request(rate=150.0)
        self.shop.ho_ok(r)
        self.shop.prices["IP-1"]["price_list_rate"] = 150.0     # the price was written before the kill
        self.assertEqual(len(self.run_apply()["applied"]), 1)

    def test_the_shop_refusing_one_does_not_stop_the_rest(self):
        a, b = self.shop.request(rate=101.0), self.shop.request(rate=102.0)
        self.shop.store_ok(a)
        self.shop.store_ok(b)
        orig = self.shop.call

        def call(method, path, params=None, body=None):
            if method == "PUT" and body["price_list_rate"] == 101:
                raise F.FeedError("403 Not permitted")
            return orig(method, path, params, body)
        self.shop.call = call
        rep = self.run_apply()
        self.assertIn("the shop said", rep["not_applied"][0]["why"])
        self.assertEqual([x["request"] for x in rep["applied"]], [b])

    def test_a_failed_action_after_the_price_is_written_says_so_and_the_next_run_finishes_it(self):
        r = self.shop.request(rate=105.0)
        self.shop.store_ok(r)
        orig = self.shop.call
        self.shop.call = lambda m, p, params=None, body=None: (_ for _ in ()).throw(F.FeedError("417 not permitted")) if m == "POST" else orig(m, p, params, body)
        rep = self.run_apply()
        self.assertIn("THE PRICE IS ALREADY WRITTEN", rep["not_applied"][0]["why"])
        self.shop.call = orig
        self.assertEqual(self.run_apply()["applied"][0]["wrote_price"], False)

    def test_the_key_needs_no_right_on_the_change_history_records(self):
        calls = []
        orig = self.shop.call
        self.shop.call = lambda m, p, params=None, body=None: (calls.append(p), orig(m, p, params, body))[1]
        r = self.shop.request()
        self.shop.store_ok(r)
        self.run_apply()
        A.export_day(self.shop, DAY, tempfile.mkdtemp())
        self.assertFalse([p for p in calls if "/Version" in p])

    # ── the nightly export ───────────────────────────────────────────────────────────────────────────────────
    def test_the_export_holds_the_days_requests_with_the_store_and_each_step_in_the_same_bytes_twice(self):
        old = self.shop.request(day="2026-10-03")
        a, b = self.shop.request(rate=150.0, store=SAN), self.shop.request()
        self.shop.store_ok(a, "mgr-b@x")
        self.shop.ho_ok(a)
        self.shop.store_ok(b)
        self.run_apply()
        with tempfile.TemporaryDirectory() as d:
            out = A.export_day(self.shop, DAY, d)
            rows = {r["name"]: r for r in csv.DictReader(open(out["path"]))}
            self.assertEqual(sorted(rows), sorted([a, b]))
            self.assertNotIn(old, rows)
            self.assertEqual((rows[a]["store"], rows[a]["store_approved_by"], rows[a]["head_office_approved_by"], rows[a]["applied_by"]), (SAN, "mgr-b@x", "ho@x", "applier@x"))
            self.assertEqual((rows[b]["store_approved_by"], rows[b]["head_office_approved_by"]), ("mgr-a@x", ""))
            self.assertEqual((rows[a]["changed_after_raise"], rows[b]["changed_after_raise"]), ("", ""))
            first = open(out["path"], "rb").read()
            A.export_day(self.shop, DAY, d)
            self.assertEqual(first, open(out["path"], "rb").read())

    def test_the_export_says_when_an_applied_request_was_edited_afterwards_and_shows_text_cells_as_text(self):
        r = self.shop.request(rate=105.0)
        self.shop.store_ok(r)
        self.run_apply()
        self.shop.change(r, "req@x", new_rate=1.0)                # the shop lets a requester edit an Applied request: the file must say so
        self.shop.reqs[r]["reason"] = '=HYPERLINK("http://x","click")'
        with tempfile.TemporaryDirectory() as d:
            row = list(csv.DictReader(open(A.export_day(self.shop, DAY, d)["path"])))[0]
        self.assertEqual(row["changed_after_raise"], "yes")
        self.assertEqual(row["reason"], "'=HYPERLINK(\"http://x\",\"click\")")

    def test_the_export_includes_the_last_instant_of_the_day_and_not_the_next_midnight(self):
        late = self.shop.request()
        self.shop.reqs[late]["creation"] = self.shop.reqs[late]["modified"] = f"{DAY} 23:59:59.500000"
        nxt = self.shop.request(day="2026-10-05")
        self.shop.reqs[nxt]["creation"] = self.shop.reqs[nxt]["modified"] = "2026-10-05 00:00:00"
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual([r["name"] for r in csv.DictReader(open(A.export_day(self.shop, DAY, d)["path"]))], [late])

    # ── a second review's cases ──────────────────────────────────────────────────────────────────────────
    def test_a_reject_landing_while_the_service_applies_puts_the_price_back_and_says_so(self):
        r = self.shop.request(rate=105.0)
        self.shop.store_ok(r)
        orig = self.shop.call

        def reject_first(m, p, params=None, body=None):
            if p.endswith("apply_workflow"):
                self.shop.change(r, "ho@x", workflow_state=A.REJECTED)     # head office's reject lands between the service's read and its action
            return orig(m, p, params, body)
        self.shop.call = reject_first
        rep = self.run_apply()
        self.assertEqual((self.price(), self.shop.reqs[r]["workflow_state"]), (100.0, A.REJECTED))
        self.assertIn("rejected while it was being applied", rep["not_applied"][0]["why"])
        self.assertIn("put back to 100", rep["not_applied"][0]["why"])

    def test_the_export_names_who_rejected(self):
        r = self.shop.request(rate=105.0)
        self.shop.change(r, "mgr-a@x", workflow_state=A.REJECTED)
        with tempfile.TemporaryDirectory() as d:
            row = list(csv.DictReader(open(A.export_day(self.shop, DAY, d)["path"])))[0]
        self.assertEqual(row["rejected_by"], "mgr-a@x")

    # ── the manifest ─────────────────────────────────────────────────────────────────────────────────────────
    def test_the_new_price_shows_the_currency_of_the_price_list_it_changes_not_the_sites_default(self):
        m = json.loads((HERE.parent / "manifest.json").read_text())
        f = {x["fieldname"]: x for x in next(d for d in m["doctypes"] if d["name"] == "PP APS Price Change Request")["fields"]}
        self.assertEqual(f["new_rate"].get("options"), "currency", "a Currency field naming no currency shows the site's default (₹ on a rand price)")
        self.assertEqual((f["currency"]["fieldtype"], f["currency"]["options"], f["currency"].get("fetch_from"), f["currency"].get("read_only")),
                         ("Link", "Currency", "price_list.currency", 1))


if __name__ == "__main__":
    unittest.main()
