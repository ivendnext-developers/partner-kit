"""The conformance check for a *fulfil at sale* service (``fulfil/1``): run it against your own service before a shop
switches it on. It is the kit's port of the product's test of its stand-in voucher service
(ivendnext/iVendNext_PWA ``apps/ivendnext_mpos/ivendnext_mpos/tests/test_partner_fulfil_standin.py`` @ 7d47d331a203): the
product's test imports the product's own signer and answer check, so the kit signs with its stand-in caller
(``tools/standin_caller/caller.py``) and judges each answer against the published schema
(``partner_fulfil.v1.schema.json``, ``issue_answer`` and ``void_answer``). A defect in what it checks is a defect there:
report it through the feedback forms (feedback/README.md).

What a service must do (``contracts/pages/partner_fulfil.md``): the same ``idempotency_key`` always returns the same code;
a ``void`` on a key wins over any later ``issue`` on it, even one sent before the code exists; two keys get two codes; a
refusal is a sentence; a wrong or stale signature is refused; every answer passes the schema.

    python3 -m unittest discover -s tools/contracts/tests                   # the kit's stand-in, in this process
    FULFIL_URL=https://your.server/fulfil FULFIL_SECRET=… \\
      python3 -m unittest tools.contracts.tests.test_fulfil_conformance      # your own service, over HTTPS

Against your own service each run uses new keys, and leaves codes behind: point it at a test denomination with codes
left. A first issue that is not issued fails the check, as in the product's test: a service with nothing to issue proves
neither promise.
"""

import json
import os
import pathlib
import sys
import time
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools" / "contracts"), str(ROOT / "tools" / "standin_caller"),
                str(ROOT / "contracts" / "extension_contracts" / "standins")]
import caller  # noqa: E402
import check  # noqa: E402

SECRET = "standin-secret"


def context(call, key, ref=""):
    base = {"v": 1, "point": "fulfil", "call": call, "idempotency_key": key, "invoice": "ACC-PSINV-0001",
            "store": "Stores - DXB", "pos_profile": "Mall Branch", "company": "Shop", "lang": "en"}
    if call == "void":
        return dict(base, ref=ref)
    return dict(base, currency="AED", currency_exponent=2, customer="CUST-0001",
                line={"item_code": "GAME-CARD-50", "item_group": "Game cards", "uom": "Nos", "face_minor": 5000,
                      "amount_minor": 5000})


def in_process(service):
    """``post(context, secret, stamp)`` → (status, answer): the call the shop sends, signed by the stand-in caller."""
    def post(ctx, secret=SECRET, stamp=None):
        body = json.dumps({"point": "fulfil/1", "context": ctx}, separators=(",", ":")).encode()
        stamp = stamp or str(int(time.time()))
        headers = {"X-iVendNext-Timestamp": stamp, "X-iVendNext-Signature": caller.sign(secret.encode(), stamp, body)}
        status, raw = service.answer(body, headers)
        return status, (json.loads(raw) if 200 <= status < 300 else None)
    return post


def over_http(url, real_secret):
    """The same, to a service at ``url``. A stale stamp cannot be sent through the caller (it stamps now), so that case
    is checked in process only."""
    def post(ctx, secret=None, stamp=None):
        kind, value = caller.call(url, (secret or real_secret).encode(), {"point": "fulfil/1", "context": ctx})
        return (200, value) if kind == "ok" else ((value, None) if kind == "http" else (0, None))
    return post


def failures(post, key=None, stale=True):
    """What a service at ``post`` gets wrong, as sentences; ``[]`` when it conforms."""
    run = key or uuid.uuid4().hex[:12]
    k1, k2, k3 = f"{run}:ROW-1", f"{run}:ROW-2", f"{run}:ROW-3"
    out = []

    def judged(ctx, definition):
        req = "issue_request" if ctx["call"] == "issue" else "void_request"
        assert check.errors("partner_fulfil", req, {"point": "fulfil/1", "context": ctx}) == [], "a test request is wrong"
        status, answer = post(ctx)
        if status != 200 or answer is None:
            out.append(f"{ctx['call']} {ctx['idempotency_key']}: answered {status}, not 200 with JSON")
            return None
        errs = check.errors("partner_fulfil", definition, answer)
        if errs:
            out.append(f"{ctx['call']} {ctx['idempotency_key']}: the answer breaks the schema: {errs[0]}")
        return answer

    first, again = judged(context("issue", k1), "issue_answer"), judged(context("issue", k1), "issue_answer")
    if not first or first.get("verdict") != "issued":
        out.append("the first issue of a new key was not issued: point the check at a denomination with codes left")
    if first and again and first != again:
        out.append("the same key returned a different answer: one key, one code")
    other = judged(context("issue", k2), "issue_answer")
    if first and other and first.get("verdict") == other.get("verdict") == "issued" and first.get("ref") == other.get("ref"):
        out.append("two keys returned the same code")
    if (judged(context("void", k3), "void_answer") or {}).get("verdict") != "voided":
        out.append("a void before the code was issued was not voided")
    if (judged(context("issue", k3), "issue_answer") or {}).get("verdict") != "refuse":
        out.append("an issue after a void was not refused: a void wins over any later issue")
    if first and first.get("verdict") == "issued":
        judged(context("void", k1, ref=first["ref"]), "void_answer")
        if (judged(context("issue", k1), "issue_answer") or {}).get("verdict") != "refuse":
            out.append("an issued code, once voided, was issued again")
    if post(context("issue", f"{run}:ROW-4"), secret="not-the-secret")[0] != 401:
        out.append("a call signed with another secret was not refused")
    if stale and post(context("issue", f"{run}:ROW-5"), stamp="1000")[0] != 401:
        out.append("a call stamped long ago was not refused")
    return out


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class Conformance(unittest.TestCase):
    def test_the_kits_stand_in_voucher_service_conforms(self):
        import voucher_service
        self.assertEqual(failures(in_process(voucher_service.VoucherService(SECRET))), [])

    def test_none_left_is_a_refusal_the_schema_accepts(self):
        import voucher_service
        status, answer = in_process(voucher_service.VoucherService(SECRET, denomination_left=0))(context("issue", "K:1"))
        self.assertEqual((status, answer), (200, {"verdict": "refuse", "reason": "None left in this denomination."}))
        self.assertEqual(check.errors("partner_fulfil", "issue_answer", answer), [])

    def test_a_service_that_issues_a_second_code_for_one_key_fails(self):
        import voucher_service

        class Twice(voucher_service.VoucherService):          # forgets each code it made: a second call makes another
            def answer(self, raw, headers):
                self.codes.clear()
                return super().answer(raw, headers)
        self.assertIn("the same key returned a different answer: one key, one code",
                      failures(in_process(Twice(SECRET))))

    def test_a_service_with_nothing_to_issue_proves_nothing_and_fails(self):
        import voucher_service

        class EmptyAndForgetful(voucher_service.VoucherService):     # none left, and would forget a code if it had one
            def answer(self, raw, headers):
                self.codes.clear()
                return super().answer(raw, headers)
        self.assertIn("the first issue of a new key was not issued: point the check at a denomination with codes left",
                      failures(in_process(EmptyAndForgetful(SECRET, denomination_left=0))))

    def test_a_service_that_issues_after_a_void_fails(self):
        import voucher_service

        class Forgets(voucher_service.VoucherService):        # never remembers a void
            def answer(self, raw, headers):
                self.voided.clear()
                return super().answer(raw, headers)
        self.assertIn("an issue after a void was not refused: a void wins over any later issue",
                      failures(in_process(Forgets(SECRET))))

    @unittest.skipUnless(os.environ.get("FULFIL_URL"), "FULFIL_URL is not set: your own service was not checked")
    def test_your_service_conforms(self):
        self.assertEqual(failures(over_http(os.environ["FULFIL_URL"], os.environ["FULFIL_SECRET"]), stale=False), [])


if __name__ == "__main__":
    unittest.main()
