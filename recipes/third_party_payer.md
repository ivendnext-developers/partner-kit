# Third-party payer — the recipe

An insurer pays part of a pharmacy sale and the patient pays the rest; an optical plan does the same for glasses; a
company pays for what its staff buy. In each, the retailer sells to its own customer, takes only the customer's share at
the till, and **claims** the rest from the payer afterwards. This recipe keeps the payer's terms outside the retailer's iVendNext, in
a payer service that answers the POS app's **payer door**, and keeps everything the retailer must see (payers, plans,
members, claims, remittances) as records in the retailer's iVendNext. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** `samples/s43_third_party_payer/` — *Third-party payer*.

⚠ **The payer door is requested from the POS team and is not in the POS app yet.** Until it is, the reference
implementation keeps the records, builds claims from booked payer sales and matches remittances; the door's
subscription and the bill-back button wait in `door_declaration.json`.

**When to use it.** Use it when a third party pays part of a sale and the retailer must claim it, or when one payer's
link (an insurer's claims platform) must be written for a market. For a payer that pays the whole sale on account,
use the till's own *On Account* tender instead: there is nothing to split.

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
   - **three Desk buttons** (`desk_actions` with `extension_subscriptions` of point `desk_action`): build claims, make
     the claims file, match a remittance;
   - **the feed registration** (`registered_applications`) on POS Invoice and Sales Invoice.
2. **Answer the payer door** (`payer/1`, two signed calls): `covers` (the customer's current covers, the member number
   masked) and `coverage` (each line covered or not, sellable on the cover or not, the payer's and the customer's
   share, a quantity limit, and a claim reference that is the same on every ask for one sale). Each share pair must
   add up to the line's amount: the door refuses an answer that does not.
3. **Split the sale, never re-price it** (`copay.py`): the retailer's pricing prices the sale; your rules split its total.
   Spread the payer's share over the covered lines to the cent, and refuse a line the plan's price list does not
   carry, or carries at zero, by **reading the list itself**: the till re-prices a missing or zero row from the
   store's list, so the line's price proves nothing.
4. **Make claims from the feed** (`claims.py`): on each booked sale the door marked, read the sale and make its claim;
   on a return, reduce the claim's lines by what the door gave back to the payer, once. A claim missing what its
   payer needs is *Incomplete* until the clerk fills it.
5. **File and follow:** the claims file (one row per claim line; never a cell a spreadsheet runs as a formula), the
   remittance matched line by line (paid, short paid, rejected, unmatched), and a claim's moves refused in words
   when its flow does not allow them.
6. **Write a payer's own link** (a partner's work, per market): read the same claims, and send them in the payer's
   format (NPHIES' FHIR, eClaimLink, Shafafiya, NHIA's form). The payer's data set says what a claim needs (GTIN,
   dose and frequency, member number, card serial).

## Limits

- **One payer per sale**; no deductible or annual limit carried across sales; no price negotiated per member.
- **Online only**: the till sells offline with one tender, cash or card, so a sale on a payer waits for a connection.
- **Health data**: run the service in the retailer's own region.
