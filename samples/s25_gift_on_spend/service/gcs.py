"""S25 — the rules of *Gift card on spend*, stated once and tested (tests/test_rules.py). Pure: no network, no clock.

- **Spend** is what the customer paid for a sale, tax included (its grand total), less its gift card lines (a card sold,
  recharged or paid out on it), less anything paid on it with a gift card, store credit, a partner's wallet, loyalty
  points or on account,
  less a tender discount (booked as a write-off; the grand total keeps it) and less anything still outstanding — so
  stored value and credit never earn a gift card, and a card is earned on money paid.
  Every other line counts with its own sign: an *Item Return* line in an exchange is negative, so the customer earns on
  the net they paid. A return takes off the sale's spend what it refunded (its grand total, less its own gift card
  lines and its share of a tender discount; its lines are *Sale Return*), whatever it was refunded to.
- **Cards** a sale earns: none below the threshold; else one for each full threshold, at most the shop's *cards per
  sale* (1 = one card per sale).
- **Who earns:** a submitted sale of transaction mode *Sale* (a layaway, order or quotation pays later or not at all), in
  the settings' currency, for a customer who is not a walk-in and not in a customer group the shop excludes.

Every amount is a ``Decimal`` (``D``), compared at the currency's precision; nothing here rounds money it pays out: a
card's value is the shop's figure, as typed.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

PLAIN_SALE = "Sale"                                   # POS Invoice.transaction_mode: the engine's default for a sale
# a line's transaction_mode that moves a gift card's value, never goods (engine pos_invoice_submit.py create_gift_card)
GIFT_CARD_LINES = ("Gift Certificate", "Gift Certificate Recharge", "Gift Certificate Cashback")
# Sales Invoice Payment.type that is not money paid now: a gift card or store credit spent, or the customer's account
# (the engine counts an On Account row as paid, so a booked sale's outstanding_amount is 0: the row is the only trace)
NO_EARN_TENDERS = ("Gift Certificate", "Store Credit", "On Account", "Wallet")   # Wallet: a partner's wallet (S22)
STATES = ("Issuing", "Held", "Released", "Voided", "Review")


def D(x) -> Decimal:
    """A Decimal from what the record API returns (a float, an int, a string). Through ``str`` so 0.1 stays 0.1."""
    return x if isinstance(x, Decimal) else Decimal(str(x if x is not None else 0))


def rnd(x, places: int) -> Decimal:
    return D(x).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def lines(text) -> set[str]:
    return {x.strip() for x in (text or "").splitlines() if x.strip()}


class Settings:
    """The shop's settings (``PP GCS Settings`` record ``Default``), edited in Desk and read fresh at every pass."""

    def __init__(self, raw: dict | None):
        raw = raw or {}
        self.enabled = bool(int(raw.get("enabled") or 0))
        self.currency = raw.get("currency") or ""
        self.places = int(raw["currency_precision"]) if raw.get("currency_precision") is not None else 2
        self.threshold = D(raw.get("threshold"))
        self.card_value = D(raw.get("card_value"))
        self.card_item = raw.get("card_item") or ""
        self.max_cards = max(int(raw.get("max_cards_per_sale") or 1), 1)
        self.hold_hours = int(raw["hold_hours"]) if raw.get("hold_hours") is not None else 24
        self.walk_in = lines(raw.get("walk_in_customers"))
        self.excluded_groups = lines(raw.get("excluded_customer_groups"))

    def why_not_ready(self) -> str:
        """``""`` when the settings can issue a card; else the reason, in the shop's words."""
        if not self.enabled:
            return "the app is switched off in its settings"
        if not self.currency:
            return "the settings name no currency"
        if self.threshold <= 0 or self.card_value <= 0:
            return "the threshold and the card's value must both be more than 0"
        if not self.card_item:
            return "the settings name no gift card item"
        if self.hold_hours < 0:
            return "the hold cannot be negative"
        return ""


def _gift_card_lines(doc: dict) -> Decimal:
    return sum((D(i.get("amount")) for i in doc.get("items") or [] if i.get("transaction_mode") in GIFT_CARD_LINES),
               Decimal(0))


def spend(sale: dict) -> Decimal:
    """What a booked sale counts towards the threshold (never below 0)."""
    stored_value = sum((max(D(p.get("amount")), Decimal(0)) for p in sale.get("payments") or []
                        if p.get("type") in NO_EARN_TENDERS), Decimal(0)) + D(sale.get("loyalty_amount"))
    owed = max(D(sale.get("outstanding_amount")), Decimal(0))
    tender_discount = max(D(sale.get("custom_tender_discount_amount")), Decimal(0))
    return max(D(sale.get("grand_total")) - _gift_card_lines(sale) - stored_value - owed - tender_discount, Decimal(0))


def return_spend(ret: dict) -> Decimal:
    """What a return takes off its sale's spend (a positive number): its whole value, whatever it was refunded to, less
    its share of the sale's tender discount (the engine reverses it on the return as a negative discount)."""
    reversed_discount = min(D(ret.get("custom_tender_discount_amount")), Decimal(0))
    return max(-(D(ret.get("grand_total")) - _gift_card_lines(ret)) + reversed_discount, Decimal(0))


def kept(net, threshold, issued: int) -> int:
    """How many of a sale's ``issued`` cards its net spend still earns, under the threshold they were earned with."""
    t = D(threshold)
    return min(int(max(D(net), Decimal(0)) // t), issued) if t > 0 else 0


def cards_for(amount, s: Settings) -> int:
    """How many cards a spend earns: one per full threshold, at most ``max_cards``; none below the threshold."""
    a = rnd(amount, s.places)
    if s.threshold <= 0 or a < rnd(s.threshold, s.places):
        return 0
    return min(int(a // s.threshold), s.max_cards)


def why_not_item(item: dict | None, s: Settings) -> str:
    """``""`` when the shop's gift card item can carry a promotion's card; else why not. A rechargeable card would let a
    void take money the customer paid in; a cashback card turns the promotion into cash; a store-credit card is the
    returns' own; a card that expires within the hold could never be spent."""
    if not item or not int(item.get("custom_is_gift_card") or 0) or int(item.get("disabled") or 0):
        return "the settings' gift card item is not an enabled gift card item"
    for flag, words in (("custom_recharge", "rechargeable"), ("custom_cashback", "paid out as cash"),
                        ("custom_use_as_store_credit", "store credit")):
        if int(item.get(flag) or 0):
            return f"the gift card item must not be {words}"
    days = int(item.get("custom_expiry_days") or 0)
    if days and days * 24 <= s.hold_hours:
        return "the gift card item expires before the hold ends"
    return ""


def why_no_card(sale: dict, s: Settings, customer_group: str | None) -> str:
    """``""`` when this sale may earn; else why not (a plain reason for the log, never shown to a customer)."""
    if int(sale.get("docstatus") or 0) != 1:
        return "not a booked sale"
    if int(sale.get("is_return") or 0):
        return "a return"
    if (sale.get("transaction_mode") or PLAIN_SALE) != PLAIN_SALE:
        return f"transaction mode {sale.get('transaction_mode')}"
    if (sale.get("currency") or "") != s.currency:
        return "another currency"
    customer = sale.get("customer") or ""
    if not customer or customer in s.walk_in:
        return "a walk-in"
    if customer_group and customer_group in s.excluded_groups:
        return "an excluded customer group"
    return ""


def card_key(sale: str, position: int) -> str:
    """The Card record's name: the sale and the card's position on it. The shop refuses a second record with this
    name, so one sale can never earn the same card twice."""
    return f"{sale}:{int(position)}"
