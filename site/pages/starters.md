# Starters for local work

Some systems a retailer uses are local to a country or a region: its accounting system, its payment gateway or wallet, its loyalty provider, its messaging gateway, its delivery company. Connecting them is a partner's business, not ours: you know the market, and the customer stays yours. This page gives you a starting point for each, where the kit has one: the sample and the recipe to copy, the need it answers in the [needs catalogue](../../needs/README.md), the door it uses, and what usually changes from one market to the next.

Why this is yours to build, and what stays yours: [Build your business on iVendNext's apps](business.md).

## A local ERP or accounting system

- **What you build:** an outside app that keeps the customer's own system and iVendNext in step: items, prices and stock out to the shop; booked sales and returns back, once each; a nightly report of anything the two disagree on.
- **Start from:** sample [S7, a system sync](../../samples/s7_system_sync/) and its recipe, [Keep a customer's own system in step with iVendNext](../../recipes/system_sync.md).
- **The need:** [The customer's own ERP kept in step both ways](../../needs/integrations/erp-in-step-both-ways.md), and [The customer's own order or warehouse system](../../needs/integrations/own-order-or-warehouse-system.md).
- **The door:** an outside app, on the record API and the [event feed](../../recipes/event_feed.md).
- **What changes per market:** the system's API and how it signs in; its item, price and tax fields; its document numbers; which side is the master for prices and stock.

## A local payment gateway or wallet

- **What you build:** a payment connector on your own server for a card, mobile-money or pay-later provider we do not connect; or a wallet, a balance your service keeps that a customer spends at the till.
- **Start from:** the recipe [Your own card or mobile-money connector](../../recipes/payment_connector.md) and its reference implementation, [the payments team's stand-in connector](../../contracts/paygw/partner_stub.py). For a stored balance: [A partner wallet at the till](../../recipes/wallet.md), with sample [S22](../../samples/s22_customer_loyalty/)'s *Member cash*.
- **The need:** [A card or mobile-money provider we do not connect](../../needs/integrations/own-payment-connector.md), and [A store wallet or a loyalty points balance spent at the till](../../needs/customers/store-wallet-at-till.md).
- **The door:** the gateway contract `paygw/1` ([chapter 11](../../guide/11_payments_fiscal_hardware.md)), reached in the customer's site through [Partner payment gateways](https://library.ivendnext.app/apps/ivendnext_pay_remote) in the App library. Your connector passes our conformance kit before it takes money.
- **What changes per market:** the provider's API and its sign-in, its approval flow (at the terminal, or on the customer's phone), its currency and minor units, how it settles and refunds.

## A loyalty provider

- **What you build:** an outside app between the shop and a loyalty provider: each booked sale earns in the provider's programme, members spend their balance at the till, and a one-time code where the provider asks for one. The provider's account and keys stay on your server.
- **Start from:** the recipe [A loyalty provider connected to the till](../../recipes/loyalty_provider.md), built from sample [S22](../../samples/s22_customer_loyalty/) and the [wallet recipe](../../recipes/wallet.md).
- **The need:** [The customer's loyalty provider earned and spent at the till](../../needs/customers/loyalty-provider.md).
- **The door:** three together: the event feed (earning), the wallet (spending), and the wallet's own code field or a capture on `customer_select` (the one-time code).
- **What changes per market:** the provider's API, how a member is found (phone, e-mail, card), its earning and spending rules, and whether it asks for a code.
- ⚠ **UNPROVEN:** each door has run on its own except the wallet's own code field; no sample runs the three together against a provider.

## A messaging gateway

- **What works today:** the till sends the receipt by WhatsApp through the store's receipt settings, with the limits on its card: [The receipt sent by WhatsApp](../../needs/documents/receipt-by-whatsapp.md) (ready, with limits: only where the store has the WhatsApp app set up, and not offered offline). The app is [WhatsApp messages](https://library.ivendnext.app/apps/ivend_whatsapp) in the App library, on the retailer's own WhatsApp Business account.
- **The door:** the receipt settings on the register ([the receipt page](../../contracts/pages/receipt.md)).
- **What changes per market:** the account and its provider, the approved message templates, the language.
- The kit has no starter for a country's own SMS or messaging gateway today. What we build, and when, is on [What iVendNext builds](roadmap.md); the gateway stays yours.

## A local delivery app

- **What you build:** an outside app on S7's pattern: it reads each order to deliver from the event feed, sends it to the delivery company's app, and writes the delivery's status back to the shop.
- **Start from:** sample [S7](../../samples/s7_system_sync/) and the [event feed recipe](../../recipes/event_feed.md) (follow **Sales Order** for `order.booked`, **POS Invoice** for `sale.booked`).
- **The need:** [A local delivery app sent the orders to deliver](../../needs/integrations/local-delivery-app.md).
- **The door:** an outside app, on the record API and the event feed.
- **What changes per market:** the delivery app's API, its address and zone format, its statuses, and who pays for the delivery.
- ⚠ **UNPROVEN:** no sample sends orders to a delivery app.

## When none of these fits

Look the need up in the [needs catalogue](../../needs/README.md), and if no door fits, tell us through the [feedback forms](feedback.md).
