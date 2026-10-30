<!-- Source: ivendnext/iVendNext_PWA docs/extending/doccheck.md @ c39b1449937a, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Document check

**Contract:** [`doccheck.v1.schema.json`](../extension_contracts/doccheck.v1.schema.json)
· samples: [`samples/doccheck/`](../extension_contracts/samples/doccheck/)
· code: `business_logic/partner_doccheck.py` (`validate_subscription`, `before_submit`, `on_validate`,
`validate_answer`, `confirm`), `business_logic/partner_point.py` (`call_in_save`, the log),
`public/js/doccheck.js` (the Desk's question).

## 1. What it is and when it fires

Your service has the last word before a back-office document the shop names becomes final: a purchase
order line blocked by data held in the shop's ERP, a goods receipt checked against the supplier's terms, a
stock transfer checked against real-time stock elsewhere.

A System Manager subscribes your service to the extension point `doccheck` for ONE record type — a
Purchase Order, a Purchase Receipt, a Purchase Invoice, a Stock Entry, a Material Request, any record type
that is submitted. It fires **when the document is submitted**, from every door: the iVendNext Desk form or
list, a data import, and the API. Where the subscription asks for it, it also fires when a **draft is
saved**. Save rules run first, so a submit a house rule refuses never reaches you.

⛔ **Never a till's sale.** POS Invoice, POS Opening Entry, POS Closing Entry and POS Invoice Merge Log are
refused as targets. And a record the till's own booking writes — a layaway's Sales Order, the engine's
Payment Entry, a delivery's Sales Invoice, a layaway forfeit's Journal Entry, the backing Quotation the till's
quote edit or quote cancel submits or cancels, anything an offline sale writes
when it reaches the server — is **not checked**, even on a record type you subscribe to: the customer is at
the counter and the cashier has no screen for a question or an approval. Each such write is logged *not
asked*. The till's door for a partner is the [check before payment](partner_check.md).

## 2. Version

Version 1: the body carries `"point": "doccheck/1"` and `"context": {"v": 1, …}`, and the header
`X-iVendNext-Point: doccheck/1`.

## 3. What is declared, what is sent, what you answer

**The subscription** (Retail Extension Subscription, extension point `doccheck`): your address, the secret,
the time to answer (3 seconds unless raised, at most 10), the answer when you are down, and its settings:

```json
{"record_type": "Purchase Order",
 "send_fields": "name, supplier, grand_total, items(item_code, qty, rate)",
 "on_validate": false,
 "fill_fields": ["custom_erp_po_number"]}
```

- `send_fields` uses the [Desk action's](desk_action.md#3-what-is-declared-what-is-sent-what-you-answer)
  grammar and limits (40 fields, 5 tables, 500 rows a table).
- `on_validate`: `true` checks a draft's save too — ⛔ not on Sales Order, Sales Invoice, Delivery Note,
  Payment Entry or Journal Entry, which the till's own booking also inserts (a draft check holds the
  record type's numbering while you answer, and the till's next booking would wait behind it).
- `fill_fields`: the fields your answer may fill — at most 10, ⛔ **only fields the shop added itself**
  (a custom field), each one a user fills in (text, a number, a date, a choice, a link), never a money
  field and never a name a total is computed from. A standard field — a ledger account, a posting date,
  a warehouse — is never filled: your answer arrives after the record's own checks ran. Refused when the
  subscription is saved, and again when you answer. A filled value then meets the shop's own save rules
  (a *derived* rule is not re-worked at a submit).

**The request** — one signed `POST` per document and moment, with the same headers as every extension
point (`X-iVendNext-Timestamp`, `X-iVendNext-Signature`, `X-iVendNext-Request-Id`) plus
`X-iVendNext-Point: doccheck/1`:

```json
{"context": {"company": "Gulf Trading LLC", "doctype": "Purchase Order", "event": "submit",
  "fields": {"grand_total": {"currency": "AED", "currency_exponent": 2, "minor": 1250000},
    "items": [{"item_code": "SKU-1", "qty": 50000, "rate": {"currency": "AED", "currency_exponent": 2, "minor": 25000}}],
    "name": "PUR-ORD-2026-00118", "supplier": "Acme Supplies"},
  "lang": "en", "name": "PUR-ORD-2026-00118", "user": "buyer@shop.example", "v": 1},
 "point": "doccheck/1"}
```

Money goes as minor units with its currency, a quantity as thousandths, as for the Desk action.
`event` is `submit` or `validate` (a draft's save).

**The answer** — HTTP 2xx, a JSON object of at most 64 KB, one of five:

| `verdict` | Also carries | What happens |
|---|---|---|
| `allow` | nothing | the submit goes on |
| `refuse` | `reason` (plain text, at most 140) | the submit stops; the user sees your reason |
| `ask` | `question` (plain text, at most 140) | in the Desk the user sees your question; *Yes* submits. An API call is refused with the question as its sentence and carries `mpos_doccheck.token` in the error; posting it to `ivendnext_mpos.api.doccheck.confirm` (the same user, within 5 minutes) and submitting the unchanged document again submits it. A submit the framework runs in the background (an import, a large list's bulk submit, a Journal Entry or Stock Reconciliation of more than 100 rows — the framework queues those from every door) cannot show a question, so it is refused in words that say so: for such records answer `allow` or `refuse`, never `ask` or `approve` |
| `approve` | `role` (a role of the site), optional `reason` | a user who holds the role is asked to approve, and a yes submits; anyone else is refused: *needs approval by* the role |
| `fill` | `fields`: 1 to 10 of the subscription's `fill_fields`, each a value of its field's type | the values are written and the submit goes on |

## 4. Every refusal, in the product's words

**The answer**, refused whole (the down answer then applies; the log names the reason):
*the verdict is not one of the five* · *the answer carries a key `<verdict>` does not allow* · *refuse needs
a reason* · *ask needs a question* · *`<key>` must be plain text of 1 to 140 characters* (markup, a control
character, a bidi override) · *approve names no role of this site* (Guest, All and Administrator never) ·
*fields must name 1 to 10 fields* · *fields names a field the subscription does not let it fill* · *the
value for `<field>` does not fit the field* (a number for a number, `YYYY-MM-DD` for a date, a listed choice,
an existing record for a link).

**A question in the background**, refused: *`<label>` asks a question, and this document is being submitted in the background, where nobody can answer it: `<question>`*

**The subscription**, refused when saved: *Name the record type in the settings* · *`<type>` is the till's
own record* · *`<type>` is written by the back office for each sale or stock move, never checked* (Serial and
Batch Bundle, Repost Item Valuation, Stock Reservation Entry) · *`<type>` is never submitted* · the Desk action's *Fields sent: …* sentences · *on_validate
must be true or false* · *The till also writes `<type>`, so only its submit can be checked, not its draft.* · *fill_fields must list at most 10 different field names* · *`<type>` has no field `<field>`* · *A service can fill text, a number, a date, a choice or a link, not `<field>`* · *`<field>` is not a field a user fills in* · *A service cannot fill
`<field>`* (not a field the shop added, or money) · *A document check answers every store. Clear the POS Profiles.* · *May approve is for
the check before payment.* · *At most 3 services may check one record type.* · *The checks of one record
type may take at most 10 seconds together.*

## 5. Consent, and when your service is down

The consent text a System Manager ticks is built from the settings. It names the record type, the moment
(submitted, or saved as a draft too), what is sent with every call — the user's login (usually an email
address) and language, the company, the record's type and name — the fields that leave the shop (money as
minor units with its currency, quantities in thousandths), and, when the settings have any, the fields an
answer may fill. A change to the settings (the record type, the moment, the fields that leave the shop, the fields an answer may fill) or to the address clears the consent and stops the calls until it is ticked again.

No answer in time, an address that cannot be reached, or an answer refused whole: the subscription's
declared down answer applies — `allow_and_flag` (the default: the submit goes on and the log row is
flagged), `refuse` (*did not answer, so this document can't be submitted yet*), or `ask` (*did not answer.
Submit anyway?*). A back-office user meets the wait, not a waiting customer, so `refuse` is a fair choice for
a shop that will not submit unchecked.

## 6. Offline

None: back-office documents are submitted on the server. A sale the till made offline never reaches you
(§1).

## 7. Money and limits

⛔ Your answer never writes money: only the named `fill_fields`, checked when the subscription is saved and
again when you answer. The database transaction — the record's own lock included — is **held while you
answer**: at most your time to answer, and at most **10 seconds for all of one submit's checks together**
(3 services per record type at most). A 100-record import against a service that never answers within 3
seconds takes 300 seconds longer, never more than 10 a record at each moment (a draft check and a submit check each have their own).

Bounds, stated: each submitted record has its own 10 seconds — a record another record's submit submits
(an Asset's depreciation schedules) included; a document inserted and submitted in ONE call holds its numbering while you
answer, as a draft check does; a request that first inserts a till sale or a day close leaves every later
submit in it unchecked (logged *not asked*) — the till's own predicate, kept as it is.

The same document, the same fields, the same user and the same moment within 5 minutes asks you **once**:
a resubmit after a refusal, or after the user said yes, gets your earlier answer. Each call writes one
*Retail Extension Log* row (the outcome, your answer, how long it took); a yes writes one more, with the
approver for an approval.

## 8. Worked example — an ERP-held purchase order

The shop's ERP holds suppliers with unpaid invoices. Subscribed on Purchase Order, sending
`name, supplier, grand_total, items(item_code, qty)`, down answer `refuse`, filling the shop's own field
`custom_erp_po_number`.
A buyer submits PUR-ORD-2026-00118 to Acme Supplies:

- Acme is on hold: answer `{"verdict": "refuse", "reason": "The ERP holds this supplier: invoice 4471 is
  unpaid."}` — the order stays a draft and the buyer reads why.
- Acme is fine, but the order is over the buyer's monthly budget: answer `{"verdict": "approve", "role":
  "Purchase Manager", "reason": "Over the monthly budget."}` — the buyer is refused; a purchase manager opens
  the order, submits, approves.
- All clear: answer `{"verdict": "fill", "fields": {"custom_erp_po_number": "ERP-PO-9912"}}` — the order is
  submitted carrying the ERP's own number.

## 9. Telling an AI assistant

> Build the HTTPS service behind an iVendNext document check, version 1. The contract is
> `doccheck.v1.schema.json`: `$defs/request` in (header `X-iVendNext-Point: doccheck/1`), `$defs/answer` out;
> `$defs/settings` is what the shop saves on the subscription. Verify the signature (base64 HMAC-SHA256 of
> `<timestamp>.<raw body>`), answer within 3 seconds (the document's transaction waits for you), treat money
> as minor units and quantities as thousandths, answer one of `allow`, `refuse` with a reason, `ask` with a
> question, `approve` with a role, or `fill` with values for the subscription's `fill_fields` only, and keep
> every sentence plain text of at most 140 characters.
