# Age-restricted sale check — the recipe

Alcohol, tobacco, vapes, knives and some medicines may be sold only to customers of a certain age, and the age differs by item and by country. This recipe adds an age check from outside, with two extension points working together. At the **scan** of a restricted item, your service shows the cashier the date of birth to compare with the customer's ID and records the check on the sale with one tap. At **Pay**, it refuses a restricted line that the recorded check does not cover. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** `samples/s37_age_check/` — *Age-restricted sale check*.

**When to use it.** A rule that the cashier must see at the scan **and** that must hold when the sale is paid. A capture on scan shapes the cashier's flow, but it is not a booking gate: an item picked from a list is never asked about. The check before payment is the gate. A value the scan's answer puts on the sale (a sale detail) is how the scan tells the check what the cashier confirmed.

## Steps

1. **Declare, in your manifest** (`samples/s37_age_check/manifest.json`):
   - **a sale detail** `<PREFIX> ID Checked` (`sale_attributes`). ⛔ Never `required`: a required sale detail stops every sale on every till of the site, and the installer refuses one;
   - a settings record type `<PREFIX> Settings` (the record `Default`): the shop's hours from UTC (for the date shown) and its *ask for ID if they look under* policy. Give **System Manager** the rights to edit it and your integration role **read only**; name the role `<PREFIX> Integration`, so the install makes it;
   - **a whole-number field on Item Group and on Item**, *Customers must be at least this old*;
   - a `capture` subscription with `"settings": {"event": "scan", "item_field": "<prefix>_min_age"}`: the till asks your service only about an item whose own age is set (a whole number 0 is no value). The shop adds its restricted groups to the same settings (`"item_groups"`): a liquor store's catalogue is too large for an item field (the filter's field may be set on at most 2000 items);
   - a `check` subscription, at the same address's other route; that one address (one origin) alone in `allowed_urls`;
   - a feed registration naming your one integration user, so the shop's *Connect again* hands that user's key to your service;
   - a help address on the settings record type (a `documentation` property setter).

2. **Choose what happens when your service is down.** The sample declares `allow_and_flag` on both: an outage never stops a shop selling, and each scan or sale it could not check is flagged on *Sales to review*. A shop can change the **scan** service to `refuse`: a restricted item **scanned** while the service is down or the till is offline then cannot be added, but an item picked from a list still goes on, flagged. Only the check's `refuse` stops every unchecked sale, and it stops every sale on its POS Profiles, restricted or not, while the service is down (offline the check is not called).

3. **Check every call with its own route's secret** (`<app>:sub:<key>`; the sample's keys are `scan` and `check`), and refuse a timestamp more than five minutes from yours.

4. **Work out each item's age.** Read the item groups once a minute (`GET /api/resource/Item Group`, `fields` `name`, `lft`, `rgt` and your field, `limit_page_length` 0) and the items' own ages with `variant_of` (`GET /api/resource/Item`, `filters` `[["name", "in", [...]]]`). An item's age is its own when above 0; else its template's (⚠ a variant does not inherit a field its template gained later: the shop copies only the fields its *Item Variant Settings* list, so read the template in a second step); else the nearest group above it (itself first) with one: the group whose `lft`/`rgt` contains the item's group, with the largest `lft`. The shop gives your role a plain **read on Item Group and Item**.

5. **Answer the scan** (`capture/1`, event `scan`), within the scan's 1.5 seconds:

   ```json
   {"verdict": "notice",
    "message": "WHISKY-70: customers 18 or over. Born on or before 22 Oct 2008. Ask for ID if they look under 25.",
    "sale_attributes": [{"sale_attribute": "PP AGE ID Checked", "attribute_value": "18 or over"}]}
   ```

   The till opens one sheet: your label, your sentence, *"This will be added to ⟨item⟩:"* and the value. **Add with these details** adds the item and puts the value on the sale; **Don't add it** adds neither. The date is the shop's today (UTC plus its hours) that many years back. An item with no age: `{"verdict": "allow"}`, nothing shown.

6. **Ask once a sale.** Remember, per shop and per the scan's `sale_ref`, the highest age you asked about, and answer `allow` to a later scan of that sale needing that age or less. The till does not tell you what the cashier answered, so a check you remember may have been refused at the sheet: the check at Pay catches that. The reference is empty on a sale's first scan; remember nothing for it.

7. **Answer the check** (`check/1`) at Pay. A sale with no line of a positive quantity is a refund: allow, reading nothing. Otherwise read the sale detail `<PREFIX> ID Checked` in `sale_attributes` as a whole age alone (*18 or over*, *18*, *18+*; anything else, a date of birth typed in included, is 0), and find the lines the sale sells whose age is above it. None: allow. Else refuse, naming the highest age needed and its first line:

   | The sale | Answer |
   |---|---|
   | no check recorded | `{"verdict": "refuse", "reason": "Line 2: WHISKY-70 is for customers 18 or over. See their ID, then enter 18 in Sale details, or take it off."}` |
   | a lower check | `{"verdict": "refuse", "reason": "Line 3: VAPE-01 is for customers 21 or over; the sale's ID check says 18. See their ID, then enter 21 in Sale details."}` |

8. **When the shop cannot be read,** answer 503, so the till applies your down answer: no answer, an error answer (a refused key included), an answer cut short, not records, or an item the shop does not return. Never follow a redirect with the key.

9. **Test it.** The sample's tests: each item's age through the tree, the date of birth (the shop's own day, 29 February), the scan's answer, the check's refusals and the recorded check, a return, the remembered asks, each route's secret, one shop and many, every answer against both contracts; `canaries.py` breaks each guarded rule and expects its test to fail. Then scan a restricted item on a sandbox and press Pay.

### Settings

The shop's record `Default` of `<PREFIX> Settings`: *Hours from UTC at the shop* (4 for Dubai, 3 for Nairobi or Riyadh, 2 for Johannesburg, −6 for Mexico City; a value past ±14 reads 0) and *Ask for ID from anyone who looks under* (such as 25; 0 or blank: *See their ID.*; shown only on an item whose age is lower). On each restricted Item Group, *Customers must be at least this old* (it covers every group below unless a group below sets its own; 0 is none of its own, so the group above applies: a group under a restricted one cannot be made free of age); on an Item whose age differs from its group's, the same field (on an item with variants, on each variant or on their group). A change reaches the service within a minute. On the scan service (*Age check*), add the restricted groups to its settings as `item_groups`.

**What the cashier does.** The cashier scans a restricted item, reads the date of birth on the sheet, checks the customer's ID, and taps **Add with these details**, or **Don't add it** when the customer is too young or has no ID. At Pay, a refusal shows *"This sale can't be paid"* and the app's sentence: the cashier checks the ID and types the age in the basket's **🗒 Sale details**, or takes the item off, and presses Pay again.

## What the shop needs from you

| You give | The shop checks |
|---|---|
| an **HTTPS** address its server trusts | the address is consented; a private address is refused on a customer's site |
| a settings record type, two fields and a sale detail, by manifest | the installer makes them and removes them at uninstall (the sale detail is kept, switched off, once booked sales name it) |
| a signature check on every call | — (yours to do) |
| an answer within each subscription's time (the sample: the scan 1.5 s, the check 3 s) | your declared down answer applies otherwise |

## Technical notes

- **No personal data is collected:** no date of birth, no ID number. The record is the age band the cashier confirmed. A shop that must log more needs a partner's version, and a data-protection reading of its own.
- **A notice** reaches POS build 2.0.0.654 and later. An older build refuses it as an unknown answer and applies the scan's down answer: the item goes on, flagged, and the check at Pay still holds.
- **A group under a restricted group cannot be exempted** (0 means *the group above applies*); move it out of the group.
- **Two ages on one sale:** the till keeps one value per sale detail, merged by name, so a later, lower ask replaces a higher one. That happens when the higher item was the sale's first (no reference to remember) or another running copy of your service answered the second scan. Pay then names the higher age to enter.
- **One scan service per POS Profile:** where another app already answers the scan (*Till guard rules*, *Warranty capture*), *Age check* cannot be switched on for that profile; switch on *Age check at Pay* alone there, and the cashier enters the age in Sale details when Pay asks. A POS Profile also holds at most three checks before payment, 10 seconds together (this one takes 3 s; 4 s on CitiXsys hosting).
- **One time zone and one age per group for the whole site;** a per-store value is a partner's version (the calls carry the store).
- **After an update of the app,** the shop checks that the scan service's settings still name its groups.
- **Offline,** the till does not call you: each down answer applies. The scan's filter travels with the till's start of day.
- **Where the check never runs:** a park to a till, a layaway deposit, an account collection (the check page, *Not in this version*), nor a sale rung in the Desk's own POS screen.
- **Not in this version:** a manager's override of a refusal, restricted selling hours, an ID scanner, and a verified age kept on the customer. Each is a partner's version ([Make one of our apps your own](make_it_your_own.md)).
- **Hosting:** the service is the app template's shape, so it serves many shops through the template's handshake (guide chapter 14b); each shop's site hands over the two secrets when it connects after the install, and its integration user's key on *Connect again*. It only answers presses, so on CitiXsys hosting it runs as a function, paid per call (`app.json` `"runs": "function"`). Until a shop's user key arrives the service answers 503, so your down answers apply.

### What was proven where

- **On the laptop:** the sample's tests and canaries (its README says how to run them).
- **On our test bench** (2026-10-22, the iVendNext POS app at `84185344` (the programme's own clone the bench mounts), the engine at `dc65d832`; the service in its one-shop form, reading the shop with a user holding only the app's role and a read on Item Group and Item; the shop's settings UTC+2, *ask for ID if they look under* 25; a group *Alcohol* at 18 with a whisky in a group below it, *Vapes* at 21, and a knife with its own age 18 in a group of none; the scan service naming Alcohol and Vapes), **11 of 11** through the till's own calls (the scan, the check, the card push, the booking) inside one day that was closed after: the whisky's scan answered with the date of birth and *18 or over*, on the sale's first scan and again once the sale had its reference · the same sale's next whisky not asked again · a vape on that sale asked at 21 · the knife asked by its own age · a plain item, and a whisky picked from a list, calling nobody · Pay on a whisky with no check refused in the app's words, the card push refused, no sale booked · a whisky with *18 or over* allowed and booked with the check on the sale · a whisky and a vape with *18 or over* refused naming the vape and 21 · the same basket with *21* typed in Sale details allowed and booked · a plain item booked with no check · the calls the till sent hold the published contracts. Before the scenario, each read the service makes was made as the app's user and none was refused. The install, the uninstall (the schema as found; the sale detail kept, switched off) and the rights put back were checked too, and no POS day was left open. **In a browser** on that bench: as a System Manager with Item Manager, the settings record (a change saved), the age on an item group and on an item (a change saved); at the till as the cashier (`/pos?frame=terminal`, 1440 wide), a whisky scanned showed the *Age check* sheet and went on with *Add with these details* (*Sale details · 1 recorded*), a vape picked from the catalogue went on with no question, Checkout was refused (*"Line 2: PPAGE-VAPE-01 is for customers 21 or over; the sale's ID check says 18. See their ID, then enter 21 in Sale details."*), and with 21 entered in Sale details the payment screen opened; the sale was voided.
