"""S22 — a settings record that drives the shop's own rules (the kit's *settings record drives rules* recipe).

A save rule and a notification hold their numbers and recipients themselves; the shop's people would rather change one
settings record (a record type of your own named ``Default``, as ``PP LYL Settings``). When that record is saved (its
event on the feed, once the record type is ticked on the feed registration), your handler calls ``sync``, which copies
its values into the records that enforce them. A standalone function: S22's own settings hold no limit and no
recipients, so S22 does not call it; the tests show it working.

  * a field link   {"from": <settings field>, "record_type": "Retail Save Rule", "record": <rule>, "field": "value"}
                   -> the rule's limit (or any field of any record the service's role may write);
  * a recipients link {"from": <settings field>, "record_type": "Notification", "record": <notification>,
                       "recipients": true}
                   -> the notification's recipient rows, one per e-mail address in the settings field (one per line or
                      comma-separated). Only rows that hold nothing but an address are the settings'; a row that
                      names a role, a field of the document, a condition or a blind copy is kept as it is.

``plan`` is pure: it says which records to write and with what, and nothing when they already match, so a replayed
event writes nothing. The records it writes are exactly the ones its links name. Standard library only.
"""

from __future__ import annotations

import re


def emails(text) -> list[str]:
    return sorted({e.strip() for e in re.split(r"[\n,;]", str(text or "")) if e.strip()})


def _only_cc(row: dict) -> bool:
    return bool(row.get("cc")) and not any(row.get(k) for k in ("bcc", "condition", "receiver_by_role", "receiver_by_document_field"))


def plan(settings: dict, links: list[dict], current: dict) -> list[tuple]:
    """``current`` = {(record type, record): the record as read}. Returns [(record type, record, body to PUT), …]."""
    out = []
    for link in links:
        dt, name = link["record_type"], link["record"]
        doc = current.get((dt, name))
        if doc is None:
            raise LookupError(f"{dt} {name} is named by a settings link but is not in the shop")
        value = settings.get(link["from"])
        if link.get("recipients"):
            rows = doc.get("recipients") or []
            mine = [r for r in rows if _only_cc(r)]
            others = [r for r in rows if not _only_cc(r)]
            if sorted(r["cc"] for r in mine) != emails(value):
                out.append((dt, name, {"recipients": others + [{"cc": e} for e in emails(value)]}))
        elif str(doc.get(link["field"])) != str(value):
            out.append((dt, name, {link["field"]: value}))
    return out


def sync(t, settings: dict, links: list[dict]) -> list[tuple]:
    """Read the linked records, write what differs. ``t`` is the shop (``get``, ``update``)."""
    current = {(link["record_type"], link["record"]): t.get(link["record_type"], link["record"]) for link in links}
    todo = plan(settings, links, current)
    for dt, name, body in todo:
        t.update(dt, name, body)
    return todo
