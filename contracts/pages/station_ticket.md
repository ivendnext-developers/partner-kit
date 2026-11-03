<!-- Source: ivendnext/iVendNext_PWA docs/extending/station_ticket.md @ cff85a09aa4d, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Station ticket — the kitchen's tickets on a kitchen screen (`station_ticket/1`)

**Who this is for:** a partner building a kitchen display (a screen per station, an expo screen, a
*Now serving* board) on iVendNext POS, and the AI assistant working with them.

**Status of this version:** read a station's tickets, move each one started, ready and bumped, and be
told within a second when the board changed; mark an item sold out at the store; send a Sales Order (a
call-centre or online order) to the kitchen. Tickets come from a till's *Send* (a counter sale's or a table's
check) and from a Sales Order sent to the kitchen (§3b).

---

## 1. What it is and when it fires

When a till presses *Send*, each kitchen station gets its own ticket: the dishes, their choices, notes,
the guest and course on a table's check, the allergen line, and the place or the call number. The
station's printer prints it. This door lets your kitchen screen read the same tickets and answer them:
*started* (a cook took it), *ready* (it is on the pass), *bumped* (it left). The shop's tills are not told
anything new by your screen in this version.

The kitchens and which item goes to which one are set up in iVendNext Desk (**Kitchen Stations**, on the
item, its item group or the register). A ticket is written only when the station has a printer on the
sending till (for a Sales Order, on the register that prints it, §3b): a station your screen serves still
needs a printer that takes the ticket (§6).

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
- `source` — `sale` (a till's counter sale), `check` (a table's or a tab's check) or `sales_order` (a Sales
  Order sent to the kitchen, §3b). ⚠ `sales_order` was added after version 1 first shipped: a screen that
  validates the board against an older copy of `station_ticket.v1.schema.json` refuses the WHOLE board answer
  while any Sales Order ticket is on it (the screen goes blank), so take this copy before the shop sends orders.
- `call_number` — a sale's call number, a check's place or tab name, or the Sales Order's name, as the order's
  last send named it: a check moved to another table shows its new place from its next send, on every ticket of
  that order.
- `till` — the till that sent it; empty on a Sales Order's ticket.
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
selling a sold-out item at once (offline, as at their last sync). At a store that set its own hours, a sold-out
from head office wins: clearing the store's own mark leaves the item sold out until head office lifts it or its time
ends, and the answer says so. To keep selling under it, send `sold_out` as `0` and both hours empty; the item then
sells all day at that store, and nothing brings the hours back, so send them again once the mark has ended. A mark is fenced to your user's stores like
the ticket calls, through this call and through the record itself (another store's item is refused, *"You are
not assigned to this outlet."*); the read answers any store's items.

### 3b. A Sales Order to the kitchen

A call centre or an online shop records an order as a Sales Order in iVendNext. It reaches the kitchen the way a
till's *Send* does — each station's ticket on its printer and on the board, `source` `sales_order` — and stays what
it is: priced, settled and delivered as Sales Orders are today, never a till's sale or a table's check.

**`sales_order_to_kitchen(sales_order, service_mode?)`** (`POST`) sends the order's lines the kitchen does not have
yet. In iVendNext Desk the same call is the **Send to kitchen** button on a submitted Sales Order, shown only where
the order's store has a kitchen (a register there with Kitchen Printers) and the user holds the right.

```json
{"sales_order": "SAL-ORD-2026-00042", "kitchen_order": "f3e2d1c0b9",
 "results": [{"station": "Grill", "lines": 2, "state": "handed", "ticket": 1},
             {"station": "Bar", "lines": 1, "state": "failed", "reason": "its printer Bar Printer didn't answer"}]}
```

- **Which kitchen.** The order's store is its lines' warehouse (the order's *Set Source Warehouse* fills them); an
  order over several stores is refused. The register whose Kitchen Printers print the tickets is your user's own
  at that store when your user has store rows (then it sends only for those stores, as at the open check, §5);
  a user with no store row — head office, or a call-centre agent working in iVendNext Desk — sends for any
  store, from the store's one running register with Kitchen Printers (a store with several asks for a store
  row: the button does not show there for such a user). Each item goes to its kitchen as at a till. A station whose printer is cabled to a till never prints it
  (there is no till): give it a network printer.
- **Never twice.** A second call sends only what is new: lines added since (amend the order — an amended order keeps
  its kitchen order), and a station whose printer failed. Nothing new is refused. An order a till took in Order mode
  and sent to the kitchen is refused: its lines went from the till (one the till never sent may be sent here). A till
  that later delivers the order sends nothing. Two calls at once send it once.
- **Each line** prints as a dish with its quantity in its unit and the line's *Additional Notes* as its note. A
  choice sold as its own line prints as its own dish.
- **`service_mode`** (optional) is printed when the register lists that mode; otherwise the ticket has none.
- **Answers.** Each kitchen's `state` is `handed` (with its `ticket`) or `failed` with the till's own reason — *"no
  printer is set for it on this till"* and *"… cabled to a till …"* mean the register that prints the order. A line
  whose item has no kitchen fails each time (*"no kitchen is set for …"*) until one is set.
- ⚠ **Bounds:** the order is locked while its kitchens print (up to 5 seconds a printer, one after another), so a
  delivery, an invoice or an *Update Items* of it in that moment waits; an order changed in that instant is refused
  (*"This order was just changed. Send it again."*). A till's order whose kitchen order holds only voided lines is
  refused as one the till sent. A sale paid offline whose printed tickets could not be handed over when it synced
  carries no kitchen order, so its order could be sent here a second time: check the kitchen before re-sending
  such an order. An amended order with less, or a cancelled one, sends no
  void: tell the kitchen. An amendment
  that moves the order to another store sends it whole to the new store's kitchen and leaves the first store's
  tickets: tell that kitchen too. The register's
  item groups are not asked: the order is already priced.

## 4. Refusals

| `exc_type` | When |
|---|---|
| `TicketStepError` | a skip, a step back, or a state other than started, ready, bumped |
| `TicketNotFoundError` | no such ticket at this store (another store's ticket answers the same) |
| `PermissionError` | your user lacks the right, or has no row for the store (*"You are not assigned to this outlet."*) |
| `DeviceRequiredError` | your user once enrolled a till device: a till's user is never a kit's (use one user per kit app) |
| `ProfileNotAssignedError`, `StoreAssignmentIncompleteError`, `DuplicateStoreAssignmentError`, `AssignedProfileDisabledError` | the user's store row is incomplete, doubled or names a disabled register |
| `SalesOrderKitchenError` | `sales_order_to_kitchen` only: no such order (*"No Sales Order named …"*); the order is not submitted, on hold or closed; its lines name more than one store, or none; a till took it and sent it to the kitchen; it has nothing new for the kitchen; or, for a user with no store row, the store has no register with Kitchen Printers, or several (*"Send it as a POS user assigned to the one that prints orders."*) |

## 5. Who may do what

The shop grants **May Work a Kitchen Screen** in **Retail Permission** (group *Open Checks*) and links that
record to your integration user; anyone with write on Kitchen Stations (System Manager unless the shop
changes it) holds it too. Sold out asks the shop's item-availability rights (write, or read, on
**Retail Item Availability**); a mark also needs your user's row for that store. A user with no store
row at all is the shop's head office and marks every store, so give your app's user its store rows.

**Sending a Sales Order** asks the shop's own right to take one: **submit on Sales Order** (the Sales User role
gives it), plus a read of that order. A user with store rows sends only for those stores; one with none sends for
every store (§3b).

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
`/shop.example.com`), on the site's address. A hosted site's name can differ from its address: if the socket
answers *Invalid namespace*, read the name once from `/app`, signed in with a Desk user's key, whose page source
names it as `"sitename"`. Connect from your server, not from a page on another address, and send three headers: `Authorization: token <key>:<secret>` (your user's API key), `Origin` = the site's own
address, and a `Cookie` header with any value that carries no `sid` (the socket refuses a connection with no
cookie, and a `sid` would sign in as that session instead of your key). Then listen for `mpos_station_ticket`.

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
error. Never send a price. To send a call-centre or online order, call
`ivendnext_mpos.api.v1.sales_order_to_kitchen(sales_order)` after the Sales Order is submitted; call it again
after the order is amended — it sends only what is new. Validate against `station_ticket.v1.schema.json`."

Contract: [`station_ticket.v1.schema.json`](../extension_contracts/station_ticket.v1.schema.json) ·
samples under `tests/extension_contracts/samples/station_ticket/` · code `business_logic/station_ticket.py`.
