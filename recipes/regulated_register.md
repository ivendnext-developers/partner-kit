# A regulated stock register — the recipe

Pharmacies, liquor shops and duty-free shops must keep a legal register of regulated stock: one line for every movement, numbered with no gap, a running balance, never edited, corrected only the way the market's law says. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, declaring a market's books and setting a store up to keep them, on iVendNext POS 2.1.0 or later.

**The door:** the register books extension point (`contracts/pages/register_books.md`). Your app **declares** each book as data in its manifest (`register_books`, manifest version 2); the POS app writes every line in the same save as the document that moves the stock. Your code writes no line, and nothing you ship can edit one.

**Reference implementation:** `samples/s41_regulated_register/` declares the pharmacy books of eight markets as data sets (Kenya's three first), with a printed layout per book. Since its 0.2.0 its manifest installs them on the door (switched off: the shop switches on its own market's), each book's print drawn from the door's own print (`ivn_register_print`), Arabic books right to left, a purchaser's slip, the register's lists and an open-tasks dashboard: its `build.py` writes every key below from a data set. A smaller book to start from is the contract's own sample, `contracts/extension_contracts/samples/register_book/accepted/01_ledger_by_item_group.json`: a liquor stock book over the shop's item groups, with a running balance per item.

## What the store sees

| Who | Where | What |
|---|---|---|
| cashier | the till | nothing new on a normal sale: the line is written as the sale is saved. A sale that would take a book's balance below zero is stopped before the tender, naming who settles it |
| goods-in clerk, Desk staff | a receipt, a delivery, a stock entry | the same: one line per book the movement enters. A person's Desk submit is refused for a required column left empty or a balance below zero |
| the book's count role (the pharmacist in charge, the licensee) | the book's form and list in Desk | the opening count, later counts, *Print book*, *Verify book*, the period's *Sign off* |
| an inspector | the printed book | the book in the market's layout, with the law it cites, each entry's number, and whether the chain of entries is whole |

## Steps

1. **Declare the book in your manifest** (`register_books`). Each book names its items (`classes` read from an item field or a dated table on Item, or `item_groups`), up to three routing conditions on the line's columns, its numbering (`book_store` or `book_store_item`), whether it keeps a `balance`, its `correction` mode, `retention_years`, its `count_role`, and the columns it prints with the source of each. Also:
   - `medium`: what the book is kept on. `printed_book` (the default: its signed printed pages are the book), `system_of_record`, `official_book` (the authority's own numbered book: each line prints at its page and line) or `regulator_system` (the authority's electronic record is the record of law; the shop's lines are its working register). Set it in the first version you ship: an update cannot change a book.
   - `details`: up to six columns read from a sale detail, a Desk field or a record. A record lookup matched `customer_link` reads the one record whose `customer` field names the sale's Customer (a patient record), so that field must be unique; a slot of `type` `Age` prints whole years at the movement's date from a date of birth.
   - a column may carry a `group` (the band printed over it, such as a received or an issued half) and may print `balance_before`, the balance before the line.
   - your print format on *Retail Register Period* for the market's layout, with `default_print_language` set to the language it prints in (`ar` prints right to left). It may call `ivn_register_print(doc)` for the door's own pages: the official book's sheets, the balance before a line, the medium line and the period's close.
2. **Check it on your laptop:** `python3 tools/manifest/validate.py manifest.json`. The site checks every name the book reads when it is saved, so a field, sale detail, record type or role that does not exist on the site is refused at install, never at the first sale.
3. **Install it** on a sandbox (`tools/deploy/deploy.py`, or the Retail Extension Package screen). Each book installs on or off as it declares, and the count role is made if the site lacks it and it carries your app's prefix.
4. **Map the register stores, before the first sale.** On each book's Desk form the retailer maps the warehouses of one premises to one register store. A manifest cannot carry this; a warehouse that already has lines keeps its register store.
5. **Count the opening** (a book that keeps a `balance`; a book without one is never counted). The count role makes a *Retail Register Count* of kind **Opening** per register store: each item's balance, entered once, before its first line. From then on a line that takes the balance below zero is flagged, a Desk submit is refused, and the till stops the basket before the tender. Nothing is flagged or refused before the opening, so a shop loads its stock, then counts.
6. **A correction is a cancel.** A line is written once. Cancelling the document writes a correction line for each line it wrote, in the same book, naming the line it corrects; the print shows it the way the book's `correction` mode says (a reversing line, a dated note, a signed strike-through or a signed amendment).
7. **Print the book cold.** *Print book* on the book's list or form prints any book for any register store and dates, in the door's plain layout or your print format, in the language the dialog names. Today's dates are the store's daily print for an outage: print them at each day's close and keep them at the store.
8. **Close each period** (a book with `period_months`): after the period's last day the count role presses *Sign off*. The sign-off records who, when and each sequence's last entry and hash; *Verify book* then finds a line changed or removed before it.

## Limits to tell the customer

- **A book cannot change in an update,** not even a column label: a corrected book ships under a new id, which numbers from 1, while the old one stays switched off with its lines.
- **A book with lines is never deleted,** not even at uninstall: it is switched off and kept, with its print formats and count role.
- **The till is never refused at its save:** a line it cannot complete is written flagged (incomplete, below zero), an open task for the count role. A Desk submit, an import of a stock-take of more than 100 rows, or a document posted through the REST API is refused instead.
- **A Stock Reconciliation follows the register:** for an item a book with a balance takes, once that store's opening is counted, it passes only to the quantity an approved count of that book found.
- **The law's signatures and seal** are written on the printed close; the door prints spaces for them and captures none.
- **Every layout is the partner's to certify.** S41's books print *a starting point, not certified for the country* until a partner checks them against the market's law.
- **What the door leaves out:** the register books page, *Stated limits of this version*.
