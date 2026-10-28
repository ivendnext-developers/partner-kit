"""S52 — the telecom company, as your service sees it: one retailer's account at a time (standard library only).

Every call carries ONE retailer's own telecom account and key, read from that retailer's ``PP TEL Settings`` at the
moment of the call (``app.py``). The address is the service's own setting (``TEL_API``), never a value a retailer typed:
the service calls one telecom company, with each retailer's own account at it.

The three calls are the stand-in's (``standin/telecom_api.py``); a real telecom company's API names them its own way, so
this file is the one you change.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

USER_AGENT = "s52-phone-plans/1"


class TelecomDown(Exception):
    """No answer in time, or the telecom company's own failure (5xx): nothing is known about the call's effect."""


class TelecomRefused(Exception):
    """The telecom company answered and said no (4xx): its own sentence, for the cashier or the activation row."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # the account's key never travels to another host
        return None


class Telecom:
    def __init__(self, base: str, account: str, key: str, timeout: float = 1.5):
        if not (base and account and key):
            raise TelecomRefused("This store has no telecom account set up yet.")
        self.base, self.account, self.key, self.timeout = base.rstrip("/"), account, key, timeout

    def _call(self, method: str, path: str, body: dict | None = None, idem: str = "") -> dict:
        headers = {"Authorization": f"Bearer {self.key}", "X-Account": self.account, "Accept": "application/json",
                   "Content-Type": "application/json", "User-Agent": USER_AGENT}
        if idem:
            headers["Idempotency-Key"] = idem
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            try:
                said = str((json.loads(e.read() or b"{}") or {}).get("error") or "")[:140]
            except ValueError:
                said = ""
            e.close()
            if e.code >= 500 or e.code in (401, 403, 429):   # a key or account refused is fixed by the retailer: try again
                raise TelecomDown(f"the telecom company answered {e.code}") from None
            raise TelecomRefused(said or f"the telecom company refused ({e.code})") from None
        except (OSError, http.client.HTTPException, ValueError) as e:   # timeouts, a cut connection, a broken answer
            raise TelecomDown(type(e).__name__) from None

    def plans(self) -> list[dict]:
        """The account's plans: [{code, name, price_minor, currency, exponent, phones}]."""
        return list(self._call("GET", "/v1/plans").get("plans") or [])

    def offers(self, phones: list[str], customer: str | None) -> dict:
        """{"offers": [{"phone", "plans"}], "refused": "<why>" when the customer may take none}."""
        return self._call("POST", "/v1/offers", {"phones": phones, "customer": customer or ""})

    def activate(self, plan: str, phone: str, serial: str, customer: str, reference: str, idem: str) -> dict:
        """{"activation", "status"}. ``idem`` names the plan line: the same line asked again gets the same number."""
        return self._call("POST", "/v1/activations", {"plan": plan, "phone": phone, "serial": serial,
                                                       "customer": customer, "reference": reference}, idem=idem)
