"""S52 — the rules, with no web code and no network: what the cashier is told, what Pay allows, what is activated.

Each function takes what was read (the retailer's settings, the till's context, the telecom company's answer) and
returns what to answer or do, so the tests drive every rule without a server.

The four rules of guide chapter 3 shape it:
  * the plan's price enters the sale as a LINE the cashier adds (an item priced from the retailer's price list, which
    the service keeps in step with the telecom company), visible before payment; no answer of this service carries money;
  * the check at Pay is the gate: the plan, its phone and its price are confirmed with the telecom company for THIS
    customer, or the sale is refused in plain words;
  * the activation happens after payment, from the event feed, and its number is written to the retailer's own records.
"""

from __future__ import annotations

from decimal import Decimal

TEXT_MAX, BODY_MAX, PHONES_MAX = 140, 256 * 1024, 50


def plain(text: str, n: int = TEXT_MAX) -> str:
    """The till's words: printable, no angle brackets, within the cap."""
    text = " ".join("".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "").split())
    return text if len(text) <= n else text[: n - 3] + "..."


def settings_of(raw: dict | None) -> dict:
    """The retailer's ``PP TEL Settings``: its own telecom account and key, the item group its plans are in, and the
    price list the service keeps in step."""
    raw = raw or {}
    return {"account": (raw.get("telecom_account") or "").strip(), "key": (raw.get("telecom_key") or "").strip(),
            "plan_group": (raw.get("plan_item_group") or "").strip(), "price_list": (raw.get("price_list") or "").strip(),
            "walk_in": {x.strip() for x in (raw.get("walk_in_customers") or "").splitlines() if x.strip()}}


def money(minor: int, exponent: int, currency: str = "") -> str:
    value = Decimal(int(minor)).scaleb(-int(exponent))
    return f"{currency} {value:,.{int(exponent)}f}".strip()


# ---- the till key: Plans ------------------------------------------------------------------------------------------

def phones_on(lines: list) -> list[str]:
    """The item codes on the sale, each once: the telecom company says which of them are phones it has plans for."""
    out = []
    for line in lines or []:
        code = str((line or {}).get("item_code") or "")
        if code and code not in out:
            out.append(code)
    return out[:PHONES_MAX]


def plans_message(answer: dict, customer: str | None, currency: str = "") -> dict:
    """The Plans key's answer: a message only (the key adds nothing to the sale; the cashier adds the plan's item)."""
    if answer.get("refused"):
        return {"message": {"title": "No plan for this customer", "body": plain(answer["refused"], 280), "level": "warning"}}
    offers = answer.get("offers") or []
    if not offers:
        return {"message": {"title": "No phone with plans", "body": "No phone on this sale has plans from this telecom "
                            "company. Scan the phone first, then press Plans.", "level": "info"}}
    o = offers[0]
    listed = " / ".join(f"{p['name']} {money(p['price_minor'], p.get('exponent', 2), currency)} ({p['code']})"
                        for p in o["plans"])
    tail = " Add the chosen plan's item to the sale." if customer else \
        " Add the customer and the plan's item: the price is confirmed for them at Pay."
    return {"message": {"title": plain(f"Plans for {o['phone']}", 60), "body": plain(listed + "." + tail, 280),
                        "level": "success"}}


def down_message() -> dict:
    return {"message": {"title": "Telecom company not answering", "body": "The plans could not be read. Nothing was "
                        "added to the sale. Try again in a minute.", "level": "warning"}}


# ---- the check at Pay ---------------------------------------------------------------------------------------------

def plan_lines(ctx: dict, s: dict) -> list[dict]:
    return [ln for ln in ctx.get("lines") or [] if s["plan_group"] and ln.get("item_group") == s["plan_group"]]


def refuse(reason: str) -> dict:
    return {"verdict": "refuse", "reason": plain(reason)}


def check(ctx: dict, s: dict, offers) -> dict:
    """The verdict for a sale. ``offers(phones, customer)`` asks the telecom company (with THIS retailer's account) and
    may raise ``TelecomDown`` or ``TelecomRefused``; the caller turns those into a refusal (``check_answer``)."""
    wanted = plan_lines(ctx, s)
    if ctx.get("stage") != "sale":              # a return: the plan is not cancelled with the telecom company (README)
        if any(int(ln.get("qty_milli") or 0) > 0 for ln in wanted):     # but a plan sold in an exchange is never confirmed
            return refuse("Sell a plan on its own sale, not in an exchange.")
        return {"verdict": "allow"}
    if not wanted:
        return {"verdict": "allow"}             # no plan on the sale: nothing to ask the telecom company
    customer = ctx.get("customer") or ""
    if not customer or customer in s.get("walk_in", ()):  # a till puts its walk-in customer on a sale that has none
        return refuse("A phone plan needs the customer on the sale. Add them, then press Pay.")
    if any(int(ln.get("qty_milli") or 0) != 1000 for ln in wanted):
        return refuse("Sell one plan per line, each with its own phone.")
    plan_codes = {ln["item_code"] for ln in wanted}
    phones = [ln for ln in ctx.get("lines") or [] if ln.get("item_code") not in plan_codes and int(ln.get("qty_milli") or 0) > 0]
    answer = offers(phones_on(phones), customer)
    if answer.get("refused"):
        return refuse(answer["refused"])
    fits = {o["phone"]: {p["code"]: p for p in o["plans"]} for o in answer.get("offers") or []}
    units = [ln["item_code"] for ln in phones if ln["item_code"] in fits for _ in range(int(ln["qty_milli"]) // 1000)]
    exponent = int(ctx.get("currency_exponent") or 0)
    for ln in wanted:
        phone = next((ph for ph in units if ln["item_code"] in fits[ph]), None)
        if phone is None:
            return refuse(f"{ln['item_code']} needs a phone it fits on the same sale.")
        units.remove(phone)
        plan = fits[phone][ln["item_code"]]
        if int(plan.get("exponent", exponent)) != exponent or (plan.get("currency") and plan["currency"] != ctx.get("currency")):
            return refuse(f"{plan['name']} is priced in another currency by the telecom company.")
        charged = int(ln.get("rate_minor") or 0) + int(ln.get("discount_minor") or 0)   # the list price, before a discount
        if charged != int(plan["price_minor"]):
            cur = ctx.get("currency") or ""
            return refuse(f"{plan['name']} is now {money(plan['price_minor'], exponent, cur)} with the telecom company, "
                          f"not {money(charged, exponent, cur)}. In a minute, take the plan off and add it again.")
    return {"verdict": "allow"}


# ---- after payment: the activation, and the price list kept in step ------------------------------------------------

def activation_work(invoice: dict, s: dict, catalogue: list[dict]) -> list[dict]:
    """One piece of work per plan line of a paid sale: the plan, the phone it goes on, and the line's own key."""
    if int(invoice.get("docstatus") or 0) != 1 or invoice.get("is_return"):
        return []
    items = invoice.get("items") or []
    plans = {p["code"]: p for p in catalogue}
    wanted = [ln for ln in items if s["plan_group"] and ln.get("item_group") == s["plan_group"]]
    phones = [ln for ln in items if ln not in wanted]
    # one unit per phone sold, each with its own serial number (a line of 2 carries two, one per line of its serial_no)
    units = [(ln, k) for ln in phones for k in range(int(float(ln.get("qty") or 0)))]
    work = []
    for ln in wanted:
        fits = (plans.get(ln.get("item_code")) or {}).get("phones") or []
        unit = next((u for u in units if u[0].get("item_code") in fits), None)
        if unit is not None:
            units.remove(unit)
        phone, k = unit if unit else (None, 0)
        serials = [x.strip() for x in ((phone or {}).get("serial_no") or "").splitlines() if x.strip()]
        serial = serials[k] if k < len(serials) else ""
        work.append({"key": f"{invoice['name']}:{ln.get('idx')}", "sale": invoice["name"], "plan": ln.get("item_code"),
                     "phone": (phone or {}).get("item_code") or "", "serial_no": serial,
                     "customer": invoice.get("customer") or ""})
    return work


def price_changes(catalogue: list[dict], current: dict[str, dict]) -> list[dict]:
    """What to write so the retailer's price list sells each plan at the telecom company's price for THIS account:
    ``current`` maps an item code to its Item Price row on that list (``name``, ``price_list_rate``)."""
    out = []
    for p in catalogue:
        rate = Decimal(int(p["price_minor"])).scaleb(-int(p.get("exponent", 2)))
        row = current.get(p["code"])
        if row is None:
            out.append({"item_code": p["code"], "rate": rate, "name": None})
        elif Decimal(str(row.get("price_list_rate") or 0)) != rate:
            out.append({"item_code": p["code"], "rate": rate, "name": row["name"]})
    return out
