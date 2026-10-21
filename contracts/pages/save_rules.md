<!-- Source: ivendnext/iVendNext_PWA docs/extending/save_rules.md @ 4c3f11b550f1, copied unchanged except the links and one framework call named by what it does: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Save rules

**Contract:** [`save_rules.v1.schema.json`](../extension_contracts/save_rules.v1.schema.json)
· samples: [`samples/save_rules/`](../extension_contracts/samples/save_rules/)
· code: `business_logic/save_rules.py` (`validate_rule` and its `_validate_*` checks; `enforce` at
every save, submit and cancel).

## 1. What it is and when it fires

A shop's own rule on a field, declared as data with no code: a code's shape, a length, a value worked out
from others, no value twice in a table's rows, a limit only some roles may pass, a field required when
others hold a value, fields locked from a workflow state on, a value never repeated across records, and
only named roles submitting or cancelling. A **Retail Save Rule** record names the record type (and the
table, for a rule on rows), one of nine kinds, and whether a broken rule **refuses** the save or **flags**
it to the *Sales to review* report.

It fires at **every save** of that record type — a Desk form, an import and an API write alike — and
when a row of a ruled table is saved on its own (a row deleted on its own is checked by a lock only). With no enabled rule on a record type the
check returns after one cached read and no query.

A `role_for_action` rule fires at the **submit** or the **cancel** it names — on every door: the Desk's
Submit and Cancel, an import that submits, the API's submit (`ivendnext_mpos.api.v1.submit`) and cancel and the REST API — and
nowhere else; a draft's save never asks it. Every other kind fires at the save, as above, and not again
at the submit or the cancel, so a flag rule writes one row for one submit — ⚠ except where a partner's
document check fills fields at the submit ([doccheck](doccheck.md)): every kind but `role_for_action` then
runs once more over the filled record, so a flag rule can write a second row. A `role_for_action` rule
judged the record as it was before the fill, so a fill that moves the record into its conditions is not
held.

⚠ What "every save" leaves out: a save the framework runs without `validate` (code that sets
`flags.ignore_validate`, a `db.set_value` / `db_set`), and installs, migrations, patches and fixtures.

## 2. Version

Version 1: the nine kinds below (`unique_across` and `role_for_action` added 2026-10-16). A new kind is added in version 1; an existing kind never changes what it
checks.

## 3. What you declare

A Retail Save Rule is the partner's whole input (a System Manager saves it in Desk, through the REST API
or in an import). Nothing is sent to a partner service and nothing is answered.

| Kind | Needs | What it checks |
|---|---|---|
| `pattern` | `field`, and **either** `pattern_class` (`alphanumeric` · `upper_alphanumeric` · `digits` · `letters` · `phone_e164`) **or** a written `pattern` | the value's shape; an empty value passes |
| `length` | `field`, `min_length` and/or `max_length` | the value's length; an empty value passes |
| `derived` | `field` (Int, Float or Percent), `formula` (`scale` · `days_until` · `percent`), `source`, and `source_b` for `percent`; `factor`, `offset`, `decimals` (0 to 6) | writes the value: `source × factor + offset`, the days from today to a date, or `source ÷ source_b × 100` |
| `unique_in_rows` | `child_table`, `field` | no value twice in that table's rows |
| `threshold` | `field` (a number), `operator` (`=` `!=` `>` `>=` `<` `<=`), `value`; `bypass_roles` one per line | the number against the limit, unless the saver holds a bypass role |
| `required_when` | `field`, 1 to 3 `conditions` (`field`, an operator or `is set` / `is not set`, `value`) | the field is filled when every condition holds |
| `locked_in_state` | `states`, `locked_fields` (one per line), an active workflow on the record type | the fields cannot change once the record was saved in one of the states |
| `unique_across` | `field`; `scope_fields` (optional, one per line, at most 3, for example `company`) | the value is on no other active record of the type with the same scope values — a cancelled record holds none; an empty value passes. The database compares as it indexes: case and trailing spaces are ignored |
| `role_for_action` | `action` (`submit` · `cancel`), `bypass_roles` (the roles that may, one per line); 0 to 3 `conditions` | that action, when every condition holds, by a person holding one of the roles only; no condition = every record of the type |

Every rule also takes `message` (at most 140 characters; shown instead of the kind's own sentence),
`mode` (`refuse`, or `flag`), `sequence` and `enabled`.

## 4. Every refusal, in the product's words

**When a rule is broken** (the kind's own sentence, unless the rule has a `message`; a pattern, length,
threshold or required rule on rows says *"Row ⟨n⟩: …"*):

- pattern: *"⟨Field⟩: use letters and digits only."* · *"⟨Field⟩: use capital letters and digits only."* ·
  *"⟨Field⟩: use digits only."* · *"⟨Field⟩: use letters only."* · *"⟨Field⟩: use an international number,
  like +971501234567."* · a written pattern: *"⟨Field⟩ is not in the expected format."*
- length: *"⟨Field⟩ must be ⟨min⟩ to ⟨max⟩ characters."* · *"… at least ⟨min⟩ characters."* · *"… at most
  ⟨max⟩ characters."*
- unique_in_rows: *"⟨value⟩ is on two rows."*
- threshold: *"⟨Field⟩ must be ⟨exactly · anything but · more than · at least · less than · at most⟩
  ⟨value⟩."*
- required_when: *"⟨Field⟩ is required."*
- locked_in_state: *"⟨Field⟩ can't change once the ⟨record type⟩ is ⟨state⟩."*
- unique_across: *"⟨Field⟩ ⟨value⟩ is already on another ⟨record type⟩."*
- role_for_action: *"Only ⟨role⟩, ⟨role⟩ can ⟨submit · cancel⟩ this ⟨record type⟩."*
- a rule that cannot be checked: *"A house rule could not be checked. Ask an administrator."* (refuses the
  save; flags where a refusal is never allowed)

**When the rule record is saved:**

- *"The message can be at most 140 characters."* · *"Choose the rule's kind."* · *"Choose the record type
  the rule checks."* · *"⟨record type⟩ cannot take a house rule."* (a table, a single, a virtual record
  type, a ledger, or the partner records themselves)
- *"A rule on ⟨record type⟩ can only flag: a booked sale or a day close is never refused."*
- *"⟨record type⟩ has no table named ⟨table⟩."* · *"Choose the table whose rows must not repeat a
  value."* · *"A lock names fields of the record itself; a table field locks its rows."*
- *"⟨What⟩: choose a field."* · *"⟨What⟩: ⟨record type⟩ has no field named ⟨field⟩."* · *"⟨What⟩: ⟨field⟩
  must be a field of type ⟨types⟩."*
- pattern: *"Choose a named shape or write a pattern, not both."* · *"Unknown shape ⟨shape⟩."* · *"A
  pattern can be at most 100 characters."* · *"A pattern must start with ^ and end with $."* · *"The
  pattern cannot be read."* · *"A pattern cannot use back-references or look-arounds."* · *"A pattern
  cannot repeat inside a repeat."* · *"A pattern cannot choose between options inside a repeat."* · *"A
  pattern can have at most 2 repeats or choices."*
- length: *"Give at least one of the two lengths, the smaller first."*
- derived: *"On ⟨record type⟩, a derived value can only write a field the shop added."* · *"A derived value
  cannot write ⟨field⟩: a money field, or one a total is computed from."* · *"Choose the formula."* · *"A
  derived value cannot be its own source."* · *"Decimals must be 0 to 6."* · *"Rule ⟨name⟩ already writes
  ⟨field⟩."*
- threshold: *"Choose how the value compares."* · *"The limit must be a number."* · *"No role named
  ⟨role⟩."*
- required_when: *"Give 1 to 3 conditions."* · *"Choose how the condition compares."* · *"A condition with
  ⟨operator⟩ needs a number."*
- unique_across and role_for_action: *"A ⟨kind⟩ rule checks the record itself, not a table."*
- unique_across: *"⟨field⟩ holds no value to compare."* · *"Name at most 3 scope fields."* · *"⟨record type⟩
  holds about ⟨n⟩ records, so ⟨field⟩ needs an index first: tick Index on it in Customize Form."* (above
  10,000 records, the database's own estimate read when the rule is saved, a field with no index is
  refused: a lookup without one reads the whole table at every save). A table, a layout break, a virtual
  field, or a tick box as the field itself, holds no value to compare.
- role_for_action: *"⟨record type⟩ is the till's own record, or one the back office writes for a sale or a
  stock move: its submit and cancel are never held by role."* (POS Opening Entry, Serial and Batch Bundle,
  Repost Item Valuation, Stock Reservation Entry; POS Invoice, POS Closing Entry and POS Invoice Merge Log
  meet *"… can only flag"* first, and this sentence when the rule flags) ·
  *"⟨record type⟩ is never submitted, so no role can hold it."* · *"Choose the action: submit or cancel."* ·
  *"Name at least one role that may ⟨action⟩."* · *"No role named ⟨role⟩."* · *"Give at most 3 conditions."*
- locked_in_state: *"Name at least one state and one field."* · *"No active workflow on ⟨record type⟩: a
  lock follows its states."* · *"The workflow ⟨workflow⟩ has no state ⟨state⟩."*

## 5. Consent, and the down answer

Nothing leaves the shop, so no consent is recorded; only a System Manager opens the record. There is no
service to be down.

## 6. Offline

⛔ **Never refused, only flagged:** a write inside an offline drain (the customer paid hours ago) writes a
flagged *drained* row the *Sales to review* report lists, and the sale goes through. So are a sale the
till booked (a rule on POS Invoice, POS Closing Entry or POS Invoice Merge Log may only flag), every record
a sale's or the day close's save writes, and the receipt's contact capture after a paid sale. To stop a
sale **before** payment, that is a check at the till, not a save rule.

A `role_for_action` rule is also only flagged on a submit or cancel the till's own work makes: inside a
sale's or the day close's save, inside the till's elevation for its operator, a layaway's forfeit entry, and
the till's quote edit and quote cancel.

⚠ That reaches further in a batch job: once a job (an import, a connector, an offline sync) has
inserted a sale, every later save in that same job flags too.

## 7. Money and limits

A derived value **never writes money**: not a field whose name holds a money or total word (`amount`,
`rate`, `total`, `price`, `discount`, `tax`, `qty`, …), and on a record that carries a total or an
Accounts master only a field the shop added itself. A submitted record is never re-derived.

Limits: message 140 · written pattern 100 characters, at most 2 repeats or choices, and it reads at most
140 characters of a value · 1 to 3 conditions (0 to 3 for `role_for_action`) · decimals 0 to 6 · 3 scope
fields · a `unique_across` field on a table above 10,000 records must be indexed.

⚠ Bounds, stated: `unique_across` is a rule, not a database constraint — two saves at the same moment can
both pass; a table that grows past 10,000 records, or loses its index, after the rule was saved is not
checked again; the index must START with the field and hold nothing else (the framework's own column
lookup), so a wider index starting with it is not counted. It judges a value when a record is new or the
value or a scope field changes: duplicates already there when the rule was added never block an unrelated
edit. "Active" means not cancelled — a disabled customer, item or supplier still holds its value (add
`disabled` as a scope field to let it repeat there).
`role_for_action` reads the person's own roles (the framework's `get_roles`), so Administrator passes every
role. A till's own write is flagged, never refused: inside a sale's or the day close's save, the till's
elevation for its operator, a layaway's forfeit entry, and the till's quote edit and quote cancel (each
cancels or re-submits the quote's backing records).

**Not a kind — a next-business-date day open.** A `threshold` compares numbers only, so a rule cannot
refuse a POS Opening Entry dated after today by itself. Two rules come close: a field the shop adds to POS
Opening Entry (Int, say *days ahead*), a `derived` rule `days_until(posting_date)` into it, then a
`threshold` rule *days ahead ≤ 0*. That refuses a date after today; it knows nothing of business days.

## 8. Worked examples

**A UAE tax id.** `{"record_type": "Customer", "kind": "pattern", "field": "tax_id", "pattern":
"^[0-9]{15}$", "message": "The tax id is 15 digits."}` — a Desk save, an import or an API write of a
Customer whose tax id is not 15 digits is refused with *"The tax id is 15 digits."*; an empty tax id passes.
Add a `required_when` rule with the condition `customer_type = Company` to make it required for companies
only.

**No item twice on an order, flagged.** `{"record_type": "Sales Order", "child_table": "items", "kind":
"unique_in_rows", "field": "item_code", "mode": "flag"}` — the order saves, and *Sales to review* lists it
with *"⟨item⟩ is on two rows."* for the back office to look at.

**One customer per tax id, per customer group.** `{"record_type": "Customer", "kind": "unique_across",
"field": "tax_id", "scope_fields": "customer_group"}` — a second customer in the same group with that tax
id is refused with *"Tax ID ⟨value⟩ is already on another Customer."*; a cancelled record never holds one.

**Only the receiving store receives.** `{"record_type": "Stock Entry", "kind": "role_for_action", "action":
"submit", "bypass_roles": "Store X Receiver", "conditions": [{"field": "purpose", "operator": "=", "value":
"Material Transfer"}, {"field": "to_warehouse", "operator": "=", "value": "Store X - CO"}]}` — a transfer
into Store X is submitted only by a person holding *Store X Receiver*, from the Desk, an import or the API;
any other Stock Entry submits as before. A second rule with `"action": "cancel"` holds the cancel. ⚠ The
conditions read the record's own fields, never its rows: a row keeps the target store it names, and the
header store may be left empty. Add a `required_when` rule (`to_warehouse` required when `purpose =
Material Transfer`) so the header always names the store; a row that names a different store than the
header is still not held.

## 9. Telling an AI assistant

> Write a Retail Save Rule for iVendNext POS, version 1, as JSON matching
> `save_rules.v1.schema.json#/$defs/declaration`; the samples under `samples/save_rules/` show accepted
> and refused records. Pick the one kind that does the job, give exactly the fields that kind needs, keep a
> written pattern anchored with at most two repeats or choices, never derive into a money or quantity
> field, and use `mode: "flag"` for anything on a booked sale. Name only fields that exist on the record
> type.
