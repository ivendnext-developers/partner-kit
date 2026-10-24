"""S51 — *Refund rules*: the pure core (no framework, no network), shared by the service and its tests.

A **check before payment** (``check/1``) that judges refunds only. Before the refund choices open on every refund the till
pays (``stage: "return"``), the retailer's server sends the refund, the methods the refund chooser offers
(``offered_tenders``) and the original it refunds (``return_of``: the sale, an order or a layaway plan, with ``paid_by``, the
names of the payment methods that paid it). The retailer keeps one settings record (``<prefix> Settings``, named
``Default``; no record: every rule off) and ``on_check`` answers:

- **Refund by the sale's own methods** (``same_methods``): on a return against a sale, an order or a plan, the methods that
  paid it, the retailer's store credit method and its *Always allowed* methods stay; every other offered method is taken off
  (``exclude_tenders``), and when none would stay the refund is refused;
- **Without its sale, only these methods** (``without_sale``): on a return without its sale, the named methods and the
  store credit method stay, every other offered method is taken off, and when none of them is offered the refund is
  refused. None named: with the methods rule on, the *Always allowed* methods and store credit stay (or a return without
  its receipt would be the way round the rule); with it off, as today.

``offered_tenders`` is the POS Profile's whole payment table, a method the store switched off for returns included (the
till grades its rows, never filters them, other than the methods no refund may use): a refusal fires only when none of
those would stay.

Which store's sales a till may refund is the retailer's own setting, not this app's: with *Use inter-store transactions*
off (Retail Setting, the default) a till opens only its own store's sales for a return.

A sale (``stage: "sale"``) and a return whose total is 0 or more are allowed without a rule. An exchange's returned items
are always a return with a negative total (their credit note is checked alone), so they are judged. The store credit method is never taken off, so an exchange, whose returned
items book store credit, goes on.

⛔ No answer moves money: no price, no line, no amount. The check names methods, never amounts.

``verify`` and ``plain`` are S50's (``samples/s50_required_sale_details/details.py``, S46's before it), copied: a defect
there is a defect here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till shows: plain text, 1 to 140 characters (the extension points' rule)
EXCLUDE_MAX = 20      # the check takes off 1 to 20 methods (the contract's limit)


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the retailer's, else why not. The signature is base64 HMAC-SHA256 of
    ``<timestamp>.<raw body>`` with the subscription's secret (the installer handed it back once)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit() and len(ts) <= 12) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def _texts(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def check_context(body: dict) -> dict:
    """The check's context, or ``ValueError`` — only the shape this app reads, checked before any decision."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    if ctx["stage"] == "sale":
        return ctx
    totals = ctx.get("totals")
    if not isinstance(totals, dict) or not isinstance(totals.get("grand_minor"), int) or isinstance(totals["grand_minor"], bool):
        raise ValueError("a return's totals carry its grand total")
    if not _texts(ctx.get("offered_tenders")):
        raise ValueError("a return names the methods offered")
    ro = ctx.get("return_of")
    if not isinstance(ro, dict) or not isinstance(ro.get("invoice"), str) or not isinstance(ro.get("channel"), str) \
            or not _texts(ro.get("paid_by")):
        raise ValueError("a return names what it refunds and the methods that paid it")
    return ctx


def _methods(rows) -> list:
    """The Modes of Payment of a settings table, in the order kept, each once."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        mop = r.get("mode_of_payment") if isinstance(r, dict) else None
        if isinstance(mop, str) and mop and mop not in out:
            out.append(mop)
    return out


def settings_of(doc) -> dict | None:
    """The retailer's settings from its record (``None``: no record, every rule off). Anything that is not a record is
    ``ValueError``."""
    if doc is None:
        return None
    if not isinstance(doc, dict):
        raise ValueError("the retailer's settings are not a record")
    credit = doc.get("store_credit")
    return {"same_methods": doc.get("same_methods") in (1, "1", True),
            "store_credit": credit if isinstance(credit, str) else "",
            "always": _methods(doc.get("always_allowed")),
            "without_sale": _methods(doc.get("without_sale"))}


MARKS = "‌‍‎‏؜"   # joiners and direction marks Arabic and Persian text carries: the till keeps them


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable (and the marks it allows), no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable() or ch in MARKS).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _names(methods) -> str:
    return plain(", ".join(methods), 60)


def on_check(ctx: dict, settings: dict | None) -> dict:
    """The answer for one check."""
    if ctx["stage"] != "return" or ctx["totals"]["grand_minor"] >= 0 or not settings:
        return {"verdict": "allow"}
    ro, offered = ctx["return_of"], ctx["offered_tenders"]
    credit = [settings["store_credit"]] if settings["store_credit"] else []     # never taken off: an exchange books it
    if ro["channel"] == "none":
        if settings["without_sale"]:
            keep = list(dict.fromkeys(settings["without_sale"] + credit))
        elif settings["same_methods"]:          # no methods named: the methods rule still holds, or a no-receipt return
            keep = list(dict.fromkeys(settings["always"] + credit))   # would be the way round it (the review's MAJOR)
        else:
            return {"verdict": "allow"}
        if not keep:                            # nothing set for it (a blank store credit method written over the API)
            return {"verdict": "refuse", "reason": "No method is set for a return without its sale. Get a manager."}
        some = plain(f"Without its sale, refunded only by {_names(keep)}.")
        none = plain(f"A return without its sale is refunded only by {_names(keep)}, not offered at this till.")
    elif settings["same_methods"]:
        keep = list(ro["paid_by"]) + settings["always"] + credit
        some = "Refunded only by the methods your rules keep for this sale."
        none = "None of the methods that paid for this can take its refund here. Get a manager."
    else:
        return {"verdict": "allow"}
    off = [t for t in dict.fromkeys(offered) if t not in keep]
    if not off:
        return {"verdict": "allow"}
    if len(off) == len(dict.fromkeys(offered)):
        return {"verdict": "refuse", "reason": none}
    if len(off) > EXCLUDE_MAX:
        return {"verdict": "refuse", "reason": "This till offers more methods than the refund rules can take off. Get a manager."}
    return {"verdict": "allow", "exclude_tenders": off, "reason": some}
