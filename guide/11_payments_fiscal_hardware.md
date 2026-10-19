# 11. Payments, fiscal and hardware

**For:** a builder whose customer asks for a payment method, a fiscal country or a device.
**Reference implementation:** for the main thing a partner can build here, an outside fiscal service's result on the sale, [Shipping your own data in a manifest](../recipes/manifest.md) (the `fiscal_readers` kind) and chapter 7. For a partner's wallet at the till, [A partner wallet at the till](../recipes/wallet.md) and sample S22; for a card or mobile-money connector, [Your own card or mobile-money connector](../recipes/payment_connector.md), built from the payments team's own stand-in connector. For hardware only [A receipt laid out for your market](../recipes/receipt_format.md) applies.

## The short answer

| The customer asks for | Today |
|---|---|
| A card or other payment connector | **Ours, or yours.** We build and install our own connectors; a partner may build one on its own server, on the gateway contract `paygw/1` ([recipe](../recipes/payment_connector.md)). |
| Their own wallet or loyalty scheme spent at the till | **An extension point:** your service answers the till's wallet ([A partner wallet at the till](../recipes/wallet.md), sample S22). |
| A country's tax clearance | The country apps **we** ship are ours. **An outside fiscal service may record its result** through a declared *fiscal reader* (below). |
| A QR code or fiscal mark on the receipt | **An extension point:** a fiscal reader may name the tax authority's QR code and seal, and the shipped receipt prints both for a cleared or reported sale; the Saudi Arabia and Mexico apps' marks print too. |
| A printer, label printer or other device | The print routes and device drivers are ours. A **label layout** the shop declares or a manifest installs (HTML, or Zebra printer commands for a counter's label printer) is an extension point. |

## When to use it

Read this chapter when a quote includes money moving, a tax authority or a device. It tells you what to promise and the doors open to a partner: a payment connector (a wallet among them), the fiscal reader and, for labels, a label layout.

## Payments

**What we provide.** One payments core and one thin connector for each payment gateway, each connector passing our conformance kit.

**Two card providers on one site:** a till takes card through the one provider its own card reader is bound to, so two providers (or two accounts of one provider) can run on one site, each on its own tills; this is in payments core 2.1.0. Walked with two Stripe sandbox accounts on two readers, and with a partner's connector on a till in place of Stripe, one at a time (our own stand-in, not a real provider). **Ask us before you promise:** one till taking card from two providers at once (a till has one reader binding); a mobile-money or pay-later payment method at the till (the till routes only a card reader's account; a till without a reader has no screen for it yet); and a split, layaway, order or account payment through any provider, which books as plain *Credit Card*, not the provider's own payment method. A card sale made on another cashier's open day also books as *Credit Card*.

**Your own payment connector: open to partners.** A partner builds a payment connector on its own server, and our payments core reaches it over HTTPS through the gateway contract **`paygw/1`, revision 1.0** (approved 2026-10-13), in one of three profiles: **card** (a card present at the till), **push** (mobile money or pay-later, finished on the customer's own phone) and **wallet** (below). Nothing of yours runs in the shop. The core calls your connector with four verbs, each call signed: `authorise`, `status`, `reverse` and, for a wallet only, `refund`; a wallet also answers `preview` (the balance and what this sale may use, within 3 seconds). A payment that completes later is reported by your connector calling back; name your connector in a `User-Agent` header on every call you make to us, or a network edge may refuse it (the wallet recipe's first step). On its sandbox copy only, your connector also answers `induce` and `settle`, which let the conformance kit drive the money-safety cases; a live connector refuses both. Card numbers never pass in clear through our system or yours. **Starting needs no approval from us:** you choose your connector's signing secret and sign its sandbox certificate yourself with [the sandbox certificate tool](../tools/sandbox_cert/README.md). The contract's full text is in the kit: [`contracts/pages/paygw.md`](../contracts/pages/paygw.md), a copy of revision 1.0; how to build one: [Your own card or mobile-money connector](../recipes/payment_connector.md). **Going live:** run our conformance kit from your connection on your sandbox site. When it reads **CERTIFIED** and **SEALED**, download the report and send it, unchanged, to `https://library.ivendnext.app/v1/payment-certificate` (POST). Paste the `certificate` you get back into the Remote Connector on the customer's site. No one at CitiXsys needs to act. Your partner code is bound to the site you first certify from. No pilot store is required. The step works on sites running our remote gateway app at 2.1.0 or later. You may sell the connector to your own customers, or list it in the App library. A terminal wired to the counter, which needs a program running in the store beside it, comes in a second phase.

**Your wallet at the till.** A customer's own wallet or loyalty balance, kept by your service, is spent at the till as its own payment method: the cashier taps it, sees the balance and what this sale may use, and enters an amount. Your service answers the till over HTTPS on the gateway contract's wallet profile (`paygw/1`, `wallet/1`), and the shop registers it as a remote connector with a certificate. **On your sandbox:** we install the remote-wallet payments app on request. How to build one: [A partner wallet at the till](../recipes/wallet.md); a worked one: sample S22's *Member cash*. Earning stays on your side after the sale, as before: your service follows the event feed (chapter 5) and adds to the balance it keeps.

## Fiscal and e-invoicing

**The till never talks to a tax authority.** A country's fiscal app, or an outside service, clears or reports each sale and records the result on the sale. The till reads the result and decides whether the receipt may print as a tax document.

- **Our country apps are ours:** Saudi Arabia and Mexico today. A new country's own app is ours to add.
- **An outside fiscal service can record its result.** If your service reaches the tax authority itself, a **fiscal reader** tells the till which fields on the sale hold your result and what each value means. A new country on this route needs no release of ours.

### Steps: an outside fiscal service

1. **The shop turns on *Clearance required* for its country.** Without it the product refuses the reader: the receipts would print at once with no tax receipt number. This is done in the shop, before the install.
2. **Your manifest declares the result fields and the reader** (chapter 7, the `fiscal_readers` kind). The status, the tax receipt number and, if you have them, the QR code and the seal are different fields on the sale (make the QR and seal fields Data, Small Text, Text or Long Text; for an XML-form seal the shop changes the seal field to Code after the install). Each is **No Copy**, **allowed on submit**, and at a permission level above 1 (never 0, never 1, never 9) that no other role may write. The map says what each value your service writes means, once each: *cleared*, *reported* or *pending*. Never *not fiscal*: that is the till's own classification, and it releases the receipt.
3. **The shop switches the reader on, adds the role's sale rights and makes your service's key.** The reader is installed switched off. The service's user holds one role, its own writer role, and nothing else. The installer gives that role rights only at the result fields' own level, so the shop adds the role's ordinary rights on the sale (read, write and submit) and generates the user's key (chapter 7 lists the steps).
4. **Your service writes its result with its own key,** by saving the submitted sale through the API with **every result field filled, every time**. A value counts only when the sale was last saved by one of the reader's declared writer users.
5. **What the cashier sees.** From the moment a sale for a company your service serves is booked, it waits as *pending*: *"Waiting for the tax receipt number … ask the back office."* A *cleared* or *reported* result releases the receipt.

**To change fiscal service, let waiting sales clear first, then repoint the one reader.**

The kit has tried this route only with a test script standing in for the fiscal service. No tax authority was reached.

### What is refused, and why

- **A result field anyone else can write.** A field at permission level 0 (anyone who may edit a sale), at level 1 (the shop's Accounts Manager already writes there), at level 9 (the till keeps it for its own tax result), or one that is copied onto a new sale is refused when the reader is saved or switched on.
- **A writer role held by anyone but the service's declared users.** Refused, with the user named.
- **A reader for a company whose country does not wait for clearance.** Refused, naming the company.
- **A status the map does not know.** It writes nothing, and the sale keeps waiting.
- **A value saved by anyone but a writer user.** Never mirrored; the receipt keeps waiting.
- **Another role gaining write on a result field later.** The writer rule is checked again every time a value would be mirrored: if it no longer holds, nothing is mirrored and every receipt keeps waiting.
- **More than one reader per source,** or the same value twice in the map. Refused.
- **A reader on a site with more than one company,** unless every company's country waits for clearance. Our rule is one company per site.

## Hardware

**What we provide.** Four ways to print: a network printer, the device's own print dialog, a helper app, and the counter printer on wired tills. Receipt formats and customer-display templates are configuration (chapter 4); a receipt laid out for your market is a recipe ([A receipt laid out for your market](../recipes/receipt_format.md)).

**Extension points** (chapter 9): the tax authority's QR code and seal on the receipt; WhatsApp on the Print sheet, where the store has the WhatsApp app; the shop's own header and footer lines; and shelf labels printed from the till (phone, counter or tablet) from a label layout, a counter's Zebra printer included. **Handheld does not print labels:** it adds them to the back office's print list, which a desktop utility prints, as labels from the back office do today. A device driver stays ours: a builder cannot add one.

The kit has not yet run the counter printer or the helper app on real hardware.

## When your service is down, and when the till is offline

- **Your wallet service is down:** the till says the wallet did not answer, and the cashier takes another payment (the product's wallet page says so; not yet walked). A wallet is never offered offline.
- **Your fiscal service is down:** the sale waits *pending* and its receipt is held. A recorded *pending* stays until a result arrives, whatever the shop changes later; the service, or the back office, owes that sale its answer. The till promises no retry.
- **The till is offline:** cash goes on, and so does a card taken on the bank's own machine and recorded by hand. An integrated card, a tax receipt in a country that waits for clearance, live balances and live stock are refused. The sale itself is kept: once the till syncs it, it waits as *pending* like any other until your service answers. The kit has not rung a fiscal sale offline; this is how the product describes it.

## Technical notes

### What the kit has proven

- **A fiscal reader installs, in order.** On the test shop a manifest made the result fields, the role, its permission row and one integration user, then the reader, switched off. The shop's country had to wait for clearance first, or the reader was refused.
- **The product held the writer rule.** It refused to switch the reader on at permission level 1, without *No Copy*, and with its role held by someone else. Installed in order, it switched on, and a service's *Queued*, unknown and *Accepted* results showed on the sale as pending, unchanged and cleared (chapter 7).

### What it has not

- **A real fiscal service.** The "service" in the test was the test's own script, saving the sale as the integration user; no tax authority was reached.
- **A fiscal sale rung offline.** The offline refusal and the *pending* wait after the sync (above) were read from the product's own documents, not run.
- **Most of payments.** No partner card or push connector exists yet; a second card provider on one site has been walked only with two Stripe sandbox accounts on two readers and with our own stand-in connector in place of Stripe on a till, never a real second provider's money; and the payments conformance kit has not been run against a partner's connector (the payments team ran it against its own stand-in partner connector on its test site).
- **A wallet, only in part.** A partner-style wallet (CitiXsys's private reference implementation, which S22's *Member cash* is adapted from) was walked on a sandbox till on 2026-10-12: the preview and the most a sale may use (there the balance), an amount over it refused, a sale paid with the wallet and cash, and a partial return paying the wallet's part back first. Not walked with it: `reverse` from a till (the payments team walked that on our test site with its own test wallet), the conformance kit against a wallet, and the till's own sheet when the wallet does not answer. S22's own copy has run only in its laptop tests.
- **The print routes on real hardware:** the counter printer and the helper app have not been run on real hardware.
- **A site with a reader and a second company.** Not run: the refusal is read from the product's code.

### Sources

- **Fiscal reader sources.** The extension-point library's fiscal reader page (2026-10-07): the declaration, the writer rule, the refusal sentences, the *pending* behaviour and the offline note. The manifest side: `../recipes/manifest.md` (`fiscal_readers`) and chapter 7. The kit's own walk of it is in chapter 7's *what the kit has proven*.
- **Country apps.** The two compiled-in readers (Saudi Arabia and Mexico) are read from the POS app's fiscal reader; a partner cannot add a compiled-in reader.
- **The wallet.** The kit's copy of the product's wallet page (`contracts/pages/wallet.md`), the payments team's partner starter note (copied into [the recipe](../recipes/wallet.md)), and the sandbox walk of 2026-10-12 described above.
- **Payments.** One payments core, a connector per gateway and the conformance kit are from the payments workstream's own description; the partner connector's shape is the gateway contract `paygw/1`, revision 1.0, approved 2026-10-13 (the kit's copy: `contracts/pages/paygw.md`; the stand-in connector: `contracts/paygw/partner_stub.py`), and the payments app that speaks it (released 2026-10-13 as 2.1.0); the production-certificate step is the payments team's own words. Two card providers on one site is the core's per-till routing (payments core 2.1.0): each till's card reader names its account, and a card sale there books that account's payment method when the account's payment method is listed on the till and live (otherwise it books as plain *Credit Card*, the money still taken). Before it, a second gateway-type payment method on a site switched the card route off; the Desk POS page still has that rule.
- **Offline.** Cash, hand-recorded card, and the waits and refusals are the till's offline model; the *pending after sync* behaviour is the fiscal reader page's.
- **Hardware.** The four print routes are from the product's receipts and labels census; the counter printer goes through the hardware integration app and a print helper on wired tills.

## See also

[4. Configure first](04_configure_first.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [7. Manifests](07_manifests.md) · [9. The extension points](09_points_and_requests.md) · [16. Possible, not possible, limits](16_possible_not_possible.md)
