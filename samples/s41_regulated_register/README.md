# S41 — Regulated stock register (`pp_rsr`): each market's books as data

A shop selling regulated stock keeps a legal register an inspector can ask for at any time: a pharmacy's poisons and controlled-drug books, a liquor or tobacco register, a duty-free ledger. Today most keep it on paper. This app keeps it for them: **one app for any regulated stock**, whose books (which book, which items, which movements, which columns, which printed layout) are a **data set** per market and vertical. A second market, or a second vertical, is a new data set file with no code change.

The first data set is **Kenya's three pharmacy books**: the Poisons Book (Rules Schedule VIII Form 16), the Prescription Book (Act s. 31(1)(b)) and the NPP Ledger Book (PPB NPP Guidelines Annex II), with the routing Kenya's law asks for: a supply on prescription goes to the Prescription Book, **not** the Poisons Book (s. 31(2)); every movement of a controlled drug goes to the NPP ledger as well. Seven more markets follow as data sets, with no code change: Jordan, Nigeria, the UAE's Abu Dhabi, Saudi Arabia, Egypt, Ghana and Mexico ([the other markets](#the-other-markets)).

⚠ **Every layout here is a starting point, not certified for the country.** It is read from the instruments named in the data set, and each print says so. A partner certifies it for a market, changes it, or adds a market.

**Door:** Manifest

**When to use it:** the shop's law names a book and its columns, and the book must hold every sale or receipt of certain stock, in order, never edited.

## The register door: what is here now, and what waits for it

The book itself is a legal record: one line written in the **same save** as the sale or the receipt, numbered without a gap, with a running balance two tills cannot break, and never edited. An app installed from a manifest cannot write such a record, so the POS app carries a **register door** for it, and this app declares its books to that door. ⚠ **The door is not in the POS app yet.** Its specification is written and requested on the POS team's board.

| Part | Installs | What it is |
|---|---|---|
| `manifest.json` | ✅ **now** | the register's own columns as fields on the Desk sale and delivery (a collapsible *Register details* section) and as the till's sale details · the role **PP RSR Register Approver** · the report *PP RSR Stock counts to watch* · the workspace *PP RSR Regulated stock register* |
| `door_declaration.json` | ⏳ **after the door** | each book's declaration (the manifest kind `register_books`), each book's print format, a reminder before each return's due date. The shop's checker refuses the kind and the door's record types until the door is in the POS app; this app's next version (0.2.0) installs them, with what it still owes: the register's lists per book, store and period (FR-K3-04), the open-tasks cards (late, incomplete and below-zero lines, a count due after a loss, a return due), the loss report with its count, the daily-print reminder, and a purchaser's slip for a Poisons Book sale |

Until the door is there, the shop's books are kept as before. Setting this app up now puts the columns on the documents, so the door's first line has them.

## A data set

`datasets/ke_pharmacy.json` is the whole of Kenya. A data set says:

| Key | What |
|---|---|
| `id`, `title`, `jurisdiction`, `vertical`, `sources` | which market and trade it is, and the instruments it is read from |
| `certified`, `notice` | `0` and the notice every print carries, until a partner certifies the layouts |
| `details` | up to six columns of the book that are neither on the line nor the authority's: each a key, a label and a type. `own: 1` makes it this app's Desk field (`pp_rsr_<key>`) and, unless `till: 0`, a sale detail every till offers (`PP RSR <Key>`): keep the till's to what the counter fills often (Kenya: occupation, purpose, the prescriber's address) |
| `authority` | where the authority columns come from: a prescription, a permit, a boarding pass (the till's sale details, the Desk's fields, and the dispenser's licence from a record) |
| `books` | each book: its title, form and citation; its items (`classes` or `item_groups`); for classes, its `class_source`: the axis it reads, from an Item field or a dated table of schedules on Item (the door copies the class into the line when it writes it, so a reclassification never rewrites history); **up to three routing conditions, all of which must hold** (`=`, `!=`, `>`, `>=`, `<`, `<=`, `is set`, `is not set`, on a column of the line: the POS app's save-rule form); numbering per book and store or per drug; a running balance or none; the market's correction mode; retention in years; the medium (`system_of_record`, `printed_book`: its signed printed pages are the book, or `official_book`: printed into the authority's own book); the columns Desk may not leave empty; and its printed columns in order |

A column prints one or more of the line's columns (`movement_date`, `item_name`, `qty`, `counterparty`, `authority_no`, `balance` …, the door's line) or a declared detail (`detail:occupation`), joined with ` · `. `when: "In"` or `"Out"` prints it only on receipts or only on issues (the NPP ledger's two halves); `mark: 1` leaves room for a signature on the printed page; `in_colour` prints received quantities in a colour (Kenya: red ink, s. 8.1(i)).

`build.py`'s `check()` is the format: it refuses `in` (a list of classes is the book's `classes`), a fourth condition, a comparison of a column against a date value (a date is not a number to the condition form; ⚠ it does not yet refuse a date column compared with a number, which never holds: don't write one), a column the line does not have, markup or template text in any label, and the rest, each in words. `routing.py` models which books a line enters, so you can test a data set before the door is installed.

## Kenya's three books

| Book | Takes | Routing | Numbering · balance | Correction | Kept |
|---|---|---|---|---|---|
| **Poisons Book** (Form 16, 9 columns) | Part I poisons (the poisons axis) | a sale (`kind = Sale`) with **no prescription** (`authority_no is not set`) | per store · none | a single strike-through, signed (NPP Guidelines s. 8.1(j)) | 2 years (Rules r. 21) |
| **Prescription Book** (s. 31(1)(b); no form prescribed: its four cited particulars) | the same | a sale **on prescription** (`authority_no is set`) | per store · none | the same | 2 years |
| **NPP Ledger Book** (Annex II, 10 columns, a page per drug headed by the establishment and its address) | controlled drugs (the controlled axis) | every receipt and issue | per drug · running balance | the same | 5 years (s. 8.1) |

So a prescription supply of pethidine (a Part I poison on one axis, a controlled drug on the other) enters the Prescription Book **and** the NPP ledger; a counter sale of a Part I poison enters the Poisons Book only; a transfer, an issue or a loss of a poison enters no sales book.

⚠ **The two poisons books are kept as printed books.** Electronic records are cited for NPP records only (Guidelines s. 8.1): print the day's pages, sign them, and keep them as the book; each print of those two books ends with a line for that signature. ⚠ Form 16 also asks for **the purchaser's** signature, given at the sale: until this app's next version prints a slip for it, have the purchaser sign the paper book or a slip at the counter (FR-K3-11).

⚠ **The classes are the shop's.** `KE Part I Poison` and `KE NPP`, and the axes `KE Poisons` and `KE Controlled`, are working names of the counter-rules app's drug schedules, read from its dated *Item Schedule* rows on Item (`pp_rxc_schedules`: `schedule`, `effective_from`), or from the Item Group's `pp_rxc_schedule` where an item has no row; the axis is the schedule's own `axis`. Rename them in the data set to the shop's own. The door refuses, at setup, a declaration naming a field or table that does not exist. ⚠ Whether every controlled drug is also a Part I poison is not cited (Kenya's narcotics Act, Cap. 245, was not read): the shop gives each drug its schedule on each axis.

⚠ **One prescription per sale.** The till's sale details belong to the whole sale, so a basket holding a poison on prescription and another sold without one would put both in the Prescription Book. The counter-rules app refuses such a line (its schedule's tick *Sold in a sale of its own when not on the prescription*): tick it on the Part I poison schedule, and the cashier sells the other as a sale of its own.

## The other markets

Each is one file in `datasets/`. Jordan's and Nigeria's columns are their printed forms, read off the form images; the others are the data their law lists, in its order, because no form is printed. Labels are the instrument's own words, Arabic or Spanish where the instrument is; where a label adds a word (a group, a letter, Abu Dhabi's *brand and generic name* from s. 7.7, Mexico's entry columns), the data set's notice says so.

| Market | Books | Takes · routing | Numbering · balance | Correction | Kept | Medium |
|---|---|---|---|---|---|---|
| **Jordan** (JFDA Instructions 2025) | **Form 9** narcotics and psychotropics, 13 columns; **Form 8** Schedule 10 preparations, 9 columns | Schedules 1–9 · Schedule 10 (Law 23/2016 Art. 2) · every receipt and issue | per drug, a page each · running balance | reversing line (not stated: the strictest) | 5 years · 2 years | the book received from JFDA, or a JFDA-approved system (Art. 7, 11) |
| **Nigeria** (Dangerous Drugs Regulations, First Schedule) | **Part A** (obtained) and **Part B** (sold or supplied) for six of reg. 18(1)(b)'s classes and one for the drugs Part III applies to by Order (amidone, pethidine …): 14 books. Codeine and dionin have none: the Modified Form Regulations take them out of reg. 18 for a retailer | Part A every movement in (`direction = In`), Part B every movement out (`direction = Out`): reg. 18(1)(a)'s *all dealings* | per store · none | dated marginal note, reg. 18(1)(f) | 2 years, reg. 26 | not stated: signed printed pages |
| **UAE, Abu Dhabi** (DOH Standard 2021) | **PH 20** narcotic, **PH 17** psychotropic and semi-controlled | every movement (s. 3.6.1, 3.6.3) | per store · running balance | reversing line, s. 7.3 | 5 years, s. 7.4 | DOH's own book (s. 3.6) |
| **Saudi Arabia** (Executive Regulation Art. 22) | one register **per drug**, 17 columns lettered as Art. 22(3) | narcotics and psychotropics · every movement | per drug, a page each · running balance | signed amendment, Art. 22(4) | 10 years, Art. 22(6) | signed printed pages until SFDA verifies a system (Art. 22(8)) |
| **Egypt** (Law 182/1960, as first published) | the **received and dispensed book** | Schedule 1 · every movement (Art. 18) | per store · none | reversing line (not stated) | 10 years, Art. 31 | the authority's numbered, sealed book |
| **Ghana** (Act 489 s. 34) | the **Dangerous Drugs Record** | Class A · every supply out: a sale, an issue, a disposal, never a move between the shop's own stores or a loss (`direction = Out`, `kind != Transfer`, `kind != Loss`); s. 34(3)'s waiver not taken | per store · none | reversing line (not stated) | 10 years (not stated: the longest cited) | a book: signed printed pages |
| **Mexico** (RIS Arts. 117, 159) | a **libro de control** for each of LGS Art. 226's fracciones I, II and III | every entry and exit (Art. 124 VII) | per product, a page each · saldo | reversing line (not stated) | 10 years (not stated) | the authorised folioed book, or an authorised system (Art. 46) |

⚠ **What a data set cannot print yet**, so the shop writes it in or waits: the patient's age, ID number and medical file (Saudi Arabia, Egypt) and the prescriptions-book entry number (Egypt) print as empty columns, because the register cannot yet read a value from the customer's record (the counter-rules app keeps the ID and the date of birth there). Mexico's prescription issue date and Jordan's special-prescription date print empty: the counter-rules app does not record a prescription's date on the sale. Nigeria's *ingredients of the prescription* is a Desk field: a counter sale prints it empty. Abu Dhabi's patient identifier (s. 7.2.1) is not printed. Jordan's Form 7, the daily prescriptions register, is a print of the counter-rules app's dispensing records, not a book here.

⚠ **A return, and a loss, print as the register door prints them today.** A return follows its original's books, so a customer's return prints in a sales book (Kenya's two poisons books, Nigeria's Part B, Ghana's record) and a return to the supplier in Nigeria's Part A, each as a movement of its own; and a loss, disposal or issue prints in a dispensing half with its prescription and patient cells empty, saying nothing of what it was. Both are requested of the door (`PB-4`); until then, mark such an entry by hand.

⚠ **Returns to the regulator are not set up**: Abu Dhabi's monthly and quarterly reports, Saudi Arabia's six-monthly statement and yearly close, and Egypt's six-monthly statement. A book's period gives its reminder a name the shop's install refuses, so no data set declares one yet.

⚠ **Every market's books install in every shop.** The app builds one declaration from every data set, so a shop installing its next version gets every market's books (27 today), each switched on. Until a shop can choose its data set, a partner keeps only its market's file in `datasets/` and builds again.

⚠ **Books the law names but these sets leave out:** Saudi Arabia's prescriptions register (Art. 21(2)) and Egypt's prescriptions book (Arts. 17, 18(ج)), whose fields the law does not list; Abu Dhabi's PH 18 (wards) and its unified prescribing platform (s. 3.9); Ghana's book for a Class B supplier, for which the Act sets no entry; Mexico's raw materials (Art. 159 IV) and a droguería's magistral book (Art. 124 VI).

⚠ **Dubai** is not in the UAE set: its register book (DHA) is named in its guidelines, but its columns were not read. Cameroon and Rwanda are not researched.

## What the shop does (now)

1. **Install the app** (the shop's administrator). It adds the *Register details* section to the Sales Invoice and the Delivery Note, the till's sale details, the role **PP RSR Register Approver**, the report and the workspace.
2. **Give the role** to the person responsible for the register (a pharmacist in charge, a licensee).
3. **Tell the dispensary's cashiers** to fill the sale's details for a regulated sale (the till's sale details: occupation, purpose …). They are never required, so no other till is stopped; the counter-rules app's check before payment is what refuses an incomplete controlled sale.
4. **Print the day's register pages** at each day's close and keep them at the store, for an outage (from the door's version on; until then, the paper book).

## The files

| File | What |
|---|---|
| `datasets/ke_pharmacy.json` | Kenya's three books, routing, columns and layouts, with their citations |
| `datasets/jo_pharmacy.json`, `ng_pharmacy.json`, `ae_abu_dhabi_pharmacy.json`, `sa_pharmacy.json`, `eg_pharmacy.json`, `gh_pharmacy.json`, `mx_pharmacy.json` | the other markets' books, the same way |
| `layouts/register.html` | the one print template every book uses: build.py writes the book's data above it. It reads the book's lines with `ivn_rows` as the person printing may read them, 200 at a time |
| `build.py` | the format's check, and the build of `manifest.json` and `door_declaration.json` from the data sets |
| `routing.py` | which books a line enters, as the door decides it |
| `tests/test_markets.py` | each other market's data set: its routing, one test per cited rule; every book's printed headers pinned to its source; books rendered from fixture lines; three canaries (two for Nigeria's routing, one for Ghana's) |
| `tests/test_rsr.py` | the manifest and its checks; each rule of the format broken once; Kenya's routing on fixture lines; each book rendered from lines shaped as the door's line; a second data set (`tests/fixtures/liquor_one_book.json`) built and rendered with no code change |

## Run it

```bash
python3 samples/s41_regulated_register/build.py
python3 tools/check/check.py samples/s41_regulated_register
python3 -m unittest discover -s samples/s41_regulated_register/tests -p 'test_*.py'   # the rendering tests need jinja2
```

## Limits

- **No book is written or printed until the door is in the POS app.** The book prints name the door's period record type, which the shop's install refuses until it exists.
- A print reads at most 10,000 lines (50 reads of 200) and, in a book printed a page per drug, 2,000 drugs. Print a shorter range for more.
- A correction struck through on this print is matched within the printed range: a correction of an entry printed in an earlier range shows as a correction line only.
- The print is printed by a signed-in person: the print readers answer nothing in a background print or an e-mail, and the print then says so rather than showing an empty book.
- On the ERP's stock-entry path no supplier is carried, so the NPP ledger's *Received from* prints empty there; *Invoice no.* is the ERP's own log number.
- The ledger's header shows the drug by its item name: put the strength in the name, as Annex II asks for it.
- The workspace's links show only to someone who may read those record types: a System Manager alone sees none (on our bench, the links appeared once the user had the stock and accounts roles a register keeper has).
- Dates print as the record holds them (`2026-10-20`). The print's own words are in English: its number column (`No.`), its notes and its footer. A data set's column labels are in its market's language.
- A book prints left to right, one header row: a right-to-left form (Jordan, Saudi Arabia, Egypt) prints its columns in the form's order, left to right, and a form's grouped header (Jordan's *in* and *out*) is carried in each column's label.
- A book printed into the authority's own book (Jordan, Abu Dhabi, Egypt, Mexico) does not follow that book's page and line numbers yet: print it on paper and copy, or keep the register in an approved system where the law allows one.
- A page per drug is headed by the item's name alone: put the strength and the dosage form in the name (Jordan's and Saudi Arabia's page headers ask for both). Nigeria's *Form in which obtained* prints the item's stock unit: name the unit by its form.

## Make it your own

- **Another market, or another trade:** copy `datasets/ke_pharmacy.json`, read the market's instrument, and write its books. Run `build.py` and the tests. Nothing else changes.
- **Another prefix:** set `PREFIX`, `FPREFIX` and `ROLE` at the top of `build.py` and build again (or copy the built manifest with `tools/manifest/rename.py`).
- **Certify a layout:** set `certified: 1` once you have checked it against the market's instrument, and change its `notice`.

The register door this app declares to is requested of the POS app as `PB-4`, the regulated-stock register door; its version will be named here when it ships.
