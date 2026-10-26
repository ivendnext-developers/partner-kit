<!-- Source: ivendnext/iVendNext_PWA docs/extending/payer.md @ b453a68eac6c, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Payer — your service pays part of a sale for someone else

**Contract:** [`payer.v1.schema.json`](../extension_contracts/payer.v1.schema.json)
· samples: [`samples/payer/`](../extension_contracts/samples/payer/)
· code: `business_logic/partner_payer.py` (`validate_subscription`, `covers_context`, `coverage_context`,
`line_amounts`, `fingerprint`, `validate_covers`, `validate_coverage`, `ask_covers`, `ask_coverage`).

> ⚠ **This version ships the extension point, its contract, the till's Payer tile, the booking (§4b), returns and
> billing a claim back (§4c), the payer on a Sales Invoice made in iVendNext Desk (§4d) and the plan's price list
> and promotions (§3.1, §4).**

## 1. What it is

Some sales are paid in part by someone other than the customer: an insurer for a pharmacy, an optical plan, a
company paying for its staff. With extension point **`payer`** your service is that someone:

- **The cashier picks the customer's cover.** On a sale to a named customer the cashier presses **Payer**; we ask
  your service which covers the customer holds (`covers`) and the cashier picks one (the only one is taken).
- **You say what you pay, line by line.** We send the basket; you answer each line's two shares: yours and the
  customer's (`coverage`). The customer pays their share with the till's other tenders.
- **Your share is owed by you, never taken.** The sale stays one invoice, to the customer, for the whole sale; your
  share is moved onto your own customer record on the shop's books, so the shop collects it from you. The
  receipt prints *Billed to ⟨you⟩* and *Paid by you*, never *paid* for your share.
- **One payer service per POS Profile**, and it takes **none** of the profile's three check slots.

Nothing here names insurance, a market or a trade: the words are *payer*, *cover* and *claim*.

## 2. The subscription

A shop's administrator adds a **Retail Extension Subscription** with point `payer` (or your manifest installs one
in `extension_subscriptions`, switched off). Its fields: your HTTPS address, the shared secret, the time to answer
(at most 5 seconds; 3 when left empty), the POS Profiles it answers (empty = all), and its settings:

| Setting | What it is |
|---|---|
| `prescription` | up to three of the sale's own details sent as the prescription: `reference`, `prescriber`, `prescriber_licence`, each the name of a sale detail (empty: none sent) |
| `bill_back_role` | the role that may bill a rejected claim back to the customer (empty: Accounts User) |
| `clearing_mode` | **the shop's own**, required before the service is switched on: an enabled mode of payment of type Custom, with no tender discount, minimum, maximum, over-tender, counting at the close or rounding, whose account in every company the service answers is its own (no other mode's), open, in the company's currency, on the balance sheet and not a receivable, payable, bank, cash, stock or temporary account. It carries your share for an instant, until it is moved to you, and it is never a tender a cashier presses. ⭐ It must also be on each of the service's POS Profiles' payment methods with **Allow in Returns** ticked: a return gives your share back on it (the product refunds only to a mode its POS Profile allows in returns). The till never shows it as a tender or as a way to pay a refund back. A manifest never carries it |

A subscription is refused, in these words:

- *"No extension point named payer is installed on this site."* (an older version of the product)
- *"Name the clearing mode before you switch the payer service on: the mode of payment that carries the payer's share until it is moved to the payer."*
- *"No mode of payment named ⟨mode⟩."* · *"clearing_mode is the name of one mode of payment."* · *"The clearing mode must be an enabled mode of payment of type Custom."* · *"⟨mode⟩ must take the payer's share exactly: switch off its tender discount, minimum, maximum, over-tender, counting at the close and rounding."* · *"⟨mode⟩ has no account for ⟨company⟩."* · *"⟨mode⟩'s account for ⟨company⟩ must be an open balance sheet account in the company's currency that is not a receivable, payable, bank, cash, stock or temporary account."* · *"⟨mode⟩'s account for ⟨company⟩ is another mode of payment's too: give it its own."* · *"Add ⟨mode⟩ to ⟨POS Profile⟩'s payment methods with Allow in Returns ticked, so a payer's sale can be returned there. The till never shows it as a tender."* (for a service that answers every POS Profile, this is asked till by till, when a sale is booked) · *"⟨mode⟩ can't be ⟨POS Profile⟩'s default payment method: it carries a payer's share."* (the POS Profile's own save says the same: *"⟨mode⟩ carries a payer's share on this till: keep it here with Allow in Returns ticked, and not as the default."*)
- *"⟨label⟩ already answers payer sales for ⟨POS Profile⟩. One payer service per POS Profile."*
- *"The extension point's settings must be a JSON object."* · *"The settings of a payer service may only carry: bill_back_role, clearing_mode, prescription."* · *"prescription names up to three sale details: reference, prescriber, prescriber_licence."* · *"No sale detail named ⟨name⟩."* · *"No role named ⟨name⟩."* · *"The bill-back role must be a role the shop gives to some users, not ⟨role⟩."* (All, Desk User, Administrator and Guest are given by the system itself)
- *"The time to answer must be more than 0 and at most 5 seconds."* · *"When the service is down, this extension point can only: no_cover."*
- A service sales were booked on is never deleted: *"Sales were booked on ⟨label⟩. Switch it off instead: its sales are still returned on its clearing mode."* Uninstalling your app switches its payer service off and keeps it for the same reason.

At the till, a payer is not offered where its share could not be given back whole: *"Payers can't be used at this
till: it sells in ⟨currency⟩, not the company's ⟨currency⟩."*, and a tender with a live payment discount is refused
beside your leg (*"⟨mode⟩ can't be taken beside a payer. Take the customer's share another way."*), because the
discount is spread over every line, your share's too.

A manifest's payer service is refused by the kit's checker for the same settings, and for a clearing mode
(*"the clearing mode is the shop's to pick"*).

## 3. The calls

Each call is a signed POST, as for every extension point: the body is `{"point": "payer/1", "context": {…}}`,
canonical JSON, with the `X-iVendNext-Point: payer/1` header and the signature of the shared secret. Money is a
whole number of **minor units** of the sale's currency (`currency_exponent` digits: 2 for ZAR, 3 for KWD), never
a decimal.

### 3.1 `covers` — when the cashier presses Payer

We send the customer's record name, the date, the store, the POS Profile and the cashier. You answer every cover
the customer holds today:

```json
{"covers": [{"member": "GLI-778812", "payer": "GLI", "payer_title": "Generic Insurer",
             "payer_customer": "Generic Insurer", "plan": "GOLD", "plan_title": "Gold plan",
             "member_label": "…0123", "valid_to": "2026-12-31",
             "price_list": "Generic Insurer Prices", "promotions_apply": false}],
 "refused": null}
```

- `member` is your own reference for the cover; we send it back on `coverage`.
- `payer_customer` is **your Customer record on the shop's site**: the party your share is owed by. It must exist,
  be in use (not disabled), and it is never the sale's own customer.
- `member_label` is printed on the receipt: at most four digits of the member number show, a digit in any script
  counting (Arabic-Indic digits too).
- `price_list` (or `null`) and `promotions_apply` (default `true`) are the plan's. While the customer's payer is on
  the sale, **every line the list carries is priced on the plan's list**, the customer's own default list
  notwithstanding. In `coverage`, `price_list` names the list the sale is priced on and `rate_minor` is the line's
  price after whatever cut applies to it (a promotion, an old-style pricing rule, a coupon or a staff discount the
  cashier applied): do not judge whether a line is on your list from `rate_minor`, read your own list. A plan with
  `null` prices on the store's list. The list must be an enabled selling list in the till's currency: otherwise the
  cover reads as *no cover*, `coverage` is never asked, and the cashier is told the till can't sell on that list (sell
  without the payer, or a manager checks the list). With `promotions_apply: false` the shop's promotions do not apply
  to the sale; a coupon or a staff discount the cashier chose still does, and an old-style pricing rule still can (§7). **A line the list does not carry** keeps the price the
  till would otherwise give it (the customer's own default list, else the store's), so the refusal is yours: answer
  `refuse` with `not_on_list` or `zero_on_list`.
- A cover whose `valid_to` has passed is not offered. To refuse the customer today, answer
  `{"covers": [], "refused": {"code": "barred", "message": "⟨your sentence⟩"}}`: the cashier sees your sentence.

### 3.2 `coverage` — before the tender, and whenever the sale moves

We send the cover's `member`, the sale's key (`sale_ref`: the same across a hold and its recall, so name your
claim from it), the currency, the sale's price list, `tax_included` (true where the prices include tax), the
prescription details the subscription names (`null` for none), and every line (at most 200; a larger sale is
never asked about):

| Field | What it is |
|---|---|
| `line_id` | `L1`, `L2`, … in the sale's order: answer each exactly once |
| `item_code`, `item_group`, `gtin` | the item; `gtin` is the line's scanned barcode, else the item's first, else `null` |
| `qty`, `uom`, `conversion_factor` | the quantity in the line's unit |
| `rate_minor`, `discount_minor` | its price, and the discount on it, both on the price's basis (tax included where `tax_included`) |
| `amount_minor` | **what the line costs**: after every discount (the sale's own spread across the lines), plus its share of tax |

The lines' `amount_minor` add up to `total_minor` exactly; `rounding_minor` is the sale's rounding, always the
customer's. You answer one of three:

- **`cover`** — every line sellable on the cover, with its two shares (and `payer`, `plan`, `member` those of the
  cover picked):

  ```json
  {"answer": "cover", "payer": "GLI", "plan": "GOLD", "member": "GLI-778812",
   "claim_ref": "GLI-CLM-sale-7f3a", "no_partial_refund": false,
   "lines": [{"line_id": "L1", "covered": true, "sellable": true, "payer_share_minor": 19040,
              "patient_share_minor": 4960, "covered_qty": 2, "qty_limit": 3},
             {"line_id": "L2", "covered": false, "sellable": true, "reason": "not_covered",
              "message": "Vitamins are not covered by this plan.",
              "payer_share_minor": 0, "patient_share_minor": 4550}],
   "totals": {"payer_share_minor": 19040, "patient_share_minor": 9510, "total_minor": 28550}}
  ```

- **`refuse`** — a line is not sellable on this cover (`reason` `not_on_list`, `zero_on_list`, …), each such line
  with `sellable: false` and its `message`. The cashier removes it, or sells the whole sale without the payer.
- **`no_cover`** — the customer cannot buy on this cover today, with your `message`.

⛔ **We check a cover answer before anything could book it**, and refuse it whole when: a line asked is not
answered, is answered twice, or a line we did not ask is answered · a share is not a whole number of minor units
at or above 0 (`80.0`, `"80"`, `true` are not) · a line's two shares do not add up to its `amount_minor` · an
uncovered line has a payer share · `covered_qty` is more than the line's quantity · the totals are not the sums,
or do not add up to `total_minor` · your share is more than the sale's rounded total (`total_minor` +
`rounding_minor`: the customer never gets money back for your share) · the answer is for another member or payer
· it pays nothing · a number is `NaN` or `Infinity` · a key the answer does not take. A refused answer reads
exactly as a service that is down.

`claim_ref` is the same on every ask for one sale. `no_partial_refund: true` means a return of this sale must take
back every line it still holds, in full.

## 4. When we ask again

We keep your answer with a fingerprint of what it was asked about: the customer, the member, the date, the
currency, the prescription details, the price list the sale is priced on, whether the plan's promotions apply, and
each line's item, quantity, unit, amount and discount. The sale is asked again whenever the
fingerprint moves (a line, a quantity, a price, a list, a discount, the prescription, the customer); changing the
customer drops the payer. At Pay, an answer older than 10 minutes is asked again. Your share is never booked on
an answer that no longer matches the sale. Keep `claim_ref` the same on every ask for one `sale_ref`: an answer
whose claim reference moved between two asks for the same sale reads as no cover.

## 4b. What a sale on a payer stores, and how your share is booked

- **On the till** the cashier presses **Payer** on the payment screen; it opens the split, where your share is one
  leg the cashier cannot type, change or remove except by *Remove the payer*. The customer pays the rest with
  the shop's other tenders, less any the shop's POS Profile refuses beside a payer (its *Tenders Refused Beside a
  Payer* setting).
- **The booking:** your share is a payment row on the shop's clearing mode, and in the same transaction a journal
  moves it to your customer record: *debit receivable, party = your `payer_customer`; credit the clearing
  account*. The customer's invoice reads paid; you owe the shop your share from the moment of the sale. Pay it
  with an ordinary payment against that journal. A journal that cannot be made fails the sale: nothing is left
  booked.
- **What the sale stores** — on the POS Invoice, the claim's source (⛔ never the Sales Invoice its posting or the
  day's close makes, which may merge several sales): `custom_mpos_payer_customer`, `_payer_title`,
  `_payer_code`, `_payer_plan`, `_payer_member`, `_payer_member_label`, `_payer_claim_ref`,
  `_payer_prescription`, `_payer_prescriber`, `_payer_prescriber_licence`, `_payer_share`, `custom_mpos_patient_share`,
  `_payer_no_partial_refund`, `_payer_answer` (your answer as booked, JSON), `_payer_journal`,
  `_payer_subscription`, `_payer_clearing_account`, `_payer_bill_back_role`; and on each line
  `custom_mpos_payer_share`, `custom_mpos_patient_share`, `custom_mpos_payer_covered_qty`, `custom_mpos_payer_gtin`.
  The journal names its sale in `custom_mpos_payer_pos_invoice`. Read them with your integration user when the
  event feed says a sale was booked.
- **A cancel in iVendNext Desk:** a sale the day has not posted yet takes its journal with it. Once a sale is
  posted, its journal goes when its posted Sales Invoice is cancelled (or the day's closing is, on a shop that
  posts each sale at once); the sale's own cancel alone leaves the journal, because its invoice still stands.
  Once a payment or another journal references your journal, the cancel is refused: *"⟨payer⟩'s share of this sale
  has moved since: return it instead."*
- **A submitted sale with an empty `_payer_journal`** is a sale whose posted invoice was cancelled after it was
  booked: its journal was cancelled with that invoice, and the sale keeps naming you (`_payer_customer` and the
  rest stay set). ⛔ It is no claim: you owe the shop nothing for it, it is not billed back, and the till does not
  return it (the books no longer hold the sale; a manager settles it in iVendNext Desk). The cancelled journal still names the sale.
- **Your customer record must be billable** when the cashier asks and when the sale is booked: in use, not
  frozen, inside any credit limit the shop gives it, and with its receivable account in the company's
  currency. Otherwise the cashier is told so and the payer is not used for that sale.
- Only the till's payer leg sets these fields or books on the clearing mode; any other writer is refused, and a
  Sales Invoice made in iVendNext Desk never carries a clearing row (the posted invoice of a till sale does; a
  Desk sale has its own payer section, §4d). `_payer_subscription` and `_payer_bill_back_role` hold names, not
  links: a sale outlives an uninstalled service, and so do its returns and bill-backs.
- Every journal says what it does in `custom_mpos_payer_entry`: `Sale` (your share booked), `Bill back` (a claim
  billed back to the customer, its reason in `custom_mpos_payer_reason`) or `Return` (your share given back).

## 4c. A return, and a claim billed back

- **A return gives your share back, never the customer.** The till's Returns works out, for each returned line,
  that line's own share in proportion to the quantity returned, rounded half up, the last unit of a line taking
  whatever is left, so returns one after another add up to the sale exactly. It reads what the sale stored and
  never asks your service. The customer is paid back their own share only. Where `no_partial_refund` is true, a
  return takes back every line of the sale, whole: *"A sale ⟨payer⟩ paid part of is returned whole: return every
  line of it."*
- **How it is booked:** the return carries one negative row on the clearing mode, and in the same transaction a
  journal (`Return`) gives your share back, in this order: what you still owe on the sale is credited against
  the sale's journal; what was billed back to the customer and not yet paid is credited against the customer's
  invoice (they no longer owe it); what was billed back and the customer has paid is refunded to the customer
  with their share; what you have already paid is a credit on your customer record, not against any journal,
  for the shop to refund or net.
- **What a return stores:** your fields as the sale had them (the claim reference included), and
  `custom_mpos_payer_back` (your share given back, a positive amount) on the return and on each returned line,
  with `custom_mpos_payer_back_billed` (of it, the part that had been billed back to the customer). Read the
  return when the event feed says a return was booked. The till shows the same split: *Given back to ⟨payer⟩*
  (what you owed plus what you had paid) and *Taken off what the customer owes* (a billed-back share not yet
  paid), beside what the customer is paid back.
- **Only the till's Returns refund.** A return parked for another till, an exchange of a payer's sale, a credit
  note made in iVendNext Desk against a till sale's invoice, and any other writer are refused: *"A payer paid part
  of this sale, and its share goes back only through a refund. Refund it from Returns, then sell the new items."*
  · *"A sale a payer paid part of is returned from the till's Returns, which gives the payer's share back."* A
  return whose charge leaves the customer owing more than their share is refused (*"A charge on this return is
  more than the customer's share of it. Take the charge off to give ⟨payer⟩'s share back."*). Never offline.
- **Billing a claim back:** `/api/method/ivendnext_mpos.api.v1.payer_bill_back` with `sale` (the POS Invoice, or
  a Desk Sales Invoice), `claim_ref`, `amount` (in the company's currency, e.g. `100` or `12.50`) and `reason`
  answers `{"journal": "<name>"}` — a `Bill back` journal, dated the day it is booked: *debit the customer against
  the sale's invoice; credit you against the sale's journal*. The customer then owes it, and the till's account
  payment (*Take a payment*) lists that invoice for them (a till sale's; a Desk sale's bill-back is collected on
  the Desk, against its Sales Invoice). The same sale, claim, reason and amount answer the
  journal booked the first time; the same reason with another amount is refused (*"⟨amount⟩ was already billed
  back for this reason. Give the new amount its own reason."*); a new reason books another. It needs a user who may submit a
  journal (the shop's accounts role), or the role your subscription names in `bill_back_role` (stored on the sale
  when it was booked). Refused: *"No sale paid by a payer is named ⟨sale⟩."* · *"That claim is not this sale's."*
  · *"Say why the claim is billed back."* · *"Bill back an amount above zero."* · *"⟨payer⟩ owes ⟨amount⟩ on this
  sale. Bill back no more than that."* · *"⟨payer⟩ owes nothing on this sale."* · *"This sale is posted at the
  day's close. Bill it back after the close."* · no right: a permission error. An answer without `journal` books
  nothing.

## 4d. A payer on a Sales Invoice made in iVendNext Desk

- **On a saved draft Sales Invoice** (not a POS invoice, not a return), the **Payer** menu has **Ask the payer**
  (on a site with a payer service switched on; reload iVendNext Desk after switching one on) and, once asked, **Remove the payer** (always, so a draft is never
  stranded by a service switched off since). *Ask the payer* is
  `/api/method/ivendnext_mpos.api.v1.payer_coverage` with `doctype` and `name`: without `cover` it answers the
  customer's covers, each with a `ticket`; with a cover's `ticket` it asks `coverage` (your `sale_ref` is the
  invoice's name) and seals your answer into the invoice, filling the same fields as a till sale. An unsaved form
  is refused (*"Save the invoice first, then ask the payer."*), as is a POS Invoice (*"A till sale's payer is
  asked at the till."*). The payer service is the invoice's POS Profile's, or the one service that answers the
  company's tills.
- **The submit books only the sealed answer:** for this invoice and customer, from the service that answers it
  now, about exactly these lines, and no older than ten minutes — else *"The invoice changed since the payer
  answered. Ask the payer again."* The invoice must be in the company's currency, and no payment or advance on it
  may pay your share too. The journal (`Sale`) is shape B as written: *debit you; credit the customer, against the
  invoice*. The customer then owes their own share on the invoice.
- **Its credit note** (made from the invoice in iVendNext Desk) gives your share back exactly as a till return
  does (§4c), its journal crediting the credit note's own credit; the customer's share stays the credit note's
  credit, as on any credit note. It must be made from the invoice, so each line names the invoice's line
  (*"Make this credit note from the sale (Create, then Return), so each line names the sale's line and ⟨payer⟩'s
  share of it goes back to ⟨payer⟩."*), and be worth at least your share of it (*"This credit note is worth less
  than ⟨payer⟩'s share of it. Make it from the sale."*).
- **A payer journal is never cancelled by hand** (*"This journal is part of a sale's payer booking. Cancel or
  return the sale instead."*): it goes with its sale or return. A `Bill back` journal may be, until a return has
  counted it.
- The Desk section follows the Sales Invoice's own rights: whoever may write the invoice may ask.

## 5. Down, slow, refused, offline

- **No down answer to choose:** a service that does not answer in time, errs, fails its signature or answers
  wrongly means **no cover**: *"⟨label⟩ cannot be reached: the customer can pay it all, or hold the sale."* We
  never book your share on a guess.
- **Never offline.** A payer is not offered offline, a sale with a payer is never queued, and its return is online
  only. Inside an offline drain nobody is asked.
- **The log:** every call writes one row to the extension log (its request's hash, the outcome, the time it
  took); a refused answer is flagged. The row is queued so a refusal cannot roll it back, and is written within
  minutes, best-effort (a restart before then, or a service deleted before then, drops it). The log is cleared on its usual
  schedule; the answer the sale booked is kept on the sale, never read back from the log.

## 6. Consent

The administrator ticks consent to this text, which the product writes (a change to the prescription details
changes it, and the calls stop until consent is ticked again):

> When a cashier sells on a payer, iVendNext sends your service: the customer's record name, the cover's
> reference you gave, the store, the till's POS Profile, the cashier, the date, the sale's key, currency and price
> list, and for each line its item code, item group, GTIN, quantity, unit, conversion factor, price, discount and
> amount, and the sale's total and its rounding ⟨, and the prescription's reference, the prescriber, the
> prescriber's licence⟩. Health data stays in the
> shop's country where the law there requires it: your service must run there. No card data, serial or batch is
> sent.

## 7. Bounds, stated

- **One payer per sale** in this version: a second payer on the same sale is not supported.
- **Your `payer_customer` is trusted** as the party your share is owed by, once it exists, is in use and is not
  the sale's own customer: name the right record.
- On a sale made in iVendNext Desk, `pos_profile` is the invoice's POS Profile, or empty.
- A Sales Invoice made in iVendNext Desk prints its whole total: the payer fields are hidden on its print, so a
  shop that wants *Billed to ⟨payer⟩* on that paper adds it to its own print format.
- A return's parts are taken in the order of §4c over the whole return, not line by line: a return of one line
  of several may meet the billed-back part before another line's. The sum given back to you is exact.
- A return of a sale whose payer booking was cancelled in iVendNext Desk is not made at the till (the books no
  longer hold the sale): the shop sorts out its goods and money by hand.
- The posted Sales Invoice of a till sale lists the clearing row among its payments, under the name the shop gives
  its clearing mode (as the X and Z reads and the count sheet do): name it for what it is, e.g. *Billed to payer*.
- The customer earns loyalty points on the whole sale, your share included (the product earns on an invoice's
  total).
- **The plan's prices are on the lines, not on the header.** The product re-sets an invoice's price-list field to
  the customer's own default list whenever it saves, but never a line's price: the saved and the posted invoice,
  and a shift-close day's combined invoice, carry the plan's prices line by line. A report that groups by the
  invoice's price list sees the customer's list.
- `promotions_apply: false` switches off the shop's promotions, not a coupon or a staff discount the cashier chose
  (their choice) and not an old-style pricing rule: the product cannot keep that rule's off-switch through its own
  save. Such a rule (a shop created none since the product stopped allowing them) can still cut the plan's price,
  replace it where it sets the rate, or discount the whole bill; one tied to the plan's own price list never applies,
  because the sale's list stays the customer's.
- The cashier meets the plan's prices once the payer is picked: the split's header shows the sale's total on the plan's
  prices and the receipt prints them line by line. Until then the basket, the first payment screen and the
  customer's display show the price the till gives without a payer (the customer's own default list, else the
  store's), and so does the screen behind the split on a counter or tablet. A sale made on the Desk is priced by the
  invoice's own list (the Desk user's choice) and ignores `promotions_apply`; the plan's list and promotions apply to
  the till.
- The cover you answered in `covers` is read when the cashier picks it: a plan whose list your service changes later
  in the same sale is priced on the old list until the cashier presses Payer again (your `coverage` answer can still
  refuse).
- No deductible or limit carried across sales, no pre-authorisation round trip and no link to any real insurer:
  each is your service's to do, behind this contract.
- A sale whose total carries a charge no line carries (a charge on the whole sale, not on one line, such as a
  service mode's charge) cannot be split by line, so it is never asked about: the cashier is told to take the
  charge off. An item's own surcharge and its tax count on that item's line.
- With a partner's check before payment on the till, the check is asked again on the plan's prices once your
  answer lands, and on the sale's own prices if the cashier removes the payer. A check that refuses the sale on
  the plan's prices takes the payer off.

## 8. Telling an AI assistant

*"Build an HTTPS service for the iVendNext POS extension point `payer/1`. Read `docs/extending/payer.md` and
validate every request and answer against `payer.v1.schema.json`. Money is integer minor units. Answer `coverage`
with exactly one line per `line_id` asked, whose `payer_share_minor` + `patient_share_minor` equal that line's
`amount_minor`, and totals that add up to `total_minor`. Keep `claim_ref` stable per `sale_ref`. Answer within 5
seconds."*
