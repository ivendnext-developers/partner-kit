# Set iVendNext up with no code — the recipe (reasons, IMEI, line detail, member pricing)

![What the cashier meets once the configuration is applied](../samples/s5_config_pack/screenshots/s5_flow.gif)

*Once the configuration is applied, the till gives a member their price, asks for reasons, checks a line detail, asks for a phone's IMEI and asks why a sale is voided.*

This recipe makes the till **ask for and keep** a coded reason, **track a phone by its IMEI**, **capture one more detail per line**, and **price members differently**. It uses only what iVendNext already has, switched on by configuration. It is for an iVendNext Partner, the CitiXsys Consulting Team or a retailer's own administrator. **Reference implementation:** `samples/s5_config_pack/`: `config.json` is the whole set-up, `apply_config.py` applies it over the record API, and `--remove` undoes it.

**When to use it.** Rung 1 of the build ladder: configure first, always. Nothing here runs partner code in the retailer's iVendNext. The script is a one-time set-up run by the retailer's administrator; after that it is not needed again.

## What each part is

| You want | The retailer's own setting | What the sample sets |
|---|---|---|
| A coded reason for a void, a return, a discount | **Reason Code Master** rows (a type each: *Void Sale, Item Return, Sale Return, Sale Discount, Item Discount, Price Override …*) and the **Retail Setting** switch for that type (`reason_void_sale`, `reason_item_return`, `reason_sale_return`, `reason_sale_discount`, `reason_item_discount`; a void reason also needs `save_voided_transaction`) | five reason codes, six switches on |
| The IMEI of every phone sold, once | the item's **serial numbers** (Item → *Has Serial No*); the IMEI **is** the serial number, received with the stock | one tracked item, three IMEIs in stock |
| One more detail on a line, for goods with no serial number | **Transaction Item Attribute** (a name, a pattern, an order) | "Warranty card", pattern `^WC-[0-9]{8}$` |
| A member price | a **Customer Group** per tier, and one **promotion** per tier that applies to the sale and **excludes every other customer group** | group *Member Gold*, a 10% promotion, a member in the group |
| A branch's till sees its own store's stock and the head office's, no other branch's (POS build 2.0.0.654 on) | the till's **POS Profile** → *Stores this till may see*: list the stores. The *Other stores* panel and a cross-store order's store list then show the listed stores only, and the item card the listed stores and the till's own (a head office that is not a retail store shows in the card only); an order to a store not listed is refused. Empty: every store marked a retail store, as before. It narrows stock and orders, not sales: a return's sale from another store and a held sale are found anywhere (the card *branch-sees-own-stock*) | not set by the sample |

## Steps

1. **Read `config.json`, and change the names, codes and numbers to the retailer's.** Names start with `PP CFG` in the sample only so its test can find and remove them; use the retailer's own.

2. **Give the script a key:** a user who may edit those records. These roles together are enough: System Manager, Retail Manager, Item Manager, Stock Manager, Sales Master Manager. The key is the retailer's administrator's, used once.

3. **Run it:**

   ```bash
   PP_BASE=https://your-shop PP_KEY=<api key> PP_SECRET=<api secret> python3 samples/s5_config_pack/apply_config.py
   ```

   - **Run it twice and nothing doubles.** The second run says *kept* for everything, and receives no stock.
   - **Each run recomputes the member promotion's exclusion list**, so a customer group added since is excluded the next time you run it.
   - **`--remove`** puts the switches back to what they were and deletes what the script made. A record a booked sale points at cannot be deleted, so it is *retired* (a reason code made inactive, the member disabled, the line detail switched off); a later run switches it back on. **Sample S22 shows what happens to an integration user that has taken a workflow step (check by workflow):** iVendNext keeps a record of each step, visible to the site's Administrator alone, so the user and its role cannot be deleted. The undo disables the user, gives it new keys that no one keeps, and disables the role; a later run switches them back on (`recipes/integration_user.md` step 6).
   - ⚠ **It does not undo the stock.** The item, its price, the unsold serial numbers and the **submitted Material Receipt** (which posts the units' value to the books) stay. On a real site, use your own IMEIs and quantities, or cancel the receipt if it was a trial.

4. **Make sure iVendNext has a default Company.** Any retailer that finished its set-up has one. A sale of a serial-tracked item builds a Serial and Batch Bundle, which takes its company from that default. Without it, the first IMEI sale fails with *"Error: Value missing for Serial and Batch Bundle: Company"*.

5. **The cashier's side: nothing to do.** The till offers the reasons it finds, asks for the IMEI of a tracked item, offers the line detail, and applies the member promotion when the member is attached to the sale.

   ![the member's price](../samples/s5_config_pack/screenshots/01_member_price.png)

   *The gold member's 10%, in the totals.*

   ![a markdown asks for a reason and a comment](../samples/s5_config_pack/screenshots/02_markdown_needs_a_reason.png)

   *A 10% markdown on the phone asks for a reason; "price match" also asks for a comment.*

   ![the line detail's pattern refuses a wrong value](../samples/s5_config_pack/screenshots/03_line_detail_pattern.png)

   *The line detail "Warranty card" refuses a value that does not match its pattern.*

   ![the IMEI](../samples/s5_config_pack/screenshots/04_imei_captured.png)

   *The phone's IMEI, captured before it can be charged.*

   ![a void asks why](../samples/s5_config_pack/screenshots/05_void_needs_a_reason.png)

   *A void asks why, and keeps the voided sale on record.*

## Two more things a retailer configures

### The document's print attached to an approval e-mail

A notification on the document, set up in Desk (or over the record API) by the retailer's administrator: **Notification** with *Channel* Email, *Send Alert On* a value change of `workflow_state` (or the event the retailer wants), its recipients by role, and **Attach Print** ticked with the print format chosen. In **Print Settings**, **Allow Print for Draft** must be on. With it off, the notification raises an error inside the document's own save, so the approval step can stop; send the first one to a test document. Checked on a sandbox (2026-10-16): a notification on Purchase Order with *Attach Print* saved as sent, switched off, then deleted. No mail was sent: the sandbox's outgoing e-mail is off.

```json
{"doctype": "Notification", "name": "PO approval mail", "document_type": "Purchase Order", "channel": "Email",
 "event": "Value Change", "value_changed": "workflow_state", "attach_print": 1, "print_format": "<the shop's PO format>",
 "subject": "Purchase order {{ doc.name }} waits for your approval", "recipients": [{"receiver_by_role": "Purchase Manager"}]}
```

Limits:
- An uploaded file (a CSV) goes as a **link** in the message, not an attachment. The installed version has no attach-from-field, and a manifest refuses one (it could mail any private file).
- *Allow Print for Draft* is site-wide.
- From POS build 2.0.0.654 a package may attach its **own** print format to a notification on its **own** record types ([chapter 7](../guide/07_manifests.md), *A notification's own print*). The retailer's own documents stay configuration.

### A member rate after the promotions: the certified pricing module

A rate the promotions cannot express (a member's percent on top of the day's promotion) is the pricing extension point, answered by a module we have certified (`guide/08_sandboxed_functions.md`, the contract `contracts/pages/price.md`).
1. **The module.** A partner builds it from the kit's template (`tools/wasm_kit/template/`). Built through the kit's meters, the template is byte-identical to the product's own reference module, *price member* (register `4XSR0YJSBW8X`). CitiXsys certifies a module's SHA-256 for the extension point `price`, version 1, by hand; the certificate comes back with it.
2. **The module record.** The retailer's System Manager opens **Retail Extension Module** in Desk, then fills it in:
   - *Extension point* `price`, *Partner*, *Version* 1;
   - *Module file*: attach the `.wasm`;
   - *Counts its own steps* (metered) as the certificate says;
   - *Certificate*: paste it.

   iVendNext works out the fingerprint and size itself, and refuses a file the certificate does not admit, in its words *"This module cannot be used: ⟨reason⟩"*. A saved module cannot be changed: a new build is a new version.
3. **The subscription.** **Retail Extension Subscription**:
   - *Extension point* `price`, *Answered by* `wasm` (the form offers nothing else);
   - *Partner module*: the record above, a *Label*;
   - *Settings*: the module's rules, for example `{"rules": [{"id": "Gold 10%", "item_group": "*", "customer_group": "Gold", "percent_bp": 1000, "cap_minor": null, "min_qty_milli": 0}]}`;
   - **Most a module may take off a line (%)**: it starts at 0, and at 0 the module is not even run. Raise it to the most iVendNext allows;
   - *Only for these POS Profiles* if the rate is not for every store; *Enabled*.

   At most one enabled pricing subscription answers a POS Profile.
4. **Test on one till.** A gold member's line shows the promotion and then *"Gold 10% −…"* beside it, on the phone, the counter and the tablet, online and offline. A refused or missing answer charges the platform's own price.

Limits:
- It takes money off a line only, after every promotion, never past the retailer's limit;
- a line a Pricing Rule priced, a return, a zero-rate line and a gift card are never shown to it;
- the Desk POS does not run it.

## What is refused, and why

- **A phone line with no IMEI, two units on one line, or one unit with two IMEIs:** the till refuses the sale, so every phone sold has exactly one IMEI on record. The same IMEI cannot be sold twice.
- **A line detail that breaks its pattern:** refused **on the till screen only**. The server saves a value that breaks the pattern.

## Limits to know before you build

- **The server does not refuse a wrong line detail, or a sale composed without a reason.** The till asks; the server does not check. If a wrong value must be refused on save, that is the save-rules extension point (P-RULES, chapter 9), not configuration.
- **Configuration cannot make a field required or hidden at the till.** That is the field-rules extension point (P-FIELDS, chapter 9), which has shipped since this recipe was measured.
- **A customer group created later gets the member discount until the script is run again** (it recomputes the exclusion list each run), or until the group is added to the promotion's exclusions in Desk.
- **One unit per line** for a serial-tracked item, by the till's design.
- **Offline** was not tested for any part.
- Reason codes, the IMEI and the line detail each cost the cashier an extra step on every line they apply to. Switch on only what the retailer will use.

## Technical notes

Proven on our test bench.

### Notes moved from the steps

- Step 2: the roles were measured on the bench.
- Step 4: our test bench has no default Company, and the first IMEI sale there failed on the bundle's missing Company (the framework words that as *"Error: Value missing for Serial and Batch Bundle: Company"*, and the failed save's own error ends `: company`) until the test set one for its run (finding F1 in the evidence file).
- Step 5: **walked in a real browser** (our test bench, 2026-10-10, iVendNext POS app at `87812e141`; frame: the till, 1440 wide; the sale voided at the end). The returns' reasons were not walked. The GIF is built from the same screens, every frame cut above the till's key row.

### What the sample was proven to do (our test bench, 22 + 2 checks)

- Every switch, reason code, item, IMEI, line detail, group, member and promotion **read back from the database**; the till's own reason list offers each reason; the line detail comes with its pattern.
- **Member pricing:** the same basket, the member pays exactly 10% less (2 338.20 against 2 598.00), the other customer pays full price; the booked sale equals the till's preview.
- **Reasons:** a sale discount keeps *Sale Discount* + its code on the invoice; a line markdown keeps *Item Discount* + its code + the cashier's comment.
- **IMEI:** a line with no IMEI is refused (*scan the unit's serial*); two units on one line are refused (*one unit per line*); one unit with two IMEIs is refused (*2 of 1 serials captured*); a right sale books, takes the IMEI out of stock, and the same IMEI cannot be sold twice.
- **Line detail:** saved with the sale against the right item.
- Applied twice: nothing created the second time. Removed: the switches back, nothing live left.
- The money kit with the pack applied: green on our test bench (`recipes/money_kit.md`).

### Limits, stated

- **The line detail's pattern is checked on the till screen only.** The server saves a value that breaks the pattern (measured: `not-a-card` was saved). If a wrong value must be refused, that is an extension point (P-RULES), not configuration.
- **A reason is asked for and kept; a sale composed without one is not refused by the server** — measured: with the switches on, the money kit's recorded basket with a 7% sale discount and no reason code booked and matched its answer. The till's own code comment says a *return* has always demanded a reason; that was **not exercised here**, and neither was capturing an **item return** or **sale return** reason on a sale (only *Sale Discount* and *Item Discount* reach an invoice in the tests): the switches and the reason codes for those types are proven present and offered by the till's own list, nothing more. **The till screen asking was walked** (2026-10-07): the markdown asked for a reason and, for *price match*, a comment; the IMEI was captured; the **void** asked for its reason (*Void: scanned in error*) and the sale was voided with its record kept. Not proven: the return reasons on the till screen, and the voided record's stored reason read back from the database.
- **What the recipe cannot do:** make a field required or hidden at the till (the field-rules extension point, P-FIELDS, chapter 9), or refuse a wrong value on save (the save-rules extension point, P-RULES, chapter 9): both have shipped since this recipe was measured.

### Tests

- The pack's bench test (applied, three sales, removed) passed on our test bench.
- The money kit with the pack applied (`recipes/money_kit.md`).
