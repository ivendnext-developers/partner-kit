# Consignment payouts — the recipe

A resale or consignment store sells pieces it does not own and pays each consignor an agreed share of what sold. This recipe gives the retailer the **consignor** and the **payout** as its own records in iVendNext Desk, the consignor named on each item, and a payout worked out from the retailer's own till sales and Desk invoices, with every sold line **paid once**. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants a store's consignment payouts off the spreadsheet without code inside the retailer's iVendNext.

**Reference implementation:** `samples/s61_consignment_payouts/`.

**When to use it.** The store takes pieces in from consignors (second-hand clothing, furniture, books, collectables, luxury resale), sells them at the till or in Desk, and pays each consignor their share once a month or when they ask. The sale itself is ordinary: the app reads what iVendNext booked.

**The four rules, here.** No code runs inside the retailer's iVendNext. One service, a function paid per call, answers two Desk buttons and reads and writes through the record API as the app's own user. It reads the retailer's sales and items and never prices anything: the money is the sale lines' own. It moves no money: how the consignor is paid is the retailer's, recorded on the payout.

## What the store sees

1. **At intake.** Store staff open **PP CSG Consignor**, **+ Add**: the consignor's name, phone, e-mail, **Consigned since** (today) and **Consignor's share** (50% unless changed). Then, on each item taken in, the **Consignor** field (under the item group), and **Consignor's share for this item** where this piece pays differently.
2. **At the till.** Nothing new: the piece is sold, returned or exchanged as any other.
3. **A payout.** The back office opens **PP CSG Payout**, **+ Add**: the consignor, the company and **Sales up to** (today). Saved, it is a draft numbered `CSG-P-00001`. **Work out the payout**: the lines appear, each sold line with its date, item, *Sold for*, share and *Consignor's part*, returns negative, and the summary.
4. **Paying.** **Print**, format *PP CSG Payout statement*, for the consignor. Pay them your way, fill **Paid with**, **Paid on** and the **Payment reference**, and an Accounts Manager presses **Pay this payout**. The payout reads **Paid** and is locked.
5. **A mistake.** A draft that is not wanted: **Drop** (Accounts User). A paid payout that was never really paid: **Cancel** (Accounts Manager); its lines come onto the next payout.

## Consignors

The record type `PP CSG Consignor`, numbered `format:CSG-C-{#####}`, shown by its name in links, tracked:

| Field | What |
|---|---|
| `consignor_name` | the consignor, required |
| `phone`, `email` | how to reach them; never read by the service |
| `since` | **Consigned since**, today by default, required: no sale before it is ever paid to them, even of an item named to them later |
| `share` | **Consignor's share**, a percent of what a piece sold for after discounts and before tax; required, 50 by default |
| `notes` | the agreement's terms, how they like to be paid |

Two fields on **Item**: `pp_csg_consignor` (a Link to the consignor, a standard filter of the Item list) and `pp_csg_share` (a percent; 0 means the consignor's own). **Sales User**, **Item Manager**, **Accounts User** and **Accounts Manager** keep consignors; a consignor's payouts show under the consignor (manifest `links`).

## Payouts

The record type `PP CSG Payout`, numbered `format:CSG-P-{#####}`, tracked: `consignor`, `consignor_name` (read only, fetched), `company`, `currency` (read only, the company's), `up_to` (**Sales up to**), the read-only `summary`, `lines`, `sales_total` and `payout_total` (**To pay**) the service writes, `worked_out_by`, the payment's `paid_with` (a Mode of Payment), `paid_on` and `payment_reference`, and `paid_by`, the manager whose press marked it paid. Its table `PP CSG Payout Line`, all read only: `posting_date`, `kind` (*Sale*, *Return*, *Cancelled after payout*), `item_code`, `item_name`, `qty`, `sale_amount`, `share`, `payout`, and the sale it came from (`sale_type`, `sale`, `sale_line`).

**A sold line** is a line of a submitted till sale (POS Invoice) or of a submitted Desk invoice that is not the till day's combined invoice (Sales Invoice with `is_consolidated` 0: the combined invoice repeats the till's lines), in the payout's company, dated from the consignor's *Consigned since* to *Sales up to*, for an item whose consignor is the payout's. Its *Sold for* is `base_net_amount`; its part is that times the share, to the cent. **A line on any payout that is not Cancelled is never put on another.**

**The workflow** `PP CSG Payout`: *PP CSG Draft* to *PP CSG Paid* by **PP CSG Pay**, allowed to `PP CSG Integration` alone, the app's own role, which only the service holds; *Draft* to *PP CSG Cancelled* by **PP CSG Drop** (Accounts User); *Paid* to *Cancelled* by **PP CSG Cancel** (Accounts Manager). iVendNext refuses a move a user's role has no transition for, on every door, and refuses a record made straight into a later step, so no person marks a payout paid.

**The lock** `PP CSG payout locked once paid` (`locked_in_state`, refuse, *Paid* and *Cancelled*) keeps every field the money rests on. It judges the step the record was saved in, so *Pay* (from a draft) and *Cancel* (which writes only the step) pass it.

## Steps

1. **Add the record types above** to your manifest (`doctypes`, the lines table with `"istable": 1`, every line field `read_only`), and the two Item fields (`custom_fields`; never `reqd` on the retailer's own record type).
2. **Add the workflow** (`workflows`): the move to Paid `allowed` your integration role, the role the install makes for your feed registration. A manifest's record types are never submittable, so the workflow, not a submit, is what makes a payout final.
3. **Add the lock** (`save_rules`) over every field the payout's money rests on. It installs switched off: the retailer switches it on, and your *Pay* service refuses while it is off (it reads the rule's `enabled` and `mode` from **Retail Save Rule**, so your role needs Read there).
4. **Add the two buttons** (`desk_actions`, `send_fields` `name`, `conditions` on `workflow_state` your Draft) and their services (`extension_subscriptions`, point `desk_action`). *Work out*: read the consignor's share and items, their sale lines through each sale type's table (`parent`), those sales' headers, and the lines other payouts hold; write the lines that are owed. *Pay*: read all of that again, check the payout's own lines against it (`consign.check_to_pay`), then write the step. Each write carries the payout's `modified` as read.
5. **Add the statement** (`print_formats`, Jinja, placing the letter head itself), the Connections (`links`) and a `documentation` property setter per record type.
6. **Check it before it reaches a retailer:** `python3 tools/check/check.py samples/s61_consignment_payouts`.

## What the retailer does

1. **Install the app.** It adds the consignor, the payout, the two Item fields, the workflow, the lock, the statement and the buttons, and makes the role `PP CSG Integration` and the app's own user with that role alone.
2. **Switch the lock on:** Desk › *Retail Save Rule* › *PP CSG payout locked once paid* › **Enabled**.
3. **Give the app's role Read** on POS Invoice, Sales Invoice, Item and Retail Save Rule (Role Permissions Manager).
4. **Switch the services and buttons on** (Retail Extension Subscription: read, consent, enable; Retail Desk Action: enable).
5. **Decide who does what:** intake (Sales User, Item Manager), payouts (Accounts User), paying and cancelling (Accounts Manager). Write on Item is a money right here: an item's consignor and share decide what a payout pays.

## Limits

- **The share when it is worked out** applies; *Pay* refuses if it changed since. An item moved to another consignor takes its unpaid lines with it.
- **A piece sold after *Consigned since* but before its item named the consignor** is counted for them; nothing before *Consigned since* ever is.
- **One consignor a press**, at most 500 lines a payout; the rest wait for the next.
- **Payment is recorded, not booked:** a purchase invoice or journal for the payout, or store credit issued as a gift card, is a version of your own.
- **A System Manager can delete a paid payout**, and its lines are then owed again; no other role may delete one.
- **Desk shows the steps and buttons with the app's prefix** (*PP CSG Pay*).
- **Uninstalling removes the consignors and payouts**; the install's export keeps a copy.
