# Open a table's order from your app (open check) — the recipe

A restaurant's guests are seated by a reservations app, or order from a QR menu at the table or a kiosk. The **open check** door lets your app open the table's running order and add what the guest chose; every till of the store sees it at once, and the cashier takes the payment when the table pays, priced by the shop with every promotion and tax. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, building one. It needs POS version 2.1.0.667 or later.

**Reference:** the open check page, [`contracts/pages/open_check.md`](../contracts/pages/open_check.md) (every call, right and refusal), and its contract [`open_check.v1.schema.json`](../contracts/extension_contracts/open_check.v1.schema.json) with its samples. There is no kit sample yet.

**The four rules, here.** Your app's code never runs inside the retailer's site: it calls the shop's own functions through `ivendnext_mpos.api.v1`. **A check never holds a price:** your app sends what was ordered, and the till prices it when it is paid.

## Before you start (the retailer's administrator)

1. Ticks **Table Service** on the POS Profile of each register that serves tables.
2. Sets up the floor in iVendNext Desk: **Floor Sections** (the terrace, the bar) and their **Floor Places** (Table 12, Seat 3).
3. Gives your app's user the store and **one register at it** on its user record (the store assignment, with that register's POS Profile): `pos_profile` in every call is that register, Table Service must be on there, and the check rings that register's service mode. The user is your app's own (`<app>@integration.invalid`, made by the install when your manifest has an event feed) or an integration user made for your app; ⛔ never a user that has signed in to a till device (refused, `DeviceRequiredError`). Its key reaches an app hosted by CitiXsys from the site itself after the install or an update; for an app you host yourself, the retailer makes it with *Generate Keys* on that user. ⚠ The product's own walk of this door set its integration user's key by hand, because the save *Generate Keys* makes was refused on that user: if it is refused on yours, report it with a *Kit defect* issue (`feedback/`).
4. Grants that user its rights in a **Retail Permission** (group *Open Checks*) linked to it: *open a check* and *see the checks* for a reservations app; *add to a check* as well for guest ordering. Ask for nothing else: moving, merging, closing, sending to the kitchen, voiding and comping are a person's decisions at the till.

## Steps

Every call is `POST /api/method/ivendnext_mpos.api.v1.<name>` with your app's key (`Authorization: token <key>:<secret>`).

1. **Read the floor:** `floor_status(store)` answers the store's sections, its places with their status (*free*, *seated*, *ordered*, *paying*) and its tabs.
2. **Open the check:** `check_open(store, pos_profile, key, place?, label?, covers?, source?, source_ref?, suggested_customer?)`, with a `place` (a table's id) or a `label` (a tab or a pre-order, such as *Order 42*). It answers the check at version 1.
3. **Add the guest's order:** `check_add_lines(check, lines, key)`, each line `{item_code, qty?, uom?, options?, note?, seat?, course?}`. A dish's choices go in `options` as `[{"item_code": "OAT-MILK"}]` and are checked against the item's choice groups when the line is added.
4. **Show the guest a price, if you need one:** `check_preview(check)` answers the shop's price of the open lines (`rows` and `total`). It is never stored: the bill is priced again when it is paid.

Staff send each round to the kitchen from a till (*Send*); your app does not ask for that right.

**The `key` rule.** Each press of your app's button sends a fresh random `key` (a UUID), never one built from an order number or a table. When an answer is lost, send exactly the same request again with the same key: the shop answers with its first answer and writes nothing twice. The same key sent for another check, or with other arguments, is refused.

**The `version` rule.** Opening and adding need no version. A call that changes what is already on a check (a right the retailer gives a person, not usually your app) carries the `version` of the check or line you last read; when someone changed it since, it is refused (`CheckChangedError`): read the check again with `check_get`.

## What is refused

- A line with a `rate`, `price`, `amount` or `discount` key, or a `concession_note`.
- Paying, claiming or printing a check (`check_claim`, `check_release`, `check_note_pending`, `check_clear_pending`, `check_break_claim`, `check_print`): a till's only, whatever your app is granted.
- A manager's sign-in sent by your app: *"A manager approves this in person, at a till."*
- A write to a check's records through `/api/resource/…` (`WrittenOutsideDoorError`).
- Opening, adding, moving, merging or splitting while the register's Table Service is off (`TableServiceOffError`); a removal, a close of an empty check and the reads still work.
- A call whose `pos_profile` is not your user's register at that store (`ProfileNotAssignedError`), or from a user with no store assignment there.

## Limits

- Online only: nothing here works offline.
- A weighed line on an open check is refused at Pay until a later POS version.
- What your app reads back carries no staff identity, no register and no server's note.
- The door tells one app's user from another, never one guest from another: which guest may see which check is your app's job, and each app has its own user.
