"""S22 — a customer's own loyalty programme: the rules run in YOUR service, the records stay in the SHOP.

Every record this service writes is one of the manifest's record types (``PP LYL …``), written through the record API
with the one integration user's key, so staff see them on the shop's own screens and nothing runs inside the shop.

Every ledger row is NAMED by its unique key (``source_key``: the document and the event). The shop itself refuses a
second row with the same name, and this service treats that refusal as "already done": a replayed event, or a crash
between the shop's write and your own note that you handled it, never writes a second row. The money arithmetic is
``money.py``'s, and only there.

Handlers take ``t`` (the shop: ``get``, ``list``, ``insert``, ``update``), ``s`` (``Settings``) and ``today`` (an ISO
date, so the tests own the clock).

The wallet's pieces here (``member_lock``, the settings' wallet fields, and ``on_sale`` earning nothing on a sale paid
with the wallet) are adapted from CitiXsys's private reference implementation @ 74c99d5; a defect here may be a defect
there — report it on the Partner feedback forms.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import fcntl
import hashlib
import json
import os

import money
import outside
from shop import Duplicate, ShopError

LEDGER, MEMBER, PLAN, SETTINGS = "PP LYL Ledger", "PP LYL Member", "PP LYL Plan", "PP LYL Settings"
BALANCE = "PP LYL Balance"
LOCKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "locks")   # set from PP_STATE at start


@contextlib.contextmanager
def member_lock(customer: str):
    """One member's cash back at a time. The till's wallet calls are answered on several threads (and a second process
    may share the state folder), so a file lock there keeps two tills from reading the same balance at once."""
    os.makedirs(LOCKS, exist_ok=True)
    path = os.path.join(LOCKS, hashlib.sha256((customer or "").encode()).hexdigest()[:24])
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def key(*parts) -> str:
    return ":".join(str(p) for p in parts)


def day(d, plus: int = 0) -> str:
    return (_dt.date.fromisoformat(str(d)[:10]) + _dt.timedelta(days=plus)).isoformat()


def insert_once(t, doc: dict) -> bool:
    """True when this call made the row; False when the shop already holds a row with that unique key."""
    try:
        t.insert(doc)
        return True
    except Duplicate:
        return False


class Settings:
    """The programme's settings (``PP LYL Settings`` record ``Default``) and plans (``PP LYL Plan``), edited by the shop
    in Desk and read fresh at every job."""

    def __init__(self, raw: dict, plans: list[dict]):
        # 0 is a real precision (a currency with no decimals); only an absent setting takes the default of 2
        self.places = int(raw["currency_precision"]) if raw.get("currency_precision") is not None else 2
        self.currency = raw.get("currency") or ""
        self.return_days = int(raw.get("return_days") or 0)
        self.window_days = int(raw.get("tier_window_days") or 365)
        self.default_plan = raw.get("default_plan")
        self.walk_in = {x.strip() for x in (raw.get("walk_in_customers") or "").splitlines() if x.strip()}
        self.plans = {p["name"]: p for p in plans}
        self.tier_groups = {p["customer_group"] for p in plans if p.get("customer_group")}
        # the wallet: the cash back as a payment at the till (service/wallet.py)
        self.wallet_mode = raw.get("wallet_mode_of_payment") or ""
        self.max_redemption_percent = money.D(raw.get("max_redemption_percent") or 0)
        self.earn_on_redemption = bool(int(raw.get("earn_on_redemption") or 0))
        # the opt-in adapter to the chain's own loyalty system (service/outside.py): off while the address is empty
        self.loyalty_api = (raw.get("loyalty_api") or "").strip()
        self.loyalty_key = (raw.get("loyalty_api_key") or "").strip()

    @classmethod
    def load(cls, t) -> "Settings":
        plans = t.list(PLAN, [["active", "=", 1]], ["name", "customer_group", "rank", "spend_threshold",
                                                    "discount_percent", "cash_back_percent"], order_by="rank asc")
        return cls(t.get(SETTINGS, "Default") or {}, plans)

    def plan(self, name) -> dict:
        return self.plans.get(name) or {}

    def money(self, x) -> str:
        return f"{self.currency} {money.rnd(x, self.places):,}".strip()


def enrol(t, s: Settings, customer: str, today: str) -> str:
    """A new customer joins the default plan and its customer group (the group is what the till's promotion reads)."""
    if not customer or customer in s.walk_in or not s.default_plan:
        return "skipped"
    c = t.get("Customer", customer)
    if not c:
        return "no such customer"
    made = insert_once(t, {"doctype": MEMBER, "customer": customer, "plan": s.default_plan, "status": "Active",
                           "enrolled_on": today})
    group = s.plan(s.default_plan).get("customer_group")
    if group and c.get("customer_group") not in s.tier_groups:
        t.update("Customer", customer, {"customer_group": group})
    return "enrolled" if made else "already enrolled"


def member(t, s: Settings, customer: str, today: str) -> dict | None:
    if not customer or customer in s.walk_in:
        return None
    m = t.get(MEMBER, customer)
    if m is None and enrol(t, s, customer, today) != "skipped":
        m = t.get(MEMBER, customer)
    return m


def on_sale(t, s: Settings, invoice: str, today: str) -> dict:
    inv = t.get("POS Invoice", invoice)
    if not inv or int(inv.get("docstatus") or 0) != 1:
        return {"result": "not booked"}
    if inv.get("is_return"):
        return on_return(t, s, inv)
    m = member(t, s, inv.get("customer"), today)
    if m is None:
        return {"result": "no member"}
    value = money.rnd(money.goods_value(inv), s.places)     # grand total less gift cards: tiers' figure, returns' scale
    if value <= 0:
        return {"result": "nothing to earn"}
    rate = 0 if _paid_with_wallet(s, inv) else s.plan(m.get("plan")).get("cash_back_percent") or 0
    amount = money.earned(money.earn_base(inv), rate, s.places)     # less the goods' share of a tender discount
    # a sale that earns nothing (paid with Member cash, or a plan with no cash back) still writes its Earn row, at 0 and
    # Cancelled: the row carries the sale's value, so the year's spend and the tiers still count it, and a return of it
    # still finds the row
    posted = str(inv.get("posting_date"))[:10]
    made = insert_once(t, {
        "doctype": LEDGER, "source_key": key("POS Invoice", invoice, "earn"), "customer": inv["customer"],
        "entry_type": "Earn", "status": "Pending" if amount > 0 else "Cancelled", "amount": amount,
        "earned_amount": amount, "sale_base": value, "against_sale": invoice,
        "posting_date": posted, "credit_on": day(posted, s.return_days + 1)})
    tell_outside(s, inv["customer"], invoice, value, amount, key("POS Invoice", invoice, "earn"))
    return {"result": "earned" if amount > 0 else "nothing to earn", "earned": str(amount), "row_made": made}


def tell_outside(s: Settings, customer: str, ref: str, value, earned, idem: str):
    """The opt-in adapter (``outside.py``): the chain's own loyalty system hears each change of what the customer earned,
    once (``idem`` is the ledger row's unique key). Down: raises, so the feed retries the event. Refused for good: noted by
    its status, and the event is done."""
    if not s.loyalty_api:
        return
    try:
        outside.of(s).post_earned(customer, ref, str(value), str(earned), s.currency, idem=idem)
    except outside.LoyaltyRefused as e:
        print(json.dumps({"loyalty_system": "refused", "status": e.status}), flush=True)


def _paid_with_wallet(s: Settings, inv: dict) -> bool:
    """A sale paid partly or wholly with the cash back earns nothing, unless the settings say it does
    (``earn_on_redemption``)."""
    if s.earn_on_redemption or not s.wallet_mode:
        return False
    return any(p.get("mode_of_payment") == s.wallet_mode and money.D(p.get("amount")) > 0
               for p in inv.get("payments") or [])


def _reversals(t, sale: str, but: str) -> list[dict]:
    return [r for r in t.list(LEDGER, [["against_sale", "=", sale], ["entry_type", "in", ["Return", "Cancel"]]],
                              ["name", "entry_type", "status", "amount", "sale_base"]) if r["name"] != but]


def _settle_pending(t, sale: str):
    """A Pending earning holds what is still to be credited: what it earned less the reversals netted against it.
    Recomputed from the rows every time, so the replay after a crash heals it."""
    earn = t.get(LEDGER, key("POS Invoice", sale, "earn"))
    if not earn or earn.get("status") not in ("Pending", "Cancelled"):
        return
    netted = sum((-money.D(r["amount"]) for r in _reversals(t, sale, "") if r["status"] == "Netted"), money.D(0))
    left = money.D(earn["earned_amount"]) - netted
    t.update(LEDGER, earn["name"], {"amount": max(left, money.D(0)), "status": "Pending" if left > 0 else "Cancelled"})


def _take_back(t, sale, this_key, entry_type, amount, base, customer, posted) -> bool:
    """While the earning is still Pending the reversal is NETTED against it (it reduces it); after it was credited, the
    reversal is a negative Credited row."""
    earn = t.get(LEDGER, key("POS Invoice", sale, "earn"))
    pending = earn.get("status") in ("Pending", "Cancelled")
    made = insert_once(t, {"doctype": LEDGER, "source_key": this_key, "customer": customer, "entry_type": entry_type,
                           "status": "Netted" if pending else "Credited", "amount": -amount,
                           "sale_base": -money.D(base), "against_sale": sale, "posting_date": posted})
    if pending:
        _settle_pending(t, sale)
    return made


def on_return(t, s: Settings, ret: dict) -> dict:
    sale = ret.get("return_against")
    earn = t.get(LEDGER, key("POS Invoice", sale, "earn")) if sale else None
    if not earn:
        return {"result": "the sale earned nothing"}
    this_key = key("POS Invoice", ret["name"], "return")
    prior = _reversals(t, sale, this_key)
    returned_before = sum((-money.D(r["sale_base"]) for r in prior if r["entry_type"] == "Return"), money.D(0))
    already = sum((-money.D(r["amount"]) for r in prior), money.D(0))
    this = abs(money.D(ret.get("grand_total")))
    amount = money.reversal(earn["earned_amount"], earn["sale_base"], returned_before, this, already, s.places)
    made = _take_back(t, sale, this_key, "Return", amount, this, ret.get("customer"), str(ret.get("posting_date"))[:10])
    tell_outside(s, ret.get("customer"), ret["name"], -this, -amount, this_key)
    return {"result": "reversed", "amount": str(amount), "row_made": made}


def on_cancel(t, s: Settings, invoice: str, today: str) -> dict:
    earn = t.get(LEDGER, key("POS Invoice", invoice, "earn"))
    if not earn:
        return {"result": "the sale earned nothing"}
    this_key = key("POS Invoice", invoice, "cancel")
    others = _reversals(t, invoice, this_key)
    already = sum((-money.D(r["amount"]) for r in others), money.D(0))
    # a partial return already took its part out of the year's spend, so the cancellation takes out only the rest
    # (cancelling a return leaves its Return row, and the sale is cancelled after it)
    returned = sum((-money.D(r["sale_base"]) for r in others if r["entry_type"] == "Return"), money.D(0))
    base = max(money.D(earn["sale_base"]) - returned, money.D(0))
    amount = money.cancellation(earn["earned_amount"], already, s.places)
    made = _take_back(t, invoice, this_key, "Cancel", amount, base, earn["customer"], today)
    tell_outside(s, earn["customer"], invoice, -base, -amount, this_key)
    return {"result": "reversed in full", "amount": str(amount), "row_made": made}


def credit_due(t, s: Settings, today: str) -> list[str]:
    done = []
    for r in t.list(LEDGER, [["entry_type", "=", "Earn"], ["status", "=", "Pending"], ["credit_on", "<=", today]],
                    ["name", "against_sale"]):
        _settle_pending(t, r["against_sale"])      # a return whose own settle was lost is netted before the credit
        r = t.get(LEDGER, r["name"]) or {}
        if r.get("status") != "Pending" or money.D(r.get("amount")) <= 0:
            continue
        t.update(LEDGER, r["name"], {"status": "Credited"})
        done.append(r["name"])
    return done


def spend(t, s: Settings, customer: str, today: str):
    rows = t.list(LEDGER, [["customer", "=", customer], ["entry_type", "in", ["Earn", "Return", "Cancel"]],
                           ["posting_date", ">", day(today, -s.window_days)]], ["sale_base"])
    return sum((money.D(r["sale_base"]) for r in rows), money.D(0))


def tier_for(s: Settings, spent) -> str | None:
    best = None
    for p in sorted(s.plans.values(), key=lambda p: p.get("rank") or 0):
        if money.D(p.get("spend_threshold")) <= spent:
            best = p["name"]
    return best


def evaluate_tiers(t, s: Settings, today: str) -> list[dict]:
    """Upgrade or drop each member to what the spend window's spend reaches, by moving the customer's group first:
    the plan moves only once the group has, so the till key's plan and the till's promotion never disagree."""
    moved = []
    for m in t.list(MEMBER, [["status", "=", "Active"]], ["name", "customer", "plan"]):
        target = tier_for(s, spend(t, s, m["customer"], today)) or s.default_plan
        group = s.plan(target).get("customer_group")
        if group and (t.get("Customer", m["customer"]) or {}).get("customer_group") != group:
            try:
                t.update("Customer", m["customer"], {"customer_group": group})
            except ShopError as e:       # the shop refuses this customer: it stays as it is, the others still move
                moved.append({"customer": m["customer"], "refused": e.status})
                continue
        if m["plan"] != target:
            t.update(MEMBER, m["name"], {"plan": target})
            moved.append({"customer": m["customer"], "from": m["plan"], "to": target})
    return moved


def balance(t, customer: str):
    rows = t.list(LEDGER, [["customer", "=", customer], ["status", "in", ["Credited", "Pending"]]], ["amount", "status"])
    credited = sum((money.D(r["amount"]) for r in rows if r["status"] == "Credited"), money.D(0))
    pending = sum((money.D(r["amount"]) for r in rows if r["status"] == "Pending"), money.D(0))
    return credited, pending


def daily_balances(t, s: Settings, today: str) -> list[str]:
    """One balance row per member for the day that ended (the kit's *balance report* recipe): the opening is that
    member's last row's closing, the closing is the member cash they can spend now (``balance``'s credited part), the
    change is the difference. Named ``balance:<customer>:<day>``, so a second run of the daily job writes nothing.
    A Report Builder report over these rows, filtered by date, reads the opening of the first day and the closing of
    the last. Bound: the closing is taken when the job runs (the first pass after 02:00 UTC), so a move made between
    midnight and the run counts in the day that ended."""
    ended, made = day(today, -1), []
    for m in t.list(MEMBER, [["status", "=", "Active"]], ["customer"]):
        c = m["customer"]
        last = t.list(BALANCE, [["customer", "=", c], ["balance_date", "<", ended]], ["balance_date", "closing"],
                      order_by="balance_date desc", limit=1)
        opening = money.D(last[0]["closing"]) if last else money.D(0)
        closing = balance(t, c)[0]
        doc = {"doctype": BALANCE, "balance_key": key("balance", c, ended), "customer": c, "balance_date": ended,
               "opening": money.rnd(opening, s.places), "change": money.rnd(closing - opening, s.places),
               "closing": money.rnd(closing, s.places)}
        if insert_once(t, doc):
            made.append(doc["balance_key"])
    return made
