"""The till harness — runs INSIDE the shop's console (as Administrator), on a STAGING shop; used by the money kit.

It does what a cashier's day does, through the till's OWN calls:
- ``open_day`` — a submitted POS Opening Entry on a terminal of our own. Shape copied from
  ivendnext/iVendNext_PWA · apps/ivendnext_mpos/ivendnext_mpos/tests/test_offline_drain_compose.py ``_open_session``
  @ 05bb4dab92f294edac7b9d5bbac697d3072a4978;
- ``preview`` / ``book`` — the till's whitelisted ``api.mpos_cart.recompute`` and ``api.mpos_tender.submit_tender``,
  called as the cashier with an enrolled device;
- ``close_day`` — the engine's own closing, the way the till's drawerless close builds it: build from the opening,
  counted = expected, submit. Copied from the same repo · ``business_logic/pos_session.py`` ``close_session`` @ the
  same SHA (without its operator fences, which guard a live cashier, not a test).
A defect in a copied shape is a defect there: report it on Retail mPOS's board.

⛔ Every day ``open_day`` opens is closed by ``close_day`` — callers use ``with day(...)``. ``open_days()`` lists any
opening with no SUBMITTED closing pointing back at it (never a status filter).

THE SHOP it rings at is a setting, never a value in this file: the cashier (a user who sells), the device enrolled for
them, the POS profile, and the terminal (made on the profile's store if it does not exist). From ``shop.json`` beside this
file when there is one, or ``configure_from(<file>)`` (the money kit's step ``shop:<file>``); shape: ``shop.example.json``.
A call that needs a value that is not set fails, naming it — before any day is opened.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets

import frappe
from frappe.utils import flt

PERSONA = DEVICE = PROFILE = TERMINAL = None   # the shop: configure() / configure_from() / shop.json beside this file
SHOP_FROM = None
SHOP_KEYS = {"cashier": "PERSONA", "device": "DEVICE", "profile": "PROFILE", "terminal": "TERMINAL"}
SIM_FLAG = "custom_mpos_simulated_card"   # mpos_tender.SIM_CARD_FLAG @ 05bb4dab


def configure(cashier: str, device: str, profile: str, terminal: str, source: str = "configure()") -> None:
    global PERSONA, DEVICE, PROFILE, TERMINAL, SHOP_FROM
    PERSONA, DEVICE, PROFILE, TERMINAL, SHOP_FROM = cashier, device, profile, terminal, source


def configure_from(path: str) -> None:
    """A shop file: {"cashier": …, "device": …, "profile": …, "terminal": …} (other keys, such as a note, are ignored)."""
    d = json.load(open(path))
    missing = [k for k in SHOP_KEYS if not d.get(k)]
    if missing:
        raise RuntimeError(f"the shop file {path} does not give {missing}")
    configure(*(d[k] for k in SHOP_KEYS), source=path)


def shop() -> dict:
    return {k: globals()[v] for k, v in SHOP_KEYS.items()}


def need(name: str) -> str:
    """The value of PERSONA / DEVICE / PROFILE / TERMINAL, or a clear failure saying how to set it."""
    v = globals()[name]
    if not v:
        key = next(k for k, n in SHOP_KEYS.items() if n == name)
        raise RuntimeError(f"till: no shop {key} is set — give a shop file (shop.json beside till.py, or the kit's step "
                           f"shop:<file>; shape: shop.example.json)")
    return v


_BESIDE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shop.json")
if os.path.isfile(_BESIDE):
    configure_from(_BESIDE)


def ukey(tag: str) -> str:
    return f"pp-p2b-{tag}-{secrets.token_hex(5)}"


def sim_card_auth(tag: str) -> dict:
    """The simulated card leg (the till's demo path), shape from test_preview_book_divergence.py @ 05bb4dab."""
    return {"kind": "card", "auth": {"custom_credit_card_name": "SIMULATED DEMO CARD", "card_last4": "0042",
                                     "custom_expiry_date": "2031-12", "card_authorization_code": f"SIM-{tag}"}}


@contextlib.contextmanager
def as_cashier(user: str | None = None, device: str | None = None):
    user, device = user or need("PERSONA"), device or need("DEVICE")
    prev = frappe.session.user
    frappe.set_user(user)
    frappe.local.form_dict = frappe._dict(device_id=device)
    # a console session carries no language, and the booking writes the total in words (measured: num2words(None))
    frappe.local.lang = frappe.local.lang or "en"
    try:
        yield
    finally:
        frappe.set_user(prev)


@contextlib.contextmanager
def simulated_card(profile: str | None = None):
    """The till takes the simulated card for the run; the profile's own value is put back after."""
    profile = profile or need("PROFILE")
    prev = frappe.db.get_value("POS Profile", profile, SIM_FLAG)
    frappe.db.set_value("POS Profile", profile, SIM_FLAG, 1)
    frappe.db.commit()
    try:
        yield
    finally:
        frappe.db.set_value("POS Profile", profile, SIM_FLAG, prev or 0)
        frappe.db.commit()


BOUND_KEY = "mpos_pos_profile"   # mpos_shell.BOUND_PROFILE_KEY @ 05bb4dab: the outlet a user's till is bound to


@contextlib.contextmanager
def bound_to(profile: str, user: str | None = None):
    """The till rings at the outlet the user is BOUND to (a user default), not the profile of the day it opened. For a sale at
    another profile — a store a roll-out made — bind the persona to it for the run and put the earlier binding back after."""
    user = user or need("PERSONA")
    prev = frappe.defaults.get_user_default(BOUND_KEY, user)
    frappe.defaults.set_user_default(BOUND_KEY, profile, user)
    frappe.db.commit()
    try:
        yield
    finally:
        frappe.db.rollback()
        if prev:
            frappe.defaults.set_user_default(BOUND_KEY, prev, user)
        else:
            frappe.db.delete("DefaultValue", {"parent": user, "defkey": BOUND_KEY})
        frappe.db.commit()
        frappe.clear_cache(user=user)


def ensure_terminal(profile: str | None = None) -> str:
    """The programme's terminal for a profile: one for the shop's own profile (``TERMINAL``), one per other profile (a terminal
    belongs to the store of its profile — a sale can be rung at a store a roll-out made)."""
    profile = profile or need("PROFILE")
    store = frappe.db.get_value("POS Profile", profile, "warehouse")
    term = need("TERMINAL") if profile == PROFILE else f"{need('TERMINAL')}-{profile.replace(' ', '-')}"
    if not frappe.db.exists("POS Terminal", term):
        company = frappe.db.get_value("POS Profile", profile, "company")
        frappe.get_doc({"doctype": "POS Terminal", "name": term, "company": company, "store": store,
                        "hardware_id": "pp-p2b"}).insert(ignore_permissions=True, set_name=term)
        frappe.db.commit()
    return term


def open_day(user: str | None = None, profile: str | None = None) -> str:
    user, profile = user or need("PERSONA"), profile or need("PROFILE")
    prev = frappe.session.user
    frappe.set_user("Administrator")
    term = ensure_terminal(profile)
    doc = frappe.get_doc({
        "doctype": "POS Opening Entry", "period_start_date": frappe.utils.get_datetime(),
        "posting_date": frappe.utils.getdate(), "user": user, "pos_profile": profile,
        "custom_current_cashier": user, "custom_active_pos_terminal": term, "custom_shift_start_on_terminal": term,
        "custom_mpos_drawered_open": 0, "company": frappe.db.get_value("POS Profile", profile, "company"),
    })
    doc.set("balance_details", [{"mode_of_payment": "Cash", "opening_amount": 0}])
    doc.submit()
    frappe.db.commit()
    frappe.set_user(prev)
    return doc.name


def close_day(opening: str) -> str:
    from ivendnext_pos.ivendnext_pos.doc_events.pos_closing_entry import (
        make_closing_entry_from_opening,
        submit_pos_closing,
    )
    from ivendnext_pos.ivendnext_pos.doc_events.pos_closing_entry_utils import update_pos_closing_amount

    prev = frappe.session.user
    frappe.set_user("Administrator")
    try:
        closing = make_closing_entry_from_opening(opening, None)
        for row in closing.get("payment_reconciliation", []):
            update_pos_closing_amount(closing.get("name"), row.get("name"), flt(row.get("expected_amount")))
        submit_pos_closing(closing.get("name"))
        frappe.db.commit()
        return closing.get("name")
    finally:
        frappe.set_user(prev)


@contextlib.contextmanager
def day(user: str | None = None, profile: str | None = None, record: dict | None = None):
    """Open a day, yield its opening, ALWAYS close it — even when the body failed."""
    opening = open_day(user, profile)
    if record is not None:
        record.setdefault("openings", []).append(opening)
    try:
        yield opening
    finally:
        frappe.db.rollback()   # never commit a failed body's half-writes into the closing (bookings commit as made)
        closing = close_day(opening)
        status = frappe.db.get_value("POS Closing Entry", closing, "status")
        if status != "Submitted":   # a close that did not finish leaves the day open: say so loudly
            raise RuntimeError(f"the day {opening} did not close: its closing {closing} is {status}")
        if record is not None:
            record.setdefault("closings", []).append(closing)


def open_days() -> list[str]:
    """Every opening not truly closed: no SUBMITTED closing pointing back, or that closing did not finish (Queued /
    Failed), or the opening does not read Closed. Never a status filter alone, never the back-reference alone (we
    measured a submitted closing stuck at Queued whose opening still read Open)."""
    openings = frappe.get_all("POS Opening Entry", filters={"docstatus": 1}, fields=["name", "status"])
    done = {c.pos_opening_entry for c in frappe.get_all("POS Closing Entry", filters={"docstatus": 1},
                                                        fields=["pos_opening_entry", "status"]) if c.status == "Submitted"}
    return sorted(o.name for o in openings if o.name not in done or o.status != "Closed")


def preview(cart: dict) -> dict:
    from ivendnext_mpos.api import mpos_cart

    with as_cashier():
        return mpos_cart.recompute(json.dumps(cart))


class CheckRefused(Exception):
    """The shop's check before payment did not let this sale be paid: the till goes back to the basket, nothing books."""


def check_round(cart: dict, key: str) -> dict | None:
    """What the till's Pay does before the payment sheet opens, when the shop has a check before payment switched on
    (row SET5): ``api.mpos_tender.check_before_tender`` prices the basket and asks each check; an *ask* is answered Yes
    by the cashier (``confirm_check``); then the card push's own gate (``card_push_amount``), as the till's terminal step.
    A refusal anywhere, or a manager's approval this harness cannot give, raises ``CheckRefused`` with the till's words. ``None`` when no check answers this till (every sale before Wave B), so the
    booking is exactly what it was. Call it as the cashier.
    ⚠ The check's call rolls the request's transaction back before it asks the partner (the product's rule), so
    everything before it is committed here first."""
    from ivendnext_mpos.api import mpos_tender

    door = getattr(mpos_tender, "check_before_tender", None)
    if door is None:                # a shop before Wave B has no check
        return None
    frappe.db.commit()
    res = door(json.dumps(cart), key)
    if not res.get("checked"):
        return None
    if res["verdict"] == "ask":
        mpos_tender.confirm_check(key)
        frappe.db.commit()
    elif res["verdict"] != "allow":
        raise CheckRefused(res.get("reason") or res["verdict"])
    # the door a real till calls before the terminal charges a card: the round must hold for THIS basket and the card
    # method the booking books. The booking itself only flags a card sale whose round does not hold (money is taken by
    # then), so without this a basket the till would refuse could book here and read as matched (SET5 review)
    from ivendnext_mpos.business_logic import mpos_tender as tender_logic
    try:
        tender_logic.card_push_amount(cart, sale_key=key)
    except Exception as e:  # noqa: BLE001 — the till goes back to the basket; nothing books
        frappe.db.rollback()
        raise CheckRefused(str(e)) from None
    return res


def book(cart: dict, tenders: list, key: str) -> dict:
    from ivendnext_mpos.api import mpos_tender

    with as_cashier():
        check_round(cart, key)      # nothing books when the shop's check refuses (CheckRefused)
        res = mpos_tender.submit_tender(json.dumps(cart), json.dumps(tenders), device_id=need("DEVICE"),
                                        idempotency_key=key)
    # a web request commits on success; a console does not — without this the day's close rolls the sale back
    # (measured on our test bench: 36 of the first baseline's 64 bookings were discarded this way)
    frappe.db.commit()
    return res


def cart_of(lines: list[tuple], customer: str | None = None, sale_discount: dict | None = None) -> dict:
    """``lines`` = [(item_code, qty) or (item_code, qty, markdown_pct)]; a markdown rides as ``{"pct": n}``, the
    cart shape ``discount.py`` reads (and the golden file's)."""
    out = []
    for i, ln in enumerate(lines):
        row = {"item_code": ln[0], "qty": ln[1], "uom": "Nos", "luid": f"l{i}"}
        if len(ln) > 2 and ln[2]:
            row["markdown"] = {"pct": ln[2]}
        out.append(row)
    cart = {"lines": out, "sale_ref": secrets.token_hex(4)}
    if customer:
        cart["customer"] = customer
    if sale_discount:
        cart["sale_discount"] = sale_discount
    return cart


def sale_return(sale: str, opening: str) -> str:
    """A return of a whole booked sale, submitted INSIDE an open day, built by the stock credit note
    (``make_sales_return``); the day it belongs to is the one the sale was rung in, so the day's close counts it.
    ⚠ Not the till's or the Desk's Sale Return: those are composed by ``make_return_doc`` (called through
    ``ivendnext_pos.api.pos_invoice_sale_return.get_sale_return_pos_doc``), which marks the return and every line
    ``Sale Return``; this one keeps the sale's line modes. A check that reads a return's line modes builds it that way
    instead (APPF run 3's review). The feed and the warehouse see a return either way."""
    from erpnext.accounts.doctype.pos_invoice.pos_invoice import make_sales_return

    prev = frappe.session.user
    frappe.set_user("Administrator")
    try:
        doc = make_sales_return(sale)
        doc.custom_pos_opening_entry = opening
        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc.name
    finally:
        frappe.set_user(prev)


def cancel_sale(sale: str) -> None:
    """Cancel a booked sale while its day is still open (a cancelled invoice is no revenue)."""
    prev = frappe.session.user
    frappe.set_user("Administrator")
    try:
        frappe.get_doc("POS Invoice", sale).cancel()
        frappe.db.commit()
    finally:
        frappe.set_user(prev)
