<!-- Source: ivendnext/iVendNext_PWA docs/extending/register_books.md @ c39b1449937a, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Register books

**Contract:** [`register_book.v1.schema.json`](../extension_contracts/register_book.v1.schema.json)
· samples: [`samples/register_book/`](../extension_contracts/samples/register_book/)
· code: `business_logic/register_book.py` (`validate_book`, `uninstall_refusals`), the manifest kind
`register_books` in `business_logic/manifest_check.py` and `business_logic/manifest_install.py`, the
line in `business_logic/register_line.py`, the count and the reconciliation's check in
`business_logic/register_count.py`, the period in `business_logic/register_period.py`, and the print
and *Verify book* in `business_logic/register_print.py`.

## 1. What it is

Pharmacies, liquor shops and duty-free shops must keep a legal register of regulated stock: one
line for every movement, numbered with no gaps, a running balance, never edited, corrected only in
the way the market's law says. The POS app keeps such registers through one general **register
door**. A shop's books are **declared as data**, one **Retail Register Book** per book, so a new
market is a data set, not new code.

A book says which items it takes, which movements enter it, how its lines are numbered and
corrected, and which columns it prints, with the source of each. An app declares its books in its
manifest (`register_books`, manifest version 2); a System Manager may also make one on the Desk.

This version installs and checks the declaration, writes the lines of every document that moves a
declared item (section 5: the till's sale and its returns, the Desk's sale and delivery, receipts
and purchase invoices, stock entries, subcontracting receipts, and any other document through the
stock ledger), counts a book against its own balance, holds a Stock Reconciliation to that count,
keeps each book's periods, and prints the book (section 7). Section 6 names what it leaves out.

## 2. What a book declares

| Key | Meaning |
|---|---|
| `book` | the book's id, `data_set.book` in lower-case words, for example `ke_pharmacy.npp_ledger`; the record's name |
| `title`, `cite` | the book's name as the inspector reads it, and the law that requires it (printed on every page) |
| `data_set` | the set of books it belongs to, for example `ke_pharmacy` |
| `certified` | `0` for a reference layout: its print says it is a starting point, not certified for the country |
| `enabled` | `1` or `0`; the book is installed as declared, and an update never switches it (the shop's own switch stays) |
| `medium` | what the book is kept on: `printed_book` (the default: its signed printed pages are the book), `system_of_record` (this system is the register; a print is a copy), `official_book` (the authority's own numbered book: each line prints at that book's page and line, section 7) or `regulator_system` (the authority's own electronic record is the record of law, and the shop's lines are its working register) |
| `items` | **either** `classes` (matched against the item's class, read from `class_source`) **or** `item_groups` |
| `class_source` | per book, where an item's class is read: `{"item_field": …}` or a dated table on Item `{"item_table", "class_field", "from_field", "axis", "group_field"}` |
| `conditions` | 0 to 3 routing conditions on the line's own columns, all of which must hold: `field`, an operator (`=`, `!=`, `>`, `>=`, `<`, `<=`, `is set`, `is not set`), `value` |
| `numbering` | `book_store` (one sequence per book and register store) or `book_store_item` (one per item) |
| `balance` | `1` keeps a running balance per book, register store and item (a ledger) |
| `correction` | how a correction prints: `reversing_line`, `dated_note`, `signed_strike_through` or `signed_amendment` |
| `required` | the columns a person or an integration may not leave empty when submitting (the till and a background job are never refused: §5, *Who is refused*) |
| `columns` | the printed columns: a label and the line columns it prints (`when`: `In` or `Out`; `group`: the band printed over the column, such as a received or an issued half, which a market's own layout prints (the door's plain print has fixed columns); `mark`); besides the line's own columns a column may print `balance_before`, the balance before the line, which the print works out (a condition or a required column cannot name it) |
| `details` | up to six slots `detail_1` … `detail_6`, each a label and a source: a sale detail, a Desk field, or a record lookup `{"doctype", "match", "field"}` — `match` is `customer` (the Customer the movement names), `customer_link` (the one record of `doctype` whose `customer` field names that Customer, such as the pharmacy counter app's patient record) or `user` (the record named by the line's dispenser); a slot with no source prints empty for the shop to write in. A slot's `type` is `Data`, `Date` (it routes as a date) or `Age`: whole years at the movement's date from the date of birth its source gives (a date field, or text written `YYYY-MM-DD`), empty when the date is missing, is written any other way, or comes after the movement. A slot's `person` (`0` or `1`) says whether it holds a person's details, which are erased once the book's retention has passed (§8); not declared, a slot read from the customer or its linked record (`customer`, `customer_link`), or an `Age`, is a person's and any other is not (a dose, a prescriber's address). A `customer_link` lookup that finds two records of one customer reads neither; the store's walk-in customer (a warehouse's cash customer or a till's default customer) reads none, so a patient record linked to it by mistake never reaches an anonymous sale |
| `authority` | where the prescription, permit or pass is read: `pos_sale_details`, `desk_fields`, `dispenser_licence` |
| `columns_from` | per document type, the field `counterparty`, `counterparty_address` or `reference_no` is read from |
| `retention_years` | each line is kept whole at least this long after its period's last day (in a book without periods, after its entry); then a person's details may be erased from it (§8). A line is never removed. A law that keeps a person's details longer (the UAE: 25 years for health data) is this number |
| `period_months`, `return_due_days` | both or neither: periods of 1, 2, 3, 4, 6 or 12 months from 1 January, the return due that many days after |
| `count_role`, `count_witness`, `loss_count_hours` | who approves a register count, whether it needs a second signer, and the hours after a loss within which a full count is due (a book that keeps a balance only) |

A book's **register stores** (several warehouses of one premises kept as one register) are the
shop's own setup, mapped on the book in the Desk **before the first sale**; a manifest does not
carry them. A warehouse that already has lines keeps its register store.

## 3. Refused when the book is saved (and so at install)

Every name a book reads must exist on the site, so a copy of an app under another prefix fails at
setup, never at the first sale: *"The field ⟨field⟩ named in this declaration does not exist."* The
same for a sale detail, a record type and a role. Also refused:
- a condition comparing a **date or time column** (or a `Date` detail) with anything but `is set` /
  `is not set`: a date compared with a number reads as 0 and never, or always, holds;
- a `>`, `>=`, `<` or `<=` condition whose value is not a number;
- more than three conditions, or a column that is not one of the register's;
- a record lookup matched any other way than `customer` (reading a Customer), `customer_link` or
  `user`; a `customer_link` whose record type has no `customer` field linking to a Customer, or whose
  `customer` field is not unique (one record per customer: the lookup never chooses);
- `loss_count_hours` on a book that keeps no balance (a register count needs one);
- a `required` detail slot with no source to fill it;
- a condition comparing a detail read from a date field (it routes as a date, `type` or not);
- a period without its return due day, or a period that does not divide the year;
- once a book has lines: changing its numbering, balance, correction mode or period
  (`period_months`, `return_due_days`), or moving a warehouse that has lines to another register
  store; once it has lines, counts or periods: deleting it (switch it off); once a period of it is
  signed off: changing its `medium` (it decides how that period prints).

**Switching a book off is always allowed**, even when a name it reads has gone since; switching
it back on checks every name again.

## 4. Install, update and uninstall

- **Install:** each book through the record's own save (section 3), installed on or off as it
  declares; the app's `count_role` is made if the site lacks it and it carries the app's prefix.
  The install's to-do names any connector field a book reads that the site lacks (that column
  prints empty until the connector is installed).
- **Update:** a new book is added; a changed book is refused (ship it under a new id, which starts
  its numbering again at 1 while the old book stays switched off with its lines); a dropped book
  is switched off and kept until the app is uninstalled. An update never switches a book it keeps.
- **Uninstall:** every book of the app is switched off first. A book with no lines, counts or
  periods goes with the app. A book **with any of them is kept, switched off, never deleted**,
  and the app's register prints (print formats on Retail Register Period) and that book's count
  role stay with it. A later install adopts the kept book with its stored declaration and switches
  it as that install declares (the consent names the switch).
- **An app a book reads** (its class field, a sale detail, a record type) cannot be uninstalled
  while an enabled book of another app reads it: *"⟨book⟩ reads ⟨field⟩: switch the book off first."*
  The request is refused at once and the package stays installed; a book switched on between the
  request and the job makes the job stop, and the package then reads Failed until it is retried.

## 5. The line

Each movement of an item a book takes writes **one Retail Register Line per book it enters, per
document row, per batch**, in the same save as the document: if a line cannot be written, the
document is not submitted, and no number is used.

- **Which books.** Each switched-on book on its own: its items first (by class, read on the book's
  own axis at the movement's date and copied into the line, or by item group, sub-groups included),
  then its conditions on the line as it would be written. One movement may enter several books.
- **Which documents.** Each on its submit, beside the core's own handlers:

  | Document | Books a line when | Direction · kind |
  |---|---|---|
  | The till's sale (POS Invoice) | its mode hands goods over (*Sale*); an order, a delivery, a quotation or a gift card book nothing, the document that moves the stock does; a sale with any line to deliver books nothing at the sale, since every one of its lines leaves on a Delivery Note, which books it | Out · Sale |
  | The till's return | a refund (*Sale Return*, *Item Return*) whose stock comes back on its own credit note; an order's refund books nothing (its goods never left), and a return of a line still to be delivered books on the Delivery Note the core makes for it | In · Return |
  | Sales Invoice | it moves stock (`update_stock`), and it is not the consolidated invoice of the till's sales, which booked at the till | Out · Sale (a credit note: In · Return) |
  | Delivery Note | always, including the one the till's own sale makes and a delivery from another store, from its own store and lot; a delivery of one till sale carries that sale's details (a prescription delivered later enters the book of prescriptions) | Out · Sale (a return: In · Return) |
  | Purchase Receipt, Subcontracting Receipt | always; a rejected quantity is a second line into its own warehouse's register store | In · Receipt (a return: Out · Return) |
  | Purchase Invoice | it moves stock (`update_stock`) | as the receipt |
  | Stock Entry | per row: out of its source store, into its target store; none between two warehouses of one register store | by purpose: *Material Issue* Issue, *Material Receipt* Receipt, the transfers and *Send to Subcontractor* Transfer, the rest Repack |
  | Any other document | a declared item moves on the stock ledger for a document the door does not book (an asset capitalisation, a future document type) | In · Receipt or Out · Issue, written incomplete |

  A product bundle books the articles it packs. A delivery to an internal customer, and a receipt
  from an internal supplier, are transfers between the two warehouses.
- **Returns.** A return enters every book its own direction and kind route it to, **and** every
  book its original entered for that item (read from the original's lines, its class copied from
  them; the lines are found on every document that booked the original, such as the Delivery Notes
  of a till sale with a line to deliver). A book the return reaches only through its original does
  not take its direction (a supplier return in a book of purchases, a customer's return in a book of
  sales): its remark names the line it returns (of its own register store, or naming the other
  store, since numbers count per store), and in a book without a balance its print shows it
  as a note of the return, never as a movement; a book that keeps a balance counts it (the goods
  came back).
- **Who is refused.** A submit made outside a background job — a person on the Desk, an integration
  through the REST API, a console or `bench execute` — and a person's own Desk action the core queues
  through its queue action (a stock-take of more than 100 rows): a column the book declares `required` left
  empty (*"⟨column⟩ is required in ⟨book⟩."*), a line that would take a balance below
  zero after its opening (*"This would take the ⟨book⟩ balance of ⟨item⟩ below zero. A count of
  ⟨book⟩ by ⟨role⟩ settles it."*), or a declared item moved by a document the door does not book.
  A POS Invoice (the till's sale), a sale drained from the offline queue, a document the till writes in its own
  save or for its operator (the Delivery Note of a sale with a line to deliver) and any other background job's post (the ERP
  path's stock entries) are never refused: their lines are written flagged (`incomplete`,
  `below_zero`), an open task. A correction is never refused.
- **A late line.** A sale drained from the offline queue is entered when it drains, numbered then,
  dated when the till captured it, with `booked_late` set and the remark *Entered late*.
- **Numbering.** The next number in the line's sequence (per book and register store, or per book,
  register store and item), at the moment it is written: two tills never share a number and a
  failed save leaves no gap.
- **Balance.** A book that keeps one carries the balance after each line, per register store and
  item. An **opening** line (once per book, register store and item, before its first line, by the
  book's count role) starts it; from then on a line that takes it below zero is written with
  `below_zero` set, an open task. The till's sale is never refused at its save: **the till checks
  before the tender** and stops a basket that would go below zero, naming who settles it (a
  count of the book by its count role). Nothing is flagged or refused before the opening.
- **Columns.** The cashier who made the sale (the person who submitted a Desk document), the
  customer or supplier and address (a transfer: the other register store), the supplier's delivery
  note on a receipt, its bill number on a purchase invoice, a stock entry's own number (or the
  field the book names, such as a connector's reference, where the document has it), the prescription or
  permit from the sale details (the till) or the document's fields (the Desk), each detail slot from
  its source; a record lookup reads with the door's own rights, so a field the writer may not read
  still fills its column, and leaves it empty when there is no record (a receipt names no
  customer). A sale made offline is dated when the till captured it.
- **Never changed.** A line is written once. A **cancel** writes a correction line for each line
  the document wrote, in the same book (whatever its conditions say, and even if it is switched
  off), reversing the quantity and naming the line it corrects; the cancel is not blocked by the
  lines. An item, warehouse or lot that has lines cannot be renamed or merged, nor a record a book
  names in its declaration (an item group or class it takes, a warehouse it maps, a condition's
  value).
- **Tamper evidence.** Each line carries the SHA-256 of every column its hash version covers, its
  submitted state, its sequence and the line before it (`prev_hash`, `line_hash`); a correction is
  the next link of the same chain. A direct database edit of a line's columns breaks the chain from
  that line on. The line stores its version (`hash_version`): lines written before it existed are
  version 1 and keep verifying as they were written. From version 2, each column a person's details
  may later be erased from (`counterparty`, `counterparty_address`, `correction_note`, `detail_1` …
  `detail_6`) is hashed as a digest under its own random salt, kept in the line's `person_seal`: such
  a column can be blanked, its salt replaced by its digest, and the chain still holds — the one edit
  that does. *Verify book* and the print's chain line then say how many entries had a person's
  details erased, so an erasure is never silent, and an erased column that no act of erasure
  recorded breaks the book (§8). A version-1 line hashes those values themselves and is never
  blanked. Neither column is a register column a book prints or routes on.

A print reads the lines and the book's state rows through `ivn_rows` by their own field names; the
contract test `test_every_field_the_kits_register_prints_read_is_a_field_of_the_line_or_state` holds the
kit's prints to them.

## 6. Stated limits of this version

- A period's sign-off records who, when and the chain; the law's own signatures and seal are
  written on the printed close (spaces are printed for them), never captured. A book without
  periods is never signed off. The market's loss reports are a later version's.
- A Stock Reconciliation is held to a count only for an item a book that keeps a balance takes: a
  book without a balance records dealings, which an inventory correction is not.
- A reconciliation spanning several register stores needs one count per store; a book in dose
  units is a later version's.
- An official book's places are the shop's own statement of where its next entry lands; the door
  does not know what was written on the paper by hand. Each line takes one line of the authority's
  book: a reversing correction's note prints in its own row, and an opening or a count is a line.
- A cold print runs in the language the dialog names, else the chosen print format's own, else the
  user's; a print sent from the Desk's own print view follows the print format's language there.
- *Verify book* and the print's chain line re-read every line of the sequence each time: a book of
  many years' lines takes longer to verify. Removing a whole sequence together with all its lines is
  detected only when a signed-off period sealed it; the period's record sits in the same database,
  and its print carries the sealed hashes.
- A count row that agrees with the balance writes no line, so its submit does not re-check it; such a
  count settles a reconciliation only while the register still holds what it counted.
- A till's bundle sold today and not yet consolidated: its articles are not taken off the store's stock
  when a reconciliation is checked (the core's reading of the till's pending sales counts their rows,
  not a bundle's articles).
- The cold print checks the right to read the book, not the store: its header names any register
  store's establishment.
- A register count counts an item, not its lots: one row per item, its lot recorded when one is
  named.
- A followed return's note re-applies the book's conditions as they are now: a book whose
  conditions are edited prints its past returns by the new ones.
- A print over 2,000 items of one store stops there and says so; a store with exactly 2,000 items
  is told the same, though nothing was left out.
- A data import of a stock-take of more than 100 rows is refused like a person's (the core queues
  its submit as the person's own action); one of 100 rows or fewer is written flagged.
- A cancel of a reconciliation a count settled is refused for a person even when its error is a
  date or a warehouse: count again and reconcile anew.
- *"This print holds N of the M entries"* counts the book's entries in the range for any signed-in
  holder of the read right, whatever their warehouses; a print nobody signed in for tells no count.
- A document an integration posts through the REST API is refused as a person's submit is (§5, *Who
  is refused*): for a required column or a balance below zero.
- A document the door does not book, moving two declared items at once, takes their register rows
  in its own order: a document locking the same two rows the other way at the same moment is ended
  by the database (rolled back whole, never a gap).
- The stock ledger's backstop acts only where a book's conditions take the line it would write (an
  Issue or a Receipt): a book of sales alone never sees an asset capitalisation of its items.
- A delivery gathering several till sales, or delivering a till order (made from its sales order), reads
  the Desk's own fields, not the sale's details.
- A subcontracting receipt books what it receives; the materials the subcontractor consumes, in the
  subcontractor's warehouse, book nothing.
- A document imported in a background job is written flagged, never refused, like any job's post.
- A line's sequence and balance rows stay locked until the sale's request ends (the payment's own
  bookkeeping included), so an app installed after this one that acts in the same save (a country
  fiscal app) runs while the book's other tills wait.
- A sale with a line to deliver is not checked before the tender: its lines are written when they
  leave, on their deliveries.
- The hash is not keyed: someone with write access to the database who recomputes every hash after
  an edit, or removes the newest lines and rewinds the sequence row, is not detected by the chain
  alone. A signed-off period records each sequence's last number and hash, and its print carries
  them, so such an edit of a line written before a sign-off is found against the period, and
  against the signed paper even if the period's own record was rewritten in the database (the
  period refuses any change through the framework once signed off); an edit of a line written since
  the last sign-off is not. *Verify book* then names the anchored entry: the change is there or
  before it.
- A line whose submit stamped its entry on a period's last day and committed just after that
  period was signed off joins the signed-off period with no anchor (the sign-off reads the
  sequences as they stood when it began).
- The verdict a sign-off records is stored in the signer's language; every print states the chain
  again in its own.
- An official book's start may name any item: one for an item the book never takes leaves an empty
  sequence, which *Verify book* counts with no entries and *Sign off* never seals (a dated schedule takes an item on
  other days than today, so the start is never held to today's class).
- A balance brought forward is read as the person printing may read the lines before the range: one
  who may read fewer gets a shorter list, and the print does not say so.
- The print translates a line's kind in the register's own words; the Desk's list and form of the
  lines show the kind with its general translation.
- A correction copies the line it corrects, a person's columns included: a version-1 line and its
  corrections written before version 2 carry a person's details that cannot be erased.
- A `Date` detail and the authority's date read from text parse it month-first, as the first
  version did (`05/01/1990` is 1 May), and text that is not a date leaves the column empty with no
  message; an `Age` reads only a date or `YYYY-MM-DD` text.
- An opening count reads its book's lines under a lock (it must see none before the first): two
  openings at go-live, or an opening beside a drain into the same book, can be ended by the
  database (rolled back whole, never a gap).
- A record lookup matches the customer, the record linked to the customer, or the user; matching
  the prescription's own patient (`match: "prescription"`) is refused: a carer buying for a patient
  fills the line from the carer's own record, or none.
- A kept book is adopted at a reinstall with its stored declaration, not the new version's.
- A book cannot change in an update, not even its title, cite or a column label: a corrected
  book ships under a new id, which numbers from 1. Changing the printed words in place is a later
  version's.
- A class a book takes is named on the install's to-do when it is not yet a record of its
  dated table's linked class field; a class read from an Item field (`item_field`) and an axis
  value (`KE Controlled`) are not checked: a misnamed one matches no item and the book takes no
  line.
- The register stores mapping is not checked against a premises: the shop maps it.
- A person's columns are held back by their permission level, which the framework does not apply
  everywhere: the Desk's group-by count on a list's sidebar and a link search still answer on a field
  above a reader's level (each asked of the framework, as for any role-limited field). System
  Manager reads them only when a book names it its count role (Administrator always does).
- Two *Erase persons' details* run at once on one store may list an entry in both records; each
  record is still true.
- A print format typed on *Retail Register Line* itself prints the line as the user rendering it may
  read it (the line empties a person's columns before any print); a print mailed or queued carries
  its sender's view, as every print does. A template that reads a line by itself
  (the framework's own `get_doc` or `db.get_value`) reads it whole: print the book through the period
  (`ivn_register_print`), never that way.
- A book's `retention_years` cannot be shortened once it has lines, a mistyped one included: the
  shop switches that book off and declares a new one (numbering from 1), the old book kept.
- A book switched off before this version keeps its count role without the person columns' level
  until it is saved switched on again (no shop ran the door before it).
- A register store whose chain is broken can never be erased from: the act will not blank a line a
  change may have touched, and a line is never rewritten. The shop takes the broken book to its
  inspector.

## 7. The count, the period and the print

- **The count.** A *Retail Register Count* counts a book's items at one register store against the
  book's own balance, not the stock ledger's (a book that keeps no balance is not counted). Each item
  on one row; its save shows the balance it is counted against and the difference. Approved (submitted)
  only by the book's count role; where the book declares `count_witness`, a second user holding that
  role, named on the count, signs it first (*Sign as witness*); only that action writes the signature,
  and a change to what was counted (the book, the store, the kind or a row) takes it away. Its submit writes a `Count` line for each item whose count differs, so the
  balance becomes the counted quantity, numbered like any line; it is refused if the balance moved
  since the count was saved (save it again, and count again if stock moved). A count is never
  cancelled: count again. A count of kind **Opening** writes each item's opening, once, before its
  first line, so a shop adopting the book mid-way enters its balances. A count also brings a balance
  that had no opening under the below-zero check.
- **Who may count.** Saving a switched-on book gives its count role, on the door's own records, the
  rights to make and approve counts and to read and print the book, each right stated (no export),
  removed with the book when it is deleted or from the old role when the book names another (a row
  the shop's admin made for that role stays; System Manager's are never taken). A count's lines name the register
  store's warehouse, so a viewer kept to other warehouses does not read them.
- **A Stock Reconciliation follows the register.** One that changes the quantity of an item a book
  keeping a balance takes, at a register store whose balance has its opening (a move between two
  warehouses of one register store changes nothing the register keeps), passes only where the stock
  the store will hold (its warehouses' stock less what the register booked for till sales the stock
  ledger has not posted yet) equals the register's balance and an approved count, not used
  before, that counted it; and only when it is dated after that count, with no later stock movement of
  the item there. That count is then used, once. A person cannot cancel a reconciliation a count
  settled (its stock would move back past the register): count again; an import's cancel writes the
  move back as flagged lines. Where the till's open sales are the only difference, the refusal names
  the quantity to reconcile to. A reconciliation of more than 100 rows, which the core submits in
  the background, is still the person's own. A person's or an integration's submit is refused otherwise (*"⟨item⟩ is kept in ⟨book⟩: count it there first
  (a count of ⟨book⟩ by ⟨role⟩), then reconcile it to the counted quantity."*); an import's job writes
  the change as flagged lines. The reconciliation writes no line: the count did. Before the opening
  nothing is refused: a shop loads its stock, then counts its opening. The reconciliation does not
  name its count; the count is found by its book, store, item and quantity.
- **A loss, a disposal.** A *Material Issue* whose Stock Entry Type is **Loss or theft** writes a
  `Loss` line, one of type **Disposal** a `Disposal` line (both types are made once a book is switched
  on), so a book of supplies that excludes losses does not take one. The types' names are the door's:
  a shop's own type of that name with another purpose books neither. In a book that declares
  `loss_count_hours`, a loss makes a count of every item of the book at that register store due
  within those hours: the item's register state carries `count_due_by` (the earliest deadline while
  one is owed) and `last_loss_at`, an open task a list can show, and a register count of the item
  made at or after the book's last loss at that store clears it, whether or not it writes a line
  (even after the book's hours are taken off). Nothing is refused while
  a count is due. The items made due are those with a register state at that store when the loss is
  written (an item never entered in the book there has none to count). A loss entered by mistake and
  cancelled still owes its count: the cancel is a correction, and the register recorded the loss.
- **The period.** A book with `period_months` keeps periods per register store from 1 January; its
  return is due `return_due_days` after a period's last day (0: on that day). Each line carries the
  period it was written into, by its entry date, so a sale drained after a period ended goes into
  today's period with its own date, and a past period's print never changes. A period is made by its
  first line, with the establishment's name (the company's) and address (the register store's
  warehouse, else the company's) copied then: the print readers serve neither.
- **The print.** The door's one plain print format, *Retail Register Plain*, prints a book from a
  period (an A4 landscape page; the prescription or permit and each declared detail as "label: value"
  in one *Particulars* column): every line of the book at that register store in the period's dates, read through `ivn_rows`
  as the person printing may read them. *Print book* on the book's list and form prints any book for
  any register store and date range, over a period made for it and never saved (the inspector's cold
  print; today's dates are the store's daily print for an outage), in the door's plain layout or a
  market's own print format on the period chosen in the dialog. A book that keeps a balance prints
  a page per item, with the balance brought forward and a page for an item with stock and no movement
  in the range. An opening or a count prints as a note; a correction as the book's `correction` mode
  says (a reversing line with its note, a dated note, the original struck through with a signed note,
  or a signed amendment); a return a book without a balance took only because its original did prints
  as a note of the return, found by applying the book's conditions to the stored line again. Each
  print says how many entries it holds, says so when it stopped at its reading limit, and when the
  person printing may read fewer entries than the book holds in the range (another warehouse's, or
  an e-mail, a background job or a shared link, where the readers answer nothing) says *"You may read
  N of the M entries"*, never showing a partial or empty read as the book. A market's layout is its declaring app's print format on *Retail Register
  Period*, which reads the period as `doc` (`book`, `register_store`, `from_date`, `to_date`,
  `establishment`, `establishment_address`, `chain_status`, `status`, `signed_off_by`,
  `signed_off_at`, `sealed`; its dates may be passed to `ivn_rows`
  filters as they are) and may call `ivn_register_print(doc)` for the same pages; the contract test
  `test_every_field_the_kits_register_prints_read_on_the_period_is_a_field_of_the_period` holds both.
- **The language and the direction.** *Print book* asks a language (empty: the chosen print
  format's *default print language*, else yours); the core prints right to left in a right-to-left
  language, and the plain format follows it. A kit's print format may declare
  `default_print_language` in its manifest (a language the site has).
- **What the book is kept on.** The print says it under the entries: a `system_of_record` book is
  this system (its print is a copy), a `regulator_system` book a working register beside the
  authority's own system; only a `printed_book` or `official_book` carries the *kept as the book*
  signature line.
- **An official book's pages.** On an `official_book`, *Official book page* (the book's form, its
  count role) states where the next entry of a sequence lands in the authority's book: the volume,
  the page, the line on that page and the book's lines a page (a book numbered per item names the
  item). Each entry's place is then worked out from its own number, so a reprint never renumbers,
  and a start applies only from the next entry, never to one already written (a start no entry has
  used yet is corrected in place; a start before the last entry's place is refused). The print gives
  a sheet per page of the authority's book, each entry at its line, blank rows for the page's lines
  before the range, and the entries before the first start apart, at no place; a sheet holds one
  sequence (a book numbered per item prints per item, whether or not it keeps a balance), and a book
  numbered per store prints as one run whose first sheet names each item's balance brought forward,
  an item with stock and no movement in the range included. A market's print
  format gets the same sheets from `ivn_register_print(doc)` (each with `place`; each row its
  `place_line`, a blank row `kind: blank`, a correction's note in the row's `note`); the starts
  themselves are the door's, read with its own rights.
- **The period's close.** *Sign off* on a period (the book's count role, after its last day) marks it
  *Signed off* with who and when, the chain's verdict, and each of the store's sequences' last
  number and hash (`sealed`); from then on *Verify book* checks them, and finds a line changed or
  removed before the sign-off even if every hash after it was recomputed. A period is signed off
  once, and is never changed or deleted after it (only *Sign off* writes what a sign-off records); a
  chain already broken at the sign-off is recorded and seals nothing. Its print names who signed it
  off, each sequence's sealed entry and hash, and prints spaces for the close's signatures and seal.
- **The balance before a line.** A book that keeps a balance prints it inside the Balance cell,
  under the balance after (*before: N*); a print format reads it as `balance_before` from
  `ivn_register_print(doc)`.
- **The plain print's columns.** The number columns (No., the line in the book, the date, the entry,
  the lot, the quantity, the balance) take fixed narrow widths so the item, the document, the name and
  the particulars have the room, and a heading never breaks inside a word; the *Reference* column is
  left out when every printed line's reference repeats its own document's number (a stock entry's).
- ***Verify book*** (the book's form) re-reads every sequence of the book: numbers whole from 1, each
  line's hash recomputed from what it holds and linked to the line before, the sequence's last number
  and hash its newest line's, and no line outside a sequence. It answers *Whole* or names the first
  entry where the chain breaks; every print carries the same verdict for its store's whole chain, never
  only its own dates. A correction of an entry printed in an earlier period prints as a note naming
  that entry.

## 8. Who reads a person's details, and when they are erased

- **Who reads them.** A line's person columns — `counterparty`, `counterparty_address`,
  `correction_note`, `detail_1` … `detail_6` — and its `person_seal` sit at permission level 1.
  Saving a switched-on book gives its count role that level's read on the lines (System Manager too,
  when a book names it); any other role reads a line without them, unless the shop gives it the
  level in the core's *Role Permissions Manager*. The framework leaves them out of the line's form,
  its lists and report, *Data Export* and `ivn_rows`; the record API returns them empty when it
  reads one line (keys kept: an event-feed application's user reads `counterparty: null`) and leaves
  them out of a list (an integration that copies the register elsewhere is given the level, or
  knows an empty or missing column may be a hidden one).
  A print through `ivn_rows` or
  `ivn_register_print(doc)` (every print of the book from its period) shows only what its viewer may
  read, and the plain
  print says *"A person's details are not shown: your role may not read them."* A level belongs to
  the record type, not to a book: a role that reads one book's people reads every book's.
- **A field only some roles read, named by a book.** The book writes it whoever submits (the law
  wants the line whole), so its readers are then the line's: a detail slot or the counterparty is
  read only by a role given level 1 here, whatever roles the field itself names. Name such a field
  only there: the checker refuses it in `authority.desk_fields`, `authority.dispenser_licence` or a
  `columns_from` → `reference_no`, which every reader of the line reads, and as the item's class
  (`class_source`), which the book also routes on (take the items by `item_groups` instead). ⚠ A
  detail slot hides its value, not what the book does with it: a condition on the slot decides
  whether a line is written, and a `required` slot left empty marks the line `incomplete` and names
  the slot in its remark (or refuses a person's submit, naming it), both read by every reader of the line.
- **When they are erased.** During a book's retention the register is kept whole, whatever a
  person asks. After it, *Erase persons' details* on the book's form (its count role; never on a
  schedule) asks a register store, an optional cut-off date (*entered up to*) and the shop's own
  reference to the destruction record its market asks for (a committee's minutes, the inspector who
  was present). It closes a volume at the last day whose retention has passed — today less
  `retention_years`, or the shop's earlier cut-off — and blanks the person's columns of the lines
  entered up to that day; in a book with periods, only a line whose period is signed off and ended
  that long ago. A person's columns are the party columns on the line of a customer's document (a POS
  sale, a Desk sale or credit note, a delivery: never a supplier's or another store's) and each detail
  the book declares a person's: declare `person: 1` on a detail that names the person supplied or a
  third person (Kenya's purchaser's occupation and purpose, the name and address of the person giving
  a certificate) — the default reads only the customer's own record and an age as a person's.
  A line is erased together with every correction of it, and only when all of them are due; a line
  written before version 2 is never erased (the act says how many it kept). The quantities, the
  balance and the chain stay: each erased column's digest is what the hash covers, so the line and a
  signed-off period's sealed anchors still verify. An act erases at most 5,000 entries; run it again
  for the rest (it says so). It refuses a book whose chain is broken, and a register store that is
  not the book's. A book's `retention_years` is never shortened once it has lines (lengthened, for
  the UAE's 25 years, it may be).
- **The record of it.** Each act writes one *Retail Register Erasure*: the book, the register store,
  the day its volume closed, the retention in force, who and when, the shop's reference, how many
  entries it erased and kept, the erased entries as the printed book numbers them (*Entry numbers*,
  per item where each item numbers from 1) and each erased line with its columns. It is never changed
  or deleted. *Verify book* checks every erased column against these records: one no record names
  reads *"Broken at entry N of … : a person's details were erased with no record of the erasure."*,
  so a blanking made outside the act reads broken. The record is not hashed or anchored: whoever can
  write the database can write a record too, so the market's own signed destruction record is the
  anchor outside it. A printed erased entry says *"A person's details erased after the retention."*
  in its name cell; a print format reads `erased` on each line from `ivn_register_print(doc)`, and
  may read the records through `ivn_rows`.
- **Backups.** An erased value stays in the site's backups and the database's own logs until they
  rotate out; the shop's backup retention is part of its destruction record.
- **What it does not erase.** The sale, delivery or receipt the line was written from keeps its own
  customer, and the pharmacy app's patient record its own details: each is erased by its owner's
  process. The staff columns (`dispenser`, `signed_by` and their names) and the prescription or
  permit number (`authority_no`, which routing reads) are not a person's columns here.
