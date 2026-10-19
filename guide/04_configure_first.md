# 4. Configure first

![What the cashier meets once the pack is applied: member price, reasons, a line detail, an IMEI, a void reason](../samples/s5_config_pack/screenshots/s5_flow.gif)

*Settings only, no code: the till gives a member their price, asks for a reason on a markdown and on a void, checks a line detail, and asks for the phone's IMEI.*

Most of what a shop asks for is already in iVendNext as a setting. This chapter shows how to set it up: the shop's administrator sets these in iVendNext Desk, or runs a one-time script, and nothing of yours runs in the shop. It is for every builder, before any code: most needs stop here.

**Reference implementation:** [Setting a shop up with no code](../recipes/configure_no_code.md) with the sample [`../samples/s5_config_pack/`](../samples/s5_config_pack/) (coded reasons, IMEI tracking, one more detail per line, member pricing), and [A receipt laid out for your market](../recipes/receipt_format.md) with [`../samples/s4_receipt_pack/`](../samples/s4_receipt_pack/).

## When to use it

Always first: rung 1 of the ladder (chapter 3, which lists everything that is configuration). Check this chapter and the [needs catalogue](../needs/README.md) before you propose an app. This chapter teaches the five set-ups the kit has built and tested, in steps below; the four last rows are settings the kit has looked at on a sandbox; each card says which parts were run and which were not.

| You want | The shop's own setting | Card |
|---|---|---|
| A coded reason when a cashier voids, returns or discounts | **Reason Code Master** rows, and the switch for that type in **Retail Setting** (a void reason also needs `save_voided_transaction`) | [reason-codes](../needs/till/reason-codes.md) |
| The IMEI of every phone sold, once | the item's **Has Serial No**; the IMEI *is* the serial number, received with the stock | [imei-per-phone-sold](../needs/stock/imei-per-phone-sold.md) |
| One more detail on a line, for goods with no serial number | a **Transaction Item Attribute** (a name, a pattern, an order) | [line-detail-for-goods](../needs/till/line-detail-for-goods.md) |
| A member price | one **Customer Group** per tier, and one **promotion** per tier. A promotion cannot be pointed *at* a customer group; it can only *exclude* groups. So each tier's promotion excludes every other group: the other tiers and every non-member group | [member-price-by-tier](../needs/prices/member-price-by-tier.md) |
| A receipt for your market: tax number, address, logo, a line per VAT rate, a second language | a print format (chapter 7), then chosen on the till's **POS Profile**. For the address, tax number and a second-language footer alone, the register's *Receipt Header* and *Receipt Footer* print on the shipped receipt without copying it (chapter 9) | [receipt-for-your-market](../needs/documents/receipt-for-your-market.md) |
| A customer statement, printed or sent on a schedule | **Process Statement Of Accounts**: pick the customers, the layout, the dates, the frequency and the sender. The schedule needs an outgoing e-mail account; run the ageing on the customer's site before you promise it | [debtors-statement](../needs/reports/debtors-statement.md) |
| One branch to see only its own stock and the head office's | a **User Permission** on *Warehouse*, one row for each store, for each user. Three stock reports ignore it (one only in its default layout): test every stock report the user may open | [branch-sees-own-stock](../needs/stock/branch-sees-own-stock.md) |
| A reminder when a store's stock is below its level | **Item Reorder** rows on the item (store, level, quantity, type) and the automatic-request setting in **Stock Settings**; leave the row's warehouse group empty. The request it makes is submitted, never a draft | [low-stock-reminder](../needs/stock/low-stock-reminder.md) |
| A column the retailer wants on a record's list | the list's own column settings, or the record type's list settings. Only the record's own fields; no total of its rows | [list-columns](../needs/setup/list-columns.md) |

## Steps: reasons, IMEI, line detail, member pricing

1. **Copy `config.json` and change the names, codes and numbers to the shop's.** It is the whole set-up as data. The `PP CFG` prefix is only there so the sample's test can find its records.
2. **Give the script a key** of a user who may edit those records. System Manager, Retail Manager, Item Manager, Stock Manager and Sales Master Manager together are enough (measured). It is the administrator's key, used once.
3. **Run it:**

   ```bash
   PP_BASE=https://your-shop PP_KEY=<api key> PP_SECRET=<api secret> python3 samples/s5_config_pack/apply_config.py
   ```

   You can run it twice: nothing doubles. Each run recomputes the member promotion's exclusion list: every customer group with no groups under it, apart from the tier's own, so *Individual*, *Commercial* and the walk-in customer's group are excluded too. **Until you run it again, a customer group added later gets every tier's discount.** S5 carries one tier; for several tiers, sample S22 makes one promotion per tier the same way. `--remove` undoes it, except the stock: the item, its price, the unsold serial numbers and the booked Material Receipt stay. On a real shop use your own IMEIs and quantities.
4. **The shop needs a default Company.** A sale of a serial-tracked item takes its company from it. Without one, the first IMEI sale fails with *"Error: Value missing for Serial and Batch Bundle: Company"*.
5. **Nothing to do at the till.** The cashier is offered the reasons, asked for the IMEI, offered the line detail, and gets the member price once the member is attached to the sale. Each costs an extra step per line: switch on only what the shop will use.

Limits to know before you rely on these settings:
- **After adding a customer group,** run `apply_config.py` again, or add the group to every tier promotion's exclusion list. Until then the new group gets the member discount.
- **A customer with no customer group is not excluded,** so it gets the member discount: a promotion only excludes a group it can match, by its exact name. Give every customer a group. The script lists the customers it finds without one.
  - **Set Selling Settings → Default Customer Group** (for example a *Non-Member* group). The server gives it to every new customer — from the till, the API or a connector — but not to a Data Import (give the file a group column). With no default, iVendNext POS's quick capture puts a new customer in the alphabetically first lowest-level group, which can be a member tier.
  - **A sale on iVendNext POS always has a customer:** with none attached it uses the store warehouse's *cash customer*. Give each store's cash customer a non-member group. The *Walk-in Customer* made at install has no group.
  - **Use lowest-level groups only.** An exclusion matches the exact group, never the groups under it, and the script excludes lowest-level groups only: a customer placed in a group that has groups under it (such as *All Customer Groups*) is never excluded.
  - Making the group mandatory (Customize Form, in Desk) is the shop's own configuration. Set the default first: a creator that sends no group is then refused.
- **The member discount is a discount on the whole sale,** shown in the sale's totals, not on each line.
- **One discount on the whole sale, never two.** Only one sale-level promotion applies to a sale: the lowest *Sequence Number* is tried first and the first that qualifies wins. The script gives the member promotion the highest number, so any other sale-level offer that qualifies takes the sale, members included; to let the member discount win, move it up in *Promotion Bonus Buys Hierarchy* (saving it renumbers them). Item promotions still apply beside it.
- **Lines already discounted are left out.** *Exclude Discounted Items* is on by default (the script leaves it on): a line on an item promotion or a markdown gets no member discount.
- **A cashier's sale discount replaces the member discount** on iVendNext POS; the two never add up (from the code; not walked).
- The till asks for the reason, but the server does not insist on one: a sale discount with no reason code still books.
- The line detail's pattern is checked on the till screen only. The server itself accepts a value that breaks it.

## Steps: a receipt for your market

![A sale at two VAT rates, and its tax invoice in the till's Print sheet](../samples/s4_receipt_pack/screenshots/s4_flow.gif)

*A sale at two VAT rates, then its tax invoice in the till's Print sheet: logo, address, tax number, each line's VAT rate and the taxable value per rate, in English beside Arabic.*

1. **Put the facts where the shop keeps them, not in the layout:** the **tax ID** on the Company, an **Address** linked to it, and the **Company Address** on the till's POS Profile. The shop copies them onto each sale when it is saved (the sample adds one field for the tax ID), and the layout prints what the sale holds and reads no other record, so one layout serves every company. A sale saved before the package was installed has no tax number.
2. **Copy `receipt.html` and `logo.png` and edit** the words, the order and the logo; the format's name starts with your prefix. VAT rates are read from each sale's own lines, never typed in, so a reprint should keep its old rate. Arabic sits beside English in a row marked right-to-left; the logo is written into the page. A script, a frame or an event attribute in a template is refused.
3. **Build and check, before anyone installs it:**

   ```bash
   python3 samples/s4_receipt_pack/build.py
   python3 tools/manifest/validate.py samples/s4_receipt_pack/manifest.json     # VALID, exit 0
   ```

4. **Install the manifest**: on your sandbox with `deploy`; on a customer's site, by its administrator from the install screen (chapter 7).
5. **Choose it on the till profile: Desk → POS Profile → the profile → Print Format → Save.** This step is configuration; a manifest cannot do it yet. The till reads the format at each print, so it is live on the next receipt. The save is refused, with the reason, if the format is not one for a POS sale or cannot print the register's latest booked sale.
6. **Book a sale and open the Print sheet** to see it.

Limits to know before you ship a receipt:
- The format is for the till sale only; a back-office invoice has its own.
- Two different non-zero rates under one tax account print a single VAT total.
- Arabic on paper or PDF, a returned sale and a sale with two or more tax rows have not been tried; test them for your market.

## What is refused, and why

- **A price, tax or total set in code.** Member pricing is a promotion, not a pricing rule: a selling pricing rule is refused today. A receipt prints money the shop has already worked out; it never decides it.
- **A manifest that edits the shop's own settings or stock.** That is why the set-up is a script run by the administrator, not a manifest.
- **A new customer's phone or email made required at the till, or a listed field hidden or relabelled,** is a field rule (chapter 9 says which fields), set in POS Studio's Fields tab or declared in a manifest (chapters 7 and 9); field rules are an extension point. **A tax authority's QR code and seal on the receipt** (a fiscal reader, chapter 11) **and labels printed from the till** (a label layout, chapter 9) are extension points too. This chapter does not set them up. (A wrong value refused on save is a save rule: chapter 9.)
- **A customised receipt gets none of our later fixes** (where the shop's own lines are enough, the register's *Receipt Header* and *Receipt Footer* keep the shipped receipt), and the seeded receipt carries more than the sample (per-item charge rows, serial and batch lines, deposit and balance lines, offline-sale lines). Copy back what your market needs and test it.

## When your service is down, and when the till is offline

No service of yours is involved: everything here lives in the shop, so there is nothing to be down. **Member pricing works offline** for a member on the list of customers the till keeps for offline use: the till takes the member discount from its own copy of the shop's promotions, whether the member was attached before or after the connection dropped, and the walk-in customer, whose group the promotion excludes, pays full price. The cashier sees the discount and a total marked *Provisional*, takes cash, and the sale is held; when the connection returns the till lists it as matching, the cashier posts it, and the booked sale equals what the till showed. From the code, a customer the till's list does not hold gets no member discount offline. The rest of this chapter has not been tried offline. One limit is known: an offline sale prints a provisional slip only, which shows the discounted total but no discount line; the final receipt format is for the booked sale.

## Technical notes

### The pictures

Both were walked on our test bench on 2026-10-10, iVendNext POS app at `87812e141`, in the till frame (`/pos?frame=terminal`, 1440 wide). The S5 walk ends with the sale voided, so nothing was sold. The S4 walk sent nothing to a printer; the test bench's currency is the Rand, so the invoice shows R where a UAE shop shows its own. Each sample's README has the stills, step by step.

### What the kit has proven

- **Read back from the shop's database:** every switch, reason code, item, IMEI, line detail, group, member and promotion; the till's own reason list offers each reason.
- **Member pricing:** the same basket costs the member exactly 10% less (2 338.20 against 2 598.00) and the other customer full price; the booked sale equals the till's preview.
- **Member pricing on the till, online** (walked 2026-10-14 on our test bench, iVendNext POS app at `8ce9bed2`, the till frame; one basket of three lines, R 5 797.00): the member paid R 5 217.30 (10% off the sale, R 579.70); the walk-in customer paid R 5 797.00; a customer with no group paid R 5 217.30; a customer in a group made after the script ran paid R 5 217.30, and after the script ran again, R 5 797.00. Each booked sale equals the till's figures.
- **Member pricing on the till, offline** (the same walk, the shop's server stopped): the member attached before the connection dropped, attached after it, and attached to a basket already priced online each paid R 5 217.30; the walk-in customer paid R 5 797.00; the customer with no group paid R 5 217.30. No sale was refused. Back online, the till listed all five as matching; once the cashier posted them, each booked sale equals what the till showed.
- **Reasons:** a sale discount keeps its type and code on the invoice; a line markdown keeps its type, code and the cashier's comment.
- **IMEI:** no IMEI, two units on one line, and one unit with two IMEIs are each refused in the till's words; a right sale books and takes the IMEI out of stock; the same IMEI cannot be sold twice.
- **Run twice, then removed:** the second run creates nothing; after `--remove` nothing live is left (a record a booked sale points at is retired, and a later run switches it back on).
- **The receipt,** on three sales (standard-rated, zero-rated, both): logo, company name, tax number, address, English and Arabic labels, right-to-left, each item's booked VAT rate, taxable value per rate, and Total and VAT equal to the booked figures. Uninstall then reinstall leaves the schema as found. With either pack applied, preview equalled booking on every basket (chapter 14).

### What it has not

- **The till screens, partly:** the 2026-10-07 walk showed the till asking for a markdown reason and its comment, the IMEI, and a void reason, and voiding the sale with its record kept. The return reasons (item return, sale return) were not walked, and the voided record's stored reason was not read back from the database.
- **A reason is not required by the server:** a sale discount with no reason code booked and matched. An item-return or sale-return reason on a sale was not exercised.
- **The line detail's pattern** is checked on the till screen only; the server saved a value that broke it.
- **Receipts:** Arabic shaping and right-to-left order on paper or PDF; a 5% VAT shop in dirhams (the test shop is rand at 15%); a real item surcharge; a returned sale; a sale with two or more tax rows (the template's branch for it was not run); the Customer TRN, DUPLICATE and Discount rows and a serial under an item were never rendered. Two different non-zero rates under one tax account print a single VAT total. The format is for the till sale only; a back-office invoice has its own.
- **A reprint keeping its old VAT rate** (step 2 of the receipt) was not tested.
- **Member pricing offline, at its edges:** a member the till's offline customer list does not hold (in the walk the list held this store's recent customers), a member moved to another group or a promotion changed while the till was offline, and a card payment offline were not tried. From the code, the till never guesses an offline member discount: when it cannot work one out exactly, it does not apply it.
- **Offline was not tested for the reasons, the IMEI, the line detail or the receipt.**
- Blind counts, permissions per till action, gift receipts and notifications with the print attached have no recipe in the kit yet (for the last, the card *approval-email-with-print* gives the setup).

## See also

[3. The ladder and the four rules](03_ladder_and_never_list.md) · [7. Manifests](07_manifests.md) · [9. The extension-point catalogue and requests](09_points_and_requests.md) · [14. Testing and release](14_testing_and_release.md) · [16. Possible, not possible, limits](16_possible_not_possible.md)
