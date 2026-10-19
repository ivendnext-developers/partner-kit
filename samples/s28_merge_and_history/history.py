"""S28 — *Customer history*: the pure core of the partner page (no framework, no network), shared by the service and
its tests.

The shop opens the page with a signed, one-time context in the address's fragment (``…/mhs/history/#ctx=…``): from a
till key, with the sale as the till holds it (its ``customer``); in Desk, for a Customer record (``doctype``/``name``).
The page's own script sends it to the page's server, which checks it here (``read_context``: the signature over the
payload's bytes, the expiry; ``OnceSet``: the nonce once), then reads that customer's sales over the record API and
shapes them here (``pick``, ``visit``): the date, the store, who served, the sale's discount and each line's discount.

The sales are read from *POS Invoice* and from *Sales Invoice* rows that are **not** consolidated: a day's roll-up
invoice repeats the till's sales, so counting it would show each sale twice. ⛔ The page answers nothing to the sale.

``read_context`` and ``OnceSet`` are S17's (``samples/s17_partner_page/page.py`` @ fac54dd): a defect here is a defect
there — report it through the feedback forms (``feedback/README.md``). This copy adds a lock to ``OnceSet.claim``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import threading
import time
from decimal import Decimal

POS, SI = "POS Invoice", "Sales Invoice"
CLOCK_SKEW_S = 60
DEFAULT_COUNT, MAX_COUNT = 10, 50


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign_context(secret: str, payload: dict) -> str:
    """The shop's own minting, for tests: canonical JSON (sorted keys, no spaces, ASCII), then the HMAC."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return b64(raw) + "." + b64(hmac.new(secret.encode(), raw, hashlib.sha256).digest())


def read_context(ctx, secret: str, now: float | None = None) -> tuple[dict | None, str]:
    """``(payload, "")`` for a context the shop signed that has not run out, else ``(None, why)``. ⛔ The HMAC is
    checked BEFORE the payload is parsed, and over the bytes as they came."""
    if not isinstance(ctx, str) or ctx.count(".") != 1 or len(ctx) > 16384:
        return None, "the context is not one the shop made"
    body, sig = ctx.split(".")
    try:
        raw, got = _unb64(body), _unb64(sig)
    except (binascii.Error, ValueError):
        return None, "the context is not one the shop made"
    if not hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).digest(), got):
        return None, "the context's signature does not match"
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, "the context is not one the shop made"
    now = now or time.time()
    if not isinstance(payload, dict) or payload.get("v") != 1 or not isinstance(payload.get("nonce"), str):
        return None, "the context is not one the shop made"
    if not isinstance(payload.get("exp"), int) or now > payload["exp"] or payload.get("iat", 0) > now + CLOCK_SKEW_S:
        return None, "the context has run out; open the page again"
    return payload, ""


class OnceSet:
    """Nonces already used, each kept until its context runs out. ⚠ In memory: a restart forgets them, so a context
    opened just before a restart could be opened once more within its five minutes. A partner keeps this in a database."""

    def __init__(self):
        self._seen: dict[str, int] = {}
        self._lock = threading.Lock()     # the server answers each request on its own thread

    def claim(self, nonce: str, exp: int, now: float | None = None) -> bool:
        now = now or time.time()
        with self._lock:
            self._seen = {n: e for n, e in self._seen.items() if e >= now}
            if nonce in self._seen:
                return False
            self._seen[nonce] = exp
            return True


def customer_of(payload: dict) -> str | None:
    """The customer the page is about: the sale's customer on the till, the record in Desk when it is a Customer."""
    if payload.get("doctype"):
        return payload.get("name") if payload["doctype"] == "Customer" and isinstance(payload.get("name"), str) else None
    sale = payload.get("sale")
    customer = sale.get("customer") if isinstance(sale, dict) else None
    return customer if isinstance(customer, str) and customer else None


def count_of(settings: dict | None) -> int:
    """How many sales the page shows: the settings' number, 10 when none is set, never more than 50."""
    try:
        n = int((settings or {}).get("history_count") or DEFAULT_COUNT)
    except (TypeError, ValueError):
        n = DEFAULT_COUNT
    return max(1, min(n, MAX_COUNT))


def _when(row: dict) -> tuple:
    return (str(row.get("posting_date") or ""), clock(row.get("posting_time")), row.get("name") or "")


def clock(value) -> tuple:
    """A time as numbers: the shop sends ``9:00:00`` with no leading zero, which sorts after ``10:30:00`` as text."""
    parts = (str(value or "0").split(":") + ["0", "0"])[:3]
    try:
        return int(parts[0]), int(parts[1]), float(parts[2])
    except ValueError:
        return 0, 0, 0.0


def pick(pos_rows: list[dict], si_rows: list[dict], customer: str, count: int) -> list[tuple[str, str]]:
    """The newest ``count`` sales of this customer across both lists, as ``(record type, name)``. A row of another
    customer, a draft or cancelled row, and a consolidated Sales Invoice are dropped here too, whatever the read asked."""
    rows = [(POS, r) for r in pos_rows] + [(SI, r) for r in si_rows if not r.get("is_consolidated")]
    rows = [(dt, r) for dt, r in rows if r.get("customer") == customer and r.get("docstatus") == 1]
    rows.sort(key=lambda x: _when(x[1]), reverse=True)
    return [(dt, r["name"]) for dt, r in rows[:count]]


def _num(value) -> Decimal:
    return Decimal(str(value or 0))


def visit(doctype: str, doc: dict, names: dict) -> dict:
    """One visit as the page shows it. The store is the sale's warehouse (else its first line's); who served is the full
    name of the user who made the sale (else that user's id); amounts are decimals, rounded to the cent for display."""
    items = doc.get("items") or []
    lines = []
    for it in items:
        qty = _num(it.get("qty"))
        off = abs(_num(it.get("discount_amount")) * qty)     # a return's quantity is below 0: show what was taken off
        lines.append({"item": it.get("item_name") or it.get("item_code") or "", "qty": _text(qty),
                      "discount_pct": _text(_num(it.get("discount_percentage"))), "discount": _money(off)})
    owner = doc.get("owner") or ""
    return {"doctype": doctype, "name": doc.get("name"), "date": str(doc.get("posting_date") or ""),
            "store": doc.get("set_warehouse") or (items[0].get("warehouse") if items else "") or "",
            "served": names.get(owner) or owner, "currency": doc.get("currency") or "",
            "total": _money(_num(doc.get("grand_total"))), "is_return": bool(doc.get("is_return")),
            "sale_discount": _money(_num(doc.get("discount_amount"))),
            "sale_discount_pct": _text(_num(doc.get("additional_discount_percentage"))),
            "lines_discount": _money(abs(sum((_num(i.get("discount_amount")) * _num(i.get("qty")) for i in items), Decimal(0)))),
            "lines": lines}


def _money(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01")))


def _text(d: Decimal) -> str:
    return format(d.normalize(), "f") if d else "0"
