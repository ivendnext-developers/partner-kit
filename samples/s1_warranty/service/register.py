"""S1 — registering warranties from booked sales: one logic for both forms (``app.py`` on your own server, ``hosted.py`` on
CitiXsys hosting). ``store`` keeps what was handled; ``tenant`` is the only door into iVendNext. Standard library only.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import core

DOCTYPES = ("Sales Invoice", "POS Invoice")


def process(store, tenant, doctype: str, name: str, via: str) -> str:
    """Idempotent: safe for a webhook, a retry, a replay and a reconciliation to reach the same sale."""
    with store.lock:
        if store.is_processed(doctype, name):
            return "already processed"
        doc = tenant.get(doctype, name)
        if doc.get("docstatus") != 1:
            return "not submitted — left for a later pass"
        if doc.get("is_return") or doc.get("is_consolidated"):
            # a return gives no new warranty; a consolidated invoice repeats POS sales already handled
            store.record(doctype, name, [], None, via)
            return "skipped (return or consolidated)"
        items = [r for r in doc.get("items") or [] if r.get("item_code")]
        terms = store.terms()
        terms["item_group"] = tenant.item_groups([r["item_code"] for r in items])
        lines = [{"item_code": r["item_code"],
                  "serials": tenant.serials_of(r) if core.term_for(r["item_code"], terms)[0] == core.COVERED else []}
                 for r in items]
        regs, skipped = core.registrations(lines, terms, date.fromisoformat(doc["posting_date"]))
        comment = None
        if regs or any(s["reason"] == "no serial numbers on the line" for s in skipped):
            if tenant.has_our_comment(doctype, name):
                comment = "(already present)"   # a crash after the comment, before the commit: never twice
            else:
                comment = tenant.add_comment(doctype, name, core.comment_text(name, regs, skipped))
        added = store.record(doctype, name, regs, comment, via)
        msg = f"{doctype} {name} via {via}: {added} warranty(ies) registered, {len(skipped)} line(s) skipped, comment {comment}"
        store.event("processed", msg)
        return msg


def _before(at: str, seconds: int) -> str:
    return (datetime.fromisoformat(at[:19]) - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def reconcile(store, tenant, since: str, time_left=None, overlap_s: int = 0, floor=None) -> dict:
    """The pull that finds every submitted sale modified since the watermark. ``time_left()`` says when to stop for now: the
    watermark stays where it got to, so the next pass goes on from there. A pull with no webhook beside it reads ``overlap_s``
    back: tills commit out of order, so a sale can be stamped before one already seen. ``floor(doctype)`` is ``(the first
    stamp, the first posting date)`` to read: a sale from before those is not new, also when it is saved again today."""
    out = {}
    for dt in DOCTYPES:
        wm = store.watermark(dt, since)
        done, (first, from_day) = 0, floor(dt) if floor else (None, None)
        look = max(_before(wm, overlap_s), first or "") if overlap_s else wm
        while True:
            filters = [["docstatus", "=", 1], ["modified", ">=", look]]
            if from_day:
                filters.append(["posting_date", ">=", from_day])
            rows = tenant.list(dt, ["name", "modified"], filters, "modified asc", 200)
            newest = wm
            for r in rows:
                if time_left is not None and time_left() <= 0:
                    rows = []
                    break
                try:
                    process(store, tenant, dt, r["name"], "reconcile")
                except Exception as e:   # any failure: stop here, keep the watermark before it, say so
                    store.event("error", f"reconcile {dt} {r['name']}: {type(e).__name__}: {e}"[:300])
                    rows = []   # stop here: the watermark stays before the failure, so it is retried
                    break
                newest, done = max(newest, r["modified"]), done + 1
            if newest != wm:
                store.set_watermark(dt, newest)
            if len(rows) < 200 or newest == wm:
                break
            wm = look = newest
        out[dt] = done
    store.event("reconcile", json.dumps(out))
    return out
