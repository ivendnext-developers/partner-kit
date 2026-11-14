# S41 — Regulated stock register (`pp_rsr`): each market's books as data

A retailer selling regulated stock keeps a legal register an inspector can ask for at any time: a pharmacy's poisons and controlled-drug books, a liquor or tobacco register, a duty-free ledger. This app keeps it for them. Its books (which book, which items, which movements, which columns, which printed layout) are a **data set** per market, so a second market is a new data set file with no code change. Each line is written in the same save as the sale or the receipt, numbered without a gap and never edited.

The first data set is Kenya's three pharmacy books: the Poisons Book, the Prescription Book and the NPP Ledger Book, with the routing Kenya's law asks for. Seven more markets follow as data sets: Jordan, Nigeria, the UAE's Abu Dhabi, Saudi Arabia, Egypt, Ghana and Mexico. Every layout is a starting point, not certified for the country: a partner certifies it for a market, changes it, or adds a market.

No liquor or customs book ships with it: a state's liquor register or an airport's customs ledger is a partner's data set, made the same way.

**Industries:** Pharmacy

**When to use it:** the retailer's law names a book and its columns, and the book must hold every sale or receipt of certain stock, in order, never edited.

## Start from it

```bash
ivn new acme_register --from s41
```

## What to change

What a partner usually changes:

- another market or another trade: copy `datasets/ke_pharmacy.json`, read the market's instrument and write its books; run `build.py` and the tests; build a retailer's copy with `build.py --sets <id> --out <folder>`;
- certify a layout: set `certified: 1` in the data set once checked against the market's instrument, and change its `notice`;
- the printed layouts: `layouts/register.html` and `layouts/purchaser_slip.html`.

Name the pharmacy counter app's drug schedules and their axes exactly as each data set's `classes` and `class_source.axis` read them: a misnamed one installs cleanly and writes nothing to the book.

More: the [recipe](../../recipes/regulated_register.md).

**The customer sets:** its own market's books to switch on, the register stores on each book before the first sale, each item's opening count, and who holds the role **PP RSR Register Approver**. Install the pharmacy counter app (0.1.3 or later) first: the books read its drug schedules, prescriptions and patient records.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- Sell an item the register covers; the till asks for the register's sale details.
- In Desk, open the register's book for that day; the sale is in it.
- Close the till day when you are done.

## Versions

### 0.2.3

- Desk shows plain names (*Regulated stock register* on the register's page, *Register entries*, *Periods open*) through the manifest's `translations` block.
- The 0.2.2 line now says that a till sale carries the engine's *No Remarks* too.

### 0.2.2

- Every data set but Kenya's (its six slots are taken) declares a *Note* slot (*Nota*, *ملاحظة* in the Spanish and Arabic books) read from the document's own Remarks: a loss written off by a stock entry prints its reason in the plain print's *Particulars*. A sale left without a remark, at the till or on the Desk, carries the engine's *No Remarks*, and the plain print shows it as *Note: No Remarks*. No market layout changes.

### 0.2.1

- Kenya's data set sets no count deadline after a loss: it cited no source for one.

### 0.2.0

- Installs its books on the POS app's register door (POS 2.1.0 build 667 or later; install S39 0.1.3 or later first).
- Each print carries its layout without comments or indentation, so the App library takes it.
- It passes its own tests.

### 0.1.3

- The register format: a value from the customer, a period's reminder, a date-column check, one shop's markets.
- Prints the prescription's date where the market asks for it (Jordan, Mexico).

### 0.1.2

- Seven more markets as data sets: Jordan, Nigeria, Abu Dhabi, Saudi Arabia, Egypt, Ghana and Mexico.

### 0.1.1

- First version in the kit: each market's books as a data set, Kenya's pharmacy books first.
