"""S44's laptop tests: the real service, a stand-in for the shop's record API, presses signed exactly as the shop signs
them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s44_lucky_draw/tests -p 'test_*.py'

On our test bench the real Desk buttons were pressed on a real campaign over real till sales; these prove the service's
own duties fast, and are what the mutation canary turns RED."""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import draw  # noqa: E402

SECRETS = {"count": "s44-count-secret", "draw": "s44-draw-secret"}
AFTER = datetime.datetime(2026, 11, 1, 6, 0, tzinfo=datetime.timezone.utc).timestamp()    # the day after the last
LAST_EVENING = datetime.datetime(2026, 10, 31, 18, 0, tzinfo=datetime.timezone.utc).timestamp()  # 22:00 in Dubai
NAME = "Summer draw 2026"


def campaign(**k):
    c = {"name": NAME, "title": NAME, "company": "PP Co", "from_date": "2026-10-01", "to_date": "2026-10-31",
         "hours_from_utc": 4, "spend_per_entry": 200, "most_entries_per_sale": 0, "winners": 2, "reserves": 1,
         "status": "Open", "tills": [], "customer_groups": [], "results": [], "modified": "2026-10-20 10:00:00.000001"}
    c.update(k)
    return c


def sale(name, customer, total, day="2026-10-02", till="POS-A", group="Members", time_="10:00:00", company="PP Co"):
    return {"name": name, "customer": customer, "customer_group": group, "base_grand_total": total,
            "posting_date": day, "posting_time": time_, "pos_profile": till, "company": company, "docstatus": 1,
            "is_return": 0}


def sales():
    return [sale("S1", "C1", 650, group="Gold"),                       # 3 entries
            sale("S2", "C2", 199.99),                                   # under one entry: none
            sale("S3", "WALK-IN", 1000),                                # a till's walk-in customer: never an entry
            sale("S4", "C3", 400, day="2026-10-03"),                    # 400 less a return of 250: none
            sale("S5", "C1", 210, day="2026-10-05", group="Gold"),      # 1
            sale("S6", "C4", 2000, day="2026-11-01"),                   # after the last day
            sale("S7", "C5", 800, day="2026-10-07", till="POS-B", group="Commercial"),   # 800 less 200: 3
            sale("S8", "C6", 400, day="2026-10-07", time_="09:00:00", group="Staff"),     # 2
            sale("S9", None, 900),                                      # no customer
            sale("S10", "C7", 900, company="Other Co"),                 # another company
            dict(sale("S11", "C8", 900), docstatus=2)]                  # cancelled


def returns():
    return [{"name": "R1", "return_against": "S4", "base_grand_total": -250, "posting_date": "2026-10-04",
             "company": "PP Co", "docstatus": 1, "is_return": 1},
            {"name": "R2", "return_against": "S7", "base_grand_total": -200, "posting_date": "2026-11-02",
             "company": "PP Co", "docstatus": 1, "is_return": 1},          # after the last day: still netted
            {"name": "R3", "return_against": "S1", "base_grand_total": -600, "posting_date": "2026-10-03",
             "company": "PP Co", "docstatus": 0, "is_return": 1}]          # a draft return: not netted


GROUPS = [{"name": "All Customer Groups", "lft": 1, "rgt": 10}, {"name": "Members", "lft": 2, "rgt": 5},
          {"name": "Gold", "lft": 3, "rgt": 4}, {"name": "Staff", "lft": 6, "rgt": 7},
          {"name": "Commercial", "lft": 8, "rgt": 9}]


def _match(row, filters):
    for f, op, v in filters:
        x = row.get(f)
        if op == "=" and x != v or op == "in" and x not in v or op == ">=" and not (x and x >= v) \
                or op == "between" and not (x and v[0] <= x <= v[1]):
            return False
    return True


class FakeTenant:
    """The shop's record API: one campaign (updated with the shop's ``modified`` check), POS Invoices, POS Profiles and
    the customer group tree."""

    def __init__(self, c=None, refuse=None, edit_before_update=0):
        self.c = campaign() if c is None else c
        self.pos = sales() + returns()
        self.profiles = [{"name": "POS-A", "customer": "WALK-IN"}, {"name": "POS-B", "customer": "WALK-IN"},
                         {"name": "POS-C", "customer": None}]
        self.refuse, self.edit_before_update = refuse, edit_before_update
        self.reads, self.writes = [], []

    def _refused(self):
        if self.refuse:
            raise app.TenantError("GET -> HTTP %d" % self.refuse, self.refuse)

    def doc(self, doctype, name):
        self._refused()
        if doctype != draw.CAMPAIGN or not self.c or name != self.c["name"]:
            raise app.TenantError("GET -> HTTP 404", 404)
        return copy.deepcopy(self.c)

    def rows(self, doctype, fields, filters, timeout=None):
        self._refused()
        self.reads.append((doctype, list(fields), copy.deepcopy(filters)))
        if doctype == "POS Invoice":
            return [{k: r.get(k) for k in fields} for r in self.pos if _match(r, filters)]
        if doctype == "POS Profile":
            return copy.deepcopy(self.profiles)
        if doctype == "Customer Group":
            return copy.deepcopy(GROUPS)
        raise app.TenantError("GET -> HTTP 403", 403)

    def update(self, doctype, name, body):
        self._refused()
        if self.edit_before_update:
            self.edit_before_update -= 1
            self.c["modified"] = "2026-10-31 23:59:59.000001"
        if body.get("modified") != self.c["modified"]:
            raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
        self.c.update({k: copy.deepcopy(v) for k, v in body.items() if k != "modified"})
        self.c["modified"] = "2026-11-01 06:00:00.000001"
        self.writes.append(copy.deepcopy(body))
        return copy.deepcopy(self.c)


class Picks:
    """``randbelow`` that answers the numbers given, in order (each an index into the pool's entries)."""

    def __init__(self, *picks):
        self.picks, self.asked = list(picks), []

    def __call__(self, n):
        self.asked.append(n)
        return self.picks.pop(0) % n


def body(name=NAME, doctype=None, records=None):
    rec = [{"doctype": doctype or draw.CAMPAIGN, "name": name, "fields": {"name": name}}]
    return json.dumps({"context": {"action": "a1", "idempotency_key": "k1", "inputs": {}, "label": "Draw winners",
                                   "lang": "en", "records": rec if records is None else records,
                                   "user": "marketing@shop.example", "v": 1}, "point": "desk_action/1"},
                      sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None):
    ts = str(int(ts if ts is not None else time.time()))      # the press is signed now; the service's day is its own clock
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "X-iVendNext-Request-Id": "r1"}


class ServiceTest(unittest.TestCase):
    def service(self, tenant, now=AFTER, picks=None):
        conf = {"PP_COUNT_SECRET": SECRETS["count"], "PP_DRAW_SECRET": SECRETS["draw"]}
        return app.Service(conf, tenant, now=now, randbelow=picks or Picks(0, 0, 0, 0, 0))

    def press(self, svc, sub, raw=None, now=AFTER):
        raw = raw or body()
        code, out = svc.handle("POST", f"/press/{sub}", signed(raw, SECRETS[sub]), raw)
        self.assertEqual(code, 200, out)
        return out

    def test_s1_count_writes_the_counts_and_the_fingerprint_on_the_campaign(self):
        t = FakeTenant()
        out = self.press(self.service(t), "count")
        self.assertEqual(out["message"]["body"], "4 sales by 3 customers: 9 entries so far.")
        self.assertTrue(out["refresh"])
        w, = t.writes
        self.assertEqual((w["sales_counted"], w["customers_counted"], w["entries_counted"]), (4, 3, 9))
        self.assertEqual(w["count_fingerprint"], draw.fingerprint([("S1", "C1", 3), ("S5", "C1", 1), ("S8", "C6", 2),
                                                                   ("S7", "C5", 3)]))
        self.assertEqual(w["counted_on"], "2026-11-01 06:00 UTC")
        self.assertEqual(w["modified"], "2026-10-20 10:00:00.000001")      # the campaign as read: never over an edit
        self.assertNotIn("status", w)
        self.assertNotIn("results", w)

    def test_s2_a_sale_on_a_tills_walk_in_customer_is_never_an_entry(self):
        t = FakeTenant()
        t.profiles = [{"name": "POS-A", "customer": None}]       # no till names WALK-IN: its 1000 counts
        self.press(self.service(t), "count")
        self.assertEqual(t.writes[0]["entries_counted"], 14)

    def test_s3_a_return_against_a_sale_takes_its_entries_off(self):
        t = FakeTenant()
        t.pos = [r for r in t.pos if r["name"] != "R2"]           # without S7's return: 800 is 4 entries
        self.press(self.service(t), "count")
        self.assertEqual(t.writes[0]["entries_counted"], 10)

    def test_s4_most_entries_per_sale_caps_a_sale(self):
        t = FakeTenant(campaign(most_entries_per_sale=2))
        self.press(self.service(t), "count")
        self.assertEqual(t.writes[0]["entries_counted"], 7)       # 2 + 1 + 2 + 2

    def test_s5_only_the_campaigns_tills_count(self):
        t = FakeTenant(campaign(tills=[{"pos_profile": "POS-B"}]))
        self.press(self.service(t), "count")
        self.assertEqual((t.writes[0]["sales_counted"], t.writes[0]["entries_counted"]), (1, 3))
        self.assertIn(["pos_profile", "in", ["POS-B"]], t.reads[0][2])

    def test_s6_a_customer_group_takes_its_groups_below_it(self):
        t = FakeTenant(campaign(customer_groups=[{"customer_group": "Members"}]))
        self.press(self.service(t), "count")
        self.assertEqual((t.writes[0]["customers_counted"], t.writes[0]["entries_counted"]), (1, 4))   # Gold's C1

    def test_s7_a_draw_before_the_last_day_ends_at_the_shop_is_refused_and_writes_nothing(self):
        t = FakeTenant()
        out = self.press(self.service(t, now=LAST_EVENING), "draw", now=LAST_EVENING)
        self.assertEqual((out["message"]["level"], out["message"]["body"]), ("warning", app.too_soon(datetime.date(2026, 10, 31))))
        self.assertEqual((t.writes, t.reads), ([], []))
        t2 = FakeTenant(campaign(hours_from_utc=7))              # 01:00 the next day at the shop: the draw runs
        self.assertIn("Drew 2 winners", self.press(self.service(t2, now=LAST_EVENING), "draw", now=LAST_EVENING)["message"]["body"])

    def test_s8_the_draw_writes_winners_then_reserves_each_customer_once_and_its_record(self):
        t = FakeTenant()
        # the entries in order: S1 C1 1-3, S5 C1 4, S8 C6 5-6, S7 C5 7-9. Pick the pool's 4th (S5: C1), then with C1's
        # entries gone the pool is S8, S7: its 2nd (S8's second entry, 6: C6), then the 1st left (S7's first, 7: C5)
        out = self.press(self.service(t, picks=Picks(3, 1, 0)), "draw")
        self.assertEqual(out["message"]["body"], "Drew 2 winners and 1 reserve from 9 entries. The results are on the campaign.")
        w, = t.writes
        self.assertEqual([(r["rank"], r["kind"], r["customer"], r["entries"], r["entry_no"], r["sale"]) for r in w["results"]],
                         [(1, "Winner", "C1", 4, 4, "S5"), (2, "Winner", "C6", 2, 6, "S8"), (3, "Reserve", "C5", 3, 7, "S7")])
        self.assertEqual((w["status"], w["drawn_by"], w["drawn_on"], w["draw_entries"], w["drawn_numbers"]),
                         ("Drawn", "marketing@shop.example", "2026-11-01 06:00 UTC", 9, "4, 6, 7"))
        self.assertEqual(w["draw_fingerprint"], w["count_fingerprint"])

    def test_s9_a_second_draw_finds_drawn_and_writes_nothing(self):
        t = FakeTenant()
        svc = self.service(t)
        self.press(svc, "draw")
        out = self.press(svc, "draw")
        self.assertEqual(out["message"]["body"],
                         "Already drawn on 2026-11-01 06:00 UTC by marketing@shop.example. A draw is never repeated.")
        self.assertEqual(len(t.writes), 1)

    def test_s10_an_edit_saved_while_the_press_read_is_never_written_over(self):
        t = FakeTenant(edit_before_update=1)
        out = self.press(self.service(t), "draw")
        self.assertEqual((out["message"]["level"], out["message"]["body"]), ("warning", app.CHANGED))
        self.assertEqual((t.writes, t.c["status"]), ([], "Open"))

    def test_s11_fewer_customers_than_places_draws_every_one_and_says_so(self):
        t = FakeTenant(campaign(winners=5, reserves=2))
        out = self.press(self.service(t), "draw")
        self.assertEqual(out["message"]["body"], "Drew 3 winners from 9 entries. Only 3 customers have entries, so every "
                                                 "one was drawn. The results are on the campaign.")
        self.assertEqual(sorted(r["customer"] for r in t.writes[0]["results"]), ["C1", "C5", "C6"])

    def test_s12_a_count_after_the_draw_leaves_the_draws_record_as_it_was(self):
        t = FakeTenant()
        svc = self.service(t)
        self.press(svc, "draw")
        drawn = copy.deepcopy(t.c)
        t.pos.append(sale("S12", "C9", 2000, day="2026-10-30"))   # a late till's sale arrives
        self.press(svc, "count")
        self.assertEqual(t.writes[1]["entries_counted"], 19)
        for k in ("status", "drawn_on", "drawn_by", "draw_entries", "draw_fingerprint", "drawn_numbers", "results"):
            self.assertEqual(t.c[k], drawn[k], k)
        self.assertNotEqual(t.c["count_fingerprint"], t.c["draw_fingerprint"])

    def test_s13_a_rule_that_cannot_be_read_is_said_in_words_and_reads_no_sales(self):
        for c, words in ((campaign(spend_per_entry=0), "Fill the spend for one entry"),
                         (campaign(to_date="2026-09-30"), "The campaign's last day is before its first"),
                         (campaign(from_date=None), "Fill the campaign's company"),
                         (campaign(winners=0), "Winners is a whole number from 1 to 50"),
                         (campaign(winners=51), "Winners is a whole number from 1 to 50"),
                         (campaign(reserves=21), "Reserves is a whole number from 0 to 20"),
                         (campaign(most_entries_per_sale=-1), "Most entries per sale")):
            t = FakeTenant(c)
            out = self.press(self.service(t), "count")
            self.assertEqual(out["message"]["level"], "warning")
            self.assertTrue(out["message"]["body"].startswith(words), out["message"]["body"])
            self.assertEqual((t.reads, t.writes), ([], []))

    def test_s14_the_apps_user_refused_by_the_shop_is_said_in_words(self):
        out = self.press(self.service(FakeTenant(refuse=403)), "count")
        self.assertEqual(out["message"]["body"], app.REFUSED)

    def test_s15_a_campaign_not_found_is_said_in_words(self):
        out = self.press(self.service(FakeTenant()), "count", body("Another campaign"))
        self.assertEqual(out["message"]["body"], app.GONE)

    def test_s16_a_draw_with_no_entries_writes_nothing(self):
        t = FakeTenant(campaign(spend_per_entry=5000))
        out = self.press(self.service(t), "draw")
        self.assertTrue(out["message"]["body"].startswith("No entries yet"))
        self.assertEqual((t.writes, t.c["status"]), ([], "Open"))

    def test_s17_a_press_on_anything_but_one_campaign_is_refused_before_any_read(self):
        t = FakeTenant()
        svc = self.service(t)
        for raw in (body(doctype="Customer"), body(records=[]),
                    body(records=[{"doctype": draw.CAMPAIGN, "name": "A"}, {"doctype": draw.CAMPAIGN, "name": "B"}])):
            code, out = svc.handle("POST", "/press/count", signed(raw, SECRETS["count"]), raw)
            self.assertEqual(code, 400, out)
        self.assertEqual(t.reads, [])

    def test_s18_each_button_takes_only_its_own_secret(self):
        t = FakeTenant()
        svc = self.service(t)
        raw = body()
        for path, secret in (("/press/draw", SECRETS["count"]), ("/press/count", SECRETS["draw"]),
                             ("/press/count", "")):
            self.assertEqual(svc.handle("POST", path, signed(raw, secret), raw)[0], 401)
        stale = signed(raw, SECRETS["count"], time.time() - draw.SKEW_S - 1)
        self.assertEqual(svc.handle("POST", "/press/count", stale, raw)[0], 401)
        self.assertEqual((t.reads, t.writes), ([], []))

    def test_s19_the_sales_read_asks_only_for_the_campaigns_submitted_till_sales(self):
        t = FakeTenant()
        self.press(self.service(t), "count")
        (dt, fields, filters), (_, rfields, rfilters) = t.reads[0], t.reads[1]
        self.assertEqual((dt, fields), ("POS Invoice", app.SALE_FIELDS))
        self.assertEqual(filters, [["docstatus", "=", 1], ["is_return", "=", 0], ["company", "=", "PP Co"],
                                   ["posting_date", "between", ["2026-10-01", "2026-10-31"]]])
        self.assertEqual(rfields, ["return_against", "base_grand_total"])
        self.assertIn(["docstatus", "=", 1], rfilters)

    def test_s20_a_shop_that_does_not_answer_is_the_shops_timeout_sentence(self):
        class Down(FakeTenant):
            def rows(self, *a, **k):
                raise app.TenantError("GET POS Invoice -> TimeoutError")

        code, out = self.service(Down()).handle("POST", "/press/count", signed(body(), SECRETS["count"]), body())
        self.assertEqual(code, 502)

    def test_health_and_an_unknown_route(self):
        svc = self.service(FakeTenant())
        self.assertEqual(svc.handle("GET", "/health", {}, b""), (200, {"ok": 1}))
        self.assertEqual(svc.handle("POST", "/press/else", {}, b"{}")[0], 404)
        self.assertEqual(svc.handle("POST", "/press/count", {}, b"x" * (draw.BODY_MAX + 1))[0], 413)


if __name__ == "__main__":
    unittest.main()
