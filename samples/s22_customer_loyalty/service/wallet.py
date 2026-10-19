"""S22 — Member cash: the member's cash back spent at the till. The service answers as a WALLET connector on the remote
gateway contract (``paygw/1``; its wallet profile is ``wallet/1``, the kit's ``contracts/pages/wallet.md``).

Adapted from CitiXsys's private reference implementation @ 74c99d5; a defect here may be a defect there — report it on
the Partner feedback forms.

The shop's payment app (the Payments remote connector) calls ``POST /paygw/1/<verb>``, signed with the connector's
secret (PP_WALLET_SECRET, chosen when the shop's Remote Connector record is made). The wallet is the cash back ledger
this service already keeps in the shop (``PP LYL Ledger``): every redemption, refund and reversal is a ledger row NAMED
by its key, so the shop itself refuses a second row for the same reference and a repeated call is one charge.

    preview     what the member may spend on this sale: the balance and the cap (``max_redemption_percent`` of the
                amount due, never more than the balance). Moves no money and writes nothing.
    authorise   a Redeem row (minus the amount), named ``wallet:<site>:<reference>``. Refused when it exceeds the balance.
    status      the answer about THAT reference: the payment, or the refund of that reference; absent if neither.
    reverse     the whole payment back (a Redeem reversal row); a reference never received is approved with 0.
    refund      part or all of a payment back, under the refund's own reference (a Redeem refund row), never more than
                the payment has left.
    declaration the connector's declaration (what CitiXsys certifies; the shop runs the signed copy).

The cap itself is the TILL's check before the call (the till sends no sale on ``authorise``); this side refuses only
what the balance cannot pay.

A write that is in flight, or that failed in a way that may still land, makes status answer ``unknown`` (never "not
here") about that reference for as long as this process runs; for the first two minutes after a start, status answers
``unknown`` about anything a refund or reversal row does not settle (a write from before the restart may still land).
An authorise starts no write once 45 seconds have passed since it was taken up (the till stops waiting at 60).

Bounds, said plainly: ``induce`` and ``settle`` (the conformance kit's test verbs) answer 403 as a live connector does,
so the kit's verdict on this connector is INCOMPLETE, never CERTIFIED; a declined answer is remembered in this process
only (a restart forgets it, and a re-asked reference is judged again); one process answers, and a file lock per member
(``loyalty.member_lock``) keeps two tills from spending the same cash at once.

    python3 service/wallet.py --declaration      # the declaration as JSON, for tools/sandbox_cert/sign_sandbox_cert.py
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
import time

import loyalty
import money
from shop import Duplicate

LEDGER = loyalty.LEDGER
VERBS = ("declaration", "preview", "authorise", "status", "reverse", "refund", "induce", "settle")
TEST_VERBS = ("induce", "settle")
LABEL = "Member cash"

DECLARATION = {
    "v": 1,
    "display_name": LABEL,
    "markets": [["US", "wallet"]],
    "rails": {"wallet": {"settlement": "synchronous", "can_prove_absence": True}},
    "capabilities": ["balance_preview", "refund", "reverse"],
    "supports_refund": True,
    "payer_required": False,            # Member cash asks nothing of the customer's phone (see the README)
    "certification": {},
}

_declined: dict[tuple, dict] = {}
_unsure: set[tuple] = set()          # (site, key) of a write in flight, or one that failed and may still have landed
WRITE_DEADLINE_S = 45                # past this an authorise starts no write: the till stops waiting at 60 s
SETTLE_S = 120                       # after a start, a write from before it may still land (the shop's 20 s, and more)
STARTED = time.monotonic()


def _today() -> str:
    return datetime.date.today().isoformat()


def _key(site, *parts) -> str:
    return loyalty.key("wallet", site, *parts)


def _id(prefix: str, *parts) -> str:
    """A handle that is the same every time it is asked for (the same reference gives the same auth_ref / refund id)."""
    return prefix + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12].upper()


class Wallet:
    def __init__(self, t, conf: dict):
        self.t = t
        self.merchants = {m.strip() for m in (conf.get("PP_WALLET_MERCHANT") or "").split(",") if m.strip()}
        self.site = (conf.get("PP_WALLET_SITE") or "").strip()

    # ── the wire ─────────────────────────────────────────────────────────────────────────────────────────────────

    def answer(self, verb: str, body: dict, s) -> tuple[int, dict]:
        if verb not in VERBS:
            return 404, {"error": "no such route"}
        if body.get("verb") != verb:            # the verb is inside the signed bytes: a body replayed elsewhere
            return 422, {"error": "verb mismatch"}
        if verb in TEST_VERBS:
            return 403, {"error": "test verbs are refused by a live connector"}
        if verb == "declaration":
            return 200, json.loads(json.dumps(DECLARATION))
        if self.site and body.get("site") != self.site:       # another shop's call: say nothing about money
            if verb == "preview":
                return 200, {"v": 1, "site": body.get("site"), "currency": body.get("currency"), "eligible": False,
                             "reason": "This store is not set up for Member cash."}
            outcome = "declined" if verb in ("authorise", "refund") else "unknown"
            return 200, self._out(body, outcome, reason="config_invalid")
        if verb == "status":    # the shop's status question carries no currency: answer in the programme's own
            body = dict(body, currency=body.get("currency") or s.currency,
                        currency_exponent=body.get("currency_exponent", s.places))
        elif verb in ("authorise", "refund") and body.get("currency_exponent") is None:
            return 422, {"error": "currency_exponent is required"}
        return 200, getattr(self, verb)(body, s)

    def _out(self, req: dict, outcome: str, **extra) -> dict:
        out = {"v": 1, "site": req.get("site"), "reference": req.get("reference"), "outcome": outcome,
               "currency": req.get("currency")}
        out.update(extra)
        return {k: v for k, v in out.items() if v is not None}

    def _ours(self, req: dict, s) -> str:
        """Why this call is not one this wallet takes, or "" when it is."""
        if req.get("merchant") is not None and req.get("merchant") not in self.merchants:
            return "config_invalid"
        if s.currency and (req.get("currency") or "").upper() != s.currency.upper():
            return "config_invalid"
        return ""

    def _amount(self, req: dict):
        return money.from_minor(req["amount_minor"], int(req.get("currency_exponent") or 0))

    def _minor(self, amount, req: dict) -> int:
        return money.to_minor(amount, int(req.get("currency_exponent") or 0))

    # ── what a member may spend ──────────────────────────────────────────────────────────────────────────────────

    def member(self, s, customer: str) -> dict | None:
        if not customer or customer in s.walk_in:
            return None
        e = self.t.get(loyalty.MEMBER, customer)
        return e if e and e.get("status") == "Active" else None

    def preview(self, req: dict, s) -> dict:
        out = {"v": 1, "site": req.get("site"), "currency": req.get("currency")}
        if req.get("merchant") not in self.merchants:
            return out | {"eligible": False, "reason": "This store is not set up for Member cash."}
        if self._ours(req, s):
            return out | {"eligible": False, "reason": "Member cash is held in another currency."}
        if not self.member(s, req.get("customer") or ""):
            return out | {"eligible": False, "reason": "This customer is not a member."}
        credited, _pending = loyalty.balance(self.t, req["customer"])
        exp = int(req.get("currency_exponent") or 0)
        due = money.from_minor(req.get("amount_due_minor") or 0, exp)
        cap = money.redeemable(credited, due, s.max_redemption_percent, exp)
        return out | {"eligible": True, "balance_minor": max(money.to_minor(credited, exp), 0),
                      "max_redeemable_minor": money.to_minor(cap, exp), "label": LABEL, "otp_required": False}

    # ── the money verbs ──────────────────────────────────────────────────────────────────────────────────────────

    def _write(self, key: tuple, doc: dict, started: float | None = None):
        """Insert a ledger row. While it is in flight, and for ever after a failure that may have landed, status about
        it answers unknown, never absent. Past the deadline nothing is written (the till has stopped waiting)."""
        if started is not None and time.monotonic() - started > WRITE_DEADLINE_S:
            raise TimeoutError("past the deadline: nothing written")
        _unsure.add(key)
        try:
            self.t.insert(doc)
        except Duplicate:
            pass                                                     # another call made it a moment ago: the same one
        except BaseException:
            raise                                                    # it may still land: stays unsure
        _unsure.discard(key)

    def authorise(self, req: dict, s) -> dict:
        started = time.monotonic()
        site, ref = req["site"], req["reference"]
        row = self.t.get(LEDGER, _key(site, ref))
        if row:                                                      # asked again: the first answer, the same handle
            return self._payment(req, row)
        if (site, ref) in _declined:
            return _declined[(site, ref)]
        why = self._ours(req, s) or ("config_invalid" if req.get("merchant") is None else "")
        if why:
            return self._out(req, "declined", reason=why)
        customer = (req.get("payer") or {}).get("party") or ""
        if not self.member(s, customer):
            return self._decline(req, "declined_by_issuer")
        amount = self._amount(req)
        if amount <= 0:
            return self._decline(req, "declined_by_issuer")
        with loyalty.member_lock(customer):
            row = self.t.get(LEDGER, _key(site, ref))
            if row:
                return self._payment(req, row)
            credited, _ = loyalty.balance(self.t, customer)
            if amount > credited:
                return self._decline(req, "insufficient_funds")
            doc = {"doctype": LEDGER, "source_key": _key(site, ref), "customer": customer, "entry_type": "Redeem",
                   "status": "Credited", "amount": -amount, "sale_base": 0, "posting_date": _today()}
            self._write((site, _key(site, ref)), doc, started)
        return self._payment(req, self.t.get(LEDGER, _key(site, ref)) or doc)

    def _decline(self, req: dict, reason: str) -> dict:
        out = self._out(req, "declined", reason=reason)
        _declined[(req["site"], req["reference"])] = out
        return out

    def _payment(self, req: dict, row: dict) -> dict:
        site, ref = req["site"], req["reference"]
        if self.t.get(LEDGER, _key(site, ref, "reverse")):
            return self._out(req, "declined", reason="payer_cancelled")
        return self._out(req, "approved", amount_minor=self._minor(-money.D(row["amount"]), req),
                         auth_ref=_id("PPA-", site, ref), capture_state="captured")

    def status(self, req: dict, s) -> dict:
        site, ref = req["site"], req["reference"]
        if req.get("merchant") is not None and req["merchant"] not in self.merchants:
            return self._out(req, "unknown", reason="config_invalid")
        refund = self.t.get(LEDGER, _key(site, "refund", ref))
        if refund:
            return self._refund_answer(req, refund)
        row = self.t.get(LEDGER, _key(site, ref))
        reversed_ = row and self.t.get(LEDGER, _key(site, ref, "reverse"))
        if not reversed_ and (time.monotonic() - STARTED < SETTLE_S
                              or (site, _key(site, ref, "reverse")) in _unsure):
            return self._out(req, "unknown")                    # a write from before the start, or a reversal, may land
        if row:
            return self._payment(req, row)
        if (site, ref) in _declined:
            return _declined[(site, ref)]
        if (site, _key(site, ref)) in _unsure or (site, _key(site, "refund", ref)) in _unsure:
            return self._out(req, "unknown")                    # a write that may still land is never "not here"
        return self._out(req, "unknown", exists=False)         # never received: the ledger is the only record

    def reverse(self, req: dict, s) -> dict:
        site, ref = req["site"], req["reference"]
        row = self.t.get(LEDGER, _key(site, ref))
        if not row:
            if not req.get("auth_ref"):
                return self._out(req, "approved", amount_minor=0)    # never received, and provably so
            return self._out(req, "unknown")
        with loyalty.member_lock(row["customer"]):
            paid = -money.D(row["amount"])
            back = paid - self._refunded(site, ref)
            if back > 0:
                self._write((site, _key(site, ref, "reverse")),     # reversing twice is safe (the same name)
                            {"doctype": LEDGER, "source_key": _key(site, ref, "reverse"),
                             "customer": row["customer"], "entry_type": "Redeem reversal", "status": "Credited",
                             "amount": back, "sale_base": 0, "against_sale": ref, "posting_date": _today()})
        return self._out(req, "approved", amount_minor=self._minor(paid, req))

    def _refunded(self, site, original_ref):
        rows = self.t.list(LEDGER, [["against_sale", "=", original_ref], ["entry_type", "=", "Redeem refund"],
                                    ["source_key", "like", _key(site, "refund", "") + "%"]], ["amount"])
        return sum((money.D(r["amount"]) for r in rows), money.D(0))

    def refund(self, req: dict, s) -> dict:
        site, ref, original = req["site"], req["reference"], req.get("original_reference") or ""
        existing = self.t.get(LEDGER, _key(site, "refund", ref))
        if existing:                                                 # one refund reference is one refund
            return self._refund_answer(req, existing)
        if self._ours(req, s):
            return self._out(req, "declined", reason="config_invalid")
        paid_row = self.t.get(LEDGER, _key(site, original))
        if not paid_row or self.t.get(LEDGER, _key(site, original, "reverse")):
            return self._out(req, "declined", reason="declined_by_issuer")
        amount = self._amount(req)
        with loyalty.member_lock(paid_row["customer"]):
            existing = self.t.get(LEDGER, _key(site, "refund", ref))
            if existing:
                return self._refund_answer(req, existing)
            if self.t.get(LEDGER, _key(site, original, "reverse")):  # reversed while this waited for the lock
                return self._out(req, "declined", reason="declined_by_issuer")
            left = -money.D(paid_row["amount"]) - self._refunded(site, original)
            if amount <= 0 or amount > left:
                return self._out(req, "declined", reason="declined_by_issuer")
            doc = {"doctype": LEDGER, "source_key": _key(site, "refund", ref), "customer": paid_row["customer"],
                   "entry_type": "Redeem refund", "status": "Credited", "amount": amount, "sale_base": 0,
                   "against_sale": original, "posting_date": _today()}
            self._write((site, _key(site, "refund", ref)), doc)
        return self._refund_answer(req, self.t.get(LEDGER, _key(site, "refund", ref)) or doc)

    def _refund_answer(self, req: dict, row: dict) -> dict:
        site, ref = req["site"], req["reference"]
        return self._out(req, "approved", amount_minor=self._minor(row["amount"], req),
                         correlation_id=_id("PPR-", site, ref))


if __name__ == "__main__" and sys.argv[1:] == ["--declaration"]:
    print(json.dumps(DECLARATION, indent=1))
