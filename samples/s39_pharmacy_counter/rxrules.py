"""S39 — *Pharmacy counter rules*: the pure core (no framework, no network), shared by the service and its tests.

Two extension points, one app:

- **a check before payment** (``check/1``), as two subscriptions of one service: the dispensary's (down answer
  ``refuse``) and the front of the shop's (``allow_and_flag``). At Pay, and at a return's confirm, ``decide`` refuses the
  first line a rule stops, in the order of ``RULES``.
- **a document check** (``doccheck/1``, submit) on Sales Order, Delivery Note and Sales Invoice: the same rules on the
  Desk, once per document chain. A document whose medicine lines all come from a linked parent (an order's delivery, a
  delivery's invoice) is allowed at once: the chain's first document checked and reserved.

What a rule needs is the shop's own data: drug schedules (``<prefix> Drug Schedule``) linked to items, one dated link per
classification axis (the strictest applies); prescriptions and pharmacists (records in the shop); the patient's identity
fields on Customer. Nothing is hard-coded per market.

**Dispensings.** Every sale that dispenses against a prescription, or sells a schedule with a frequency cap, is one
``<prefix> Dispensing`` record in the shop, named ``<patient key>~<0001…>`` (an opaque key per customer): the patient's
next number. The service inserts
it after the rules allow the sale; of two tills that read the same last number, one insert fails on the name and that
till decides again. A dispensing counts from the moment it is reserved, and stops counting only when the shop says so
(``resolve``): the sale was never booked and its POS day is closed, its booked sale or Desk document was cancelled or
deleted. Never on a timer: a check's approval does not expire. A give-back (a return where the schedule allows it) is a
dispensing with negative quantities that counts only once its return is booked.

⛔ No answer moves money or writes a sale: the only record the app writes is its own Dispensing.

``verify`` and ``plain`` are S37's (``samples/s37_age_check/agecheck.py``), copied: a defect there is a defect here.
``nearest_group`` reads the group tree as S37's ``age_of`` does.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import re
import time

SKEW_S = 300          # a request stamped further than this from our clock is refused (a replay window, not a clock)
BODY_MAX = 256 * 1024
TEXT_MAX = 140        # every sentence the till or the Desk shows: plain text, 1 to 140 characters
SEQ_WIDTH = 4         # <customer>~0001: the patient's dispensings, in the order they were taken
REFS_MAX = 5          # prescription numbers one sale may name

# the sale details (till) and the fields (Desk) this app reads; "<prefix> <suffix>" and "<prefix>_<field>"
RX, PRESCRIBER, LICENCE, DIRECTIONS = "Rx Number", "Prescriber", "Prescriber Licence", "Directions"
DESK_FIELDS = {RX: "rx_number", PRESCRIBER: "prescriber", LICENCE: "prescriber_licence", DIRECTIONS: "directions"}
# the patient's fields on Customer a schedule may need set: the schedule's tick → the Customer field → the words the cashier
# reads. The last is the patient's consent to keep their prescription records, dated (who gave it is a field of its own)
IDENTITY = (("needs_id_number", "id_number", "national or residence ID"),
            ("needs_birth_date", "birth_date", "date of birth"),
            ("needs_authority", "authority", "authority to possess"),
            ("needs_consent", "consent_date", "consent to keep their records"))
DATED = ("consent_date",)   # set AND on or before today: a consent dated ahead is a mis-keyed one, not a consent
DESK_TYPES = ("Sales Order", "Delivery Note", "Sales Invoice")
# a Desk line made from a linked parent: (the parent's name, its ROW reference). A line is linked only when the row
# reference is set: the engine then holds the line to that row's item; a parent name alone could be typed onto any line
PARENT_FIELDS = (("against_sales_order", "so_detail"), ("against_sales_invoice", "si_detail"), ("sales_order", "so_detail"),
                 ("delivery_note", "dn_detail"))

RESERVED, DISPENSED, RELEASED, RETURNED = "Reserved", "Dispensed", "Released", "Returned"


# ── the call ──────────────────────────────────────────────────────────────────


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


def plain(text, n: int = TEXT_MAX) -> str:
    """Plain text the till accepts: printable, no ``<`` or ``>``, at most ``n`` characters."""
    text = "".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def sale_context(body: dict) -> dict:
    """A till check (``check/1``) as the rules read it, or ``ValueError``. Quantities stay in the line's unit here; the
    service converts them to the item's stock unit (``to_stock``)."""
    if not isinstance(body, dict) or body.get("point") != "check/1":
        raise ValueError("not a check/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("stage") not in ("sale", "return"):
        raise ValueError("no context")
    lines, attrs = ctx.get("lines"), ctx.get("sale_attributes")
    if not isinstance(lines, list) or not all(
            isinstance(x, dict) and isinstance(x.get("item_code"), str) and x["item_code"]
            and isinstance(x.get("item_group"), str) and _number(x.get("qty_milli")) for x in lines):
        raise ValueError("lines are rows of item_code, item_group and qty_milli")
    if not isinstance(attrs, list) or not all(
            isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("value"), str) for a in attrs):
        raise ValueError("sale_attributes are rows of name and value")
    for k in ("sale_ref", "operator", "customer", "pos_profile", "pos_opening"):
        if not isinstance(ctx.get(k) or "", str):
            raise ValueError(f"{k} is text")
    ret = ctx.get("return_of")
    if ret is not None and not (isinstance(ret, dict) and isinstance(ret.get("invoice") or "", str)):
        raise ValueError("return_of names the original sale")
    if not _text(ctx.get("sale_ref")):
        raise ValueError("no sale_ref: a reservation could never be matched to its booking")
    return {"source": "till", "stage": ctx["stage"], "moves_stock": True, "sale_ref": _text(ctx.get("sale_ref")),
            "operator": _text(ctx.get("operator")), "customer": _text(ctx.get("customer")),
            "pos_profile": _text(ctx.get("pos_profile")), "pos_opening": _text(ctx.get("pos_opening")),
            "return_of": _text((ret or {}).get("invoice")), "doctype": "", "name": "",
            "details": {a["name"]: a["value"].strip() for a in attrs},
            "lines": [{"n": x.get("line_no") if isinstance(x.get("line_no"), int) else i + 1, "item": x["item_code"],
                       "group": x["item_group"], "qty": x["qty_milli"] / 1000, "uom": _text(x.get("uom")), "linked": False}
                      for i, x in enumerate(lines)]}


def desk_context(body: dict, prefix: str) -> dict:
    """A Desk document check (``doccheck/1``) as the rules read it, or ``ValueError``. Quantities are the lines'
    ``stock_qty`` (the item's stock unit already), signed as the document books them (a return's are negative)."""
    if not isinstance(body, dict) or body.get("point") != "doccheck/1":
        raise ValueError("not a doccheck/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("event") not in ("submit", "validate"):
        raise ValueError("no context")
    if ctx.get("doctype") not in DESK_TYPES:
        raise ValueError("this app checks sales orders, deliveries and sales invoices")
    f = ctx.get("fields")
    if not isinstance(f, dict) or not isinstance(f.get("customer"), str) or not isinstance(f.get("items"), list):
        raise ValueError("the document's customer and items")
    if not isinstance(ctx.get("name"), str) or not ctx["name"]:
        raise ValueError("the document's name")
    p = field_prefix(prefix)
    lines = []
    for i, x in enumerate(f["items"]):
        if not (isinstance(x, dict) and isinstance(x.get("item_code"), str) and x["item_code"]
                and _number(x.get("stock_qty"))):
            raise ValueError("items are rows of item_code and stock_qty")
        parent = next((_text(x.get(k)) for k, row in PARENT_FIELDS if _text(x.get(k)) and _text(x.get(row))), "")
        lines.append({"n": i + 1, "item": x["item_code"], "group": _text(x.get("item_group")),
                      "qty": x["stock_qty"] / 1000, "uom": "", "linked": bool(parent), "parent": parent})
    is_return = bool(f.get("is_return"))
    details = {suffix: _text(f.get(f"{p}_{field}")) for suffix, field in DESK_FIELDS.items()}
    moves = ctx["doctype"] == "Delivery Note" or bool(f.get("update_stock"))
    return {"source": "desk", "stage": "return" if is_return else "sale", "event": ctx["event"], "moves_stock": moves,
            "sale_ref": f"{ctx['doctype']}:{ctx['name']}", "operator": _text(ctx.get("user")),
            "customer": f["customer"].strip(), "pos_profile": "", "pos_opening": "",
            "return_of": _text(f.get("return_against")), "doctype": ctx["doctype"], "name": ctx["name"],
            "details": {f"{prefix} {k}": v for k, v in details.items()}, "lines": lines}


def field_prefix(prefix: str) -> str:
    return prefix.lower().replace(" ", "_")


# ── the shop's data ───────────────────────────────────────────────────────────


def _flag(v) -> bool:
    return v in (1, True, "1")


def _whole(v) -> int:
    return int(v) if _number(v) and v >= 0 and v == int(v) else 0


def _amount(v) -> float:
    return float(v) if _number(v) and v > 0 else 0.0


def schedules_of(records) -> dict:
    """``{name: rule}`` from the shop's Drug Schedule records. Anything that is not a list of named records is
    ``ValueError`` (the service then answers 503: nothing was judged). A number that is not a whole, positive one reads 0
    (no limit), so a schedule never limits by accident."""
    if not isinstance(records, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):
        raise ValueError("the shop's drug schedules are not a list of records")
    out = {}
    for r in records:
        out[r["name"]] = {
            "name": r["name"], "axis": _text(r.get("axis")) or r["name"],
            "rx": _flag(r.get("needs_prescription")), "pharmacist": _flag(r.get("pharmacist_only")),
            "dispensary": _flag(r.get("dispensary_only")), "validity": _whole(r.get("validity_days")),
            "max_fills": _whole(r.get("max_fills")), "qty_cap": _amount(r.get("qty_cap")),
            "freq_qty": _amount(r.get("freq_qty")), "freq_days": _whole(r.get("freq_days")),
            "ids": tuple(f for tick, f, _ in IDENTITY if _flag(r.get(tick))),
            "returnable": _flag(r.get("returnable")), "gives_back": _flag(r.get("return_gives_back")),
            "directions": _flag(r.get("needs_directions")),
            "own_sale": _flag(r.get("own_sale_without_rx")),
            "max_occasions": _whole(r.get("max_occasions")), "one_drug": _flag(r.get("one_drug_per_rx")),
        }
    return out


def groups_of(records, prefix: str) -> dict:
    """The shop's item groups: ``{name: (lft, rgt, schedule or "", needs directions)}``."""
    p = field_prefix(prefix)
    if not isinstance(records, list) or not all(
            isinstance(r, dict) and isinstance(r.get("name"), str) and isinstance(r.get("lft"), int)
            and isinstance(r.get("rgt"), int) for r in records):
        raise ValueError("the shop's item groups are not a list of records")
    return {r["name"]: (r["lft"], r["rgt"], _text(r.get(f"{p}_schedule")), _flag(r.get(f"{p}_needs_directions")))
            for r in records}


def nearest_group(group: str, groups: dict, pick) -> object:
    """The nearest group, the group itself first, then each group above it, for which ``pick(row)`` is truthy: its value,
    else ``None``. The tree nests by lft/rgt, so the largest lft that contains the group is the nearest."""
    g = groups.get(group)
    if not g:
        return None
    above = sorted(((lft, row) for lft, rgt, *rest in groups.values()
                    for row in [(lft, rgt, *rest)] if lft <= g[0] and g[1] <= rgt and pick(row)), reverse=True)
    return pick(above[0][1]) if above else None


def items_of(records, prefix: str) -> dict:
    """``{item_code: {"template", "stock_uom", "directions"}}`` from the shop's Item records."""
    p = field_prefix(prefix)
    if not isinstance(records, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):
        raise ValueError("the shop's items are not a list of records")
    return {r["name"]: {"template": _text(r.get("variant_of")), "stock_uom": _text(r.get("stock_uom")),
                        "directions": _text(r.get(f"{p}_directions"))} for r in records}


def item_schedules_of(rows, today: datetime.date) -> dict:
    """``{item_code: [(schedule, effective_from)]}`` from the item's schedule rows; a row effective after today is left
    out (a reclassification takes effect on its own date). A row with no date is effective from always."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("parent"), str) for r in rows):
        raise ValueError("the items' schedule rows are not a list of records")
    out: dict = {}
    for r in rows:
        name, since = _text(r.get("schedule")), _date(r.get("effective_from")) or datetime.date.min
        if name and since <= today:
            out.setdefault(r["parent"], []).append((name, since))
    return out


def conversions_of(rows) -> dict:
    """``{(item_code, uom): factor}`` from the items' unit rows (UOM Conversion Detail)."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("parent"), str) for r in rows):
        raise ValueError("the items' units are not a list of records")
    return {(r["parent"], _text(r.get("uom"))): float(r["conversion_factor"]) for r in rows
            if _number(r.get("conversion_factor")) and r["conversion_factor"] > 0 and _text(r.get("uom"))}


def _date(v) -> datetime.date | None:
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()[:10]):
        try:
            return datetime.date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return None


def today_at(hours: float, now: float | None = None) -> datetime.date:
    """The shop's own date: UTC plus the shop's hours from UTC (S37's)."""
    t = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t + datetime.timedelta(hours=hours)).date()


def settings_of(record) -> dict:
    """The shop's settings, from its record *Default* (``None``: not made yet, so UTC and no walk-in customer named; the
    POS Profile's own default customer is read beside it)."""
    r = record if isinstance(record, dict) else {}
    hours = r.get("hours_from_utc")
    walk = r.get("walk_in_customers") if isinstance(r.get("walk_in_customers"), str) else ""
    return {"hours": float(hours) if _number(hours) and -14 <= hours <= 14 else 0.0,
            "walk_ins": {w.strip() for w in walk.splitlines() if w.strip()}}


# ── which schedules an item is under ─────────────────────────────────────────


def schedules_for(item: str, group: str, items: dict, item_rows: dict, groups: dict, schedules: dict) -> list:
    """The schedules an item is under today, ONE PER AXIS: the item's own row effective most recently on that axis; for an
    axis it has none on, its template's (a variant does not copy a field its Item Variant Settings do not list); for an
    axis neither has, the nearest item group's schedule. So a variant's own quantity cap never hides its template's
    prescription class. A schedule name the shop no longer holds is left out."""
    def own(code):
        latest: dict = {}
        for name, since in item_rows.get(code) or []:
            if name not in schedules:
                continue
            axis = schedules[name]["axis"]
            if axis not in latest or since >= latest[axis][1]:
                latest[axis] = (name, since)
        return {axis: n for axis, (n, _) in latest.items()}

    per_axis = own(item)
    for axis, n in own((items.get(item) or {}).get("template") or "").items():
        per_axis.setdefault(axis, n)
    g = nearest_group(group, groups, lambda row: row[2] if row[2] in schedules else None)
    if g:
        per_axis.setdefault(schedules[g]["axis"], g)
    return [schedules[n] for n in sorted(per_axis.values())]


def strictest(rules: list) -> dict | None:
    """One rule from an item's schedules, the strictest of each: a need is any schedule's; a limit (validity, fills, caps)
    the least that is set; returnable and give-back only when every schedule says so. ``None``: no schedule."""
    if not rules:
        return None

    def least(k):
        vals = [r[k] for r in rules if r[k]]
        return min(vals) if vals else 0

    capped = [r for r in rules if r["freq_qty"] and r["freq_days"]]
    return {"schedules": sorted(r["name"] for r in rules),
            "rx": any(r["rx"] for r in rules), "pharmacist": any(r["pharmacist"] for r in rules),
            "dispensary": any(r["dispensary"] for r in rules), "directions": any(r["directions"] for r in rules),
            "validity": least("validity"), "max_fills": least("max_fills"), "qty_cap": least("qty_cap"),
            "max_occasions": least("max_occasions"), "one_drug": any(r["one_drug"] for r in rules),
            "freq": sorted(((r["name"], r["freq_qty"], r["freq_days"]) for r in capped)),
            "ids": tuple(f for _, f, _ in IDENTITY if any(f in r["ids"] for r in rules)),
            "returnable": all(r["returnable"] for r in rules), "gives_back": all(r["gives_back"] for r in rules),
            "own_sale": any(r["own_sale"] for r in rules)}


def to_stock(line: dict, items: dict, conversions: dict) -> float | None:
    """The line's quantity in the item's stock unit: the till sends the line's own unit. ``None``: a unit the item does
    not convert (the rules then refuse the line rather than guess)."""
    uom = line.get("uom") or ""
    stock = (items.get(line["item"]) or {}).get("stock_uom") or ""
    if not uom or uom == stock:
        return line["qty"]
    f = conversions.get((line["item"], uom)) or conversions.get(((items.get(line["item"]) or {}).get("template") or "", uom))
    return line["qty"] * f if f else None


# ── prescriptions and dispensings ────────────────────────────────────────────


def refs_of(value: str) -> list:
    """The prescription numbers a sale names: one detail, several numbers separated by commas or semicolons (a paper
    number may hold a space, "KNH 12345")."""
    return [r.strip() for r in re.split(r"[,;]+", value or "") if r.strip()][:REFS_MAX]


def fingerprint(rx: dict) -> str:
    """What a dispensing froze of its prescription: patient, date written, fills, retained, and each item's quantity."""
    items = sorted((i["item"], round(i["qty"], 6)) for i in rx["items"])
    raw = json.dumps([rx["customer"], rx["date_written"], rx["fills"], rx["retained"], items])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def prescriptions_of(records, item_rows) -> dict:
    """``{name: prescription}`` from the shop's Prescription records and their item rows."""
    if not isinstance(records, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):
        raise ValueError("the shop's prescriptions are not a list of records")
    if not isinstance(item_rows, list) or not all(isinstance(r, dict) and isinstance(r.get("parent"), str)
                                                  for r in item_rows):
        raise ValueError("the prescriptions' items are not a list of records")
    out = {}
    for r in records:
        out[r["name"]] = {
            "name": r["name"], "reference": _text(r.get("reference")), "customer": _text(r.get("customer")),
            "date_written": _text(r.get("date_written"))[:10], "fills": _whole(r.get("fills_authorised")) or 1,
            "retained": _flag(r.get("retained")), "active": _text(r.get("status")) in ("", "Active"),
            "prescriber": _text(r.get("prescriber")),
            "items": [{"item": _text(i.get("item_code")), "qty": _amount(i.get("qty")),
                       "directions": _text(i.get("directions"))} for i in item_rows if i["parent"] == r["name"]]}
    return out


def find_rx(ref: str, customer: str, rxs: dict) -> tuple[dict | None, str]:
    """A number the sale names → the prescription and ``""``, or ``None`` and why not. The record's own name first; else
    its paper reference, when exactly one prescription of this customer carries it."""
    if ref in rxs:
        return rxs[ref], ""
    same = [r for r in rxs.values() if r["reference"] == ref and r["customer"] == customer]
    if len(same) == 1:
        return same[0], ""
    if len(same) > 1:
        return None, f"Prescription {ref} is on more than one record. Use the record's number."
    return None, f"No prescription {ref} was found."


def dispensings_of(records) -> list:
    """The patient's dispensings, from the shop's Dispensing records (their lines are JSON the service wrote)."""
    if not isinstance(records, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):
        raise ValueError("the shop's dispensings are not a list of records")
    out = []
    for r in records:
        try:
            body = json.loads(r.get("lines_json") or "{}")
        except ValueError:
            body = {}
        lines = body.get("lines") if isinstance(body, dict) else None
        out.append({"name": r["name"], "seq": _whole(r.get("seq")), "status": _text(r.get("status")) or RESERVED,
                    "customer": _text(r.get("customer")),
                    "source": _text(r.get("source")), "sale_ref": _text(r.get("sale_ref")),
                    "document_type": _text(r.get("document_type")), "document": _text(r.get("document")),
                    "pos_opening": _text(r.get("pos_opening")), "pos_invoice": _text(r.get("pos_invoice")),
                    "day": _date(r.get("day")) or datetime.date.min,
                    "lines": [x for x in lines or [] if isinstance(x, dict) and _number(x.get("qty"))],
                    "fingerprints": body.get("fingerprints") if isinstance(body.get("fingerprints"), dict) else {}})
    return out


def counts(d: dict) -> bool:
    """Whether a dispensing counts: a dispensing (positive) until it is released; a give-back (negative) only once its
    return is booked."""
    give_back = any(x["qty"] < 0 for x in d["lines"])
    return d["status"] == RETURNED if give_back else d["status"] in (RESERVED, DISPENSED)


def resolve(d: dict, shop: dict) -> str:
    """The status the shop's own records give a dispensing (``shop`` is what the service read back):

    - ``sales``: ``{sale_ref (stripped, lower-cased): (pos_invoice, docstatus)}`` — booked till sales by their reference;
    - ``returns``: ``{key: (pos_invoice, docstatus)}`` — till returns by their key (the refund's own ``sale_ref``);
    - ``closed_days``: the POS days that are closed;
    - ``documents``: ``{"<doctype>:<name>": docstatus}`` — the Desk documents that still exist.

    - ``newest``: ``{sale_ref: dispensing name}`` — the newest dispensing of each sale or document; an older one was
      replaced on a later press of Pay or submit and is released, whatever its sale did.

    The status is worked out from the shop every time, so one set by hand (the pharmacist-in-charge may release a stuck
    reservation) never outlives what the shop shows: a released dispensing whose sale is booked reads *Dispensed* again.
    A dispensing whose sale or document the shop cannot place yet stays as it is: it keeps counting (a dispensing), keeps
    not counting (a give-back), or stays released by hand."""
    give_back = any(x["qty"] < 0 for x in d["lines"])
    newest = shop.get("newest")
    if newest is not None and newest.get(d["sale_ref"], d["name"]) != d["name"]:
        return RELEASED                                         # replaced by a later press of Pay or a later submit
    if d["source"] == "desk":
        found = shop["documents"].get(d["sale_ref"])
        status, owner = found if isinstance(found, tuple) else (found, None)
        if found is not None and owner is not None and d.get("customer") and owner != d["customer"]:
            return RELEASED                                     # its name was taken by another customer's document
        if status == "hidden":
            return d["status"]                                  # the shop would not show it: never read as gone
        if status is None or status == 2:                       # deleted, or cancelled
            return RELEASED
        if status == 1:
            return RETURNED if give_back else DISPENSED
        return d["status"]                                      # a draft: as it was
    if give_back:
        booked = shop["returns"].get(d["sale_ref"])
    else:
        booked = shop["sales"].get(d["sale_ref"].strip().lower())
    if booked and booked[1] == 1:
        return RETURNED if give_back else DISPENSED
    if booked and booked[1] == 2:
        return RELEASED
    if d["pos_opening"] and d["pos_opening"] in shop["closed_days"]:
        return RELEASED                                         # never booked, and its day is closed
    return d["status"]


# ── the rules ────────────────────────────────────────────────────────────────


def _refuse(line: dict | None, text: str) -> dict:
    head = f"Line {line['n']}: {plain(line['item'], 24)}: " if line else ""
    return {"verdict": "refuse", "reason": plain(head + text)}


def decide(ctx: dict, route: str, shop: dict, today: datetime.date, prefix: str) -> dict:
    """The answer for one sale, return or Desk document, and what to record. ``shop`` holds what the service read:

    ``rules`` (per line, ``strictest`` or ``None``) · ``qty`` (per line, in the stock unit, or ``None``) · ``items`` ·
    ``group_directions`` (per line) · ``walk_in`` (bool) · ``pharmacist`` (the operator's record or ``None``) ·
    ``customer_fields`` · ``rxs`` · ``dispensings`` (the patient's, resolved) · ``returned_from`` (the dispensings of
    the sale or document a return takes back).

    Returns ``{"verdict": …, ["reason": …], "record": None | {"lines": [...], "fingerprints": {...}}}``. ``record`` is the
    dispensing to reserve when the answer is allow."""
    lines, rules, qty = ctx["lines"], shop["rules"], shop["qty"]
    detail = lambda suffix: ctx["details"].get(f"{prefix} {suffix}", "")   # noqa: E731
    on_desk = ctx["source"] == "desk"
    # a Desk line made from a linked parent was checked, and reserved, when the chain's first document was submitted;
    # a line going back is judged whatever it came from
    live = [i for i, x in enumerate(lines) if not (x["linked"] and x["qty"] > 0)]
    sold = [i for i in live if lines[i]["qty"] > 0]
    back = [i for i in live if lines[i]["qty"] < 0]

    for i in live:
        if rules[i] and qty[i] is None:
            return _refuse(lines[i], f"its unit {plain(lines[i]['uom'], 12)} has no conversion to the stock unit.")

    # 1 · dispensed medicine is not taken back (P5, VR-11)
    for i in back:
        if rules[i] and not rules[i]["returnable"]:
            return _refuse(lines[i], "Dispensed medicine cannot be taken back.")

    # 2 · the front of the shop sells no prescription, pharmacist-only or dispensary medicine (VR-07)
    if route == "front":
        for i in sold:
            r = rules[i]
            if r and (r["rx"] or r["pharmacist"] or r["dispensary"]):
                return _refuse(lines[i], "Sell this at the dispensary.")

    # 3 · pharmacist only (VR-06), from the app's own Pharmacist record, its licence in date (F12)
    for i in sold:
        if rules[i] and rules[i]["pharmacist"]:
            ph = shop["pharmacist"]
            if not ph or not ph["active"] or ph.get("delegate"):
                return _refuse(lines[i], "Only a pharmacist may sell this.")
            if not ph["valid_until"] or ph["valid_until"] < today:
                until = ph["valid_until"].isoformat() if ph["valid_until"] else "a date not set"
                return _refuse(lines[i], f"Only a pharmacist may sell this: your licence ran out on {until}.")
            break

    # 4 · a named customer for a prescription or a frequency cap (VR-34); 5 · the patient's identity (VR-08)
    for i in sold:
        r = rules[i]
        if r and (r["rx"] or r["freq"] or r["ids"]) and shop["walk_in"]:
            return _refuse(lines[i], "needs a named customer, not a walk-in sale.")
        for _tick, field, words in IDENTITY:
            if r and field in r["ids"] and not shop["customer_fields"].get(field):
                return _refuse(lines[i], f"needs the customer's {words}. Add it on their Desk record.")

    # 6 · the quantity cap per sale, in the stock unit (VR-09)
    per_item: dict = {}
    for i in sold:
        if rules[i]:
            per_item[lines[i]["item"]] = per_item.get(lines[i]["item"], 0.0) + qty[i]
    for i in sold:
        r = rules[i]
        if r and r["qty_cap"] and per_item[lines[i]["item"]] > r["qty_cap"] + 1e-9:
            return _refuse(lines[i], f"No more than {_fmt(r['qty_cap'])} may be sold at once.")

    # 7 · prescriptions (VR-01 to VR-05, VR-33, and the freeze after the first dispense)
    counted = [d for d in shop["dispensings"] if counts(d) and d["sale_ref"] != ctx["sale_ref"]]
    record_lines, fps, recorded = [], {}, set()
    rx_lines = [i for i in sold if rules[i] and rules[i]["rx"]]
    named = refs_of(detail(RX))
    found, why = [], ""
    for ref in named:
        rx, why = find_rx(ref, ctx["customer"], shop["rxs"])
        if not rx:
            break
        found.append(rx)
    for i in rx_lines:
        line, r = lines[i], rules[i]
        if not named:
            what = "a prescription number field" if on_desk else "the prescription number in Sale details"
            return _refuse(line, f"needs a prescription. Add {what}.")
        if why:
            return _refuse(line, why)
        rx = next((x for x in found if any(it["item"] == line["item"] for it in x["items"])), None)
        if not rx:
            return _refuse(line, "is not on the prescription this sale names.")
        if rx["customer"] != ctx["customer"]:
            return _refuse(line, f"Prescription {rx['name']} is for another patient.")
        if not rx["active"]:
            return _refuse(line, f"Prescription {rx['name']} is cancelled.")
        written = _date(rx["date_written"])
        if not written:
            return _refuse(line, f"Prescription {rx['name']} has no date written.")
        if written > today:
            return _refuse(line, f"Prescription {rx['name']} is dated {written.isoformat()}, after today.")
        if r["validity"] and today >= written + datetime.timedelta(days=r["validity"]):
            last = written + datetime.timedelta(days=r["validity"] - 1)
            return _refuse(line, f"Prescription {rx['name']} was valid until {last.isoformat()}.")
        fp = fingerprint(rx)
        first = min((d for d in shop["dispensings"] if d["status"] in (DISPENSED, RETURNED)
                     and rx["name"] in d["fingerprints"]), key=lambda d: d["seq"], default=None)
        if first and first["fingerprints"][rx["name"]] != fp:
            return _refuse(line, f"Prescription {rx['name']} was changed after it was dispensed. Enter a new one.")
        fills = rx["fills"]
        if r["max_fills"]:
            fills = min(fills, r["max_fills"])
        if rx["retained"]:
            fills = 1
        mine = [d for d in counted if any(x.get("rx") == rx["name"] and x["qty"] > 0 for x in d["lines"])]
        if (rx["retained"] and mine) or (r["max_occasions"] and len(mine) >= r["max_occasions"]):
            return _refuse(line, f"Prescription {rx['name']} has nothing left to dispense.")
        if r["one_drug"] and len({it["item"] for it in rx["items"]}) > 1:
            return _refuse(line, f"Prescription {rx['name']} names more than one drug; this class allows one per prescription.")
        per_fill = sum(it["qty"] for it in rx["items"] if it["item"] == line["item"])
        dispensed = sum(x["qty"] for d in counted for x in d["lines"]
                        if x.get("rx") == rx["name"] and x.get("item") == line["item"])
        left = per_fill * fills - dispensed
        if left <= 1e-9:
            return _refuse(line, f"Prescription {rx['name']} has nothing left to dispense.")
        want = sum(qty[j] for j in rx_lines if lines[j]["item"] == line["item"])
        if want > min(left, per_fill) + 1e-9:
            return _refuse(line, f"Prescription {rx['name']} has only {_fmt(min(left, per_fill))} of this left.")
        fps[rx["name"]] = fp
        record_lines.append({"item": line["item"], "qty": qty[i], "rx": rx["name"], "schedules": r["schedules"]})
        recorded.add(i)

    # 7b · a register books the sale's prescription number for the whole sale: where the sale names a prescription, a line
    # whose schedule is sold in its own sale when not prescribed, and that no named prescription covers, is refused
    if named:
        for i in sold:
            r = rules[i]
            if r and r["own_sale"] and not any(it["item"] == lines[i]["item"] for x in found for it in x["items"]):
                return _refuse(lines[i], "Sell this in a sale of its own: it is not on the prescription this sale names.")

    # 8 · directions and a doctor's name, per product group or schedule
    for i in sold:
        if (rules[i] and rules[i]["directions"]) or shop["group_directions"][i]:
            line = lines[i]
            rx = next((x for x in found if any(it["item"] == line["item"] for it in x["items"])), None)
            doctor = detail(PRESCRIBER) or (rx["prescriber"] if rx else "")
            words = detail(DIRECTIONS) or next((it["directions"] for it in (rx["items"] if rx else [])
                                                if it["item"] == line["item"] and it["directions"]), "") \
                or (shop["items"].get(line["item"]) or {}).get("directions", "")
            if not doctor:
                return _refuse(line, "needs the doctor's name in Sale details." if not on_desk
                               else "needs the prescriber's name.")
            if not words:
                return _refuse(line, "needs directions for use in Sale details." if not on_desk
                               else "needs directions for use.")

    # 9 · the frequency cap per patient (VR-10), reserved with the sale
    for i in sold:
        r = rules[i]
        if not r or not r["freq"]:
            continue
        for name, cap, days in r["freq"]:
            since = today - datetime.timedelta(days=days - 1)
            had = sum(x["qty"] for d in counted if d["day"] >= since for x in d["lines"]
                      if name in (x.get("schedules") or []))
            now = sum(qty[j] for j in sold if rules[j] and name in rules[j]["schedules"] and qty[j] is not None)
            if had + now > cap + 1e-9:
                until = min((d["day"] for d in counted if d["day"] >= since), default=today) + datetime.timedelta(days=days)
                return _refuse(lines[i], plain(f"The patient has reached the limit for {name} until {until.isoformat()}.", 100))
        if i not in recorded:                  # by line, never by item and quantity: two equal lines are two lines
            record_lines.append({"item": lines[i]["item"], "qty": qty[i], "rx": "", "schedules": r["schedules"]})
            recorded.add(i)

    # 10 · a return gives back what its dispensing took, where its schedule says so (FR-K1-08): only a return that moves
    # stock back (a money-only credit note returns no medicine), and never twice for one dispensed quantity
    given: dict = {}
    for d in shop["dispensings"]:
        if d["sale_ref"] != ctx["sale_ref"] and d["status"] in (RESERVED, RETURNED):
            for x in d["lines"]:
                if x["qty"] < 0 and x.get("from"):
                    given[(x["from"], x.get("item"))] = given.get((x["from"], x.get("item")), 0.0) - x["qty"]
    for i in back if ctx.get("moves_stock", True) else ():
        r = rules[i]
        if not r or not r["gives_back"]:
            continue
        left = -qty[i]
        for d in shop["returned_from"]:
            for x in d["lines"]:
                if x.get("item") == lines[i]["item"] and x["qty"] > 0 and left > 1e-9:
                    take = min(left, x["qty"] - given.get((d["name"], x["item"]), 0.0))
                    if take <= 1e-9:
                        continue
                    record_lines.append({"item": x["item"], "qty": -take, "rx": x.get("rx", ""),
                                         "schedules": x.get("schedules") or [], "from": d["name"]})
                    given[(d["name"], x["item"])] = given.get((d["name"], x["item"]), 0.0) + take
                    left -= take

    return {"verdict": "allow", "record": {"lines": record_lines, "fingerprints": fps} if record_lines else None}


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else f"{n:g}"


def same_record(d: dict, record: dict) -> bool:
    """Whether an existing reservation already holds exactly what this answer would record (Pay pressed again)."""
    key = lambda xs: sorted((x.get("item"), round(x["qty"], 6), x.get("rx", "")) for x in xs)   # noqa: E731
    return d["status"] == RESERVED and key(d["lines"]) == key(record["lines"])


def patient_key(customer: str) -> str:
    """An opaque key for the patient: the record's name never carries the patient's name (it would land in the shop's
    access logs and Desk addresses). Equal for one customer, so it is still the per-patient lock."""
    return hashlib.sha256(customer.encode()).hexdigest()[:16]


def next_name(customer: str, dispensings: list) -> tuple[str, int]:
    """The patient's next dispensing name and number: ``<opaque patient key>~<0001…>``."""
    seq = max((d["seq"] for d in dispensings), default=0) + 1
    return f"{patient_key(customer)}~{seq:0{SEQ_WIDTH}d}", seq


def summary(lines: list) -> str:
    """The dispensing's lines as the Desk list shows them."""
    return plain("; ".join(f"{x['item']} {_fmt(x['qty'])}" + (f" ({x['rx']})" if x.get("rx") else "") for x in lines), 140)
