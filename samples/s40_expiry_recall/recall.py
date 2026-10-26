"""S40 — *Expiry and recall*: the pure core (no framework, no network), shared by the service and its tests.

Five doors call one service, each signed with its own subscription's secret:

    desk_action/1   Block these batches   on a Recall Notice   {"records": [{"doctype", "name", "fields": {…, "lots": [{"batch"}]}}]}
    desk_action/1   Refresh               on an Expiry Worklist {"records": [{"doctype", "name", "fields": {"store", "window_days"}}]}
    doccheck/1      a Purchase Receipt's submit                 {"doctype", "event", "name", "user", "fields": {…, "items": […]}}
    doccheck/1      a Stock Entry's submit                      the same shape
    doccheck/1      a Stock Reconciliation's submit             the same shape

``verify`` checks the shop's signature; the ``*_of`` readers take a call apart and refuse a malformed one before anything is
read; ``block_outcome``, ``stock_by_store``, ``customers`` and ``clocks`` decide a recall; ``worklist`` builds the
worklist; ``judge_receipt`` and ``judge_disposal`` answer the two checks. ⛔ Nothing here writes: the service writes the
app's own records and a lot's ``disabled`` itself, with its own key, BEFORE it answers a press; a check's answer writes
nothing but the one field the subscription lets it fill.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import time

PREFIX, P = "PP RCL", "pp_rcl"
SKEW_S = 300               # a request stamped further than this from our clock is refused (a replay window)
BODY_MAX = 256 * 1024
MOST_LOTS = 100            # lots on one notice that one press handles
TEXT_MAX = 140             # a check's reason, a filled value
SALES = ("POS Invoice", "Sales Invoice", "Delivery Note")   # the documents that hand a lot to a customer
CLASSES = ("Class I", "Class II", "Class III")
DEPTHS = ("Consumer", "Retail", "Wholesale")
WITNESS = ("Items with a listed schedule", "Every disposal", "No disposal")
DEFAULT_SCHEDULE_FIELD = "pp_rxc_schedules"    # Pharmacy counter rules' table of schedules on Item


def use_prefix(prefix: str):
    """The app's names under another prefix: ``IVENDNEXT RCL Recall Notice`` and ``ivendnext_rcl_pack_expiry`` for the
    library's app. The schedule field is the shop's setting, not ours, so it does not move."""
    global PREFIX, P
    PREFIX, P = prefix, prefix.lower().replace(" ", "_")


def f(name: str) -> str:
    """A field this app adds to one of the shop's own record types: ``pp_rcl_pack_expiry``."""
    return f"{P}_{name}"


def t(name: str) -> str:
    """One of the app's own record types: ``PP RCL Recall Notice``."""
    return f"{PREFIX} {name}"


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not: base64 HMAC-SHA256 of ``<timestamp>.<raw body>`` with the
    subscription's secret."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig.encode()):
        return "the signature does not match"
    return ""


# ── reading a call ────────────────────────────────────────────────────────────────────────────────────────────────


def press_of(body: dict, record_type: str) -> tuple[str, dict, str]:
    """(the record's name, its sent fields, the pressing user) of a press on ONE record of ``record_type``, else
    ``ValueError``."""
    if not isinstance(body, dict) or body.get("point") != "desk_action/1":
        raise ValueError("not a desk_action/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or not isinstance(ctx.get("records"), list):
        raise ValueError("no records")
    if len(ctx["records"]) != 1:
        raise ValueError("one record a press")
    rec = ctx["records"][0]
    if not isinstance(rec, dict) or rec.get("doctype") != record_type or not isinstance(rec.get("name"), str) \
            or not rec["name"]:
        raise ValueError(f"not a {record_type}")
    fields = rec.get("fields") if isinstance(rec.get("fields"), dict) else {}
    return rec["name"], fields, ctx.get("user") if isinstance(ctx.get("user"), str) else ""


def lots_of(fields: dict) -> list[str]:
    """The notice's lots, in its order, once each; ``ValueError`` when there are none or too many."""
    out = []
    for row in fields.get("lots") if isinstance(fields.get("lots"), list) else []:
        b = row.get("batch") if isinstance(row, dict) else None
        if isinstance(b, str) and b.strip() and b.strip() not in out:
            out.append(b.strip())
    if not 1 <= len(out) <= MOST_LOTS:
        raise ValueError("one to 100 lots on a notice")
    return out


def check_of(body: dict, record_type: str) -> dict:
    """The context of a document check on ``record_type``, else ``ValueError``."""
    if not isinstance(body, dict) or body.get("point") != "doccheck/1":
        raise ValueError("not a doccheck/1 call")
    ctx = body.get("context")
    if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("doctype") != record_type \
            or not isinstance(ctx.get("fields"), dict):
        raise ValueError(f"not a {record_type} check")
    return ctx


# ── small readers ─────────────────────────────────────────────────────────────────────────────────────────────────


def date_of(v) -> datetime.date | None:
    """A date from ``YYYY-MM-DD`` (a datetime's date part too), else None."""
    if not isinstance(v, str) or len(v) < 10:
        return None
    try:
        return datetime.date.fromisoformat(v[:10])
    except ValueError:
        return None


def whole(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def qty_of(v) -> float:
    """A quantity as sent: thousandths of a unit (2 units arrive as 2000)."""
    return v / 1000 if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def lines(text) -> list[str]:
    """A settings list, one value per line."""
    return [x.strip() for x in text.splitlines() if x.strip()] if isinstance(text, str) else []


def today_at(hours, now: float | None = None) -> datetime.date:
    t0 = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t0 + datetime.timedelta(hours=hours if isinstance(hours, (int, float)) else 0)).date()


def now_at(hours, now: float | None = None) -> datetime.datetime:
    """The shop's wall clock, as the shop writes a Datetime (no zone)."""
    t0 = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc)
    return (t0 + datetime.timedelta(hours=hours if isinstance(hours, (int, float)) else 0)).replace(tzinfo=None,
                                                                                                       microsecond=0)


def stamp(d: datetime.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")


def fit(text: str, most: int = TEXT_MAX) -> str:
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


# ── a recall ──────────────────────────────────────────────────────────────────────────────────────────────────────


def block_outcome(lot: dict | None, item: dict | None = None) -> str:
    """What *Block these batches* does to one lot: ``block`` (write ``disabled`` 1) · ``already`` (disabled before) ·
    ``no_expiry`` (left as it is: a lot of an item with *Has Expiry Date* and no expiry date is never saved, because the
    shop would write a guessed date into it, or refuse the save) · ``not_found``. A lot of an item that does not track
    expiry is blocked whatever its expiry field holds: the shop writes nothing into it."""
    if not isinstance(lot, dict) or not lot.get("name"):
        return "not_found"
    if lot.get("disabled"):
        return "already"
    if not date_of(lot.get("expiry_date")) and (item is None or item.get("has_expiry_date")):
        return "no_expiry"
    return "block"


OUTCOME_WORDS = {"block": "blocked", "already": "already blocked", "not_found": "not found",
                 "no_expiry": "not blocked: no expiry date (enter the pack's, then press again)",
                 "refused": "not blocked: the shop refused the change", "changed": "not blocked: changed meanwhile, press again"}


def clocks(recall_class: str, received_on, settings: dict) -> tuple[str | None, str | None, str | None]:
    """(start by, complete by, depth) for a class from the settings' clock: hours to start and days to complete from
    when the notice was received. None where the settings give none."""
    n = {"Class I": 1, "Class II": 2, "Class III": 3}.get(recall_class)
    rec = None
    if isinstance(received_on, str) and len(received_on) >= 10:
        try:
            rec = datetime.datetime.fromisoformat(received_on[:19])
        except ValueError:
            rec = None
    if not n or rec is None:
        return None, None, None
    hours, days = whole(settings.get(f"class_{n}_start_hours")), whole(settings.get(f"class_{n}_days"))
    depth = settings.get(f"class_{n}_depth") if settings.get(f"class_{n}_depth") in DEPTHS else None
    start = stamp(rec + datetime.timedelta(hours=hours)) if hours and hours > 0 else None
    done = stamp(rec + datetime.timedelta(days=days)) if days and days > 0 else None
    return start, done, depth


def quarantines(settings: dict) -> set:
    """The shop's quarantine stores, one per line (a chain keeps one per store)."""
    return set(lines(settings.get("quarantine_stores")))


def stock_by_store(entries: list[dict], lots: list[str]) -> dict:
    """``{(store, lot): quantity}`` on hand, from the lot ledger's rows (one per bundle entry: ``voucher_type``,
    ``warehouse``, ``batch_no``, ``qty``; an outward entry's quantity is negative). A POS sale's own bundle is left
    out: until the day's sales are merged it books no stock, and the merged invoice's bundle does. Only stores that
    still hold some are kept."""
    out = {}
    for r in entries if isinstance(entries, list) else []:
        if not isinstance(r, dict) or r.get("batch_no") not in lots or r.get("voucher_type") == "POS Invoice":
            continue
        q = r.get("qty")
        if not isinstance(q, (int, float)) or isinstance(q, bool) or not isinstance(r.get("warehouse"), str):
            continue
        k = (r["warehouse"], r["batch_no"])
        out[k] = out.get(k, 0.0) + q
    return {k: round(v, 6) for k, v in out.items() if v > 1e-9}


def customers(entries: list[dict], docs: dict, lots: list[str]) -> list[dict]:
    """The customers a recalled lot reached: one row per sales document and lot, its quantity handed over (a return
    shows as a negative quantity). ``docs`` maps ``(type, name)`` to the document's ``customer``, ``customer_name`` and
    ``posting_date``. A till sale is listed under its POS sale until its day closes, then under the day's merged
    invoice: the shop moves the sale's lot record onto the merged invoice, so one sale is never listed twice (measured
    on our test bench). A document the service could not read is listed with no customer, never dropped."""
    agg = {}
    for r in entries if isinstance(entries, list) else []:
        if not isinstance(r, dict) or r.get("batch_no") not in lots or r.get("voucher_type") not in SALES:
            continue
        q = r.get("qty")
        if not isinstance(q, (int, float)) or isinstance(q, bool) or not isinstance(r.get("voucher_no"), str):
            continue
        key = (r["voucher_type"], r["voucher_no"], r["batch_no"])
        row = agg.setdefault(key, {"qty": 0.0, "store": r.get("warehouse") or ""})
        row["qty"] -= q            # an outward entry is negative: handed over is positive
    out = []
    for (vt, vn, lot), row in sorted(agg.items()):
        if abs(row["qty"]) < 1e-9:
            continue
        doc = docs.get((vt, vn)) if isinstance(docs.get((vt, vn)), dict) else {}
        out.append({"customer": doc.get("customer") or "", "customer_name": fit(str(doc.get("customer_name") or ""), 140),
                    "document_type": vt, "document": vn, "posting_date": doc.get("posting_date") or None,
                    "batch": lot, "qty": round(row["qty"], 6), "store": row["store"]})
    return out


# ── the worklist ──────────────────────────────────────────────────────────────────────────────────────────────────


ACTIONS = ("", "To check", "Marked down", "Returned to supplier", "Moved to quarantine")


def worklist(stock: list[dict], batches: dict, items: dict, store: str | None, window: int, today: datetime.date,
             kept: dict) -> tuple[list[dict], list[dict]]:
    """(near-expiry rows, no-expiry rows). ``stock``: the shop's lot read (``batch_no``, ``warehouse``, ``qty``; it
    already leaves out disabled lots); ``batches``: lot → its ``item``, ``expiry_date``, ``disabled``, ``batch_qty``;
    ``items``: item → ``has_expiry_date``; ``kept``: ``(lot, store)`` → the action the pharmacist chose, kept across
    refreshes. A near-expiry row is a lot with stock in the store whose expiry is within ``window`` days (a lot past its
    date is listed too, with negative days left). A no-expiry row is a lot of an item with *Has Expiry Date* and no
    expiry date, disabled or not (the setup script's sweep disables them)."""
    near = []
    for r in stock if isinstance(stock, list) else []:
        if not isinstance(r, dict) or (store and r.get("warehouse") != store):
            continue
        b = batches.get(r.get("batch_no")) or {}
        exp = date_of(b.get("expiry_date"))
        q = r.get("qty")
        if exp is None or not isinstance(q, (int, float)) or q <= 0:
            continue
        left = (exp - today).days
        if left > window:
            continue
        near.append({"batch": r["batch_no"], "item": b.get("item") or "", "store": r.get("warehouse") or "",
                     "qty": q, "expiry_date": exp.isoformat(), "days_left": left,
                     "action": kept.get((r["batch_no"], r.get("warehouse") or "")) or "To check"})
    near.sort(key=lambda x: (x["days_left"], x["store"], x["batch"]))
    gaps = []
    for name, b in sorted(batches.items()):
        if date_of(b.get("expiry_date")) or not (items.get(b.get("item")) or {}).get("has_expiry_date"):
            continue
        gaps.append({"batch": name, "item": b.get("item") or "", "qty": b.get("batch_qty") or 0,
                     "disabled": 1 if b.get("disabled") else 0})
    return near, gaps


def lots_on(line: dict, bundle_lots: dict) -> dict:
    """A document line's lots and the quantity of each, in the STOCK unit: its bundle's entries (``bundle_lots``:
    bundle → {lot: quantity, never signed}), and its own ``batch_no`` with the line's stock quantity (``transfer_qty`` on
    a stock entry, ``stock_qty`` on a receipt; ``qty`` × ``conversion_factor`` otherwise). Empty when it names no lot."""
    out = {}
    for lot, q in (bundle_lots.get(line.get("serial_and_batch_bundle")) or {}).items():
        out[lot] = out.get(lot, 0.0) + abs(q)
    b = line.get("batch_no")
    if isinstance(b, str) and b and b not in out:
        out[b] = stock_qty_of(line)
    return out


def stock_qty_of(line: dict) -> float:
    for k in ("transfer_qty", "stock_qty"):
        if isinstance(line.get(k), (int, float)) and not isinstance(line.get(k), bool):
            return qty_of(line[k])
    cf = line.get("conversion_factor")
    return qty_of(line.get("qty")) * (cf if isinstance(cf, (int, float)) and not isinstance(cf, bool) and cf > 0 else 1)


# ── receiving ─────────────────────────────────────────────────────────────────────────────────────────────────────


def judge_receipt(fields: dict, items: dict, batches: dict, bundle_lots: dict, settings: dict,
                  today: datetime.date, erp: bool = False) -> list[str]:
    """The receipt's problems, in line order, as short sentences (empty: it may submit). ``items``: item → its
    ``has_expiry_date``, ``shelf_life_in_days`` and the app's two Item fields; ``batches``: lot → ``expiry_date``,
    ``manufacturing_date``; ``bundle_lots``: bundle → {its lot: quantity}. Days left are counted from the later of the
    shop's ``today`` and the posting date, so a backdated receipt never lets an expired or short-dated lot in (Good
    Life's rule counted from today)."""
    out = []
    posting = date_of(fields.get("posting_date"))
    since = max(today, posting) if posting else today
    if settings.get("supplier_note_required") and not str(fields.get("supplier_delivery_note") or "").strip():
        out.append("Type the supplier's invoice or credit-note number in Supplier Delivery Note.")
    if fields.get("is_return"):
        return out
    floor = whole(settings.get("min_shelf_days")) or 0
    pack_needed = settings.get("pack_expiry_required", 1) not in (0, "0", False) and not erp   # an ERP sends none
    later = []
    for i, line in enumerate(fields.get("items") if isinstance(fields.get("items"), list) else [], 1):
        if not isinstance(line, dict):
            continue
        if line.get(f("lou")) and (whole(line.get(f("lou_days"))) or 0) <= 0:
            out.append(f"Row {i}: a Letter of Undertaking needs its days.")      # whenever it is ticked
            continue
        if isinstance(line.get("qty"), (int, float)) and line["qty"] <= 0 and line.get("rejected_qty"):
            continue                                       # every unit rejected: nothing of the lot is received
        code = line.get("item_code")
        item = items.get(code)
        if not isinstance(item, dict):
            out.append(f"Row {i}: the app could not read item {code}.")
            continue
        if not item.get("has_expiry_date"):
            continue
        lots = lots_on(line, bundle_lots)
        if not lots:
            out.append(f"Row {i}: name the lot of {code} before you submit, with the expiry printed on the pack.")
            continue
        pack = date_of(line.get(f("pack_expiry")))
        life = whole(item.get("shelf_life_in_days")) or 0
        for lot in lots:
            b = batches.get(lot)
            exp = date_of((b or {}).get("expiry_date"))
            if exp is None:
                out.append(f"Row {i}: lot {lot} has no expiry date. Enter the date printed on the pack.")
                continue
            if pack is not None and pack != exp:
                out.append(f"Row {i}: lot {lot} expires {exp}, the pack says {pack}. Correct the lot.")
                continue
            if pack is None and life > 0:
                # with a shelf life set the shop can work a lot's expiry out (manufacturing date + shelf life), and a
                # later edit of either leaves no trace on the lot: the pack's own date is asked for (setting on), or the
                # arithmetic is the only test left (setting off, a shop receiving on Handheld)
                made = date_of((b or {}).get("manufacturing_date"))
                if pack_needed or made is None or made + datetime.timedelta(days=life) == exp:
                    msg = f"Row {i}: type the expiry printed on lot {lot}'s pack in Pack expiry."
                    if not erp:
                        out.append(msg)
                        continue
                    later.append(msg)   # the ERP's flag says first what else is wrong with the lot
            left = (exp - since).days
            if left <= 0:
                out.append(f"Row {i}: lot {lot} expired on {exp}.")
                continue
            if item.get(f("shelf_life_exempt")):
                continue
            least = whole(item.get(f("min_shelf_days"))) or floor
            if left >= least:
                continue
            if line.get(f("lou")):
                lou = whole(line.get(f("lou_days"))) or 0
                if left < lou:
                    out.append(f"Row {i}: lot {lot} has {left} days left; the Letter of Undertaking covers {lou}.")
                continue
            out.append(f"Row {i}: lot {lot} has {left} days left, under {least}. Tick Letter of Undertaking with its "
                       f"days, or refuse the goods.")
    return out + later


def is_erp(user, settings: dict) -> bool:
    """The receipt was posted by one of the ERP connector's own users (the settings' list; case does not matter)."""
    return isinstance(user, str) and user.strip().lower() in {u.lower() for u in lines(settings.get("erp_users"))}


def receipt_answer(problems: list[str], erp: bool) -> dict:
    """The check's answer: allow · refuse (the first problem, and how many more) · for the ERP's own user, fill the
    receipt's *Receiving check* field instead, so an ERP-posted receipt is flagged, never stopped for what it holds."""
    if not problems:
        return {"verdict": "allow"}
    more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
    if erp:
        return {"verdict": "fill", "fields": {f("short_dated"): fit(problems[0], TEXT_MAX - len(more)) + more}}
    return {"verdict": "refuse", "reason": fit(problems[0], TEXT_MAX - len(more)) + more}


# ── disposal ──────────────────────────────────────────────────────────────────────────────────────────────────────


class NoScheduleField(Exception):
    """The item has no field the settings name for its schedules: the disposal is refused loudly, never let through."""


def schedules_of(item_doc: dict, field: str, on: datetime.date | None) -> list[str]:
    """The item's schedules on ``on``: the field may be a table of rows (``schedule``, optional ``effective_from``;
    Pharmacy counter rules') or a field naming one schedule. ``NoScheduleField`` when the item carries no such field."""
    if not isinstance(item_doc, dict) or field not in item_doc:
        raise NoScheduleField(field)
    v = item_doc[field]
    if isinstance(v, str):
        return [v] if v.strip() else []
    out = []
    for row in v if isinstance(v, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("schedule"), str) or not row["schedule"]:
            continue
        frm = date_of(row.get("effective_from"))
        if frm is None or on is None or frm <= on:
            out.append(row["schedule"])
    return out


def witnessed(item_doc: dict, settings: dict, on: datetime.date | None) -> bool:
    rule = settings.get("witness_rule") or WITNESS[0]
    if rule == "No disposal":
        return False
    if rule == "Every disposal":
        return True
    have = schedules_of(item_doc, (settings.get("schedule_field") or DEFAULT_SCHEDULE_FIELD).strip(), on)
    wanted = lines(settings.get("witness_schedules"))
    return bool(have) and (not wanted or any(s in wanted for s in have))


LOCK_RULE = "disposal locked once the visit is recorded"      # the manifest's save rule, after the prefix
LOCKED_FIELDS = ("lines", "store", "officer_name", "authority", "visit_date", "signed_form", "prior_notice_on")


def lock_holds(rule: dict | None) -> bool:
    """The save rule really locks the record: on, refusing, in the visit's state, over the lines and the visit, with no
    role let past it. A rule left on but made to flag, or emptied, locks nothing."""
    if not isinstance(rule, dict) or not rule.get("enabled") or (rule.get("mode") or "refuse") != "refuse":
        return False
    states, fields_ = lines(rule.get("states")), lines(rule.get("locked_fields"))
    return f"{PREFIX} Visit recorded" in states and all(k in fields_ for k in LOCKED_FIELDS) \
        and not lines(rule.get("bypass_roles"))


def visit_recorded(rec: dict | None) -> bool:
    return isinstance(rec, dict) and rec.get("workflow_state") == f"{PREFIX} Visit recorded" and all(
        str(rec.get(k) or "").strip() for k in ("officer_name", "authority", "visit_date", "signed_form"))


def bad_lots(lots, batches: dict, on: datetime.date) -> list[str]:
    """The lots that are blocked (disabled) or past their date on ``on``."""
    out = []
    for lot in lots:
        b = batches.get(lot) or {}
        exp = date_of(b.get("expiry_date"))
        if b.get("disabled") or (exp is not None and exp < on):
            out.append(lot)
    return out


def judge_disposal(fields: dict, item_docs: dict, batches: dict, bundle_lots: dict, record: dict | None,
                   settings: dict, today: datetime.date, used: dict | None = None, locked: bool = True) -> list[str]:
    """The stock entry's problems (empty: it may submit). A line of a witnessed item is a DISPOSAL when the entry is a
    Material Issue, or when it takes stock out of a quarantine store, or a lot that is blocked or past its date, to
    anywhere but a quarantine store (a transfer to a scrap store, a repack, a consumption). A disposal names a Disposal
    Record whose visit is recorded and locked, at the line's store, on or before the posting date, whose lines cover the
    lot and quantity (in the stock unit) less what earlier submitted issues drew on it (``used``: {(item, lot): qty})."""
    posting = date_of(fields.get("posting_date")) or today
    on = max(today, posting)
    q_stores = quarantines(settings)
    rec_name = fields.get(f("disposal_record")) or ""
    covered = {}
    for row in (record or {}).get("lines") or []:
        if isinstance(row, dict):
            k = (row.get("item"), row.get("batch") or "")
            covered[k] = covered.get(k, 0.0) + (row.get("qty") if isinstance(row.get("qty"), (int, float)) else 0)
    for k, q in (used or {}).items():
        covered[k] = covered.get(k, 0.0) - q
    purpose = fields.get("purpose")
    rows_ = [x for x in fields.get("items") or [] if isinstance(x, dict)]
    # stock transformed, not written off: a repack or manufacture whose finished lines are ALL witnessed items (a box
    # into strips of a controlled medicine); one unscheduled finished line would launder the controlled stock out. ⚠ A
    # repack between two witnessed items, or into fewer units, is not judged here: the controlled register records it.
    # With no quarantine store named, stock that sits in an unnamed quarantine store is not known to leave it.
    finished = [x for x in rows_ if x.get("t_warehouse") and not x.get("s_warehouse")]
    made = False
    if purpose in ("Repack", "Manufacture") and finished:
        try:
            made = all(witnessed(item_docs.get(x.get("item_code")) or {}, settings, on) for x in finished)
        except NoScheduleField:
            made = False
    out = []
    for i, line in enumerate(fields.get("items") if isinstance(fields.get("items"), list) else [], 1):
        if not isinstance(line, dict) or not line.get("s_warehouse"):
            continue                                       # nothing leaves a store on this line
        code = line.get("item_code")
        lots = lots_on(line, bundle_lots)
        leaves = line.get("s_warehouse") in q_stores or bad_lots(lots, batches, on)
        # written off: out of a store and into none (an issue, a consumption, a source-only repack), unless the entry
        # turns it into something else (a repack or manufacture with a finished line)
        written_off = not line.get("t_warehouse") and not made
        if not written_off and not (leaves and line.get("t_warehouse") not in q_stores):
            continue
        try:
            if not witnessed(item_docs.get(code) or {}, settings, on):
                continue
        except NoScheduleField as e:
            out.append(f"Row {i}: the app cannot read {code}'s schedules (no field {e}). Install the schedules or "
                       f"change the witness rule.")
            continue
        if not q_stores:
            out.append("Expiry and recall names no quarantine store: list them in its settings.")
            break
        if not rec_name:
            out.append(f"Row {i}: {code} is disposed of only with the regulator's visit. Name its Disposal Record.")
            continue
        if not visit_recorded(record):
            out.append(f"Row {i}: Disposal Record {rec_name} has no regulator's visit recorded yet.")
            continue
        if not locked:
            out.append(f"Disposal records are not locked: switch on the save rule {PREFIX} {LOCK_RULE}.")
            continue
        if record.get("store") and record["store"] != line.get("s_warehouse"):
            out.append(f"Row {i}: Disposal Record {rec_name} is for {record['store']}, not {line.get('s_warehouse')}.")
            continue
        visit = date_of(record.get("visit_date"))
        if visit is not None and visit > posting:
            out.append(f"Row {i}: the regulator's visit on {visit} is after this disposal's date.")
            continue
        need = lots or {"": stock_qty_of(line)}
        for lot, q in need.items():
            if covered.get((code, lot), 0.0) + 1e-9 < q:
                out.append(f"Row {i}: Disposal Record {rec_name} does not cover {code} lot {lot or '(none)'} x {q:g}"
                           " (what earlier issues drew on it counted).")
                break
            covered[(code, lot)] = covered.get((code, lot), 0.0) - q     # two lines of one lot draw on one record line
    return out


def erp_stock_answer(problems: list[str]) -> dict:
    """The ERP connector's own stock entry (SAP brings its receipts and its disposals as stock entries, every few minutes
    in the background): never refused, its problems written into the entry's *ERP check* field."""
    if not problems:
        return {"verdict": "allow"}
    more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
    return {"verdict": "fill", "fields": {f("erp_check"): fit(problems[0], TEXT_MAX - len(more)) + more}}


def judge_count(fields: dict, item_docs: dict, batches: dict, bundle_lots: dict, settings: dict,
                today: datetime.date) -> list[str]:
    """A stock reconciliation's problems: a count never disposes of witnessed stock. A line that lowers a lot held in a
    quarantine store, or a lot that is blocked or past its date, of a witnessed item, is refused (dispose of it by an
    issue naming its Disposal Record)."""
    on = max(today, date_of(fields.get("posting_date")) or today)
    q_stores = quarantines(settings)
    out = []
    for i, line in enumerate(fields.get("items") if isinstance(fields.get("items"), list) else [], 1):
        if not isinstance(line, dict):
            continue
        new, cur = line.get("qty"), line.get("current_qty")
        if not (isinstance(new, (int, float)) and isinstance(cur, (int, float)) and new < cur):
            continue
        lots = lots_on(line, bundle_lots) or lots_on(
            {"serial_and_batch_bundle": line.get("current_serial_and_batch_bundle")}, bundle_lots)
        if line.get("warehouse") not in q_stores and not bad_lots(lots, batches, on):
            continue
        code = line.get("item_code")
        try:
            if not witnessed(item_docs.get(code) or {}, settings, on):
                continue
        except NoScheduleField as e:
            out.append(f"Row {i}: the app cannot read {code}'s schedules (no field {e}). Install the schedules or "
                       f"change the witness rule.")
            continue
        out.append(f"Row {i}: a count may not dispose of {code}: issue it naming its Disposal Record.")
    return out


def disposal_answer(problems: list[str]) -> dict:
    if not problems:
        return {"verdict": "allow"}
    more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
    return {"verdict": "refuse", "reason": fit(problems[0], TEXT_MAX - len(more)) + more}


# ── a press's answer (the Desk action's closed vocabulary) ────────────────────────────────────────────────────────


def message(title: str, body: str, level: str = "success", refresh: bool = True) -> dict:
    out = {"message": {"title": fit(title, 60), "body": fit(body, 280), "level": level}}
    if refresh:
        out["refresh"] = True
    return out


def block_answer(outcomes: dict, stores: int, people: int, depth: str, sales: int | None = None) -> dict:
    """*Blocked 3 lots. 1 already blocked. Stock found in 2 stores; 14 sales to 9 customers.*"""
    words = []
    for k in ("block", "already", "no_expiry", "not_found", "refused", "changed"):
        n = outcomes.get(k, 0)
        if n:
            words.append(f"{n} {OUTCOME_WORDS[k]}" if k != "block" else f"Blocked {n} lot{'s' if n != 1 else ''}")
    found = f"Stock found in {stores} store{'s' if stores != 1 else ''}" if stores else "No stock found"
    sales = people if sales is None else sales
    who = (f"{sales} sale{'s' if sales != 1 else ''} to {people} customer{'s' if people != 1 else ''}"
           if depth == "Consumer" else f"customers not traced at {depth.lower()} depth")
    level = "warning" if any(outcomes.get(k) for k in ("no_expiry", "not_found", "refused", "changed")) else "success"
    return message("Recall", ". ".join(words) + f". {found}; {who}.", level)
