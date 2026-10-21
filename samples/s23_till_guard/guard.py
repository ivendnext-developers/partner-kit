"""S23 — *Till guard rules*: the pure core (no framework, no network), shared by the service and its tests.

Two extension points, one app:

- **a check before payment** (``check/1``): when the cashier presses Pay, the shop's server sends its own priced basket.
  ``on_check`` refuses a line priced at or below the shop's placeholder price (a free line, priced 0, is never refused),
  refuses a line holding more of one item than the shop allows (line by line: a promotion may split one item across
  lines), and asks the cashier (``ask``, the default) — or calls a manager (``approve``), if the shop chose it — for a
  sale at or above the shop's approval amount. Otherwise it allows.
- **a capture on scan** (``capture/1``): the product calls it only for an item whose *Confirm at the till when scanned*
  field is ticked (the manifest's filter), before its line goes on the sale. ``on_scan`` answers ``confirm`` with the
  shop's question: a beep and a yes/no. If the shop switched on *Warn of a shorter-dated batch* instead,
  ``on_scan_shelf`` answers ``notice`` when the store holds a batch of the item that expires sooner: the item goes on
  with no tap and the till shows the sentence (from POS build 2.0.0.654; an older build refuses ``notice``).

The rules come from the shop's own settings record (``settings_of``), each off until the shop sets it. The rules are
about selling: what a sale or a return takes back (a negative quantity) is never judged, and what a return sells (an
exchange rung without its sale) is judged by the line rules, as a sale's lines are. The large-sale rule reads the total the
customer pays: a sale's, or an exchange's net of what it takes back (a plain return's total is below zero, so never).

⛔ No answer moves money: no price, no line, no payment. A refused sale is not paid — the till goes back to the basket,
and the door before any money refuses a sale without an allowing answer for exactly this basket.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
QUESTION = "Check this item before it goes on the sale. Add it?"
NO_RULES = {"max_qty": 0.0, "lowest_price": 0.0, "approval_from": 0.0, "approval_answer": "ask", "question": QUESTION,
            "shelf_warning": False}


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


def check_context(body: dict) -> dict:
    """The check's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    if not isinstance(ctx.get("lines"), list) or not isinstance(ctx.get("totals"), dict):
        raise ValueError("no lines or totals")
    if not isinstance(ctx.get("currency_exponent"), int) or not isinstance(ctx["totals"].get("grand_minor"), int):
        raise ValueError("money is whole minor units")
    for line in ctx["lines"]:
        if not isinstance(line, dict) or not isinstance(line.get("qty_milli"), int) or not isinstance(line.get("rate_minor"), int):
            raise ValueError("a line's quantity and price are whole numbers")
    return ctx


def scan_context(body: dict) -> dict:
    """The capture's scan context, or ``ValueError``. This app answers the scan event only."""
    if not isinstance(body, dict) or body.get("point") != "capture/1":
        raise ValueError("not a capture/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("event") != "scan":
        raise ValueError("not a scan")
    if not isinstance(ctx.get("line"), dict) or not ctx["line"].get("item_code"):
        raise ValueError("no line")
    return ctx


def _number(value) -> float:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return n if n > 0 else 0.0


def settings_of(doc: dict | None) -> dict:
    """The shop's rules from its settings record (``<prefix> Settings``, record ``Default``); no record = every rule off.
    A blank, zero, negative or unreadable number switches its rule off."""
    if not doc:
        return dict(NO_RULES)
    answer = (doc.get("approval_answer") or "ask").strip().lower()
    return {"max_qty": _number(doc.get("max_qty_per_line")), "lowest_price": _number(doc.get("lowest_unit_price")),
            "approval_from": _number(doc.get("approval_from")),
            "approval_answer": answer if answer in ("approve", "ask") else "ask",
            "question": plain(doc.get("confirm_question") or "") or QUESTION,
            "shelf_warning": str(doc.get("warn_shorter_shelf_life") or "0").strip() in ("1", "True", "true")}


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable, no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _minor(amount: float, exp: int) -> int:
    return round(amount * 10 ** exp)


def money(minor: int, exp: int, currency: str = "") -> str:
    return f"{minor / 10 ** exp:,.{exp}f} {currency or ''}".strip()


def _qty(milli: int) -> str:
    return f"{milli / 1000:g}"


def sold_lines(ctx: dict) -> list:
    """The lines this check sells: those with a positive quantity, on a sale or a return. An exchange rung without its
    sale carries the items it sells that way, and the contract says judge them as a sale's; a returned line is not judged."""
    return [line for line in ctx["lines"] if line["qty_milli"] > 0]


def on_check(ctx: dict, rules: dict) -> dict:
    """The answer for one check: the first refusal on a sold line, then the large-sale rule on the total paid, else allow."""
    exp, cur = ctx["currency_exponent"], ctx.get("currency") or ""
    floor = _minor(rules["lowest_price"], exp) if rules["lowest_price"] else 0
    most = round(rules["max_qty"] * 1000) if rules["max_qty"] else 0
    for line in sold_lines(ctx):
        item, n = plain(line.get("item_code") or "", 40), line.get("line_no") or ""
        if floor and 0 < line["rate_minor"] <= floor:
            return {"verdict": "refuse", "reason": plain(
                f"Line {n}: {item} is priced {money(line['rate_minor'], exp, cur)}. Correct its price before the sale is paid.")}
        if most and line["qty_milli"] > most:
            return {"verdict": "refuse", "reason": plain(
                f"Line {n}: {_qty(line['qty_milli'])} of {item}. The most on one line is {_qty(most)}.")}
    if rules["approval_from"]:          # the total the customer pays: on an exchange, net of what it takes back
        limit = _minor(rules["approval_from"], exp)
        if ctx["totals"]["grand_minor"] >= limit:
            amount = money(limit, exp, cur)
            if rules["approval_answer"] == "ask":
                return {"verdict": "ask", "question": plain(f"This sale is {amount} or more. Has a manager agreed to it?")}
            return {"verdict": "approve", "reason": plain(f"Sales of {amount} or more need a manager's approval.")}
    return {"verdict": "allow"}


def on_scan(ctx: dict, rules: dict) -> dict:
    """A flagged item (the product filtered by the item's own tick): a beep and the shop's question."""
    item = plain(ctx["line"].get("item_code") or "", 40)
    return {"verdict": "confirm", "question": plain(f"{item}: {rules['question']}")}


def on_scan_shelf(ctx: dict, dated: list) -> dict:
    """*Warn of a shorter-dated batch*: ``dated`` is the store's batches of the item with stock and an expiry date, as
    ``(expiry ISO date, batch)``. A scan that names its batch is warned when another batch expires sooner; a scan that
    names none (an ordinary item barcode) is warned when the store's batches expire on different days, naming the one
    to sell first. Otherwise allow: nothing is shown, and the item goes on either way."""
    if not dated:
        return {"verdict": "allow"}
    expiry, first = min(dated)
    item, scanned = plain(ctx["line"].get("item_code") or "", 40), ctx["line"].get("batch_no") or ""
    if scanned:
        mine = dict((b, e) for e, b in dated).get(scanned)
        if not mine or expiry >= mine:
            return {"verdict": "allow"}
        return {"verdict": "notice", "message": plain(f"{item}: batch {first} expires sooner ({expiry}). Sell it first.")}
    if len({e for e, _ in dated}) < 2:
        return {"verdict": "allow"}
    return {"verdict": "notice", "message": plain(f"{item}: sell batch {first} first. It expires {expiry}.")}
