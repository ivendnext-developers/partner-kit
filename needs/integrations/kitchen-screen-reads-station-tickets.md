---
id: kitchen-screen-reads-station-tickets
title: A kitchen screen reads a station's tickets and moves them
area: integrations
topic: outside-systems
asks: Our kitchen screen shows each station what the tills sent, the cooks tap a dish started, ready and bumped, and a board tells the guests whose order is ready
status: ready-with-limits
door: station-ticket
blocked-by: -
recipe: contracts/pages/station_ticket.md
sample: none
request: -
verified: run by the product 2026-10-29 (the product's own walk, before its review fixes, which its tests then proved, through the API and the site's live socket: an integration user set up as the open check's, then Generate Keys, its store row kept; a till's Send printed the ticket and the user's server was told within 0.1 seconds; the user read the grill board with the guest, course and allergen line, moved a ticket started, ready and bumped, was answered already for the same step twice, and was refused a skip, a step back, another store's board and an unknown order); not run by a kit sample
related: open-check-from-an-app
---
## What you build
A kitchen display (a screen per station, an expo screen, a *Now serving* board) on the *station ticket* door (`station_ticket/1`, POS version 2.1.0.669 and later) through `ivendnext_mpos.api.v1`: `station_tickets` reads a station's board (every ticket a till sent in the last 12 hours that is not bumped, and those bumped in the last 30 minutes), `station_ticket_move` moves one ticket one step (`new`, `started`, `ready`, `bumped`; the same step twice answers `already`), and the notice `mpos_station_ticket` on the site's live socket says which store and station changed, so your screen reads that board again. `set_item_availability` marks an item sold out at a store and `item_availability` reads it. The calls, rights and refusals are on the station ticket page (`contracts/pages/station_ticket.md`).

## Limits
- The retailer sets up the kitchens in iVendNext Desk (*Kitchen Stations*) and gives your app's user *May Work a Kitchen Screen* in a Retail Permission, and its store, as for the open check. A station your screen serves still needs a printer that takes the ticket: a send no printer takes writes no ticket.
- The notice comes only to a long-running server of yours (never a function, which holds no connection between calls) on the site's own Socket.IO socket at `/socket.io` (namespace `/<site name>`, your user's key in `Authorization: token <key>:<secret>`, `Origin` the site's own address, a `Cookie` header with no `sid`), never to a page on another address.
- There is no cursor: every read is the whole board. Read it on every notice and every few seconds, since a ticket can leave the board with no notice.
- Tickets a till printed while the store was offline never reach the board.
- One integration user for each kit app: a user that ever enrolled a till device is refused (`DeviceRequiredError`). A user who holds the right only through write on Kitchen Stations may read and move tickets but is never told of a change.
- Your screen moves tickets only: it never voids, comps or changes a line, and a ticket carries no price.
- A `void` ticket names a dish a manager voided, with no link to the ticket it cancels: show it for the cook to strike, and leave it out of a *Now serving* count.
- ⚠ The sold-out calls are not fenced to your user's stores: they answer to read, write and create on *Retail Item Availability* for every store. Ask for them only where your app may mark every store's items.

## Tell the customer
Each station sees on its screen what the tills sent, as the printed ticket shows it; the cooks tap a dish through and the board shows the guests whose order is ready. The printers keep printing, so a kitchen still works when the screen or the network is down.
