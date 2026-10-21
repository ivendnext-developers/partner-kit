"""S35 — *Send to store*: the pure core (no framework, no network), shared by the service and its tests.

The shop's Desk button on a draft Sales Order sends one signed POST per press (the Desk action extension point,
``desk_action/1``):

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang",
                                           "records": [{"doctype": "Sales Order", "name", "fields": {"name", "territory"}}],
                                           "inputs": {}, "idempotency_key"}}

``verify`` checks the signature the shop puts on every call; ``store_for`` walks the order's territory up the tree to
the first territory with a Serving store; ``plan`` decides what changes on the order (the header's warehouse and every
line's, as Desk's own Set Source Warehouse does); ``sent`` and ``already`` build the reply in the extension point's closed vocabulary
(a ``message``, and ``refresh`` once the order changed). ⛔ The answer never writes anything: the service writes the
order itself, with its own API key and its own rights, BEFORE it answers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

FIELD = "pp_cco_store"   # the Serving store on Territory: the manifest's own field
SKEW_S = 300             # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
DEPTH = 12               # territories walked up at most: a tree deeper than this is not a district tree


def use_prefix(prefix: str):
    """The field under another prefix: ``ivendnext_cco_store`` for the App library's app."""
    global FIELD
    FIELD = prefix.lower().replace(" ", "_") + "_store"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def order_of(body: dict) -> str:
    """The one Sales Order the press names, or ``ValueError`` — checked before anything is read or written."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if len(ctx["records"]) != 1:            # the button is on the form only: one order a press
        raise ValueError("one order a press")
    rec = ctx["records"][0]
    if not isinstance(rec, dict) or rec.get("doctype") != "Sales Order" or not isinstance(rec.get("name"), str) \
            or not rec["name"]:
        raise ValueError("not a sales order")
    return rec["name"]


def store_for(territory: str, read) -> tuple[str, str] | tuple[None, None]:
    """(the store, the territory that names it) for ``territory``: its own Serving store, else the nearest one above
    it. ``read(name)`` gives one territory as a dict (``parent_territory`` and the Serving store field). (None, None)
    when no territory up the tree names one, or the tree loops or runs deeper than ``DEPTH``."""
    seen, name = set(), territory
    while name and name not in seen and len(seen) < DEPTH:
        seen.add(name)
        row = read(name) or {}
        if row.get(FIELD):
            return row[FIELD], name
        name = row.get("parent_territory")
    return None, None


def routed(order: dict, store: str) -> bool:
    """The order already ships from ``store``: its header and every line. Every line, a supplier's too, as Desk's own Set
    Source Warehouse does: the shop clears the header on save when the lines' warehouses differ, so a line left on another
    warehouse would empty the header, drop the order from the store's list and make every press write it again."""
    return order.get("set_warehouse") == store and all(
        ln.get("warehouse") == store for t in ("items", "packed_items") for ln in order.get(t) or [])


def can_ship(warehouse: dict, order: dict) -> bool:
    """The Serving store can take this order's lines: a warehouse, not a group, not disabled, of the order's company.
    The shop saves a DRAFT with any of these wrong and refuses it only at submit, so the service checks first."""
    return (not warehouse.get("is_group") and not warehouse.get("disabled")
            and warehouse.get("company") == order.get("company"))


def plan(order: dict, store: str) -> dict:
    """The write that sends ``order`` to ``store``: the header's warehouse, and every line as it was read with its
    warehouse changed. A table is written whole (a row left out is deleted), so EVERY line goes back. ``modified`` as
    read makes the shop refuse the write if the order changed since."""
    lines = [dict(ln, warehouse=store) for ln in order.get("items") or []]
    out = {"set_warehouse": store, "items": lines, "modified": order["modified"]}
    if order.get("packed_items"):   # a bundle's parts: the shop fills a packed row's warehouse only when it is empty,
        out["packed_items"] = [dict(p, warehouse=store) for p in order["packed_items"]]   # so they would stay behind
    return out


def _fit(text: str, most: int = 280) -> str:
    """The extension point's limit on a message's body (280): a long store or territory name is cut, never refused."""
    return text if len(text) <= most else text[: most - 1] + "…"


def _lines(n: int) -> str:
    return f"{n} line{'s' if n != 1 else ''}"


TOTALS = ("grand_total", "rounded_total")


def total_moved(before: dict, after: dict) -> tuple | None:
    """(was, now) when the shop's save changed what the customer pays: a store's own item tax or a price limited to a
    warehouse applies when the warehouse changes. None when the totals are as they were (or the shop did not say)."""
    for k in TOTALS:
        if k in after and before.get(k) != after.get(k):
            return before.get(k), after.get(k)
    return None


def sent(order: dict, store: str, named_by: str, saved: dict | None = None) -> dict:
    """The reply once the order was written: the form reloads and shows the store. If the save changed the total (the
    store's own tax or prices), the agent is told before the customer hangs up."""
    n = len(order.get("items") or [])
    why = (f"the store for {named_by}" if named_by == order.get("territory")
           else f"the store for {named_by}, which {order.get('territory')} is part of")
    body = f"This order and its {_lines(n)} now ship from {store}, {why}."
    moved = total_moved(order, saved or {})
    if moved:
        body = f"Its total is now {moved[1]} (was {moved[0]}): the store's own tax or prices apply. " + body
    return {"refresh": True, "message": {"title": "Sent to store", "body": _fit(body),
                                         "level": "warning" if moved else "success"}}


def already(store: str, named_by: str) -> dict:
    """The reply when the order already ships from its store: nothing was written."""
    return {"message": {"title": "Already with its store",
                        "body": _fit(f"This order already ships from {store}, the store for {named_by}. Nothing changed."),
                        "level": "info"}}
