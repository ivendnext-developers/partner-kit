"""S64's service against a stand-in shop (``fakeshop.py``): the Make link press, the station's four calls (the board, a
tag, undo, Cart full) and the Work out press. Cart full is the stock code: a double tap, a retry after a lost answer and
a failure between the two entries each post nothing twice; a taken-back tag is never received; the receipt's quantity of
each item is the cart's tags'.

    python3 -m unittest discover -s samples/s64_production_station/tests -p 'test_*.py'
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "service"), os.path.dirname(HERE)]
import app  # noqa: E402
import fakeshop as F  # noqa: E402
import pst  # noqa: E402

UTC = datetime.timezone.utc


class Clock:
    def __init__(self, when=datetime.datetime(2026, 11, 4, 14, 30, tzinfo=UTC)):
        self.t = when.timestamp()

    def __call__(self):
        return self.t


def service(shop, clock):
    conf = {"IVN_SHOP_URL": f"https://{F.SITE}", "IVN_SHOP_KEY": "k:s", "IVN_LINK_SECRET": F.SECRET,
            "IVN_WORK_SECRET": F.WORK_SECRET, "PST_PAGE_URL": F.PAGE}
    return app.Service(conf, tenant=shop, now=clock, clock=clock)


def signed(svc, route, doctype, names, secret, ts):
    raw = json.dumps({"point": "desk_action/1", "context": {"v": 1, "user": "lead@thrift", "lang": "en",
                                                            "records": [{"doctype": doctype, "name": n} for n in names]}}).encode()
    ts = str(int(ts))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    code, body, _ = svc.handle("POST", route, {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw)
    return code, json.loads(body)


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.shop = F.Shop(self.clock)
        self.svc = service(self.shop, self.clock)
        code, a = signed(self.svc, "/pst/link", "PP PST Station", ["PST-S-00001"], F.SECRET, self.clock())
        self.assertEqual(code, 200, a)
        self.token = self.shop.db["PP PST Station"]["PST-S-00001"]["link"].split("&t=")[1]

    def call(self, path, **extra):
        code, body, _ = self.svc.handle("POST", path, {}, json.dumps(dict({"s": F.SITE, "t": self.token}, **extra)).encode())
        return code, json.loads(body)

    def tag(self, price=4.99, category="Women's tops", worker="Ana"):
        code, a = self.call("/pst/tag", worker=worker, category=category, price=price)
        self.assertEqual(code, 200, a)
        return a

    def later(self, seconds):
        self.clock.t += seconds


class MakeLink(Base):
    def test_a_press_writes_a_signed_link_with_a_new_number(self):
        st = self.shop.db["PP PST Station"]["PST-S-00001"]
        self.assertEqual(st["number"], 1)
        self.assertTrue(st["link"].startswith(F.PAGE + "/#s=thrift.example.com&t=PST-S-00001.1."))
        self.assertEqual(st["made_for"], pst.made_for(st))

    def test_a_link_made_again_stops_the_old_one(self):
        old = self.token
        signed(self.svc, "/pst/link", "PP PST Station", ["PST-S-00001"], F.SECRET, self.clock())
        self.later(app.STATION_KEEP_S + 1)
        self.assertEqual(self.call("/pst/board"), (404, {"state": "unknown"}))
        self.token = self.shop.db["PP PST Station"]["PST-S-00001"]["link"].split("&t=")[1]
        self.assertNotEqual(old, self.token)
        self.assertEqual(self.call("/pst/board")[1]["state"], "open")

    def test_a_press_signed_with_another_secret_or_too_old_is_refused(self):
        self.assertEqual(signed(self.svc, "/pst/link", "PP PST Station", ["PST-S-00001"], F.WORK_SECRET, self.clock())[0], 401)
        self.assertEqual(signed(self.svc, "/pst/link", "PP PST Station", ["PST-S-00001"], F.SECRET, self.clock() - 1000)[0], 401)
        self.assertEqual(signed(self.svc, "/pst/work", "PP PST Report", ["PST-R-1"], F.SECRET, self.clock())[0], 401)

    def test_a_signed_test_call_is_answered_without_the_handler(self):
        raw = b"{}"
        ts = str(int(self.clock()))
        sig = base64.b64encode(hmac.new(F.SECRET.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        n = len(self.shop.calls)
        code, body, _ = self.svc.handle("POST", "/pst/link", {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig,
                                                              "X-iVendNext-Test": "1"}, raw)
        self.assertEqual((code, json.loads(body)), (200, {"test": "ok", "point": "link"}))
        self.assertEqual(len(self.shop.calls), n)
        self.assertEqual(self.svc.handle("POST", "/pst/nothing", {"X-iVendNext-Test": "1"}, raw)[0], 404)


class Board(Base):
    def test_the_board_shows_the_active_workers_the_price_points_this_weeks_colour_and_the_cart(self):
        self.tag()
        code, a = self.call("/pst/board")
        self.assertEqual(code, 200)
        self.assertEqual((a["title"], a["colour"], a["workers"], a["cart"], a["currency"]), ("Station 3", "Blue", ["Ana", "Ben"], 1, "USD"))
        self.assertEqual(a["categories"], [{"name": "Women's tops", "prices": [4.99, 6.99, 19.99]},
                                           {"name": "Men's shirts", "prices": [6.99]}])
        self.assertEqual([p["label"] for p in a["places"]], ["Store 12", "Outlet", "Keep here"])
        self.assertEqual(a["tag"], {"width_mm": 50, "height_mm": 30})

    def test_the_leads_colour_for_today_is_told_as_todays(self):
        s = self.shop.db["PP PST Settings"][F.COMPANY]
        s["day_colour"], s["day_colour_on"] = "Green", "2026-11-04"
        self.later(app.STATION_KEEP_S + 1)
        a = self.call("/pst/board")[1]
        self.assertEqual((a["colour"], a["one_day"]), ("Green", True))
        self.later(86400)
        self.assertEqual((self.call("/pst/board")[1]["colour"], self.call("/pst/board")[1]["one_day"]), ("Blue", False))

    def test_next_week_is_the_next_colour(self):
        self.later(7 * 86400)
        self.assertEqual(self.call("/pst/board")[1]["colour"], "Green")

    def test_a_bad_link_reads_nothing(self):
        n = len(self.shop.calls)
        self.token = self.token[:-2] + "xx"
        self.assertEqual(self.call("/pst/board"), (404, {"state": "unknown"}))
        self.assertEqual(len(self.shop.calls), n)

    def test_no_right_on_the_sites_time_zone_is_said(self):
        self.shop.settings_rights = False
        self.assertEqual(self.call("/pst/board"), (200, {"state": "not_set_up"}))


class Tagging(Base):
    def test_a_tap_writes_one_tag_with_the_settings_price_the_weeks_colour_and_the_engines_barcode(self):
        a = self.tag(price="19.99")
        self.assertEqual(a["state"], "tagged")
        (t,) = self.shop.tags()
        self.assertEqual((t["item"], t["colour"], t["week_start"], t["price"], t["quantity"], t["worker"], t["station"]),
                         ("TOPS-BLU", "Blue", "2026-11-02", 19.99, 1, "Ana", "PST-S-00001"))
        self.assertEqual((t["barcode"], t["tagged_on"], t["hour"], t["void"]), ("2970102019990", "2026-11-04", 14, 0))
        self.assertEqual(a["tag"], {"name": t["name"], "price": 19.99, "category": "Women's tops", "colour": "Blue",
                                    "barcode": "2970102019990"})

    def test_the_day_and_hour_are_the_sites_own(self):
        self.clock.t = datetime.datetime(2026, 11, 9, 2, 0, tzinfo=UTC).timestamp()   # 21:00 on the 8th in New York
        self.shop.db["System Settings"]["System Settings"]["time_zone"] = "America/New_York"
        self.svc = service(self.shop, self.clock)
        self.tag()
        (t,) = self.shop.tags()
        self.assertEqual((t["tagged_on"], t["hour"], t["colour"], t["week_start"]), ("2026-11-08", 21, "Blue", "2026-11-02"))

    def test_a_site_with_no_time_zone_set_keeps_its_own_default_zones_day(self):
        self.clock.t = datetime.datetime(2026, 11, 8, 20, 0, tzinfo=UTC).timestamp()   # 01:30 on the 9th there
        self.shop.db["System Settings"]["System Settings"]["time_zone"] = ""
        self.svc = service(self.shop, self.clock)
        self.tag(category="Women's tops")
        (t,) = self.shop.tags()
        self.assertEqual((t["tagged_on"], t["hour"], t["colour"]), ("2026-11-09", 1, "Green"))

    def test_a_second_tag_at_a_price_already_read_back_asks_the_engine_nothing(self):
        self.tag()
        n = sum(1 for c in self.shop.calls if c[0] == "engine")
        self.tag()
        self.assertEqual(sum(1 for c in self.shop.calls if c[0] == "engine"), n)
        self.assertEqual(n, 2)                      # the encoder, then the reader, once

    def test_the_leads_colour_for_one_day(self):
        s = self.shop.db["PP PST Settings"][F.COMPANY]
        s["day_colour"], s["day_colour_on"] = "Green", "2026-11-04"
        self.later(app.STATION_KEEP_S + 1)
        self.tag()
        (t,) = self.shop.tags()
        self.assertEqual((t["item"], t["colour"], t["week_start"]), ("TOPS-GRN", "Green", "2026-11-04"))

    def test_each_refusal_writes_nothing_and_says_what_to_do(self):
        cases = [(dict(worker="Cy"), "no_worker"), (dict(worker="Zed"), "no_worker"), (dict(price=5.00), "no_price"),
                 (dict(price=19.99, category="Men's shirts"), "no_price"), (dict(category="Hats"), "no_price"),
                 (dict(price="nine"), "no_price")]
        for args, why in cases:
            self.assertEqual(self.tag(**args), {"state": "refused", "why": why}, args)
        self.assertEqual(self.shop.tags(), [])

    def test_no_item_of_this_weeks_colour(self):
        self.shop.db["Item"]["TOPS-BLU"]["pp_pst_tag_colour"] = "Pink"
        self.assertEqual(self.tag(), {"state": "refused", "why": "no_item", "colour": "Blue", "category": "Women's tops"})

    def test_an_item_with_no_barcode_mask(self):
        self.shop.db["Item"]["TOPS-BLU"]["custom_barcode_mask"] = ""
        self.assertEqual(self.tag(), {"state": "refused", "why": "no_mask", "item": "TOPS-BLU"})

    def test_a_label_the_engine_cannot_make(self):
        self.shop.db["Item"]["TOPS-BLU"]["barcodes"] = []
        self.assertEqual(self.tag(), {"state": "refused", "why": "no_label", "item": "TOPS-BLU"})
        self.assertEqual(self.shop.tags(), [])

    def test_a_site_whose_labels_carry_a_price_their_scan_does_not_read_back_prints_nothing(self):
        self.shop.old_engine = True                 # 19.99 * 100 is 1998.9999999999998: it reads back as 999.98
        self.assertEqual(self.tag(price=19.99), {"state": "refused", "why": "too_old", "item": "TOPS-BLU"})
        self.assertEqual(self.tag(price=4.99)["state"], "tagged")     # a price the old engine wrote right still prints
        self.assertEqual(len(self.shop.tags()), 1)

    def test_undo_takes_back_the_last_tag_of_this_cart_only(self):
        self.tag(4.99)
        self.tag(6.99)
        code, a = self.call("/pst/undo")
        self.assertEqual((a["state"], a["tag"]["price"]), ("undone", 6.99))
        self.assertEqual(sorted((t["price"], t["void"]) for t in self.shop.tags()), [(4.99, 0), (6.99, 1)])
        self.call("/pst/undo")
        self.assertEqual(self.call("/pst/undo")[1], {"state": "refused", "why": "no_undo"})


class Carts(Base):
    def stock(self, item, wh):
        return self.shop.stock.get((item, wh), 0)

    def fill(self):
        for p in (4.99, 4.99, 6.99, 19.99):
            self.tag(p)
        self.tag(6.99, "Men's shirts", "Ben")
        self.tag(6.99, "Men's shirts", "Ben")
        self.call("/pst/undo")                      # the last shirt taken back: never received

    def test_cart_full_receives_at_no_value_into_the_room_then_moves_the_same_lines_to_the_store(self):
        self.fill()
        code, a = self.call("/pst/cart", warehouse=F.STORE)
        self.assertEqual((code, a["state"], a["pieces"], a["place"], a["kept"]), (200, "sent", 5, "Store 12", False))
        (rc,), (tr,) = self.shop.entries("Material Receipt"), self.shop.entries("Material Transfer")
        self.assertEqual(sorted((i["item_code"], i["qty"]) for i in rc["items"]), [("SHIRT-BLU", 1), ("TOPS-BLU", 4)])
        self.assertTrue(all(i["basic_rate"] == 0 and i["allow_zero_valuation_rate"] == 1 and i["conversion_factor"] == 1
                            and i["uom"] == "Nos" and i["t_warehouse"] == F.ROOM for i in rc["items"]))
        self.assertEqual((rc["pp_pst_cart"], tr["pp_pst_cart"], rc["docstatus"], tr["docstatus"]), (a["cart"], a["cart"], 1, 1))
        self.assertEqual([(i["item_code"], i["qty"], i["s_warehouse"], i["t_warehouse"]) for i in tr["items"]],
                         [("SHIRT-BLU", 1, F.ROOM, F.STORE), ("TOPS-BLU", 4, F.ROOM, F.STORE)])
        self.assertEqual((self.stock("TOPS-BLU", F.STORE), self.stock("SHIRT-BLU", F.STORE), self.stock("TOPS-BLU", F.ROOM)), (4, 1, 0))
        self.assertEqual(self.shop.values.get(("TOPS-BLU", F.ROOM)), 0)
        cart = self.shop.db["PP PST Cart"][a["cart"]]
        self.assertEqual((cart["state"], cart["receipt"], cart["transfer"], cart["open_for"], cart["pieces"]),
                         ("Sent", rc["name"], tr["name"], None, 5))
        live = [t for t in self.shop.tags() if not t["void"]]
        self.assertTrue(all(t["cart"] == a["cart"] for t in live))
        self.assertEqual([t.get("cart") for t in self.shop.tags() if t["void"]], [None])    # the taken-back tag stays out
        self.assertEqual(sum(i["qty"] for i in rc["items"]), len(live))

    def test_a_double_tap_posts_nothing_twice(self):
        self.fill()
        first = self.call("/pst/cart", warehouse=F.STORE)[1]
        again = self.call("/pst/cart", warehouse=F.STORE)[1]
        self.assertEqual(again, first)              # the cart just sent, told again
        self.later(app.LEASE_S + 1)
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1], {"state": "refused", "why": "empty"})
        self.assertEqual((len(self.shop.entries("Material Receipt")), len(self.shop.entries("Material Transfer"))), (1, 1))

    def test_a_tap_while_another_posts_this_stations_cart_is_told_busy(self):
        self.fill()
        self.shop.fail["insert:Stock Entry"] = (0, "refuse")        # the first call stops after making the cart
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[0], 503)
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1], {"state": "busy"})
        self.assertEqual(self.shop.entries(), [])

    def test_two_calls_at_once_make_one_cart(self):
        self.fill()
        self.shop.put("PP PST Cart", "PST-C-09999", station="PST-S-00001", state="Sent", destination=F.STORE, open_for="PST-S-00001")
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1], {"state": "busy"})   # the unique open cart refused
        self.assertEqual(self.shop.entries(), [])

    def test_a_retry_after_a_lost_answer_takes_the_receipt_made_and_posts_it_once(self):
        self.fill()
        self.shop.fail["insert:Stock Entry:lose"] = (0, "lose")     # the receipt is made; its answer never arrives
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE), (503, {"state": "unavailable"}))
        self.assertEqual(len(self.shop.entries("Material Receipt")), 1)
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1], {"state": "busy"})   # within the minute: wait
        self.tag(4.99)                              # a tag made meanwhile goes on the next cart, not this one
        self.later(app.LEASE_S + 1)
        a = self.call("/pst/cart", warehouse=F.OUTLET)[1]           # the cart keeps its own place
        self.assertEqual((a["state"], a["pieces"], a["place"]), ("sent", 5, "Store 12"))
        self.assertEqual((len(self.shop.entries("Material Receipt")), len(self.shop.entries("Material Transfer"))), (1, 1))
        self.assertEqual((self.stock("TOPS-BLU", F.STORE), self.stock("TOPS-BLU", F.ROOM)), (4, 0))
        self.assertEqual(len(self.shop.tags(cart=None, void=0)), 1)
        self.assertEqual(self.call("/pst/board")[1]["cart"], 1)

    def test_a_failure_between_the_two_entries_leaves_the_cart_received_and_a_repeat_finishes_it(self):
        self.fill()
        self.shop.fail["insert:Stock Entry"] = (1, "refuse")        # the receipt posts, the transfer is refused
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[0], 503)
        (cart,) = self.shop.db["PP PST Cart"].values()
        self.assertEqual((cart["state"], self.stock("TOPS-BLU", F.ROOM)), ("Received", 4))
        self.later(app.LEASE_S + 1)
        a = self.call("/pst/cart", warehouse=F.STORE)[1]
        self.assertEqual(a["state"], "sent")
        self.assertEqual((len(self.shop.entries("Material Receipt")), len(self.shop.entries("Material Transfer"))), (1, 1))
        self.assertEqual((self.stock("TOPS-BLU", F.STORE), self.stock("TOPS-BLU", F.ROOM)), (4, 0))

    def test_a_lost_answer_after_the_transfer_posts_nothing_twice(self):
        self.fill()
        self.shop.fail["insert:Stock Entry:lose"] = (1, "lose")
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[0], 503)
        self.later(app.LEASE_S + 1)
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1]["state"], "sent")
        self.assertEqual((len(self.shop.entries("Material Receipt")), len(self.shop.entries("Material Transfer"))), (1, 1))
        self.assertEqual(self.stock("TOPS-BLU", F.STORE), 4)

    def test_a_cart_kept_in_the_room_is_received_only_and_the_next_cart_starts(self):
        self.fill()
        a = self.call("/pst/cart", warehouse=F.ROOM)[1]
        self.assertEqual((a["state"], a["kept"]), ("sent", True))
        self.assertEqual((len(self.shop.entries("Material Receipt")), len(self.shop.entries("Material Transfer"))), (1, 0))
        self.assertEqual(self.shop.db["PP PST Cart"][a["cart"]]["state"], "Received")
        self.tag()
        self.later(app.LEASE_S + 1)
        b = self.call("/pst/cart", warehouse=F.STORE)[1]
        self.assertEqual((b["state"], b["pieces"]), ("sent", 1))
        self.assertNotEqual(a["cart"], b["cart"])

    def test_an_empty_cart_and_a_place_not_listed_are_refused(self):
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1], {"state": "refused", "why": "empty"})
        self.tag()
        self.assertEqual(self.call("/pst/cart", warehouse="Elsewhere")[1], {"state": "refused", "why": "no_place"})
        self.assertEqual(self.shop.db.get("PP PST Cart", {}), {})

    def test_a_cart_whose_tags_were_all_taken_back_posts_nothing(self):
        self.tag()
        self.shop.fail["call:bulk_update"] = (0, "refuse")
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[0], 503)
        self.call("/pst/undo")
        self.later(app.LEASE_S + 1)
        self.assertEqual(self.call("/pst/cart", warehouse=F.STORE)[1], {"state": "refused", "why": "empty"})
        self.assertEqual(self.shop.entries(), [])


class WorkOut(Base):
    def setUp(self):
        super().setUp()
        self.shop.put("PP PST Report", "PST-R-00001", from_date="2026-11-04", to_date="2026-11-04", settings="")

    def press(self):
        code, a = signed(self.svc, "/pst/work", "PP PST Report", ["PST-R-00001"], F.WORK_SECRET, self.clock())
        self.assertEqual(code, 200, a)
        return a["message"]["body"], self.shop.db["PP PST Report"]["PST-R-00001"]

    def day(self):
        for p in (4.99, 6.99, 19.99):
            self.tag(p)
        self.later(3600)
        self.tag(4.99)
        self.tag(6.99, "Men's shirts", "Ben")
        self.tag(6.99, "Men's shirts", "Ben")
        self.call("/pst/undo")
        self.call("/pst/cart", warehouse=F.STORE)

    def test_the_rows_by_worker_add_up_to_the_tags_and_the_cart(self):
        self.day()
        body, r = self.press()
        self.assertEqual(r["worker_rows"], [
            {"day": "2026-11-04", "station": "PST-S-00001", "worker": "Ana", "pieces": 4, "hours": 2, "per_hour": 2.0},
            {"day": "2026-11-04", "station": "PST-S-00001", "worker": "Ben", "pieces": 1, "hours": 1, "per_hour": 1.0}])
        (rc,) = self.shop.entries("Material Receipt")
        self.assertEqual(sum(x["pieces"] for x in r["worker_rows"]), len(self.shop.tags(void=0)))
        self.assertEqual(sum(x["pieces"] for x in r["worker_rows"]), sum(i["qty"] for i in rc["items"]))
        self.assertEqual(self.svc.last_read, "grouped")
        self.assertTrue(body.startswith("2 worker rows and 1 colour row written. 2026-11-04 to 2026-11-04: 5 pieces"))

    def test_sell_through_reads_the_colours_items_in_the_stores_in_the_weeks_window(self):
        self.day()
        self.shop.sales += [("2026-11-05", F.STORE, "TOPS-BLU", 2), ("2026-11-06", F.OUTLET, "SHIRT-BLU", 1),
                            ("2026-11-05", F.STORE, "TOPS-GRN", 5), ("2026-11-05", F.ROOM, "TOPS-BLU", 9),
                            ("2026-11-20", F.STORE, "TOPS-BLU", 7)]
        self.later(3 * 86400)                       # today is the 7th: the window ends today, not on the 15th
        _, r = self.press()
        self.assertEqual(r["colour_rows"], [{"colour": "Blue", "week_start": "2026-11-02", "tagged": 5, "sold": 3.0,
                                             "sell_through": 60.0}])
        reports = [c for c in self.shop.calls if c[0] == "report"]
        self.assertEqual(sorted(c[2] for c in reports), sorted([F.STORE, F.OUTLET]))   # the room is no store
        self.assertTrue(all((c[3], c[4]) == ("2026-11-02", "2026-11-07") for c in reports))

    def test_a_shop_that_refuses_a_grouped_read_is_read_a_page_at_a_time_with_the_same_rows(self):
        self.day()
        _, grouped = self.press()
        rows = json.loads(json.dumps(grouped["worker_rows"]))
        self.shop.no_grouping = True
        _, paged = self.press()
        self.assertEqual(self.svc.last_read, "pages")
        self.assertEqual(paged["worker_rows"], rows)

    def test_a_misfilled_report_says_what_to_fix_and_reads_no_tag(self):
        r = self.shop.db["PP PST Report"]["PST-R-00001"]
        for frm, to, words in (("", "2026-11-04", "fill From and To"), ("2026-11-05", "2026-11-04", "fill From and To"),
                               ("2026-01-01", "2026-11-04", "at most 92 days")):
            r["from_date"], r["to_date"] = frm, to
            body, _ = self.press()
            self.assertIn(words, body)
        self.assertFalse(any(c[0] == "rows" and c[1] == "PP PST Tag" for c in self.shop.calls))

    def test_two_settings_records_and_none_named_asks_which(self):
        self.shop.put("PP PST Settings", "Other Co", company="Other Co")
        body, _ = self.press()
        self.assertIn("choose the settings", body)

    def test_a_refused_report_is_said_in_words(self):
        self.day()
        self.shop.fail["report"] = (0, "refuse")
        body, _ = self.press()
        self.assertIn("could not run POS Sale Report", body)


if __name__ == "__main__":
    unittest.main()
