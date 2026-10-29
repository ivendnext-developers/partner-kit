# Donation intake with a donor receipt — the recipe

A charity or thrift store takes donated goods in at its door, and the donor often wants a receipt. This recipe gives the retailer the **donation** as its own record in iVendNext Desk: who gave, what came in, which store took it, and a **donor receipt** that holds once it is given; and, when the sorted goods go into stock, the stock entry names the donation. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants a store's donations off paper without code inside the retailer's iVendNext.

**Reference implementation:** `samples/s57_donation_intake/`.

**When to use it.** The store takes goods people give it (clothes, books, household goods), prices and sells them, and keeps no record of who gave what, or writes receipts by hand. Stock is already the engine's: the sorted goods go into stock with a Stock Entry of type **Material Receipt**, at the valuation the store chooses.

**The four rules, here.** No code runs inside the retailer's iVendNext. No address is called: the app is a manifest of records, a workflow, a lock, a print format, a report and one field on Stock Entry. It reads and writes no money and no stock, and its receipt states no value. Its only message to a donor is the retailer's own Notification, which sends through the retailer's own mail server.

## What the store sees

1. **At the donation door.** Store staff open **PP DON Donation** in Desk and press **+ Add**. A donor who is one of the retailer's customers is chosen as the **Customer**: its **Customer name** and **Customer's e-mail** show, read only. Any other donor's name is typed as the **Donor** (and the phone and e-mail, if given); a donor who gives no name is left blank. **Donor's address** if the donor wants it on the receipt. **Received at** (the store) and **Received on** (today). One row per kind of goods under **The goods**: **Kind of goods**, **What it is**, **How many**, **Of** (*Items*, *Bags*, *Boxes*), **Condition**. Saved, it is numbered `DON-00001` and is **Received**.
2. **The receipt.** **Give receipt** ticks **Receipt given**. **Print**, format *PP DON Donor receipt*: the receipt under the store's letter head. From now on the donor, the store, the day and the goods cannot change.
3. **A mistake.** **Cancel**: by store staff while the donation is **Received**, by a store manager once its receipt was given. A cancelled donation keeps its number and prints as no receipt; the store never deletes one.
4. **Into stock.** The Material Receipt that takes the sorted goods into the store names the donation in its **Donation** field.
5. **What came in.** The report **PP DON Donations** lists every donation not cancelled, newest first.

## Donations

The record type `PP DON Donation`, numbered `format:DON-{#####}`, tracked (its history shows who changed it and when):

| Field | What |
|---|---|
| `customer` | the customer, when the donor is one; optional |
| `customer_name`, `customer_email` | read only, `fetch_from` the customer's `customer_name` and `custom_email` (the field the till's new-customer sheet and customer edit write) |
| `donor_name`, `donor_phone`, `donor_email` | typed, for a donor who is not a customer; none required |
| `donor_address` | text, printed on the receipt |
| `store` | **Received at**, a Warehouse; required |
| `received_on` | **Received on**, today by default; required |
| `goods` | child table `PP DON Goods`: `category`, `description`, `quantity` (a whole number, 1 by default), `unit` (Items, Bags, Boxes), `condition` (blank, Good, Fair, For recycling) |
| `notes` | text, never printed |
| `receipt_given` | a read-only tick *Give receipt* sets; a Notification reads it, the receipt never does |

**Sales User** and **Sales Manager** read, write, create and print donations; only **System Manager** deletes one; **Stock User** reads them, so the Stock Entry's **Donation** field can find one. The donation shows under the Customer it names (manifest `links`).

## The workflow and the lock

| State | Sets | Who edits |
|---|---|---|
| Received | — | Sales User |
| Receipt given | `receipt_given` 1 | Sales User |
| Cancelled | — | System Manager |

The actions: **Give receipt** (Received to Receipt given, Sales User), **Cancel** (Received to Cancelled, Sales User; Receipt given to Cancelled, Sales Manager).

A **save rule** of kind `locked_in_state` (`save_rules`) refuses any change to `customer`, `donor_name`, `donor_address`, `store`, `received_on`, the `goods` rows and `receipt_given` once the donation was saved **Receipt given** or **Cancelled** (the save that moves it there may still change them), at every save: Desk's form, an import and the record API alike, with the message *"The receipt was given: the donor, the store, the day and the goods stay as on it. Cancel it and take a new donation instead."* (A workflow's *who edits* and a read-only field are only the browser's rules; the lock is the save's. `customer_name` is not locked: it is fetched again at each save, so a lock on it would refuse every later save after the customer is renamed.)

## The receipt

The print format *PP DON Donor receipt* (Jinja) reads only the donation's own fields and its rows. It prints under the store's default **Letter Head**, so the charity's name, registration number and address are the retailer's own: a Jinja print places the letter head itself, `{% if letter_head and not no_letterhead %}<div class="letter-head">{{ letter_head }}</div>{% endif %}` at its top (only Desk's standard layout adds it on its own; measured on the bench, APPF run 22). It reads the donation's step (`workflow_state`), never a tick box the API could set. It prints *Donation receipt · DON-00001*, **Received at** and the day, *From* the typed donor, else the customer's name, else *an anonymous donor*, the address, a row for each line of goods that has a kind or a description (a row with neither is skipped), its count and condition, and the sentence *"Thank you for your donation of the goods listed above. This receipt describes the goods and states no value."* It says nothing about what the store gave back: a store that gives a voucher for a donation says so in its own words (its letter head, or its own copy of the print). A donation not yet in *Receipt given* prints *Not yet a receipt: press Give receipt first.* at the top; a cancelled one, *Cancelled: this is not a receipt.* (the print tests the step's end, `state.endswith(" Receipt given")`, so a renamed prefix still matches).

## Steps

1. **Add the record types above** to your manifest (`doctypes`, the goods table with `"istable": 1`), with no money field: the receipt states no value. Never make the goods table `reqd`: Desk drops a row whose list fields are all blank, so *none* is a donation with no rows. A row whose count and unit have defaults is kept even when the rest is blank, so the print skips a row with no kind and no description.
2. **Add the workflow** (`workflows`), its states and actions under your prefix, *Receipt given*'s tick in `update_field` and `update_value` (a workflow writes the tick as text, `"0"` or `"1"`).
3. **Add the lock** (`save_rules`, kind `locked_in_state`, mode `refuse`), naming the states and every field the receipt prints, and the tick. A lock needs an active workflow on its record type, and installs switched off: the retailer switches it on. It judges the state the record was saved in, so never lock a field the move out of a locked state writes (a *Cancelled* tick would refuse the manager's own Cancel): read the step instead.
4. **E-mail the receipt, with the retailer's own Notification** (a manifest notifies only the retailer's own users). In Desk, **Notification**, **+ Add**: Document Type *PP DON Donation*, Send Alert On **Value Change**, Value Changed **Receipt given**, Condition `doc.receipt_given in (1, "1") and (doc.donor_email or doc.customer_email)` (a bare `doc.receipt_given` would also fire on a text `"0"`), the channel **Email** to the document fields **Donor's e-mail** and **Customer's e-mail** (two recipient rows), **Attach Print** with the print format *PP DON Donor receipt*.
5. **Add the field on Stock Entry** (`custom_fields`): a Link to your donation, named with your reserved field prefix, `allow_on_submit` 1, `depends_on` the purpose *Material Receipt*, never `reqd`. A Material Receipt needs a **Stock Entry Type** of that purpose: a site set up without the setup wizard's records has none, and the retailer adds *Material Receipt* once. Then the report (`reports`, Report Builder, filtered `workflow_state != PP DON Cancelled`, ordered by `received_on desc`; a Check a report filters on is never `in_standard_filter`, or Desk drops the saved filter), the Connections (`links`, the donation under Customer) and a `documentation` property setter that points at your help.
6. **Check it before it reaches a retailer:** `python3 tools/check/check.py samples/s57_donation_intake`.

## What the retailer does

1. **Install the app.** It adds the donation, its workflow and lock, the receipt, the report, the Stock Entry field and the Connections. No setting, no role, no outside address.
2. **Switch the lock on:** Desk › *Retail Save Rule* › *PP DON donation locked once its receipt is given* › **Enabled**. A manifest installs every save rule switched off; until it is on, a given receipt can still be changed.
3. **Give Sales User** to the people at the donation door. A Sales Manager cancels a given receipt. Whoever makes the Material Receipt holds Stock User; add the Stock Entry Type *Material Receipt* if the site has none.
4. **Put the charity's details on the Letter Head** the store prints with.
5. **Add its own Notification** if it e-mails receipts (step 4).

## Limits

- **The receipt states no value.** A valuation for a tax claim, or a scheme such as the UK's Gift Aid, is a version of your own (and regulated).
- **The donation is written in Desk**, at the donation door; a till key that takes it at the till is a version of your own.
- **The donor's phone, the e-mails and the notes stay editable after the receipt:** the receipt prints none of them. **A customer's name follows the customer:** a receipt reprinted after the customer is renamed prints the new name; the customer itself cannot change.
- **Duplicating a Material Receipt copies its Donation:** clear it on the copy (a manifest's field cannot carry `no_copy`).
- **The stock entry names the donation; the donation does not list its stock entries** (a manifest's link may only list its own records under a retailer's record). Filter the Stock Entry list by **Donation**.
- **Desk shows the states and buttons with the app's prefix** (*PP DON Give receipt*).
- **Before removing the app,** delete the retailer's own Notifications on the donation.
- **The donor's details are personal data** the retailer keeps under its own policy. Uninstalling removes the donations and the Stock Entry field; the install's export keeps a copy.
