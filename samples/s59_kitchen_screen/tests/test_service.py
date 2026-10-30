"""S59's service against a stand-in shop (``fakeshop.py``): the press that makes a screen's link, and a screen's three
calls (the board, a move, sold out).

    python3 -m unittest discover -s samples/s59_kitchen_screen/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "service"), os.path.dirname(HERE)]
import app  # noqa: E402
import fakeshop as F  # noqa: E402
import ksc  # noqa: E402


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def service(shop, clock=None):
    conf = {"IVN_SHOP_URL": f"https://{F.SITE}", "IVN_SHOP_KEY": "k:s", "IVN_LINK_SECRET": F.SECRET, "KSC_PAGE_URL": F.PAGE}
    clock = clock or Clock()
    return app.Service(conf, tenant=shop, now=clock, clock=clock)


def press(svc, names, secret=F.SECRET, ts=None, doctype="PP KSC Screen"):
    raw = json.dumps({"point": "desk_action/1", "context": {"v": 1, "user": "manager@bistro", "lang": "en",
                                                            "records": [{"doctype": doctype, "name": n} for n in names]}}).encode()
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return svc.handle("POST", "/ksc/link", {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw)


def answer(res):
    code, body, _ = res
    return code, json.loads(body)


def token_of(shop, name):
    return shop.screens[name]["link"].split("&t=")[1]


def call(svc, path, t, **extra):
    return answer(svc.handle("POST", path, {}, json.dumps(dict({"s": F.SITE, "t": t}, **extra)).encode()))


def made(shop, svc, name="KSC-SCREEN-00001"):
    """The link made by a press, and its token as written on the screen record."""
    code, out = answer(press(svc, [name]))
    assert code == 200 and out["message"]["level"] == "success", out
    return token_of(shop, name)


SCREENS = [F.screen("KSC-SCREEN-00001"), F.screen("KSC-SCREEN-00002", kind="Expo", stations=(), title="Pass"),
           F.screen("KSC-SCREEN-00003", kind="Board", stations=(), title="Counter board"),
           F.screen("KSC-SCREEN-00004", stations=(F.GRILL, F.FRY), title="Hot side")]


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.shop = F.FakeTenant(screens=SCREENS)
        self.clock = Clock()
        self.svc = service(self.shop, self.clock)

    def later(self, s=2.0):
        self.clock.t += s

    # ── Make link ──
    def test_l1_an_unsigned_or_wrongly_signed_press_is_refused(self):
        self.assertEqual(answer(press(self.svc, ["KSC-SCREEN-00001"], secret="wrong"))[0], 401)
        self.assertEqual(answer(press(self.svc, ["KSC-SCREEN-00001"], ts=time.time() - 3600))[0], 401)
        self.assertEqual(self.shop.calls, [])                         # nothing read before the signature holds

    def test_l2_make_link_raises_the_number_and_writes_a_link_to_this_screen(self):
        made(self.shop, self.svc)
        s = self.shop.screens["KSC-SCREEN-00001"]
        self.assertEqual(s["number"], 1)
        self.assertTrue(s["link"].startswith(F.PAGE + "/#s=bistro.example.com&t=KSC-SCREEN-00001.1."))
        self.assertEqual(s["made_for"], ksc.made_for(s))

    def test_l3_make_link_again_stops_the_old_link_within_its_keep(self):
        old = made(self.shop, self.svc)
        self.assertEqual(call(self.svc, "/ksc/board", old)[1]["state"], "open")
        new = made(self.shop, self.svc)
        self.later(app.SCREEN_KEEP_S + 1)
        self.assertEqual(call(self.svc, "/ksc/board", old)[0], 404)
        self.assertEqual(call(self.svc, "/ksc/board", new)[1]["state"], "open")

    def test_l4_a_station_screen_with_no_station_gets_no_link(self):
        self.shop.screens["KSC-SCREEN-00001"]["stations"] = []
        code, out = answer(press(self.svc, ["KSC-SCREEN-00001"]))
        self.assertEqual(out["message"]["level"], "warning")
        self.assertIn("add the screen's kitchen stations", out["message"]["body"])
        self.assertEqual(self.shop.screens["KSC-SCREEN-00001"]["number"], 0)

    def test_l5_a_screen_changed_a_moment_ago_is_not_overwritten(self):
        self.shop.stale = 1
        code, out = answer(press(self.svc, ["KSC-SCREEN-00001"]))
        self.assertIn("changed a moment ago", out["message"]["body"])
        self.assertEqual(self.shop.screens["KSC-SCREEN-00001"]["number"], 0)

    def test_l6_a_press_on_another_record_type_is_refused_before_anything_is_read(self):
        self.assertEqual(answer(press(self.svc, ["X"], doctype="Item"))[0], 400)
        self.assertEqual(self.shop.calls, [])

    def test_l7_a_refused_app_user_is_said_plainly(self):
        self.shop.refuse = ("doc", 403)
        self.assertIn("may not read or write", answer(press(self.svc, ["KSC-SCREEN-00001"]))[1]["message"]["body"])

    # ── the link ──
    def test_g1_a_forged_or_edited_link_is_refused_before_the_shop_is_read(self):
        t = made(self.shop, self.svc)
        n = len(self.shop.calls)
        for bad in (t[:-1] + ("A" if t[-1] != "A" else "B"), t.replace("00001", "00002"), "KSC-SCREEN-00001.9.xxxxxxxxxxxxxxxxxxxxxx", ""):
            self.assertEqual(call(self.svc, "/ksc/board", bad), (404, {"state": "unknown"}), bad)
        self.assertEqual(len(self.shop.calls), n)

    def test_g2_a_screen_whose_store_or_stations_changed_is_refused(self):
        t = made(self.shop, self.svc)
        self.shop.screens["KSC-SCREEN-00001"]["stations"] = [{"station": F.BAR}]
        self.assertEqual(call(self.svc, "/ksc/board", t)[0], 404)
        t = made(self.shop, self.svc, "KSC-SCREEN-00002")
        self.shop.screens["KSC-SCREEN-00002"]["store"] = F.OTHER
        self.assertEqual(call(self.svc, "/ksc/board", t)[0], 404)

    def test_g3_a_store_with_no_row_answers_closed(self):
        t = made(self.shop, self.svc)
        self.shop.settings[F.CO]["stores"] = []
        self.assertEqual(call(self.svc, "/ksc/board", t)[1]["state"], "closed")

    def test_g4_the_shop_refusing_the_app_user_answers_not_set_up(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("station_tickets", 403, "PermissionError")
        self.assertEqual(call(self.svc, "/ksc/board", t)[1]["state"], "not_set_up")
        self.shop.door_refuse = ("station_tickets", 417, "DeviceRequiredError")
        self.later(5)
        self.assertEqual(call(self.svc, "/ksc/board", t)[1]["state"], "not_set_up")

    # ── the board ──
    def test_b1_a_station_screen_shows_its_own_stations_at_its_own_store(self):
        t = made(self.shop, self.svc)
        v = call(self.svc, "/ksc/board", t)[1]
        self.assertEqual((v["kind"], v["title"], v["stations"]), ("Station", "Grill", [F.GRILL]))
        self.assertEqual([(x["kitchen_order"], x["ticket"]) for x in v["view"]["tickets"]], [("ko1", 1), ("ko2", 1)])
        self.assertNotIn("kx9", json.dumps(v))                         # another store's ticket never reaches it
        self.assertEqual(v["as_of"], "2026-10-30 19:05:30.000001")
        hot = made(self.shop, self.svc, "KSC-SCREEN-00004")
        self.later(2)
        self.assertEqual({x["station"] for x in call(self.svc, "/ksc/board", hot)[1]["view"]["tickets"]}, {F.GRILL, F.FRY})

    def test_b2_the_expo_groups_each_order_and_adds_up_what_waits(self):
        t = made(self.shop, self.svc, "KSC-SCREEN-00002")
        v = call(self.svc, "/ksc/board", t)[1]["view"]
        self.assertEqual([o["kitchen_order"] for o in v["orders"]], ["ko1", "ko2"])
        self.assertEqual([len(o["tickets"]) for o in v["orders"]], [2, 2])
        self.assertEqual([(d["item_name"], d["qty"]) for d in v["waiting"]],
                         [("Fries", 3), ("Beer", 2), ("Burger", 2), ("Steak", 1)])   # the cheese is a choice: not counted

    def test_b3_the_board_shows_call_numbers_only_counter_sales_by_default(self):
        for t in self.shop.tickets:
            if t["kitchen_order"] == "ko1":
                t["state"] = "ready"
        t = made(self.shop, self.svc, "KSC-SCREEN-00003")
        v = call(self.svc, "/ksc/board", t)[1]
        self.assertEqual(v["view"], {"preparing": [], "ready": ["42"]})
        self.assertNotIn("Burger", json.dumps(v))                      # no dish, no till on the guests' board
        self.assertNotIn("sold_out", v)
        self.shop.settings[F.CO]["stores"][0]["tables_on_board"] = 1
        self.later(app.SCREEN_KEEP_S + 1)
        self.assertEqual(call(self.svc, "/ksc/board", t)[1]["view"], {"preparing": ["Table 12"], "ready": ["42"]})

    def test_b4_screens_of_one_store_share_one_read_and_a_screen_reads_twenty_times_a_minute(self):
        a, b = made(self.shop, self.svc), made(self.shop, self.svc, "KSC-SCREEN-00002")
        self.shop.calls.clear()
        for _ in range(20):                                            # one minute at the page's 3 seconds
            call(self.svc, "/ksc/board", a)
            call(self.svc, "/ksc/board", b)
            self.later(3)
        self.assertEqual(self.shop.calls.count("station_tickets"), 20)  # two screens, one read each 3 s
        self.assertEqual(self.shop.calls.count("item_availability"), 2)  # the sold-out list is kept 30 s
        self.shop.calls.clear()
        call(self.svc, "/ksc/board", a)
        call(self.svc, "/ksc/board", b)
        self.assertEqual(self.shop.calls.count("station_tickets"), 1)

    def test_b5_the_store_row_sets_the_look(self):
        self.shop.settings[F.CO]["stores"][0].update(look="Light", accent="#0b4d69", language="Arabic", warn_min=5, late_min=3,
                                                     slip_size="Large")
        t = made(self.shop, self.svc)
        self.assertEqual(call(self.svc, "/ksc/board", t)[1]["look"],
                         {"mode": "light", "accent": "#0b4d69", "lang": "ar", "warn": 5, "late": 6, "size": "large"})

    # ── moves ──
    def move(self, t, order, n, state):
        return call(self.svc, "/ksc/move", t, kitchen_order=order, ticket=n, state=state, store=F.OTHER)[1]

    def test_m1_a_cook_moves_a_ticket_one_step_at_a_time_and_a_double_tap_is_safe(self):
        t = made(self.shop, self.svc)
        for state in ("started", "ready", "bumped"):
            self.assertEqual(self.move(t, "ko1", 1, state), {"state": "moved", "moved": 1}, state)
            self.later(1)
        self.assertEqual(self.move(t, "ko1", 1, "bumped"), {"state": "moved", "moved": 1})   # the door answers already
        moves = [b for v, b in self.shop.sent if v == "station_ticket_move"]
        self.assertEqual([b["state"] for b in moves], ["started", "ready", "bumped", "bumped"])
        self.assertTrue(all(b["store"] == F.STORE for b in moves))

    def test_m2_a_skip_or_a_step_back_is_refused_before_the_door(self):
        t = made(self.shop, self.svc)
        self.assertEqual(self.move(t, "ko1", 1, "ready"), {"state": "refused", "why": "step"})
        self.shop.tickets[0]["state"] = "ready"
        self.later(1)
        self.assertEqual(self.move(t, "ko1", 1, "started"), {"state": "refused", "why": "step"})
        self.assertFalse([v for v, _ in self.shop.sent if v == "station_ticket_move"])

    def test_m3_a_station_screen_never_moves_another_stations_or_another_stores_ticket(self):
        t = made(self.shop, self.svc)
        self.assertEqual(self.move(t, "ko1", 2, "started"), {"state": "refused", "why": "not_yours"})   # the fryer's
        self.later(1)
        self.assertEqual(self.move(t, "kx9", 1, "started"), {"state": "refused", "why": "gone"})        # another store's
        self.assertFalse([v for v, _ in self.shop.sent if v == "station_ticket_move"])

    def test_m4_the_board_moves_nothing_and_the_expo_only_bumps(self):
        board, expo = made(self.shop, self.svc, "KSC-SCREEN-00003"), made(self.shop, self.svc, "KSC-SCREEN-00002")
        self.assertEqual(self.move(board, "ko1", 1, "started"), {"state": "refused", "why": "board"})
        self.assertEqual(self.move(expo, "ko1", 1, "started"), {"state": "refused", "why": "not_yours"})
        self.assertEqual(call(self.svc, "/ksc/move", board, kitchen_order="ko1", order=True)[1]["why"], "not_yours")

    def test_m5_the_expo_bumps_an_order_only_when_every_station_is_ready(self):
        self.shop.tickets.append(F.ticket("ko1", 3, F.FRY, [F.line("FRIES", "Fries", 1)], kind="void"))
        expo = made(self.shop, self.svc, "KSC-SCREEN-00002")
        self.assertEqual(call(self.svc, "/ksc/move", expo, kitchen_order="ko1", order=True)[1], {"state": "refused", "why": "step"})
        for tk in self.shop.tickets[:2]:
            tk["state"] = "ready"
        self.later(1)
        self.assertEqual(call(self.svc, "/ksc/move", expo, kitchen_order="ko1", order=True)[1], {"state": "moved", "moved": 2})
        self.assertEqual([t["state"] for t in self.shop.tickets[:2]], ["bumped", "bumped"])
        self.assertEqual(self.shop.tickets[-1]["state"], "new")           # the void is the fryer's to strike and bump

    def test_m6_a_flood_of_taps_reads_the_retailer_no_more(self):
        t = made(self.shop, self.svc)
        self.assertEqual(self.move(t, "ko1", 1, "started")["state"], "moved")
        self.assertEqual(self.move(t, "ko1", 1, "ready"), {"state": "refused", "why": "wait"})

    def test_m7_the_doors_refusal_is_said_and_the_board_read_again(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("station_ticket_move", 417, "TicketStepError")
        self.assertEqual(self.move(t, "ko1", 1, "started"), {"state": "refused", "why": "step"})
        self.later(1)
        self.shop.door_refuse = ("station_ticket_move", 404, "TicketNotFoundError")
        self.assertEqual(self.move(t, "ko1", 1, "started"), {"state": "refused", "why": "gone"})

    def test_m8_a_move_names_a_real_ticket(self):
        t = made(self.shop, self.svc)
        for bad in ({"kitchen_order": "ko1", "ticket": "1", "state": "started"},
                    {"kitchen_order": "../x", "ticket": 1, "state": "started"},
                    {"kitchen_order": "ko1", "ticket": 1, "state": "new"},
                    {"kitchen_order": "ko1", "ticket": True, "state": "started"}):
            self.assertEqual(call(self.svc, "/ksc/move", t, **bad)[1], {"state": "refused", "why": "gone"}, bad)

    # ── sold out ──
    def sold(self, t, code, out=True):
        return call(self.svc, "/ksc/soldout", t, item_code=code, sold_out=out, warehouse=F.OTHER, store=F.OTHER)[1]

    def test_s1_a_dish_on_the_board_is_marked_sold_out_at_the_screens_own_store_only(self):
        t = made(self.shop, self.svc)
        self.assertEqual(self.sold(t, "BURGER"), {"state": "set", "item_code": "BURGER", "sold_out": True})
        (body,) = [b for v, b in self.shop.sent if v == "set_item_availability"]
        self.assertEqual((body["warehouse"], body["sold_out"]), (F.STORE, 1))
        self.later(1)
        board = call(self.svc, "/ksc/board", t)[1]
        self.assertEqual(board["sold_out"]["out"], [{"item_code": "BURGER"}])
        self.later(1)
        self.assertEqual(self.sold(t, "BURGER", False)["sold_out"], False)
        self.assertEqual(self.shop.sold, set())

    def test_s2_an_item_the_kitchen_has_not_seen_is_refused(self):
        t = made(self.shop, self.svc)
        self.assertEqual(self.sold(t, "CAVIAR"), {"state": "refused", "why": "not_listed"})
        self.assertFalse([v for v, _ in self.shop.sent if v == "set_item_availability"])

    def test_s3_an_item_already_sold_out_can_be_cleared_though_no_ticket_names_it(self):
        self.shop.sold = {("SOUP", F.STORE)}
        t = made(self.shop, self.svc)
        self.assertEqual(self.sold(t, "SOUP", False)["state"], "set")

    def test_s5_a_station_screen_offers_only_its_own_stations_dishes(self):
        t = made(self.shop, self.svc)
        self.assertEqual([d["item_code"] for d in call(self.svc, "/ksc/board", t)[1]["sold_out"]["dishes"]],
                         ["BURGER", "CHEESE", "STEAK"])                  # the grill's: no beer, no fries
        self.assertEqual(self.sold(t, "BEER"), {"state": "refused", "why": "not_listed"})
        expo = made(self.shop, self.svc, "KSC-SCREEN-00002")
        self.later(1)
        self.assertEqual(self.sold(expo, "BEER")["state"], "set")        # the pass sees every station

    def test_s6_a_sold_out_read_the_shop_refuses_leaves_the_tickets_showing(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("item_availability", 403, "PermissionError")
        v = call(self.svc, "/ksc/board", t)[1]
        self.assertEqual((v["state"], len(v["view"]["tickets"])), ("open", 2))
        self.assertNotIn("sold_out", v)
        self.shop.calls.clear()
        for i in range(11):                                            # 33 s of reads: kept refused 30 s, so asked once
            self.later(3)
            self.assertNotIn("sold_out", call(self.svc, "/ksc/board", t)[1], i)
            if i == 2:                                                 # a tap while it is kept is told the same refusal
                self.assertEqual(self.sold(t, "FRIES"), {"state": "not_set_up"})
        self.assertEqual(self.shop.calls.count("item_availability"), 1)

    def test_s7_a_sold_out_read_that_timed_out_is_kept_as_a_timeout_not_a_refusal(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("item_availability", None)
        self.assertNotIn("sold_out", call(self.svc, "/ksc/board", t)[1])
        self.later(3)
        self.assertEqual(call(self.svc, "/ksc/soldout", t, item_code="FRIES", sold_out=True), (503, {"state": "unavailable"}))
        self.assertEqual(self.shop.calls.count("item_availability"), 1)

    def test_s8_a_dish_sold_out_that_no_ticket_names_is_shown_by_its_name(self):     # KSCSOLDNAME (demo-2, 10-30)
        self.shop.sold = {("SOUP", F.STORE)}
        t = made(self.shop, self.svc)
        self.assertEqual(call(self.svc, "/ksc/board", t)[1]["sold_out"]["out"],
                         [{"item_code": "SOUP", "item_name": "Soup of the day"}])

    def test_s9_a_names_read_the_shop_refuses_leaves_the_codes_showing(self):
        self.shop.sold = {("SOUP", F.STORE)}
        self.shop.refuse = ("rows Retail Item Availability", 403)
        t = made(self.shop, self.svc)
        v = call(self.svc, "/ksc/board", t)[1]
        self.assertEqual((v["state"], v["sold_out"]["out"]), ("open", [{"item_code": "SOUP"}]))

    def test_s4_sold_out_off_for_the_store_or_from_the_board_is_refused(self):
        board = made(self.shop, self.svc, "KSC-SCREEN-00003")
        self.assertEqual(self.sold(board, "FRIES"), {"state": "refused", "why": "off"})
        self.shop.settings[F.CO]["stores"][0]["sold_out_on"] = 0
        t = made(self.shop, self.svc)
        self.assertEqual(self.sold(t, "FRIES"), {"state": "refused", "why": "off"})
        self.assertNotIn("sold_out", call(self.svc, "/ksc/board", t)[1])
        self.assertFalse([v for v, _ in self.shop.sent if v == "set_item_availability"])

    # ── every call ──
    def test_e1_the_page_is_served_with_a_strict_policy_and_the_kits_files(self):
        for path in ("/", "/page.js", "/fit.js", "/page.css", "/ivn-kit.css", "/ivn-kit.js"):
            code, body, hdrs = self.svc.handle("GET", path, {}, None)
            self.assertEqual(code, 200, path)
            policy = dict(p.strip().split(" ", 1) for p in hdrs["Content-Security-Policy"].split(";"))
            self.assertEqual((policy["default-src"], policy["script-src"], policy["style-src"], policy["connect-src"],
                              policy["frame-ancestors"]), ("'none'", "'self'", "'self'", "'self'", "'none'"), path)
        page = self.svc.handle("GET", "/", {}, None)[1].decode()
        self.assertNotIn("<script>", page)                             # no inline script
        self.assertNotIn("style=", page)
        self.assertNotRegex(page, r"(src|href)=\"(https?:)?//")         # nothing from another site

    def test_e3_every_file_the_service_serves_is_in_the_hosted_package(self):   # the page's files; app.json's
        # handler and the template modules it imports are listed by hand beside them
        pkg = set(json.load(open(os.path.join(os.path.dirname(HERE), "app.json")))["package"])
        for fname, _ in app.STATIC.values():
            self.assertIn(f"samples/s59_kitchen_screen/service/{fname}", pkg, fname)   # else the hosted page is blank

    def test_e4_the_page_may_reach_the_live_service_and_nothing_else(self):
        live = "https://kitchen-screen-live.example.app"
        conf = {"IVN_SHOP_URL": f"https://{F.SITE}", "IVN_SHOP_KEY": "k:s", "IVN_LINK_SECRET": F.SECRET,
                "KSC_PAGE_URL": F.PAGE, "KSC_LIVE_URL": live + "/"}
        svc = app.Service(conf, tenant=self.shop, now=self.clock, clock=self.clock)
        policy = dict(p.strip().split(" ", 1) for p in svc.handle("GET", "/", {}, None)[2]["Content-Security-Policy"].split(";"))
        self.assertEqual(policy["connect-src"], "'self' " + live)
        self.assertEqual(call(svc, "/ksc/board", made(self.shop, svc))[1]["live"], live)
        self.assertNotIn("live", call(self.svc, "/ksc/board", made(self.shop, self.svc))[1])   # unset: 3-second reads only
        for bad in (live + "/ksc", "javascript:alert(1)", live + " 'unsafe-eval'", "https://user@live.example.app", live + ";"):
            with self.assertRaises(SystemExit, msg=bad):
                app.Service(dict(conf, KSC_LIVE_URL=bad), tenant=self.shop)

    def test_e2_a_large_or_shapeless_call_is_refused(self):
        self.assertEqual(answer(self.svc.handle("POST", "/ksc/board", {}, b"x" * (ksc.PAGE_BODY_MAX + 1)))[0], 413)
        self.assertEqual(answer(self.svc.handle("POST", "/ksc/board", {}, b"[]"))[0], 400)
        self.assertEqual(answer(self.svc.handle("POST", "/ksc/nope", {}, b"{}"))[0], 404)


if __name__ == "__main__":
    unittest.main()
