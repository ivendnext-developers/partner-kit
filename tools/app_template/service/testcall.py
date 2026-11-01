"""The test call: a site (or our server, or ``ivn test``) asks a connection point "do you answer?" without a sale.

A call carrying ``X-iVendNext-Test: 1`` is checked like any call to that point, and then answered without running the
point's handler:

    200 {"test": "ok", "point": "<the point's key>"}

The order is the whole contract, and every service built from the template keeps it:
  1. the route is matched first: a test call to a route the service does not have answers 404, so a test can never pass
     at a wrong address;
  2. the signature is checked exactly as for a real call, with the same secret: a bad one gets the real refusal;
  3. only then the test answer, and the point's handler never runs (nothing is read, written or counted).

The connect and disconnect routes are not points: a test call there is an ordinary call. The call's form is the one in
the request to the POS team (a header, nothing in the body); if the POS settles another form, the kit follows it.
Standard library only.
"""
from __future__ import annotations

import shops                        # the key the site knows the point by (shops.ALIASES, set for a combined app)

HEADER = "X-iVendNext-Test"


def is_test(headers) -> bool:
    """Whether the call is a test call (the header's value is exactly ``1``)."""
    value = headers.get(HEADER) if headers is not None else None
    return isinstance(value, str) and value.strip() == "1"


def answer(key: str) -> tuple[int, dict]:
    """The test call's answer for the point ``key`` (the app's own key for it: in an app made from several samples, the
    key carries the sample's tag, as the manifest names it)."""
    return 200, {"test": "ok", "point": shops.public_key(key)}
