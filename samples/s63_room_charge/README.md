# S63 — Room charge (`pp_rmc`): a hotel's restaurant charging a meal to a guest's room

A hotel's restaurant or bar puts a meal on the guest's room. The server types the room and surname on the check, a wrong room is stopped at Pay, and the charge reaches the guest's folio within about a minute. A night auditor reads one list of what was posted, what is waiting and what was refused.

**Industries:** Hospitality

**When to use it:** any restaurant, bar or room service in a hotel whose hotel system can find a guest and take a charge. It also shows a check that fills a sale detail, and a worker that posts once per sale with no state of its own.

## Start from it

```bash
ivn new acme_rmc --from s63
```

## What to change

- **The hotel system:** add your own file beside `service/hotel_mews.py`, the reference, and name it in `service/hotel.py`.
- **The rules:** `service/rooms.py` (what the check answers, what one sale owes the folio).
- **The post:** `service/worker.py`.
- **The app's id:** `IVN_LIBRARY_APP` in `app.json`.

More: the [recipe](../../recipes/room_charge.md).

**The customer sets:** the *Room Charge* mode and its clearing account first (the restaurant docs show how), then one row per store on *PP RMC Settings*: hotel system, connection, charge code, tip code.

**The app's role needs:** nothing from the retailer's administrator. The install makes *PP RMC Integration* and the app's own user, and gives the role read on POS Invoice, which the feed follows. Give the night auditor the role *PP RMC Auditor*.

**Who carries the hosting plan's charge:** the app is free to install. Its one-minute schedule needs a hosting plan, and whoever hosts the app carries that plan's charge.

## Run it

```bash
ivn check
ivn try
```

To run the whole flow with no network, start the stand-in hotel system and pick *Simulator* on the store's row:

```bash
python3 standin/hotel_api.py
```

## Try it at the till

- Open *Sale details*, type **412** and **Smith**, and press Pay: the Folio is filled.
- Type **412** and **Brown** instead: the Room Charge tile is dimmed, with the reason.
- Take it on Room Charge; within a minute the *Room charges* workspace shows it as *Posted*.
- Close the till day when you are done.

## Versions

### 0.1.0

- First version in the kit: the check at Pay, the post to the folio, the auditor's workspace, the Mews adapter and a stand-in hotel system.
