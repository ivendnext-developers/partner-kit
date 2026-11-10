---
id: delivery-marketplaces-through-a-delivery-partner
title: DoorDash, Uber Eats and Grubhub orders reach the kitchen through a delivery partner
area: integrations
topic: online-shops-and-orders
asks: Our DoorDash, Uber Eats and Grubhub orders come in through our delivery partner (Otter, Deliverect, Chowly or Olo), go straight to the kitchen, tell the app how they are getting on, and what we have run out of (86) stops selling
status: ready-with-limits
door: station-ticket
blocked-by: -
recipe: recipes/kitchen_screen.md
sample: none
request: -
verified: run on a sandbox 2026-11-10 · POS 2.1.0.697 (a Sales Order sent with `call_number` showed the code on its ticket; an *Update Items* that cut a line, and then a cancel, each wrote a void ticket (`kind` void) with the same code; an order sent with no code read its own name, and a call with a code alone relabelled its ticket; made as the sandbox's administrator, the board read as the store's manager) · and on 2026-11-08 · POS 2.1.0.694 (with the key of an app user made by hand, as the open check's: a Sales Order saved, submitted and sent to the kitchen reached the Grill station's board as a sales_order ticket with its note; the same order read back started, ready and bumped; a second send was refused as nothing new; a dish marked sold out read as unavailable, and available again after the clear; the event feed carried a ticket's steps and a sold-out's changes made by another user) · not run against a delivery partner's own test system, a menu, or settlement
related: local-delivery-app, kitchen-screen-reads-station-tickets, own-online-shop
---
## What you build
A small service of yours (or one the delivery partner builds) between a delivery partner the marketplace has approved and iVendNext; you build to the delivery partner, not to the marketplace. It carries four jobs, on the door's page (`contracts/pages/station_ticket.md`):
- **The menu out.** Read *Item*, *Item Price*, *Retail Option Group* and *Retail Item Option Group* through `/api/resource/…` under your app's rights, and publish them to the delivery partner.
- **The order in.** `POST /api/resource/Sales Order` (`customer`, `company`, `delivery_date`, `set_warehouse`, the `items`), submit it (`PUT` `{"docstatus": 1}`), then call `ivendnext_mpos.api.v1.sales_order_to_kitchen`, with the courier's pickup code as `call_number` if you have it. Each kitchen answers `handed` or `failed` with the reason.
- **Its status back.** `ivendnext_mpos.api.v1.station_tickets` reads a store's board: a ticket's `call_number` is the code you sent, else the order's name, and its state is `new`, `started`, `ready` or `bumped`. Read `kind` as well: a `void` ticket stops a dish and is not a status. Report the nearest status the delivery partner's own document allows.
- **What is sold out.** `ivendnext_mpos.api.v1.item_availability` answers the store's items that carry a rule; pause on the delivery partner each one that reads `available: false`.

## Limits
- Cancelling the Sales Order (`PUT` `{"docstatus": 2}`) writes a *VOID: STOP MAKING* ticket (`kind` void) on the board and the printer, with the same `call_number`. The original ticket stays on the board until it is bumped: read the void before confirming a cancel to the delivery partner as stopped.
- To cut a dish, have the store cut it in iVendNext Desk with *Update Items*, which voids only what was cut; there is no call for it in `ivendnext_mpos.api.v1` yet, so an app cuts by cancelling the order and sending its amended copy, which `sales_order_to_kitchen` sends whole.
- No delivery partner is connected to iVendNext today. This card was checked against Deliverect's and Otter's published documents; Chowly's and Olo's are not public. Each one's approval of the link is yours or theirs to get.
- Each delivery partner sends orders to an address you run, in its own format. Keep its order id on the Sales Order (`po_no`), look for it first, and handle one order id at a time, because delivery partners send an order again.
- A ticket belongs to one station, and there is no read by order: match `call_number` on the store's board. An order is ready when each kitchen's `send` ticket is `ready` or `bumped` and none answered `failed` (call again after fixing it). `bumped` means it left the pass, not that the courier took it.
- A status needs a kitchen screen to move the ticket: a kitchen that only prints stays `new` and never reports preparing or ready.
- Send the marketplace's pickup code as `call_number` with the first call, or alone in a later call when the courier is assigned after the order reached the kitchen: every ticket of the order, and its voids, then read it (a ticket already printed keeps the order's name). With none, the ticket shows the Sales Order's name.
- A Sales Order line has no choices under a dish: write the dish's choices into its *Additional Notes*, and add a priced choice's price to the dish's rate. A choice sent as its own line is a dish of its own on the ticket.
- To hear of a change without reading, follow *Retail Kitchen Ticket* and *Retail Item Availability* on your event feed (seconds later, and never for your own user's writes). Ignore the sold-out labels and read `item_availability` on each event and on a timer: a sold-out that ends at its own time sends no event, and an item no longer listed is available.
- Send a scheduled order when it is time to cook it; the board keeps a ticket for 12 hours.
- Your app's user is set up as for the open check: one user per app, a row for each store with a register that lists each kitchen, *May Work a Kitchen Screen*, create, write, read, submit and cancel on Sales Order (run with the Sales User role: the void follows whoever may cancel the order), and read on *Retail Item Availability*. A printer cabled to a till answers `failed` with no ticket: use a network printer, or none for a kitchen screen only.
- Settlement is yours, as for any Sales Order: the invoice and the marketplace's payout. Where the marketplace collects the sales tax, agree with the customer how the order books it. Not run.

## Tell the customer
Once your delivery partner's link is built, your delivery orders reach the kitchen as tickets the cooks already know, and the link sends the delivery apps the status your kitchen screens record and pauses a dish you run out of. No delivery partner is connected yet. When your link cancels or cuts a Sales Order, the kitchen gets a void ticket.
