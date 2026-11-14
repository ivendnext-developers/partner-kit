# S55 — Front of house (reservations, a waiting list, seating that opens a check)

A restaurant's host keeps the evening in iVendNext Desk: a **reservation** for each booking (the store, the date and time, the party size, the guest, a table if chosen) and a **waiting list** of walk-ins. **Book** holds the table for the party's stay and refuses an overlapping booking, naming the other one. **Seat** opens the party's check on the till at its table, once, never twice. **No-show** and **Cancel booking** free the table the booking held, and a waiting party set to *Table ready* can text the guest. Each press writes the next booking of every table at the store on the till's own tables, so the till's floor shows each booked table *Booked* with its time and a server does not seat a walk-in there. A guest's details are seen only by the host role, and the service never reads them.

![Reservations: each booking's date, time, guest, party size and table, the latest date first](screenshots/01_list.png)

For tonight's parties, set *Date* to *Timespan → Today* and sort by *Time*: Desk keeps both for that person. A host who opened *Reservations* before 1.3.1 keeps the old sort until they pick *Date* once in the sort button.

**Industries:** Hospitality

## Start from it

```bash
ivn new acme_foh --from s55
```

## What to change

What a partner usually changes:

- **The booking length and the deposit's words:** `minutes` and `no_show_deposit` on each row of `PP FOH Store` in `manifest.json`; `second_check` lets a long shared table take a second check.
- **The buttons and what they do:** the five services in `manifest.json` and the rules in `foh.py`.
- **A booking platform:** write its bookings as `PP FOH Reservation` records through the record API.
- **A reminder:** the retailer's own Notification the day before; table-ready SMS is a Notification on `PP FOH Waitlist Entry` (*Value Change* on *Status*), never the app.
- **The record types' names:** `FOH_PREFIX` for the service.

More: the [recipe](../../recipes/front_of_house.md).

**The customer sets:** the tables as the till's own floor (*Retail Floor Section* and its *Retail Floor Place* records, with **Table Service** ticked on the store's register), one `PP FOH Settings` record for the company with a row per store, the role **PP FOH Host** for hosts and managers, and an SMS provider if guests are texted. Nothing for the app's user: the install makes it (the manifest's `app_user_rights`): its own Retail Permission with only *open a check* and *see the checks*, **Is POS User**, a row for every store (on its Table Service register if it has one), and a Shift Profile.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- In Desk, make a reservation with a table, press Book, then Seat.
- The party's check opens on the till at that table; add dishes and take the payment.
- The deposit's path was walked with the whole bill put on the guest's account; charging only the deposit's part on account beside a card (a split payment) is the till's own split and was not walked with this app.
- Close the till day when you are done.

## Versions

### 1.3.1

Manifest 0.4.1.

- *Reservations* opens on the latest date first and shows each booking's date beside its time, so a host reads tonight's parties without mixing them with last week's; for one evening, set *Date* to *Timespan → Today* and sort by *Time*.
- *Cancel booking* and *No-show* say the table is free again only when the booking held it: a reservation never booked leaves its table to the booking that holds it. Their prompts now ask *Cancel this booking?* and *Mark this booking a no-show?*.
- Desk shows plain names (*Reservation*, *Waitlist entry*, *Host*, *Front of house settings*) through the manifest's `translations` block. The stored names are unchanged: an installed site keeps its records.

### 1.3.0

Manifest 0.4.0. Needs POS build `2.1.0.697` or later.

- Each press tells the whole store's floor: the service reads the store's tables and its booked reservations once, and writes each table whose next booking changed, usually none or one or two. A booking that ended with no press, one moved to another table in the list, and the day you update all show right at the next press anywhere in the store; there is nothing to press again.
- A booking's time is the store's own. Where the store's Warehouse has a *Time Zone* (the one its receipts print in), the service reads the booking in that zone and writes the floor in the site's time, so a Portland store on a New York site reads a 7pm booking at 7pm. *Seat* checks a booking due within the party's stay on the store's clock too. A store with no zone keeps the site's time, as before.
- `role_rights` give **PP FOH Integration** *Read* on *Warehouse*. On a site that has not updated the app yet, the store keeps the site's time.
- At a store that uses the app, hold a table with a reservation: each press sets every table's *Held From* and *Held To* from the store's reservations, so a hold typed on the table by hand, or written by another app, is cleared at the next press.
- The till shows a booking from the start of its day on the site's calendar. At a store west of its site, a booking late in the evening can fall after the site's midnight (21:30 in Portland is 00:30 in New York): the floor shows it from that midnight.

### 1.2.0

Manifest 0.3.0. Needs POS build `2.1.0.697` or later (the till's tables carry a booking's times).

- A booked table reads *Booked* with its time on the till's floor. *Book*, *Seat*, *No-show*, *Cancel booking* and *Change booking* each write the table's next booking (its start and end, never the guest) on its *Retail Floor Place*, or clear them when it has none. The floor shows it from the start of the booking's day until it ends, and the table still opens.
- Press *Seat* or *No-show* on each booking as the evening goes, so the floor moves on to the table's next booking; one that ends without a press lapses by itself. On the day you update, press *Book* again on the day's booked reservations so the floor shows them.
- `role_rights` give the app's own role **PP FOH Integration** *Read* and *Write* on *Retail Floor Place*. On a site that has not updated the app yet, the press still books, seats or frees as before and says the floor was not told.

### 1.1.2

Needs POS build 2.1.0.682 or later. Manifest 0.2.2.

- The manifest's `app_user_rights` make the app's own user at the install: its own Retail Permission with only *open a check* and *see the checks*, **Is POS User**, a row for every store (on its Table Service register if it has one), and a Shift Profile, so the administrator sets nothing up by hand (a user already set up by hand stays as it is).

### 1.1.1

Manifest 0.2.1.

- The *Seat key* help says what the service does: set when Seat opens the table's check and kept with it, so a second press returns that check; cleared when Seat is refused.
- `role_rights` give **PP FOH Host** *Read* on *Retail Floor Place* and *Select* on *Warehouse*, *POS Invoice* and *Customer*, so a host needs no Role Permissions step.

### 1.1.0

- The set-up words say the install switches the feed on and gives the role its reads (POS build `2.1.0.691` or later). The app does what it did.

### 1.0.3

- *Seat* says what to fix when the till's floor refuses the app's user, for example a user with no register at that store: *"Not seated: the app's user is not assigned to register …"*. Before, the host read *did not answer in time*.

### 1.0.2

- When iVendNext refuses one of your service's calls, or does not answer it, the press's line in your service's log says which call, and iVendNext's status and own words when it gave them (for example *Could not find Company*). The host still reads *did not answer in time*; the cause is in the log (on CitiXsys hosting, your function's log).

### 1.0.1

- Hosts at different stores no longer wait for each other; *Seat* and *Change booking* ask no confirmation.

### 1.0.0

- First version in the kit: reservations, a waiting list and seating that opens the table's check.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
