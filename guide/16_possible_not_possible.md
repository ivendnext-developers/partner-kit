# 16. What is possible, what is not, and the limits

This chapter gives a straight answer to "can we do this for the customer?". The answer is one of three: yes; not through an extension point, with what to do instead; or never. Each answer comes with the limit that goes with it. It is for a builder, or a salesperson, before a quote.

Each answer is a card in the [needs catalogue](../needs/README.md): one card per need, in the customer's words, with its verdict, its door, the recipe and sample to start from, and its limits. On the partner site the two lists below are built from those cards; this chapter keeps the limits that apply to every project.

## When to use it

Use it before you quote. Find each of the customer's needs in the catalogue (on the site, its A to Z list; at a terminal, `python3 tools/needs/needs.py search <words>`). If a need has no card, place it on the ladder (chapter 3). If no single rung fits, combine doors (chapter 3, rung 6) and state the limit of the combination; request an extension point (chapter 9) only if no combination meets the need.

## Possible today

Two kinds: configuration, our connectors and outside apps; then an extension point or a manifest (chapters 7 and 9), which you build and test on your hosted sandbox (chapter 2). The list is built from the catalogue's cards whose verdict is *Ready* or *Ready, with limits*; by area: [prices](../needs/prices/) · [stock](../needs/stock/) · [customers](../needs/customers/) · [till](../needs/till/) · [documents](../needs/documents/) · [reports](../needs/reports/) · [integrations](../needs/integrations/) · [setup](../needs/setup/).

{{needs: possible-today}}

## The four rules

- Money enters the sale visibly, before payment, and is never changed after the cashier has seen it; on a back-office document, before it is submitted.
- Don't override or patch iVendNext.
- Your code runs on your server; inside the customer's site you ship data.
- Your screens come through our doors — on the till your page as a sheet over the sale, the till's own sheets when an item is scanned, a customer is picked or a quantity changes, and extra fields; in Desk buttons, your pages and native screens. You can't put your JavaScript inside our screens.

The reasons and the alternatives are in chapter 3.

## When the product has no door for it

The catalogue's cards whose verdict is *Not yet* (a new extension point, or product work on our side: ask us) or *Not possible* (it breaks one of the four rules), each with what to do instead.

{{needs: no-door}}

## How it behaves, before you quote

| How it behaves | What to do |
|---|---|
| A customer's busiest hour sets the load | run the customer's scale profile on a sandbox before go-live |
| Our Acumatica connector: about 2.75 complete sales a minute per connection | size the busiest hour against it |
| One ERP per company | choose one ERP per company |
| Handheld books online only, and offers no extension point | receiving and counts need a connection |
| A sandboxed function that runs on a till is compiled from Rust | JavaScript started too slowly on a slowed-down till stand-in; a function that only runs on the server may be JavaScript (chapter 8) |
| Till keys answer online only, and the request carries no money and no serial numbers | read money and serials from the booked sale, after it is booked |
| An API key acts with its user's role; there are no scoped keys and no server-to-server sign-in grant | narrow the role; one user per app |
| The kit's samples read the shared feed, whose key is not limited to one app (a scoped feed is an extension point: chapter 9); webhooks try three times, then stop | use the feed for anything you must not miss; a webhook is only a nudge |
| Fields made required by a condition are checked in the Desk form only, not on API writes or imports | your service checks its own writes; a save rule of kind *required when* holds on every save, imports and API writes included (chapter 9) |
| Who may edit a record in a workflow state is checked in the browser only | follow the four safeguards in chapter 13a |
| Permissions hide an action, never a field | hide some fields on the till's screens with field rules, as far as the library's list goes (chapter 9) |
| Member pricing goes through promotions, not pricing rules, and a promotion can only exclude customer groups | one promotion per tier that excludes every other group, non-members included (chapter 4) |
| Offline: pricing rules are not applied; loyalty, gift cards and store credit wait for a connection | plan offline behaviour per need |
| One company is one country and one currency | several countries, several sites |
| Our WooCommerce connector does not reserve stock, and takes percentage vouchers only | state it to the customer |
| Labels from the back office and from Handheld print through a desktop utility | use the desktop utility; labels printed from the till use a label layout (above) |
| A manifest's report, number card or chart cannot name a field the same manifest adds to a retailer's record type, and its workspace cannot link its own report | a list filter on the field, saved by the user, and a workspace shortcut to the record type's list (sample S33) |
| Before POS build 2.0.0.654, a manifest report cannot show a document's item rows, a manifest notification cannot run on a retailer's own record, and a kit print template cannot read rows. From that build all three can: a report's columns from one table of the record, a reminder before or after a date on a retailer's record, and a print format reading through `ivn_rows` and `ivn_value` (chapter 7) | on an older site: a report built in Desk's own report view, a notification the retailer's administrator sets in Desk, an alert record of your own with a notification on it, or an outside app (the cards count-list-totals, expiry-alert-before-date and price-list-with-photos) |
| A warehouse permission does not fence every stock report: on a sandbox, *Item Balance (Simple)*, *Warehouse wise Item Balance Age and Value* and *Stock Ageing* in its default layout showed every store to a user with one store, while the other reports and layouts that were run were fenced | test each stock report a branch may open before you promise it, and take away the ones that leak (the card branch-sees-own-stock) |
| The standard automatic reorder submits its request, never a draft | a draft request needs an outside app (the card stock-and-expiry-alerts) |

## What is refused, and why

Anything that breaks one of the four rules. The reasons are in chapter 3. What we run on a submission is not covered by the kit yet (chapter 17).

## When your service is down, and when the till is offline

Offline, pricing rules are not applied, and loyalty, gift cards and store credit wait for a connection (the offline row in the limits table). Each chapter has its own section on what happens when your service is down.

## The tests

Every need in your blueprint has a card in the catalogue (or a request for one), and every limit on its card and in *How it behaves* is written into the customer's proposal.

## Technical notes

The exact wording behind some limits above, with the evidence for them. The lists of what is possible and what has no door are built from the cards in `needs/` when the site is built, so they are not written in this file; each card says when it was last checked.

- **Feed limit.** The kit's samples read the engine feed, whose key is not scoped to one application (a scoped feed is an extension point: chapter 9); webhooks try three times, then stop.
- **Rust on the till.** A sandboxed function that runs on a till is compiled from Rust. JavaScript compiled to WebAssembly started too slowly on a slowed-down till stand-in; a function that only runs on the server may be JavaScript (chapter 8).
- **Required-by-condition fields.** Conditional mandatory fields are checked in the Desk form only, not on API writes or imports.
- **API keys.** API keys act with their user's role; there are no scoped keys and no server-to-server sign-in grant.
