"""S28 — *Merge counts*: the pure core of the Desk button (no framework, no network), shared by the service and its tests.

A stock user ticks several draft stock counts (Stock Reconciliation) on the list and presses **Merge counts**. The shop
sends one signed POST (the Desk action extension point, ``desk_action/1``) naming the ticked records. The service then
re-reads each record over the record API — it trusts nothing the press carried but the names — and:

* ``refusal`` says why the merge may not run (a single count, a submitted or cancelled one, two companies, two purposes,
  a serial-numbered row), or ``""``;
* ``merge_rows`` folds the rows: one row per item, warehouse and batch, its quantity the SUM of the counts or the LAST
  count's (by posting date and time), its valuation rate the last count's; a row with no item or no warehouse is dropped;
* ``plan`` is the ONE new draft the service writes (the press key on it, so a retry finds it and writes no second one);
* ``answer`` is the reply in Desk's closed vocabulary: a message, and ``open_record`` on the new draft.

⛔ The answer writes nothing, and no source count is ever edited or deleted: each gets a comment, ``merged into <name>``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from decimal import Decimal

COUNT = "Stock Reconciliation"
KEY_FIELD = "pp_mhs_press_key"     # the field this app's manifest adds to the count: the press key of the merge that made it
SUM, LAST = "Sum", "Last"
SKEW_S = 300
BODY_MAX = 256 * 1024


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the press is the shop's, else why not: base64 HMAC-SHA256 of ``<timestamp>.<raw body>`` with the
    service's secret (handed back once at install, as ``pp_mhs:sub:merge``), checked before anything is parsed."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def context_of(body: dict) -> dict:
    """The press's context, or ``ValueError``: a ``desk_action/1`` call naming records of the count type, with a key."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list) or not ctx["records"]:
        raise ValueError("no records")
    if any(not isinstance(r, dict) or r.get("doctype") != COUNT or not isinstance(r.get("name"), str) for r in ctx["records"]):
        raise ValueError("a record that is not a stock count")
    key = ctx.get("idempotency_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 64:
        raise ValueError("no idempotency key")
    return ctx


def clock(value) -> tuple:
    """A time as numbers: the shop sends ``9:00:00`` with no leading zero, which sorts after ``10:30:00`` as text."""
    parts = (str(value or "0").split(":") + ["0", "0"])[:3]
    try:
        return int(parts[0]), int(parts[1]), float(parts[2])
    except ValueError:
        return 0, 0, 0.0


def _when(doc: dict) -> tuple:
    """A count's place in time: its posting date and time, then its name (two counts at the same minute stay in order)."""
    return (str(doc.get("posting_date") or ""), clock(doc.get("posting_time")), doc.get("name") or "")


def in_order(docs: list[dict]) -> list[dict]:
    return sorted(docs, key=_when)


def refusal(docs: list[dict]) -> str:
    """Why these counts may not be merged, in a sentence for the user — or ``""``. The whole press is refused on one."""
    if len(docs) < 2:
        return "Tick at least two draft counts to merge."
    for d in docs:
        if d.get("docstatus") == 1:
            return f"{d['name']} is submitted. A submitted count is never merged."
        if d.get("docstatus") == 2:
            return f"{d['name']} is cancelled. A cancelled count is never merged."
        if d.get("docstatus") != 0:
            return f"{d['name']} could not be read as a draft."
    if len({d.get("company") for d in docs}) > 1:
        return "The counts belong to different companies. Merge counts of one company."
    if len({d.get("purpose") for d in docs}) > 1:
        return "The counts have different purposes (opening stock and a count). Merge counts of one purpose."
    for d in docs:
        if any((r.get("serial_no") or "").strip() or r.get("serial_and_batch_bundle") for r in d.get("items") or []):
            return (f"{d['name']} has a row with serial numbers, or its batch or serials in a bundle. "
                    "Merge those counts by hand.")
    return ""


def _num(value) -> Decimal:
    return Decimal(str(value or 0))


def merge_rows(docs: list[dict], rule: str) -> list[dict]:
    """One row per item, warehouse and batch, in the order each first appears. ``Sum`` adds the quantities; ``Last``
    keeps the quantity of the last count (by posting date and time) that has the row. The valuation rate is always the
    last count's that has one (a row counted at zero stores a rate of 0). Quantities are added as decimals."""
    if rule not in (SUM, LAST):
        raise ValueError(f"the merge rule must be {SUM} or {LAST}")
    out: dict[tuple, dict] = {}
    for d in in_order(docs):
        for r in d.get("items") or []:
            item, wh = r.get("item_code"), r.get("warehouse")
            if not item or not wh:        # a blank row is dropped
                continue
            k = (item, wh, r.get("batch_no") or "")
            row = out.get(k)
            if row is None:
                row = out[k] = {"item_code": item, "warehouse": wh, "qty": Decimal(0)}
                if r.get("batch_no"):
                    row["batch_no"] = r["batch_no"]
                    row["use_serial_batch_fields"] = 1
            row["qty"] = row["qty"] + _num(r.get("qty")) if rule == SUM else _num(r.get("qty"))
            if _num(r.get("valuation_rate")) or "valuation_rate" not in row:   # a counted zero stores no rate: keep the last real one
                row["valuation_rate"] = _num(r.get("valuation_rate"))
    return [{**r, "qty": float(r["qty"]), "valuation_rate": float(r["valuation_rate"])} for r in out.values()]


def plan(docs: list[dict], rule: str, key: str) -> dict:
    """The one new draft: the counts' company and purpose, the last count's posting date and time (kept, not today's),
    accounts and cost centre; one store when every count names the same one; the merged rows; the press key."""
    last = in_order(docs)[-1]
    stores = {d.get("set_warehouse") for d in docs}
    doc = {"doctype": COUNT, "docstatus": 0, "company": last["company"], "purpose": last.get("purpose"),
           "posting_date": last.get("posting_date"), "posting_time": last.get("posting_time"), "set_posting_time": 1,
           KEY_FIELD: key, "items": merge_rows(docs, rule)}
    if len(stores) == 1 and None not in stores:
        doc["set_warehouse"] = stores.pop()
    for f in ("expense_account", "cost_center"):
        if last.get(f):
            doc[f] = last[f]
    return doc


def comment_text(name: str) -> str:
    return f"merged into {name}"


def answer(new_name: str, sources: list[str], lines: int) -> dict:
    body = (f"{len(sources)} counts, {lines} line{'s' if lines != 1 else ''}, in the new draft {new_name}. Check it, then "
            "submit it. The ticked counts are still drafts: cancel or delete them, or the stock is counted twice.")
    return {"message": {"title": "Counts merged", "body": body[:280], "level": "success"},
            "open_record": {"doctype": COUNT, "name": new_name}}


def refused(why: str) -> dict:
    """A refusal as an answer: a warning and no next step. Nothing was written."""
    return {"message": {"title": "Nothing merged", "body": why[:280], "level": "warning"}}
