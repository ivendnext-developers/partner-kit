# 9. The extension points, and how to ask for a new one

**For:** a builder whose need fits no rung of the ladder, or who needs to know which extension points exist.
**Reference implementation:** [Request an extension point](../feedback/point_request.md) (the form) · for each extension point, the chapter and sample named in the table below. The **extension-point library** — one page and one contract for each extension point — is kept with the product. The table below says where each is covered in the kit; the contracts are in [`contracts/`](../contracts/README.md).

## What an extension point is

Most of what a customer asks for needs no new door: set it up in iVendNext (chapter 4), run your own service beside it (chapter 5), give the cashier a key (chapter 6) or ship your own records (chapter 7). An **extension point** is the door we build when none of those can do the job. It is a published place in iVendNext where your service, your page or your declared data takes part, with three things fixed in advance:

- **the question we ask you**, and the closed list of answers we accept;
- **what happens when your service is down** or too slow;
- **what happens on a till with no network.**

Because all three are written down before you build, the cashier is never left waiting on something we did not plan for. An extension point is never a place to change money after the cashier has seen it, and your service's code never runs inside the shop's site: where an extension point asks your service during a save, our code asks and applies your answer from a closed list (chapter 3, the four rules). The one code of yours that runs inside the shop is a sandboxed module we have certified, at the two extension points that take one (chapter 8).

## When to use it

Go down the ladder first (chapter 3). Come here only when the rung above cannot do the job:

1. **Is the extension point you need in the table below?** Use it and the chapter it names.
2. **Is it not listed?** Combine the doors you have first (chapter 3, rung 6): an outside app with a document check, a Desk button that asks for inputs, a partner page opened from a button, a capture at the scan, save rules and configuration meet most needs, and a composition with its limit stated is a complete answer. Ask for a new extension point (below) only when no composition meets the customer's outcome, and say in the request which compositions you tried and why each falls short. Composing keeps the four rules: it is never code inside the shop, a script in Desk, or a price changed after the cashier has seen it.

## The extension points

Each is dormant until the customer's administrator switches it on, except field rules, which have no switch.

| Extension point | What it lets you do | Where in the kit |
|---|---|---|
| **Remote till key** | Your HTTPS service answers a key the cashier presses: a message, details added to the sale, values for its lines, or any of them together. | Chapter 6 · [A till key](../recipes/point_handler.md) · samples [S1](../samples/s1_warranty/), [S2](../samples/s2_bins/), [S6](../samples/s6_ai_till_key/) |
| **Event feed** | Your app pulls its own queue of what changed in the shop (sales, customers, stock) and marks each item done. | Chapter 5 · [Reading iVendNext's events reliably](../recipes/event_feed.md) · [`../tools/feed_client/`](../tools/feed_client/) |
| **Save rules** | The shop declares a rule on a field, held at every save: a code's shape, a value worked out from others, no value twice in a document's rows or across records (one tax id per customer group), a field required when others are filled. A rule can also keep a document's submit or cancel for named roles when its header holds a value (only the receiving store receives a transfer). | Chapter 7 (the `save_rules` kind) · the library page *Save rules* |
| **Desk action** | Your service answers a button on a record in iVendNext Desk, on the form or for the ticked rows of a list. | Chapter 13a · [A button on a Desk record](../recipes/desk_action.md) · [S16](../samples/s16_pick_route/) |
| **Document check** (`doccheck/1`) | Your service has the last word before a back-office document the shop names is submitted (a purchase order, a goods receipt, a stock transfer), from every door: Desk, an import, the API. It allows the submit, refuses it with your sentence, asks the user a question, asks for approval by a role, or fills fields. **Back office only:** never a till sale, and never a record the till's own booking writes (a layaway's order, a delivery's invoice, an offline sale reaching the server), so the till's quote edit and quote cancel are not checked either; the till's door is the check before payment. **`fill` writes only a field the shop added** (a field your package adds counts), never a standard field or money: a subscription naming one is refused when it is saved. | Chapter 7 (an `extension_subscriptions` row of point `doccheck`) · [Purchase orders checked by your ERP](../samples/s34_po_check/) (S34) · [A rule checked before a document is submitted](../recipes/document_check.md) · the library page [*Document check*](../contracts/pages/doccheck.md) |
| **Partner page** | Your own page, framed on the till or in Desk, told who is looking at what by a signed context; on the till it may answer once. | Chapter 13a · [Your own screen inside the shop's frame](../recipes/partner_page.md) · [S17](../samples/s17_partner_page/) |
| **Fiscal reader** | An outside fiscal service's result for a sale, read from the fields it writes, so the receipt prints only when the tax result is back, with the tax authority's QR code and seal where the service writes them. | Chapter 11 · chapter 7 (the `fiscal_readers` kind) |
| **Check before payment** | Your service has the last word on a sale before money is taken: it allows the sale, allows it without some payment methods, refuses it with your own sentence, asks the cashier a question, or calls a manager. Every door that moves money, except those the library page lists, holds your answer to the basket. It is sent the POS day and its terminal (`pos_opening`, `pos_terminal`), so one rule can hold per terminal; both are among the fields the shop consents to send, and a consent ticked before a site took them lapses until the shop ticks it again. | Chapter 7 (an `extension_subscriptions` row of point `check`) · [A rule checked before payment](../recipes/rule_guard.md) · [S18](../samples/s18_rule_guard/) · [Several till rules in one app](../recipes/till_guard.md) · [S23](../samples/s23_till_guard/) · [Coupon rules](../recipes/coupon_rules.md) · [S32](../samples/s32_coupon_rules/) · the library page *Partner check* |
| **Pricing** | Your sandboxed module takes money off a line after every promotion: a member rate that multiplies with a promotion, a cap per line from your own tier table. It runs on the server and on the till offline, never takes more than the shop's own limit (which starts at 0), is never offered a line a Pricing Rule has already priced, a return or a gift-card line, and only a module we have certified runs. The Desk POS does not run it: a sale rung there is priced without your module. | Chapter 8 · [the Wasm kit's template](../tools/wasm_kit/template/) (a member discount) · the library page *Pricing* |
| **Wallet** | Your service keeps a balance (cash back, store credit) that a customer spends at the till as its own payment method: the till asks your service what this sale may use, takes it, and gives it back on a return. | Chapter 11 · [A partner wallet at the till](../recipes/wallet.md) · [S22](../samples/s22_customer_loyalty/) |
| **Scan source** | The shop declares a table of its units' own codes (a barcode per pack, a tag per handset). The till's scan finds the unit, its batch and serial, and refuses one already sold. It also reads a pharmacy pack's GS1 code. It is data: no code runs and nothing leaves the shop. | Chapter 7 (the `scan_sources` kind) · [Unit codes at the scan](../recipes/unit_codes.md) · [S19](../samples/s19_unit_codes/) · the library page *Scan source* |
| **Capture on an event** | Your service is asked when an item your filter names is scanned (a beep and a yes or no, a refusal, or values for the line) and when a new customer is added (a one-time code the server checks before the customer is made). It is also asked when the cashier puts an **existing customer** on a sale (`customer_select`): allow, challenge with a one-time code, or refuse (the customer is taken off the sale). The server holds every door that charges or books the sale until it has recorded your pass for that cashier, customer, POS Profile and service (a payment on something the customer already holds, such as a layaway's later payment or an order's balance, is not held); the booking spends the pass; the store's walk-in customer is never asked. | Chapter 7 (an `extension_subscriptions` row of point `capture`) · [A value captured at the scan, and a code before a new customer](../recipes/capture.md) · [S20](../samples/s20_capture/) · [S23](../samples/s23_till_guard/) (a beep and a yes or no on a ticked item) · the library page *Partner capture* |
| **Field rules** | Per till theme, the till hides a field, calls it by the shop's own word, requires it on a new customer, or shows up to three more item fields and three more customer fields, offline too, and item fields on the receipt (on screen, on paper and on the offline slip). It is data: no code runs and nothing leaves the shop. | Chapter 7 (the `field_rules` kind) · [The shop's own fields on the till](../recipes/field_rules.md) · [S21](../samples/s21_field_rules/) · the library page *Field rules* |
| **Label layout** | The shop declares a label stock and its layout (HTML, or Zebra printer commands for a counter's label printer) with placeholders from a closed list; the cashier prints shelf labels from an item or a basket line. It is data: no code runs and nothing leaves the shop. | Chapter 7 (the `label_layouts` kind) · chapter 11 · the library page *Label layout* |
| **Receipt** | Store settings, not a declaration: the shop's own header and footer lines on the shipped receipt without copying it, WhatsApp on the Print sheet where the store has the WhatsApp app, and a register's receipt layout checked before it is set. No manifest kind. | Chapter 4 · chapter 11 · the library page *Receipt* |

One more way in is not an extension point: the **manifest install screen** (chapter 7) installs your declared data, and the declarations of the extension points above, except the wallet (registered on the shop's payment screens), the receipt (store settings) and pricing (a module the shop's administrator adds in Desk). Each is installed switched off where the product has a switch. A field rule has none: it reaches every till on its theme at the till's next start.

## Asking for a new extension point, or for more from one

1. **Say what you need, not how.** Describe the customer's need in business terms. A request that needs money changed in a hook, an override, a server script or in-tenant code by an outsider is read as a request for the need to be met another way.
2. **Check the catalogue above and the ladder.** If an extension point already does it, the answer says which.
3. **Fill in the [request form](../feedback/point_request.md).** It has three short questions and a tick box: what you need to do (and the step in the sale it concerns), the closest extension point, and what happens if it is never built. We ask the rest in the issue: the data in, the answer out, what should happen when your service is down, how long the cashier may wait, and what should happen offline. A request that leaves out *down*, *slow* or *offline* comes back with those questions.
4. **Send it.** The form is a GitHub issue form in the private feedback repository, `ivendnext-developers/partner-feedback`, open to onboarded members: an iVendNext Partner, a licensed customer's IT team and the CitiXsys Consulting Team (chapter 17). Every member can read every issue, so leave out secrets and customers' names.

**What happens next.** It is given an id and answered in the issue, as one of four things: **answered** (an existing door already meets it, and the answer says which), **needs more** (a question about a field), **planned** (it joins the work we do, and you can follow it) or **declined**, with the reason. Requests of the same kind are collected, and the collection decides what is built next. We give no date.

## What is refused, and why

- **A request that breaks one of the four rules** (chapter 3): money changed after the cashier has seen it, an override or patch of iVendNext, your code inside the customer's site, your own screens in Desk or on the till. These are declined with the reason, not planned.
- **Product work dressed as an extension point.** A change to what every cashier sees, or to the order of the steps, is product work, not something a partner extends. It is declined, with that reason.
- **A declaration the product has no door for.** A manifest that declares something no extension point accepts is refused, and the checker names why.
- **A sandboxed function where there is no module leg.** Only the check before payment and pricing run a module, and only one we have certified; a manifest that carries a module is refused, and the checker names why.

## When your service is down, and when the till is offline

Every extension point states both before it ships. For the ones above:

| Extension point | Your service is down or slow | The till is offline |
|---|---|---|
| Remote till key | The cashier reads that your app could not finish; nothing is added; the sale goes on. No retry. | The key is dimmed. |
| Event feed | Nothing is lost: you pull, so your events wait until you are back. | An offline sale's events appear when the till syncs, possibly hours later. |
| Save rules | No service is called. | A write inside an offline sync is never refused, only flagged for review. |
| Desk action | The user reads *"… did not answer in time. Check the record before you try again."* It never claims nothing changed: your service may have written before it went quiet. | Desk is online by nature. |
| Document check | The answer you declared applies: allow the submit and flag it (the default), refuse it (*did not answer, so this document can't be submitted yet*), or ask the user whether to submit anyway. The document waits for you, at most 10 seconds for all of one submit's checks. | None: back-office documents are submitted on the server. A sale the till made offline never reaches you. |
| Partner page | A page that does not load in 10 seconds shows *"… isn't answering."* Nothing is added to the sale. | The key is dimmed. |
| Fiscal reader | The sale waits as *pending* and its receipt is held until the service answers or the back office does. | A sale made offline waits as pending, like any other, once the till syncs it. |
| Check before payment | The answer you declared applies: allow the sale and flag it (the default), refuse it, or ask the cashier whether to go on. | You are not called. The till applies each check's declared answer; the sale, when it syncs, is flagged and never refused. A need that must hold offline declares *refuse*, or runs as a module (chapter 8). |
| Pricing | No service is called: the module runs inside the shop. A module that traps, runs out of steps or answers something refused takes nothing off the line. | The same module runs on the till from its offline copy. A customer the till does not know reads as no customer group, so a rule keyed on the group takes nothing off there. |
| Wallet | The till says the wallet did not answer, and the cashier takes another payment. A payment left without an answer is settled later by asking your service about its reference. | The wallet is not offered. |
| Capture on an event | The answer you declared applies: let the item or customer on and flag it (the default), or refuse. On `customer_select`, *refuse* takes the customer off the sale. | You are not called. The till applies the declared answer: a scanned item your filter names is let on or refused by it, and a customer is taken on the till or stopped by it. A customer added offline and synced with the sale is created and flagged, never refused. On `customer_select`, a sale paid offline with a customer you were not asked about books when it syncs and is flagged. |
| Scan source | No service is called: the source is a table in the shop, and one that cannot be read is skipped. | A unit's code reads *Not found*: the cashier scans the item barcode and picks the batch. A GS1 pack code is read offline. |
| Field rules | No service is called. | Hide, relabel and require work, and a shown field rides the till's offline data. A customer added offline without a required field is created when the sale syncs, and flagged. |
| Label layout | No service is called. | The cashier reads *"Labels need a connection."* |
| Receipt | No service is called. | WhatsApp is not offered offline: the receipt offers email and SMS, as before. |

## Technical notes

### What the kit has proven

- **The manifest installs the declarations of the extension points.** On the test shop a manifest installed a Desk action, a Desk-action and a page subscription, two save rules and a fiscal reader, all switched off. When the shop switched them on, the product accepted them (chapter 7).
- **The manifest installs Wave B's declarations too (2026-10-08).** On the test shop a manifest installed a check and a capture subscription, a scan source and field rules on a named till theme; each was used by the product, exported as the shop left it, uninstalled to the schema as found and reinstalled (chapter 7).
- **Two were walked on screen.** The Desk action (S16) and the partner page (S17) were walked in a real browser on the test bench on 2026-10-07.
- **The document check and the two newest save-rule kinds were used on a sandbox site (2026-10-21, POS app 2.0.0.656, a build after the one that brought them), through the API.** A purchase order's submit with S34's service unreachable took the declared *refuse*, and its log row was written by the next scheduled job; a subscription naming a standard or a money field to fill was refused at its save; a second customer with one tax id in one customer group was refused; a Material Request of type Purchase was refused at submit for a user without the role and submitted by one with it. Not run there: Desk's question and approval dialogs, an import, and a service's own answers (proven on the laptop against the contract).
- **A remote till key was pressed by a cashier on the till's own screen,** the iVendNext POS app in a desktop browser on our test bench (S6's *AI tip*, 2026-10-07, frame `/pos?frame=terminal`, POS app at `8dc36aab8`), answered over HTTPS with a certificate the bench's server trusted for the run. S1's *Warranty* key was pressed through the same endpoint from the bench's console as the cashier, not from a screen (2026-10-07).

### What it has not

- **The kit's contracts are a copy.** The tables name each page; the pages and schemas are in `contracts/`, copied from the product at a pinned commit, and the product's own pages are the source.
- **The four newest were used through the till's own server calls (2026-10-08).** S18's check was driven through the till's payment door on the test shop: a refusal in the service's own words, with the card push refused before any money and no sale booked; a question refused until the cashier's Yes; a slow, down, invalid or malformed service under both declared down answers (22 of 22). S19's unit codes (9 of 9), S20's scan capture and customer code (16 of 16) and S21's field rules (6 of 6) ran too, and the money kit rings a sale through the check as a till does.
- **The four newest were not walked on a till screen,** and were not run offline. Not run for S18: a check with *ask* as its down answer, excluded payment methods, a manager's approval, a return. Not run for S20: *confirm* and *refuse* on scan. A sale refused after a failed check but paid by card books and is flagged (read in the code, not run).
- **The scoped event feed:** the kit's client reads its door with POST (read on a test shop on 2026-10-09). The client's crash-and-restart exit check ran against a stand-in for the door only (chapter 5).
- **The wallet** was walked on a sandbox till only with CitiXsys's own reference implementation (chapter 11 says which steps); the kit's sample S22 has run only in its laptop tests.
- **A press from a physical till device** (a counter terminal or a phone, rather than the till app in a desktop browser) was not tried, and neither were the Desk screens for registering a till key.

### Sources

- **Not listed on purpose.** Two engine-side items (narrowing the feed's grant, and default permissions on two record types) are product work on the underlying engine, not extension points a partner uses, so they have no row here.
- **What the table does not mean.** Each extension point above is dormant until configured (the receipt layout check runs on every change to a register's receipt layout). Being in the table does not mean every example in the kit has run against it; the sections above say which have.
- **Request form.** `../feedback/point_request.md`, three questions and a tick box; the rest is asked in the issue.
- **Names.** The record the shop's administrator fills in for most of these is a *Retail Extension Subscription*; its call log is the *Retail Extension Log*; a sandboxed module's record is a *Retail Extension Module*.

## See also

[3. The ladder and the four rules](03_ladder_and_never_list.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [6. Till keys](06_till_keys.md) · [7. Manifests](07_manifests.md) · [11. Payments, fiscal, hardware](11_payments_fiscal_hardware.md) · [16. Possible, not possible, limits](16_possible_not_possible.md) · [17. Submitting, support, feedback](17_submit_support_feedback.md)
