# A loyalty provider connected to the till — the recipe

Many retailers already run their loyalty programme with an outside provider (Punchh or GameBall, for example): the members, their balances and the rules live in the provider's system. This recipe connects such a provider to a retailer's iVendNext as an **outside app**: each booked sale earns in the provider's programme, a member spends their balance at the till as a payment, and the member can confirm a spend with a one-time code. It is for an iVendNext Partner, or a provider connecting its own product.

**Nothing of yours runs inside the shop.** Your service runs on your own server and holds the provider's account and keys; the shop only ever talks to your service, and your service talks to the provider.

**Start from:** `samples/s22_customer_loyalty/` and its two recipes, [A customer's own loyalty programme](customer_owned_loyalty.md) (the earning) and [A partner wallet at the till](wallet.md) (the spending). S22 keeps the balance itself; here the provider keeps it, so you replace S22's ledger with calls to the provider.

**When to use it.** The retailer's programme lives with a provider and must stay there. If the retailer owns its rules and wants the records inside iVendNext, use S22 as it is; if iVendNext's own loyalty does the job, configure it instead (chapter 4).

> ⚠ **UNPROVEN.** No sample runs this combination. Each door below is published and has its own recipe; the three together, against a provider, have not been run by the kit.

## The three doors

| What happens | The door | Its recipe |
|---|---|---|
| **Earning.** A sale books; your service reads it from the shop's queue of changes and tells the provider | the event feed extension point (`sale.booked`, `return.booked`, `sale.cancelled`) | [Reading iVendNext's events reliably](event_feed.md) |
| **Spending at the till.** The cashier taps the provider's tile; the till asks your service the balance and the most this sale may use, then takes it as a payment | the wallet extension point | [A partner wallet at the till](wallet.md) |
| **The customer's one-time code.** The provider sends the member a code; the cashier types what the member reads out | the wallet's own code field, or the capture extension point's `customer_select` *challenge* (step 5) | [A value captured at the scan, and a code before a new customer](capture.md), step 5b |

## Steps

1. **Map the customer to the member.** Keep your own map of the shop's customer id to the provider's member id. Fill it when a customer is created (`customer.created` on the feed: look the member up by the phone or e-mail the shop holds) and when a member first shows at the till. A customer with no member is simply not a member: the wallet answers *not eligible*, and the sale earns nothing.

2. **Register your app and its user** (the shop's administrator): one integration user for your service ([integration user](integration_user.md)), and a registered application on the feed that follows **POS Invoice** and **Customer**, each record type ticked on ([event feed](event_feed.md), step 1).

3. **Earn on the feed.** Pull your events; on `sale.booked` read the sale over the API and send the provider what earns. Key every provider call on the shop's sale number, so a replayed event earns once (the feed delivers at least once). On `return.booked` and `sale.cancelled`, take back that sale's share, never more than it earned (S22's recipe, step 6, has the money rules). Mark every other event done.

4. **Answer the wallet's questions.** Copy S22's `service/wallet.py` and its signed route, and replace its ledger with the provider:
   - **preview:** the member's balance and the most this sale may use, from the provider, within 3 seconds in total;
   - **authorise:** redeem at the provider, keyed on the payment's reference, so the same reference asked twice is one redemption;
   - **reverse** and **refund:** give it back at the provider, keyed on the reference, never more than was paid;
   - **status:** the provider's answer about exactly that reference.

   Then register it on your sandbox as the wallet recipe's steps 2 to 9 describe (the certificate, the Remote Connector, the payment account and connection, the payment method on each till).

5. **The one-time code, when the provider wants one.** Choose one of two places:
   - **At the spend (the wallet's own code):** your preview answers `otp_required: true` and asks the provider to send the member a code (at most one per sale and customer: the 3 seconds include the provider's send, and a preview may be asked again); the till shows a code field with the amount, and your `authorise` receives what the cashier typed as `payer_code`. A wrong code is `declined` with reason `invalid_code`. Never store or log the code ([the wallet page](../contracts/pages/wallet.md); [the gateway contract](../contracts/pages/paygw.md), §3a). This asks only when the member spends.
   - **When the member is put on the sale (`customer_select`):** a capture service on `customer_select` answers `challenge`, sends the code through the provider, and checks it at `verify`. Use it only when the provider must confirm the member on **every** sale they are on: while it is switched on, every sale with a customer is held until your service allows it or a code is checked.

6. **Keep the provider's account and keys on your server.** The shop never sees them: it holds your service's address, the signing secret you chose for each door, the wallet's certificate and merchant reference, and your integration user.

## When your service or the provider is down, and when the till is offline

- **Earning:** the events wait in the feed until you are back; nothing is lost. A sale earns late, never twice.
- **Spending:** the till says the wallet did not answer, and the cashier takes another payment. Never answer *approved* until the provider has redeemed.
- **The code at `customer_select`:** the answer you declared for *down* applies (let on and flag, or refuse).
- **Offline till:** the wallet is not offered and `customer_select` is not asked; the sale earns when it syncs, if the customer stayed on it (a `customer_select` declared `refuse` takes them off offline).

## What is proven, and what is not

- **Proven elsewhere, door by door:** S22's earning on the feed on our test bench; a partner wallet walked on a sandbox till with CitiXsys's reference implementation ([the wallet recipe](wallet.md)); `customer_select` with a one-time code walked by the product on three till frames (the card [A question when an existing customer is chosen](../needs/customers/question-on-existing-customer.md)).
- **UNPROVEN:** the three together, any provider's own interface, the wallet's own code field (`otp_required`) with a partner's service (S22 answers `false`), and the conformance kit against a wallet that calls a provider.
