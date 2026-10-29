# Donation intake with a donor receipt — the recipe

A charity or thrift store takes donated goods in at its door, and the donor often wants a receipt. This recipe gives the retailer the **donation** as its own record in iVendNext Desk: who gave, what came in, which store took it, and a **donor receipt** that holds once it is given; and, when the sorted goods go into stock, the stock entry names the donation. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants a store's donations off paper without code inside the retailer's iVendNext.

**Reference implementation:** `samples/s57_donation_intake/`.

**When to use it.** The store takes goods people give it (clothes, books, household goods), prices and sells them, and keeps no record of who gave what, or writes receipts by hand. Stock is already the engine's: the sorted goods go into stock with a Stock Entry of type **Material Receipt**, at the valuation the store chooses.

**The four rules, here.** No code runs inside the retailer's iVendNext. No address is called: the app is a manifest of records, a workflow, a lock, a print format, a report and one field on Stock Entry. It reads and writes no money and no stock, and its receipt states no value. Its only message to a donor is the retailer's own Notification, which sends through the retailer's own mail server.

## What the store sees

1. **At the donation door.** Store staff open **PP DON Donation** in Desk and press **+ Add**. A donor who is one of the retailer's customers is chosen as the **Customer**: the **Donor**, **Donor's phone** and **Donor's e-mail** come from the customer. Any other donor's name is typed (and the phone and e-mail, if given); a donor who gives no name is left blank. **Donor's address** if the donor wants it on the receipt. **Received at** (the store) and **Received on** (today). One row per kind of goods under **The goods**: **Kind of goods**, **What it is**, **How many**, **Of** (*Items*, *Bags*, *Boxes*), **Condition**. Saved, it is numbered `DON-00001` and is **Received**.
2. **The receipt.** **Give receipt** ticks **Receipt given**. **Print**, format *PP DON Donor receipt*: the receipt under the store's letter head. From now on the donor, the store, the day and the goods cannot change.
3. **A mistake.** **Cancel**: by store staff while the donation is **Received**, by a store manager once its receipt was given. A cancelled donation keeps its number and prints as no receipt.
4. **Into stock.** The Material Receipt that takes the sorted goods into the store names the donation in its **Donation** field.
5. **What came in.** The report **PP DON Donations** lists every donation not cancelled, newest first.

## Donations

The record type `PP DON Donation`, numbered `format:DON-{#####}`, tracked (its history shows who changed it and when):

| Field | What |
|---|---|
| `customer` | the customer, when the donor is one; optional |
| `donor_name`, `donor_phone`, `donor_email` | `fetch_from` the customer's `customer_name`, `custom_phone_no` and `custom_email` (the fields the till's new-customer sheet and customer edit write), and typed when there is no customer; none required |
| `donor_address` | text, printed on the receipt |
| `store` | **Received at**, a Warehouse; required |
| `received_on` | **Received on**, today by default; required |
| `goods` | child table `PP DON Goods`: `category`, `description`, `quantity` (a whole number, 1 by default), `unit` (Items, Bags, Boxes), `condition` (blank, Good, Fair, For recycling) |
| `notes` | text, never printed |
| `receipt_given`, `cancelled` | read only ticks the workflow sets |

**Sales User** reads, writes, creates and prints donations; **Sales Manager** and **System Manager** may also delete; **Stock User** reads them, so the Stock Entry's **Donation** field can find one. The donation shows under the Customer it names (manifest `links`).

## The workflow and the lock

| State | Sets | Who edits |
|---|---|---|
| Received | — | Sales User |
| Receipt given | `receipt_given` 1 | Sales User |
| Cancelled | `cancelled` 1 | System Manager |

The actions: **Give receipt** (Received to Receipt given, Sales User), **Cancel** (Received to Cancelled, Sales User; Receipt given to Cancelled, Sales Manager).

A **save rule** of kind `locked_in_state` (`save_rules`) refuses any change to `customer`, `donor_name`, `donor_address`, `store`, `received_on` and the `goods` rows once the donation is **Receipt given** or **Cancelled**, at every save: Desk's form, an import and the record API alike, with the message *"The receipt was given: the donor, the store, the day and the goods stay as on it. Cancel it and take a new donation instead."* (A workflow's *who edits* is only the browser's screen rule; the lock is the save's.)

## The receipt

The print format *PP DON Donor receipt* (Jinja) reads only the donation's own fields and its rows. Desk prints it under the store's default **Letter Head**, so the charity's name, registration number and address are the retailer's own. It prints *Donation receipt · DON-00001*, **Received at** and the day, *From* the donor or *an anonymous donor*, the address, a row for each line of goods that has a kind or a description (a row with neither is skipped), its count and condition, and the sentence *"Thank you for your donation of the goods listed above. No goods or services were given in return. This receipt describes the goods and states no value."* A donation not yet given its receipt prints *Not yet a receipt: press Give receipt first.* at the top; a cancelled one, *Cancelled: this is not a receipt.*

## Steps

1. **Add the record types above** to your manifest (`doctypes`, the goods table with `"istable": 1`), with no money field: the receipt states no value. Never make the goods table `reqd`: Desk drops a row whose list fields are all blank, so *none* is a donation with no rows. A row whose count and unit have defaults is kept even when the rest is blank, so the print skips a row with no kind and no description.
2. **Add the workflow** (`workflows`), its states and actions under your prefix, each state's tick in `update_field` and `update_value` (a workflow writes the tick as text, `"0"` or `"1"`).
3. **Add the lock** (`save_rules`, kind `locked_in_state`, mode `refuse`), naming the states and every field the receipt prints. A lock needs an active workflow on its record type.
4. **E-mail the receipt, with the retailer's own Notification** (a manifest notifies only the retailer's own users). In Desk, **Notification**, **+ Add**: Document Type *PP DON Donation*, Send Alert On **Value Change**, Value Changed **Receipt given**, Condition `doc.receipt_given in (1, "1") and doc.donor_email` (a bare `doc.receipt_given` would also fire on a text `"0"`), the channel **Email** to the document field **Donor's e-mail**, **Attach Print** with the print format *PP DON Donor receipt*.
5. **Add the field on Stock Entry** (`custom_fields`): a Link to your donation, named with your reserved field prefix, `allow_on_submit` 1, `depends_on` the purpose *Material Receipt*, never `reqd`. Then the report (`reports`, Report Builder, filtered `cancelled = 0`, ordered by `received_on desc`; a Check a report filters on is never `in_standard_filter`, or Desk drops the saved filter), the Connections (`links`, the donation under Customer) and a `documentation` property setter that points at your help.
6. **Check it before it reaches a retailer:** `python3 tools/check/check.py samples/s57_donation_intake`.

## What the retailer does

1. **Install the app.** It adds the donation, its workflow and lock, the receipt, the report, the Stock Entry field and the Connections. No setting, no role, no switch, no outside address.
2. **Give Sales User** to the people at the donation door. A Sales Manager cancels a given receipt and deletes a donation taken in error. Whoever makes the Material Receipt holds Stock User.
3. **Put the charity's details on the Letter Head** the store prints with.
4. **Add its own Notification** if it e-mails receipts (step 4).

## Limits

- **The receipt states no value.** A valuation for a tax claim, or a scheme such as the UK's Gift Aid, is a version of your own (and regulated).
- **The donation is written in Desk**, at the donation door; a till key that takes it at the till is a version of your own.
- **The donor's phone, e-mail and the notes stay editable after the receipt:** the receipt prints none of them.
- **The stock entry names the donation; the donation does not list its stock entries** (a manifest's link may only list its own records under a retailer's record). Filter the Stock Entry list by **Donation**.
- **Desk shows the states and buttons with the app's prefix** (*PP DON Give receipt*).
- **Before removing the app,** delete the retailer's own Notifications on the donation.
- **The donor's details are personal data** the retailer keeps under its own policy. Uninstalling removes the donations and the Stock Entry field; the install's export keeps a copy.
