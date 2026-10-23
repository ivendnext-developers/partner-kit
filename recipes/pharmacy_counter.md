# Pharmacy counter rules — the recipe

A pharmacy must not take money for prescription medicine without a valid prescription, and only a licensed pharmacist
may sell it. A controlled medicine needs the patient's identity, quantities are capped, and dispensed medicine is not
taken back. Each rule differs by country and drug class. This recipe holds those rules from outside the shop: at **Pay**
on the till, at a return's confirm, and at **Submit** of a sales order, delivery or sales invoice on the Desk. Every rule
is a record the shop fills. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** `samples/s39_pharmacy_counter/` — *Pharmacy counter rules*.

**When to use it.** Use it for a rule that must hold before money is taken, and that needs state shared between tills:
a refill that two tills must not both spend, or a cap per patient over days. The check before payment is the gate at
the till. A document check is the gate on the Desk. The state lives in the shop as your own records, so a service
answering presses keeps nothing.

## Steps

1. **Declare, in your manifest** (`samples/s39_pharmacy_counter/manifest.json`):
   - **record types the shop fills:**
     - `<PREFIX> Drug Schedule`: one class per axis, with its rules as fields;
     - `<PREFIX> Pharmacist`: user, licence, *valid until*;
     - `<PREFIX> Prescription`, with an item table;
     - `<PREFIX> Premises Licence`;
     - `<PREFIX> Settings`.
   - **one record type only your service writes,** `<PREFIX> Dispensing`, named by a field (`autoname: field:key`) so
     its name can serve as a lock (step 5);
   - **permission rows that say who writes what:**
     - only `<PREFIX> Pharmacist in Charge` writes the pharmacist list;
     - only pharmacists write prescriptions;
     - only `<PREFIX> Integration` writes dispensings;
     - only `<PREFIX> Records Officer`, a role nobody holds until the shop gives it, deletes a prescription or a
       dispensing: laws keep a prescription for years, and a permission row cannot say *not once dispensed*.

     Name the roles with your prefix and the install makes them;
   - **fields on the shop's record types:**
     - a schedules table on Item (one row per axis, with *effective from*);
     - a schedule on Item Group;
     - ⭐ **not** the patient's identity and consent: a field on Customer is read by everyone who reads customers, and a
       permission level does not keep it from the form's change history, the list's group-by count or the link
       search. Put them on a record type of your own, one per customer (a `customer` Link, unique), named by a hash,
       readable only by the pharmacist roles, the integration role and the records officer, with a System Manager row
       of read alone (else the install gives that role every right, and a row with no right is refused). S39 0.1.2's *Patient*;
     - the prescription fields on Sales Order, Delivery Note and Sales Invoice;
   - **sale details** for the prescription number, prescriber, licence and directions. ⛔ Never `required`: a required
     sale detail stops every sale on every till of the site;
   - **two `check` subscriptions** with different down answers:
     - the dispensary's `refuse`: it sells only medicine, online only;
     - the front's `allow_and_flag`.

     Inside one manifest the checker counts them as one POS Profile, so they total 10 s at most (5 s + 5 s);
   - **three `doccheck` subscriptions,** one per record type (Sales Order, Delivery Note, Sales Invoice). Each is
     `on_validate: false` (a draft check is refused on these types) and sends `stock_qty` and the lines' parent links;
   - **two *Days Before* notifications** on the licences' *valid until*, to the pharmacist-in-charge's role;
   - a feed registration naming your integration user, and a help address on each record type.

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
   - the identity fields the schedule needs. Ask the shop *whether* each is set
     (`filters [["name", "=", customer], ["<field>", "is", "set"]]`, `fields ["name"]`), so the value never leaves it;
   - the quantity cap per sale;
   - the prescription: known, this customer's, active, in validity, a fill and quantity left, unchanged since its first
     dispense (a fingerprint);
   - directions and a doctor's name, where the group or schedule asks;
   - the frequency cap.

   Answer `refuse` with one sentence of at most 140 characters, naming the line.

5. **Reserve with the record's name as the lock.**
   - On allow, insert `<PREFIX> Dispensing` named `<an opaque key for the customer>~<next number>`. Never the patient's
     name: a record's name lands in access logs and Desk addresses.
   - Never reserve once the check has run 4 s: the till gives up at 5 s, and a reservation it never sees would hold
     the fill until the day closes.
   - If the insert fails because the name exists (409), another till took that number: read again and decide again.
   - Every dispensing of one patient is thereby decided in turn.
   - Pay pressed again for the same basket keeps its reservation. A changed basket releases it.

6. **Read back what the shop says, never a timer.** At the next decision for that patient:
   - **a reservation becomes *Dispensed*** when a booked POS Invoice carries its `sale_ref` (`custom_mpos_sale_ref`,
     stripped and lower-cased);
   - **it becomes *Released*** when its booked sale is cancelled, or when it was never booked and its POS day (`POS
     Opening Entry`) is *Closed*;
   - **a Desk reservation follows its document's `docstatus`:** cancelled or deleted releases it;
   - **a give-back counts only once its return is booked** (the till's return stores the refund's key in
     `custom_mpos_idempotency_key`).
   - **A document missing from a list is asked for by name.** A 404 means gone. Any other refusal means the shop
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

8. **Answer 503 when the shop cannot be read,** so the till or the Desk applies the declared down answer. Each read
   waits about 2 s; the till cuts the whole check at its 5 s.

## Proof

- **Laptop:** `python3 -m unittest discover -s samples/s39_pharmacy_counter/tests -p 'test_*.py'`.
  - It includes two tills on real threads (exactly one is allowed) and the stand-in shop's 409.
  - `canaries.py` breaks each guarded rule.
- **A bench:** install through the shop's installer, with the service's user holding your role alone plus the card's
  reads. Then run:
  - the prescription line refused for a counter assistant and booked for the pharmacist;
  - no prescription, or an expired one, refused;
  - the last fill refused;
  - an abandoned sale's fill released at day close;
  - a lapsed licence refused;
  - a till return refused;
  - a Desk invoice refused, and an order, delivery and invoice chain spending one fill;
  - the service stopped, so the dispensary refuses and the front lets the sale through.

## Limits to tell the customer

- **The till cannot take or show the patient's identity:** enter it on the patient's record on the Desk. A clerk is
  refused that record whole, but an assignment on it, the customer's Connections count and one engine export still
  tell a clerk something (S39's README, *Limits*).
- **A POS Invoice made on the Desk POS screen, or through the API, is not checked:** a POS Invoice cannot be a document
  check's target.
- **The sentence shows at Pay,** not when the line is added.
- **A day left open holds its reservations.**
- **The item's own *Returnable* tick** refuses a till return before any check runs. This app adds the schedule's rule
  and the Desk credit note.
