<!-- Source: ivendnext/iVendNext_PWA docs/extending/fiscal_reader.md @ c39b1449937a, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Fiscal reader

**Contract:** [`fiscal_reader.v1.schema.json`](../extension_contracts/fiscal_reader.v1.schema.json)
· samples: [`samples/fiscal_reader/`](../extension_contracts/samples/fiscal_reader/)
· code: `business_logic/fiscal_app_reader.py` (`read`, `_read_declared`, `writer_rule_problem`,
`DECLARED_TARGETS`, `result_fields`), the `Retail Fiscal Reader` record's controller;
`business_logic/receipt_fiscal_mark.py` (`fiscal_marks`, the `receipt_fiscal_marks` Jinja method) for
what the receipt prints.

## 1. What it is and when it fires

iVendNext POS never talks to a tax authority. A country's fiscal app on the site — or an **outside
service** that writes through the API — clears or reports each sale, and records the result on the sale.
A **Retail Fiscal Reader** tells the POS which POS Invoice fields hold that result and what each status
value means, so a new country needs no release. The POS then **mirrors** the result onto its own fiscal
fields, which every receipt and fiscal screen reads.

It fires when a submitted sale changes (the sale's own change hook, after every app's submit), and again
whenever the till re-reads a sale that is still waiting — the net for a writer that fires no hook.
Declared readers are read after the compiled-in ones (ZATCA, Mexico): a compiled-in result wins. A
reader serves only sales of the companies it names.

## 2. Version

Version 1: the record's fields below and the three statuses.

## 3. What you declare, and what you write

**The declaration:**

| Field | |
|---|---|
| `source` | an installed fiscal app, or `Outside service`. The record's name: one reader per source |
| `companies` | the companies it serves, each with a clearance-required **Retail Fiscal Regime Config** row for its country |
| `status_field`, `ref_field`, `qr_field`, `signature_field` | the POS Invoice fields holding the status, the tax receipt number and, optionally, the authority's QR payload and its seal or digital signature: all different fields |
| `status_map` | each value your source writes, once, and what it means: `CLEARED` · `REPORTED` · `PENDING` |
| `writer_role`, `writer_users` | outside service only: the one role that may write the result fields, and the only users who hold it |
| `enabled` | on by default |

**The writer rule** (checked at save, and again, live, every time a value would be mirrored): every
result field sits at a permission level **above 0** that **no role may write** — except, for an outside
service, its own writer role, held by its declared users only and never an automatic role — and is **No
Copy** (the engine's settlement and order-change steps copy a sale's fields onto a new one). ⚠ Not level
1: the engine grants Accounts Manager write there on POS Invoice. ⚠ Not level 9 either: iVendNext
POS keeps it for its own tax result, which no role may write, so your writer role may not hold
write there either. The service's role also needs write
**and submit** at level 0, so it can submit a draft sale and change every level-0 field a submitted sale
may still change — the record names them when it is saved. ⚠ The level check binds a
permission-checked save by a user who is not Administrator: Administrator, an `ignore_permissions` save
and a direct write to the database bypass it, so code running on the site can always write the fields.

**What an outside service writes.** Its integration user saves the submitted sale through the API with
the result fields filled, **every result field each time**:

```http
PUT /api/resource/POS%20Invoice/ACC-PSINV-2026-00042
{"pp_fbr_status": "Accepted", "pp_fbr_invoice_no": "FBR-1234567890", "pp_fbr_qr": "…", "pp_fbr_seal": "…"}
```

⚠ This write has **no machine contract**: its field names are the ones the reader declares, so a schema
could only say "an object of text values". The rules below are proven by the product's own fiscal-reader
tests, not by the library's samples.

A value is mirrored only when the sale was last saved by one of the writer users, so a value anyone else
saved is never mirrored. A status the map does not know writes nothing. A tax receipt number, a QR and a
seal travel only with a CLEARED or REPORTED result. The QR and the seal are mirrored **exactly as stored**:
nothing trims or re-encodes them (a value of nothing but blanks counts as none). ⚠ When a value holding `<` or `>` (an
XML-form signature) is saved through the API, the framework cleans it of HTML before anything reads it,
in every field type but **Code** (or a field with *Ignore XSS Filter*), so it would reach the receipt
altered: make the QR and seal fields Code fields. A manifest cannot make a Code field, so a reader installed from
a manifest keeps an XML-form seal only if the shop changes that field to Code. A base64 seal or a URL is
unaffected either way. The QR and seal
fields hold text (Data, Small Text, Text, Long Text or Code): a reader naming an image or attachment field
is refused, since the receipt would draw the file's path as the QR.

**What the receipt prints.** Under the totals of a CLEARED or REPORTED sale, the seeded `mPOS Receipt`
and the till's receipt screen print the authority's QR, drawn from the stored payload (encoded UTF-8,
with the framework's own QR library), and the seal as plain text. A payload over 2,000 characters, or
one too large for a QR, is not drawn; the receipt says *"The tax QR is too long to print. Open the sale
in the back office."* instead. A gift copy prints neither: a tax QR can encode the sale's total. A store
whose profile prints the engine's own `Print Format Receipt 3"` gets them too, under its totals, through
the place that receipt leaves for an installed app's lines. A store whose profile prints a format of its
own shows the marks on the till's receipt screen but prints none on paper unless that format calls
`receipt_lines(doc, "totals")` (as a copy of the engine's 3" does) or the Jinja method
`receipt_fiscal_marks(doc)`, which returns
`qr_svg` (the drawn code), `qr_too_long_text` and `signature`.

**What the till does with it:** CLEARED and REPORTED release the receipt. PENDING shows *"Waiting for
the tax receipt number … ask the back office"*. From the moment a sale of a company an outside service
serves is booked on the till, it waits PENDING until the service answers.

## 4. Every refusal, in the product's words

**When the record is saved:**

- *"⟨source⟩ is not an app installed on this site. Name the fiscal app, or Outside service."*
- *"⟨company⟩ does not wait for tax clearance, so its receipts would print at once with no tax receipt
  number. Turn on Clearance required for its country first."*
- *"POS Invoice has no field ⟨field⟩."* · *"The status, tax receipt number and QR fields must be different
  fields."*
- *"Row ⟨n⟩: the value the source writes is empty."* · *"Row ⟨n⟩: say what ⟨value⟩ means."* · *"Row ⟨n⟩:
  ⟨status⟩ cannot be a result. Use CLEARED, REPORTED or PENDING."* · *"Row ⟨n⟩: ⟨value⟩ is listed twice."*
- an enabled reader that breaks the writer rule: *"An outside service needs its own writer role, never
  ⟨role⟩."* · *"⟨field⟩ is not a field of POS Invoice."* · *"⟨field⟩ is copied onto a new sale (No Copy is
  off), so another sale's result could arrive on it."* · *"⟨field⟩ is at permission level 0, so anyone who
  may edit a sale can write it."* · *"⟨field⟩ is at permission level ⟨n⟩, which iVendNext POS keeps for its
  own tax result. Use another level."* · *"⟨field⟩ is at permission level ⟨n⟩, which ⟨roles⟩ may also write."* ·
  *"The writer role ⟨role⟩ is also held by ⟨users⟩."* · *"The writer role ⟨role⟩ may write permission level
  ⟨n⟩, which iVendNext POS keeps for its own tax result."*

**When a value is not mirrored** (the receipt keeps waiting; the Error Log says why):
*"Fiscal reader ⟨source⟩: its result fields are writable by another role; nothing mirrored."* (with the
writer-rule sentence above) · *"Fiscal reader ⟨source⟩: its result was not saved by its writer users;
nothing mirrored."* (*"Last saved by ⟨user⟩, not by a writer user."*).

## 5. Consent, and when the service is down

Nothing leaves the shop: the service writes in, so no consent is recorded. Only a System Manager opens
the record.

**Down:** the sale waits PENDING and the receipt is held. ⚠ A recorded PENDING is held until a result
arrives, whatever the store changes later (clearance off, the company dropped, the reader disabled): the
service, or the back office, owes that sale its answer. No retry is promised by the POS.

## 6. Offline

A sale made offline reaches the server when the till drains it; from then it waits PENDING like any other
until the service answers.

## 7. Money and limits

**Fiscal, not money.** The reader moves no amount; it decides whether a receipt may print as a tax
document. ⛔ Never `NOT-FISCAL`: that is the POS's own classification, and it releases the receipt.

Limits: one reader per source · each value once in the map · three statuses · a QR payload up to
2,000 characters. The compiled-in readers carry their apps' marks too: Mexico's SAT verification
URL as the QR and its CFDI seal as the seal (not the SAT seal: the app does not keep it whole), and
ZATCA's QR, which that app keeps only as a picture (`ksa_einv_qr`). The receipt prints that picture's
code only on a cleared or reported sale, only from a file on this site that came attached to that
sale and field (a file first attached to another sale does not count), read back module by module and
redrawn; a picture that is not an opaque PNG of clean square modules prints nothing, and the receipt
says nothing about it (the error log does). Nothing is fetched. A declared reader still names text
fields only. ⚠ The compiled-in readers get no writer rule: both apps keep their fields at level 0, so
anyone who may edit a draft sale can type them, and where the Mexico app does not stamp a sale (its
e-invoicing off, or a sale copied from another) another sale's verification QR can print. A Mexican
receipt carries the verification QR, the CFDI number and the CFDI seal only — not the SAT seal, the SAT
certificate number or the original string, which the app does not keep. A ZATCA company not on phase 2
records `Phase-1 QR Generated`, a status the reader does not know: its receipt prints no ZATCA QR, and
where the store's regime requires clearance it is held.

## 8. Worked examples

The names in the samples are the test bench's (`MPOS Test Co`, the `pp_fbr_*` fields, the role
`PFiscal Test Integration`).

**A real-time reporting service.** `source: Outside service`, the company, three custom fields on POS
Invoice at a level only the service's role writes (No Copy, allow on submit), the role and its one
integration user, and the map *Accepted → CLEARED*, *Queued → PENDING*. The till books a sale; it waits
PENDING; the service reports it, saves *Accepted* and the invoice number as its integration user; the
receipt prints with the tax receipt number.

**A clearance service with a QR and a seal** (a Mexico-shaped service: a seal and the verification QR).
The same, with `signature_field` naming a fourth field at the service's level. The receipt of a cleared
sale prints the QR and the seal under the totals.

**A reporting regime with no QR.** The same, without `qr_field`, and the map *OK → REPORTED*. A sale the
service saved as *OK* releases its receipt as reported.

## 9. Telling an AI assistant

> Declare a Retail Fiscal Reader for iVendNext POS, version 1, as JSON matching
> `fiscal_reader.v1.schema.json#/$defs/declaration`; the samples under `samples/fiscal_reader/` show
> accepted and refused records. Map each status value the service writes, once, to CLEARED, REPORTED or
> PENDING — never NOT-FISCAL. Put the result fields at a permission level above 1, other than 9, that only the
> service's own role writes, mark them No Copy, give that role to the integration user alone, and have
> the service write every result field on each save. Name the authority's QR payload's field as
> `qr_field` and its seal's as `signature_field` to have the receipt print them.
