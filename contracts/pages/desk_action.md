<!-- Source: ivendnext/iVendNext_PWA docs/extending/desk_action.md @ 4c3f11b550f1, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Desk action

**Contract:** [`desk_action.v1.schema.json`](../extension_contracts/desk_action.v1.schema.json)
· samples: [`samples/desk_action/`](../extension_contracts/samples/desk_action/)
· code: `business_logic/desk_action.py` (`validate_declaration`, `parse_send_fields`, `run`,
`validate_answer`), `business_logic/partner_point.py` (the call, the log).

## 1. What it is and when it fires

A partner's button on a shop's own Desk record — *Assign pick route* on a sales order, *Recheck unit
barcodes* on a batch — on the form, or for the ticked rows of a list. A System Manager declares it as a
**Retail Desk Action**; one small Desk script of ours draws it, and no partner JavaScript runs in Desk.

It fires when a user presses it. The server then **re-checks everything the button showed** on the
record as SAVED (never the form's copy): the user holds one of its roles and may read the record, the
record is in an admitted state and meets every condition, each input is of its declared type. Only then
does it send exactly the declared fields to your service and judge your answer.

## 2. Version

Version 1: the body carries `"point": "desk_action/1"` and `"context": {"v": 1, …}`, and the header
`X-iVendNext-Point: desk_action/1`.

## 3. What is declared, what is sent, what you answer

**The declaration** (Retail Desk Action): the record type · the label (at most 40) and an optional menu ·
`form`, `list` or `both` · the roles that see and run it · the states it shows in (draft, submitted,
cancelled; the workflow state, or the status where there is no workflow; up to 3 field conditions) · up to
10 typed inputs for the dialog (`Data`, `Int`, `Float`, `Date`, `Select`, `Link`, `Check`, `Small Text`) ·
an optional confirm sentence · the fields that leave the shop (`name, customer, items(item_code, qty)`) ·
the partner service that answers: a **Retail Extension Subscription** of extension point `desk_action`,
holding your address, the secret and the time to answer. A button that arrives in a manifest is checked
before the shop consents: the manifest checker refuses any input type outside the eight above, naming them
(the product would otherwise refuse it at install, after the consent).

**The request** — one signed `POST` per press (sorted keys, no spaces, ASCII), with the same headers as
every extension point (`X-iVendNext-Timestamp`, `X-iVendNext-Signature`, `X-iVendNext-Request-Id`) plus
`X-iVendNext-Point: desk_action/1`; the signature is the [remote till key's](remote_till_key.md#3-what-is-sent-and-what-you-answer):

```json
{"context": {"action": "3f9c1e2ab4", "idempotency_key": "a1b2c3d4e5f6a7b8", "inputs": {"wave": "Morning"},
  "label": "Assign pick route", "lang": "en",
  "records": [{"doctype": "Sales Order", "name": "SAL-ORD-2026-00042",
    "fields": {"customer": "CUST-0001", "delivery_date": "2026-10-14",
      "grand_total": {"currency": "AED", "currency_exponent": 2, "minor": 23046},
      "items": [{"item_code": "SKU-1", "qty": 2000}], "name": "SAL-ORD-2026-00042"}}],
  "user": "stock@shop.example", "v": 1},
 "point": "desk_action/1"}
```

- **Money** goes as a whole number of minor units with its currency and that currency's digits
  (`{"minor": 12346, "currency": "KWD", "currency_exponent": 3}`).
- **A quantity** — a number field or a typed input whose name holds `qty` or `quantity` — goes as a whole
  number of thousandths (`qty` 1.5 → `1500`). Other numbers go as stored, dates as ISO text.
- A password, an attachment, an HTML field or any field above permission level 0 is never sent —
  checked again at every press.
- `idempotency_key` is the same on a retry from the same dialog.

**The answer** — HTTP 2xx, a JSON object of at most 64 KB: a `message` (the
[till key's shape](remote_till_key.md#3-what-is-sent-and-what-you-answer): title ≤ 60, body ≤ 280, level
info · success · warning), and **at most one** next step:

| Kind | Shape | Checked |
|---|---|---|
| `open_record` | `{"doctype", "name"}` | the record exists and the user may read it |
| `open_page` | `{"url"}` | the address is at or below a [partner page](partner_page.md) placed on Desk |
| `refresh` | `true` | the form reloads |

⛔ **The answer writes nothing.** Your service does its work through its own API calls, with its own
rights, before it answers.

## 4. Every refusal, in the product's words

**At a press, before anyone is called** (the user sees it; one *refused* row is logged):

- *"This button is no longer available. Reload the page."* · *"You may not use ⟨label⟩."*
- *"Choose the records first."* · *"Choose at most 100 records at a time."* · *"A record is chosen
  twice."* · *"⟨label⟩ runs on one record at a time."*
- *"The button sent no request key. Reload the page."*
- *"The dialog's values could not be read."* · *"The dialog sent a value this button does not ask for."* ·
  *"⟨input⟩ is required."* · *"⟨input⟩: the value is not one this button accepts."*
- *"⟨record type⟩ ⟨name⟩ was not found."* · *"You may not read ⟨record type⟩ ⟨name⟩."*
- *"⟨label⟩ does not run on ⟨name⟩ in this state."* · *"⟨label⟩ does not run on ⟨name⟩ as it stands."*
- *"⟨label⟩ cannot send ⟨name⟩ as it stands."* (a money value with no known currency, a table over 500
  rows, a field no longer sendable)
- *"⟨label⟩ cannot reach its partner service: the service is switched off, or a System Manager must tick
  its consent again."*

**After your service was called:** down, slow or unreachable — *"⟨label⟩ did not answer in time. Check
the record before you try again."*; an answer the checks refuse — *"⟨label⟩ answered in a way Desk cannot
use. Check the record before you try again."* The log row says why, in one of these:
*"the answer is not JSON"* · *"the answer is not a non-empty object"* · *"the answer has a kind Desk does
not know"* · *"the answer asks for more than one next step"* · *"message must be {title, body, level}"* ·
*"message needs a title, a body within the caps, and a known level"* · *"refresh must be true"* ·
*"open_record must be {doctype, name}"* · *"open_record names no record type"* · *"open_record names no
record"* · *"open_record names a record the user may not read"* · *"open_page must be {url}"* ·
*"open_page names an address under no Desk page's own address"*.

**When the declaration is saved:**

- *"Choose the record type the button sits on."* · *"A Desk button cannot sit on ⟨record type⟩."*
- *"The label must be 1 to 40 characters."* · *"The menu name must be at most 40 characters."* ·
  *"Choose where the button is shown."* · *"The confirm sentence must be at most 140 characters."*
- *"Tick at least one of: on a draft, on a submitted or on a cancelled record."* · *"⟨record type⟩ is never
  submitted, so tick On a draft."* · *"Name at least one role that may see and run the button."*
- *"A state is at most 140 characters."* · *"⟨record type⟩ has no workflow and no status to match."*
- *"Give at most 3 conditions."* · *"Condition: ⟨record type⟩ has no field ⟨field⟩."* · *"Condition: ⟨field⟩
  is not readable by every reader."* · *"Condition: choose how it compares."* · *"A condition with
  ⟨operator⟩ needs a number."*
- *"A dialog asks at most 10 inputs."* · *"Input ⟨n⟩: use a new field name of lower case letters, digits
  and _."* · *"Input ⟨n⟩: the label must be 1 to 60 characters."* · *"Input ⟨n⟩: choose one of the listed
  types."* · *"Input ⟨n⟩: a choice list needs 1 to 50 lines."* · *"Input ⟨n⟩: name the record type it
  links to."* · *"Input ⟨n⟩: the default is not a value of its type."*
- *"Fields sent: ⟨why⟩."* (the list could not be read) · *"Fields sent: ⟨record type⟩ has no field
  ⟨field⟩."* · *"Fields sent: name the fields of the table ⟨table⟩ in brackets."* · *"Fields sent: ⟨field⟩
  is not readable by every reader."* · *"Fields sent: the table ⟨table⟩ has no field ⟨field⟩ that can be
  sent."* · *"Fields sent: ⟨field⟩ is not a table."* · *"Fields sent: ⟨field⟩ cannot be sent."* · *"Fields
  sent: at most 40 fields and 5 tables."*
- *"The partner service must be a Retail Extension Subscription of extension point desk_action."*

## 5. Consent, and when your service is down

The service's consent text is **built from the declarations that name it**, word for word:

> Sent on each press of a Desk button this service answers: the user's login (usually an email address)
> and language, the inputs the user typed, each record's type and name, and these fields of it (money as
> minor units with its currency, quantities in thousandths).

followed by one line per declaration, `⟨record type⟩ · ⟨label⟩: ⟨fields sent⟩`. Changing what a button
sends (its record type, label, fields or service) clears the consent until a System Manager ticks it
again; switching a button off or on asks for nothing.

**Down:** the one down answer is `refuse` — the user reads *"⟨label⟩ did not answer in time. Check the
record before you try again."* The sentence never claims nothing changed: your service may have written
before it went quiet. 3 seconds to answer unless the subscription allows more, 10 at most. No retry.

## 6. Offline

Desk is online by nature; nothing is queued.

## 7. Money and limits

**Reads money, never moves it.** Money fields you declare leave the shop in minor units; no answer kind
carries money, and the answer writes nothing.

Limits: label 40 · menu 40 · confirm 140 · 10 inputs, each label 60 · up to 3 conditions · 40 fields in 5
tables sent, 500 rows per table · 100 records per list press · answer 64 KB · 3 to 10 seconds. Every
press writes one *Retail Extension Log* row (who, which records, the outcome, how long it took); a Desk
press names no store, so every reader of the log sees its rows.

## 8. Worked examples

**Assign pick route.** Declared on Sales Order, `form`, submitted only, for Stock Users, one Select input
*Pick wave* (Morning, Afternoon), sending `name, customer, delivery_date, items(item_code, qty)`. Your
service plans the route, writes it to its own system and answers
`{"message": {"title": "Route assigned", "body": "14 lines across 3 aisles.", "level": "success"},
"refresh": true}`.

**Recheck unit barcodes for many records.** Declared on Batch, `list`. The user ticks 30 batches; one
press sends all 30 (refused whole if one fails its checks). Your service answers
`{"open_page": {"url": "https://partner.example/console/batches?run=8812"}}`, and Desk opens your page —
placed on Desk as a partner page whose address is `https://partner.example/console/`.

## 9. Telling an AI assistant

> Build the HTTPS service behind an iVendNext POS Desk action, version 1. The contract is
> `desk_action.v1.schema.json`: `$defs/request` in (header `X-iVendNext-Point: desk_action/1`), `$defs/answer`
> out; `$defs/declaration` is the Retail Desk Action record. Verify the signature (base64 HMAC-SHA256 of
> `<timestamp>.<raw body>`), answer within 3 seconds, treat money as minor units and quantities as
> thousandths, make the work idempotent on `context.idempotency_key`, write through your own API calls,
> and answer a message plus at most one of `open_record`, `open_page` or `refresh`.
