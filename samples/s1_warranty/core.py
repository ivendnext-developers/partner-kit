"""S1 warranty check (`pp_wrc`) — the PURE CORE.

It imports no framework and talks to nothing: every answer is a function of its arguments. The same
functions are bound twice — by the outside service (service/), and in-process at the till —
so a partner who starts outside moves inside without rewriting this file.

Shapes:
- ``context`` is exactly what the till's app button sends an app (``build_context`` in
  ivendnext_mpos/business_logic/app_button.py @ 05bb4dab): ``sale_ref``, ``store``, ``pos_profile``,
  ``company``, ``currency``, ``operator``, ``customer`` and ``lines`` — each line only ``item_code``,
  ``qty``, ``uom``, ``luid``. No prices and no serial numbers.
- ``terms`` is the partner's own reference data::

      {"items":      {"<item code>": <months>},     # an item's own term wins
       "groups":     {"<item group>": <months>},    # else its group's
       "item_group": {"<item code>": "<group>"}}    # which items exist, and their group

  A binding fills ``item_group`` for the items it was asked about (over the API outside; from the
  database inside). An item missing from it is an UNKNOWN item.
"""

from __future__ import annotations

import calendar
from datetime import date

# The till's closed answer vocabulary, as validate_result enforces it
# (ivendnext/iVendNext_PWA · apps/ivendnext_mpos/ivendnext_mpos/business_logic/app_button.py @ 05bb4dab,
# lines 33-37). A defect here is a defect there — report it on Retail mPOS's board.
TITLE_MAX = 60
BODY_MAX = 280
LEVELS = ("info", "success", "warning")

COVERED, NOT_COVERED, UNKNOWN = "covered", "not covered", "unknown item"


def term_for(item_code: str, terms: dict) -> tuple[str, int | None]:
    """``(status, months)`` for one item: its own term, else its group's, else none."""
    items = terms.get("items") or {}
    groups = terms.get("groups") or {}
    group_of = terms.get("item_group") or {}
    if item_code not in group_of and item_code not in items:
        return UNKNOWN, None
    if item_code in items:
        return COVERED, int(items[item_code])
    group = group_of.get(item_code)
    if group in groups:
        return COVERED, int(groups[group])
    return NOT_COVERED, None


def _fit(parts: list[str], cap: int) -> str:
    """Join parts with '; ', dropping trailing parts (named as '… and N more') to stay within cap."""
    for keep in range(len(parts), 0, -1):
        rest = len(parts) - keep
        text = "; ".join(parts[:keep]) + (f"; … and {rest} more" if rest else "")
        if len(text) <= cap:
            return text
    return f"{len(parts)} items — open the sale for detail"[:cap]


def warranty_answer(context: dict, terms: dict) -> dict:
    """The till's answer: one ``message`` naming each line's warranty. Always valid for the closed vocabulary."""
    seen, parts, statuses = set(), [], []
    for line in context.get("lines") or []:
        code = line.get("item_code")
        if not code or code in seen:
            continue
        seen.add(code)
        status, months = term_for(code, terms)
        statuses.append(status)
        parts.append(f"{code}: {months} months" if status == COVERED else f"{code}: {status}")
    if not parts:
        return {"message": {"title": "Warranty", "body": "There are no items on this sale yet.", "level": "info"}}
    if UNKNOWN in statuses:
        level = "warning"
    elif all(s == COVERED for s in statuses):
        level = "success"
    else:
        level = "info"
    return {"message": {"title": "Warranty", "body": _fit(parts, BODY_MAX), "level": level}}


def add_months(day: date, months: int) -> date:
    """``day`` plus whole months, clamped to the month's end (31 Jan + 1 month = 28/29 Feb)."""
    m = day.month - 1 + months
    year, month = day.year + m // 12, m % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def registrations(lines: list[dict], terms: dict, sold_on: date) -> tuple[list[dict], list[dict]]:
    """From a booked sale's lines (``{"item_code", "serials": [...]}``) to ``(registrations, skipped)``.

    One registration per covered serial number. A line with no serials, or an item with no term, is
    SKIPPED with its reason — never silently dropped.
    """
    regs, skipped = [], []
    for line in lines:
        code, serials = line.get("item_code"), [s for s in (line.get("serials") or []) if s]
        status, months = term_for(code, terms)
        if status != COVERED:
            skipped.append({"item_code": code, "reason": status})
            continue
        if not serials:
            skipped.append({"item_code": code, "reason": "no serial numbers on the line"})
            continue
        for serial in serials:
            regs.append({"serial_no": serial, "item_code": code, "months": months,
                         "starts": sold_on.isoformat(), "expires": add_months(sold_on, months).isoformat()})
    return regs, skipped


def comment_text(invoice: str, regs: list[dict], skipped: list[dict]) -> str:
    """The one Comment written on the sale — the result a shopkeeper sees in Desk."""
    if regs:
        head = f"Warranty registered for {len(regs)} serial number(s) on {invoice}:"
        body = [f"• {r['serial_no']} ({r['item_code']}): {r['months']} months, until {r['expires']}" for r in regs]
    else:
        head, body = f"No warranty registered on {invoice}.", []
    body += [f"• {s['item_code']}: not registered — {s['reason']}" for s in skipped]
    return "\n".join([head, *body, "— pp_wrc warranty sample (outside service)"])
