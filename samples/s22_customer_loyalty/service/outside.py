"""S22 — the opt-in adapter to the chain's OWN loyalty system, outside iVendNext (standard library only).

Off unless the retailer's settings record names its loyalty system (``loyalty_api``, with ``loyalty_api_key``). Off,
the service behaves exactly as shipped: S22's service is then the loyalty engine itself and calls nothing outside. On:
  * the Member key also asks the chain's loyalty system for the customer's points and today's offer, and shows them;
  * after payment, each change of what the customer earned is posted to the chain's loyalty system, once: a sale's
    earning, and what a return or a cancellation takes back (each ledger row's unique key is the call's Idempotency-Key,
    so the feed's retry after a lost answer never posts twice). The chain's system not answering: the feed event stays
    undone and is tried again. The chain's system refusing (a 4xx other than 429, or an address that is not allowed): the
    refusal is noted in the service's log, by its status only, and the event is done: it is not retried every pass.

The two calls are those of the stand-in beside the tests (``tests/standin_loyalty.py``); a real loyalty system names them
its own way, so this file is the one you change. Its address is the retailer's to give: https to a public name or address,
with no query or fragment (never a private, loopback or link-local address, a one-word host or a .local/.internal name, so
a hosted service never calls inside its own network); plain http only to this machine and only in local mode
(``IVN_LOCAL=1``, a laptop run). No redirect is followed, so the
key never travels to another host.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import urllib.error
import urllib.parse
import urllib.request

LOCAL = ("localhost", "127.0.0.1", "::1")


class LoyaltyDown(Exception):
    """No answer in time, or the loyalty system's own failure (5xx, 429): nothing is known; the feed tries again."""


class LoyaltyRefused(Exception):
    """The loyalty system said no for good (4xx), or its address is not allowed: noted, never retried every pass."""

    def __init__(self, status: int, why: str = ""):
        super().__init__(f"{status} {why}".strip())
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def address_ok(base: str) -> bool:
    u = urllib.parse.urlsplit(base or "")
    if not u.hostname or u.query or u.fragment or "?" in (base or "") or "#" in (base or ""):
        return False
    local = os.environ.get("IVN_LOCAL") == "1"
    if u.scheme == "http":
        return u.hostname in LOCAL and local
    if u.scheme != "https":
        return False
    try:                                        # an address typed as numbers: never one inside a network, outside local mode
        ip = ipaddress.ip_address(u.hostname)
        return local or ip.is_global
    except ValueError:
        pass
    return local or ("." in u.hostname and u.hostname not in LOCAL and not u.hostname.endswith((".local", ".internal", ".localhost")))


class LoyaltySystem:
    def __init__(self, base: str, key: str, timeout: float = 0.8):
        if not address_ok(base):
            raise LoyaltyRefused(0, "the loyalty system's address must be https, with no query")
        self.base, self.key, self.timeout = base.rstrip("/"), key, timeout

    def _post(self, path: str, body: dict, idem: str = "") -> dict:
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "s22-customer-loyalty/1"}
        if idem:
            headers["Idempotency-Key"] = idem
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST", headers=headers)
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            e.close()
            if e.code >= 500 or e.code == 429:
                raise LoyaltyDown(f"the loyalty system answered {e.code}") from None
            raise LoyaltyRefused(e.code) from None
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise LoyaltyDown(type(e).__name__) from None

    def lookup(self, customer: str) -> dict:
        """{"points": int, "offer": "<one line>"} for the customer, as the chain's loyalty system knows them."""
        got = self._post("/v1/members/lookup", {"customer": customer})
        if not isinstance(got, dict):
            raise LoyaltyDown("the loyalty system did not answer with an object")
        return got

    def post_earned(self, customer: str, sale: str, value: str, earned: str, currency: str, idem: str) -> dict:
        """One change of what the customer earned: a sale (positive), or a return or cancellation (negative)."""
        return self._post("/v1/earn", {"customer": customer, "sale": sale, "value": value, "earned": earned,
                                       "currency": currency}, idem=idem)


def of(s) -> LoyaltySystem | None:
    """The chain's loyalty system from the settings, or None when the adapter is off (the shipped behaviour)."""
    return LoyaltySystem(s.loyalty_api, s.loyalty_key) if s.loyalty_api else None
