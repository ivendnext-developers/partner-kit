"""S22's opt-in adapter to the chain's OWN loyalty system (``service/outside.py``), against a stand-in of that system
running as a real web server on this machine (``standin_loyalty.py``). Off, nothing changes; on, the Member key shows
the outside system's points and offer, and each sale's earning is posted to it once."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(SAMPLE, "service")]
import app  # noqa: E402
import loyalty  # noqa: E402
import outside  # noqa: E402
import standin_loyalty  # noqa: E402
from fake_shop import sale, shop  # noqa: E402

PRESS = {"context": {"customer": "C1", "lines": []}}


class Adapter(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"IVN_LOCAL": "1"})     # the stand-in is plain http on this machine: local mode
        env.start()
        self.addCleanup(env.stop)
        self.chain = standin_loyalty.Loyalty()
        self.srv = standin_loyalty.serve(self.chain)
        self.t = shop()
        loyalty.enrol(self.t, loyalty.Settings.load(self.t), "C1", "2026-10-01")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def switch_on(self, key="chain-loyalty-key"):
        self.t.db["PP LYL Settings"]["Default"].update(
            loyalty_api=f"http://127.0.0.1:{self.srv.server_address[1]}", loyalty_api_key=key)
        return loyalty.Settings.load(self.t)

    def test_off_the_member_key_and_the_earning_are_exactly_as_shipped(self):
        s = loyalty.Settings.load(self.t)
        before = app.member_key(self.t, s, PRESS, "2026-10-02")
        sale(self.t, "S1", "C1", "500.00")
        self.assertEqual(loyalty.on_sale(self.t, s, "S1", "2026-10-01")["result"], "earned")
        self.assertNotIn("Loyalty points", before["message"]["body"])

    def test_on_the_member_key_shows_the_chains_own_points_and_offer(self):
        out = app.member_key(self.t, self.switch_on(), PRESS, "2026-10-02")
        self.assertIn("Loyalty points: 1,240. Offer: 10% off shoes today.", out["message"]["body"])
        self.assertEqual(set(out), {"message"})                       # a message: no money on the sale

    def test_on_each_sale_is_posted_to_the_chains_system_once(self):
        s = self.switch_on()
        sale(self.t, "S1", "C1", "500.00")
        loyalty.on_sale(self.t, s, "S1", "2026-10-01")
        loyalty.on_sale(self.t, s, "S1", "2026-10-01")               # the feed delivers it again
        self.assertEqual(list(self.chain.posted), ["POS Invoice:S1:earn"])
        self.assertEqual((self.chain.posted["POS Invoice:S1:earn"]["value"], self.chain.posted["POS Invoice:S1:earn"]["earned"]),
                         ("500.00", "10.00"))

    def test_down_the_key_says_so_and_the_sale_is_retried_by_the_feed(self):
        s = self.switch_on()
        self.chain.down = True
        out = app.member_key(self.t, s, PRESS, "2026-10-02")
        self.assertIn("The loyalty system is not answering.", out["message"]["body"])
        sale(self.t, "S1", "C1", "500.00")
        with self.assertRaises(outside.LoyaltyDown):                   # the event stays undone, and is tried again
            loyalty.on_sale(self.t, s, "S1", "2026-10-01")
        self.chain.down = False
        loyalty.on_sale(self.t, s, "S1", "2026-10-01")
        self.assertEqual(len(self.chain.posted), 1)
        self.assertEqual(len([r for r in self.t.db["PP LYL Ledger"].values() if r["entry_type"] == "Earn"]), 1)

    def test_a_return_and_a_cancellation_take_back_in_the_chains_system_too_once(self):
        s = self.switch_on()
        sale(self.t, "S1", "C1", "500.00")
        loyalty.on_sale(self.t, s, "S1", "2026-10-01")
        sale(self.t, "R1", "C1", "-100.00", is_return=1, return_against="S1", posting_date="2026-10-02")
        loyalty.on_sale(self.t, s, "R1", "2026-10-02")
        loyalty.on_sale(self.t, s, "R1", "2026-10-02")               # the feed delivers the return again
        loyalty.on_cancel(self.t, s, "S1", "2026-10-03")
        got = {k: (v["value"], v["earned"]) for k, v in self.chain.posted.items()}
        self.assertEqual(got, {"POS Invoice:S1:earn": ("500.00", "10.00"), "POS Invoice:R1:return": ("-100.00", "-2.00"),
                               "POS Invoice:S1:cancel": ("-400.00", "-8.00")})

    def test_a_refusal_for_good_is_noted_and_the_event_is_done_not_retried_every_pass(self):
        s = self.switch_on()
        self.chain.refuse = True
        sale(self.t, "S1", "C1", "500.00")
        self.assertEqual(loyalty.on_sale(self.t, s, "S1", "2026-10-01")["result"], "earned")   # no raise: the feed moves on
        self.assertEqual(self.chain.posted, {})

    def test_an_address_is_https_with_no_query_and_plain_http_only_to_this_machine_in_local_mode(self):
        self.assertFalse(outside.address_ok("http://loyalty.example.com"))
        self.assertTrue(outside.address_ok("https://loyalty.example.com"))
        self.assertFalse(outside.address_ok("https://loyalty.example.com/x?"))
        self.assertFalse(outside.address_ok("https://loyalty.example.com/#a"))
        self.assertTrue(outside.address_ok("http://127.0.0.1:9000"))
        with mock.patch.dict(os.environ, {"IVN_LOCAL": "0"}):
            self.assertFalse(outside.address_ok("http://127.0.0.1:9000"))
            for inside in ("https://10.0.0.5/", "https://169.254.169.254", "https://[::1]:443", "https://intranet",
                           "https://loyalty.internal", "https://127.0.0.1"):
                self.assertFalse(outside.address_ok(inside), inside)
            self.assertTrue(outside.address_ok("https://8.8.8.8"))

    def test_two_chains_at_once_each_ask_their_own_loyalty_system_with_their_own_key(self):
        import threading
        other = standin_loyalty.Loyalty(key="other-chain-key", members={"C1": {"points": 7, "offer": "B's offer"}})
        srv_b = standin_loyalty.serve(other)
        self.addCleanup(srv_b.server_close)
        self.addCleanup(srv_b.shutdown)
        s_a = self.switch_on()
        t_b = shop()
        loyalty.enrol(t_b, loyalty.Settings.load(t_b), "C1", "2026-10-01")
        t_b.db["PP LYL Settings"]["Default"].update(loyalty_api=f"http://127.0.0.1:{srv_b.server_address[1]}",
                                                   loyalty_api_key="other-chain-key")
        s_b, out, go = loyalty.Settings.load(t_b), {}, threading.Barrier(2)

        def press(name, t, s):
            go.wait()
            out[name] = app.member_key(t, s, PRESS, "2026-10-02")["message"]["body"]
        ths = [threading.Thread(target=press, args=a) for a in (("A", self.t, s_a), ("B", t_b, s_b))]
        for th in ths:
            th.start()
        for th in ths:
            th.join(10)
        self.assertIn("Loyalty points: 1,240", out["A"])
        self.assertIn("Loyalty points: 7. Offer: B's offer.", out["B"])
        self.assertEqual((len(self.chain.calls), len(other.calls)), (1, 1))


if __name__ == "__main__":
    unittest.main()
