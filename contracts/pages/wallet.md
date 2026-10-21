<!-- Source: ivendnext/iVendNext_PWA docs/extending/wallet.md @ 4c3f11b550f1, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Wallet extension point

> **Needs the Payments remote-wallet app.** Until the payments core ships it, no site holds a *Wallet* tender
> and nothing on this page runs: a *Wallet* Mode of Payment made by hand is drawn as a dead tile
> (*"Wallet isn't installed on this site."*) and is never booked as a plain row.

**Contract:** [`wallet.v1.schema.json`](../extension_contracts/wallet.v1.schema.json)
· samples: [`samples/wallet/`](../extension_contracts/samples/wallet/)
(the spec's wire scenarios S1–S5 and S7, accepted and refused; S6 and S8 are till behaviour, pinned in the tests) · code: the till's half in `business_logic/wallet_tender.py`
(`preview`, `wallet_push_amount`, `booking_rows`, `refund_to_wallet`) and `business_logic/card_terminal.py`
(`begin_wallet_push`); the core's half is the Payments board's (`remotewallet`).

## 1. What it is

A customer's own wallet or loyalty balance, run by the shop or a partner on their own server, is spent at
the till like any tender. The cashier taps the wallet's tile with a customer on the sale, sees the balance
and the most this sale may use, enters an amount (and the customer's one-time code when the wallet asks for
one), and the sale is paid. Nothing of yours runs in the shop: your service answers our published wire
format, `wallet/1`, which is the wallet profile of the payment connector contract (`paygw/1`).

## 2. What the shop's server sends, and what you answer

Money is in the currency's own minor units, with `currency_exponent` on every call.

| Call | We send | You answer |
|---|---|---|
| `preview` | `{v, customer, customer_name, amount_due_minor, currency, currency_exponent, store, sale_ref, lang}` | `{eligible, balance_minor, max_redeemable_minor, label, currency, otp_required, reason}` within 3 s |
| `authorise` | `{v, reference, customer, amount_minor, currency, currency_exponent, payer_code, sale_ref}` | `{reference, outcome, amount_minor, auth_ref, correlation_id, reason}` |
| `status` | `{v, reference}` | the same shape as `authorise` |
| `reverse` | `{v, reference, auth_ref, amount_minor, currency, currency_exponent}` | `{reference, outcome, reason}` |
| `refund` | `{v, reference, original_reference, auth_ref, amount_minor, currency, currency_exponent, return_ref}` | `{reference, outcome, amount_minor, reason}` |

- `amount_due_minor` is the server's own figure — the sale's total less its redeems and every wallet leg
  already on it — never a number the till sent.
- Every money answer echoes the `reference` it answers for; another reference is refused whole and read as
  *unknown*. `authorise` twice with one reference is one debit.
- `outcome` is one of `approved · declined · pending · unknown`. `approved` carries the amount actually taken
  and an `auth_ref`; a different amount is reversed automatically. `declined` and `unknown` carry a standard
  reason, plus `invalid_code` for a wrong one-time code.
- Capture before you answer `approved`: an approved wallet leg is money already taken.
- `payer_code` is never stored or logged on our side; do the same on yours.

## 3. What the till checks before it ever calls you

The server refuses, with no call to your service, a sale with no named customer, a push with no preview on
record for this sale, an amount above the cap your preview answered (cumulative per wallet), two wallets
together above the amount due, a total below the tender's minimum, and any sale its partner check, party,
seller or stock rules would refuse at booking.

## 4. Returns and the offline queue

- A wallet-paid sale refunds only to the same wallet, through `refund`, and the return books only after you
  confirm it. A refund you do not confirm stays *unknown* and is recovered by reference, never booked. The
  wallet's share goes back to the wallet first: a return at the till never pays it out another way. A
  wallet-paid sale is refunded from Returns only — it is not parked for another till, and it is not
  exchanged (return it, then sell the new item).
- **Setting a store up (tell the store, or do it for them):** tick *Allow in Returns* on the wallet's
  payment row of every till's POS Profile. Until it is ticked, a wallet-paid sale cannot be returned at
  all: its wallet share must go back to the wallet first, and the till offers the wallet row as *"This
  store doesn't pay refunds back this way."*, so every way of paying it back is refused. This line sits
  here because this page is the only wallet set-up page; whoever installs the wallet sets up its stores.
- The wallet is never offered offline. A sale queued after its wallet was approved posts with it; an
  unconfirmed leg, or one the wallet gave back while the sale was queued, goes to the queue's review, and a
  leg no sale ever books is reversed by the core.

## 5. Frames

The wallet tile, its amount sheet and the code field are one component on every frame of `/pos` — phone,
counter (`/pos?frame=terminal`) and tablet (`/pos?frame=tablet`). A wallet that cannot be used is dimmed with
its reason (*"Wallet isn't installed on this site."*, *"Add the customer first."*), never hidden; a wallet
that does not answer its preview says so in the opened sheet.
