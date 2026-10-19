# Source: ivendnext/iVendNext_Payments apps/ivendnext_pay_remote/ivendnext_pay_remote/tests/partner_stub.py @ 36385b31a5d0, copied unchanged: the payments team's stand-in partner connector. Its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md), and we take it to the payments board.
# Copyright (c) 2026, CitiXsys Technologies and contributors
# For license information, please see license.txt
"""A STUB PARTNER CONNECTOR — the partner's side of `paygw/1`, for the tests, the kit and the walk.

It stands in for a payment connector on a PARTNER's server. It owns what a real connector owns: the
provider's wire format (here a toy in-memory ledger), the map from OUR reference to the provider's own handle,
idempotency by (site, reference), and the answer to "what happened to reference X". It owns nothing of ours.

⭐ SCOPED BY SITE (draft §1, C17). One connector serves many tenants and our reference is unique per tenant
only, so every lookup is by (`site`, `reference`) and every answer echoes `site` and `currency`.

FIVE PROFILES, the five most-unlike shapes the `premote0` stress test named:
    card_cloud   card-present, the provider's cloud terminal API, synchronous, can prove absence
    card_agent   card-present, a counter-wired terminal behind a store agent, CANNOT prove absence
    momo         mobile money: pending + the partner's own handle, settles out of band (callback / poll)
    wallet       a stored-value wallet the partner's server holds, synchronous, can prove absence
    bnpl         pay-later online: pending while the shopper approves on their own phone

FLAWS, each one a way a real connector charges twice, mis-attributes money, or answers a thing the wire
forbids. The conformance kit — or our validator — must refuse every one:
    wrong_amount       captures MORE than was asked (100 minor units), and says so truthfully
    double_debit       a repeated `authorise` on one reference makes a second charge (a new handle)
    foreign_status     `status` answers about the most recent OTHER transaction
    reverse_pending    a reversal that answers `pending` for ever
    reverse_unknown    a reversal that answers `unknown` for ever
    reverse_wrong_amount   a reversal that approves a different amount than was sent
    wrong_site         answers carrying another tenant's `site`
    no_currency        money answers with no `currency`
  the wallet profile's own (`remotewallet`):
    refund_double      a repeated `refund` on one reference refunds AGAIN (a new refund id)
    foreign_refund     a `refund` answers about the most recent OTHER refund
    refund_wrong_amount    a refund that approves a different amount than was asked
    preview_over_balance   a preview whose most-redeemable is more than the balance
    refund_by_original     refunds de-duplicated by the ORIGINAL payment: a second refund of one payment gets the
                           first refund's row back, echoing the new reference
    refund_status_blind    `status` searches only payments, so a refund it made reads "not found"
    refund_no_id           approved refunds carry no refund id
    refund_lost_by_id      `status` given a refund's own id looks for it among PAYMENTS, so it reads "not found"
    refund_status_other_id `status` about a refund answers approved under a DIFFERENT refund id

THE WALLET PROFILE (`remotewallet`): `preview` answers what a customer may spend (balance 150.00 a customer,
less what it has already spent; the customer `NO-WALLET` has no membership) and moves NO money; `refund` gives
a captured payment's money back under the refund's own reference, idempotent by (site, reference), never more
than the payment has left; `status` about a refund reference answers the refund. The condition `otp` makes the
next preview ask for a one-time code, and the next `authorise` then needs `payer_code` = `OTP_CODE`
(`invalid_code` otherwise).

Run standalone (for a walk, behind a tunnel that terminates TLS):
    IVN_POINT_SECRET=... python3 partner_stub.py --profile momo --port 18431 --no-tls
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import ssl
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROFILES = ("card_cloud", "card_agent", "momo", "wallet", "bnpl")
FLAWS = (
    "wrong_amount",
    "double_debit",
    "foreign_status",
    "reverse_pending",
    "reverse_unknown",
    "reverse_wrong_amount",
    "wrong_site",
    "no_currency",
    "refund_double",
    "foreign_refund",
    "refund_wrong_amount",
    "preview_over_balance",
    "refund_by_original",
    "refund_status_blind",
    "refund_no_id",
    "refund_lost_by_id",
    "refund_status_other_id",
)

DECLARATIONS = {
    "card_cloud": {
        "v": 1,
        "display_name": "Stub Cloud Terminal",
        "markets": [["SG", "card_present"]],
        "rails": {"card_present": {"settlement": "synchronous", "can_prove_absence": True}},
        "capabilities": ["reverse"],
        "supports_refund": False,
        "payer_required": False,
        "certification": {},
    },
    "card_agent": {
        "v": 1,
        "display_name": "Stub Counter Terminal (store agent)",
        "markets": [["SG", "card_present"]],
        "rails": {"card_present": {"settlement": "synchronous", "can_prove_absence": False}},
        "capabilities": ["reverse"],
        "supports_refund": False,
        "payer_required": False,
        "certification": {},
    },
    "momo": {
        "v": 1,
        "display_name": "Stub Mobile Money",
        "markets": [["KE", "mobile_money"]],
        "rails": {"mobile_money": {"settlement": "asynchronous", "can_prove_absence": True}},
        "capabilities": ["reverse"],
        "supports_refund": False,
        "payer_required": True,
        "certification": {},
    },
    "wallet": {
        "v": 1,
        "display_name": "Stub Store Wallet",
        "markets": [["AE", "wallet"]],
        "rails": {"wallet": {"settlement": "synchronous", "can_prove_absence": True}},
        "capabilities": ["balance_preview", "refund", "reverse"],
        "supports_refund": True,
        "payer_required": True,
        "certification": {},
    },
    "bnpl": {
        "v": 1,
        "display_name": "Stub Pay Later",
        "markets": [["AE", "card_not_present"]],
        "rails": {"card_not_present": {"settlement": "asynchronous", "can_prove_absence": True}},
        "capabilities": ["reverse"],
        "supports_refund": False,
        "payer_required": True,
        "certification": {},
    },
}
ASYNC = {"momo", "bnpl"}
CARD = {"card_cloud", "card_agent"}
RAIL = {"card_cloud": "card_present", "card_agent": "card_present", "momo": "mobile_money", "wallet": "wallet", "bnpl": "card_not_present"}
LOST_REPLY_SLEEP_S = 4.0
HELD_MERCHANTS = ("M-STUB-1", "M-STUB-2")
BODY_MAX, SKEW_S, PREFIX = 64 * 1024, 300, "/paygw/1/"
VERBS = ("declaration", "authorise", "status", "reverse", "induce", "settle", "preview", "refund")
WALLET_BALANCE_MINOR = 15000
NO_WALLET = "NO-WALLET"
OTP_CODE = "246810"


class LostReply(Exception):
    """Send NOTHING back (drop the connection, or outlive the caller's deadline)."""

    def __init__(self, after_capture: bool):
        super().__init__("reply lost")
        self.after_capture = after_capture


class Unavailable(Exception):
    """Answer 503: the provider behind the connector cannot be reached."""


class Connector:
    def __init__(self, profile: str, flaws=(), live: bool = False, lost_reply_sleep: float = LOST_REPLY_SLEEP_S):
        if profile not in PROFILES:
            raise ValueError(profile)
        bad = set(flaws) - set(FLAWS)
        if bad:
            raise ValueError(sorted(bad))
        self.profile, self.flaws, self.live = profile, set(flaws), live
        self.lost_reply_sleep = lost_reply_sleep
        self.lock = threading.Lock()
        self.ledger = {}  # (site, our reference) -> row
        self.refunds = {}  # (site, our REFUND reference) -> refund row
        self.refund_order = []
        self.spent = {}  # (site, customer) -> minor units debited and not given back
        self.otp_armed = False
        self.order = []
        self.condition = "clear"
        self.charges = 0  # every provider-side debit: a double debit shows here
        self.refunds_made = 0  # every provider-side refund: a double refund shows here
        self.calls = []  # (verb, body) of every money call, for the tests

    def declaration(self) -> dict:
        return json.loads(json.dumps(DECLARATIONS[self.profile]))

    # ------------------------------------------------------------------ test verbs (a LIVE connector refuses)
    def induce(self, req) -> dict:
        if self.live:
            raise PermissionError("a live connector refuses test verbs")
        condition = req["condition"]
        if condition == "capture_outstanding":
            raise ValueError("this provider has no authorise-then-capture split")
        self.condition = condition
        return {"v": 1, "accepted": condition}

    def settle(self, req) -> dict:
        if self.live:
            raise PermissionError("a live connector refuses test verbs")
        with self.lock:
            row = self.ledger.get((req["site"], req["reference"]))
            if not row:
                raise KeyError(req["reference"])
            if row["state"] == "pending":
                row["state"] = "approved"
                row["auth_ref"] = row["auth_ref"] or ("AUTH-" + uuid.uuid4().hex[:10].upper())
                self.charges += 1
            return {"v": 1, "reference": req["reference"], "state": row["state"]}

    def _take_condition(self) -> str:
        c, self.condition = self.condition, "clear"
        return c

    # ------------------------------------------------------------------ the money verbs
    def authorise(self, req: dict) -> dict:
        site, ref, amount = req["site"], req["reference"], int(req["amount_minor"])
        with self.lock:
            self.calls.append(("authorise", dict(req)))
            cond = self._take_condition()
            if cond == "provider_unreachable":
                raise Unavailable()
            if cond == "bad_credentials":
                return self._decl(req, "declined", reason="config_invalid")
            existing = self.ledger.get((site, ref))
            if existing and "double_debit" not in self.flaws:
                return self._answer(req, existing)  # ⭐ idempotent by (site, reference)
            if cond == "decline":
                return self._answer(req, self._new(site, ref, amount, req, "declined"))
            if cond == "reply_lost_before_capture":
                raise LostReply(after_capture=False)
            if self.profile == "wallet":
                if self.otp_armed and req.get("payer_code") != OTP_CODE:
                    return self._answer(req, self._new(site, ref, amount, req, "declined", reason="invalid_code"))
                party = (req.get("payer") or {}).get("party") or ""
                if amount > WALLET_BALANCE_MINOR - self.spent.get((site, party), 0):
                    return self._answer(req, self._new(site, ref, amount, req, "declined", reason="insufficient_funds"))
            if req.get("merchant") not in (None,) + HELD_MERCHANTS or (req.get("merchant") is None and self.profile not in CARD):
                return self._decl(req, "declined", reason="config_invalid")
            if self.profile in ASYNC and cond == "reply_lost_after_capture":
                row = self._new(site, ref, amount, req, "approved")
                self.charges += 1
            elif self.profile in ASYNC:
                row = self._new(site, ref, amount, req, "pending")
            else:
                row = self._new(site, ref, amount, req, "approved")
                self.charges += 1
                if self.profile == "wallet":
                    party = (req.get("payer") or {}).get("party") or ""
                    row["party"] = party
                    self.spent[(site, party)] = self.spent.get((site, party), 0) + row["amount_minor"]
                    self.otp_armed = False
            if cond == "reply_lost_after_capture":
                raise LostReply(after_capture=True)
            return self._answer(req, row)

    def status(self, req: dict) -> dict:
        site, ref = req["site"], req["reference"]
        with self.lock:
            self.calls.append(("status", dict(req)))
            if self._take_condition() == "provider_unreachable":
                raise Unavailable()
            if "foreign_status" in self.flaws:
                others = [k for k in self.order if k != (site, ref)]
                if others:
                    other = others[-1]
                    return self._answer(dict(req, reference=other[1]), self.ledger[other], reference=other[1])
            if req.get("merchant") not in (None,) + HELD_MERCHANTS:
                # ⭐ a merchant this connector does not hold: it can say nothing about it
                return self._decl(req, "unknown", reason="config_invalid")
            # ⭐ a HELD merchant only shows who is asking: the lookup is by (site, reference), never narrowed by it
            blind = "refund_status_blind" in self.flaws or ("refund_lost_by_id" in self.flaws and req.get("correlation_id"))
            refund = self.refunds.get((site, ref)) if not blind else None
            if refund:
                if "refund_status_other_id" in self.flaws:
                    return self._refund_answer(req, dict(refund, refund_id="RF-OTHER-" + uuid.uuid4().hex[:6].upper()))
                return self._refund_answer(req, refund)
            row = self.ledger.get((site, ref))
            if not row:
                if DECLARATIONS[self.profile]["rails"][RAIL[self.profile]]["can_prove_absence"]:
                    return self._decl(req, "unknown", exists=False)
                return self._decl(req, "unknown")
            return self._answer(req, row)

    def reverse(self, req: dict) -> dict:
        site, ref = req["site"], req["reference"]
        with self.lock:
            self.calls.append(("reverse", dict(req)))
            if self._take_condition() == "provider_unreachable":
                raise Unavailable()
            amount = int(req["amount_minor"])
            if "reverse_pending" in self.flaws:
                return self._decl(req, "pending", correlation_id="REV-" + uuid.uuid4().hex[:8])
            if "reverse_unknown" in self.flaws:
                return self._decl(req, "unknown")
            row = self.ledger.get((site, ref))
            if not row:
                if not req.get("auth_ref") and DECLARATIONS[self.profile]["rails"][RAIL[self.profile]]["can_prove_absence"]:
                    # ⭐ never received, and provably so: approved, nothing to give back (C15)
                    return self._decl(req, "approved", amount_minor=0)
                return self._decl(req, "unknown")
            if row["state"] == "approved":
                row["state"] = "reversed"  # ⭐ reversing twice is safe and answers approved again
                if row.get("party") is not None:
                    key = (site, row["party"])
                    self.spent[key] = self.spent.get(key, 0) - (row["amount_minor"] - row.get("refunded", 0))
            elif row["state"] == "pending":
                row["state"] = "cancelled"
            given = row["amount_minor"] if row["state"] in ("reversed", "cancelled") else amount
            if "reverse_wrong_amount" in self.flaws:
                given += 100
            return self._decl(req, "approved", amount_minor=given)

    # ------------------------------------------------------------------ the wallet profile
    def preview(self, req: dict) -> dict:
        """What a customer may spend. ⛔ Moves no money: nothing here touches the ledger or `charges`."""
        if self.profile != "wallet":
            raise KeyError("preview")
        with self.lock:
            self.calls.append(("preview", dict(req)))
            cond = self._take_condition()
            if cond == "provider_unreachable":
                raise Unavailable()
            if cond == "otp":
                self.otp_armed = True
            site, customer = req["site"], req.get("customer") or ""
            out = {"v": 1, "site": self._site(req), "currency": req.get("currency")}
            if req.get("merchant") not in HELD_MERCHANTS:
                out.update(eligible=False, reason="This merchant is not enrolled with the wallet.")
                return out
            if customer == NO_WALLET:
                out.update(eligible=False, reason="No active membership.")
                return out
            balance = max(WALLET_BALANCE_MINOR - self.spent.get((site, customer), 0), 0)
            cap = min(balance, int(req["amount_due_minor"]))
            if "preview_over_balance" in self.flaws:
                cap = balance + 100
            out.update(
                eligible=True,
                balance_minor=balance,
                max_redeemable_minor=cap,
                label="Stub Store Wallet",
                otp_required=self.otp_armed,
            )
            return out

    def refund(self, req: dict) -> dict:
        """Give a captured payment's money back, under the REFUND's own reference. Idempotent by (site, reference)."""
        if self.profile != "wallet":
            raise KeyError("refund")
        site, ref = req["site"], req["reference"]
        with self.lock:
            self.calls.append(("refund", dict(req)))
            if self._take_condition() == "provider_unreachable":
                raise Unavailable()
            if "foreign_refund" in self.flaws:
                others = [k for k in self.refund_order if k != (site, ref)]
                if others:
                    return self._refund_answer(dict(req, reference=others[-1][1]), self.refunds[others[-1]])
            if "refund_by_original" in self.flaws:
                same = [r for (st, _r), r in self.refunds.items() if st == site and r.get("original") == req.get("original_reference")]
                if same:
                    return self._refund_answer(req, same[0])  # ⛔ THE FLAW: the first refund, under the new reference
            existing = self.refunds.get((site, ref))
            if existing and "refund_double" not in self.flaws:
                return self._refund_answer(req, existing)  # ⭐ idempotent: the first answer, the same refund id
            original = self.ledger.get((site, req.get("original_reference")))
            amount = int(req["amount_minor"])
            if not original or original["state"] != "approved":
                return self._decl(req, "declined", reason="declined_by_issuer")
            if amount > original["amount_minor"] - original.get("refunded", 0):
                return self._decl(req, "declined", reason="declined_by_issuer")
            original["refunded"] = original.get("refunded", 0) + amount
            if original.get("party") is not None:
                key = (site, original["party"])
                self.spent[key] = self.spent.get(key, 0) - amount
            row = {"amount_minor": amount, "currency": req["currency"], "refund_id": "RF-" + uuid.uuid4().hex[:10].upper(),
                   "original": req.get("original_reference")}
            if "refund_wrong_amount" in self.flaws:
                row["amount_minor"] += 100
            self.refunds[(site, ref)] = row
            self.refund_order.append((site, ref))
            self.refunds_made += 1  # every money-back: a double refund shows here
            return self._refund_answer(req, row)

    def _refund_answer(self, req, row) -> dict:
        refund_id = None if "refund_no_id" in self.flaws else row["refund_id"]
        return self._decl(dict(req, currency=req.get("currency") or row["currency"]), "approved", amount_minor=row["amount_minor"], correlation_id=refund_id)

    # ------------------------------------------------------------------ helpers
    def _site(self, req):
        return "SOMEONE-ELSE" if "wrong_site" in self.flaws else req["site"]

    def _decl(self, req, outcome, **extra) -> dict:
        out = {"v": 1, "site": self._site(req), "reference": req["reference"], "outcome": outcome, "currency": req.get("currency")}
        if "no_currency" in self.flaws:
            out.pop("currency")
        out.update(extra)
        return {k: v for k, v in out.items() if v is not None}

    def _new(self, site, ref, amount, req, state, reason=None) -> dict:
        if "wrong_amount" in self.flaws and state == "approved":
            amount += 100  # ⛔ THE FLAW: it took more than it was asked for (and will say so)
        row = {
            "state": state,
            "amount_minor": amount,
            "currency": req["currency"],
            "auth_ref": ("AUTH-" + uuid.uuid4().hex[:10].upper()) if state == "approved" else None,
            "correlation_id": ("PH-" + uuid.uuid4().hex[:12].upper()) if self.profile in ASYNC else None,
            "reason": reason,
        }
        self.ledger[(site, ref)] = row
        self.order.append((site, ref))
        return row

    def _answer(self, req, row, reference=None) -> dict:
        req = dict(req, currency=req.get("currency") or row["currency"])
        if reference:
            req["reference"] = reference
        state = row["state"]
        if state == "approved":
            amount = row["amount_minor"]
            extra = {"amount_minor": amount, "auth_ref": row["auth_ref"], "capture_state": "captured"}
            if row["correlation_id"]:
                extra["correlation_id"] = row["correlation_id"]
            if self.profile in CARD:
                extra["instrument"] = {"brand": "visa", "last4": "4242", "expiry": "2030-12"}
            if "double_debit" in self.flaws:
                extra["auth_ref"] = "AUTH-" + uuid.uuid4().hex[:10].upper()
                self.charges += 1
            return self._decl(req, "approved", **extra)
        if state == "pending":
            return self._decl(req, "pending", correlation_id=row["correlation_id"])
        if state == "declined":
            return self._decl(req, "declined", reason=row.get("reason") or "declined_by_issuer")
        if state in ("reversed", "cancelled"):
            return self._decl(req, "declined", reason="payer_cancelled")
        return self._decl(req, "unknown")


def verified(secret: bytes, headers, raw: bytes) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not ts.isdigit() or abs(time.time() - int(ts)) > SKEW_S:
        return False
    want = base64.b64encode(hmac.new(secret, ts.encode() + b"." + raw, hashlib.sha256).digest())
    return hmac.compare_digest(want, sig.encode())


def make_server(conn: Connector, secret: bytes, port: int = 0, *, script=None, host="127.0.0.1"):
    """A threaded server. ``script(verb, body, handler)`` may return ``(status, body)`` to override an answer
    (used by the transport tests: redirects, oversize bodies, slow drips); ``None`` falls through."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        timeout = 30

        def _send(self, code, body, headers=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(200, {"status": "ok"}) if self.path == "/health" else self._send(404, {"error": "not found"})

        def do_POST(self):
            verb = self.path.split(PREFIX, 1)[1] if PREFIX in self.path else ""  # a base path may precede it
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > BODY_MAX:
                return self._send(413, {"error": "too large"})
            raw = self.rfile.read(n)
            seen.append({"verb": verb, "raw": raw, "headers": dict(self.headers)})
            if not verified(secret, self.headers, raw):
                return self._send(401, {"error": "bad signature"})
            if verb not in VERBS:
                return self._send(404, {"error": "no such route"})
            req = json.loads(raw or b"{}")
            if req.get("verb") != verb:
                # ⭐ the verb is inside the signed bytes: a signed body replayed at another route is refused
                return self._send(422, {"error": "verb mismatch"})
            if script:
                override = script(verb, req, self)
                if override is not None:
                    if override == "DROP":
                        self.close_connection = True
                        try:
                            self.connection.shutdown(2)
                        except OSError:
                            pass
                        return
                    if override[0] == "SLOWHEAD":
                        # the status line, then one header line at a time, slowly — never a complete response
                        _, lines, delay = override
                        self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                        for i in range(lines):
                            self.wfile.write(b"X-Pad-%d: x\r\n" % i)
                            self.wfile.flush()
                            time.sleep(delay)
                        return
                    if override[0] == "DRIP":
                        # headers promise the whole body, then it arrives a chunk at a time, slowly
                        _, chunks, delay = override
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(sum(len(c) for c in chunks)))
                        self.end_headers()
                        for chunk in chunks:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            time.sleep(delay)
                        return
                    code, body = override[0], override[1]
                    return self._send(code, body, override[2] if len(override) > 2 else None)
            try:
                if verb == "declaration":
                    body = conn.declaration()
                else:
                    body = getattr(conn, verb)(req)
            except LostReply as lost:
                if lost.after_capture:
                    time.sleep(conn.lost_reply_sleep)
                self.close_connection = True
                try:
                    self.connection.shutdown(2)
                except OSError:
                    pass
                return
            except Unavailable:
                return self._send(503, {"error": "provider unavailable"})
            except PermissionError:
                return self._send(403, {"error": "test verbs are refused by a live connector"})
            except (KeyError, ValueError) as e:
                return self._send(422, {"error": type(e).__name__})
            self._send(200, body)

        def log_message(self, fmt, *args):
            pass

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.seen = seen
    return srv


def make_cert(directory: str) -> tuple[str, str]:
    """A self-signed certificate for `localhost` / 127.0.0.1, written under ``directory``."""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")
    with open(cert_path, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as fh:
        fh.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    return cert_path, key_path


def serve_tls(srv, cert_path, key_path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return thread


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True, choices=PROFILES)
    p.add_argument("--flaw", action="append", default=[], choices=FLAWS)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-tls", action="store_true", help="behind a tunnel that terminates TLS")
    p.add_argument("--cert")
    p.add_argument("--key")
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    secret = (os.environ.get("IVN_POINT_SECRET") or "").strip().encode()
    if not secret:
        raise SystemExit("IVN_POINT_SECRET is not set")
    conn = Connector(a.profile, a.flaw, live=a.live)
    srv = make_server(conn, secret, a.port, host=a.host)
    if not a.no_tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(a.cert, a.key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(json.dumps({"listening": a.port, "profile": a.profile, "flaws": a.flaw}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
