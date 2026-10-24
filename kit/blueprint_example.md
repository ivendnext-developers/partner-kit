# Blueprint example — Corvane Mobile

*Corvane Mobile is an invented company: no real retailer, its needs and figures made up to show a blueprint filled in.*

Print it beside the blank form: [this example as a PDF](https://developer.ivendnext.com/downloads/blueprint_example.pdf) · [the blank form (PDF)](https://developer.ivendnext.com/downloads/blueprint_form.pdf) · [the template](blueprint_template.md) to copy · [the project blueprint](blueprint.md), which says how to fill each section.

A chain of nine phone and electronics stores in one country, with a web store, on our Acumatica and WooCommerce connectors. Every handset is tracked by its IMEI. Each row of (b) names its card in the [needs catalogue](../needs/README.md), and the site's build checks each row's verdict and door against that card, so a card whose verdict or door changes fails the build until the row is updated. The limits and figures are as they stood on 2026-10-16.

| Field | Your answer |
|---|---|
| **Prepared by** (one of: iVendNext Partner · Licensed customer · CitiXsys Consulting Team) | iVendNext Partner, for Corvane Mobile's IT and store operations teams |
| **Date** | 2026-10-16 |
| **Version** | 2 |
| **Kit version** (the version of the kit you worked from) | the kit of 2026-10-21 |
| **Sandbox / staging site** (the site you tried it on) | the partner's own sandbox site |

## (a) The project in two lines

*What the customer wants, and what you will deliver. Two lines, no more.*

Corvane Mobile wants its nine stores and its web store on iVendNext, with every handset tracked by its IMEI from delivery to sale. We deliver the configuration, our Acumatica and WooCommerce connectors, two checks before payment, a warranty key, and two requests for the doors it lacks.

## (b) Fit-gap

*One row per need, in the customer's words: its card, the card's verdict and door, and every limit.*

| # | Need (customer's words) | Card | Status | Door | Limits and note |
|---|---|---|---|---|---|
| 1 | Every phone we sell is recorded by its IMEI, and the same IMEI can never be sold twice | imei-per-phone-sold | Ready, with limits | Configure | Offline: not run. The IMEI is the item's serial number, received with the stock. |
| 2 | Scan the IMEI label on the box, and the till refuses a handset already sold | unit-code-at-scan | Ready, with limits | Scan source | A unit sold on another till a moment before: not run in the kit (the product's own tests cover it). |
| 3 | Sell our two-year care plan alongside a phone | extended-warranty-as-item | Ready | Configure | The care plan is an item of its own; checked on the sandbox. |
| 4 | When a customer brings a phone back, the cashier sees whether it is still under the maker's warranty | warranty-check-at-till | Ready, with limits | Till key | Online only: the key is dimmed on an offline till; when the service is down the sale goes on; the key's request carries no serial numbers (risk 3). |
| 5 | A manager approves any sale over 1,500 before it is paid | manager-for-large-sale | Ready, with limits | Check before payment | Answered at Pay, not when the line is entered; the manager signs in on the till (no approval by e-mail). |
| 6 | No more than two of a new launch phone in one sale | line-quantity-cap | Ready, with limits | Check before payment | Answered at Pay, not when the quantity is typed; the card's check is per line (risk 5). |
| 7 | Prepaid airtime top-ups: the PIN is made when the sale is paid and printed on the receipt | voucher-at-payment | Ready, with limits | Fulfil at sale | The PIN is made after the sale is paid, one per line, and prints on the receipt; a top-up is sold online only, and its refund waits until the PIN is cancelled with the provider. |
| 8 | Customers can pay for a phone in instalments with a pay-later provider | buy-now-pay-later | Not yet | Request | Ask us: a buy-now-pay-later tender in our payment connectors. |
| 9 | Take the customer's old phone as a trade-in, valued at the till and taken off the new one | none | Not yet | Request | No card. Nearest request class: payment / tender (the trade-in as a tender, so the new phone's price never changes after the cashier has seen it, rule 1). An extension-point request to send. |
| 10 | Every sale, stock move and purchase goes to our Acumatica | erp-acumatica | Ready, with limits | Our connector | About 2.75 complete sales a minute per connection (165 an hour): the launch-day peak is above it (risk 1); one ERP per company. |
| 11 | Our WooCommerce web store shows the stores' stock and prices, and its orders come in | online-shop-woocommerce | Ready, with limits | Our connector | It does not reserve stock; it takes percentage vouchers only. |
| 12 | Store staff receive deliveries and count stock with a Handheld | receiving-and-counts-on-handheld | Ready, with limits | Configure | Handheld books online only; a count has no in-app approval step; Handheld offers no extension point. |

## (c) Scale profile

*Real figures, or a guess marked as one; then work out the peak and check it against the known limits.*

| Measure | Value | Basis (counted / estimated) |
|---|---|---|
| Stores | 9 | counted |
| Tills per store, by kind (counter · phone · tablet · Handheld) | 2 counters, 2 phones, 1 Handheld (18 counters, 18 phones and 9 Handhelds in all) | counted |
| Active products (and variants) | 4,200 items; the 1,100 phones among them come in 3,600 colour and storage variants | counted |
| Customers on file | 60,000 | counted |
| Sales per day per till — an average day | 45 on a counter, 12 on a phone | estimated from last year's till reports |
| Sales per day per till — the busiest day | 3 times the average, on a flagship phone's launch day | estimated from last year's launch |
| Lines per sale (average) | 1.6 | counted |
| Peak-hour share (share of a day's sales in the busiest hour) | 15% | estimated |
| Offline hours expected per till per week; the longest single outage | 1 hour; 5 hours (a cut line at a mall store last year) | estimated |
| Integration event volume per day; at the peak hour | about 3,000 a day (1,026 sales, 1,640 stock moves, 150 purchases and transfers, 140 web orders), 450 at the peak hour; on a launch day about 8,600, 1,300 at the peak hour | estimated, worked out from the figures above |

**The peak, worked out.** Sales per day = 9 stores × (2 counters × 45 + 2 phones × 12) = 9 × 114 = **1,026**. In the peak hour: 1,026 × 15% = **154**, or 2.6 a minute. On a launch day: 3,078 a day, **462** in the peak hour, or 7.7 a minute.

**Against the known limits.** The average peak (154 an hour) is just under one Acumatica connection's 165 an hour. The launch-day peak (462) is 2.8 times it. The estate has 45 devices, against a largest live estate of 18 terminals. The longest outage (5 hours) is inside the 24-hour sales snapshot. Handheld books online only, so receiving and counts stop during an outage.

## (d) Integration map

*One row per outside system and direction: its door, what moves, how much, and what happens when it is down.*

| System | Direction | Door | What moves | Volume (per day / peak hour) | Who owns the far side | Our connector or your app | Identity map kept by | If the far side is down |
|---|---|---|---|---|---|---|---|---|
| Acumatica | out | event feed | the stores' sales, stock moves, purchases and transfers | about 2,800 a day; 154 sales at the peak hour, 462 on a launch day (web orders: risk 1) | the customer's finance team and its Acumatica partner | our Acumatica connector | the connector | not covered by the kit: ask us how the connector catches up (risk 1) |
| WooCommerce web store | out and in | API | orders in; stock and prices out | about 140 orders a day; 420 on a launch day | the customer's e-commerce agency | our WooCommerce connector | the connector | orders wait on the retailer's side; stock is not reserved meanwhile |
| Airtime top-up provider | out and in | fulfil at sale | the paid top-up line out; the PIN in | about 200 a day (one sale in five carries a top-up) | the airtime provider | the partner's outside service | the outside service | the sale stands and the receipt waits; the cashier prints without the PIN and reprints it once the provider answers |
| Phone makers' warranty services | in | till key | the warranty of a phone brought back | about 30 a day (returns and repairs, about 3% of sales) | each phone maker | the partner's outside service | — | the key says it could not finish, nothing is added, and the sale goes on |

## (e) What this blueprint switches on

*Each module on or off, and the row or figure that decides it.*

| Module | On / off | Because (row or figure) |
|---|---|---|
| Joint extension-point lane | On | row 9 needs an extension-point request |
| Scale proof | On | the launch-day peak (462 sales an hour) is 2.8 times one Acumatica connection, and 45 devices is above the largest live estate of 18 terminals |
| Release gate in the customer's CI | On | rows 5 and 6 reach the sale through a check before payment, and row 4 through a till key |
| Dedicated bench (CitiXsys Consulting Team only) | Off | no need requires embedded Python, and an iVendNext Partner builds the project |

## (f) Risks and open questions

*What you do not know yet, what would settle it, and who can answer.*

| # | Risk or question | Touches | What would settle it | Who can answer |
|---|---|---|---|---|
| 1 | The launch-day peak (462 sales an hour) is 2.8 times one Acumatica connection; whether the 140 web orders a day count against the same connection, and what the connector does while Acumatica is down, are not in the kit | row 10, (c), (d) | the scale proof on the sandbox; how many connections the customer's release carries, and how the connector catches up | us; the builder |
| 2 | A top-up cannot be sold offline, and a store's sale waits on the provider's PIN for its receipt | row 7, (d) | the outage rehearsal on the sandbox (risk 4), and the provider's answer time measured against the till's 5 seconds | the builder; the airtime provider |
| 3 | The maker's warranty is held per IMEI, but the till key's request carries no serial numbers | row 4 | answer by model and the original sale's date at the till, or by IMEI once the return is booked; try both on the sandbox | the builder; the customer |
| 4 | A five-hour outage at a mall store: Handhelds cannot receive or count, and the warranty key is dimmed | rows 4 and 12, (c) | a rehearsal on the sandbox with the till offline, and a paper fallback for deliveries | the builder; the customer's store operations team |
| 5 | The two-per-sale limit is checked per line, so a cashier could put the launch phone on two lines | row 6 | a basket test on the sandbox: the service adds up the phone's lines before it answers | the builder |
| 6 | Trade-ins have no door: stores value them by hand until the extension-point request is answered | row 9 | the answer to the extension-point request | us |
