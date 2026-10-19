# 15. Customer archetypes — worked examples by customer size

This chapter walks through typical customers, from one shop to a fifty-store chain, plus three specialist trades. For each one it shows where every need lands: configuration, our apps, or your own. It is for a builder, or the salesperson beside them, sizing a project before quoting it.

Each example names the samples it uses.

## When to use it

Use it at the blueprint step, after [Common custom projects](../recipes/common_custom_projects.md) has placed the needs a retailer asks for most. Find the example closest to your customer. Then find each of the customer's own needs in the [needs catalogue](../needs/README.md) (a need with no card goes on the ladder by hand, chapter 3), and give it the card's verdict and door:

| Verdict | Meaning |
|---|---|
| **Ready** | build it today; nothing to caveat |
| **Ready, with limits** | build it today, and tell the customer each limit |
| **Not yet** | after an extension point we are still building (chapter 9), or product work on our side: ask us |
| **Not possible** | it breaks one of the four rules; do what the card says instead |

The **door** says how it is built: configure, an outside app, our connector, a manifest, or an extension point by its name (chapters 7 and 9). Each need below links its card.

A customer's size describes it; it never decides the path. A large project's blueprint adds three things: a scale proof, a release gate in the customer's own CI and, where needed, joint work with us on an extension point.

## 15.1 Small — one to three stores

**The shape.** One to three stores; phones and a counter till; an online shop.

**Steps.**
1. Configure: prices, promotions and coupons; receipts with the shop's logo and tax number (a print format set up by hand; the receipt pack sample installs one by manifest); reason codes for voids, returns and discounts; blind till counts for cashiers; sale details captured at the till; permissions by role.
2. Our apps: the iVendNext POS on phones and on the counter; our WooCommerce connector for the online shop.
3. Your apps: usually none. Perhaps one outside app — a price checker (sample S24), an accounting export.

**Limits.** Our WooCommerce connector does not reserve stock, and it takes percentage vouchers only. Card payments need a certified payment connector in the customer's country — ours, or one a builder has written and certified (chapter 11).

**Effort.** Days of configuration, not a build.

## 15.2 Mid — twenty terminals on our connectors

**The shape.** Six stores: 12 phones, 6 counter tills and 2 tablets, all running the iVendNext POS. Handheld does receiving and stock counts. WooCommerce runs the online shop. Acumatica is the ERP, with Sage X3 to follow.

| Need | Where it goes | Verdict · door |
|---|---|---|
| Prices, promotions, member tiers by customer group | configure | Ready, with limits · configure: combined discounts follow the promotion rules ([prices-promotions-coupons](../needs/prices/prices-promotions-coupons.md), [member-price-by-tier](../needs/prices/member-price-by-tier.md)) |
| Reason codes, blind counts, sale details, permissions | configure | all configure: reason codes Ready, with limits ([reason-codes](../needs/till/reason-codes.md)) · blind counts Ready ([blind-counts](../needs/till/blind-counts.md)) · sale details Ready, with limits ([line-detail-for-goods](../needs/till/line-detail-for-goods.md)) · permissions Ready, with limits ([permissions-by-role](../needs/setup/permissions-by-role.md)) |
| Receipts with logo and tax number | a print format, set up by hand (chapter 4) or installed by the receipt pack (a manifest) | Ready, with limits · configure by hand, manifest by the pack ([receipt-for-your-market](../needs/documents/receipt-for-your-market.md)) |
| Shelf and product labels | from the till: the label layout extension point · from Handheld: the back office's print list, printed by a desktop utility | Ready, with limits · label layout ([shelf-labels-from-till](../needs/documents/shelf-labels-from-till.md)) |
| Online orders in; stock and prices out | our WooCommerce connector | Ready, with limits · our connector ([online-shop-woocommerce](../needs/integrations/online-shop-woocommerce.md)) |
| Sales, stock moves and purchasing to the ERP | our Acumatica connector | Ready, with limits · our connector: limits below ([erp-acumatica](../needs/integrations/erp-acumatica.md)) |
| Receiving and counts | Handheld | Ready, with limits · configure: online only; a count has no in-app approval step ([receiving-and-counts-on-handheld](../needs/stock/receiving-and-counts-on-handheld.md)) |
| A warranty check at the till | a till key answered by your service (the warranty sample) | Ready, with limits · till key ([warranty-check-at-till](../needs/till/warranty-check-at-till.md)) |
| Loyalty | ours, or the customer's own — your call with the customer | ours: Ready, with limits · configure ([loyalty-ours](../needs/customers/loyalty-ours.md)); redeeming the customer's own at the till: Ready, with limits · wallet ([store-wallet-at-till](../needs/customers/store-wallet-at-till.md)) |

**Limits to plan for.**
- **ERP throughput.** Our Acumatica connector books about 2.75 complete sales a minute per connection — about 165 an hour. Size the customer's busiest hour against it before you promise.
- **One ERP per company.** Acumatica now and Sage X3 later cannot both be one company's ERP. Our Sage X3 connector is not built yet.
- **Scale.** No load test has been run yet, and the largest live customer runs 18 terminals. Run the customer's scale profile on a sandbox before go-live (the scale-profile kit).
- **Handheld** books online only in its first release, so receiving needs a connection.
- **Counter printers** are wired to counter tills. We have not yet tried that route on the customer's own hardware, so test it in the pilot store. A phone prints through the network printer or the device's own dialog.

## 15.3 Mid — with its own systems

**The shape.** Ten to thirty stores. The customer runs its own loyalty programme, CRM, online shop and ERP, and wants iVendNext as its store system.

| System | How it connects | Verdict · door |
|---|---|---|
| Its own ERP | your outside app on the API and the event feed, keeping its own map of record ids, its own place in the feed, and a nightly reconciliation (the enterprise sync sample) | Ready, with limits · outside app: the enterprise sync sample reads the shared feed, which the customer's administrator opens to your app; a feed scoped to your own app is an extension point (chapter 9), and the kit has not run against it yet (chapter 5) ([erp-in-step-both-ways](../needs/integrations/erp-in-step-both-ways.md)) |
| Its own online shop | your outside app: orders in, stock and prices out | Ready, with limits · outside app: an online order cannot be edited at the till ([own-online-shop](../needs/integrations/own-online-shop.md)) |
| Its own CRM | your outside app reading customers and sales | Ready, with limits · outside app ([own-crm](../needs/customers/own-crm.md)) |
| Its own loyalty — earning | the customer's service on each booked sale | Ready, with limits · outside app ([own-loyalty-earning](../needs/customers/own-loyalty-earning.md)) |
| Its own loyalty — redeeming at the till | the wallet extension point, answered by the customer's service ([recipe](../recipes/wallet.md)) | Ready, with limits · wallet ([store-wallet-at-till](../needs/customers/store-wallet-at-till.md)) |
| A member's status at the till | a till key answered by the customer's service | Ready, with limits · till key ([member-status-at-till](../needs/customers/member-status-at-till.md)) |

**The pattern: the customer's logic, the records in iVendNext.** The logic runs in the customer's service. Its records — the loyalty ledger, member plans — live in iVendNext as your manifest's record types, written through the API. Reports, audit and native screens stay in iVendNext. No code runs there.

Worked end to end in sample S22 ([recipe](../recipes/customer_owned_loyalty.md)), with a receipt checked before it books ([check by workflow](../recipes/check_by_workflow.md)).

## 15.4 Enterprise — fifty stores and more, distribution centres, its own order and warehouse systems

**The shape.** Fifty or more stores and distribution centres. The customer has its own order-management and warehouse systems. It has specialised processes: a barcode on every physical unit, approvals across stores, its own loyalty with a wallet, and quick-commerce marketplaces.

**Five patterns that carry it.**
1. **The customer's logic, the records in iVendNext** (15.3).
2. **Check by workflow.** Use this for a back-office check that must block, with no code in iVendNext. The document's workflow has a *Verified* step that only the customer's service can take, after its check passes. Submit is allowed only from *Verified*. The user waits a few seconds, and the service must be up for back-office submits. A manager-held *Override* step can sit beside it.
3. **Member tier as a customer group.** Each tier is a customer group with its own promotion. The service moves customers between groups. The till prices a tier offline too, from its own copy of the promotions, for a member on the till's offline customer list; the booked sale equals what it showed (chapter 4).
4. **Status from events, with reconciliation.** The event feed sets a status (a unit sold or available). A nightly pass checks it against the booked documents.
5. **Marketplace calls land at the customer's service**, never at iVendNext. The service creates the orders through the API.

**Steps.**
1. Blueprint every process on the ladder. Most land on configuration, a manifest and the customer's service.
2. Name the extension points the project needs (often the wallet, a scan source for unit barcodes, and the check before payment). Agree joint work on any that are not yet built.
3. Write the scale profile and run it on a sandbox.
4. Put the customer's release gate in its own CI from the first sprint.
5. Rehearse a full trading day, with offline replay, before cut-over. Move all stores together.

**Limits to plan for.** No load test has been run yet. Stock lookups grow with the number of warehouses, and promotions are evaluated for every store, so a 50-store chain must be measured on its own profile. One company is one country and one currency, so several countries mean several sites. There is no store server. The customer's distribution centres and warehouse system stay its own: you connect to them.

## 15.5 Vertical — pharmacy, optical, electronics

| Vertical | Today (Ready, or Ready with limits; the door in brackets) | Not yet: after an extension point | Not yet: product work on our side |
|---|---|---|---|
| **Pharmacy** | [batches and expiry dates](../needs/stock/batches-and-expiry.md) (configure); [reason codes](../needs/till/reason-codes.md) (configure); [prescriptions as your own records](../needs/documents/prescriptions-as-records.md) (manifest); [a prescription number required before payment](../needs/till/prescription-before-payment.md) (check before payment); [pharmacy 2D codes at scan, with an expired pack refused](../needs/stock/pharmacy-pack-code-at-scan.md) (scan source); [first-expiry-first-out at the till](../needs/stock/first-expiry-first-out.md) (configure; the cashier confirms the pick) | other shelf-life rules (no card yet: [ask for one](../feedback/point_request.md)) | [insurance co-payment](../needs/till/insurance-co-payment.md); [the controlled-drug register](../needs/documents/controlled-drug-register.md) — our pharmacy pack |
| **Optical** | [lab orders as your own records, with a workflow; your outside app to the lab](../needs/documents/lab-orders-as-records.md) (manifest, outside app); [a check before payment that needs a prescription](../needs/till/prescription-before-payment.md) (check before payment) | — | — |
| **Electronics** | [a serial number or IMEI per unit (exactly one per unit, never sold twice)](../needs/stock/imei-per-phone-sold.md) (configure); [a unit's own code recognised at scan and refused once sold](../needs/stock/unit-code-at-scan.md) (scan source); [a warranty key at the till](../needs/till/warranty-check-at-till.md) (till key); [extended warranties sold as items](../needs/prices/extended-warranty-as-item.md) (configure) | — | [buy-now-pay-later tenders](../needs/integrations/buy-now-pay-later.md) (our payment connectors) |

## What is refused, and why

Every example keeps the four rules (chapter 3):
- money enters the sale visibly, before payment;
- no overrides or patches;
- your code on your server;
- your screens through our doors.

Where a need seems to break one, it needs an extension point instead. Request it (chapter 9).

## When your service is down, and when the till is offline

Each example follows the rule of the rungs it uses. Configuration works offline, and so does a member-tier promotion for a member on the till's offline customer list: the till prices it from its own copy, and the booked sale equals what it showed (chapter 4). Outside apps catch up from the event feed. A till key is dimmed offline; when your service is down, a press tells the cashier it could not finish and nothing is added, and the sale goes on. A wallet is never offered offline; when its service is down, the till says it did not answer and the cashier takes another payment.

## The tests

- Every need in the customer's blueprint carries a verdict and a door: its card's, or one placed by hand on the ladder for a need with no card.
- The scale profile has been run on a sandbox (mid and above).
- The customer's release gate runs in its CI before the first upgrade (chapter 14).

## Technical notes

- **Scale bound.** No load test has been run yet; the largest live estate is 18 terminals.
- **Counter printers.** The route through a wired counter till has not yet been proven on the customer's own hardware.
- **Acumatica throughput.** About 2.75 complete sales a minute per connection — about 165 an hour.
- **The scoped feed (15.3, its own ERP).** The event feed extension point is in the extension-point library (commit `21c7512`), and its code (`api/feed.py`, `business_logic/feed.py`) is in the bench's pin `8dc36aab8`. Not proven: neither the kit's feed client nor the enterprise sync sample (S7) has been run against the event feed extension point (chapter 5, *Technical notes*; S7's README).
