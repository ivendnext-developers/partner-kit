"""S49's laptop tests: the real service, a stand-in for the retailer's record API, presses signed exactly as the
retailer signs them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON), and the customer's page
calls with the link the service wrote.

    python3 -m unittest discover -s samples/s49_post_sale_feedback/tests -p 'test_*.py'

On our test bench the real Desk button was pressed on a real rule over real till sales and the page answered; these
prove the service's own duties fast, and are what the mutation canary turns RED."""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import feedback as fb  # noqa: E402
import shops  # noqa: E402

SECRET = "s49-send-secret"
URL, SITE, PAGE = "https://shop.example", "shop.example", "https://feedback.example"
NOW = datetime.datetime(2026, 10, 24, 18, 0, tzinfo=datetime.timezone.utc).timestamp()
CONF = {"IVN_SHOP_URL": URL, "IVN_SHOP_KEY": "k:s", "IVN_SEND_SECRET": SECRET, "PSF_PAGE_URL": PAGE}


def sale(name, customer, day="2026-10-24", till="POS-A", mobile="+971 50 123 4567", email="", creation=None, **k):
    s = {"name": name, "customer": customer, "customer_name": f"Name of {customer}", "contact_mobile": mobile,
         "contact_email": email, "pos_profile": till, "posting_date": day, "docstatus": 1, "is_return": 0,
         "creation": creation or f"{day} 10:00:{int(name[1:]):02d}.000000"}
    s.update(k)
    return s


def sales():
    return [sale("S1", "C1"),
            sale("S2", "C2", mobile="", email="c2@example.com"),
            sale("S3", "WALK-IN"),                                       # the till's walk-in customer: never asked
            sale("S4", "C4", mobile="", email=""),                       # no contact on the sale or the customer
            sale("S5", "C5", mobile="", email=""),                       # no contact on the sale: the customer's own
            sale("S6", "C6", till="POS-B"),                              # another till
            sale("S7", "C7", day="2026-10-20"),                          # before the rule's days
            sale("S8", "C8", is_return=1),                               # a return
            sale("S9", "C9", docstatus=2),                               # cancelled
            sale("S10", "C1", creation="2026-10-24 10:00:59.000000"),    # C1 again: the later sale is asked
            sale("S11", "STOP"),                                         # asked us to stop before
            sale("S12", None)]                                           # no customer


def rule(**k):
    r = {"name": "Dubai", "enabled": 1, "shown_name": "Al Waha Stores", "question": "How was your visit?",
         "answer_good": "Great", "answer_ok": "Fine", "answer_bad": "Poor", "look_back_days": 1, "open_days": 7,
         "asked_up_to": "", "profiles": ["POS-A"], "modified": "2026-10-20 10:00:00.000001"}
    r.update(k)
    return r


def _match(row, filters):
    for f, op, v in filters:
        x = row.get(f)
        if op not in ("=", "in", ">=", "<="):
            raise AssertionError(f"the stand-in does not know the operator {op}")
        if op == "=" and x != v or op == "in" and x not in v or op == ">=" and not (x is not None and str(x) >= str(v)) \
                or op == "<=" and not (x is not None and str(x) <= str(v)):
            return False
    return True


class FakeTenant:
    """The retailer's record API: its rules, POS Profiles, sales, customers and the app's requests, and every call."""

    def __init__(self, rules=None, sales_=None):
        self.rules = {r["name"]: r for r in (rules or [rule()])}
        self.sales = sales_ if sales_ is not None else sales()
        self.tills = [{"name": "POS-A", "customer": "WALK-IN", "warehouse": "Stores - DXB"},
                      {"name": "POS-B", "customer": "WALK-IN-B", "warehouse": "Stores - AUH"}]
        self.customers = {"C5": {"name": "C5", "mobile_no": "", "email_id": "", "custom_phone_no": "050 765 4321",
                                 "custom_email": ""}, "C4": {"name": "C4"}}
        self.requests = {"OLD": {"name": "OLD", "sale": "OLD", "customer": "STOP", "asked_to_stop": 1,
                                 "sale_date": "2026-10-01", "modified": "m0"}}
        self.calls, self.refuse, self.down_on, self.slow, self.key = [], None, None, 0, None

    def _check(self, kind):
        self.calls.append(kind)
        if self.refuse:
            raise app.TenantError("refused", self.refuse)
        if self.down_on and self.down_on in kind:
            raise app.TenantError("down")

    def rows(self, doctype, fields, filters, timeout=None, order_by="", limit=0):
        self._check(("rows", doctype, json.dumps(filters, sort_keys=True), order_by, limit))
        if doctype == fb.RULE:
            out = []
            for r in self.rules.values():
                if _match(r, filters):
                    base = {k: v for k, v in r.items() if k != "profiles"}
                    out += [dict(base, pos_profile=p) for p in r["profiles"]] or [dict(base, pos_profile=None)]
            return copy.deepcopy(out)
        if doctype == "POS Profile":
            return copy.deepcopy(self.tills)
        if doctype == "POS Invoice":
            got = sorted((s for s in self.sales if _match(s, filters)), key=lambda s: s["creation"])
            return copy.deepcopy(got[:limit] if limit else got)
        if doctype == fb.REQUEST:
            return [{f: q.get(f) for f in fields} for q in self.requests.values() if _match(q, filters)]
        if doctype == "Customer":
            return copy.deepcopy([c for c in self.customers.values() if _match(c, filters)])
        raise AssertionError(doctype)

    def doc(self, doctype, name, timeout=None):
        self._check(("doc", doctype, name))
        src = self.requests if doctype == fb.REQUEST else self.rules if doctype == fb.RULE else {}
        if name not in src:
            raise app.TenantError("missing", 404)
        return copy.deepcopy(src[name])

    def insert(self, doctype, body, timeout=None):
        self._check(("insert", doctype, body["sale"]))
        time.sleep(self.slow)
        assert doctype == fb.REQUEST
        if body["sale"] in self.requests:
            raise app.TenantError("dup", 409, app.DUPLICATE)
        self.requests[body["sale"]] = dict(body, name=body["sale"], modified="m1")
        return self.requests[body["sale"]]

    def update(self, doctype, name, body, timeout=None):
        self._check(("update", doctype, name))
        src = self.requests if doctype == fb.REQUEST else self.rules
        if "modified" in body and body["modified"] != src[name].get("modified"):
            raise app.TenantError("stale", 417, app.STALE)
        src[name].update({k: v for k, v in body.items() if k != "modified"}, modified=src[name].get("modified", "") + "+")
        return src[name]


def body(names=("Dubai",), doctype=None):
    recs = [{"doctype": doctype or fb.RULE, "name": n, "fields": {"name": n}} for n in names]
    ctx = {"v": 1, "action": "a1", "label": "Send feedback requests", "user": "manager@shop.example", "lang": "en",
           "idempotency_key": "k1", "inputs": {}, "records": recs}
    return json.dumps({"point": "desk_action/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=SECRET, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
    if site:
        h[shops.SITE_HEADER] = site
    return h


def token_of(link):
    frag = urllib.parse.parse_qs(urllib.parse.urlsplit(link).fragment)
    return frag["s"][0], frag["t"][0]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW)

    def press(self, raw=None, h=None):
        raw = raw or body()
        code, out, _ = self.svc.handle("POST", "/psf/send", signed(raw) if h is None else h, raw)
        return code, json.loads(out)

    def page(self, path, **b):
        code, out, _ = self.svc.handle("POST", path, {}, json.dumps(b).encode())
        return code, json.loads(out)

    # ---- the press -------------------------------------------------------------------------------------------------

    def test_s1_a_press_asks_each_customer_of_the_rules_new_sales_once_with_their_contact(self):
        code, out = self.press()
        self.assertEqual(code, 200)
        made = {k: v for k, v in self.shop.requests.items() if k != "OLD"}
        self.assertEqual(sorted(made), ["S10", "S2", "S5"])                      # C1's later sale, C2 by e-mail, C5's own
        self.assertEqual((made["S2"]["mobile"], made["S2"]["email"]), ("", "c2@example.com"))
        self.assertEqual(made["S5"]["mobile"], "050 765 4321")                    # the till's phone field on the customer
        r = made["S10"]
        self.assertEqual((r["customer"], r["rule"], r["store"], r["pos_profile"], r["sale_date"], r["open_until"],
                          r["status"]), ("C1", "Dubai", "Stores - DXB", "POS-A", "2026-10-24", "2026-10-31", "Sent"))
        self.assertTrue(r["link"].startswith(PAGE + "/#s=shop.example&t=S10."))
        self.assertEqual(out["message"]["level"], "success")
        self.assertIn("Made 3 feedback requests.", out["message"]["body"])
        self.assertIn("1 asked us to stop", out["message"]["body"])
        self.assertIn("1 with no mobile number or e-mail", out["message"]["body"])
        self.assertTrue(out["refresh"])

    def test_s2_the_sales_read_asks_only_for_submitted_till_sales_of_the_rules_tills_and_days_oldest_first(self):
        self.press()
        reads = [c for c in self.shop.calls if c[0] == "rows" and c[1] == "POS Invoice"]
        self.assertEqual(len(reads), 1)
        f = json.loads(reads[0][2])
        self.assertIn(["docstatus", "=", 1], f)
        self.assertIn(["is_return", "=", 0], f)
        self.assertIn(["pos_profile", "in", ["POS-A"]], f)
        self.assertIn(["posting_date", ">=", "2026-10-23"], f)
        self.assertEqual((reads[0][3], reads[0][4]), ("creation asc", app.SALES_MAX))

    def test_s3_a_second_press_starts_where_the_first_stopped_and_asks_nobody_twice(self):
        self.press()
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "2026-10-24 10:00:59.000000")
        before = dict(self.shop.requests)
        code, out = self.press()
        self.assertEqual(self.shop.requests, before)
        self.assertIn(["creation", ">=", "2026-10-24 10:00:59.000000"],
                      json.loads([c for c in self.shop.calls if c[1] == "POS Invoice"][-1][2]))
        self.assertIn("No new feedback requests.", out["message"]["body"])

    def test_s4_a_sale_already_asked_is_counted_never_asked_again(self):
        self.shop.requests["S10"] = {"name": "S10", "sale": "S10", "customer": "C1", "sale_date": "2026-10-24"}
        code, out = self.press()
        self.assertNotIn("S1", self.shop.requests)        # C1's earlier sale is not asked instead
        self.assertIn("2 already asked", out["message"]["body"])   # both of C1's sales

    def test_s5_no_rule_profiles_covers_every_till(self):
        self.shop.rules["Dubai"]["profiles"] = []
        self.press()
        self.assertIn("S6", self.shop.requests)
        f = json.loads([c for c in self.shop.calls if c[1] == "POS Invoice"][0][2])
        self.assertFalse([x for x in f if x[0] == "pos_profile"])

    def test_s6_a_rule_switched_off_or_misfilled_is_said_in_words_and_reads_no_sales(self):
        for change, words in (({"enabled": 0}, "Dubai is switched off."),
                              ({"look_back_days": 3, "open_days": 2}, "may not be more than the days a link stays open"),
                              ({"shown_name": ""}, "fill the name your customers read"),
                              ({"look_back_days": 9}, "days back must be 1 to 7"),
                              ({"open_days": 31}, "1 to 30")):
            self.shop = FakeTenant(rules=[rule(**change)])
            self.svc = app.Service(CONF, tenant=self.shop, now=NOW)
            code, out = self.press()
            self.assertIn(words, out["message"]["body"])
            self.assertEqual(out["message"]["level"], "warning")
            self.assertFalse([c for c in self.shop.calls if c[1] == "POS Invoice"], change)

    def test_s7_several_rules_in_one_press_ask_a_customer_once(self):
        self.shop = FakeTenant(rules=[rule(), rule(name="Every till", profiles=[])])
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW)
        code, out = self.press(body(("Dubai", "Every till")))
        made = sorted(k for k in self.shop.requests if k != "OLD")
        self.assertEqual(made, ["S10", "S2", "S5", "S6"])
        self.assertEqual(self.shop.requests["S6"]["rule"], "Every till")
        self.assertEqual(self.shop.rules["Every till"]["asked_up_to"], "2026-10-24 10:00:59.000000")

    def test_s8_a_press_out_of_time_after_its_reads_writes_nothing(self):
        clock = Clock()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW, clock=clock)
        real = self.shop.rows

        def slow_rows(doctype, *a, **k):
            if doctype == "Customer":
                clock.t += app.BUDGET_S          # the last read answers, but past the press's budget
            return real(doctype, *a, **k)
        self.shop.rows = slow_rows
        code, out = self.press()
        self.assertEqual(code, 502)
        self.assertEqual(sorted(self.shop.requests), ["OLD"])
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "")

    def test_s9_requests_not_started_in_time_wait_for_the_next_press_which_reads_them_again(self):
        clock = Clock()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW, clock=clock)
        real = self.shop.insert
        seen = []

        def insert(doctype, b, timeout=None):
            seen.append(b["sale"])
            clock.t = app.WRITE_UNTIL                   # the first save takes us to the line
            return real(doctype, b, timeout)
        self.shop.insert = insert
        app.WRITERS, writers = 1, app.WRITERS
        try:
            code, out = self.press()
        finally:
            app.WRITERS = writers
        self.assertEqual(len(seen), 1)
        self.assertIn("More sales wait: press again.", out["message"]["body"])
        self.assertEqual(out["message"]["level"], "warning")
        unmade = [s for s in self.shop.sales if s["name"] in ("S2", "S5", "S10") and s["name"] not in self.shop.requests]
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], min(s["creation"] for s in unmade))
        self.shop.insert = real
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW)
        self.press()
        self.assertEqual(sorted(k for k in self.shop.requests if k != "OLD"), ["S10", "S2", "S5"])

    def test_s10_a_request_the_retailer_refuses_is_counted_and_never_holds_the_rules_place(self):
        real = self.shop.insert

        def insert(doctype, b, timeout=None):
            if b["sale"] == "S2":
                raise app.TenantError("invalid e-mail", 417, "InvalidEmailAddressError")
            return real(doctype, b, timeout)
        self.shop.insert = insert
        code, out = self.press()
        self.assertIn("1 could not be made.", out["message"]["body"])
        self.assertNotIn("press again", out["message"]["body"])
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "2026-10-24 10:00:59.000000")

    def test_s27_a_store_east_of_utc_whose_sale_is_dated_ahead_of_utcs_day_is_asked(self):
        self.shop.sales.append(sale("S20", "C20", day="2026-10-25", creation="2026-10-24 21:30:00.0"))   # Dubai, 01:30
        code, out = self.press()
        self.assertIn("S20", self.shop.requests)
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "2026-10-24 21:30:00.0")

    def test_s28_a_refusal_of_every_request_is_tried_again_by_the_next_press(self):
        real = self.shop.insert

        def insert(doctype, b, timeout=None):
            raise app.TenantError("a Notification's condition failed", 417, "ValidationError")
        self.shop.insert = insert
        code, out = self.press()
        self.assertIn("3 could not be made.", out["message"]["body"])
        self.assertIn("press again", out["message"]["body"])
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "2026-10-24 10:00:02.000000")   # S2's: the first not made
        self.shop.insert = real
        self.press()
        self.assertEqual(sorted(k for k in self.shop.requests if k != "OLD"), ["S10", "S2", "S5"])

    def test_s29_reads_that_take_the_press_time_say_so(self):
        clock = Clock()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW, clock=clock)
        real = self.shop.rows

        def slow(doctype, *a, **k):
            if doctype == "Customer":
                clock.t = app.WRITE_UNTIL               # the reads end past the line: no request can start
            return real(doctype, *a, **k)
        self.shop.rows = slow
        code, out = self.press()
        self.assertEqual(sorted(self.shop.requests), ["OLD"])
        self.assertIn("Reading your sales took the press's time, so none was made yet.", out["message"]["body"])
        self.assertIn("press again", out["message"]["body"])

    def test_s30_the_press_reads_side_by_side(self):
        import threading
        gate = threading.Barrier(4, timeout=3)      # POS Profiles, the requests, the stops and the one rule's sales
        real = self.shop.rows

        def rows(doctype, fields, filters, *a, **k):
            if doctype in ("POS Profile", "POS Invoice") or doctype == fb.REQUEST:
                gate.wait()                         # passes only when all four are asked at once
            return real(doctype, fields, filters, *a, **k)
        self.shop.rows = rows
        code, out = self.press()
        self.assertEqual(code, 200)
        self.assertIn("Made 3", out["message"]["body"])

    def test_s31_a_customer_who_asked_to_stop_is_not_asked_on_another_record_with_the_same_number(self):
        self.shop.requests["OLD"].update(mobile="+971 50 123 4567", email="Stop@Example.com")
        self.shop.sales.append(sale("S21", "C21", mobile="", email="stop@example.com", creation="2026-10-24 11:00:00.0"))
        code, out = self.press()
        self.assertNotIn("S10", self.shop.requests)      # C1's sale carries the stopped number
        self.assertNotIn("S21", self.shop.requests)      # C21's carries the stopped e-mail
        self.assertIn("asked us to stop", out["message"]["body"])

    def test_s11_a_request_with_no_answer_is_tried_again_by_the_next_press(self):
        real = self.shop.insert

        def insert(doctype, b, timeout=None):
            if b["sale"] == "S5":
                raise app.TenantError("timeout")
            return real(doctype, b, timeout)
        self.shop.insert = insert
        code, out = self.press()
        self.assertIn("press again", out["message"]["body"])
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "2026-10-24 10:00:05.000000")

    def test_s12_a_request_made_meanwhile_by_another_press_counts_as_made(self):
        real = self.shop.insert

        def insert(doctype, b, timeout=None):
            raise app.TenantError("dup", 409, app.DUPLICATE)
        self.shop.insert = insert
        code, out = self.press()
        self.assertIn("Made 3", out["message"]["body"])
        self.assertEqual(self.shop.rules["Dubai"]["asked_up_to"], "2026-10-24 10:00:59.000000")
        self.shop.insert = real

    def test_s13_the_apps_user_refused_by_the_retailer_is_said_in_words(self):
        self.shop.refuse = 403
        code, out = self.press()
        self.assertEqual(code, 200)
        self.assertEqual(out["message"]["body"], app.REFUSED)

    def test_s14_a_press_signed_with_another_secret_or_too_old_is_refused_before_any_read(self):
        raw = body()
        for h in (signed(raw, "other"), signed(raw, ts=time.time() - 600), {}):
            code, out = self.press(raw, h)
            self.assertEqual(code, 401)
        self.assertEqual(self.shop.calls, [])

    def test_s15_a_press_on_anything_but_rules_is_refused_before_any_read(self):
        for raw in (body(doctype="POS Invoice"), body(()), body([f"R{i}" for i in range(101)]), b'{"point":"x"}'):
            code, out = self.press(raw, signed(raw))
            self.assertEqual(code, 400, raw[:60])
        self.assertEqual(self.shop.calls, [])

    def test_s16_a_rule_not_found_is_named(self):
        code, out = self.press(body(("Dubai", "Gone")))
        self.assertIn("Gone was not found.", out["message"]["body"])
        self.assertIn("Made 3", out["message"]["body"])

    def test_s17_customers_whose_sale_holds_no_contact_are_read_fifty_at_a_time(self):
        many = [sale(f"S{i}", f"N{i}", mobile="", creation=f"2026-10-24 11:{i // 60:02d}:{i % 60:02d}.0")
                for i in range(100, 220)]
        self.shop = FakeTenant(sales_=many)
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW)
        self.press()
        reads = [json.loads(c[2]) for c in self.shop.calls if c[0] == "rows" and c[1] == "Customer"]
        self.assertEqual(sorted(len(f[0][2]) for f in reads), [20, 50, 50])        # read side by side

    # ---- the page --------------------------------------------------------------------------------------------------

    def answered_link(self):
        self.press()
        return token_of(self.shop.requests["S10"]["link"])

    def test_s18_the_page_shows_the_rules_words_and_the_date_never_the_customer(self):
        s, t = self.answered_link()
        code, out = self.page("/psf/open", s=s, t=t)
        self.assertEqual(code, 200)
        self.assertEqual(out, {"state": "open", "name": "Al Waha Stores", "date": "2026-10-24",
                               "question": "How was your visit?", "answers": ["Great", "Fine", "Poor"], "stopped": False})

    def test_s19_an_answer_is_written_once_in_english_with_its_comment(self):
        s, t = self.answered_link()
        code, out = self.page("/psf/answer", s=s, t=t, answer=2, comment="  Long   queue  ", stop=False)
        self.assertEqual(out["state"], "answered")
        q = self.shop.requests["S10"]
        self.assertEqual((q["answer"], q["comment"], q["status"], q["answered_at"]),
                         ("Not satisfied", "Long queue", "Answered", "2026-10-24 18:00 UTC"))
        code, out = self.page("/psf/answer", s=s, t=t, answer=0, comment="changed my mind", stop=False)
        self.assertEqual((out["state"], self.shop.requests["S10"]["answer"]), ("answered", "Not satisfied"))

    def test_s20_stop_these_messages_is_kept_even_without_an_answer_and_the_next_press_skips_them(self):
        s, t = self.answered_link()
        code, out = self.page("/psf/answer", s=s, t=t, answer=None, comment="", stop=True)
        self.assertEqual((out["state"], out["stopped"]), ("open", True))
        self.assertEqual(self.shop.requests["S10"]["asked_to_stop"], 1)
        self.shop.sales.append(sale("S13", "C1", creation="2026-10-24 12:00:00.0"))
        code, out = self.press()
        self.assertNotIn("S13", self.shop.requests)
        self.assertIn("asked us to stop", out["message"]["body"])

    def test_s21_a_link_past_its_last_day_is_closed_and_takes_no_answer(self):
        s, t = self.answered_link()
        later = app.Service(CONF, tenant=self.shop, now=NOW + 8 * 86400)
        code, out, _ = later.handle("POST", "/psf/answer", {}, json.dumps({"s": s, "t": t, "answer": 0}).encode())
        self.assertEqual(json.loads(out)["state"], "closed")
        self.assertNotIn("answer", self.shop.requests["S10"])

    def test_s22_a_guessed_or_altered_link_never_reaches_the_retailer(self):
        s, t = self.answered_link()
        self.shop.calls.clear()
        sale_, _, sig = t.rpartition(".")
        for bs, bt in ((s, f"S2.{sig}"), (s, sale_ + "." + "A" * fb.SIG_LEN), ("other.example", t), (s, "S10"), (s, None)):
            code, out = self.page("/psf/open", s=bs, t=bt)
            self.assertEqual((code, out), (404, {"state": "unknown"}), (bs, bt))
        self.assertEqual(self.shop.calls, [])

    def test_s23_two_taps_at_once_keep_the_first_answer(self):
        s, t = self.answered_link()
        real = self.shop.update

        def racing(doctype, name, b, timeout=None):
            self.shop.requests[name].update(answer="Satisfied", status="Answered", modified="m9")   # the other tap
            return real(doctype, name, b, timeout)
        self.shop.update = racing
        code, out = self.page("/psf/answer", s=s, t=t, answer=2, comment="", stop=False)
        self.assertEqual((code, out["state"], self.shop.requests["S10"]["answer"]), (200, "answered", "Satisfied"))

    def test_s24_a_bad_answer_is_refused_and_writes_nothing(self):
        s, t = self.answered_link()
        for b in ({"answer": 3}, {"answer": True}, {"answer": "0"}, {"answer": None, "stop": False}, {"comment": 5}):
            code, out = self.page("/psf/answer", s=s, t=t, **b)
            self.assertEqual(code, 400, b)
        self.assertNotIn("answer", self.shop.requests["S10"])

    def test_s25_the_page_and_its_files_are_served_with_a_strict_policy(self):
        for path in ("/", "/page.js", "/page.css"):
            code, data, h = self.svc.handle("GET", path, {}, b"")
            self.assertEqual(code, 200)
            self.assertIn("default-src 'none'", h["Content-Security-Policy"])
            self.assertEqual(h["Referrer-Policy"], "no-referrer")
        self.assertEqual(self.svc.handle("GET", "/app.py", {}, b"")[0], 404)

    def test_s26_the_retailer_down_on_the_page_is_said_and_the_page_waits(self):
        s, t = self.answered_link()
        self.shop.down_on = "doc"
        code, out = self.page("/psf/open", s=s, t=t)
        self.assertEqual((code, out), (503, {"state": "unavailable"}))


class Together(unittest.TestCase):
    def test_the_reads_go_side_by_side(self):
        import threading
        gate = threading.Barrier(3, timeout=2)

        def call(n):
            def f():
                gate.wait()                     # each waits for the other two: only calls made at once get past
                return n
            return f
        svc = app.Service(CONF, tenant=FakeTenant(), now=NOW)
        self.assertEqual(svc.together([call(1), call(2), call(3)]), [1, 2, 3])


class ManyRetailers(unittest.TestCase):
    APP = "ivendnext_psf"

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(tmp, "shops.json"))
        for site, n in (("shop-a.ivendnext.com", "a"), ("shop-b.ivendnext.com", "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{self.APP}:sub:send": f"send-{n}", "user:psf@x": f"key-{n}:sec-{n}", "user:Administrator": "adm"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{self.APP}:sub:send": "send-c"}})     # no user key yet
        self.doors = {}
        self.svc = app.Service({"IVN_LIBRARY_APP": self.APP, "PSF_PREFIX": "IVENDNEXT PSF", "PSF_PAGE_URL": PAGE},
                               store=self.store, tenants=self.door, now=NOW)

    def tearDown(self):
        fb.use_prefix("PP PSF")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = FakeTenant(rules=[rule()])
            self.doors[url].key = key
        return self.doors[url]

    def press(self, secret, site):
        raw = body()
        code, out, _ = self.svc.handle("POST", "/psf/send", signed(raw, secret, site=site), raw)
        return code, json.loads(out)

    def test_each_retailer_is_checked_with_its_own_secret_and_written_with_its_own_key_under_the_librarys_prefix(self):
        self.assertEqual(self.press("send-b", "shop-a.ivendnext.com")[0], 401)
        code, out = self.press("send-a", "shop-a.ivendnext.com")
        self.assertEqual(code, 200)
        door = self.doors["https://shop-a.ivendnext.com"]
        self.assertEqual(door.key, "key-a:sec-a")                      # never Administrator's
        self.assertEqual(fb.REQUEST, "IVENDNEXT PSF Request")
        self.assertTrue(door.requests["S10"]["link"].startswith(PAGE + "/#s=shop-a.ivendnext.com&t=S10."))
        self.assertNotIn("https://shop-b.ivendnext.com", self.doors)

    def test_a_link_works_only_for_its_own_retailer(self):
        self.press("send-a", "shop-a.ivendnext.com")
        s, t = token_of(self.doors["https://shop-a.ivendnext.com"].requests["S10"]["link"])
        ok = self.svc.handle("POST", "/psf/open", {}, json.dumps({"s": s, "t": t}).encode())
        self.assertEqual(json.loads(ok[1])["state"], "open")
        other = self.svc.handle("POST", "/psf/open", {}, json.dumps({"s": "shop-b.ivendnext.com", "t": t}).encode())
        self.assertEqual(other[0], 404)

    def test_a_link_signed_with_the_previous_secret_still_opens(self):
        self.press("send-a", "shop-a.ivendnext.com")
        s, t = token_of(self.doors["https://shop-a.ivendnext.com"].requests["S10"]["link"])
        rec = self.store.get("shop-a.ivendnext.com")
        rec["previous"] = {f"{self.APP}:sub:send": "send-a"}
        rec["secrets"][f"{self.APP}:sub:send"] = "send-a2"
        self.store.put("shop-a.ivendnext.com", rec)
        code, out, _ = self.svc.handle("POST", "/psf/open", {}, json.dumps({"s": s, "t": t}).encode())
        self.assertEqual(json.loads(out)["state"], "open")

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("send-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["body"]), (200, app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_the_function_answers_health_a_press_and_the_page(self):
        os.environ.update({"IVN_LIBRARY_APP": self.APP, "PSF_PREFIX": "IVENDNEXT PSF", "PSF_PAGE_URL": PAGE,
                           "IVN_SHOPS_FILE": self.store.path})
        app._KEPT.clear()
        try:
            r = app.lambda_handler({"httpMethod": "GET", "path": "/health", "headers": {}})
            self.assertEqual((r["statusCode"], json.loads(r["body"])), (200, {"ok": 1}))
            r = app.lambda_handler({"httpMethod": "GET", "path": "/", "headers": {}})
            self.assertTrue(r["headers"]["Content-Type"].startswith("text/html"))
            raw = body()
            h = {k.lower(): v for k, v in signed(raw, "send-x", site="shop-a.ivendnext.com").items()}
            r = app.lambda_handler({"httpMethod": "POST", "path": "/psf/send", "headers": h,
                                    "body": base64.b64encode(raw).decode(), "isBase64Encoded": True})
            self.assertEqual(r["statusCode"], 401)
        finally:
            for k in ("IVN_LIBRARY_APP", "PSF_PREFIX", "PSF_PAGE_URL", "IVN_SHOPS_FILE"):
                os.environ.pop(k, None)
            app._KEPT.clear()
            fb.use_prefix("PP PSF")


class ShopApi(unittest.TestCase):
    def test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed(self):
        import http.server
        import threading
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header("Location", "https://elsewhere.example/")
                self.end_headers()

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            t = app.Tenant(f"http://127.0.0.1:{srv.server_port}", "k", "s")
            with self.assertRaises(app.TenantError) as e:
                t.doc("PP PSF Request", "A/B")
            self.assertEqual(e.exception.code, 302)
            self.assertEqual(seen, ["/api/resource/PP%20PSF%20Request/A%2FB"])
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
