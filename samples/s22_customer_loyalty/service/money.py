"""S22 — the money rules of the cash back, stated once and tested (tests/test_money.py). Pure: no network, no clock.

- Every amount is a ``Decimal``, rounded to the currency's precision with ``ROUND_HALF_UP``.
- What a sale sold (``goods_value``, kept on the ledger as ``sale_base``): its grand total less any gift card sold,
  recharged or paid out on it. So a gift card earns once, when it is spent, never when it is sold. It is what the tiers
  count, and the scale a return is measured on (a return's grand total: the engine refuses a gift card on a return).
- Earning: ``base × rate %``, rounded, where the base (``earn_base``) is that value less the goods' share of a tender
  discount (a discount for paying a certain way, which the grand total keeps). How the sale was paid does not change
  either figure (Member cash has its own setting: ``loyalty._paid_with_wallet``).
- A return reverses its share of what the sale earned: ``earned × returned ÷ sale value``, rounded. The return that
  brings the returned total to the whole sale takes exactly what is left, so the reversals of one sale always add up
  to what it earned, and never more (the cap). Bounds: a partial return's share is by grand total, so where the lines
  carry different tax it can differ a little from the share of the discounted goods (the last return evens it out);
  and a sale discount the engine spreads over several returns, rounding each, can leave them a cent short of the
  whole sale, so a cent of cash back stays.
- A cancelled sale reverses everything not yet reversed.
- The wallet (``wallet.py``, spending the cash back at the till): a sale may take at most ``max % of the amount due`` from
  the wallet (0 = no cap), never more than the balance or the amount due. Money on the wire is in minor units
  (``amount_minor`` with ``currency_exponent``).

The three wallet functions (``from_minor``, ``to_minor``, ``redeemable``) are adapted from CitiXsys's private reference
implementation @ 74c99d5; a defect here may be a defect there — report it on the Partner feedback forms.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal

# a line's transaction_mode that moves a gift card's value, never goods (the engine's pos_invoice_submit.py); the same
# list as S25's (samples/s25_gift_on_spend/service/gcs.py). The engine refuses a gift card item on a return.
GIFT_CARD_LINES = ("Gift Certificate", "Gift Certificate Recharge", "Gift Certificate Cashback")


def D(x) -> Decimal:
    """A Decimal from what the record API returns (a float, an int, a string). Through ``str`` so 0.1 stays 0.1."""
    return x if isinstance(x, Decimal) else Decimal(str(x if x is not None else 0))


def rnd(x, places: int) -> Decimal:
    return D(x).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _gift_card_lines(doc: dict, field: str) -> Decimal:
    return sum((D(i.get(field)) for i in doc.get("items") or [] if i.get("transaction_mode") in GIFT_CARD_LINES),
               Decimal(0))


def _gift_card_tax(sale: dict) -> Decimal:
    """The tax the sale's tax rows put on its gift card lines, in the sale's currency: each row's ``item_wise_tax_detail``
    is ``{item code: [rate, amount]}`` (or ``{item code: {"tax_amount": …}}``, as the engine's own tax test also reads it)
    in the COMPANY's currency (the engine multiplies by ``conversion_rate``), and a gift card item is never a goods item,
    so its code names gift card lines only."""
    codes = {i.get("item_code") for i in sale.get("items") or [] if i.get("transaction_mode") in GIFT_CARD_LINES}
    tax = Decimal(0)
    for row in sale.get("taxes") or []:
        detail = row.get("item_wise_tax_detail") or {}
        detail = json.loads(detail) if isinstance(detail, str) else detail
        for v in (detail.get(c) for c in codes):
            tax += D(v[1] if isinstance(v, list) else (v or {}).get("tax_amount") if isinstance(v, dict) else 0)
    rate = D(sale.get("conversion_rate") or 1)
    return tax / (rate if rate > 0 else 1)


def goods_value(sale: dict) -> Decimal:
    """What a booked sale sold, gift cards aside: its grand total less its gift card lines at what they added to it
    (``net_amount``, after a sale discount, and the tax the shop's tax setup put on them; prices with tax included or
    not). A pay-out rides alone, so its sale is 0."""
    return D(sale.get("grand_total")) - _gift_card_lines(sale, "net_amount") - _gift_card_tax(sale)


def earn_base(sale: dict) -> Decimal:
    """What a booked sale earns on: its goods value less the goods' share of its tender discount (the engine spreads the
    discount over every line, a gift card's too: ``custom_tender_discount_apportioned``)."""
    goods_discount = (max(D(sale.get("custom_tender_discount_amount")), Decimal(0))
                      - _gift_card_lines(sale, "custom_tender_discount_apportioned"))
    return goods_value(sale) - goods_discount


def earned(base, rate_percent, places: int) -> Decimal:
    """What a sale earns. A negative or zero base earns nothing."""
    b = D(base)
    if b <= 0:
        return rnd(0, places)
    return rnd(b * D(rate_percent) / 100, places)


def reversal(earned_amount, sale_total, returned_before, this_return, already_reversed, places: int) -> Decimal:
    """What one return takes back (a positive number). ``sale_total`` is the sale's value (``goods_value``).

    ``returned_before``: the returned value of this sale's earlier returns; ``this_return``: this return's value (both
    positive); ``already_reversed``: what earlier returns and cancellations of this sale already took back."""
    e, total = D(earned_amount), D(sale_total)
    left = max(e - D(already_reversed), Decimal(0))
    if total <= 0 or left == 0:
        return rnd(0, places)
    if D(returned_before) + D(this_return) >= total:
        return rnd(left, places)                       # the last return takes exactly what is left
    return rnd(min(e * D(this_return) / total, left), places)


def cancellation(earned_amount, already_reversed, places: int) -> Decimal:
    """A cancelled sale: everything not yet reversed."""
    return rnd(max(D(earned_amount) - D(already_reversed), Decimal(0)), places)


def from_minor(amount_minor, exponent: int) -> Decimal:
    """A wire amount (whole minor units) as a Decimal amount of the currency."""
    return D(int(amount_minor)).scaleb(-int(exponent))


def to_minor(amount, exponent: int) -> int:
    """An amount of the currency as whole minor units (rounded half-up first)."""
    return int(rnd(amount, int(exponent)).scaleb(int(exponent)))


def redeemable(balance, amount_due, max_percent, places: int) -> Decimal:
    """The most a sale may take from the wallet: the lower of the balance, the amount due and ``max %`` of the amount
    due, rounded DOWN to the currency's precision (a cap is never exceeded by rounding). ``max %`` of 0 means no cap.
    Nothing below zero."""
    step = Decimal(1).scaleb(-places)
    due = D(amount_due)
    cap = due if D(max_percent) <= 0 else (due * D(max_percent) / 100).quantize(step, rounding="ROUND_DOWN")
    return max(min(D(balance), cap, due), Decimal(0)).quantize(step, rounding="ROUND_DOWN")
