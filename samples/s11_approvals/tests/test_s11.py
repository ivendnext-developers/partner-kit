"""Laptop tests of S11's service (approvals.py), no bench: an in-memory shop that speaks the few record-API calls the service makes.

    python3 -m unittest discover -s samples/s11_approvals/tests -p 'test_*.py'
"""
import csv
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2] / "tools" / "feed_client")]
import approvals as A  # noqa: E402
import feed_client as F  # noqa: E402

DAY = "2026-10-04"


class Shop:
    """requests, price rows and the Version log, with the calls the service makes. ``calls`` records every write."""

    def __init__(self):
        self.reqs, self.prices, self.versions, self.calls, self.n = {}, {}, [], [], 0
        self.service_may_reject = True
        self.prices["IP-1"] = {"name": "IP-1", "item_code": "SKU-1", "price_list": "Retail", "selling": 1, "price_list_rate": 100.0}

    def request(self, item="SKU-1", rate=120.0, state=A.REQUESTED, owner="req@x", day=DAY):
        self.n += 1
        name = f"PP-APR-{self.n:05d}"
        self.reqs[name] = {"name": name, "item": item, "price_list": "Retail", "new_rate": rate, "reason": "r", "workflow_state": state,
                           "owner": owner, "creation": f"{day} 09:00:0{self.n % 10}", "modified": f"{day} 09:00:0{self.n % 10}"}
        return name

    def change(self, name, who, **fields):
        ch = []
        for k, v in fields.items():
            ch.append([k, self.reqs[name].get(k), v])
            self.reqs[name][k] = v
        self.versions.append({"docname": name, "owner": who, "creation": f"{DAY} 10:{len(self.versions) // 60:02d}:{len(self.versions) % 60:02d}", "data": json.dumps({"changed": ch})})

    def approve(self, name, who="boss@x"):
        self.change(name, who, workflow_state=A.APPROVED)

    def call(self, method, path, params=None, body=None):
        parts = [urllib.parse.unquote(p) for p in path.split("/")[3:]]
        params = params or {}
        if method == "GET" and parts == ["ivendnext_mpos.api.v1.get_docinfo"]:
            vs = [v for v in self.versions if v["docname"] == params["name"]]      # the shop's own: newest first, at most 10
            vs = sorted(vs, key=lambda v: v["creation"], reverse=True)[:10]
            return {"docinfo": {"versions": [{"name": f"V{i}", **v} for i, v in enumerate(vs)]}}
        if method == "GET" and parts[0] == A.DT and len(parts) == 2:
            return {"data": dict(self.reqs[parts[1]])}
        if method == "GET":
            flt = json.loads(params.get("filters", "[]"))
            rows = {A.DT: list(self.reqs.values()), "Item Price": list(self.prices.values()), "Version": self.versions}[parts[0]]
            for f, op, v in flt:
                if f != "ref_doctype":
                    rows = [r for r in rows if _ok(r.get(f), op, v)]
            return {"data": [dict(r) for r in sorted(rows, key=lambda r: (r.get("creation", ""), r.get("name", "")))]}
        if method == "PUT":
            self.calls.append(("PUT", parts, body))
            rows = self.reqs if parts[0] == A.DT else self.prices
            rows[parts[1]].update(body)
            return {"data": rows[parts[1]]}
        if method == "POST" and parts == ["method", "ivendnext_mpos.api.v1.apply_workflow"] or path.endswith("apply_workflow"):
            self.calls.append(("ACTION", body["action"], json.loads(body["doc"])["name"]))
            name = json.loads(body["doc"])["name"]
            if body["action"] == A.ACTION_REJECT:      # the shop's own: the saved record is read again (load_from_db)
                if not self.service_may_reject:         # the workflow checks the caller's role on the transition
                    raise F.FeedError("417 Not a valid Workflow Action")
                if self.reqs[name]["workflow_state"] not in (A.REQUESTED, A.APPROVED):
                    raise F.FeedError("417 not a valid action in this state")
                self.change(name, "approver@x", workflow_state=A.REJECTED)
                return {"message": {}}
            if self.reqs[name]["workflow_state"] != A.APPROVED:
                raise F.FeedError("417 not a valid action in this state")
            self.change(name, "applier@x", workflow_state=A.APPLIED)
            return {"message": {}}
        raise AssertionError((method, path))


def _ok(have, op, want):
    return {"=": have == want, ">=": str(have) >= str(want), "<=": str(have) <= str(want), "<": str(have) < str(want)}[op]


class T(unittest.TestCase):
    def setUp(self):
        self.shop = Shop()

    def writes(self):
        return [c for c in self.shop.calls]

    def test_an_approved_request_is_applied_once_and_a_second_run_changes_nothing(self):
        r = self.shop.request()
        self.shop.approve(r)
        rep = A.apply_all(self.shop)
        self.assertEqual([x["request"] for x in rep["applied"]], [r])
        self.assertEqual(self.shop.prices["IP-1"]["price_list_rate"], 120.0)
        self.assertEqual(self.shop.reqs[r]["workflow_state"], A.APPLIED)
        n = len(self.writes())
        rep2 = A.apply_all(self.shop)
        self.assertEqual(rep2, {"applied": [], "not_applied": [], "skipped": []})
        self.assertEqual(len(self.writes()), n, "the second run wrote nothing and took no action")

    def test_only_approved_requests_are_touched(self):
        a, b, c = self.shop.request(rate=111), self.shop.request(rate=222), self.shop.request(rate=333, state=A.REJECTED)
        self.shop.approve(b)
        A.apply_all(self.shop)
        self.assertEqual(self.shop.prices["IP-1"]["price_list_rate"], 222.0)
        self.assertEqual([self.shop.reqs[x]["workflow_state"] for x in (a, b, c)], [A.REQUESTED, A.APPLIED, A.REJECTED])

    def test_a_crash_between_the_price_and_the_action_is_finished_by_the_rerun_without_writing_the_price_again(self):
        r = self.shop.request()
        self.shop.approve(r)
        self.shop.prices["IP-1"]["price_list_rate"] = 120.0          # the price was written before the crash …
        rep = A.apply_all(self.shop)                                  # … the rerun finds it done and only takes the action
        self.assertEqual(rep["applied"][0]["wrote_price"], False)
        self.assertEqual([c[0] for c in self.shop.calls], ["ACTION"])
        self.assertEqual(self.shop.reqs[r]["workflow_state"], A.APPLIED)

    def test_a_request_changed_after_it_was_approved_is_not_applied(self):
        r = self.shop.request()
        self.shop.approve(r)
        self.shop.change(r, "req@x", new_rate=1.0)
        rep = A.apply_all(self.shop)
        self.assertEqual(rep["not_applied"][0]["why"], "changed after it was raised")
        self.assertIn("new_rate", rep["not_applied"][0]["changes"][0])
        self.assertEqual(self.shop.prices["IP-1"]["price_list_rate"], 100.0)
        self.assertFalse(self.shop.calls)

    def test_a_price_changed_before_approval_by_the_approver_or_the_requester_is_not_applied(self):
        a, b = self.shop.request(), self.shop.request()
        self.shop.change(a, "boss@x", new_rate=1.0)                  # the approver sets the number, then approves it
        self.shop.approve(a)
        self.shop.change(b, "req@x", new_rate=2.0)                   # changed between the approver's look and the click
        self.shop.approve(b)
        rep = A.apply_all(self.shop)
        self.assertEqual(sorted(x["request"] for x in rep["not_applied"] if x["why"] == "changed after it was raised"), [a, b])
        self.assertFalse(self.shop.calls)

    def test_approved_by_the_person_who_raised_it_is_not_applied(self):
        r = self.shop.request(owner="both@x")
        self.shop.approve(r, who="both@x")                           # a state written straight in skips the shop's self-approval check
        rep = A.apply_all(self.shop)
        self.assertEqual(rep["not_applied"][0]["why"], "approved by the person who raised it")
        self.assertFalse(self.shop.calls)

    def test_a_change_to_a_field_that_is_not_money_does_not_stop_it(self):
        r = self.shop.request()
        self.shop.approve(r)
        self.shop.change(r, "req@x", reason="typo")
        self.assertEqual(len(A.apply_all(self.shop)["applied"]), 1)

    def test_no_recorded_approval_is_not_applied(self):
        r = self.shop.request(state=A.APPROVED)                      # in Approved, but no version says how it got there
        rep = A.apply_all(self.shop)
        self.assertIn("no version records the approval", rep["not_applied"][0]["why"])
        self.assertFalse(self.shop.calls)

    def test_no_price_row_or_two_rows_is_not_applied(self):
        r = self.shop.request(item="NO-SUCH")
        self.shop.approve(r)
        self.assertIn("0 selling price rows", A.apply_all(self.shop)["not_applied"][0]["why"])
        self.shop.prices["IP-2"] = dict(self.shop.prices["IP-1"], name="IP-2")
        r2 = self.shop.request()
        self.shop.approve(r2)
        self.assertIn("2 selling price rows", [x for x in A.apply_all(self.shop)["not_applied"] if x["request"] == r2][0]["why"])
        self.assertFalse(self.shop.calls)

    def test_the_shop_refusing_one_does_not_stop_the_rest(self):
        a, b = self.shop.request(rate=111), self.shop.request(rate=222)
        self.shop.approve(a)
        self.shop.approve(b)
        orig = self.shop.call

        def call(method, path, params=None, body=None):
            if method == "PUT" and body["price_list_rate"] == 111:
                raise F.FeedError("403 Not permitted")
            return orig(method, path, params, body)
        self.shop.call = call
        rep = A.apply_all(self.shop)
        self.assertIn("the shop said", rep["not_applied"][0]["why"])
        self.assertEqual([x["request"] for x in rep["applied"]], [b], "the next request was still applied")
        self.assertEqual(self.shop.prices["IP-1"]["price_list_rate"], 222.0)

    def test_a_failed_action_after_the_price_is_written_says_the_price_is_live_and_the_next_run_finishes_it(self):
        r = self.shop.request()
        self.shop.approve(r)
        orig = self.shop.call

        def call(method, path, params=None, body=None):
            if method == "POST":
                raise F.FeedError("417 not permitted")
            return orig(method, path, params, body)
        self.shop.call = call
        rep = A.apply_all(self.shop)
        self.assertEqual(rep["applied"], [])
        self.assertIn("THE PRICE IS ALREADY WRITTEN", rep["not_applied"][0]["why"])
        self.assertTrue(rep["not_applied"][0]["wrote_price"])
        self.assertEqual(self.shop.prices["IP-1"]["price_list_rate"], 120.0)
        self.shop.call = orig
        rep = A.apply_all(self.shop)
        self.assertEqual(rep["applied"][0]["wrote_price"], False, "the rerun only takes the action")

    def test_ten_or_more_versions_fail_safe_not_applied_and_nine_are_applied(self):
        r, ok = self.shop.request(), self.shop.request()
        for x, n in ((r, 9), (ok, 8)):
            self.shop.approve(x)
            for i in range(n):
                self.shop.change(x, "req@x", reason=f"edit {i}")  # not money — the approval plus 9 is ten: the shop may be hiding more
        rep = A.apply_all(self.shop)
        self.assertIn("10 or more recorded changes", rep["not_applied"][0]["why"])
        self.assertEqual([x["request"] for x in rep["applied"]], [ok], "nine versions are the whole history: applied")

    def test_the_export_does_not_call_a_cut_history_unchanged(self):
        r, ok = self.shop.request(), self.shop.request()
        for x, n in ((r, 9), (ok, 3)):
            self.shop.approve(x)
            for i in range(n):
                self.shop.change(x, "req@x", reason=f"edit {i}")            # not money: nothing in the visible history is a money change
        with tempfile.TemporaryDirectory() as d:
            rows = {x["name"]: x for x in csv.DictReader(open(A.export_day(self.shop, DAY, d)["path"]))}
        self.assertEqual((rows[r]["changed_after_raise"], rows[ok]["changed_after_raise"]), ("unknown", ""))

    def test_the_key_needs_no_right_on_the_change_history_records(self):
        calls = []
        orig = self.shop.call
        self.shop.call = lambda m, p, params=None, body=None: (calls.append(p), orig(m, p, params, body))[1]
        r = self.shop.request()
        self.shop.approve(r)
        A.apply_all(self.shop)
        A.export_day(self.shop, DAY, tempfile.mkdtemp())
        self.assertFalse([p for p in calls if "/Version" in p or "/Version%20" in p], "the history is read through the request, never the shop's history records")

    def test_the_export_says_when_an_applied_request_was_edited_afterwards_and_shows_text_cells_as_text(self):
        r = self.shop.request(rate=105.0)
        self.shop.approve(r)
        A.apply_all(self.shop)
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
            names = [r["name"] for r in csv.DictReader(open(A.export_day(self.shop, DAY, d)["path"]))]
        self.assertEqual(names, [late])

    def test_the_export_holds_exactly_the_days_requests_with_who_approved_and_applied(self):
        old = self.shop.request(day="2026-10-03")
        mine = [self.shop.request(), self.shop.request()]
        self.shop.approve(mine[0], "boss@x")
        A.apply_all(self.shop)
        with tempfile.TemporaryDirectory() as d:
            out = A.export_day(self.shop, DAY, d)
            rows = list(csv.DictReader(open(out["path"])))
            self.assertEqual([r["name"] for r in rows], sorted(mine))
            self.assertNotIn(old, [r["name"] for r in rows])
            first = [r for r in rows if r["name"] == mine[0]][0]
            self.assertEqual((first["approved_by"], first["applied_by"], first["workflow_state"]), ("boss@x", "applier@x", A.APPLIED))
            self.assertEqual([r["changed_after_raise"] for r in rows], ["", ""], "nothing was edited after it was raised")
            a = open(out["path"], "rb").read()
            A.export_day(self.shop, DAY, d)
            self.assertEqual(a, open(out["path"], "rb").read(), "the same bytes every time")
            self.assertEqual(out["requests"], 2)


class Reject(unittest.TestCase):
    """A reason asked before a request is rejected (recipes/desk_action.md): the press handler's core."""

    def setUp(self):
        self.shop = Shop()
        sys.path.insert(0, str(HERE.parents[2] / "tools" / "contracts"))
        from check import errors
        self.errors = errors

    def test_the_reason_and_who_pressed_are_kept_then_the_request_is_rejected(self):
        r = self.shop.request()
        ans = A.reject(self.shop, r, "  The supplier price is wrong  ", "boss@x")
        self.assertEqual(self.shop.reqs[r]["workflow_state"], A.REJECTED)
        self.assertEqual((self.shop.reqs[r]["rejection_reason"], self.shop.reqs[r]["rejected_by"]), ("The supplier price is wrong", "boss@x"))
        kinds = [c[0] for c in self.shop.calls]
        self.assertEqual(kinds, ["PUT", "ACTION"], "the reason is written before the workflow moves")
        self.assertEqual(self.errors("desk_action", "answer", ans), [])

    def test_a_short_reason_writes_nothing(self):
        r = self.shop.request()
        ans = A.reject(self.shop, r, "no", "boss@x")
        self.assertEqual(ans["message"]["level"], "warning")
        self.assertEqual(self.shop.calls, [])
        self.assertEqual(self.errors("desk_action", "answer", ans), [])

    def test_a_second_press_answers_and_rejects_nothing_again(self):
        r = self.shop.request()
        A.reject(self.shop, r, "The supplier price is wrong", "boss@x")
        n = len(self.shop.calls)
        ans = A.reject(self.shop, r, "The supplier price is wrong", "boss@x")
        self.assertEqual((ans["message"]["title"], len(self.shop.calls)), ("Already rejected", n))

    def test_a_refused_transition_puts_the_fields_back(self):
        r = self.shop.request()
        self.shop.service_may_reject = False
        ans = A.reject(self.shop, r, "The supplier price is wrong", "boss@x")
        self.assertEqual(ans["message"]["title"], "Not rejected")
        self.assertEqual((self.shop.reqs[r]["workflow_state"], self.shop.reqs[r].get("rejection_reason"), self.shop.reqs[r].get("rejected_by")),
                         (A.REQUESTED, None, None))
        self.assertEqual(self.errors("desk_action", "answer", ans), [])

    def test_a_reject_that_went_through_behind_a_timeout_keeps_its_reason(self):
        r = self.shop.request()
        real = self.shop.call

        def lost_answer(method, path, params=None, body=None):
            out = real(method, path, params, body)
            if path.endswith("apply_workflow"):
                raise F.FeedError("unreachable: timed out")      # the shop rejected it; the answer never came back
            return out
        self.shop.call = lost_answer
        ans = A.reject(self.shop, r, "The supplier price is wrong", "boss@x")
        self.assertEqual((self.shop.reqs[r]["workflow_state"], self.shop.reqs[r]["rejection_reason"]), (A.REJECTED, "The supplier price is wrong"))
        self.assertEqual(ans["message"]["title"], "Rejected")

    def test_an_applied_request_cannot_be_rejected(self):
        r = self.shop.request(state=A.APPLIED)
        ans = A.reject(self.shop, r, "The supplier price is wrong", "boss@x")
        self.assertEqual((ans["message"]["title"], self.shop.calls), ("Cannot be rejected", []))


if __name__ == "__main__":
    unittest.main()
