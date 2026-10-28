# S41 — Regulated stock register (`pp_rsr`): each market's books as data

*The steps for any register, this one or your own: [the regulated stock register recipe](../../recipes/regulated_register.md).*

*Start from this sample: `python3 tools/manifest/start.py s41_regulated_register --prefix "ACME RSR"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

A retailer selling regulated stock keeps a legal register an inspector can ask for at any time: a pharmacy's poisons and controlled-drug books, a liquor or tobacco register, a duty-free ledger. Today most keep it on paper. This app keeps it for them: **one app for any regulated stock**, whose books (which book, which items, which movements, which columns, which printed layout) are a **data set** per market and vertical. A second market, or a second vertical, is a new data set file with no code change.

The first data set is **Kenya's three pharmacy books**: the Poisons Book (Rules Schedule VIII Form 16), the Prescription Book (Act s. 31(1)(b)) and the NPP Ledger Book (PPB NPP Guidelines Annex II), with the routing Kenya's law asks for: a supply on prescription goes to the Prescription Book, **not** the Poisons Book (s. 31(2)); every movement of a controlled drug goes to the NPP ledger as well. Seven more markets follow as data sets, with no code change: Jordan, Nigeria, the UAE's Abu Dhabi, Saudi Arabia, Egypt, Ghana and Mexico ([the other markets](#the-other-markets)).

⚠ **Every layout here is a starting point, not certified for the country.** It is read from the instruments named in the data set, and each print says so. A partner certifies it for a market, changes it, or adds a market.

**When to use it:** the retailer's law names a book and its columns, and the book must hold every sale or receipt of certain stock, in order, never edited.

## On the register door

The book itself is a legal record: one line written in the **same save** as the sale or the receipt, numbered without a gap, with a running balance two tills cannot break, and never edited. An app installed from a manifest cannot write such a record, so the POS app carries a **register door** for it (POS 2.1.0 or later: [its page](../../contracts/pages/register_books.md)), and this app declares its books to that door. ⚠ **Install the pharmacy counter app first** ([S39](../s39_pharmacy_counter/), 0.1.3 or later): the books read its drug schedules, prescriptions and patient records, and the door refuses, at install, a book naming a field the site does not have.

`manifest.json` (0.2.0) installs:

| Part | What it is |
|---|---|
| `register_books` | each market's books, as data. This sample's catalogue installs every market's books **switched off**: the retailer switches on its own market's ([a retailer's own copy](#one-retailer-its-own-markets) installs only its own markets' books, also switched off: an update never switches a book) |
| `print_formats` | each book's print on the register period, drawn from the door's print: its pages, an official book's sheets at the authority's page and line, the balance before an entry, an erased or hidden person's details said in their place, and the period's close. Jordan's, Saudi Arabia's, Egypt's and Abu Dhabi's print right to left, the door's words in Arabic (Abu Dhabi's own labels are the Standard's English words). Each print is named by its data set's and book's ids (*PP RSR ke_pharmacy poisons_book*). And the **purchaser's slip** of a Poisons Book sale, printed from the sale in Desk |
| `notifications` | a reminder seven days before each return to the regulator is due |
| `reports` | the register's lists: *PP RSR Register entries* (filter by book, store and dates), *PP RSR Losses and disposals*, *PP RSR Counts due after a loss*, *PP RSR Periods open* (a return is sent for each period; and *PP RSR Stock counts to watch*, on Stock Reconciliation) |
| `number_cards`, `dashboards` | the dashboard **PP RSR Register** of open tasks: entries entered late, entries incomplete, entries below zero, counts due after a loss, periods open (the current one included, until its count role signs it off). Each card opens its list |
| `custom_fields`, `sale_attributes` | the register's own columns on the Desk sale and delivery (a collapsible *Register details* section) and as the till's sale details |
| the role and the workspace | **PP RSR Register Approver**, each book's count role (it reads, prints and counts the books, and reads a person's details on them), and the workspace *PP RSR Regulated stock register*, which says what no manifest can install: the daily print, and erasing a person's details once a book's retention has passed |

## A data set

`datasets/ke_pharmacy.json` is the whole of Kenya. A data set says:

| Key | What |
|---|---|
| `id`, `title`, `jurisdiction`, `vertical`, `sources` | which market and trade it is, and the instruments it is read from |
| `certified`, `notice` | `0` and the notice every print carries, until a partner certifies the layouts |
| `details` | up to six columns of the book that are neither on the line nor the authority's: each a key, a label and a type, and where the door reads it. `person: 1` says the detail names a person (the purchaser, or a third person such as a certificate's giver), whose details the door erases once the book's retention has passed; a detail read from the customer's records, or an age, is a person's without it. `type: "Age"` with a record lookup of a date of birth prints the age in whole years at the movement's date. `own: 1` makes it this app's Desk field (`pp_rsr_<key>`) and, unless `till: 0`, a sale detail every till offers (`PP RSR <Key>`): keep the till's to what the counter fills often (Kenya: occupation, purpose, the prescriber's address). Or another app's sources: `pos_sale_detail` and `desk_field` (Abu Dhabi's dose, the counter-rules app's directions). Or `record`: one value of a record, `{"doctype", "match", "field"}`: `match: "customer"` reads the Customer the moving document names (the buyer, not always the patient) (a sale's or a delivery's; a receipt or a stock entry has none, so the column is empty), `match: "customer_link"` the one record of another type whose Link field `customer` names that Customer (a record the customer's own readers need not read: the counter-rules app's patient record; none, the column is empty), `match: "user"` a record named by the line's dispensing user (the dispenser's licence: the counter-rules app's Pharmacist) (Saudi Arabia's ID number: `{"doctype": "PP RXC Patient", "match": "customer_link", "field": "id_number"}`). With none of these, the column prints empty for the retailer to write in |
| `print_language` | the language its books print in (`ar` prints right to left); the print's own words are the door's, in that language |
| `authority` | where the authority columns come from: a prescription, a permit, a boarding pass (the till's sale details, the Desk's fields, and the dispenser's licence from a record) |
| `books` | each book: its title, form and citation; its items (`classes` or `item_groups`); for classes, its `class_source`: the axis it reads, from an Item field or a dated table of schedules on Item (the door copies the class into the line when it writes it, so a reclassification never rewrites history); **up to three routing conditions, all of which must hold** (`=`, `!=`, `>`, `>=`, `<`, `<=`, `is set`, `is not set`, on a column of the line: the POS app's save-rule form); numbering per book and store or per drug; a running balance or none; the market's correction mode; retention in years; for a book with a periodic return, `period_months` (1, 2, 3, 4, 6 or 12: periods run from 1 January) and `return_due_days` (the days after a period's last day its return is due; `0` where the law names no day, so the reminder falls on that day); the medium (`system_of_record`, `printed_book`: its signed printed pages are the book, `official_book`: printed into the authority's own book, or `regulator_system`: the authority's own system is the record of law, and this one its working register); `purchaser_slip: 1` where the purchaser signs each entry (a slip printed from the sale); the columns Desk may not leave empty; and its printed columns in order |

A column prints one or more of the line's columns (`movement_date`, `item_name`, `qty`, `counterparty`, `authority_no`, `balance` …, the door's line) or a declared detail (`detail:occupation`), joined with ` · `. `when: "In"` or `"Out"` prints it only on receipts or only on issues (the NPP ledger's two halves); `group` prints a band over the column (a form's received and issued halves); a book that keeps a balance may print `balance_before`, the balance before the entry, which the door works out; `mark: 1` leaves room for a signature on the printed page; `in_colour` prints a receipt's received half (its `when: "In"` columns) in a colour (Kenya: red ink, s. 8.1(i)).

`build.py`'s `check()` is the format: it refuses `in` (a list of classes is the book's `classes`), a fourth condition, a comparison on a date or time column of the line or a declared `Date` detail (the condition form compares a date as text, or as the number 0, so a condition on one can only be `is set` or `is not set`), a column the line does not have, a detail's key it does not know, a record lookup without its three keys, a period that does not divide the year, markup or template text in any label, and the rest, each in words. `routing.py` models which books a line enters, so you can test a data set before the door is installed.

## Kenya's three books

| Book | Takes | Routing | Numbering · balance | Correction | Kept |
|---|---|---|---|---|---|
| **Poisons Book** (Form 16, 9 columns) | Part I poisons (the poisons axis) | a sale (`kind = Sale`) with **no prescription** (`authority_no is not set`) | per store · none | a single strike-through, signed (NPP Guidelines s. 8.1(j)) | 2 years (Rules r. 21) |
| **Prescription Book** (s. 31(1)(b); no form prescribed: its four cited particulars) | the same | a sale **on prescription** (`authority_no is set`) | per store · none | the same | 2 years |
| **NPP Ledger Book** (Annex II, 10 columns, a page per drug headed by the establishment and its address) | controlled drugs (the controlled axis) | every receipt and issue | per drug · running balance | the same | 5 years (s. 8.1) |

So a prescription supply of pethidine (a Part I poison on one axis, a controlled drug on the other) enters the Prescription Book **and** the NPP ledger; a counter sale of a Part I poison enters the Poisons Book only; a transfer, an issue or a loss of a poison enters no sales book.

⚠ **The two poisons books are kept as printed books.** Electronic records are cited for NPP records only (Guidelines s. 8.1): print the day's pages, sign them, and keep them as the book; each print of those two books ends with a line for that signature. Form 16 also asks for **the purchaser's** signature, given at the sale: print the sale's **purchaser's slip** in Desk (the print format *PP RSR ke_pharmacy poisons_book slip till* on the till's sale, *… slip Desk* on a Desk sale), have the purchaser sign it, and keep it with the book's printed pages. The till prints no slip of its own.

⚠ **The classes are the retailer's.** `KE Part I Poison` and `KE NPP`, and the axes `KE Poisons` and `KE Controlled`, are working names of the counter-rules app's drug schedules, read from its dated *Item Schedule* rows on Item (`pp_rxc_schedules`: `schedule`, `effective_from`), or from the Item Group's `pp_rxc_schedule` where an item has no row; the axis is the schedule's own `axis`. Rename them in the data set to the retailer's own. The door refuses, at setup, a declaration naming a field or table that does not exist. ⚠ Whether every controlled drug is also a Part I poison is not cited (Kenya's narcotics Act, Cap. 245, was not read): iVendNext gives each drug its schedule on each axis.

⚠ **One prescription per sale.** The till's sale details belong to the whole sale, so a basket holding a poison on prescription and another sold without one would put both in the Prescription Book. The counter-rules app refuses such a line (its schedule's tick *Sold in a sale of its own when not on the prescription*): tick it on the Part I poison schedule, and the cashier sells the other as a sale of its own.

## The other markets

Each is one file in `datasets/`. Jordan's and Nigeria's columns are their printed forms, read off the form images; the others are the data their law lists, in its order, because no form is printed. Labels are the instrument's own words, Arabic or Spanish where the instrument is; where a label adds a word (a group, a letter, Abu Dhabi's *brand and generic name* from s. 7.7, Mexico's entry columns), the data set's notice says so.

| Market | Books | Takes · routing | Numbering · balance | Correction | Kept | Medium |
|---|---|---|---|---|---|---|
| **Jordan** (JFDA Instructions 2025) | **Form 9** narcotics and psychotropics, 13 columns; **Form 8** Schedule 10 preparations, 9 columns | Schedules 1–9 · Schedule 10 (Law 23/2016 Art. 2) · every receipt and issue | per drug, a page each · running balance | reversing line (not stated: the strictest) | 5 years · 2 years | the book received from JFDA, or a JFDA-approved system (Art. 7, 11) |
| **Nigeria** (Dangerous Drugs Regulations, First Schedule) | **Part A** (obtained) and **Part B** (sold or supplied) for six of reg. 18(1)(b)'s classes and one for the drugs Part III applies to by Order (amidone, pethidine …): 14 books. Codeine and dionin have none: the Modified Form Regulations take them out of reg. 18 for a retailer | Part A every movement in (`direction = In`), Part B every movement out (`direction = Out`): reg. 18(1)(a)'s *all dealings* | per store · none | dated marginal note, reg. 18(1)(f) | 2 years, reg. 26 | not stated: signed printed pages |
| **UAE, Abu Dhabi** (DOH Standard 2021) | **PH 20** narcotic, **PH 17** psychotropic and semi-controlled | every movement (s. 3.6.1, 3.6.3) | per store · running balance | reversing line, s. 7.3 | 25 years (s. 7.4 keeps the record 5; the UAE keeps health data 25, Federal Law 2/2019 Art. 20) | DOH's own book (s. 3.6) |
| **Saudi Arabia** (Executive Regulation Art. 22) | one register **per drug**, 18 columns lettered as Art. 22(3) | narcotics and psychotropics · every movement | per drug, a page each · running balance | signed amendment, Art. 22(4) | 10 years, Art. 22(6) | signed printed pages until SFDA verifies a system (Art. 22(8)) |
| **Egypt** (Law 182/1960, as first published) | the **received and dispensed book** | Schedule 1 · every movement (Art. 18) | per store · none | reversing line (not stated) | 10 years, Art. 31 | the authority's numbered, sealed book |
| **Ghana** (Act 489 s. 34) | the **Dangerous Drugs Record** | Class A · every supply out: a sale, an issue, a disposal, never a move between the retailer's own stores or a loss (`direction = Out`, `kind != Transfer`, `kind != Loss`); s. 34(3)'s waiver not taken | per store · none | reversing line (not stated) | 10 years (not stated: the longest cited) | a book: signed printed pages |
| **Mexico** (RIS Arts. 117, 159) | a **libro de control** for each of LGS Art. 226's fracciones I, II and III | every entry and exit (Art. 124 VII) | per product, a page each · saldo | reversing line (not stated) | 10 years (not stated) | the authorised folioed book, or an authorised system (Art. 46) |

⭐ **Read from the patient's record:** Saudi Arabia's ID number (Art. 22(3)(ح)) and Abu Dhabi's patient identifier (s. 7.2.1, which names no particular identifier) are the counter-rules app's *National or residence ID* on its patient record (*PP RXC Patient*, since its 0.1.2: the pharmacist roles, its records officer and service, and the site's System Manager read it; a Desk clerk does not), the one that links to the Customer the sale names. The register door reads it with its own rights (`match: "customer_link"`). A partner who renames the counter-rules app's prefix renames the record type here too, and the Jordan and Mexico data sets' *authority date* sources (`PP RXC Rx Date`, `pp_rxc_rx_date`): the door refuses a lookup of a record type, or a declaration naming a sale detail, that does not exist. ⚠ That is the **buyer's**: when a carer buys, or the sale names a walk-in customer, the column holds the carer's ID or nothing. Sell a controlled medicine to the patient's own customer record, or correct the entry: the door reads the buyer's record, never the prescription's patient.

Saudi Arabia's patient's age is worked out by the door, in whole years at the movement's date, from the date of birth on the same patient record. ⚠ **What a data set cannot print yet**, so the retailer writes it in: Egypt's patient's age (its set has no patient lookup), Saudi Arabia's medical file and Egypt's prescriptions-book entry number, which have no source, print as empty columns. Mexico's prescription issue date and Jordan's special-prescription date are read from the counter-rules app's *Prescription's date* (0.1.3 on): filled from the prescription at Submit on the Desk, typed by the cashier at the till, where that app refuses a date that is not the prescription's (and an empty one, on a schedule ticked *Its register books the prescription's date*); a sale made before that version prints it empty. ⚠ The till's detail is typed text: one that is not `YYYY-MM-DD`
prints empty, or a wrong day, where that app did not check it (a front-of-store sale while its service is down). Nigeria's *ingredients of the prescription* is a Desk field: a counter sale prints it empty. Jordan's Form 7, the daily prescriptions register, is a print of the counter-rules app's dispensing records, not a book here.

**A return, and a loss.** A return enters the books its own direction and kind route it to (a customer's return is a movement in, so Nigeria's Part A takes it as obtained), and every book its original entered; in a book without a balance that took it only because its original did (a customer's return in Kenya's two poisons books, Nigeria's Part B, Ghana's record), the door prints it as a note of the return, never as a movement. A loss, a disposal, an issue, a transfer or a return printed as an entry names its kind under its number.

⭐ **Returns to the regulator** have their periods and a reminder seven days before each is due: Abu Dhabi's PH 17 monthly and PH 20 quarterly (DOH s. 4.6), Saudi Arabia's register every six months (Art. 16(2)) and Egypt's book every six months, due in the first fifteen days of January and July (Art. 23, the 1960 text). Abu Dhabi and Saudi Arabia name no due day, so their reminder falls on the period's last day. ⚠ The return itself is the retailer's to send: its form (Egypt's, the authority's), Saudi Arabia's signatures and seal on the statement and at the yearly close (Art. 22(5)), and Abu Dhabi's e-mailed report are not printed here.

⚠ **Books the law names but these sets leave out:** Saudi Arabia's prescriptions register (Art. 21(2)) and Egypt's prescriptions book (Arts. 17, 18(ج)), whose fields the law does not list; Abu Dhabi's PH 18 (wards) and its unified prescribing platform (s. 3.9); Ghana's book for a Class B supplier, for which the Act sets no entry; Mexico's raw materials (Art. 159 IV) and a droguería's magistral book (Art. 124 VI).

⚠ **Dubai** is not in the UAE set: its register book (DHA) is named in its guidelines, but its columns were not read. Cameroon and Rwanda are not researched.

### One retailer, its own markets

`python3 build.py --sets ke_pharmacy --out ../my_register` builds a Kenyan retailer's copy in a folder of its own: its manifest holds only Kenya's books, prints and reminders (each book's `data_set` says which). Name several for a retailer in several markets (`--sets sa_pharmacy,ae_abu_dhabi_pharmacy`). With no `--sets`, the build writes this sample's catalogue, every data set (27 books): the app a retailer installs from the library. A retailer's copy is never written over it, and is a different package: give it a version of its own (and, for a partner's app, your own prefix), since a shop refuses a second content under a version it has installed. ⚠ The manifest is always built from every data set, so every retailer gets every set's Desk fields and till details: an update may not drop a field an earlier version installed, so a narrower build would be refused. ⛔ Do not delete the other markets' files to narrow a build: that drops their fields from the manifest.

## What the retailer does

1. **Install the pharmacy counter app** (0.1.3 or later), then **this app** (the retailer's administrator). Every market's books install switched off, with their prints, reminders, lists, the open-tasks dashboard, the *Register details* section on the Sales Invoice and the Delivery Note, the till's sale details, the role **PP RSR Register Approver** and the workspace.
2. **Switch on your market's books** (*Retail Register Book*: Kenya's three, say) and **map their register stores** on each book before the first sale (several warehouses of one premises kept as one register).
3. **Give the role** to the person responsible for the register (a pharmacist in charge, a licensee). It is each book's count role: it reads, prints and counts the books, and it reads a person's details on them. Another role reads no entry at all until you give it read on *Retail Register Line* (and read and print on *Retail Register Book* and *Retail Register Period* to print a book); then it reads them without a person's details unless you also give it that level in Role Permissions Manager, and a print for it says the details are hidden.
4. **Count each item's opening balance** (*Retail Register Count*, kind *Opening*) in a book that keeps a balance, before the item's first receipt or sale there (after that its opening is past: count it with kind *Count*): from then on a basket that would take a balance below zero is refused at the till before the tender, and a Desk submit is refused.
5. **Tell the dispensary's cashiers** to fill the sale's details for a regulated sale (the till's sale details: occupation, purpose …). A till sale is never refused for a missing one: its entry is written and counted on the dashboard as incomplete. A Desk submit is refused until the book's required columns are filled.
6. **At each Poisons Book sale, print the purchaser's slip** from the sale in Desk (someone holding the role and allowed to print that sale, such as Sales User or Accounts User; it lists the sale's entries in the book), and have the purchaser sign it there. A cancelled sale or a return has no slip.
7. **Each day at close, print the day's pages** of each book (*Print book* on the book, today's dates) and keep them at the store, for an outage.
8. **Watch the open tasks** on the dashboard *PP RSR Register*, and send each return to the regulator when its reminder falls due.

## The files

| File | What |
|---|---|
| `datasets/ke_pharmacy.json` | Kenya's three books, routing, columns and layouts, with their citations |
| `datasets/jo_pharmacy.json`, `ng_pharmacy.json`, `ae_abu_dhabi_pharmacy.json`, `sa_pharmacy.json`, `eg_pharmacy.json`, `gh_pharmacy.json`, `mx_pharmacy.json` | the other markets' books, the same way |
| `layouts/register.html` | the one print template every book uses: build.py writes the book's data above it. It draws the register door's print, `ivn_register_print(doc)` (its pages, rows and notes, as the person printing may read them), in the market's columns, in the door's words |
| `layouts/purchaser_slip.html` | the purchaser's slip of a book that asks for one: the sale's entries in that book, read with `ivn_rows`, and a line for the purchaser's signature |
| `build.py` | the format's check, and the build of `manifest.json` from the data sets (`--sets` for a retailer's own) |
| `routing.py` | which books a line enters, as the door decides it |
| `tests/test_markets.py` | each other market's data set: its routing, one test per cited rule; every book's printed headers pinned to its source; books rendered from fixture lines; three canaries (two for Nigeria's routing, one for Ghana's) |
| `tests/test_rsr.py` | the manifest and its checks; every reminder through iVendNext's checker; a retailer's own build, and no build dropping a field the installed version has; each rule of the format broken once; Kenya's routing on fixture lines; each book rendered over a stand-in of the door's print; a second data set (`tests/fixtures/liquor_one_book.json`) built and rendered with no code change |

## Run it

```bash
python3 samples/s41_regulated_register/build.py
python3 samples/s41_regulated_register/build.py --sets ke_pharmacy --out ../my_register   # a Kenyan shop's copy
python3 tools/check/check.py samples/s41_regulated_register
python3 -m unittest discover -s samples/s41_regulated_register/tests -p 'test_*.py'   # the rendering tests need jinja2
```

## Limits

- The prints are the door's: its own limits hold (a print reads at most 10,000 entries (per item, in a book that keeps a balance) and 2,000 items, and says so; it is printed by a signed-in person, and a print in the background or by e-mail says it read none). See [its page](../../contracts/pages/register_books.md).
- The print's own words are the door's, in the print's language; the data set's notice and the book's medium note stay in the data set's words, and the correction mode's sentence in this app's English. Entry dates print as the record holds them (`2026-10-20`); the page's heading in the site's date format.
- A book's page and line in the authority's own book (Jordan, Abu Dhabi, Egypt, Mexico) are the shop's statement: set each book's first page with *Official book page* before its first entry; the door prints each entry at its place from then on.
- A book declared here cannot change in an update, not even a label: a corrected book ships under a new id, numbered from 1, the old book kept switched off: keep the old book in the data set too, so its print (named by its id) stays with its entries. A kept book (one with entries, after an uninstall) is adopted at the next install with its stored declaration, switched off: switch it on again, or the sales in between write no line.
- A connector's stock entry carries no supplier, so the NPP ledger's *Received from* prints empty for it; *Invoice no.* is the connector's reference field (`columns_from`).
- A page per drug is headed by the item's name alone: put the strength and the dosage form in the name (Kenya's Annex II, Jordan's and Saudi Arabia's page headers ask for them). Nigeria's *Form in which obtained* prints the item's stock unit: name the unit by its form.
- The till prints no slip: the purchaser's slip is a Desk print of the sale, on the till's sale or a Desk sale. A sale delivered later books on its Delivery Note, which has no slip: have the purchaser sign the delivery's printed entry or a paper slip.
- The daily print has no reminder of its own (no reminder can fire every day): the workspace says it. Entries due for a person's erasure have no card (their due day is a date no list filter can hold): running *Erase persons' details* on the book erases what is due and says what still waits; it has no preview.
- The workspace's links show only to someone who may read those record types (on our bench, once the user had the stock, accounts, sales and purchase roles a register keeper has).

## Make it your own

- **Another market, or another trade:** copy `datasets/ke_pharmacy.json`, read the market's instrument, and write its books. Run `build.py` and the tests. Nothing else changes. Build a retailer's copy with `--sets` and `--out`.
- **Another prefix:** set `PREFIX`, `FPREFIX` and `ROLE` at the top of `build.py` and build again (or copy the built manifest with `tools/manifest/rename.py`).
- **Certify a layout:** set `certified: 1` once you have checked it against the market's instrument, and change its `notice`.

The register door this app declares to is the POS app's (2.1.0 or later): [its page](../../contracts/pages/register_books.md).
