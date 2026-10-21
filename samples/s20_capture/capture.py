"""S20 — *Warranty capture and a member code*: the pure core (no framework, no network), shared by the service and tests.

The till asks at three moments the cashier did not choose (the capture extension point, ``capture/1``), one signed POST each:

- **on scan** of an item in the shop's named item groups, before its line goes on the sale. This service answers *allow*
  with a warranty reference on the line (``line_attributes``: one row of an active line attribute the shop keeps; the
  cashier sees it on a confirm sheet first). The till sends **no line id** (the line does not exist until the answer lets
  it on), so the reference is a new one per scan and nothing here keys on a line;
- **on customer add**, before the customer is created: *refuse* without a phone or for a phone the shop has barred,
  else *challenge* — it sends the customer a code
  and the till shows a code field. The code comes back as ``verify`` with the same ``challenge_id``: *ok* or *refuse*.
  The product counts the tries (three wrong codes end it) and is the gate on the till: no customer is created there
  without an answer it recorded (an offline sale's customer, and the receipt's contact after payment, are created and
  flagged instead — the customer has paid).
- **on a quantity change** of a line in the named item groups (POS build 2.0.0.654 on): the till sends the line's last
  allowed quantity and the new one, once the presses settle. Up to ``PP_QTY_ASK_ABOVE`` on a line (3) are allowed, up
  to ``PP_QTY_MOST`` (5) asked about, more refused (a serial- or lot-tracked line is never asked): a refusal or a *No* puts the last allowed quantity back.

⛔ No answer writes a customer field, and none moves money: no price, no total, no tender.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time

SKEW_S = 300
BODY_MAX = 256 * 1024
CODE_TTL_S = 10 * 60       # the product's own challenge lifetime: a code older than this is never accepted
CODE_LENGTH = 6
_PHONE = re.compile(r"[^0-9+]")


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not (base64 HMAC-SHA256 of ``<timestamp>.<raw body>``)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


def context_of(body: dict) -> dict:
    """The call's context, or ``ValueError`` — only the shape this sample reads, by event."""
    if not isinstance(body, dict) or body.get("point") != "capture/1":
        raise ValueError("not a capture/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1:
        raise ValueError("no context")
    event = ctx.get("event")
    if event == "scan" and isinstance(ctx.get("line"), dict) and ctx["line"].get("item_code"):
        return ctx
    if event == "customer_add" and isinstance(ctx.get("customer"), dict) and _id(ctx.get("challenge_id")):
        return ctx
    if event == "verify" and _id(ctx.get("challenge_id")) and isinstance(ctx.get("code"), str):
        return ctx
    if event == "qty_change" and isinstance(ctx.get("line"), dict) and isinstance(ctx["line"].get("qty_milli"), int):
        return ctx
    raise ValueError("not an event this service answers")


def _id(x) -> bool:
    return isinstance(x, str) and 8 <= len(x) <= 64


def settings_from(env: dict) -> dict:
    return {"attribute": (env.get("PP_LINE_ATTRIBUTE") or "").strip(),
            "barred": {phone(x) for x in (env.get("PP_BARRED_PHONES") or "").split(",") if phone(x)},
            "ask_above": _whole(env.get("PP_QTY_ASK_ABOVE"), 3), "most": _whole(env.get("PP_QTY_MOST"), 5)}


def _whole(raw, default: int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def phone(raw) -> str:
    return _PHONE.sub("", str(raw or ""))


def warranty_ref() -> str:
    """A new reference for each scan. The till sends no line id (the line does not exist until the answer lets it on),
    and two units of one model scanned by their item barcode look the same, so nothing here keys on the scan."""
    return "WR-" + secrets.token_hex(5).upper()


def on_scan(ctx: dict, conf: dict) -> dict:
    """The product already filtered by item group; this service puts its reference on the line."""
    if not conf["attribute"]:
        return {"verdict": "allow"}             # nothing to record: the line goes on untouched
    return {"verdict": "allow", "line_attributes": [{"name": conf["attribute"], "value": warranty_ref()}]}


def on_qty(ctx: dict, conf: dict) -> dict:
    """A quantity change of a line in the named group: the product already filtered by item group and sends the NEW quantity,
    ``qty_milli`` (thousandths), beside the last allowed one. Judge the new one only; never set a quantity."""
    qty, item = ctx["line"]["qty_milli"] / 1000, str(ctx["line"].get("item_code") or "")[:40]
    if qty <= conf["ask_above"]:
        return {"verdict": "allow"}
    if qty <= conf["most"]:
        return {"verdict": "confirm",
                "question": f"{qty:g} of {item} on one line. Has a manager agreed to more than {conf['ask_above']}?"}
    return {"verdict": "refuse", "reason": f"At most {conf['most']} of {item} on one line."}


class Codes:
    """The codes this service sent, by ``challenge_id`` — in this process, ten minutes each.
    A partner running several processes keeps them in its own database."""

    def __init__(self, clock=time.time):
        self.clock, self._lock = clock, threading.Lock()
        self.pending: dict[str, tuple[str, str, float]] = {}     # challenge_id -> (code, phone, sent at)

    def _purge(self, now):
        self.pending = {k: v for k, v in self.pending.items() if now - v[2] < CODE_TTL_S}

    def issue(self, challenge_id: str, number: str) -> str:
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
        with self._lock:
            now = self.clock()
            self._purge(now)
            self.pending[challenge_id] = (code, number, now)
        return code

    def check(self, challenge_id: str, code: str) -> str:
        """``ok`` · ``wrong`` · ``unknown`` (never sent, or older than ten minutes). A right code is spent."""
        with self._lock:
            now = self.clock()
            self._purge(now)
            found = self.pending.get(challenge_id)
            if not found:
                return "unknown"
            if not hmac.compare_digest(found[0], code):
                return "wrong"
            del self.pending[challenge_id]
            return "ok"


def on_customer(ctx: dict, conf: dict, codes: Codes, send) -> dict:
    """``send(phone, code)`` is the partner's own message gateway (SMS, WhatsApp); it is called before the answer."""
    number = phone(ctx["customer"].get("phone"))
    if not number:
        return {"verdict": "refuse", "reason": "A mobile number is needed to join. Ask the customer for one."}
    if number in conf["barred"]:
        return {"verdict": "refuse", "reason": "This number can't join the club. Ask the customer for another one."}
    send(number, codes.issue(ctx["challenge_id"], number))
    return {"verdict": "challenge", "prompt": f"Ask the customer for the {CODE_LENGTH}-digit code we just sent.",
            "length": CODE_LENGTH}


def on_verify(ctx: dict, codes: Codes) -> dict:
    result = codes.check(ctx["challenge_id"], ctx["code"])
    if result == "ok":
        return {"verdict": "ok"}
    if result == "wrong":
        return {"verdict": "refuse", "reason": "That code is not right."}
    return {"verdict": "refuse", "reason": "This code has expired. Add the customer again."}
