# Third-party payer — the recipe

An insurer pays part of a pharmacy sale and the patient pays the rest; an optical plan does the same for glasses; a
company pays for what its staff buy. In each, the retailer sells to its own customer, takes only the customer's share at
the till, and **claims** the rest from the payer afterwards. This recipe keeps the payer's terms outside the retailer's iVendNext, in
a payer service that answers the POS app's **payer** extension point, and keeps everything the retailer must see (payers, plans,
members, claims, remittances) as records in the retailer's iVendNext. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**The door:** the payer extension point (`payer/1`), in the POS app from version 2.1.0.666 ([the payer page](../contracts/pages/payer.md)).
The page is the contract; this recipe is the order to build it in.

**Reference implementation:** [`samples/s43_third_party_payer/`](../samples/s43_third_party_payer/README.md) —
*Third-party payer* 0.2.0: the payer service on the door (both calls answered in the shipped contract: whole minor
units, the stored fields' own names, a subscription with no clearing mode), the records, the claims built from booked
payer sales, the claims file, the remittance match and *Bill to the customer*.

**When to use it.** Use it when a third party pays part of a sale and the retailer must claim it, or when one payer's
link (an insurer's claims platform) must be written for a market. For a payer that pays the whole sale on account,
use the till's own *On Account* tender instead: there is nothing to split.

## What the store sees

| Who | Where | What |
|---|---|---|
| cashier | the payment screen, on a sale to a named customer | **Payer**: the customer's covers (the only one is taken); the split, where the payer's share is one leg the cashier cannot type or change; the customer pays the rest with the shop's other tenders |
| customer | the receipt | *Billed to ⟨payer⟩* for the payer's share, *Paid by you* for theirs; the member number with at most four digits showing |
| cashier | Returns | the payer's share given back to the payer, the customer paid back their own share only |
| claims clerk | Desk | the claims, the claims file, the remittance matched; a rejected claim billed back to the customer |
| accounts | the books | the payer's share owed by the payer's own customer record from the moment of the sale |

## Steps

1. **Declare, in your manifest** (`samples/s43_third_party_payer/manifest.json`):
   - **the records the retailer fills:** `<PREFIX> Payer` (each linked to the payer's own Customer record: the door books
     what the payer owes against it), `<PREFIX> Plan` (the co-pay rules, a price list, a formulary), `<PREFIX>
     Formulary` (rows by item or item group: covered, extra-item pay a unit, most units on a sale), `<PREFIX> Member`
     (a customer's policy, member number and card serial);
   - **the records your service writes:** `<PREFIX> Claim`, named by its claim reference (`autoname:
     field:claim_ref`), so a sale is never claimed twice; `<PREFIX> Claim Batch` (the claims file);
     `<PREFIX> Remittance`, entered by the clerk and matched by your service;
   - **permission rows that keep health data off the till:** members and claims are read by your clerk's role and
     your integration role only;
   - **a tick on Customer**, *Barred from sales a third party pays*;
   - **Desk buttons** (`desk_actions` with `extension_subscriptions` of point `desk_action`): build claims, make
     the claims file, match a remittance, bill a rejected claim back;
   - **the feed registration** (`registered_applications`) on POS Invoice and Sales Invoice.
2. **Declare the payer service** in `extension_subscriptions`, installed switched off:

   ```json
   {"key": "payer", "point": "payer", "label": "Insurer co-pay", "endpoint_url": "https://your.server/payer",
    "timeout_seconds": 5,
    "down_answer": "no_cover",
    "settings": {"prescription": {"reference": "ACME RXC Rx Number", "prescriber": "ACME RXC Prescriber",
                                  "prescriber_licence": "ACME RXC Prescriber Licence"},
                 "bill_back_role": "ACME ICP Integration"}}
   ```

   - list the address in `allowed_urls`; `timeout_seconds` is at most 5 (3 when left out); the only down answer is
     `no_cover`.
   - `prescription` names up to three of the sale's own details, sent with `coverage`; each must exist on the site
     (a pharmacy counter app's sale details, for example), so leave it out where none is installed. Changing it
     changes the consent text, and the calls stop until the administrator ticks consent again.
   - `bill_back_role` is the role that may bill a claim back (empty: the shop's accounts role).
   - ⛔ **No `clearing_mode`.** It is the shop's own, picked at switch-on; the kit's checker refuses it in a manifest
     (*"the clearing mode is the shop's to pick"*).
3. **The shop's set-up before switch-on** (tell the retailer's administrator, payer page §2): an enabled **Custom**
   mode of payment with no tender discount, minimum, maximum, over-tender, counting at the close or rounding, whose
   account in each company is its own open balance-sheet account in the company's currency (not a receivable,
   payable, bank, cash, stock or temporary one); that mode on each of the service's POS Profiles' payment methods with **Allow in Returns**
   ticked, and never as the default. Name it for what it is, such as *Billed to payer*: the posted invoice lists
   it among its payments. Then the subscription's clearing mode, consent, and the switch. One payer service per
   POS Profile.
4. **Answer `covers`** (a signed POST, `{"point": "payer/1", "context": …}`, payer page §3.1): every cover the
   customer holds today, each with your `member` reference, the payer's `payer_customer` (its Customer record on
   the shop's site: it must exist, be in use and never be the sale's own customer), a `member_label` showing at
   most four digits, and the plan's `price_list` and `promotions_apply`. While the payer is on the sale, every line
   the plan's list carries is priced on that list. To refuse the customer today, answer no covers and a `refused`
   sentence the cashier sees.
5. **Answer `coverage`** (payer page §3.2): money in **whole minor units**, never a decimal. Answer every `line_id`
   asked exactly once, each with its two shares adding up to its `amount_minor`, and totals adding up to
   `total_minor`; your share never more than the sale's rounded total. Keep `claim_ref` the same on every ask for
   one `sale_ref`. Answer one of three: `cover`; `refuse`, a line not sellable on this cover, with its reason and
   message; or `no_cover`. **Split the sale, never re-price it** (`copay.py`): spread your share over the covered
   lines to the minor unit, and refuse a line your plan's list does not carry, or carries at zero (`not_on_list`,
   `zero_on_list`), by **reading your list itself**, never from `rate_minor`: the till keeps the price it would otherwise give a
   line the list does not carry (the customer's own default list, else the store's). An answer that breaks any of these rules is refused whole, and reads as a service
   that is down.
6. **Make claims from the feed** (`claims.py`): the door books your share as a payment row on the shop's clearing
   mode and, in the same transaction, a journal moving it to `payer_customer`; the sale stores your answer and each
   line's shares (payer page §4b). On each booked sale the feed names, read the POS Invoice (never the posted Sales
   Invoice, which may merge several sales) with your integration user and make its claim. A submitted sale with an
   empty `custom_mpos_payer_journal` is no claim: its invoice was cancelled after it was booked.
7. **A return gives your share back, never the customer** (payer page §4c): the till's Returns works out each
   returned line's share and books a `Return` journal. Read the return from the feed and reduce the claim's lines by
   `custom_mpos_payer_back`, once.
8. **Bill a rejected claim back to the customer** through `/api/method/ivendnext_mpos.api.v1.payer_bill_back`
   (`sale`, `claim_ref`, `amount` in the company's currency, `reason`), as a user holding `bill_back_role` or the
   shop's accounts role. It answers `{"journal": …}`; the same sale, claim, reason and amount answer the same journal,
   and a till sale is billed back only once it is posted (at the day's close, where the shop posts then). The customer then owes it, and the till's *Take a
   payment* lists that invoice for them.
9. **File and follow:** the claims file (one row per claim line; never a cell a spreadsheet runs as a formula), the
   remittance matched line by line (paid, short paid, rejected, unmatched), and a claim's moves refused in words
   when its flow does not allow them.
10. **Write a payer's own link** (a partner's work, per market): read the same claims, and send them in the payer's
   format (NPHIES' FHIR, eClaimLink, Shafafiya, NHIA's form). The payer's data set says what a claim needs (GTIN,
   dose and frequency, member number, card serial).

## Limits

- **One payer per sale**; no deductible or annual limit carried across sales; no price negotiated per member; no
  pre-authorisation round trip.
- **Never offline**: a payer is not offered offline, a sale with a payer is never queued, and its return is online only.
- **A sale whose total carries a charge no line carries** (a charge on the whole sale, such as a service mode's
  charge) is never asked about: the cashier is told to take the charge off. An item's own surcharge counts on its line.
- **A slow or failed answer is no cover:** the customer can pay it all, or hold the sale. Your share is never booked on
  a guess.
- **The customer's basket and display** show the price without the payer until the cashier picks it; the split and the
  receipt show the plan's prices.
- **The customer earns loyalty points on the whole sale,** your share included.
- **A Desk Sales Invoice** can take a payer too (*Ask the payer*, payer page §4d), priced by the invoice's own list.
- **Health data**: run the service in the retailer's own country where its law requires it.
