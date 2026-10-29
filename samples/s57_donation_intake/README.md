# S57 — Donation intake with a donor receipt (`pp_don`)

*Start from this sample: `python3 tools/manifest/start.py s57_donation_intake --prefix "ACME DON"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

A charity or thrift store's record of the goods people give it, kept in iVendNext Desk: who gave (one of the retailer's customers, a donor typed in at the door, or no one named), what came in (each kind of goods, how many, its condition), which store took it in and when, and a **donor receipt** that holds once it is given. When the sorted goods go into stock with the engine's own Material Receipt, the stock entry names the donation. The app moves no money, changes no stock and states no value for the goods. It calls nothing outside: no service, no outside address. The [recipe](../../recipes/donation_intake.md) walks a store through it.

It uses the manifest's `doctypes` (a record type and a child table), `workflows`, `save_rules` (a lock), `print_formats`, `reports`, `custom_fields` (one field on Stock Entry), `links` and a `documentation` property setter. **When to use it:** a store takes donated goods in at its door, and its donations and receipts are on paper or nowhere today.

## What happens

1. **At the donation door.** Store staff open **PP DON Donation** in Desk, **+ Add**. If the donor is one of the retailer's customers, choose the **Customer**: the donor's name, phone and e-mail come from it (as the till keeps them). Otherwise type the **Donor**'s name, and the phone and e-mail if the donor gives them; leave the name blank for a donor who gives none. Add the **Donor's address** if the donor wants it on the receipt. **Received at** is the store; **Received on** is today. Add a row per kind of goods: **Kind of goods** (*Clothing*), **What it is** (*children's coats*), **How many** and **Of** (*items*, *bags* or *boxes*), **Condition**. Save: the donation is numbered `DON-00001` and is **Received**.
2. **The receipt.** **Give receipt**: the donation is **Receipt given**, its **Receipt given** box is ticked, and from now on its donor, store, day and goods cannot change. **Print** › *PP DON Donor receipt*: under the store's own letter head, *Donation receipt · DON-00001*, where and when, the donor (or *an anonymous donor*) and address, each line of goods with its count and condition, and *"Thank you for your donation of the goods listed above. No goods or services were given in return. This receipt describes the goods and states no value."* A donation printed before **Give receipt** says *Not yet a receipt* at the top.
3. **A mistake.** **Cancel** a donation still **Received** (store staff), or one whose receipt was given (a store manager only): it is **Cancelled**, keeps its number and prints *Cancelled: this is not a receipt*. Take a new donation for the right goods.
4. **Into stock.** Whoever prices the sorted goods takes them into stock as today, with a **Stock Entry** of type **Material Receipt** into the store, and chooses the donation in its **Donation** field (shown on a Material Receipt only; settable after submit too). The Stock Entry list, filtered by **Donation**, shows where a donation's goods went.
5. **What came in.** The report **PP DON Donations** lists every donation not cancelled, newest first, with its store, its donor and whether its receipt was given. A customer's donations show under the customer, in the form's connections.

## What the retailer does

- Give the people at the donation door **Sales User** (they take donations, give receipts, print them and cancel a donation not yet given its receipt; they cannot delete one). A **Sales Manager** cancels a given receipt and may delete a donation taken in error.
- Put the charity's name, its registration number and its address on the **Letter Head** the store prints with (Desk › *Letter Head*): the receipt prints under it.
- Whoever makes the Material Receipt holds **Stock User**, which reads donations so the **Donation** field can find one. Reading a donation shows the donor's details.
- If the store e-mails receipts: its own Notification (the recipe's step 4). Nothing else: the app installs no setting, no role and no switch.

## The files

| File | What |
|---|---|
| `manifest.json` | the donation (`PP DON Donation`) and its child table (`PP DON Goods`); the workflow with its three states; the lock (a save rule); the donor receipt print format; the report *Donations*; the field *Donation* on Stock Entry; the donation list under Customer; the donation's help address |
| `tests/test_manifest.py` | the manifest passes the kit's checker and nothing the retailer's install refuses; no outside address and no money field, and the Stock Entry field optional and settable after submit; *Give receipt* and *Cancel* tick their boxes; a given receipt is cancelled by a manager only, and nothing leaves *Cancelled*; the lock holds every field the receipt prints; the donor's details come from the customer and can be typed; the report lists donations not cancelled, newest first; the goods table is not required; the receipt reads only fields that exist, skips a blank row and states no value; the Connections; the rights; the help |
| `tests/canaries.py` | each test goes RED when the rule it guards is broken |

## Run it

The tests need nothing but Python:

```bash
python3 -m unittest discover -s samples/s57_donation_intake/tests -p 'test_*.py'
python3 samples/s57_donation_intake/tests/canaries.py
```

Install the manifest in a retailer's iVendNext through **Extension Packages** (guide chapter 3), then open **PP DON Donation**.

## What is refused, and why

- **A value on the receipt, or any money field**: a value for a tax claim is the donor's to state, or a regulated scheme's (a partner's version, below). The receipt describes the goods.
- **Connections from the donation to its stock entries**: a manifest's link may only list its own records under a retailer's record. The stock entry names the donation; its list filters by it.
- **A required goods table**: Desk drops a row whose list fields are all blank, so *no goods yet* is a donation with no rows.

## Make it your own

What a partner usually changes:
- **a tax scheme:** the UK's Gift Aid (a declaration per donor, the sale proceeds reported back, the claim), or a valuation for a tax deduction where the law lets the charity state one;
- **at the till:** a till key that takes a donation at the till (the donor, the goods, the receipt printed by the till's printer) (recipe [A till key](../../recipes/point_handler.md));
- **sorting:** grading stations, lots with a sale-ready status, the goods into stock from the donation's rows;
- **supporters:** a supporter record and loyalty linked to donors; mission reports (what each store's donations raised);
- **the prefix:** `tools/manifest/rename.py` makes your copy under your own reserved prefix in one step (the naming series `DON-` too: change it in the donation's `autoname`);
- **its records:** `tools/deploy/copy_records.py` moves donations between a test site and the retailer's iVendNext.

## Technical notes

### Why it is built this way

A manifest only. The engine already takes goods into stock (a Material Receipt at the valuation the store chooses) and keeps the store's customers; what nothing holds is the donation itself and its receipt (the ERP removed its own donation records in its version 14). The receipt's integrity is a save rule rather than code: a workflow state and a lock, on every door. A till key would make the donation at the till, but a donation is taken at the back door, and an app user would cost a seat on every site; that is a partner's version, above. With no service there is nothing to host, no key to keep and no user to add.

### Bounds, stated

- **The lock holds from *Receipt given***, on the donor, the store, the day and the goods (Desk, an import and the API alike). The phone, the e-mail and the notes stay editable: the receipt prints none of them.
- **The donor's name, phone and e-mail are filled from the customer** when one is chosen (the till's `custom_phone_no` and `custom_email`) and can be typed when none is.
- **Desk shows the states and buttons with the prefix** (*PP DON Give receipt*, *IVENDNEXT DON Give receipt* in the library app).
- **A workflow's *who may edit* is a screen rule**; the lock is not: it refuses the save itself.
- **The Material Receipt's valuation is the store's choice**, as today; the app reads and writes no stock.
- **The donor's details are personal data** the retailer keeps under its own policy, as it keeps its customers'; uninstalling the app removes the donations (its export keeps a copy) and the Stock Entry field.
