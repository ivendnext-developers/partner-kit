<!-- Source: ivendnext/iVendNext_PWA docs/extending/save_rules.md @ 8c955ffd9fcf, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Save rules

**Contract:** [`save_rules.v1.schema.json`](../extension_contracts/save_rules.v1.schema.json)
· samples: [`samples/save_rules/`](../extension_contracts/samples/save_rules/)
· code: `business_logic/save_rules.py` (`validate_rule` and its `_validate_*` checks; `enforce` at
every save).

## 1. What it is and when it fires

A shop's own rule on a field, declared as data with no code: a code's shape, a length, a value worked out
from others, no value twice in a table's rows, a limit only some roles may pass, a field required when
others hold a value, fields locked from a workflow state on. A **Retail Save Rule** record names the
record type (and the table, for a rule on rows), one of seven kinds, and whether a broken rule
**refuses** the save or **flags** it to the *Sales to review* report.

It fires at **every save** of that record type — a Desk form, an import and an API write alike — and
when a row of a ruled table is saved on its own (a row deleted on its own is checked by a lock only). With no enabled rule on a record type the
check returns after one cached read and no query.

⚠ What "every save" leaves out: a save the framework runs without `validate` (code that sets
`flags.ignore_validate`, a `db.set_value` / `db_set`), and installs, migrations, patches and fixtures.

## 2. Version

Version 1: the seven kinds below. A new kind is added in version 1; an existing kind never changes what it
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

⚠ That reaches further in a batch job: once a job (an import, a connector, an offline sync) has
inserted a sale, every later save in that same job flags too.

## 7. Money and limits

A derived value **never writes money**: not a field whose name holds a money or total word (`amount`,
`rate`, `total`, `price`, `discount`, `tax`, `qty`, …), and on a record that carries a total or an
Accounts master only a field the shop added itself. A submitted record is never re-derived.

Limits: message 140 · written pattern 100 characters, at most 2 repeats or choices, and it reads at most
140 characters of a value · 1 to 3 conditions · decimals 0 to 6.

## 8. Worked examples

**A UAE tax id.** `{"record_type": "Customer", "kind": "pattern", "field": "tax_id", "pattern":
"^[0-9]{15}$", "message": "The tax id is 15 digits."}` — a Desk save, an import or an API write of a
Customer whose tax id is not 15 digits is refused with *"The tax id is 15 digits."*; an empty tax id passes.
Add a `required_when` rule with the condition `customer_type = Company` to make it required for companies
only.

**No item twice on an order, flagged.** `{"record_type": "Sales Order", "child_table": "items", "kind":
"unique_in_rows", "field": "item_code", "mode": "flag"}` — the order saves, and *Sales to review* lists it
with *"⟨item⟩ is on two rows."* for the back office to look at.

## 9. Telling an AI assistant

> Write a Retail Save Rule for iVendNext POS, version 1, as JSON matching
> `save_rules.v1.schema.json#/$defs/declaration`; the samples under `samples/save_rules/` show accepted
> and refused records. Pick the one kind that does the job, give exactly the fields that kind needs, keep a
> written pattern anchored with at most two repeats or choices, never derive into a money or quantity
> field, and use `mode: "flag"` for anything on a booked sale. Name only fields that exist on the record
> type.
