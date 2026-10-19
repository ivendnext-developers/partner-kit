"""S30's core: what to move, and what became of each unit. Pure functions: no shop, no network, standard library only.

Two jobs, both read-only here (the scripts beside this file do the calls):

  * ``plan_migration`` — from the rows of a shop's own unit table to the codes each new batch+serial item receives, by
    batch and store; what is skipped (sold), already moved, missing (no item map, no batch, no store) and what
    conflicts (a code that is already another item's serial number, or two rows with one code). One code, one item.
  * ``classify`` — what became of a unit, from its Serial No and its own stock movements. A count with *Reconcile All*
    takes every unit of the store out and puts the counted ones back in, so a unit the count did not find reads
    *Delivered*, exactly like a sold one. The ledger's voucher type tells them apart.
"""

from __future__ import annotations

COUNT = "Stock Reconciliation"
SALES = ("POS Invoice", "Sales Invoice", "Delivery Note")

# what classify answers, in the order the report prints them
IN_STOCK, DEFECTIVE, SOLD_DAY_OPEN, SOLD, COUNTED_OUT, ISSUED, OTHER_OUT, NOT_RECEIVED = (
    "in stock", "defective", "sold, till day not closed", "sold", "counted out", "issued", "out", "not received")
ORDER = (IN_STOCK, DEFECTIVE, SOLD_DAY_OPEN, SOLD, COUNTED_OUT, ISSUED, OTHER_OUT, NOT_RECEIVED)


def batch_name(template: str, old_batch: str) -> str:
    """The new item's batch for an old batch. Batch names are unique across items in this version of iVendNext, so the
    new item cannot reuse the old item's batch name; the template makes a new one (``{batch}-U`` by default)."""
    return template.format(batch=old_batch)


def plan_migration(units: list[dict], existing: dict, conf: dict) -> dict:
    """Plan the move of a unit table onto batch+serial items.

    ``units``: the source rows, with the field names of ``conf["fields"]`` (code, item, batch, warehouse, status).
    ``existing``: Serial Nos already in the shop for these codes, ``{code: {"item_code", "batch_no", "warehouse"}}``.
    ``conf``: the ``migration`` block of config.json.

    Returns ``receive`` {(new item, store, new batch): [codes]}, ``batches`` {new batch: {"item", "from"}},
    ``expected`` {(old item, store, old batch): the coded units that must move}, ``blocked`` (the lots holding a code that
    conflicts: such a lot is never counted to 0, or that pack would leave the stock unseen) and the lists ``moved`` (already a
    serial of the right item and batch), ``skipped``, ``missing`` and ``conflicts``, each entry {"code", "why"}.
    """
    f = conf["fields"]
    item_map = conf["item_map"]
    available = set(conf["available_values"])
    out = {"receive": {}, "batches": {}, "expected": {}, "blocked": set(), "moved": [], "skipped": [], "missing": [],
           "conflicts": []}
    seen: dict[str, str] = {}       # the code in capitals -> the code as written: two rows with one code is a conflict
    have_upper = {k.upper(): v for k, v in existing.items()}

    for row in units:
        code = (row.get(f["code"]) or "").strip()
        if not code:
            out["missing"].append({"code": "", "why": "a row with no code"})
            continue
        key = code.upper()          # the till reads a typed serial in capitals: two codes that differ only in case collide
        if key in seen:
            out["conflicts"].append({"code": code, "why": f"two rows carry this code (also {seen[key]})"})
            continue
        seen[key] = code
        if f.get("status") and row.get(f["status"]) not in available:
            out["skipped"].append({"code": code, "why": f"status {row.get(f['status'])!r}: only {sorted(available)} move"})
            continue
        old_item = row.get(f["item"])
        new_item = item_map.get(old_item)
        if not new_item:
            out["missing"].append({"code": code, "why": f"item {old_item!r} has no new item in item_map"})
            continue
        old_batch = row.get(f["batch"]) if f.get("batch") else None
        if not old_batch:
            out["missing"].append({"code": code, "why": "no batch: a batch+serial unit needs its batch"})
            continue
        store = (row.get(f["warehouse"]) if f.get("warehouse") else None) or conf.get("default_warehouse")
        if not store:
            out["missing"].append({"code": code, "why": "no store: set fields.warehouse or default_warehouse"})
            continue
        new_batch = batch_name(conf.get("batch_name", "{batch}-U"), old_batch)
        lot = (old_item, store, old_batch)
        out["expected"][lot] = out["expected"].get(lot, 0) + 1

        have = have_upper.get(key)
        if have and have.get("item_code") == new_item and not have.get("warehouse") and have.get("status") in (None, "", "Inactive"):
            have = None     # its receipt was cancelled (or never made): the code is received again, as Allow existing Serial No permits
        if have:
            if have.get("item_code") != new_item:
                out["conflicts"].append({"code": code, "why": f"already a serial number of item {have.get('item_code')!r}"})
                out["blocked"].add(lot)
            elif have.get("batch_no") != new_batch:
                out["conflicts"].append({"code": code, "why": f"already a serial number of {new_item} in batch {have.get('batch_no')!r}, not {new_batch!r}"})
                out["blocked"].add(lot)
            else:
                out["moved"].append({"code": code, "why": "already moved"})
            continue
        out["batches"][new_batch] = {"item": new_item, "from": old_batch}
        out["receive"].setdefault((new_item, store, new_batch), []).append(code)
    return out


def zero_rows(plan: dict, current: dict, conf: dict, expired: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Which lots of the old item may be counted to 0, and which are held.

    ``current``: the old item's stock per lot, {(old item, store, old batch): (quantity, valuation rate)}, as the shop's
    own count works it out. A lot is counted to 0 only when its quantity equals the coded units that move from it:
    otherwise packs without a code would leave the stock unseen. Such a lot is held and named with its figures, and
    nothing of it moves. A lot already at 0 whose codes have all moved is done (a second run); a lot at 0 with codes
    still to move is held too, because receiving them would make stock the shop does not have.
    A lot whose old batch has expired (``expired`` = {old batch: its expiry date}) is held: iVendNext refuses to
    receive into an expired batch. Returns (rows to count to 0, held lots)."""
    rows, held = [], []
    tmpl = conf.get("batch_name", "{batch}-U")
    for (item, store, batch), want in sorted(plan["expected"].items()):
        qty, rate = current.get((item, store, batch), (0, 0))
        if not qty:
            if (conf["item_map"][item], store, batch_name(tmpl, batch)) in plan["receive"]:
                held.append({"item": item, "warehouse": store, "batch": batch, "in_stock": 0, "with_codes": want,
                             "why": "none of this lot is in stock, yet the unit table lists codes to move: check the table"})
            continue
        if batch in (expired or {}):
            held.append({"item": item, "warehouse": store, "batch": batch, "in_stock": qty, "with_codes": want,
                         "why": f"the batch expired on {expired[batch]}: count it out by hand, it cannot be received again"})
            continue
        if (item, store, batch) in plan["blocked"]:
            held.append({"item": item, "warehouse": store, "batch": batch, "in_stock": qty, "with_codes": want,
                         "why": "a code in this lot conflicts (see conflicts): settle it first"})
            continue
        if qty != want:
            held.append({"item": item, "warehouse": store, "batch": batch, "in_stock": qty, "with_codes": want,
                         "why": f"{qty:g} in stock, {want} with a code: give the other packs a code, or count them by hand first"})
            continue
        rows.append({"item_code": item, "warehouse": store, "batch_no": batch, "qty": 0, "rate": rate})
    return rows, held


def held_receipts(held: list[dict], conf: dict) -> set:
    """The receipt groups that wait because their old lot is held: a unit received while its old pack is still in
    stock would count twice."""
    tmpl = conf.get("batch_name", "{batch}-U")
    return {(conf["item_map"][h["item"]], h["warehouse"], batch_name(tmpl, h["batch"])) for h in held}


def _clock(t) -> tuple:
    """A posting time as numbers: the shop writes 9:30 as "9:30:00", which sorts after "14:00:00" as text."""
    h, m, s = (str(t or "0:0:0").split(":") + ["0", "0"])[:3]
    return (int(h), int(m), float(s))


def _when(m: dict) -> tuple:
    return (str(m.get("posting_date") or ""), _clock(m.get("posting_time")), str(m.get("creation") or ""))


def classify(serial: dict, movements: list[dict], defective: set) -> dict:
    """What became of one unit.

    ``serial``: its Serial No {name, item_code, batch_no, warehouse, status}. ``movements``: its own submitted, uncancelled
    stock movements {voucher_type, voucher_no, type_of_transaction ("Inward" or "Outward"), posting_date, posting_time,
    creation}. ``defective``: the names of the Defective stores.

    The unit's status comes first. A unit the count found was taken out and put back, so it is in a store again and in
    stock, whatever the count's own outward entry says. Only a unit that is out (*Delivered*) is judged by its latest
    outward movement: a count says *counted out*, a sale says *sold*."""
    status, store = serial.get("status"), serial.get("warehouse")
    moves = sorted(movements, key=_when)
    last = moves[-1] if moves else None
    outs = [m for m in moves if m.get("type_of_transaction") == "Outward"]
    last_out = outs[-1] if outs else None
    res = {"serial": serial.get("name"), "item": serial.get("item_code"), "batch": serial.get("batch_no"),
           "warehouse": store, "status": status, "voucher_type": None, "voucher_no": None}

    def said(what, m=None):
        if m:
            res.update(voucher_type=m.get("voucher_type"), voucher_no=m.get("voucher_no"))
        return dict(res, result=what)

    if status == "Consumed":
        return said(ISSUED, last_out)
    if status == "Delivered":
        if not last_out:
            return said(OTHER_OUT)
        if last_out.get("voucher_type") == COUNT:
            return said(COUNTED_OUT, last_out)
        if last_out.get("voucher_type") in SALES:
            return said(SOLD, last_out)
        return said(OTHER_OUT, last_out)
    if store:
        # a till sale moves no stock until the day closes: the unit still reads Active in its store
        if last and last.get("type_of_transaction") == "Outward" and last.get("voucher_type") == "POS Invoice":
            return said(SOLD_DAY_OPEN, last)
        return said(DEFECTIVE if store in defective else IN_STOCK)
    return said(NOT_RECEIVED if status in (None, "Inactive") else OTHER_OUT)


def report(serials: list[dict], movements: dict, defective: set) -> dict:
    """``classify`` for each unit; ``movements`` = {serial: [movement, …]}. Returns {"rows": [...], "counts": {...}}."""
    rows = [classify(s, movements.get(s["name"], []), defective) for s in serials]
    counts = {k: 0 for k in ORDER}
    for r in rows:
        counts[r["result"]] += 1
    return {"rows": sorted(rows, key=lambda r: (ORDER.index(r["result"]), r["item"] or "", r["serial"] or "")),
            "counts": counts}
