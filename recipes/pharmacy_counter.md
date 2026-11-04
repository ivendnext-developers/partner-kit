# Pharmacy counter rules — the recipe

A pharmacy must not take money for prescription medicine without a valid prescription, and only a licensed pharmacist
may sell it. A controlled medicine needs the patient's identity, quantities are capped, and dispensed medicine is not
taken back. Each rule differs by country and drug class. This recipe holds those rules from outside the retailer's iVendNext: at **Pay**
on the till, at a return's confirm, and at **Submit** of a sales order, delivery or sales invoice on the Desk. Every rule
is a record the retailer fills. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** `samples/s39_pharmacy_counter/` — *Pharmacy counter rules*.

**When to use it.** Use it for a rule that must hold before money is taken, and that needs state shared between tills:
a refill that two tills must not both spend, or a cap per patient over days. The check before payment is the gate at
the till. A document check is the gate on the Desk. The state lives in the retailer's iVendNext as your own records, so a service
answering presses keeps nothing.

## Steps

1. **Declare, in your manifest** (`samples/s39_pharmacy_counter/manifest.json`):
   - **record types the retailer fills:**
     - `<PREFIX> Drug Schedule`: one class per axis, with its rules as fields;
     - `<PREFIX> Pharmacist`: user, licence, *valid until*;
     - `<PREFIX> Prescription`, with an item table;
     - `<PREFIX> Premises Licence`;
     - `<PREFIX> Patient`: one per customer, the identity and consent a schedule may need (below);
     - `<PREFIX> Settings`.
   - **one record type only your service writes,** `<PREFIX> Dispensing`, named by a field (`autoname: field:key`) so
     its name can serve as a lock (step 5);
   - **permission rows that say who writes what:**
     - only `<PREFIX> Pharmacist in Charge` writes the pharmacist list;
     - only pharmacists write prescriptions;
     - only `<PREFIX> Integration` writes dispensings;
     - only `<PREFIX> Records Officer`, a role nobody holds until iVendNext gives it, deletes a prescription, a
       dispensing or a patient record: laws keep a prescription for years, and a permission row cannot say *not once dispensed*.

     the install makes any role the manifest names that the site lacks, with no one in it;
   - **fields on the retailer's record types:**
     - a schedules table on Item (one row per axis, with *effective from*);
     - a schedule on Item Group;
     - ⭐ **not** the patient's identity and consent: a field on Customer is read by everyone who reads customers, and a
       permission level does not keep it from the form's change history, the list's group-by count or the link
       search. Put them on a record type of your own, one per customer (a `customer` Link, unique), named by a hash,
       readable only by the pharmacist roles, the integration role and the records officer, with a System Manager
       row of read alone (else the install gives that role every right, and a row with no right is refused). S39
       0.1.2's *Patient*;
     - the prescription fields on Sales Order, Delivery Note and Sales Invoice, the prescription's date among them (a
       `Date` a user can fill: never read only, fetched or levelled, or the document check may not fill it);
   - **sale details** for the prescription number, prescriber, licence, directions and the prescription's date. ⛔ Never
     `required`: a required sale detail stops every sale on every till of the site;
   - **two `check` subscriptions** with different down answers:
     - the dispensary's `refuse`: it sells only medicine, online only. Its settings list the prescription's date,
       `{"fill_attributes": ["<PREFIX> Rx Date"]}`, so its answer may fill it, and it calls an address of its own
       (`/rxc/dispensary/fill`): a till still on a version whose list is empty would refuse a fill whole, and its down
       answer would then refuse every sale, so the service fills only at that address. Deploy the service before any
     retailer updates: it still answers 0.1.3's address as before;
     - the front's `allow_and_flag`, with no settings: it refuses every prescription line before the date matters.

     Inside one manifest the checker counts them as one POS Profile, so they total 10 s at most (5 s + 5 s);
   - **three `doccheck` subscriptions,** one per record type (Sales Order, Delivery Note, Sales Invoice). Each is
     `on_validate: false` (a draft check is refused on these types), sends `stock_qty` and the lines' parent links, and
     names the prescription's date in `fill_fields`;
   - **a Report Builder report on `<PREFIX> Dispensing`** for the prescriptions register, for the pharmacist roles only
     (the readers of the dispensings are the readers of the patient record);
   - **two *Days Before* notifications** on the licences' *valid until*, to the pharmacist-in-charge's role;
   - a feed registration (no user named: the install makes the app's own user and names it), and a help address on each record type;
   - **a dispensing label** (`label_layouts`, below) and the three Item fields it prints, `<prefix>_strength`,
     `<prefix>_route` and `<prefix>_storage` (Data);
   - **the erasure** (below): a keeping period on `<PREFIX> Settings` (`keep_years`, an Int with no default), a record
     type `<PREFIX> Erasure` with a table of patients, and two `desk_action` buttons on it for the Records Officer,
     answered by two `desk_action` subscriptions. The integration role gets *delete* on the patient, the prescription and
     the dispensing, which only the second button uses.

2. **Check every call with its own route's secret** (`<app>:sub:<key>`), and refuse a timestamp more than five minutes
   from yours.

3. **Work out each line's rule.**
   - Read the schedules and item groups once a minute.
   - Read the lines' items with `variant_of` and `stock_uom`.
   - Read their schedule rows (`GET /api/resource/<PREFIX> Item Schedule?parent=Item`, filtered by `parent`) and units
     (`UOM Conversion Detail`, `parent=Item`).
   - An item's schedules are, per axis, its own row effective most recently; else its template's; else the nearest
     group's.
   - The strictest applies: any need, the least limit, returnable only if all say so.
   - Convert the till line's unit to the stock unit; on the Desk, use `stock_qty`.

4. **Decide, in this order** (`rxrules.decide`):
   - a returned line of a non-returnable schedule (P5);
   - on the front profile, medicine that needs a prescription, a pharmacist or the dispensary;
   - pharmacist only: the operator's `<PREFIX> Pharmacist` row, active, not a delegate, licence in date;
   - a named customer, never the walk-in (the settings' list and each POS Profile's own `customer`);
   - the identity fields the schedule needs, on the customer's `<PREFIX> Patient` record. Ask iVendNext *whether* each
     is set, both ways (`filters [["customer", "=", customer], ["<field>", "is", "set"]]` and `"is", "not set"`,
     `fields ["name", "customer"]`), so the value never leaves it; no record means none is set; an answer that names
     another customer, or answers a field of a record iVendNext does not list, is unreadable (503), never filled;
   - the quantity cap per sale;
   - the prescription: known, this customer's, active, in validity, a fill and quantity left, unchanged since its first
     dispense (a fingerprint);
   - the prescription's date: prescriptions written on different days in one sale are refused where a date is
     booked or typed; at the till a typed date that is not the prescription's is refused, and an empty one where the
     schedule ticks *Its register books the prescription's date* (the sentence shows the date to type);
   - directions and a doctor's name, where the group or schedule asks;
   - the frequency cap.

   Answer `refuse` with one sentence of at most 140 characters, naming the line. On the Desk, an allowed document whose
   prescriptions share one date answers `fill` with that date (`{"verdict": "fill", "fields": {"<prefix>_rx_date":
   "2026-10-19"}}`), which writes it over whatever was typed; a fill reserves as an allow does. Fill only a document
   that sent the field: a subscription still on older settings does not list it to fill, and refuses the answer
   whole. At the till, the dispensary's filling address answers `{"verdict": "allow", "fill": {"<PREFIX> Rx Date":
   "2026-10-19"}}` (the sale detail by its name, built from the prefix), over whatever the cashier typed. The till
   writes it, prices the sale again and asks once more on the filled sale: answer the same value, and keep the
   reservation (step 5). Never fill on a return. 0.1.3's address keeps the typed date: a wrong one is refused, and
   an empty one where the schedule books it.

5. **Reserve with the record's name as the lock.**
   - On allow, insert `<PREFIX> Dispensing` named `<an opaque key for the customer>~<next number>`. Never the patient's
     name: a record's name lands in access logs and Desk addresses.
   - Never reserve once the check has run 4 s: the till gives up at 5 s, and a reservation it never sees would hold
     the fill until the day closes.
   - If the insert fails because the name exists (409), another till took that number: read again and decide again.
   - Every dispensing of one patient is thereby decided in turn.
   - Pay pressed again for the same basket keeps its reservation. A changed basket releases it.
   - Write on it what the prescriptions register prints: the prescriber, the prescriber's directions (the dose: never
     a default standing in) and a licensed pharmacist's name from their record; the patient's name is fetched from the
     customer.

6. **Read back what iVendNext says, never a timer.** At the next decision for that patient:
   - **a reservation becomes *Dispensed*** when a booked POS Invoice carries its `sale_ref` (`custom_mpos_sale_ref`,
     stripped and lower-cased);
   - **it becomes *Released*** when its booked sale is cancelled, or when it was never booked and its POS day (`POS
     Opening Entry`) is *Closed*;
   - **a Desk reservation follows its document's `docstatus`:** cancelled or deleted releases it;
   - **a give-back counts only once its return is booked** (the till's return stores the refund's key in
     `custom_mpos_idempotency_key`).
   - **A document missing from a list is asked for by name.** A 404 means gone. Any other refusal means iVendNext
     hides it from your user, which is never read as gone.
   - Write each status back so the Desk list reads it.

7. **On the Desk, spend once per chain.**
   - A document whose medicine lines all carry a parent row (`against_sales_order` with `so_detail` on a delivery,
     `sales_order` with `so_detail` or `delivery_note` with `dn_detail` on an invoice) is allowed at once. The row
     reference matters: the engine holds the line to that row's item, while a parent's name alone can be typed onto
     any line.
   - A return line is always judged.
   - ⚠ A request that already booked a till sale leaves every later submit in it unchecked (the door's own rule,
     logged *not asked*). Test your Desk path in its own request.

8. **Answer 503 when iVendNext cannot be read,** so the till or the Desk applies the declared down answer. Each read
   waits about 2 s; the till cuts the whole check at its 5 s.

9. **The dispensing label** (`label_layouts`, [label layout](../contracts/pages/label_layout.md)): one `html` layout
   printed from the basket line, so `{uom}` is the line's unit (a strip sold from a box); the item's name, strength,
   route and storage (`{item.<field>}`: at most three, each Data, Select, Int or Check); the lot and its expiry; the
   store; and the dose, `{detail.Dose}`. No barcode: a part pack's unit has none, which refuses the label.
   - `{detail.…}` must name an **active Transaction Item Attribute when the layout is saved**, and the install saves
     it, so the install stops without it. No manifest kind makes one: the customer makes *Dose* before installing.
   - The layout installs switched on. A label layout cannot change in a later update: ship a changed one under a new
     name.
   - The markets that name a dispensing label's contents: Abu Dhabi (from a bulk pack) and Dubai (a part pack) ask the
     lot and expiry, and Saudi Arabia's part pack also the storage conditions. Egypt's registration number is the
     manufacturer's outer pack, not this label. Elsewhere it is a general label.

## After the keeping period

The customer's act, never a timer. Laws keep a prescription for a period (25 years in the UAE, 10 in Egypt, 5 in
Saudi Arabia and Jordan, 2 in Ghana, Kenya and Nigeria), then want the person's data destroyed. The customer sets the
period in `<PREFIX> Settings`; until it does, nobody is due.

1. The Records Officer makes a `<PREFIX> Erasure` and presses **List patients due**. The service reads each customer's
   newest dispensing (`day`), prescription (`date_written`) and change to the patient record (`modified`), grouped by customer
   (``max(`<field>`) as last``, the column in backticks, and `group_by`), and lists up to 100 whose newest record of every kind is older than today
   less the period, with their counts.
2. They press **Erase these patients**, typing the market's destruction record (a committee's minutes, the inspector
   present). For each row the service reads the patient's records again: one dated since the cut-off keeps the patient
   (*Kept*), and so does a value still on the customer's five fields of 0.1.1, asked set or not (cleared, the patient
   goes on a new erasure). Patients run six at a time. Otherwise it
   deletes the dispensings, then the prescriptions (a dispensing names its prescription), then the patient record.
3. The record keeps the period, the cut-off, who pressed and when, the destruction record and each patient's outcome.
   Nobody changes or deletes it, and once a patient is erased it is never listed again. A press works about 7
   seconds: one that runs out says so, and the next goes on.

What stays: a copy of each deleted record and of its change history in the Desk's *Deleted Documents* (a delete
through the API is never permanent), which a System Manager deletes; the button's last answer says so. Also the
till's sales and their sale details, and the register's own lines, which the register
erases after its own retention.

## Proof

- **Laptop:** `python3 -m unittest discover -s samples/s39_pharmacy_counter/tests -p 'test_*.py'`.
  - It includes two tills on real threads (exactly one is allowed) and the stand-in iVendNext's 409.
  - `canaries.py` breaks each guarded rule.
- **A sandbox:** `ivn try`, with the service's user holding your role alone plus the card's reads. Then run:
  - the prescription line refused for a counter assistant and booked for the pharmacist;
  - no prescription, or an expired one, refused;
  - the last fill refused;
  - an abandoned sale's fill released at day close;
  - a lapsed licence refused;
  - a till return refused;
  - a Desk invoice refused, and an order, delivery and invoice chain spending one fill;
  - the service stopped, so the dispensary refuses and the front lets the sale through.

## Limits to tell the customer

- **The prescription's date is filled at the dispensary's till and at Desk submit,** never at an order's or a layaway
  plan's placement at the till, which fills nothing: type it there.
- **The dispensing label has no patient name and no dispensing date:** the label door's list has neither. It needs a
  connection, and prints the dose only from a basket line.
- **The prescriptions register prints no age and no price:** a print or report may not read the patient's record yet,
  and the dispensing keeps no price (S39's README).
- **The till cannot take or show the patient's identity:** enter it on the patient's record on the Desk. A clerk is
  refused that record whole, but an assignment on it, the customer's Connections count and one engine export still
  tell a clerk something.
- **A POS Invoice made on the Desk POS screen, or through the API, is not checked:** a POS Invoice cannot be a document
  check's target.
- **The sentence shows at Pay,** not when the line is added.
- **A day left open holds its reservations.**
- **The item's own *Returnable* tick** refuses a till return before any check runs. This app adds the schedule's rule
  and the Desk credit note.
