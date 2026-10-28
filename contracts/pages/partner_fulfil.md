<!-- Source: ivendnext/iVendNext_PWA docs/extending/partner_fulfil.md @ 60147699cce4, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Partner fulfil — a code your service makes for a paid sale line

**Contract:** [`partner_fulfil.v1.schema.json`](../extension_contracts/partner_fulfil.v1.schema.json)
· samples: [`samples/partner_fulfil/`](../extension_contracts/samples/partner_fulfil/)
· stand-in: [`standins/voucher_service.py`](../extension_contracts/standins/voucher_service.py)
· code: `business_logic/partner_fulfil.py` (`write_rows`, `ask`, `void`, `assert_returnable`, `codes_for_invoice`,
`validate_answer`, `validate_subscription`), `api/partner_fulfil.py`, the till's waiting receipt and the return
screen's **Cancel code** in `public/js/mpos_partner_fulfil.js`.

## 1. What it is

Some items only your service can make, at the moment of sale: a digital voucher, a mobile top-up PIN, a game
card, another brand's e-gift card. With extension point **`fulfil`**:

- **The sale is paid first.** Your service is never asked before the money is taken, so an abandoned sale never
  leaves a live code. (If you must say *none left* before payment, answer the check before payment with a
  refusal: [partner check](partner_check.md).)
- **One code per sold line.** The till sells such an item one per line (a second scan is a second line).
- **The receipt waits for it.** The cashier sees *Waiting for ⟨your label⟩'s code for ⟨item⟩*, with **Try again**
  and **Print without it**. Your code's lines print under the item: on the screen receipt, the paper receipt,
  the gift receipt and every reprint.
- **A refund waits for the cancel.** Before that line can be refunded, at any door (the till's refund, exchange
  or return, a return without a receipt, a basket that brings it back, a parked refund, a layaway or order
  refund, the Desk), its code must be cancelled with you. The refusal says where: the sale in
  Returns on the till, or its `Retail Partner Code` record in iVendNext Desk.

Such an item is sold and paid at the till only: it is refused on a quote, an order, a layaway plan and a held
sale, and refused offline (*"⟨label⟩ needs a connection to sell this item."*).

## 2. The declaration

A `Retail Extension Subscription` with point **`fulfil`**: your address, your secret, a label (what the cashier
reads), a time to answer (5 seconds unless raised, at most 10) and in **settings** the items you make — the
scan capture's filter:

```json
{"item_groups": ["Game Cards"]}
```

`item_groups` (a group and every group below it) and/or `item_field` (an Item field that is set). The down
answer is fixed (`wait`): a paid sale is never undone, so when you are slow or down the receipt waits (§5).

**What you are sent, the consent the shop gives:** the sale's number, the store, the till's POS Profile, the
company, the currency, the language, the customer's id, and the line's item code, item group, unit, face value
and amount, with a key that stays the same for that line. To cancel: the same key and your code's reference.
No card data, serial, batch or other line.

## 3. The calls

Every call is a POST of `{"point": "fulfil/1", "context": …}` with the shop's secret, as every extension point
(`X-iVendNext-Point: fulfil/1`).

### 3.1 `issue` — after the sale's booking commits, once per line

```json
{"v": 1, "point": "fulfil", "call": "issue",
 "idempotency_key": "POS-INV-00042:a1b2c3d4e5", "invoice": "POS-INV-00042",
 "store": "Mall Branch - NM", "pos_profile": "Mall Till 1", "company": "Northgate Market",
 "lang": "en", "currency": "ZAR", "currency_exponent": 2, "customer": "CUST-0007",
 "line": {"item_code": "GAME-100", "item_group": "Game Cards", "uom": "Nos",
          "face_minor": 10000, "amount_minor": 9000}}
```

- **`face_minor`** — the voucher's value: the line's list price (its rate where it has none), in the sale's
  currency, in minor units (`currency_exponent` digits). A voucher sold at a discount is still worth its face;
  the discount is the shop's.
- **`amount_minor`** — what the line was sold for; the same field and meaning as the check before payment's.

Answer one of:

```json
{"verdict": "issued", "ref": "GZ-77120", "lines": ["PIN 4821 0937 5521", "Valid until 16 Oct 2027"]}
{"verdict": "refuse", "reason": "None left in this denomination."}
```

- `ref` — your own id of the code, 1 to 80 plain characters.
- `lines` — what prints under the item: 1 to 6 lines of at most 48 plain characters.
- `refuse` — the receipt prints *"⟨label⟩ could not issue this. Ask the store for a refund."* and the cashier
  is told to refund the line.

⛔ **The whole answer is refused** — and read as no answer — if it carries any other key (an amount, a price,
a quantity), markup, or is over 64 KB.

### 3.2 `void` — before the line's refund, when the sale is cancelled, or for a code that came late

```json
{"v": 1, "point": "fulfil", "call": "void",
 "idempotency_key": "POS-INV-00042:a1b2c3d4e5", "invoice": "POS-INV-00042",
 "store": "Mall Branch - NM", "pos_profile": "Mall Till 1", "company": "Northgate Market",
 "lang": "en", "ref": "GZ-77120"}
```

`ref` is the code to cancel; it is **empty while the code is still on its way** — cancel whatever the key holds.
Answer:

```json
{"verdict": "voided"}
{"verdict": "refuse", "reason": "This code has been used."}
```

A refusal keeps the code, so that line cannot be refunded; your sentence is shown to the cashier.

## 4. Your two promises — the key rule and void-wins

1. **The same `idempotency_key` always returns the same code.** A retry (1 and 5 minutes after the sale, and
   each **Try again**) sends the same key; a reply that was lost is asked again.
2. **A `void` on a key wins over any later `issue` on it.** Once you have voided a key, refuse to issue on it.

The [stand-in](../extension_contracts/standins/voucher_service.py)
keeps both, and its test is the conformance check to run your service against.

**On our side, and why there is no lock across your call:** iVendNext writes one *Pending* record per sold line
inside the sale's own booking, then asks you after the booking commits. It holds **no lock while it waits for
you** (a till's sale must never wait on a partner). Two asks can therefore overlap — the first try and a
cashier's **Try again** — and the guarantee is (a) your key and (b) our re-check: an answer is written only
while the line is still *Pending*. A different code arriving for a line that already has one, was refused or
was cancelled is **cancelled with you at once** (a `void` with that `ref`) and flagged for the shop.

## 5. Slow, down, refused, offline

- **Slow or down at the sale:** the sale stands. The receipt waits; **Print without it** prints *"⟨label⟩ code:
  on its way. Ask the store to reprint this receipt."* and the retries go on; a reprint once the code is issued
  prints it. After three failed tries the cashier is told *"⟨label⟩ has not answered. The sale is paid; try
  again later. To refund this line, cancel its code first."* and the line is flagged (*Sales to review*).
- **Refused:** the receipt releases with the refusal line; the line is flagged.
- **Offline:** the item cannot be sold. A sale drained with one anyway is never refused: its record is written
  at the drain and you are asked after it; the line is flagged.
- **A return while you are down:** refused — money is never given back for a code that may still be live.
- **A cancelled sale:** codes still on their way are cancelled at once; issued codes are voided with you after
  the cancel commits. A void you refuse is flagged for the shop.

## 6. Where the code lives

In the `Retail Partner Code` record: `ref` in plain text, the printed `lines` encrypted. Only the receipt reader
decrypts them, on the server; a list, a REST read, the record's own password read and the Extension Log never
show them (the log carries the outcome and `ref`). **Cancel code** on the record (iVendNext Desk) asks you to cancel; it needs write on the
record, and on the till the right to return that sale (or a manager's approval of that return). A cancelled
code with no refund booked after it is flagged the next day (*code cancelled, nothing refunded*).

## 7. Bounds, stated

- **A shop's own print format** prints your code only if it calls `receipt_partner_code(item)` under each item,
  as the shipped formats do. The screen receipt always shows it.
- **A Desk credit note against a day's consolidated invoice** is checked by item, not by line: a live code of
  the same item on any sale that consolidation took in refuses it. It fails closed (no refund with a live
  code). Where the ERP layer keeps each POS line on the consolidated invoice, a per-line check is possible
  and is not built: cancel the code first, then raise the credit note.
- **A cancelled sale's code the partner does not answer about** is flagged for the shop (*Sales to review*)
  and may be asked once more by the minute sweep, then not again by itself: press **Cancel code** on the record. The cancel runs as a job after the sale's
  cancel commits; if that job is lost (a worker restarted before it ran), nothing lists the code: find the
  sale's `Retail Partner Code` records and press **Cancel code**.
- **A receipt sent by text message** carries the receipt's number and total, not your code; a plain email's
  text the same, while its attached receipt prints the code where the paper does.
- **Offline, an item offered beside another (an offer) or given by a promotion** is added (from its sheet,
  or by the promotion itself) without the till's offline refusal; such a sale is drained and its line flagged (§5).
- **A line of more than one** cannot be sold at the till; a booking made another way gets one code, and
  its record is flagged (not listed in *Sales to review*).
- **Who sees the code:** anyone who may print the sale prints its code (it is on the receipt). The record and its
  reads stay masked.
