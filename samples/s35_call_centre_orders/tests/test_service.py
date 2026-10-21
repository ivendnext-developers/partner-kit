"""S35's laptop tests: the real service on a local port, a stand-in for the shop's record API, presses signed exactly
as the shop signs them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s35_call_centre_orders/tests -p 'test_*.py'

On our test bench the real Desk button was pressed on real orders; these prove the service's own duties fast, and are
what the mutation canary turns RED."""

import base64
import copy
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import route  # noqa: E402

SECRET = "s35-test-secret"
F = "pp_cco_store"


def territories():
    """A district tree: Egypt › Cairo (its store) › Maadi (its own store), Heliopolis (none: Cairo's); Giza (none at all)."""
    return {"Egypt": {"parent_territory": "All Territories"}, "All Territories": {"parent_territory": ""},
            "Cairo": {"parent_territory": "Egypt", F: "Cairo Store - S"},
            "Maadi": {"parent_territory": "Cairo", F: "Maadi Store - S"},
            "Heliopolis": {"parent_territory": "Cairo"}, "Giza": {"parent_territory": "Egypt"}}


WAREHOUSES = {"Maadi Store - S": {"company": "Shop"}, "Cairo Store - S": {"company": "Shop"},
              "All Warehouses - S": {"company": "Shop", "is_group": 1}, "Old Store - S": {"company": "Shop", "disabled": 1},
              "Other Co Store - O": {"company": "Other Co"}}


def order(name="SO-0001", territory="Maadi", modified="2026-10-21 10:00:00.000001", docstatus=0):
    return {"name": name, "doctype": "Sales Order", "docstatus": docstatus, "territory": territory, "customer": "C1",
            "company": "Shop",
            "modified": modified, "set_warehouse": "Call Centre - S", "grand_total": 230.46, "rounded_total": 230.0,
            "items": [{"name": "row-1", "item_code": "A", "qty": 2.0, "rate": 100.0, "amount": 200.0, "warehouse": "Call Centre - S"},
                      {"name": "row-2", "item_code": "B", "qty": 1.0, "rate": 30.46, "amount": 30.46, "warehouse": "Call Centre - S"},
                      {"name": "row-3", "item_code": "D", "qty": 1.0, "rate": 0.0, "amount": 0.0, "warehouse": "Supplier - S",
                       "delivered_by_supplier": 1}]}


class FakeTenant:
    """The shop's record API: orders, territories, and the shop's refusal of a write whose ``modified`` is stale."""

    def __init__(self, orders=None, tree=None, refuse=None, refuse_write=None, edit_before_write=0, warehouses=None,
                 reprice=None, routed_before_write=None):
        self.orders = {o["name"]: o for o in (orders or [order()])}
        self.warehouses = warehouses if warehouses is not None else WAREHOUSES
        self.reprice = reprice      # {store: new grand total}: the store's own item tax re-rates the order on save
        self.routed_before_write = routed_before_write  # a store: another press routes the order between read and write
        self.tree, self.refuse, self.refuse_write = tree or territories(), refuse, refuse_write
        self.edit_before_write, self.writes, self.reads = edit_before_write, [], []
        self.clock = 0

    def order(self, name):
        if self.refuse:
            raise app.TenantError("GET -> HTTP %d" % self.refuse, self.refuse)
        if name not in self.orders:
            raise app.TenantError("GET -> HTTP 404", 404)
        self.reads.append(name)
        return copy.deepcopy(self.orders[name])

    def territory(self, name):
        if name not in self.tree:
            raise app.TenantError("GET -> HTTP 404", 404)
        return dict(self.tree[name], name=name)

    def warehouse(self, name):
        if name not in self.warehouses:
            raise app.TenantError("GET -> HTTP 404", 404)
        return dict(self.warehouses[name], name=name)

    def write(self, name, body):
        if self.routed_before_write:            # a double click: the other press's write lands first
            o = self.orders[name]
            o["set_warehouse"] = self.routed_before_write
            for ln in o["items"]:
                ln["warehouse"] = self.routed_before_write
            self.routed_before_write = None
            self._touch(name)
        if self.edit_before_write:              # someone saves the order between the service's read and its write
            self.edit_before_write -= 1
            self._touch(name)
        if self.refuse_write:
            raise app.TenantError("PUT -> HTTP %s" % self.refuse_write[0], *self.refuse_write)
        o = self.orders[name]
        if body.get("modified") != o["modified"]:
            raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
        self.writes.append((name, copy.deepcopy(body)))
        o.update({k: v for k, v in body.items() if k != "modified"})
        if len({ln.get("warehouse") for ln in o["items"]}) > 1:     # the shop's own rule on save: lines that differ
            o["set_warehouse"] = None                                # clear the header (reset_default_field_value)
        if self.reprice and o["set_warehouse"] in self.reprice:
            o["grand_total"] = o["rounded_total"] = self.reprice[o["set_warehouse"]]
        self._touch(name)
        return copy.deepcopy(o)

    def _touch(self, name):
        self.clock += 1
        self.orders[name]["modified"] = f"2026-10-21 10:00:{self.clock:02d}.000001"


def body(name="SO-0001", records=None, **extra):
    recs = records if records is not None else [{"doctype": "Sales Order", "name": name,
                                                 "fields": {"name": name, "territory": "Maadi"}}]
    ctx = {"v": 1, "action": "x", "label": "Send to store", "user": "agent@shop.example", "lang": "en", "records": recs,
           "inputs": {}, "idempotency_key": "key-0001-abcdef", **extra}
    return json.dumps({"point": "desk_action/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=SECRET, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tenant = FakeTenant()
        self.start()

    def start(self):
        self.svc = app.Service({"PP_POINT_SECRET": SECRET}, self.tenant)
        self.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.svc, log=open(os.devnull, "w")))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/press/route"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def use(self, tenant):
        self.tearDown()
        self.tenant = tenant
        self.start()

    def post(self, raw, headers):
        req = urllib.request.Request(self.url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def press(self, name="SO-0001"):
        raw = body(name)
        return self.post(raw, signed(raw))

    def test_s1_an_order_goes_to_its_districts_own_store_on_the_header_and_every_line(self):
        before = copy.deepcopy(self.tenant.orders["SO-0001"])
        code, out = self.press()
        self.assertEqual(code, 200, out)
        self.assertEqual(out["message"]["title"], "Sent to store")
        self.assertIs(out["refresh"], True)
        self.assertIn("Maadi Store - S", out["message"]["body"])
        self.assertIn("3 lines", out["message"]["body"])
        self.assertEqual(out["message"]["level"], "success")    # the total did not move
        (name, sent), = self.tenant.writes
        self.assertEqual(sent["set_warehouse"], "Maadi Store - S")
        self.assertEqual(sent["modified"], before["modified"])  # the write names the order as it was read
        # every line, the supplier's too (as Desk's Set Source Warehouse does): lines that differ would empty the header
        self.assertEqual([ln["warehouse"] for ln in sent["items"]], ["Maadi Store - S"] * 3)
        self.assertEqual(self.tenant.orders["SO-0001"]["set_warehouse"], "Maadi Store - S")
        for was, now in zip(before["items"], sent["items"]):    # every line goes back whole: only its warehouse changed
            self.assertEqual({k: v for k, v in now.items() if k != "warehouse"}, {k: v for k, v in was.items() if k != "warehouse"})
        self.assertEqual(set(sent), {"set_warehouse", "items", "modified"})   # nothing else on the order is written

    def test_s2_a_district_without_a_store_takes_the_store_above_it(self):
        self.use(FakeTenant([order(territory="Heliopolis")]))
        code, out = self.press()
        self.assertEqual(self.tenant.writes[0][1]["set_warehouse"], "Cairo Store - S")
        self.assertIn("the store for Cairo, which Heliopolis is part of", out["message"]["body"])

    def test_s3b_a_total_the_store_changes_is_told_to_the_agent(self):
        self.use(FakeTenant(reprice={"Maadi Store - S": 251.04}))
        code, out = self.press()
        self.assertEqual(out["message"]["level"], "warning")
        self.assertTrue(out["message"]["body"].startswith("Its total is now 251.04 (was 230.46)"), out["message"]["body"])
        self.assertIs(out["refresh"], True)

    def test_s3_a_second_press_changes_nothing_and_says_where_the_order_is(self):
        self.press()
        code, out = self.press()
        self.assertEqual(code, 200)
        self.assertEqual(len(self.tenant.writes), 1)
        self.assertEqual(out["message"]["title"], "Already with its store")
        self.assertNotIn("refresh", out)

    def test_s4_no_store_up_the_tree_is_said_in_words_and_nothing_is_written(self):
        self.use(FakeTenant([order(territory="Giza")]))
        code, out = self.press()
        self.assertEqual((code, out["message"]["level"]), (200, "warning"))
        self.assertIn("No store serves Giza", out["message"]["body"])
        self.assertEqual(self.tenant.writes, [])

    def test_s5_an_order_without_a_territory_is_said_in_words(self):
        self.use(FakeTenant([order(territory="")]))
        code, out = self.press()
        self.assertEqual(out["message"]["body"], app.NO_TERRITORY)
        self.assertEqual(self.tenant.writes, [])

    def test_s6_a_submitted_order_is_never_written(self):
        self.use(FakeTenant([order(docstatus=1)]))
        code, out = self.press()
        self.assertEqual(out["message"]["body"], app.SUBMITTED)
        self.assertEqual(self.tenant.writes, [])

    def test_s7_an_edit_saved_between_the_read_and_the_write_is_never_written_over(self):
        self.use(FakeTenant(edit_before_write=1))    # the write is stale: answered in words, never retried
        code, out = self.press()
        self.assertEqual(out["message"]["body"], app.CHANGED)
        self.assertEqual(self.tenant.writes, [])
        self.assertEqual(self.tenant.reads, ["SO-0001", "SO-0001"])   # the stale write re-read once, never written again
        code, out = self.press()                      # the agent reloads and presses again: routed from what was saved
        self.assertEqual(out["message"]["title"], "Sent to store")

    def test_s7b_a_double_click_answers_already_never_changed(self):
        self.use(FakeTenant(routed_before_write="Maadi Store - S"))
        code, out = self.press()
        self.assertEqual(out["message"]["title"], "Already with its store")
        self.assertEqual(self.tenant.writes, [])          # the stale write was refused; nothing written over

    def test_s8_an_order_the_shop_will_not_save_is_said_in_the_services_own_words(self):
        self.use(FakeTenant(refuse_write=(417, "ValidationError")))
        code, out = self.press()
        self.assertEqual((code, out["message"]["body"]), (200, app.NOT_SAVED))

    def test_s8b_a_group_a_disabled_or_another_companys_store_is_never_written(self):
        for wh in ("All Warehouses - S", "Old Store - S", "Other Co Store - O", "Gone Store - S"):
            tree = territories()
            tree["Maadi"][F] = wh
            self.use(FakeTenant(tree=tree))
            code, out = self.press()
            self.assertEqual((code, out["message"]["level"]), (200, "warning"), wh)
            self.assertIn(f"{wh} cannot ship this order", out["message"]["body"])
            self.assertEqual(self.tenant.writes, [], wh)

    def test_s9_the_apps_user_refused_by_the_shop_is_said_in_words(self):
        for refuse in (401, 403):
            self.use(FakeTenant(refuse=refuse))
            code, out = self.press()
            self.assertEqual((code, out["message"]["body"]), (200, app.REFUSED))

    def test_s10_an_order_deleted_meanwhile_is_said_in_words(self):
        code, out = self.press("SO-9999")
        self.assertEqual(out["message"]["body"], app.GONE)

    def test_s11_a_write_with_no_answer_is_an_unknown_outcome_and_a_second_press_finds_it(self):
        self.use(FakeTenant(refuse_write=(None,)))
        code, out = self.press()
        self.assertEqual(code, 502)
        self.assertNotIn("message", out)    # the shop tells the agent to check the order before pressing again

    def test_the_signature_is_checked_and_an_old_press_refused(self):
        raw = body()
        self.assertEqual(self.post(raw, signed(raw, "another-secret"))[0], 401)
        self.assertEqual(self.post(raw, signed(raw, ts=time.time() - 3600))[0], 401)
        self.assertEqual(self.tenant.writes, [])

    def test_a_press_must_name_exactly_one_sales_order(self):
        two = [{"doctype": "Sales Order", "name": n, "fields": {"name": n}} for n in ("SO-1", "SO-2")]
        for recs in ([], two, [{"doctype": "Delivery Note", "name": "DN-1", "fields": {}}], [{"doctype": "Sales Order"}]):
            raw = body(records=recs)
            self.assertEqual(self.post(raw, signed(raw))[0], 400, recs)
        self.assertEqual(self.tenant.writes, [])

    def test_a_long_store_name_is_cut_to_the_answers_limit(self):
        long, district = "S" * 140, "D" * 140        # both at a link field's longest: the sentence runs past 280
        tree = territories()
        tree[district] = {"parent_territory": "Cairo", F: long}
        self.use(FakeTenant([order(territory=district)], tree=tree, warehouses=dict(WAREHOUSES, **{long: {"company": "Shop"}})))
        code, out = self.press()
        self.assertEqual(len(out["message"]["body"]), 280)
        self.assertTrue(out["message"]["body"].endswith("…"))
        self.assertEqual(self.tenant.writes[0][1]["set_warehouse"], long)    # the store itself is never cut

    def test_a_territory_gone_from_the_tree_names_no_store(self):
        tree = territories()
        tree["Maadi"] = {"parent_territory": "Vanished"}
        self.use(FakeTenant(tree=tree))
        code, out = self.press()
        self.assertIn("No store serves Maadi", out["message"]["body"])
        self.assertEqual(self.tenant.writes, [])

    def test_a_looping_tree_ends(self):
        tree = {"A": {"parent_territory": "B"}, "B": {"parent_territory": "A"}}
        self.assertEqual(route.store_for("A", lambda n: tree.get(n)), (None, None))


if __name__ == "__main__":
    unittest.main()
