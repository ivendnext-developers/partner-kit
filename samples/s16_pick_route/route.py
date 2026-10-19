"""S16 — *Assign pick route*: the pure core (no framework, no network), shared by the service and its tests.

The shop's Desk button sends one signed POST per press (the Desk action extension point, ``desk_action/1``):

    {"point": "desk_action/1", "context": {"v": 1, "action", "label", "user", "lang",
                                           "records": [{"doctype", "name", "fields": {...send_fields...}}],
                                           "inputs": {"picker", "priority"}, "idempotency_key"}}

``verify`` checks the signature the shop puts on every call; ``plan`` turns one record into the pick task the
service creates over the record API; ``answer`` builds the reply in the extension point's closed vocabulary
(a ``message`` plus at most one of ``open_record`` · ``refresh``). ⛔ The answer never writes anything: the
task is written by the service itself, with its own API key and its own rights, BEFORE it answers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

TASK = "PP PCK Pick Task"
SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024


def use_prefix(prefix: str):
    """The record types under another prefix: ``IVENDNEXT PCK`` for the App library's app."""
    global TASK
    TASK = f"{prefix} Pick Task"


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


def context_of(body: dict) -> dict:
    """The press's context, or ``ValueError`` — only the shape this sample needs, checked before any write."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list) or not ctx["records"]:
        raise ValueError("no records")
    key = ctx.get("idempotency_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 64:
        raise ValueError("no idempotency key")
    inputs = ctx.get("inputs") or {}
    if not isinstance(inputs.get("picker"), str) or not inputs["picker"]:
        raise ValueError("no picker")
    return ctx


def plan(record: dict, inputs: dict, key: str) -> dict:
    """The pick task for one Sales Order: its lines in walking order (warehouse, then item). Quantities arrive in
    THOUSANDTHS (an integer, the extension points' one rule), so 2.5 units arrive as 2500."""
    f = record["fields"]
    rows = sorted(f.get("items") or [], key=lambda r: (r.get("warehouse") or f.get("set_warehouse") or "",
                                                     r.get("item_code") or ""))
    lines = [{"item_code": r["item_code"], "qty": (r.get("qty") or 0) / 1000,
              "warehouse": r.get("warehouse") or f.get("set_warehouse"), "stop": i + 1} for i, r in enumerate(rows)]
    return {"doctype": TASK, "sales_order": record["name"], "customer": f.get("customer"),
            "picker": inputs["picker"], "priority": inputs.get("priority") or "Normal",
            "pick_by": f.get("delivery_date"), "press_key": key, "lines": lines}


def summary(tasks: list[dict]) -> str:
    lines = sum(len(t["lines"]) for t in tasks)
    places = len({ln["warehouse"] for t in tasks for ln in t["lines"]})
    return f"{lines} line{'s' if lines != 1 else ''} across {places} warehouse{'s' if places != 1 else ''}"


def answer(tasks: list[dict], names: list[str], mode: str = "open") -> dict:
    """The reply. One order: the message, then its task opens. Several (the list's bulk press): the message only.
    ``mode`` is for the sample's own tests (``refresh``: S2's answer; ``missing``: S3's, naming no record)."""
    if mode == "missing":
        return {"open_record": {"doctype": TASK, "name": "PT-404"}}
    picker = tasks[0]["picker"]
    if len(tasks) > 1:
        return {"message": {"title": f"{len(tasks)} routes assigned",
                            "body": f"{summary(tasks)} for {picker}.", "level": "success"}}
    msg = {"title": "Route assigned", "body": f"{summary(tasks)} for {picker}.", "level": "success"}
    if mode == "refresh":
        return {"refresh": True, "message": msg}
    return {"message": msg, "open_record": {"doctype": TASK, "name": names[0]}}
