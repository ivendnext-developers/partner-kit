"""S2 bin locations (`pp_bln`) — the PURE CORE. No framework import, no network: every answer is a function of
its arguments, so the hosted till key and the outside service share it (and a remote key can, once it ships).

``rows`` are "what is in which bin" records, already limited to the till's store, each::

    {"name": "<record name>", "item": "<item code>", "bin": "<bin code>", "qty": <float>,
     "kind": "Shop floor" | "Back room", "movements": [{"kind", "qty", "reference"}, ...]}   (movements optional)

``context`` is the till's app-key context (no prices, no serials): only ``lines[].item_code`` is read.
"""

from __future__ import annotations

TITLE, BODY_MAX = "Where is it?", 280      # the till's caps: app_button.py @ mPOS 05bb4dab (TITLE_MAX 60, BODY_MAX 280)
FLOOR, BACK = "Shop floor", "Back room"


def _qty(x) -> str:
    return f"{float(x):g}"


def _fit(parts: list[str]) -> str:
    for keep in range(len(parts), 0, -1):
        rest = len(parts) - keep
        text = "; ".join(parts[:keep]) + (f"; … and {rest} more" if rest else "")
        if len(text) <= BODY_MAX:
            return text
    return f"{len(parts)} items — open Bins in Desk for detail"


def where_answer(context: dict, rows: list[dict]) -> dict:
    """One ``message`` naming, for each item on the sale, the bin it sits in: the shop floor first, else the back room."""
    seen, parts, found = set(), [], []
    for line in context.get("lines") or []:
        code = line.get("item_code")
        if not code or code in seen:
            continue
        seen.add(code)
        mine = sorted((r for r in rows if r.get("item") == code and float(r.get("qty") or 0) > 0),
                      key=lambda r: (-float(r["qty"]), r["bin"]))
        floor = [r for r in mine if r.get("kind") == FLOOR]
        back = [r for r in mine if r.get("kind") == BACK]
        if floor:
            more = f" (+{len(floor) - 1} more bin)" if len(floor) > 1 else ""
            parts.append(f"{code}: shop floor {floor[0]['bin']} ({_qty(floor[0]['qty'])}){more}")
            found.append(FLOOR)
        elif back:
            parts.append(f"{code}: back room {back[0]['bin']} ({_qty(back[0]['qty'])}), fetch it")
            found.append(BACK)
        else:
            parts.append(f"{code}: no bin recorded")
            found.append(None)
    if not parts:
        return {"message": {"title": TITLE, "body": "There are no items on this sale yet.", "level": "info"}}
    level = "warning" if None in found else ("success" if all(f == FLOOR for f in found) else "info")
    return {"message": {"title": TITLE, "body": _fit(parts), "level": level}}


def sale_decrements(sale_ref: str, lines: list[dict], rows: list[dict]) -> list[dict]:
    """What a booked sale takes off the shop floor: ``[{"name", "take", "short"}]`` per bin record touched.

    ``lines`` are the sale's ``[{"item_code", "qty"}]`` at this store; ``rows`` its shop-floor records WITH their
    movements. A record that already carries a ``Sale`` movement for ``sale_ref`` is skipped, and what the sale's
    earlier movements took OR reported short is subtracted first — so handling the same sale twice (a retry, a replay,
    the reconciliation pull) takes nothing more, even after a pick has refilled the floor. Never below zero: what the
    bins do not hold is ``short`` on the last record touched, written into its movement so the shop can see it.
    """
    def taken(r) -> float:   # what this record already ANSWERED for this sale: taken + reported short
        return sum(float(m.get("qty") or 0) + float(m.get("short") or 0) for m in r.get("movements") or []
                   if m.get("kind") == "Sale" and m.get("reference") == sale_ref)

    need: dict[str, float] = {}
    for line in lines:
        if line.get("item_code"):
            need[line["item_code"]] = need.get(line["item_code"], 0.0) + float(line.get("qty") or 0)
    plan = []
    for code, qty in need.items():
        floor = [r for r in rows if r.get("item") == code and r.get("kind") == FLOOR]
        qty -= sum(taken(r) for r in floor)
        mine = sorted((r for r in floor if not any(m.get("kind") == "Sale" and m.get("reference") == sale_ref
                                                    for m in r.get("movements") or [])),
                      key=lambda r: (-float(r.get("qty") or 0), r["bin"]))
        if qty <= 0:
            continue
        for r in mine:
            if qty <= 0:
                break
            take = min(qty, float(r.get("qty") or 0))
            if take > 0:
                plan.append({"name": r["name"], "take": take, "short": 0.0})
                qty -= take
        if qty > 0 and mine:
            if plan and plan[-1]["name"] in {r["name"] for r in mine}:
                plan[-1]["short"] = qty
            else:
                plan.append({"name": mine[0]["name"], "take": 0.0, "short": qty})
    return plan
