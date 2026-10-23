# S39 — Pharmacy counter rules (a check before payment and document checks)

A pharmacy sells medicine under a licence. A prescription line is paid only against a valid prescription for this
customer. A controlled or prescription-only line is sold only by a pharmacist whose licence is in date. A controlled sale
needs the patient's identity. Quantity caps hold, and dispensed medicine is not taken back. The same rules hold when a
sale is made on the Desk.

This app checks those rules at **Pay** on the till, at a return's confirm, and when a sales order, delivery or sales
invoice is submitted on the Desk. Each rule is a record the shop fills: its **drug schedules**, its **pharmacists**, the
**prescriptions** its pharmacist enters and its **patients'** records (identity and consent). Nothing is written in per
country. The
recipe: [`recipes/pharmacy_counter.md`](../../recipes/pharmacy_counter.md).

## What the cashier and the clerk read

| When | What they read |
|---|---|
| **Pay**, a counter assistant, a prescription line | *"This sale can't be paid"* and *"Line 1: AMOX-250: Only a pharmacist may sell this."* |
| **Pay**, a pharmacist whose licence has lapsed | *"… Only a pharmacist may sell this: your licence ran out on 2026-10-21."* |
| **Pay**, no prescription number in **Sale details** | *"… needs a prescription. Add the prescription number in Sale details."* |
| **Pay**, an expired or post-dated prescription | *"… Prescription RX-00012 was valid until 2026-10-01."* (the class's validity, the written day counting as day 1) · *"… is dated 2026-10-25, after today."* |
| **Pay**, every fill used, or this sale over what is left | *"… Prescription RX-00012 has nothing left to dispense."* · *"… has only 9 of this left."* |
| **Pay**, another patient's prescription, or the walk-in customer | *"… Prescription RX-00012 is for another patient."* · *"… needs a named customer, not a walk-in sale."* |
| **Pay**, a controlled line, the customer has no ID on record | *"… needs the customer's national or residence ID. Add it on their patient record on the Desk."* |
| **Pay**, a schedule that needs consent, none on record | *"… needs the customer's consent to keep their records. Add it on their patient record on the Desk."* |
| **Pay**, over the schedule's cap | *"… No more than 20 may be sold at once."* · *"The patient has reached the limit for CD Schedule 2 until 2026-11-11."* |
| a till return, or a Desk credit note, of dispensed medicine | *"… Dispensed medicine cannot be taken back."* |
| **Pay** on the front of the shop, prescription medicine | *"… Sell this at the dispensary."* |
| **Submit** on the Desk, no prescription number | *"… needs a prescription. Add a prescription number field."* |

Everything else is allowed.

## How a fill is reserved, spent and given back

Every sale that dispenses against a prescription, or sells a schedule with a frequency cap, is one record in the shop:
**PP RXC Dispensing**, named by an opaque key for the patient (never their name) and their next number
(`3f9c0a71d2e4b8c6~0007`).

- **Reserved.** The service makes the record when it allows the sale. The record's name is unique, so if two tills read
  the same last number, one of them fails to make its record. That till reads again and decides again, and if the last
  fill has gone, it refuses.
- **It counts at once.** A reserved fill counts against the prescription and the patient's caps from the moment it is
  reserved.
- **It stops counting only when the shop says so,** which the service reads back the next time that patient is checked.
  A document the app's user cannot see is never read as gone:
  - the sale was never booked and its POS day is closed (*Released*);
  - its booked sale, or its Desk document, was cancelled or deleted (*Released*).

  Never on a timer, because a check's approval does not expire. An abandoned sale holds its fill until its day closes.
- **A return gives the quantity back** where the schedule allows returns, but only once the return is booked
  (*Returned*).
- **Pay pressed again** for the same basket keeps the same reservation. If the basket has changed, the old reservation is
  released and a new one is made.
- **On the Desk, a fill is spent once per document chain.** The chain's first document (a sales order, or a direct
  invoice or delivery) is checked and reserves. A delivery or invoice line made from it, carrying its parent's row
  reference, is allowed unchecked, so a clerk can deliver what the pharmacist ordered. A parent's name typed on a line
  without its row is checked like any line. *Pharmacist only* is met by the pharmacist who submitted the first document.
- **A stuck reservation can be released by hand.** A sale the till gave up on holds its fill until its day closes, and
  a sales order closed but never delivered holds its fill until it is cancelled.
  - The pharmacist-in-charge may set that Dispensing to *Released*.
  - The status is worked out from the shop at every check, so a release set by hand on a sale that did book reads
    *Dispensed* again.
  - The service never reserves after 4 s of a check (the till's limit is 5 s).
- **A return gives back** only what moved back into stock (a till return, a delivery's return, or a credit note that
  updates stock), and never twice for the same dispensed quantity.
- **A prescription edited after its first dispense is not dispensed again.** Each dispensing stores a fingerprint of
  the prescription: patient, date, fills and quantities. An edit makes the till refuse it (*"was changed after it was
  dispensed. Enter a new one."*). The record keeps its change history.

## What the shop does

1. **Install the app** from the App library, or paste its manifest into **Retail Extension Package** in Desk. Read what it
   will do, and consent.
   - The install adds the record types *PP RXC Settings*, *Drug Schedule*, *Pharmacist*, *Premises Licence*, *Patient*,
     *Prescription* and *Dispensing*.
   - It adds fields on Item, Item Group, Sales Order, Delivery Note and Sales Invoice, and four sale details (*PP RXC Rx
     Number*, *Prescriber*, *Prescriber Licence*, *Directions*). The five fields it adds on Customer are 0.1.1's, kept
     empty and out of sight: an update may not remove a field.
   - It adds two licence reminders and the roles **PP RXC Integration**, **PP RXC Pharmacist**, **PP RXC Pharmacist in
     Charge** and **PP RXC Records Officer**. Nobody holds the last one until you give it ([How long to
     keep](#how-long-to-keep-and-what-happens-after)).
   - It adds five services, all switched off. Nothing changes at the till yet.
2. **Make the app's integration user** ([integration user recipe](../../recipes/integration_user.md)). Give it the role
   **PP RXC Integration** alone, generate its API key, and choose it on the feed registration **PP RXC Counter**. Then
   give that role a plain **read** on Item, Item Group, Customer, POS Profile, POS Invoice, POS Opening Entry, Sales
   Order, Delivery Note and Sales Invoice (*Role Permissions*), and press **Connect again** on the app's record.
   ⚠ Give that user **no User Permissions**: a booked sale the app cannot see cannot be counted.
3. **Give your people their roles.** Pharmacists get **PP RXC Pharmacist**. The pharmacist-in-charge gets **PP RXC
   Pharmacist in Charge**, adds each pharmacist under *PP RXC Pharmacist* (user, licence number, *valid until*) and enters
   the premises licence. Only that role writes the list, so nobody adds themselves. A row ticked *delegate* does not
   sell pharmacist-only medicine.

   **The patient's record.** A patient's national or residence ID, date of birth, authority to possess and consent go
   on their **PP RXC Patient** record, one per customer, entered on the Desk by a pharmacist. Only **PP RXC
   Pharmacist**, **PP RXC Pharmacist in Charge**, **PP RXC Records Officer** and the app's integration user read it,
   so the clerk who serves a customer at the Desk never sees it: there is nothing to set up. The site's **System
   Manager** reads them too (form, list, report view, print view) but cannot change or delete one: the shop's installer
   gives that role a row on every record type, and a row needs at least one right, so this app gives it read alone. Never give another role a right on *PP RXC Patient*. The health and data-protection laws of the UAE, Saudi Arabia, Kenya, Jordan, Mexico and
   Nigeria limit these fields to the staff whose work needs them. ⚠ The till cannot take or show them: enter them on the
   Desk. Open the record from the *PP RXC Patient* list, filtered by the customer; it has no link on the customer's
   form, because a count there would tell everyone who reads customers that the person is a patient.

   **Updating from 0.1.0 or 0.1.1** (the patient's fields were on Customer):
   - Update the app first. Customer's five fields keep their values (and any level you gave them), and show only while
     they hold a value; their labels end *(moved)*.
   - As a pharmacist, filter the *Customer* list by each field *is set*. For each customer found, make their *PP RXC
     Patient* record with the same values, then clear the five fields on the customer and save. Until you do, the till
     refuses a sale that needs one of them: the app reads only the patient's record.
   - Then, as the site's *Administrator*, open the **Version** list, filter *Document Type* = *Customer* and *Data*
     like `%pp_rxc_%`, and delete those rows: each customer's change history still holds the values, and clearing a
     field adds one more row holding them. Only the Administrator deletes a change history.
   - The level and its grants on *Customer* (0.1.1's step 3) can then go: the app's integration user no longer reads
     those fields.

4. **Make your drug schedules** (*PP RXC Drug Schedule*), one per class per classification axis, each with its rules. Set
   them on your medicine items (*Drug schedules*: one row per axis, with its *effective from*) or on an item group
   (*Drug schedule*), which covers the groups below it. For items with variants, add *Drug schedules* in **Item Variant
   Settings** so variants copy it. Make the settings record **Default**: your hours from UTC, and any walk-in customers
   besides each POS Profile's own.
   - **Consent.** Tick *Needs the patient's recorded consent* on a schedule whose prescriptions your law lets you keep
     only with the patient's consent:
     - **Egypt:** written and explicit, for any prescription record no law requires (Law 151 of 2020, Art. 12);
     - **Mexico** and **Saudi Arabia:** for what goes beyond dispensing, such as an image kept or a history used for
       later sales (Mexico's LFPDPPP arts 8 and 9; Saudi Arabia's PDPL Art. 6(2), Implementing Regulation Art. 11(2)(a));
     - **Kenya,** if your pharmacy is a healthcare provider under the *Digital Health Act* (s. 31);
     - **Jordan,** likely not for dispensing records: the data-protection law lets a licensed medical professional
       keep health data without consent (Law 24 of 2023, Art. 6(a)(2)), and the Public Health Law lists pharmacy among
       the medical and health professions a minister licenses (Art. 5(a)–(b)). That is our reading, not a ruling: the
       law does not separate *medical* from *health*. Tick it if you want the consent anyway. Sending a claim to a
       private insurer, or a recall trace to a manufacturer, needs the patient's consent and a record of it whatever
       the profession (Art. 14(أ)–(ب)); those are the payer and recall apps' sends, not this app's.

     The consent goes on **the patient's** *PP RXC Patient* record (the prescription's customer's), with the day it was given (a day
     after today counts as no consent) and who gave it: the patient, or for a child their parent or guardian. Record it before you enter the prescription: the
     app checks it at Pay and on the Desk, never when a prescription is saved. Keep the signed form where *Consent given
     by* says. When a patient withdraws consent, clear the date: their next sale under that schedule is refused (a Desk
     delivery or invoice made from an order already submitted still goes through). What a law makes you keep stays for
     its period ([How long to keep](#how-long-to-keep-and-what-happens-after)); what you kept only on their consent
     (in Egypt, a record no law requires; in Mexico and Saudi Arabia, an image or a history kept beyond dispensing)
     has no basis left: delete it, as *How long to keep* says. The app
     writes no consent text: yours is your own.
   - **The UAE:** tick *Needs the customer's national or residence ID* on every schedule. The law wants the ID on every
     health record, except in emergencies and other cases a Ministry decision sets (Federal Law 2 of 2019, Art. 21).
     Those exceptions are not built in: the till refuses a sale with no ID on a schedule that needs it.
     - A narcotic prescription never repeats, and each is kept marked with its dispensing date and its register entry
       number (Federal Decree-Law 30 of 2021, Art. 37). On your narcotic schedule set *Most fills a prescription may
       authorise* to **1** (⛔ never 0: 0 means no cap) and *Most dispensings of one prescription* to **1**, and have
       the pharmacist tick *Original retained at the pharmacy* on each such prescription, which also holds it to one
       fill. The entry number is the register's.
     - Controlled and semi-controlled habit-forming products do not repeat either, unless the prescriber marks the
       prescription so (Federal Decree-Law 38 of 2024, Art. 79): set *Most fills* to 1 on those schedules, and enter a
       higher *Fills authorised* only when the prescription says so.
   - **Saudi Arabia:** controlled prescriptions are dispensed through SFDA's **Raqeeb** platform, on paper only while it
     is down (SFDA *Procedures and Controls*, 2026, Art. 11(1)). A prescription entered in this app is your shop's
     working copy for the counter's rules, not the lawful record (our reading); the app does not connect to Raqeeb.
   - **Jordan:** a special (controlled) prescription that anyone but its prescriber has struck out or amended, signed and
     stamped, is refused (JFDA *Instructions on Medical Prescriptions and Registers*, 2025, Annex 7 (خ); read from the
     page image). That is the pharmacist's check at the counter: the app does not see the paper.
   - **Egypt:** Decree 44 of 2026 puts benzodiazepines, pregabalin, codeine, zolpidem and others in Schedule 3, Section
     IV, under some of the narcotics restrictions. Make a *Schedule 3* drug schedule and set it on those items. Its
     dispensing rules (prescription, validity, register) are not yet read from the law: set them with your adviser.
5. **Narrow the till services before switching either on.**
   - On **Pharmacy counter rules (dispensary)**, choose the dispensary's POS Profile.
   - On **(front)**, choose the shop's other profiles.

   A check switched on with no POS Profile answers every till.
6. **Switch the services on.** Read what each is sent, tick the consent and switch it on, the three Desk services too.
   - **A POS Profile holds at most three checks, 10 seconds together.** This app takes one on each profile (5 s),
     leaving room for the age check (S37) and one more.
   - **A pharmacy sells offline nothing this app must check:** keep the dispensary's POS Profile on *Offline selling:
     Disabled*.

**Where it shows.**
- **At the till:** a refusal at **Pay**, or at a return's confirm. The prescription number goes in the basket's
  **🗒 Sale details**.
- **On the Desk:**
  - prescriptions, entered by a pharmacist before the sale;
  - dispensings, with their status;
  - the pharmacist list and the premises licence;
  - each customer's prescriptions and dispensings, under *Pharmacy* on their record;
  - each patient's record (*PP RXC Patient*), for the pharmacist roles only;
  - a refusal at **Submit**.

**What leaves the shop.**
- **At Pay, and before each refund the till pays,** the till sends the priced basket: the cashier's user, the customer
  and their group, the sale details (the prescription number among them), the POS day, each line's item, group,
  quantity and unit, and, on a refund, the original sale.
- **At each Desk submit,** the shop sends the fields each Desk service names.
- **The service reads back with the integration user's key:**
  - the prescriptions named and the operator's pharmacist record;
  - whether each patient field the sale needs is filled in on the patient's record. The shop answers yes or no: the
    ID, date of birth, authority and consent values never leave it;
  - the patient's dispensings (which medicine, how much, when);
  - the schedules and the items;
  - the sales, days and documents the patient's dispensings name;
  - every POS Profile's default customer.
- **It writes only its own Dispensing records.** It keeps nothing between calls but a minute's copy of the settings,
  schedules, item groups and profiles' default customers. Prescriptions, patients and dispensings stay records in your
  site.
- ⚠ **The prescription number reaches every check on the POS Profile**, the age check included, as a sale detail: a
  reference, not clinical content.

**Limits, said plainly.**
- **Who reads a patient's record.** Only the pharmacist roles, the Records Officer and the service's user (step 3).
  On our test bench a Desk clerk who reads customers was refused the record whole: its form, and so its change
  history, its list, report view and print, and every filter on its ID (the API's and the Desk's lists, the count, a
  single value, the list's group-by count on a field, the link search). The site's *System Manager* reads patients'
  records (read alone, measured: form, list, report view and print view), can give any role a right on them, and
  reads every record's change history in the **Version** list: keep that role few. Three framework paths still tell a clerk something, each recorded for the team that owns it:
  - **an assignment:** once a patient's record is itself assigned to someone (*Assign To*), the list's group-by count
    by *Assigned To* answers a clerk's *starts with* filter on the ID, because it counts assignments without asking
    whether the clerk may read the record. Don't assign patient records; an assignment on the customer tells nothing
    (the record is named by a code, never by its customer);
  - **the customer's Connections:** the *Pharmacy* group on a customer's form counts their prescriptions and
    dispensings for anyone who reads the customer. It shows that the person has had prescriptions, never which;
  - **one engine call** returns any record whole to any signed-in user, a patient's record included.
- **The till never shows a patient's fields** and cannot take them: enter them on the Desk, never on a till field rule.
- **The regulated register app** ([S41](../s41_regulated_register/README.md)) prints the ID into Saudi Arabia's and
  Abu Dhabi's books from the patient's record: its register must read it with its own rights, or a line written by a
  clerk prints it empty.
- **A POS Invoice made on the Desk POS screen, or through the API, is not checked:** a check before payment holds only
  at the till's own doors, and a POS Invoice cannot be a document check's target. Sell medicine at the till, or on a
  Sales Invoice.
- **The prescription image is kept in your site, private when attached on the Desk:** the upload opens with its lock
  closed, because neither the field nor the record type makes attachments public. A person can open the lock, and a
  file attached through the API is public unless the call says it is private. Keep the lock closed: a public file is
  read by anyone who has its address. The app cannot hold it private.
- **When the service is down,** the dispensary stops taking payment and the front till lets sales through, flagged on
  *Sales to review*.
- **The till holds a check's answer for the basket, not for the cashier who asked.** A pharmacist's answer stays valid
  for that basket under that sale's key. We have asked for it to be bound to the operator too.
- **The front of the shop sells offline unchecked.** Keep prescription and controlled stock only in the dispensary's
  store, so the front cannot sell it online either, or turn offline selling off on every profile that sells medicine
  until the till can keep chosen items online only.
- **Whoever may write an Item may change its *Drug schedules* rows.** Removing a row removes that drug's rules. Keep
  Item writing to your item managers; every change is in the item's history.
- **The pharmacist-in-charge's write on a Dispensing reaches its whole record.** Only the status is meant to be set,
  and every change is kept in the record's history.
- **A customer renamed or merged after a dispensing:** their dispensed prescriptions are refused as *changed*. Enter
  new ones.
- **A reclassification** (a new schedule row on its date) starts the new schedule's frequency count from that day.
- **Hosting:** CitiXsys hosting runs services in the United States. This app reads prescriptions and dispensing
  history, so run it in your shop's own region: the service is a container or a function you deploy yourself, from this
  folder.
- **A POS day left open holds its reservations,** so close every day. A Desk draft left after an allowed submit failed
  holds its fill until it is submitted or deleted.
- **The engine's own *Returnable* tick on Item** (off by default) already refuses a till return of the item before any
  check is asked. This app adds the schedule's rule, so a medicine ticked returnable by mistake is still refused, and
  the Desk credit note.

## How long to keep, and what happens after

**No role that works the counter can delete a prescription or a dispensing.** The pharmacist-in-charge could before
version 0.1.1; a permission is the same for every record of a type, so *not once dispensed* cannot be one. A
prescription entered by mistake is set *Cancelled*, and a cancelled prescription never sells. The site's
*Administrator* still deletes anything, and a *System Manager* can give any role delete in **Role Permissions
Manager**: keep both few.
- ⚠ **Updating from 0.1.0:** if your shop ever changed the permissions of *PP RXC Prescription* or *PP RXC Dispensing*
  in Role Permissions Manager, your own rows replace the app's, and the update cannot take delete from the
  pharmacist-in-charge. Open each in Role Permissions Manager and press **Restore Original Permissions**, then make
  your change again.
- ⚠ **Never uninstall this app while a period runs.** An uninstall removes its record types, and every prescription and
  dispensing with them. Take the export it offers and keep it as long as the longest period.

**The periods the laws set for a prescription** (read from their texts, October 2026):

| Market | Keep a prescription | Counted from |
|---|---|---|
| UAE | 25 years (Federal Law 2 of 2019, Art. 20; in Dubai all prescriptions, controlled drugs included, DHA PP-12) | the patient's last health procedure |
| Egypt | 10 years, the controlled-drug prescriptions and the books (Law 182 of 1960, Art. 31) | the book's last entry |
| Saudi Arabia | the original 3 years; the pharmacy's prescriptions register 5 years (Executive Regulation, Art. 21) | not stated in the text read |
| Ghana | 2 years (Act 489, s. 32(b)) | the full dispensing |
| Kenya | 2 years, a prescription that is not repeatable (Rules, r. 6(6)) | not stated in the text read |
| Nigeria | at least 2 years, the controlled-drug records (reg. 26) | the prescription's date or the last entry |
| Jordan | at least 5 years, the narcotic records, destroyed in the inspector's presence (Law 12 of 2013, Art. 74) | the last entry |

Elsewhere no prescription period was found in the laws read: keep as long as your pharmacy law and your register need,
and no longer, since a data-protection law ends the keeping when its purpose ends. Three more rules from those laws:
- **Egypt:** what you keep only because a law says so (the 10 years above) is held unreadable and not identifying,
  and erased when the period ends (the Executive Regulation, Decision 816 of 2025, Art. 3);
- **Nigeria:** where no law sets a period, 6 months after the purpose (GAID 2025, Art. 49(3)), so a prescription that
  is not for a controlled drug;
- **Kenya:** what is sent to the national Shared Health Record is kept 20 years (*Digital Health Act*, s. 25(1)).

A register book's own period is the register app's.

**After the period, the shop acts; nothing runs on a timer.**
1. Where your law says how a record is destroyed, do that first: in Saudi Arabia a three-member committee the director
   appoints, with minutes (Executive Regulation, Arts 21(3) and 22(7)).
2. Give a person **PP RXC Records Officer** for the act. It reads, and deletes, prescriptions and dispensings, nothing
   else.
3. Delete a prescription and all its dispensings in one act, the dispensings first (a prescription the dispensing names
   first cannot go before it). ⛔ Never a dispensing whose prescription stays: its fill would count again. A dispensing
   names only the first of the prescriptions its sale used; look for the others in its lines, and keep the dispensing
   until the last of their periods ends. An attached image goes with its prescription.
4. When the last of a patient's periods has ended, the Records Officer deletes their *PP RXC Patient* record (ID, date
   of birth, authority, consent). No other role can.
5. The Desk still holds copies: each deleted record in *Deleted Documents*, which a *System Manager* deletes, and
   each record's change history, the patient record's included, with its old values, which only the site's
   *Administrator* deletes.
6. The prescription number, prescriber, licence and directions also stay on the sales orders, deliveries and invoices
   that carried them, and on the till's sales as sale details. They are your sales records: what your law lets you keep
   of them is yours to decide.
7. Take the role back.

A patient's request to erase does not shorten a period a law sets in seven of the eight markets read. Egypt's law lists
no exception to erasure: ask your adviser there.

## What is in the folder

| File | What it is |
|---|---|
| `manifest.json` | the record types (the patient's identity and consent on *PP RXC Patient*), fields, sale details, four roles, two licence reminders, the feed registration, and five services: two checks before payment (dispensary `refuse`, front `allow_and_flag`) and three document checks (Sales Order, Delivery Note, Sales Invoice; `refuse`), each installed switched off |
| `rxrules.py` | the pure core: the signature check (`verify`), the shapes (`sale_context`, `desk_context`), an item's schedules (`schedules_for`, `strictest`), prescriptions and fingerprints, the dispensings that count (`counts`) and their statuses (`resolve`), and the rules (`decide`) |
| `service/app.py` | the service, standard library only: five routes, `GET /health`, the app template's handshake for many shops; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the rules; the service against a stand-in shop (`fake_shop.py`), two tills on real threads included; the calls and answers against the published contracts; the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s39_pharmacy_counter/tests -p 'test_*.py'
```
```bash
python3 samples/s39_pharmacy_counter/tests/canaries.py
```
```bash
python3 samples/s39_pharmacy_counter/service/app.py samples/s39_pharmacy_counter/service/.env.local
```

**Settings, one shop** (`service/.env.local`, never committed):
- `IVN_SECRET_DISPENSARY`, `IVN_SECRET_FRONT`, `IVN_SECRET_DESK_ORDER`, `IVN_SECRET_DESK_DELIVERY` and
  `IVN_SECRET_DESK_INVOICE`: each handed back at install as `pp_rxc:sub:<key>`;
- `IVN_SHOP_URL`;
- `IVN_SHOP_KEY` (`<api key>:<api secret>` of the integration user);
- `PORT`.

**Many shops** (the [app template](../../tools/app_template/README.md)'s handshake): `IVN_LIBRARY_APP` and a store
(`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`). `RXC_PREFIX` names the record types, fields and sale
details (default `PP RXC`).

## Technical notes

- **An item's schedules:**
  - per classification axis, the item's own row effective most recently (a row dated in the future waits for its date);
  - else its template's rows (a variant copies only the fields *Item Variant Settings* lists);
  - else the nearest item group's schedule.
- **The strictest of an item's schedules applies:** a need on any schedule applies; validity, fills and caps take the
  least that is set; returnable and give-back hold only when every schedule says so.
- **Quantities** are compared in the item's stock unit. A till line in another unit is converted with the item's own
  units, and a unit the item does not convert is refused rather than guessed.
- **Prescription numbers:** the record's own number, or its paper reference when exactly one prescription of this
  customer carries it. Up to five numbers in one detail, separated by commas.
- **A fill** is a quantity. A sale dispenses at most one fill's quantity of an item, and a part fill leaves the rest.
  - The schedule's *most fills* caps what a prescription authorises.
  - *Most dispensings* caps the occasions, however small each one.
  - A prescription marked *retained* is dispensed once.
  - A class with *one drug per prescription* refuses a prescription naming two items.
- **Validity:** the written day counts as day 1, so a 3-day class sells on the written day and the next two days. A
  prescription dated after today is refused.
- **The frequency cap** counts the patient's dispensings of that schedule in the last *n* days, this sale included.
- **What the shop says** is re-read for every reserved fill and every dispensing of the last 400 days, whatever its
  status: a sale cancelled since, or a status set by hand. Only the newest dispensing of a sale or document is matched
  to its booking; an older one, from an earlier press of Pay, is released.
- **The shop cannot be read** (no answer, an error, a refused key, not records, a check with no sale reference): 503,
  and the subscription's down answer applies. Each read waits at most 2 s, and nothing is reserved after 4 s. The till
  cuts the whole check at its own 5 s.
- It logs one line per call: the route, the status and the milliseconds, never the body.

### What was proven where

- **On the laptop:** the tests and canaries above (119 tests, one of them replaying a recorded bench run when one is
  given; 77 canaries, each RED with its baseline passing).
- **On our test bench** (2026-10-22, the iVendNext POS app at `84185344`, the engine at `dc65d832`):
  - **The setup.** The app was installed through the shop's own installer: five services, switched off, with the
    declared down answers. The service's user held only the app's role and the card's reads, and every read and write
    the service makes was made as that user first.
  - **The till: 11 of 11, through the till's own calls** (the check, the card push, the booking, the return confirm),
    in POS days that were all closed after:
    - a counter assistant was stopped on a prescription line and the pharmacist was served;
    - no prescription, and a controlled-drug prescription written 40 days earlier (its class allows 30), were refused;
    - a two-fill prescription booked twice and was refused the third time;
    - a fill answered on one sale refused a second sale until the first booked;
    - an abandoned sale held its fill until its day closed, then the fill sold;
    - a pharmacist whose licence ran out yesterday was refused;
    - the booked prescription sale was refused at the till's return confirm, and a returnable shelf medicine's return
      passed;
    - with the item's own *Returnable* off, the till refused the return itself before asking;
    - another patient's prescription, the walk-in customer, a controlled sale to a customer with no ID on record, and a
      controlled quantity over its cap were each refused, and a paper reference found its record;
    - on the front profile, a prescription line read *"Sell this at the dispensary"*, a shelf medicine over its cap of
      2 was refused, and 2 were allowed;
    - the 33 calls the till sent hold the published contract.
  - **The Desk: 2 of 2, each in its own request.**
    - A sales invoice with no prescription number, one on a spent prescription, one a clerk began, and a credit note of
      dispensed medicine were each refused at Submit.
    - The pharmacist's sales order reserved one fill. The clerk's delivery from it and the invoice from the delivery
      went through unchecked. A further invoice on that prescription was refused, and one dispensing stood for the
      chain.
  - **The down answers.** With the service stopped, the dispensary refused (*"did not answer"*) and the front let the
    sale go on.
  - **The uninstall** left the schema as found, the sale details kept and switched off, and no permission row of the
    app's role was left.
- **On our test bench again for 0.1.1** (2026-10-23, the same builds; 32 of 32 checks):
  - **The update.** Version 0.1.0 was installed, the three identity fields were given level 2 as step 3 says (level 1
    is held there by *Retail Cashier*, *Sales User* and *Sales Master Manager*), and the app was updated to 0.1.1
    through the shop's installer. The fields kept level 2, the ID's new description was written, the
    pharmacist-in-charge lost *delete* on prescriptions, and the Records Officer role was made.
  - **The till and the Desk, with the fields at level 2:** all of the 0.1.0 walk above again, the controlled sale's ID
    check included, with the service's user reading at that level. Without that grant, the shop answered the service
    neither way and the service refused the controlled sale (*"did not answer"*), as step 3 says.
  - **Who reads them:** a Desk clerk who reads customers saw none of the five fields on the form, the list, the report
    view or the print, a clerk's edit of one was ignored, and a clerk's filter on the ID was refused by the API's and
    the Desk's lists, the count and a single value; the pharmacist read and wrote them. The form's change history,
    the group-by count and the link search still reach the clerk (*Limits*).
  - **Consent:** with *Needs the patient's recorded consent* ticked, Pay was refused (*"needs the customer's consent to
    keep their records"*) until the pharmacist entered the day on the patient's form, then the sale was allowed.
  - **Deleting:** the pharmacist-in-charge and a pharmacist were refused. On a dispensed prescription with an image,
    the prescription could not go before its dispensing; the Records Officer deleted the dispensing, then it, and the
    image went with it. A *System Manager* deleted the *Deleted Documents* copies and was refused the change history,
    which the *Administrator* deleted.
  - **A shop's own permission copy:** with the prescription and dispensing permissions changed on 0.1.0, the update
    left the pharmacist-in-charge's delete in the shop's copy; *Restore Original Permissions* on each left only the
    Records Officer deleting.
  - **Filters:** a clerk's filter on the ID was refused by the API's and the Desk's lists, the count and a single
    value; the group-by count and the link search answered a *starts with* filter that matched and gave nothing for
    one that did not (*Limits*).
  - **Timing:** the dispensary's checks took 164 ms at the median and 395 ms at the slowest, each patient field asked
    both ways.
  - **Customize Form** on Customer refused to save with the app installed (*Limits*, step 3), so the levels were set on
    each Custom Field record.
  - **The teardown** put Customer's permission rows back exactly as found and left no setting on its fields.

## Make it your own

A partner's version of this app usually changes:
- **the market's schedules and their rules:** loaded as records, no code;
- **a rule:** a pharmacist's exception with a reason, a fixed price on medicine, an e-prescription link;
- **the words** the cashier reads (`rxrules.py`, `decide`).

The service takes its prefix from the setting `RXC_PREFIX`, so
`python3 tools/manifest/rename.py samples/s39_pharmacy_counter/manifest.json --prefix "ACME RXC"` renames the manifest
and the hosting order, and the code needs no change for the name. A shop's schedules, pharmacists and settings move to
your copy with `tools/deploy/copy_records.py`
([Make one of our apps your own](../../recipes/make_it_your_own.md)).
