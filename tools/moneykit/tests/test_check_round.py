"""Laptop tests of ``till.check_round`` (row SET5), no shop: a stub of the framework's module and a stub of the POS app's tender door stand in
for the console, so what is tested is the till's order — check, the cashier's Yes, a refusal books nothing — never the
product's answer (the bench proves that).

    python3 -m unittest discover -s tools/moneykit/tests -p 'test_*.py'
"""
import pathlib
import sys
import types
import unittest

KIT = pathlib.Path(__file__).resolve().parents[1]


class T(unittest.TestCase):
    def setUp(self):
        self.calls = []
        f = types.ModuleType("frappe")
        f.db = types.SimpleNamespace(commit=lambda: self.calls.append("commit"), rollback=lambda: None)
        f.set_user = lambda *a, **k: None
        f.session = types.SimpleNamespace(user="Administrator")
        f.local = types.SimpleNamespace(lang="en")
        f._dict = dict
        u = types.ModuleType("frappe.utils")
        u.flt = lambda v, *a: float(v or 0)
        f.utils = u
        self.tender = types.ModuleType("ivendnext_mpos.api.mpos_tender")
        self.answer = {"checked": 0, "verdict": "allow"}
        self.tender.check_before_tender = lambda cart, key: (self.calls.append(("check", key)), self.answer)[1]
        self.tender.confirm_check = lambda key: self.calls.append(("confirm", key))
        self.tender.submit_tender = lambda *a, **k: (self.calls.append(("submit", k["idempotency_key"])), {"name": "INV-1"})[1]
        api = types.ModuleType("ivendnext_mpos.api")
        api.mpos_tender = self.tender
        self.push_error = None

        def push(cart, sale_key=None):
            self.calls.append(("push", sale_key))
            if self.push_error:
                raise self.push_error
            return {"amount": 1}
        logic = types.ModuleType("ivendnext_mpos.business_logic.mpos_tender")
        logic.card_push_amount = push
        bl = types.ModuleType("ivendnext_mpos.business_logic")
        bl.mpos_tender = logic
        sys.modules.update({"frappe": f, "frappe.utils": u, "ivendnext_mpos": types.ModuleType("ivendnext_mpos"),
                            "ivendnext_mpos.api": api, "ivendnext_mpos.api.mpos_tender": self.tender,
                            "ivendnext_mpos.business_logic": bl, "ivendnext_mpos.business_logic.mpos_tender": logic})
        sys.modules.pop("till", None)
        sys.path.insert(0, str(KIT))
        import till
        till.configure("c@shop.example", "dev-1", "My Profile", "T-1")
        self.till = till

    def tearDown(self):
        sys.path.remove(str(KIT))
        for m in ("till", "ivendnext_mpos", "ivendnext_mpos.api", "ivendnext_mpos.api.mpos_tender",
                  "ivendnext_mpos.business_logic", "ivendnext_mpos.business_logic.mpos_tender"):
            sys.modules.pop(m, None)

    def steps(self):
        return [c for c in self.calls if c != "commit"]

    def test_no_check_in_scope_books_as_before(self):
        self.till.book({"lines": []}, [], "k1")
        self.assertEqual(self.steps(), [("check", "k1"), ("submit", "k1")])

    def test_a_shop_before_wave_b_is_not_asked(self):
        del self.tender.check_before_tender
        self.till.book({"lines": []}, [], "k1")
        self.assertEqual(self.steps(), [("submit", "k1")])

    def test_an_allow_books(self):
        self.answer = {"checked": 1, "verdict": "allow"}
        self.till.book({"lines": []}, [], "k2")
        self.assertEqual(self.steps(), [("check", "k2"), ("push", "k2"), ("submit", "k2")])

    def test_an_ask_is_answered_yes_then_books(self):
        self.answer = {"checked": 1, "verdict": "ask", "questions": ["ID?"]}
        self.till.book({"lines": []}, [], "k3")
        self.assertEqual(self.steps(), [("check", "k3"), ("confirm", "k3"), ("push", "k3"), ("submit", "k3")])

    def test_a_refusal_books_nothing_and_says_why(self):
        for verdict in ("refuse", "approve"):
            self.calls.clear()
            self.answer = {"checked": 1, "verdict": verdict, "reason": "Members only."}
            with self.assertRaises(self.till.CheckRefused) as e:
                self.till.book({"lines": []}, [], "k4")
            self.assertEqual(str(e.exception), "Members only.")
            self.assertNotIn(("submit", "k4"), self.calls)

    def test_a_round_that_does_not_hold_at_the_push_books_nothing(self):
        """The basket changed after the check, or the card method is excluded: the till's push refuses before any money,
        so the kit refuses too — the booking alone would only flag it."""
        self.answer = {"checked": 1, "verdict": "allow"}
        self.push_error = RuntimeError("The sale changed after the check. Press Pay again.")
        with self.assertRaises(self.till.CheckRefused) as e:
            self.till.book({"lines": []}, [], "k6")
        self.assertIn("Press Pay again", str(e.exception))
        self.assertNotIn(("submit", "k6"), self.calls)

    def test_no_check_in_scope_never_pushes(self):
        self.till.book({"lines": []}, [], "k7")
        self.assertNotIn(("push", "k7"), self.calls)

    def test_everything_before_the_check_is_committed_first(self):
        self.answer = {"checked": 1, "verdict": "allow"}
        self.till.book({"lines": []}, [], "k5")
        self.assertEqual(self.calls[0], "commit")       # the check's call rolls the transaction back before it asks


if __name__ == "__main__":
    unittest.main()
