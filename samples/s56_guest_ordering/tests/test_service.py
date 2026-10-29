"""S56's service against a stand-in shop (``fakeshop.py``): the press that makes a code, and the guest's two calls."""

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
import gor  # noqa: E402

ORDER = "6f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a"


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def service(shop, clock=None):
    conf = {"IVN_SHOP_URL": f"https://{F.SITE}", "IVN_SHOP_KEY": "k:s", "IVN_CODE_SECRET": F.SECRET, "GOR_PAGE_URL": F.PAGE}
    clock = clock or Clock()
    return app.Service(conf, tenant=shop, now=clock, clock=clock)


def press(svc, names, secret=F.SECRET, ts=None, doctype="PP GOR Code"):
    raw = json.dumps({"point": "desk_action/1", "context": {"v": 1, "user": "manager@bistro", "lang": "en",
                                                            "records": [{"doctype": doctype, "name": n} for n in names]}}).encode()
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return svc.handle("POST", "/gor/code", {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw)


def answer(res):
    code, body, _ = res
    return code, json.loads(body)


def token_of(shop, name):
    return shop.codes[name]["link"].split("&t=")[1]


def guest(svc, path, t, **extra):
    return answer(svc.handle("POST", path, {}, json.dumps(dict({"s": F.SITE, "t": t}, **extra)).encode()))


def made(shop, svc, name="GOR-CODE-00001"):
    """The code made by a press, and its token as printed."""
    code, out = answer(press(svc, [name]))
    assert code == 200 and out["message"]["level"] == "success", out
    return token_of(shop, name.replace("%", ""))


def latte(**kw):
    return dict({"item_code": "LATTE", "qty": 1, "options": ["OAT"]}, **kw)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.shop = F.FakeTenant(codes=[F.code("GOR-CODE-00001"), F.code("GOR-CODE-00002", kind="Kiosk",
                                                                          kiosk_name="By the door")])
        self.clock = Clock()
        self.svc = service(self.shop, self.clock)

    # ── Make code ──
    def test_c1_an_unsigned_or_wrongly_signed_press_is_refused(self):
        self.assertEqual(answer(press(self.svc, ["GOR-CODE-00001"], secret="wrong"))[0], 401)
        self.assertEqual(answer(press(self.svc, ["GOR-CODE-00001"], ts=time.time() - 3600))[0], 401)
        self.assertEqual(self.shop.calls, [])

    def test_c2_make_code_writes_a_signed_link_its_qr_and_what_it_was_made_for(self):
        t = made(self.shop, self.svc)
        c = self.shop.codes["GOR-CODE-00001"]
        self.assertEqual(c["number"], 1)
        self.assertTrue(c["link"].startswith(F.PAGE + "/#s=" + F.SITE + "&t="))
        self.assertEqual(gor.code_of(F.SITE, t.replace("%2E", "."), [F.SECRET.encode()]), ("GOR-CODE-00001", 1))
        self.assertTrue(c["qr"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual(c["made_for"], "Table|Bistro - BC|FP-T12")

    def test_c3_make_code_again_stops_the_old_card(self):
        old = made(self.shop, self.svc)
        self.assertEqual(guest(self.svc, "/gor/menu", old)[1]["state"], "open")
        new = made(self.shop, self.svc)
        self.assertEqual(self.shop.codes["GOR-CODE-00001"]["number"], 2)
        self.clock.t += app.CODE_KEEP_S                                  # a copy that read the old code keeps it this long
        self.assertEqual(guest(self.svc, "/gor/menu", old), (404, {"state": "unknown"}))
        self.assertEqual(guest(self.svc, "/gor/menu", new)[1]["state"], "open")

    def test_c4_a_table_not_on_the_floor_and_a_nameless_kiosk_get_no_code(self):
        self.shop.codes["GOR-CODE-00001"]["place"] = "FP-GONE"
        self.shop.codes["GOR-CODE-00002"]["kiosk_name"] = " "
        code, out = answer(press(self.svc, ["GOR-CODE-00001", "GOR-CODE-00002"]))
        self.assertEqual(out["message"]["level"], "warning")
        self.assertIn("not an active table", out["message"]["body"])
        self.assertIn("name the kiosk", out["message"]["body"])
        self.assertEqual(self.shop.codes["GOR-CODE-00001"]["number"], 0)

    def test_c5_a_code_changed_a_moment_ago_is_not_overwritten(self):
        self.shop.stale_code = 1
        out = answer(press(self.svc, ["GOR-CODE-00001"]))[1]
        self.assertIn("changed a moment ago", out["message"]["body"])
        self.assertEqual(self.shop.codes["GOR-CODE-00001"]["number"], 0)

    def test_c6_a_press_on_another_record_type_is_refused_before_anything_is_read(self):
        self.assertEqual(answer(press(self.svc, ["GOR-CODE-00001"], doctype="PP GOR Settings"))[0], 400)
        self.assertEqual(self.shop.calls, [])

    # ── the guest's link ──
    def test_g1_a_forged_or_edited_link_is_refused_before_the_shop_is_read(self):
        t = made(self.shop, self.svc)
        self.shop.calls.clear()
        record, number, sig = t.replace("%2E", ".").rsplit(".", 2)
        for bad in (f"GOR-CODE-00002.{number}.{sig}", f"{record}.9.{sig}", f"{record}.{number}.{'A' * 22}", "", "x" * 300):
            self.assertEqual(guest(self.svc, "/gor/menu", bad), (404, {"state": "unknown"}), bad)
        self.assertEqual(answer(self.svc.handle("POST", "/gor/menu", {}, json.dumps({"s": "other.example.com", "t": t}).encode())),
                         (404, {"state": "unknown"}))
        self.assertEqual(self.shop.calls, [])

    def test_g2_a_code_whose_table_changed_since_it_was_made_is_refused(self):
        t = made(self.shop, self.svc)
        self.shop.codes["GOR-CODE-00001"]["place"] = F.T14
        self.clock.t += app.CODE_KEEP_S
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()]), (404, {"state": "unknown"}))
        self.assertEqual(self.shop.checks, {})

    def test_g3_the_stores_switch_off_answers_ask_staff(self):
        t = made(self.shop, self.svc)
        self.shop.settings[F.CO]["stores"][0]["tables_on"] = 0
        self.clock.t += app.CODE_KEEP_S
        code, out = guest(self.svc, "/gor/menu", t)
        self.assertEqual((code, out["state"], out["say"]), (200, "closed", "ask_staff"))

    # ── the menu ──
    def test_m1_the_menu_is_the_registers_groups_dishes_choices_and_prices(self):
        t = made(self.shop, self.svc)
        code, out = guest(self.svc, "/gor/menu", t)
        self.assertEqual((code, out["state"], out["where"], out["currency"]), (200, "open", "Table 12", "EUR"))
        self.assertEqual([s["group"] for s in out["menu"]], ["Drinks", "Mains"])
        dishes = gor.dishes_of(out["menu"])
        self.assertNotIn("OAT", dishes)                                  # sold only as a choice
        latte_ = dishes["LATTE"]
        self.assertEqual(latte_["price"], 3.2)
        milk = {c["code"]: c["price"] for c in latte_["groups"][0]["choices"]}
        self.assertEqual(milk, {"OAT": 0.6, "COW": 0.0})                 # the row's Amount, else the list price
        self.assertEqual(latte_["groups"][1]["choices"][0]["price"], 0.4)  # the list price less the row's 50%
        bacon = [c for c in dishes["BURGER"]["groups"][0]["choices"] if c["code"] == "BACON"][0]
        self.assertEqual(bacon["price"], 1.0)                             # 1.50 less 0.50
        self.assertEqual((out["most_lines"], out["most_qty"]), (10, 10))

    def test_m2_a_register_with_no_menu_groups_answers_ask_staff(self):
        self.shop.register["item_groups"] = []
        t = made(self.shop, self.svc)
        self.assertEqual(guest(self.svc, "/gor/menu", t)[1]["say"], "ask_staff")

    def test_m3_the_menu_is_kept_two_minutes(self):
        t = made(self.shop, self.svc)
        guest(self.svc, "/gor/menu", t)
        n = self.shop.calls.count("GET POS Profile")
        guest(self.svc, "/gor/menu", t)
        self.assertEqual(self.shop.calls.count("GET POS Profile"), n)

    # ── an order at a table ──
    def test_o1_no_bill_at_the_table_opens_one_and_adds_the_lines_unsent_under_the_course(self):
        t = made(self.shop, self.svc)
        code, out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte(note="extra hot\n<b>"), {"item_code": "SALAD", "qty": 2}])
        self.assertEqual((code, out["state"], out["say"]), (200, "sent", "sent_table"))
        (chk,) = self.shop.checks.values()
        self.assertEqual((chk["place"], chk["source_ref"]), (F.T12, "GOR-CODE-00001"))
        self.assertEqual([ln["item_code"] for ln in chk["lines"]], ["LATTE", "SALAD"])
        self.assertEqual({ln["course"] for ln in chk["lines"]}, {"Guest order"})
        self.assertEqual(chk["lines"][0]["options"], [{"item_code": "OAT", "option_group": "Milk"}])
        self.assertEqual(chk["lines"][0]["note"], "extra hot <b>")
        opened = [s for s in self.shop.sent if isinstance(s, dict) and "pos_profile" in s][0]
        self.assertEqual((opened["store"], opened["pos_profile"], opened["source"]), (F.STORE, F.REG, "guest_ordering"))
        self.assertNotEqual(opened["key"], ORDER)                          # the door's key is made from the page's

    def test_o2_one_bill_at_the_table_gets_the_lines(self):
        self.shop.checks["CHK-SRV"] = {"check": "CHK-SRV", "place": F.T12, "lines": [{"item_code": "WATER"}]}
        t = made(self.shop, self.svc)
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]["state"], "sent")
        self.assertEqual(list(self.shop.checks), ["CHK-SRV"])
        self.assertEqual(len(self.shop.checks["CHK-SRV"]["lines"]), 2)
        self.assertNotIn("CALL check_open", self.shop.calls)

    def test_o3_two_bills_at_the_table_are_refused_and_nothing_is_written(self):
        for c in ("CHK-A", "CHK-B"):
            self.shop.checks[c] = {"check": c, "place": F.T12, "lines": []}
        t = made(self.shop, self.svc)
        out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"]), ("refused", "many_bills"))
        self.assertEqual([c["lines"] for c in self.shop.checks.values()], [[], []])

    def test_o4_a_retry_after_a_lost_answer_opens_and_adds_once(self):
        t = made(self.shop, self.svc)
        self.shop.lose = {"check_open": 1}
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()]), (503, {"state": "unavailable"}))
        self.clock.t += gor.SPACING_S
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]["state"], "sent")
        self.shop.lose = {"check_add_lines": 1}
        self.clock.t += gor.SPACING_S
        k2 = "1f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a"
        self.assertEqual(guest(self.svc, "/gor/order", t, key=k2, lines=[latte()])[0], 503)
        self.clock.t += gor.SPACING_S
        self.assertEqual(guest(self.svc, "/gor/order", t, key=k2, lines=[latte()])[1]["state"], "sent")
        (chk,) = self.shop.checks.values()
        self.assertEqual(len(chk["lines"]), 2)

    def test_o5_one_order_a_table_every_fifteen_seconds(self):
        t = made(self.shop, self.svc)
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]["state"], "sent")
        k2 = "2f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a"
        out = guest(self.svc, "/gor/order", t, key=k2, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"]), ("wait", "wait"))
        self.clock.t += gor.SPACING_S + 0.1
        self.assertEqual(guest(self.svc, "/gor/order", t, key=k2, lines=[latte()])[1]["state"], "sent")

    def test_o6_a_retry_of_lines_since_moved_says_it_was_sent_once(self):
        t = made(self.shop, self.svc)
        self.shop.checks["CHK-SRV"] = {"check": "CHK-SRV", "place": F.T12, "lines": []}
        guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])
        self.shop.checks.pop("CHK-SRV")                                 # paid at the till since
        self.clock.t += gor.SPACING_S
        out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"]), ("refused", "sent_twice"))

    def test_o7_the_apps_set_up_refused_by_the_door_answers_ask_staff(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("check_open", "TableServiceOffError", 417)
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]["say"], "ask_staff")

    def test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits(self):
        t = made(self.shop, self.svc)
        bad = [[], [{"item_code": "OAT"}], [{"item_code": "NOPE"}], [latte(qty=11)], [latte(qty=0)], [latte(qty="2")],
               [latte(qty=1.5)], [latte(options=[])], [latte(options=["OAT", "COW"])], [latte(options=["OAT", "OAT"])],
               [latte(options=["OAT", "CHEESE"])], [latte(options=["OAT", "SHOT", "SHOT"])], [latte()] * 11, "x"]
        for i, lines in enumerate(bad):
            self.clock.t += gor.SPACING_S
            out = guest(self.svc, "/gor/order", t, key=f"{ORDER[:-2]}{i:02d}", lines=lines)[1]
            self.assertEqual(out["state"], "refused", lines)
        self.assertEqual(self.shop.checks, {})

    def test_o9_a_key_that_is_not_a_fresh_value_is_refused(self):
        t = made(self.shop, self.svc)
        for k in ("", "short", "x" * 70, "../../etc", None, 7):
            self.assertEqual(guest(self.svc, "/gor/order", t, key=k, lines=[latte()]), (400, {"state": "unknown"}))
        self.assertEqual(self.shop.checks, {})

    def test_o10_a_bill_being_paid_takes_no_guest_order(self):
        self.shop.checks["CHK-PAY"] = {"check": "CHK-PAY", "place": F.T12, "lines": [], "paying": 1}
        t = made(self.shop, self.svc)
        out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"]), ("refused", "paying"))
        self.assertEqual(self.shop.checks["CHK-PAY"]["lines"], [])

    def test_o11_one_order_a_table_even_with_two_cards_on_it(self):
        self.shop.codes["GOR-CODE-00003"] = F.code("GOR-CODE-00003")      # a second card at the same table
        t1, t3 = made(self.shop, self.svc), made(self.shop, self.svc, "GOR-CODE-00003")
        self.assertEqual(guest(self.svc, "/gor/order", t1, key=ORDER, lines=[latte()])[1]["state"], "sent")
        k2 = "3f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a"
        self.assertEqual(guest(self.svc, "/gor/order", t3, key=k2, lines=[latte()])[1]["state"], "wait")
        self.assertEqual(len(self.shop.checks), 1)

    def test_o12_a_body_the_page_never_sends_is_refused_and_nothing_is_written(self):
        t = made(self.shop, self.svc)
        for i, lines in enumerate(([{"item_code": ["LATTE"]}], [latte(options=[{"a": 1}])], [latte(options=[["OAT"]])],
                                   [{"item_code": {"x": 1}}])):
            self.clock.t += gor.SPACING_S
            code, out = guest(self.svc, "/gor/order", t, key=f"{ORDER[:-2]}{i:02d}", lines=lines)
            self.assertEqual((code, out["state"]), (200, "refused"), lines)
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()], s=["x"])[0], 400)
        self.assertEqual(self.shop.checks, {})

    def test_o13_a_table_switched_off_after_the_floor_read_is_ask_staff_not_sent(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("check_open", "CheckRequestError", 417)
        out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"]), ("closed", "ask_staff"))

    def test_m4_a_gift_card_in_a_menu_group_is_not_on_the_menu(self):
        t = made(self.shop, self.svc)
        self.assertNotIn("GIFT", gor.dishes_of(guest(self.svc, "/gor/menu", t)[1]["menu"]))

    def test_m5_a_menu_the_time_budget_cut_prices_only_what_it_missed_soon_after(self):
        t = made(self.shop, self.svc)
        self.shop.slow, self.shop.tick = {"BURGER"}, self.clock     # the first price (by name) takes the budget
        real, app.PRICERS = app.PRICERS, 1
        try:
            first = gor.dishes_of(guest(self.svc, "/gor/menu", t)[1]["menu"])
            self.assertEqual((first["BURGER"]["price"], first["SALAD"]["price"]), (11.0, None))
            self.shop.slow = set()
            asked = len([c for c in self.shop.calls if c == "CALL get_item_details"])
            self.clock.t += app.MENU_SHORT_S
            second = gor.dishes_of(guest(self.svc, "/gor/menu", t)[1]["menu"])
        finally:
            app.PRICERS = real
        self.assertEqual((second["BURGER"]["price"], second["SALAD"]["price"]), (11.0, 7.5))
        again = len([c for c in self.shop.calls if c == "CALL get_item_details"]) - asked
        self.assertEqual(again, 4)                                    # SALAD, LATTE, COW, SHOT: never BURGER again
        self.clock.t += app.MENU_SHORT_S
        guest(self.svc, "/gor/menu", t)
        self.assertEqual(len([c for c in self.shop.calls if c == "CALL get_item_details"]) - asked, 4)   # full: 2 minutes

    def test_m7_a_flood_on_a_replaced_card_reads_the_retailer_once_a_copy(self):
        old = made(self.shop, self.svc)
        made(self.shop, self.svc)
        self.clock.t += app.CODE_KEEP_S
        self.assertEqual(guest(self.svc, "/gor/menu", old), (404, {"state": "unknown"}))
        before = list(self.shop.calls)
        for _ in range(50):
            self.assertEqual(guest(self.svc, "/gor/menu", old)[0], 404)
        self.assertEqual(self.shop.calls, before)

    def test_m6_a_flood_of_calls_on_one_code_reads_the_retailer_once_a_copy(self):
        t = made(self.shop, self.svc)
        guest(self.svc, "/gor/menu", t)
        before = list(self.shop.calls)
        for _ in range(50):
            guest(self.svc, "/gor/menu", t)
        self.assertEqual(self.shop.calls, before)

    def test_c7_a_link_too_long_for_a_qr_code_is_said_and_nothing_written(self):
        svc = app.Service({"IVN_SHOP_URL": f"https://{F.SITE}", "IVN_SHOP_KEY": "k:s", "IVN_CODE_SECRET": F.SECRET,
                           "GOR_PAGE_URL": "https://" + "p" * 150 + ".example.app"}, tenant=self.shop, now=self.clock)
        out = answer(press(svc, ["GOR-CODE-00001"]))[1]
        self.assertIn("too long for a QR code", out["message"]["body"])
        self.assertEqual(self.shop.codes["GOR-CODE-00001"]["number"], 0)

    # ── the kiosk ──
    def test_k1_a_kiosk_order_opens_a_tab_named_by_its_code_and_a_retry_opens_none(self):
        t = made(self.shop, self.svc, "GOR-CODE-00002")
        out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"], out["code"]), ("sent", "sent_kiosk", gor.kiosk_code(ORDER, F.SECRET.encode())))
        (chk,) = self.shop.checks.values()
        self.assertEqual((chk["place"], chk["label"], chk["covers"]), (None, f"Kiosk {out['code']}", 1))
        self.clock.t += gor.SPACING_S
        self.assertEqual(guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]["code"], out["code"])
        self.assertEqual(len(self.shop.checks), 1)
        self.assertEqual(len(chk["lines"]), 1)

    def test_k2_the_stores_kiosk_switch_off_answers_order_at_the_counter(self):
        self.shop.settings[F.CO]["stores"][0]["kiosk_on"] = 0
        t = made(self.shop, self.svc, "GOR-CODE-00002")
        self.assertEqual(guest(self.svc, "/gor/menu", t)[1]["say"], "ask_staff_kiosk")

    # ── every call ──
    def test_e1_the_page_is_served_with_its_own_rules(self):
        code, body, hdrs = self.svc.handle("GET", "/", {}, b"")
        self.assertEqual(code, 200)
        csp = hdrs["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(hdrs["Referrer-Policy"], "no-referrer")
        html = body.decode()
        self.assertNotIn("<script>", html)
        self.assertNotRegex(html, r"\son[a-z]+=")
        self.assertEqual(self.svc.handle("GET", "/../app.py", {}, b"")[0], 404)

    def test_e5_a_kiosk_keeps_no_order_key_in_the_browser_and_clears_itself_after_the_last_touch(self):
        js = open(os.path.join(os.path.dirname(HERE), "service", "page.js")).read()
        self.assertIn("function keptKey(sig) {\n    if (kiosk()) { return null; }", js)
        self.assertIn("function keepKey(sig, k) {\n    if (kiosk()) { return; }", js)
        self.assertIn('["pointerdown", "keydown", "input"]', js)            # the idle clock restarts on every touch
        self.assertIn("if (busy || lost) { return resetLater(ms); }", js)   # never under a retry

    def test_e4_the_page_sets_every_word_as_text_never_as_markup(self):
        js = open(os.path.join(os.path.dirname(HERE), "service", "page.js")).read()
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "setAttribute(\"on"):
            self.assertNotIn(sink, js, sink)
        self.assertIn("textContent", js)

    def test_c8_the_apps_user_refused_by_the_retailer_is_said_in_words(self):
        self.shop.refuse = ("GET PP GOR Code", 403)
        out = answer(press(self.svc, ["GOR-CODE-00001"]))[1]
        self.assertEqual((out["message"]["level"], out["message"]["body"]), ("warning", app.REFUSED))

    def test_o14_a_dish_the_door_refuses_is_said_to_ask_staff(self):
        t = made(self.shop, self.svc)
        self.shop.door_refuse = ("check_add_lines", "ItemRefusedError", 417)
        out = guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte()])[1]
        self.assertEqual((out["state"], out["say"]), ("refused", "item_refused"))

    def test_e2_a_page_call_over_its_size_is_refused(self):
        self.assertEqual(answer(self.svc.handle("POST", "/gor/order", {}, b"{" + b" " * gor.PAGE_BODY_MAX + b"}"))[0], 413)

    def test_e3_no_line_the_service_sends_carries_a_price(self):
        t = made(self.shop, self.svc)
        guest(self.svc, "/gor/order", t, key=ORDER, lines=[latte(), {"item_code": "BURGER", "options": ["BACON"]}])
        for s in self.shop.sent:
            for ln in (s or {}).get("lines") or []:
                self.assertFalse(set(ln) - {"item_code", "qty", "options", "note", "course"}, ln)


if __name__ == "__main__":
    unittest.main()
