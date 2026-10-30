<!-- Source: ivendnext/iVendNext_PWA docs/extending/station_ticket.md @ c39b1449937a, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Station ticket — the kitchen's tickets on a kitchen screen (`station_ticket/1`)

**Who this is for:** a partner building a kitchen display (a screen per station, an expo screen, a
*Now serving* board) on iVendNext POS, and the AI assistant working with them.

**Status of this version:** read a station's tickets, move each one started, ready and bumped, and be
told within a second when the board changed; mark an item sold out at the store. Tickets come from a
till's *Send* (a counter sale's or a table's check). A Sales Order as a ticket source is a later version.

---

## 1. What it is and when it fires

When a till presses *Send*, each kitchen station gets its own ticket: the dishes, their choices, notes,
the guest and course on a table's check, the allergen line, and the place or the call number. The
station's printer prints it. This door lets your kitchen screen read the same tickets and answer them:
*started* (a cook took it), *ready* (it is on the pass), *bumped* (it left). The shop's tills are not told
anything new by your screen in this version.

The kitchens and which item goes to which one are set up in iVendNext Desk (**Kitchen Stations**, on the
item, its item group or the register). A ticket is written only when the station has a printer on the
sending till: a station your screen serves still needs a printer that takes the ticket (§6).

## 2. Version

`station_ticket/1`. The names below are a contract: once published, a name keeps its meaning.

## 3. The calls

Each is a call on the partner API, `/api/method/ivendnext_mpos.api.v1.<name>`, under the rights of the
user your app signs in as.

**`station_tickets(store, station?)`** (`GET` or `POST`) answers the station's board now (every station's
when you name none): every ticket sent in the last 12 hours that is not bumped, and those bumped in the
last 30 minutes (so a cook can recall one), oldest first.

```json
{"store": "Main Store", "station": "Grill", "as_of": "2026-10-29 19:42:10.120331",
 "event": "mpos_station_ticket",
 "tickets": [{"kitchen_order": "a1b2c3d4e5", "ticket": 3, "station": "Grill", "kind": "send",
   "source": "check", "call_number": "Table 12", "service_mode": "Dine In", "till": "Till 2",
   "sent_at": "2026-10-29 19:41:58.004211", "state": "new", "state_at": null,
   "lines": [
     {"item_code": "BURGER", "item_name": "Burger", "uom": "Nos", "qty": 1, "note": "no onions",
      "under": null, "guest": "2", "course": "Mains", "allergens": "Allergens: sesame, gluten"},
     {"item_code": "CHEESE", "item_name": "Extra cheese", "uom": "Nos", "qty": 1, "note": "",
      "under": 0, "guest": "2", "course": "Mains", "allergens": ""}]}]}
```

- `kind` — `send` (make it) or `void` (a manager voided a line the kitchen had: stop making it). A void ticket
  names the dish by its item, quantity, guest and course on the same `kitchen_order`; it carries no link to the
  ticket it cancels. Show it, let the cook strike the dish, then bump it like any ticket.
- `source` — `sale` (a till's counter sale) or `check` (a table's or a tab's check).
- `call_number` — a sale's call number, or a check's place or tab name, as the order's last send named it: a
  check moved to another table shows its new place from its next send, on every ticket of that order.
- `under` — a choice's dish, by its position in this ticket's `lines`; `null` for a dish.
- `guest`, `course` — a check line's; empty on a sale.
- `allergens` — the Item fields the store's receipt theme shows for that item, as the printed ticket
  carries them; empty when the theme shows none.
- `state` — `new`, `started`, `ready` or `bumped`; `state_at` is when it reached that state.

A ticket is one station's, numbered per kitchen order: name it by `kitchen_order` **and** `ticket`.

**`station_ticket_move(store, kitchen_order, ticket, state)`** (`POST`) moves one ticket one step:
`new` → `started` → `ready` → `bumped`. The same step again changes nothing and answers
`"already": true` (a double tap is safe). A skip (`new` to `ready`) or a step back is refused. The answer
is the ticket as it now is: `{"ok": true, "already": false, "ticket": {…}}`.

**Sold out** (the kitchen runs out of an item): **`set_item_availability(item_code, warehouse,
sold_out?, sold_out_until?, available_from?, available_to?)`** (`POST`) marks an item sold out at one
store (until a time, or until cleared), clears it, or sets the hours it is sold; a parameter left out
keeps its value, an empty one clears it. **`item_availability(warehouse, item_code?)`** answers the
store's items that carry a rule (or the one you ask for), available now or not and why. The tills stop
selling a sold-out item at once (offline, as at their last sync). ⚠ Unlike the ticket calls, these two are
not fenced to your user's stores: they answer to the item-availability rights for any store, so ask the shop
for them only where your app may mark every store's items.

## 4. Refusals

| `exc_type` | When |
|---|---|
| `TicketStepError` | a skip, a step back, or a state other than started, ready, bumped |
| `TicketNotFoundError` | no such ticket at this store (another store's ticket answers the same) |
| `PermissionError` | your user lacks the right, or has no row for the store (*"You are not assigned to this outlet."*) |
| `DeviceRequiredError` | your user once enrolled a till device: a till's user is never a kit's (use one user per kit app) |
| `ProfileNotAssignedError`, `StoreAssignmentIncompleteError`, `DuplicateStoreAssignmentError`, `AssignedProfileDisabledError` | the user's store row is incomplete, doubled or names a disabled register |

## 5. Who may do what

The shop grants **May Work a Kitchen Screen** in **Retail Permission** (group *Open Checks*) and links that
record to your integration user; anyone with write on Kitchen Stations (System Manager unless the shop
changes it) holds it too. Sold out asks the shop's item-availability rights (write, or read, on
**Retail Item Availability**).

Your user is fenced to its stores and is set up exactly as for the open check: see
[Open check §4](open_check.md#4-who-may-do-what) for the ticks, the store row and *Generate Keys*.
One integration user per kit app.

## 6. Live and offline

After a send, a void or a move commits, each enabled user of the store whose Retail Permission ticks
*May Work a Kitchen Screen* is told
`{"store": …, "station": …}` on the realtime event `mpos_station_ticket` — a notice, never the ticket:
read the board again. Nothing is told for a change that was rolled back. (A user who holds the right only by
write on Kitchen Stations, an administrator, may read and move tickets but is not told.)

**A ticket can leave the board without a bump, and some never reach it.** No notice is sent for these, so read
the board on every notice and every few seconds:
- a `send` ticket the till's own print agent later reports unprinted leaves the board; its dishes come back as
  a new ticket, state `new`, on the next Send of that sale or check (a sale paid with no second Send never
  brings them back). A `void` reported unprinted stays: the void stands;
- a send whose kitchen's network printer refuses or does not answer writes no ticket: a kitchen your screen
  serves needs a printer that takes the job, not only a printer row;
- a void whose kitchen has no printer (on the voiding till's register for a sale; on the register of the check's
  last send for a check), or whose printer is cabled to another till, is not on the board: the manager is told
  at the till, and the kitchen hears it in person.

There is no cursor to lose: every read is the whole board, so a screen that dropped its connection reads
it again and has caught up. Poll the board every few seconds whenever the live connection is down.

⚠ The live connection is the site's own realtime socket, namespace `/<site name>` (for example
`/shop.example.com`), on the site's address. Connect from your server, not from a page on another address,
and send three headers: `Authorization: token <key>:<secret>` (your user's API key), `Origin` = the site's own
address, and a `Cookie` header with any value that carries no `sid` (the socket refuses a connection with no
cookie, and a `sid` would sign in as that session instead of your key). Then listen for `mpos_station_ticket`.
⚠ The site's name is not always its address: a hosted site can answer at one address and carry another name
(a sandbox measured 2026-10-30 answers at its own address and names itself under the hosting's domain), and the
socket then refuses the address with *Invalid namespace*. Read the name once from the site's Desk page (`/app`, with
your key): its boot data carries `"sitename"`. Sample S59's live service (`samples/s59_kitchen_screen/live/`) does both.

A kitchen screen needs the internet: while the store is offline, tills print their tickets on their own
and your screen shows the board as it last read it. ⚠ Those offline tickets never reach the board,
even after the till reconnects: what the kitchen made in the outage is on paper only.

## 7. Money and limits

No money moves through this door; a ticket carries no price. A void ticket is the manager's decision at
the till: your screen cannot void, comp or change a line.

## 8. Two worked examples

**A grill screen.** On start, read `station_tickets(store, "Grill")` and draw each ticket not bumped. On each
`mpos_station_ticket` notice for `Grill`, read again. A cook's tap sends `started`, the next `ready`, the
last `bumped`; a bumped ticket stays in a *Recall* list for 30 minutes.

**A *Now serving* board.** Read every station's board; show each `call_number` whose `send` tickets of one
`kitchen_order` are all `ready` (leave `void` tickets out of the count). When they are `bumped`, take the
number off.

## 9. Telling an AI assistant

"Read `ivendnext_mpos.api.v1.station_tickets(store, station)`; re-read on each `mpos_station_ticket`
notice and every few seconds while the socket is down. Move a ticket with `station_ticket_move` one step
at a time (new, started, ready, bumped), naming `kitchen_order` and `ticket`; `already: true` is not an
error. Never send a price. Validate against `station_ticket.v1.schema.json`."

Contract: [`station_ticket.v1.schema.json`](../extension_contracts/station_ticket.v1.schema.json) ·
samples under `tests/extension_contracts/samples/station_ticket/` · code `business_logic/station_ticket.py`.
