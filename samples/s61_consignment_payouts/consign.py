"""S61 — *Consignment payouts*: the pure core (no framework, no network), shared by the service and its tests.

The retailer's two Desk buttons on a draft payout (the Desk action extension point, ``desk_action/1``) each send one
signed POST per press:

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang",
                                           "records": [{"doctype": "PP CSG Payout", "name", "fields": {"name"}}],
                                           "inputs": {}, "idempotency_key"}}

``verify`` checks the signature the retailer's site puts on every call; ``payout_of`` takes the press's one payout;
``work_out`` turns the consignor's items, their sale lines, those sales' headers and the lines other payouts already hold
into the payout's lines; ``check_to_pay`` compares a payout's lines with what a work-out gives now, before the service
marks it paid; the ``*_answer`` functions build the reply in the extension point's closed vocabulary. ⛔ The answer never
writes anything: the service writes the payout itself, with its own API key and its own rights, BEFORE it answers.

A **sold line** is a line of a submitted till sale (POS Invoice) or of a submitted Desk invoice that is not the till
day's combined invoice (Sales Invoice, ``is_consolidated`` 0: the combined invoice repeats the till's lines), in the
payout's company, dated from the consignor's *Consigned since* to the payout's *Up to*. Its amount is ``base_net_amount``: after discounts, before tax, in the
company's currency. A return's line is negative. A line on any payout that is not Cancelled is never put on another.
A line whose sale was cancelled after a PAID payout held it comes back once, negative, as *Cancelled after payout*.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PREFIX = "PP CSG"
CONSIGNOR, PAYOUT, LINE = "PP CSG Consignor", "PP CSG Payout", "PP CSG Payout Line"
FIELD = "pp_csg_"                       # the prefix of the two fields on Item: <FIELD>consignor, <FIELD>share
DRAFT, PAID, CANCELLED = "PP CSG Draft", "PP CSG Paid", "PP CSG Cancelled"
LOCK_RULE = "PP CSG payout locked once paid"
SALE_TYPES = ("POS Invoice", "Sales Invoice")
SALE, RETURN, REVERSAL = "Sale", "Return", "Cancelled after payout"
UNDONE = "/cancelled"                    # a reversal's line key: the sale line's own, with this after it
SKEW_S = 300                             # a request stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024
MOST_LINES = 500                         # a payout's lines, oldest first; the rest wait for the next payout
CENT = Decimal("0.01")
LINE_FIELDS = ("sale_type", "sale", "sale_line", "kind", "posting_date", "item_code", "item_name", "qty",
               "sale_amount", "share", "payout")
COMPARED = ("sale_type", "sale", "kind", "item_code", "sale_amount", "share", "payout")


def use_prefix(prefix: str):
    """Every name under another prefix: *IVENDNEXT CSG Payout* and the field ``ivendnext_csg_consignor`` for the library's app."""
    global PREFIX, CONSIGNOR, PAYOUT, LINE, FIELD, DRAFT, PAID, CANCELLED, LOCK_RULE
    PREFIX = prefix
    CONSIGNOR, PAYOUT, LINE = f"{prefix} Consignor", f"{prefix} Payout", f"{prefix} Payout Line"
    FIELD = prefix.lower().replace(" ", "_") + "_"
    DRAFT, PAID, CANCELLED = f"{prefix} Draft", f"{prefix} Paid", f"{prefix} Cancelled"
    LOCK_RULE = f"{prefix} payout locked once paid"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the retailer's site's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def payout_of(body: dict) -> tuple[str, str]:
    """(the payout's name, the pressing user), or ``ValueError`` — checked before anything is read or written."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if len(ctx["records"]) != 1:
        raise ValueError("one payout a press")
    rec = ctx["records"][0]
    if not isinstance(rec, dict) or rec.get("doctype") != PAYOUT or not isinstance(rec.get("name"), str) or not rec["name"]:
        raise ValueError("not a payout")
    user = ctx.get("user")
    return rec["name"], user if isinstance(user, str) else ""


def date_of(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def money(v) -> Decimal | None:
    """An amount as the site sent it, exactly (never through a float's rounding), or None when it is not one."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def share_of(v) -> Decimal | None:
    """A share in percent: above 0 and at most 100; blank or 0 is None (the consignor's own share applies)."""
    d = money(v) if v not in (None, "") else Decimal(0)
    if d is None or d < 0 or d > 100:
        raise ValueError
    return d if d > 0 else None


def payout_amount(amount: Decimal, share: Decimal) -> Decimal:
    """The consignor's part of one line, to the cent, half away from zero (a return's part is the same, negative)."""
    return (amount * share / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def _key(row: dict) -> str:
    return str(row.get("sale_line") or "")


def holds_of(rows: list[dict], states: dict[str, str], this: str) -> dict[str, dict]:
    """The lines other payouts hold: ``{sale line key: {"payout", "state", the line}}``. A Cancelled payout holds none,
    and this payout's own lines are not a hold on itself."""
    out = {}
    for r in rows:
        p, k = r.get("parent"), _key(r)
        st = states.get(p)
        if not k or not p or p == this or st is None or st == CANCELLED:
            continue
        out.setdefault(k, dict(r, payout_name=p, state=st))
    return out


def work_out(consignor_share, items: dict, lines: list[dict], heads: dict, holds: dict, company: str,
             up_to: datetime.date, since: datetime.date | None = None) -> tuple[list[dict], str]:
    """(every line the consignor is owed now, oldest first; or ``[]`` and the words saying why not).

    ``items``: ``{item code: {"item_name", "share"}}`` (the consignor's items, their own share as the site holds it);
    ``lines``: sale lines, each ``{"sale_type", "name", "parent", "item_code", "item_name", "qty", "base_net_amount"}``;
    ``heads``: ``{(sale type, sale): {"docstatus", "company", "posting_date", "is_return", "is_consolidated"}}``;
    ``holds``: ``holds_of`` for every key of these lines and their reversals; ``since``: the consignor's *Consigned
    since*, before which no sale is theirs (an item named to them later keeps its earlier sales off their payouts)."""
    try:
        own = share_of(consignor_share)
    except ValueError:
        return [], "The consignor's share must be a percent above 0 and at most 100."
    if own is None:
        return [], "The consignor has no share yet: fill it on the consignor, then work the payout out again."
    shares = {}
    for code, it in items.items():
        try:
            shares[code] = share_of((it or {}).get("share")) or own
        except ValueError:
            return [], f"The consignor's share on item {code} must be a percent from 0 to 100."
    out = []
    for ln in lines:
        code, typ = ln.get("item_code"), ln.get("sale_type")
        head = heads.get((typ, ln.get("parent")))
        day = date_of((head or {}).get("posting_date"))
        if code not in shares or typ not in SALE_TYPES or not head or not ln.get("name") or not day:
            continue
        if head.get("company") != company or day > up_to or (since and day < since) \
                or (typ == "Sales Invoice" and head.get("is_consolidated")):
            continue
        key, status = str(ln["name"]), head.get("docstatus")
        if status == 1:
            if key in holds:
                continue
            amount = money(ln.get("base_net_amount"))
            if amount is None:
                continue
            share = shares[code]
            out.append({"sale_type": typ, "sale": ln["parent"], "sale_line": key,
                        "kind": RETURN if head.get("is_return") else SALE, "posting_date": day.isoformat(),
                        "item_code": code, "item_name": ln.get("item_name") or (items.get(code) or {}).get("item_name") or "",
                        "qty": ln.get("qty") or 0, "sale_amount": amount, "share": share,
                        "payout": payout_amount(amount, share)})
        elif status == 2:
            held, back = holds.get(key), key + UNDONE
            if not held or held["state"] != PAID or back in holds:
                continue                    # never paid (a draft's Pay refuses it), or already taken back
            paid, part = money(held.get("sale_amount")), money(held.get("payout"))
            if paid is None or part is None:
                continue
            out.append({"sale_type": typ, "sale": ln["parent"], "sale_line": back, "kind": REVERSAL,
                        "posting_date": day.isoformat(), "item_code": code,
                        "item_name": ln.get("item_name") or held.get("item_name") or "",
                        "qty": -(ln.get("qty") or 0), "sale_amount": -paid, "share": money(held.get("share")) or Decimal(0),
                        "payout": -part})
    out.sort(key=lambda r: (r["posting_date"], r["sale_type"], r["sale"], r["sale_line"]))
    return out, ""


def totals(rows: list[dict]) -> tuple[Decimal, Decimal]:
    return sum((r["sale_amount"] for r in rows), Decimal(0)), sum((r["payout"] for r in rows), Decimal(0))


def as_written(rows: list[dict]) -> list[dict]:
    """The payout's table rows as the service writes them (amounts as plain numbers the site stores to the cent)."""
    return [{k: (float(r[k]) if isinstance(r[k], Decimal) else r[k]) for k in LINE_FIELDS} for r in rows]


def check_to_pay(payout: dict, owed: list[dict], holds: dict, lock: dict | None) -> str:
    """``""`` when the payout may be marked paid, else the words saying why not. ``owed`` is what a work-out gives now
    (every line, uncapped); ``holds`` the lines other payouts hold; ``lock`` the payout lock's row or None."""
    if payout.get("workflow_state") not in (DRAFT, None, ""):
        return "Only a draft payout can be paid. This one is already paid or cancelled."
    rows = [r for r in payout.get("lines") or [] if isinstance(r, dict)]
    if not rows:
        return "This payout has no lines. Work it out first."
    if not payout.get("paid_with") or not date_of(payout.get("paid_on")):
        return "Fill Paid with and Paid on first, then press Pay this payout again."
    if not lock or not lock.get("enabled") or lock.get("mode") != "refuse":
        return (f"Switch on the rule {LOCK_RULE} (Retail Save Rule, refuse) first: it keeps a paid payout as it was paid.")
    keys = [_key(r) for r in rows]
    if len(set(keys)) != len(keys) or not all(keys):
        return "A sale line is on this payout twice. Work it out again."
    now = {r["sale_line"]: r for r in owed}
    for r in rows:
        k = _key(r)
        if k in holds:
            return f"A line is also on payout {holds[k]['payout_name']}. Cancel one of them, then work this one out again."
        want = now.get(k)
        if not want:
            return "A line is no longer owed (its sale or item changed, or it was cancelled). Work the payout out again."
        if not all(_same(r.get(f), want[f]) for f in COMPARED):
            return "A line has changed since the payout was worked out. Work it out again, check it, then pay."
    _, part = totals([now[k] for k in keys])
    total = money(payout.get("payout_total"))
    if total is None or total.quantize(CENT) != part:
        return "The payout's total is not the sum of its lines. Work it out again."
    if part < 0:
        return "The returns are more than the sales: nothing is owed yet. Keep the payout as a draft until more sells."
    return ""


def _same(got, want) -> bool:
    """One field of a stored line against the work-out's: money to the cent, anything else as text."""
    if isinstance(want, Decimal):
        g = money(got)
        return g is not None and g.quantize(CENT) == want.quantize(CENT)
    return str(got or "") == str(want or "")


def _fit(text: str, most: int = 280) -> str:
    return text if len(text) <= most else text[: most - 1] + "…"


def _n(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def message(body: str, level: str = "success", refresh: bool = False, title: str = "Consignment payouts") -> dict:
    out = {"message": {"title": title, "body": _fit(body), "level": level}}
    if refresh:
        out["refresh"] = True
    return out


def summary_of(rows: list[dict], left: int, currency: str = "") -> str:
    """The words written on the payout and said to the user after *Work out the payout*."""
    if not rows:
        return "Nothing owed: no sold line of this consignor's items is waiting to be paid up to this date."
    sales, part = totals(rows)
    cur = f" {currency}" if currency else ""
    n = {k: sum(1 for r in rows if r["kind"] == k) for k in (SALE, RETURN, REVERSAL)}
    kinds = [_n(n[k], one, many) for k, one, many in ((SALE, "sale", "sales"), (RETURN, "return", "returns"),
             (REVERSAL, "sale cancelled after payout", "sales cancelled after payout")) if n[k]]
    body = f"{_n(len(rows), 'line', 'lines')}: {', '.join(kinds)}. Sold for {sales:,.2f}{cur}; the consignor's share {part:,.2f}{cur}."
    if left:
        body += f" {_n(left, 'older line waits', 'more lines wait')} for the next payout (at most {MOST_LINES} a payout)."
    if part < 0:
        body += " The returns are more than the sales: nothing to pay yet."
    return body


def paid_answer(part, currency: str = "") -> dict:
    cur = f" {currency}" if currency else ""
    return message(f"Paid: {Decimal(str(part)):,.2f}{cur}. The payout is locked; its lines will never be paid again.",
                   refresh=True)
