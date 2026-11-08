# Room charge: a hotel's restaurant or bar charging a meal to a guest's room — the recipe

A guest at the hotel's restaurant signs the bill and says "put it on my room". The till needs one tile for that, and the hotel needs the charge on the guest's bill. This recipe ties the two together, and works with any hotel system that can find a guest and take a charge.

**Reference implementation:** `samples/s63_room_charge/`.

**When to use it.** A restaurant, bar or room service in a hotel whose till is iVendNext and whose hotel system is someone else's: Mews, OPERA Cloud, Cloudbeds or your own. A hotel with no link needs no app: the tile alone, in the [restaurant docs](https://docs.ivendnext.com/docs/hospitality/charge-a-meal-to-a-room), and the auditor types each charge in by hand.

**The four rules, here.** No code runs inside the retailer's iVendNext. The tile is the retailer's own *Custom* mode of payment. Your service answers the check at Pay, and reads the event feed after the sale; it writes only to its own record type. It never changes a price, a total or a payment.

## How it works

1. The server types **Room** and **Guest** (the surname) on the check's *Sale details*, and any **Tip**.
2. At **Pay**, the check asks the hotel system for that guest. A match answers `allow` and fills the reservation as **Folio**. A room it cannot confirm, or none at all, answers `allow` with the Room Charge tile dimmed and the reason shown, so the guest can still pay by card. The hotel system down with a room typed answers `ask`.
3. The sale books on the *Custom* tile, on its own clearing account.
4. The worker reads `sale.booked`, `return.booked` and `sale.cancelled` from the event feed, and posts the sale's own Room Charge row to the folio.

**The till books first and the folio follows,** within about a minute of the sale booking (two when the shop's worker is busy). On a bad day a charge is booked that the hotel then refuses: it waits on the night auditor's list.

## What a post does

Each sale or return gets one **PP RMC Post** row, *named by the invoice* and written *Sending* before the hotel system is called. A second delivery of the event fails on the name and calls nobody.

| What happened | The row | Why |
|---|---|---|
| The hotel system took it | *Posted*, with a reference per line | |
| The hotel system was down (no connection, a 5xx, a 429) | *Waiting*, sent again each pass | nothing reached it |
| It was sent and no answer came | *Refused*, for the auditor | it may be on the folio: never sent twice |
| The worker stopped mid-call | *Refused*, for the auditor | the same |
| The hotel system said no (a guest who left, a blocked folio) | *Refused*, with its sentence | |
| The sale was cancelled in Desk | *Refused*, reading *Cancelled in Desk* | a posted one also names the folio line to take off |

A **return** posts its own Room Charge row as a negative line, on the sale's folio, and nothing if it has none. The tip stays posted, as the till's own tips do. A return waits while its sale is still *Waiting*, and is refused when its sale never reached the folio.

An **exchange** of a Room Charge sale is refused at the till: the check dims every tender that did not pay the sale, Store Credit with them. Return it and ring it again.

## Steps

1. Make the tile, its account and the register's row: the [restaurant docs](https://docs.ivendnext.com/docs/hospitality/charge-a-meal-to-a-room) walk the hotel's accounts person through it.
2. Install the manifest. It adds the details *Room*, *Guest*, *Folio* and *Tip*, the check, the feed, the records and the *Room charges* workspace.
3. On **PP RMC Settings**, one row per store: the hotel system, its connection, the charge code, the tip code and the mode's name (*Room Charge* unless you named yours differently).
4. Hide the details on themes that are not the hotel's: POS Studio, *Fields*, *Sale details*, *Hide*.

## Add your hotel system

Copy `service/hotel_mews.py` beside it, keep its two calls and add it to `ADAPTERS` in `service/hotel.py`.

| Call | Answers | Raises |
|---|---|---|
| `find(room, guest)` | the reservation's id | `NoGuest` with the sentence the server reads |
| `post(folio, lines, receipt, currency)` | one reference per line | `HotelRefused` · `HotelDown` when nothing reached it · `HotelLost` when it was sent and no answer came |

Read your hotel system's own "do not post" flag: some do not enforce it on the API. The needs cards name what each vendor asks for.

## Limits

- **The tip** is a fourth detail, posted to the folio on the hotel's tip code. The till takes a tip only on a cash or card leg, so iVendNext books nothing for it and its tips report does not see it.
- **The tile is online only,** as the till's Custom tiles are. Offline, the server takes cash or a card, or writes the room on a paper slip for the front desk.
- **The hotel call** is capped at 1.5 seconds, inside the check's 3.
- **The guest's surname stays on the sale** as a sale detail, so the auditor can settle a dispute.
- **The Folio detail** carries the room and guest it was found for, such as `R-1001 (412 Smith)`. A room corrected after the check is looked up again, and never posted to the first guest.
- A store the settings do not name is left alone.
