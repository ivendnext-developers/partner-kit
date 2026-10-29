# Front of house: reservations, a waiting list and seating that opens the table's check — the recipe

A restaurant's host takes bookings on the phone, keeps walk-ins waiting in order, tells a party its table is ready and seats it. The till already keeps a table's running order (the open check) and the floor's tables; what it does not keep is the evening before the party sits down. This recipe gives the host a diary of bookings and a waiting list in iVendNext Desk, holds a table against two bookings at once, records a no-show, ties a booking to the sale that took its deposit, and seats a party by opening its table's check through the till's open-check door, so the server finds the table on the floor with the party's size.

**Reference implementation:** `samples/s55_front_of_house/`.

**When to use it.** A store with *Table Service* on its register (full service, a bar that takes bookings, a hotel's restaurant). The tables are the till's own floor: *Retail Floor Section* and *Retail Floor Place*, set up in Desk. A deposit is the till's own customer advance. A booking platform or a messaging provider of your own comes on top (*Make it your own*, below).

**The four rules, here.** No code runs inside the retailer's iVendNext. One address is called, your service, and only when the host presses one of the buttons. The service opens a check only through the till's door (`check_open`), as the app's own user, with the two rights front of house asks for: *open a check* and *see the checks*. A guest's name, phone, customer and notes are fields only the host role reads, so they never reach your service.

## What the host and the server see

| | |
|---|---|
| A reservation: the store, the date and time, the party, the guest, the table; **Book**, **Seat**, **No-show**, **Cancel booking** | *(pictures follow the walk on a demo site)* |
| The waiting list: walk-ins in the order added; **Table ready** sends the guest an SMS; **Seat** | |
| The till's floor: the seated party's table, its check open with the party's size | |

## Steps

### Settings

1. Install the manifest. It adds the settings (one per company, with a row per store), the reservation, the waiting-list entry, *Guest notes* on Customer, the roles **PP FOH Host** and **PP FOH Integration**, four buttons and their services (off), and the feed registration that makes the app's own user (`pp_foh@integration.invalid`, from POS 2.1.0.667; leave the feed off).
2. Give the app's user its store and its key, in this order, on its User record: keep *Is Desk User*, tick **Is POS User**, choose a **Shift Profile**, link a **Retail Permission** with *Open Checks*: **open a check** and **see the checks** only; add one row to the store access table (the store and its register, *Table Service* on); **Save**; then **Generate Keys**. Without *Is POS User* the save drops the store row and the till answers *"You are not assigned to this outlet."* Never give it write on *Floor Section*: that is every check verb, a comp included.
3. On **PP FOH Settings**, one row per store: **the same register** the app's user holds there, the usual booking length (90 minutes to start), whether a table with an open check may take a second check, and the **No-show deposit** rule (*Keep it* or *Return it*).
4. Give **PP FOH Host** to the hosts and managers; consent to the four services and switch the five buttons on; press **Connect again** on the app's package record if the site could not reach the app.

### Reservations

5. The host makes a reservation and saves it: it reads **Requested**. **Book** holds its table: no other *Booked* or *Seated* booking of that table may overlap it, each from its start for its length (a booking running past midnight included). A clash is refused with the other booking's number and time, and the reservation stays *Requested*. Change the time, the length or the table after *Book*, and press *Book* again.
6. **Seat** opens the party's check at its table: the table must not be booked for someone else within the party's stay, and must have no open check (unless the store's row allows a second). The check carries the party's size, the booking's number as its reference (`source_ref`) and label, and the deposit's amount when it took one; it has no server until the first till writes to it. The reservation reads **Seated** with the check's number.
7. **No-show** marks it a no-show and writes the store's deposit rule on it; **Cancel booking** frees the table.

### Waiting list

8. The host adds a walk-in: the party, a name and phone, the wait quoted. Setting **Table ready** sends the guest an SMS through the retailer's own **Notification** (on *PP FOH Waitlist Entry*, *Value Change* on *Status*, the condition `doc.status == "Table ready" and doc.phone`, channel *SMS*, the receiver *by document field* `phone`; **SMS Settings** set to the retailer's provider). **Seat**, with a table chosen, opens its check as for a booking.

### A deposit

9. The cashier takes the deposit at the till as the guest's advance (*Customers*, *Take a payment*); the host names that sale on the reservation, which shows its amount. Nothing applies an advance when the table pays: at the table's payment the cashier puts the guest on the sale and charges the deposit's part *On account* (the guest needs a credit limit), the rest as usual; the accountant then allocates the deposit's Payment Entry to that invoice in **Payment Reconciliation**.

## What the retailer does

Day to day the host presses four buttons and the server works the table at the till as before. The app never adds a dish, moves, merges, closes, voids, comps or prints a check, and never takes a payment: those are a person's decisions, at a till.

## Limits

- The guard runs when *Book* and *Seat* are pressed, never on a plain save: a booking changed after *Book* is checked again only when *Book* is pressed again.
- Nothing marks a booking late by itself; the host presses *No-show*.
- At a table the floor names a check by its place, so the booking's number and deposit are read on the check, not the floor tile.
- A check moved or merged at a till after *Seat* keeps its first number on the reservation.
- Opening a check needs a connection: nothing here works offline.

## Technical notes

- **One check per press, even when an answer is lost.** The service writes a fresh key (a UUID) and the exact call on the record **before** it calls `check_open`, and sends the same call again when a press finds them there: the door returns its first answer for the same key and arguments, and writes nothing twice. Two presses at once meet the record's own `modified` check: the loser takes the winner's key. A refusal (a door error the till answered) clears the key, so the next press starts afresh; a lost answer keeps it.
- **No guest data leaves.** The guest's fields carry `read_roles` and `write_roles` of *PP FOH Host* and System Manager (the field limit of POS 2.1.0); the app's own role is not among them, so the record API leaves them out of every answer to its user. The Desk button sends `name` only. The call that opens the check names no `suggested_customer` and no `server`.
- **The status is the app's.** The reservation's status and the app's own fields carry `write_roles` of the app's role and System Manager: a host cannot set *Booked* without the guard.
- **One press at a time per company.** *Book* and *Seat* stamp the company's settings with the shop's own `modified` check while they read the table's bookings, so two hosts never hold one table twice; a stamp older than a minute has lapsed.
- **Refusals in the host's words.** The till's refusals come back by their stable codes (`ProfileNotAssignedError`, `TableServiceOffError`, `PermissionError`, `CheckRequestError`) and the service answers with what to fix.

## Make it your own

A partner usually adds a booking platform's link (its bookings written as reservations through the record API, the guard pressed by the service), the retailer's SMS provider (SMS Settings, never the app), a reminder Notification before a booking, and the store's own deposit words. Start with `python3 tools/manifest/start.py s55_front_of_house --prefix "ACME FOH"`.
