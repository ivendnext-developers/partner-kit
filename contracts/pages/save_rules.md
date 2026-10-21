<!-- Source: ivendnext/iVendNext_PWA docs/extending/save_rules.md @ 7d47d331a203, copied unchanged except the links, the framework's own calls (named by what they do), a customer's name and a reference to our board: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Save rules

**Contract:** [`save_rules.v1.schema.json`](../extension_contracts/save_rules.v1.schema.json)
· samples: [`samples/save_rules/`](../extension_contracts/samples/save_rules/)
· code: `business_logic/save_rules.py` (`validate_rule` and its `_validate_*` checks; `enforce` at
every save, submit and cancel).

## 1. What it is and when it fires

A shop's own rule on a field, declared as data with no code: a code's shape, a length, a value worked out
from others, no value twice in a table's rows, a limit only some roles may pass, a field required when
others hold a value, fields locked from a workflow state on, a value never repeated across records,
only named roles submitting or cancelling, and no more than so many records a day per store (or any other
field). A **Retail Save Rule** record names the record type (and the
table, for a rule on rows), one of ten kinds, and whether a broken rule **refuses** the save or **flags**
it to the *Sales to review* report.

It fires at **every save** of that record type — a Desk form, an import and an API write alike — and
when a row of a ruled table is saved on its own (a row deleted on its own is checked by a lock only). With no enabled rule on a record type the
check returns after one cached read and no query.

A `role_for_action` rule fires at the **submit** or the **cancel** it names — on every door: the Desk's
Submit and Cancel, an import that submits, the API's submit (`ivendnext_mpos.api.v1.submit`), a cancel through the API, and the REST API — and
nowhere else; a draft's save never asks it. Every other kind fires at the save, as above, and not again
at the submit or the cancel, so a flag rule writes one row for one submit — ⚠ except where a partner's
document check fills fields at the submit ([doccheck](doccheck.md)): every kind but `role_for_action` then
runs once more over the filled record, so a flag rule can write a second row. A `role_for_action` rule
judged the record as it was before the fill, so a fill that moves the record into its conditions is not
held.

⚠ What "every save" leaves out: a save the framework runs without `validate` (code that sets
`flags.ignore_validate`, a `db.set_value` / `db_set`), and installs, migrations, patches and fixtures.

## 2. Version

Version 1: the ten kinds below (`unique_across` and `role_for_action` added 2026-10-16, `count_per_day` and
the `in` condition later the same day). A new kind is added in version 1; an existing kind never changes what it
checks — with one dated exception: on 2026-10-17 (lane `prules3`) `derived` gained `sum_rows` and `count_rows`,
began running at the submit, and its money check tightened (§7), so a rule saved before may stop writing (it is
listed at the upgrade's migrate). Later on 2026-10-17 (lane `prules4`) `percent` began clearing its figure when
a source is empty or its base is 0 (it kept the last one), and three kinds gained optional keys, each changing nothing for a rule
that does not use it: `derived` the formula `days_between`, `threshold`
`judge_on_change` and a limit read from a settings record (`value_from_type` …), and `required_when` on a
table's rows a condition on the record's header (`parent.⟨field⟩`).

## 3. What you declare

A Retail Save Rule is the partner's whole input (a System Manager saves it in Desk, through the REST API
or in an import). Nothing is sent to a partner service and nothing is answered.

| Kind | Needs | What it checks |
|---|---|---|
| `pattern` | `field`, and **either** `pattern_class` (`alphanumeric` · `upper_alphanumeric` · `digits` · `letters` · `phone_e164`) **or** a written `pattern` | the value's shape; an empty value passes |
| `length` | `field`, `min_length` and/or `max_length` | the value's length; an empty value passes |
| `derived` | `field` (Int, Float or Percent), `formula` (`scale` · `days_until` · `percent` · `sum_rows` · `count_rows` · `days_between`), `source`, and `source_b` for `percent` and `days_between`; `factor`, `offset`, `decimals` (0 to 6). `sum_rows`: `source_table` (a table of the record) and `source` (a number field of its rows). `count_rows`: `source_table` and 0 to 3 `conditions` on the row. `days_between`: two Date or Datetime fields; `source` may be `creation` (when the record was made) on a rule without a table | writes the value: `source × factor + offset`, the days from today to a date, `source ÷ source_b × 100`, or the days from `source` to `source_b` — each in the same row it reads; `percent` and `days_between` clear their figure when either source is empty (and `percent` on a zero base); `sum_rows` writes the sum of `source` over the table's rows and `count_rows` the number of its rows where every condition holds (all rows when none), both on the record's own header (no `child_table`) |
| `unique_in_rows` | `child_table`, `field` | no value twice in that table's rows |
| `threshold` | `field` (a number), `operator` (`=` `!=` `>` `>=` `<` `<=`), `value`; `bypass_roles` one per line; optional `judge_on_change` (1); optional `value_from_type`, `value_from_name`, `value_field` and `roles_field` | the number against the limit, unless the saver holds a bypass role. With `judge_on_change`, only when the record is new, is submitted, or the value changed (on a table, a new row or a changed row): an edit that leaves the value as it was saves. With `value_from_type`, the limit is the settings record's `value_field` and the one role that may pass it its `roles_field` (§7) |
| `required_when` | `field`, 1 to 3 `conditions` (`field`, an operator or `is set` / `is not set`, `value`); on a rule with `child_table`, a condition's field may be `parent.⟨field⟩` | the field is filled when every condition holds; `parent.⟨field⟩` reads the record's own header, so a row rule can ask *"is this a transfer?"* |
| `locked_in_state` | `states`, `locked_fields` (one per line), an active workflow on the record type | the fields cannot change once the record was saved in one of the states |
| `unique_across` | `field`; `scope_fields` (optional, one per line, at most 3, for example `company`) | the value is on no other active record of the type with the same scope values — a cancelled record holds none; an empty value passes. The database compares as it indexes: case and trailing spaces are ignored |
| `role_for_action` | `action` (`submit` · `cancel`), `bypass_roles` (the roles that may, one per line); 0 to 3 `conditions` | that action, when every condition holds, by a person holding one of the roles only; no condition = every record of the type |
| `count_per_day` | `scope_field` (one field, for example `store`), `day_field` (a Date or Datetime field), `cap` (1 to 10,000); 0 to 3 `conditions`, which may use `in` | no more than `cap` records a day per value of the scope field. A record counts when a save makes it **newly** meet every condition (it did not before the save, or it is new, and it does after); one that keeps meeting them is not judged again, and one that leaves them and meets them again counts again. The day is the day field's calendar day in the site's time zone (today when it is empty). At the cap the save is refused; below it the count goes up by one in the same save, so a save that fails takes its count back |

A condition's operator is `=`, `!=`, `>`, `>=`, `<`, `<=`, `is set` or `is not set`; on a `count_per_day`
rule also `in`: the value is one of up to 10 values written in `value`, separated by commas.

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
- required_when: *"⟨Field⟩ is required."* (on rows: *"Row ⟨n⟩: ⟨Field⟩ is required."*)
- locked_in_state: *"⟨Field⟩ can't change once the ⟨record type⟩ is ⟨state⟩."*
- unique_across: *"⟨Field⟩ ⟨value⟩ is already on another ⟨record type⟩."*
- role_for_action: *"Only ⟨role⟩, ⟨role⟩ can ⟨submit · cancel⟩ this ⟨record type⟩."*
- count_per_day: *"⟨scope value⟩ has had its ⟨cap⟩ for today."* (give the rule a `message` that says what
  to do instead — the worked example below does)
- a rule that cannot be checked: *"A house rule could not be checked. Ask an administrator."* (refuses the
  save; flags where a refusal is never allowed) — ⚠ a `derived` rule never refuses: one that cannot be worked
  out flags and the save goes on (since 2026-10-17, §7)

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
  cannot write ⟨field⟩: a money field, or one a total is computed from."* · *"⟨field⟩ is a field an app added,
  not the shop: a derived value cannot write it."* · *"A derived value writes a field named custom_… or with
  your package's prefix: other names are ones the system may read."* · *"Choose the formula."* · *"A
  derived value cannot be its own source."* · *"Decimals must be 0 to 6."* · *"Rule ⟨name⟩ already writes
  ⟨field⟩."*
- `sum_rows` and `count_rows`: *"A total of rows writes a field of the record itself, not of a table."* ·
  *"⟨record type⟩ has no table named ⟨table⟩."* · *"Sum: ⟨field⟩ must be a number field of the table's
  rows."* · *"Condition: ⟨table⟩'s rows have no field named ⟨field⟩."* · *"Give at most 3 conditions."* ·
  *"A total of rows can only write a field the shop added."* · *"Sum: write a Float or Percent field."*
- `days_between`: *"Days between can only write a field the shop added."* · *"creation can be the first source of
  days_between only, on a rule without a table."* (also for `scale` and `days_until`) · *"Second source: choose a
  field."* · *"Second source: ⟨field⟩ must be a field of type Date, Datetime."*
- A package's `prefix` (the manifest checker): *"a prefix cannot start with ⟨word⟩: the system reads fields
  whose names start that way"* for a first word `IS`, `IGNORE`, `FOR`, `REDEEM`, `HAS`, `UPDATE`, `SKIP`,
  `ALLOW`, `APPLY`, `SET`, `DONT`, `BASE`, `INCLUDE`, `NO`, `DO`, `POST`, `REMOVE`, `PRICING`, `PRICE`,
  `FREE`, `RECALLED` or `NOT`.
- threshold: *"Choose how the value compares."* · *"The limit must be a number."* · *"No role named
  ⟨role⟩."*
- a limit from a settings record: *"A limit from a settings record names its record type, record and field."* ·
  *"⟨record type⟩ holds no record to read a limit from."* (a table or a virtual record type) · *"⟨record type⟩ is a
  single record: its name is ⟨record type⟩."* · *"A limit is read from a record type your package installed, or
  from Stock Settings, Selling Settings, Buying Settings."* · *"Limit from: ⟨field⟩ must be a field of type Int,
  Float, Percent."* · *"⟨field⟩: a role is read from a text field or a link to Role."*
- required_when: *"Give 1 to 3 conditions."* · *"Choose how the condition compares."* · *"A condition with
  ⟨operator⟩ needs a number."* · *"parent.⟨field⟩ reads the record's header: it is for a rule on a table's
  rows."* · *"Condition: ⟨record type⟩ has no field named ⟨field⟩."* · *"parent.⟨field⟩ holds no value to
  compare."* (a table, a layout break or a virtual field)
- unique_across, role_for_action and count_per_day: *"A ⟨kind⟩ rule checks the record itself, not a
  table."*
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
- count_per_day: *"⟨field⟩ holds no value to count by."* · *"At most per day must be 1 to 10,000."* ·
  *"Give at most 3 conditions."* · *"An in condition takes 1 to 10 values, separated by commas."* ·
  *"⟨field⟩ is a number: list numbers in its in condition."* · *"⟨record type⟩ cannot take a count_per_day
  rule: every till would wait on it."* (POS Invoice, POS Closing Entry, POS Invoice Merge Log) · on any
  other kind: *"The in operator is offered on count_per_day rules only."*
- locked_in_state: *"Name at least one state and one field."* · *"No active workflow on ⟨record type⟩: a
  lock follows its states."* · *"The workflow ⟨workflow⟩ has no state ⟨state⟩."*

## 5. Consent, and the down answer

Nothing leaves the shop, so no consent is recorded; only a System Manager opens the record. There is no
service to be down.

**Who may tune a limit.** A threshold with `value_from_type` reads its limit (and one role that may pass it)
from a settings record. Whoever the shop lets write that record tunes the limit — a store's quality lead, say —
without opening the rule, which stays with a System Manager: the delegate edits a record of values, never the
rule's kind, mode, operator or roles.

## 6. Offline

⛔ **Never refused, only flagged:** a write inside an offline drain (the customer paid hours ago) writes a
flagged *drained* row the *Sales to review* report lists, and the sale goes through. So are a sale the
till booked (a rule on POS Invoice, POS Closing Entry or POS Invoice Merge Log may only flag), every record
a sale's or the day close's save writes, the receipt's contact capture after a paid sale, and an *Action*
approval request (§7: written after its action ran). To stop a
sale **before** payment, that is a check at the till, not a save rule.

⚠ **Approvals given offline are not counted** by a `count_per_day` rule: a discount a manager approves with
their badge at the till, or at the offline sync sheet, writes no approval request (the customer has paid by
then), so nothing reaches the count. The cap covers the approvals managers give online, in the approvals
inbox or in person on the cashier's device.

A `role_for_action` rule is also only flagged on a submit or cancel the till's own work makes: inside a
sale's or the day close's save, inside the till's elevation for its operator, a layaway's forfeit entry, and
the till's quote edit and quote cancel.

⚠ That reaches further in a batch job: once a job (an import, a connector, an offline sync) has
inserted a sale, every later save in that same job flags too.

## 7. Money and limits

A derived value **never writes money**: not a field whose name holds a money or total word (`amount`,
`rate`, `total`, `price`, `discount`, `tax`, `qty`, …), and on a record that carries a total or an
Accounts master only a field the shop added itself. **A field the shop added** is a Custom Field that no app
made: a field an app ships by fixture or by code carries its module, and is never the shop's (⚠ bound: a field
an app ships in its own `custom/*.json` file carries no module and reads as the shop's — none is numeric on a
money record today). A field the
shop added is written only when it is **named `custom_…` or with the prefix of an installed package that
installed that very field**, and no field the system made carries the same name: the system reads fields
by name, on the same record (`is_return` lifts the maximum discount) and in the next document made from it
(a same-named field is copied across), and the line pricer reads names that are no field anywhere
(`ignore_party`). A `sum_rows` or `count_rows` rule writes a field the shop added on **any** record type, a
Float or Percent field for a sum: a figure on screen, shown as a number without a currency, never money. A
package whose prefix starts with a reserved word vouches for no field, whenever it was installed.
The same test holds for a partner's document check that fills fields.

A derived rule **runs at the submit too**: a record inserted already submitted (a till's sale, an import,
an API insert) and a draft edited and submitted in one action carry the figure of the rows they were
submitted with. A submitted record is never re-derived after that. A derived rule that **cannot be worked
out** (its field, table or source removed since it was saved) **flags** the record on *Sales to review* and
the save goes on: a figure guards nothing (a total of rows, or any rule on a money record, whose target field
was removed reads as a refused field: it writes nothing and logs once, with no flag). A rule saved before this check tightened, whose field it now
refuses, writes nothing — on the record's save and on a row saved on its own alike — (the figure freezes) and
logs one error until any rule is saved again (or the cache is cleared); such a rule
can still be switched off, and the upgrade's migrate lists them per site (`prules3 offender: …`).

Limits: message 140 · written pattern 100 characters, at most 2 repeats or choices, and it reads at most
140 characters of a value · 1 to 3 conditions (0 to 3 for `role_for_action`) · decimals 0 to 6 · 3 scope
fields · a `unique_across` field on a table above 10,000 records must be indexed · a `count_per_day` cap of
1 to 10,000, an `in` condition of 1 to 10 values, and a scope value counted under its first 140 characters.

⚠ Bounds, stated (`sum_rows` / `count_rows`): a row saved on its own does not re-total the header — the
record's next save does; the two run after every other derived rule of the record type whatever their
`sequence`, so a derived rule whose `source` is a header figure a total writes reads the previous save's
value (a check — a limit, a required field — that the shop sequences after a total still runs after it and
reads the total — and, from the first total on, it runs after every derived rule of the record type, whatever
their sequences); a package's own record type's fields are not Custom Fields, so they are never a total's target; a
derived rule on POS Invoice now runs at the till's submit (and the offline drain's), so its figure is on
the sale. The residual — v1 rules may still write a field the shop did not add on a record that is not a
money record (an item's `weight_per_unit`, our apps' own system-made fields such as the engine's
`Item.custom_return_days`) — is a recorded decision; code of the shop's or
a partner's own that reads its own field, and a `fetch_from` the shop configures, are theirs.

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

`count_per_day` keeps its count in **Retail Save Rule Count**, one row per rule, scope value and day. A save
that newly meets the rule locks the rule itself, then that row, until the save commits: two saves at the same
moment queue, and the second sees the first's count — exactly one passes at the cap. The queue is per rule,
across every scope value, so on a submittable record type a partner's document check that answers slowly
holds the rule's other saves behind it. Nobody edits a count (a System Manager may read them); deleting the
rule deletes its counts. Only the cap and the rule's switch are read at each save; its other settings come
from the rules the server holds in memory, refreshed when a rule is saved. ⚠ Bounds, stated: a NEW rule saved
part-way through a day starts at 0 (earlier records that day are not counted), while an edited or re-enabled
rule keeps the day's count (a changed scope field counts its values afresh, unless they are the same values); a write without `validate` is not counted; the cap is per site time zone, so a
store open past midnight starts a new count at midnight; a scope value compares as the database indexes it
(case and accents ignored), and records whose scope field is empty all share one count; a record met in a
`flag` rule past the cap is flagged and not added; a cap lowered during the day leaves the count above it
until midnight; a partner's document check that fills the scope or day field counts the record under
the values it had before the fill. `in` compares numbers on a number or tick-box field (a stored 25.0 is the
listed 25) and text everywhere else. A count rule never sits on a sale or a day close (refused when the rule
is saved), and should never sit on a record a sale or the day close writes — a payment, loyalty points, a coupon's count, a
layaway's order and deposit, a delivery note, the consolidated invoice: its one lock per rule is held to each
sale's commit and every till would wait.

**Count discount approvals, as the worked example does.** An *Action* request is the record an in-person
approval leaves, written in the action's own save — for a void, after its card payments were released — so
**no house rule refuses an Action request, whatever its kind: it is only flagged**, because a refusal would
fail an action whose money had moved. (A count rule still counts it below the cap; a database deadlock while
counting it still fails the action — a stated bound, the lock order makes it unlikely.) A cap on *Transaction
Approval* requests refuses the approval before the transaction, which is safe.

**A limit from a settings record** (`value_from_type`, `value_from_name`, `value_field`, `roles_field`). The
record type is one an installed package installed (a package's settings are one row of its own record type)
or one of the singles Stock Settings, Selling Settings and Buying Settings, where the shop adds its own number
field; a single's name is its record type. `value_field` is an Int, Float or Percent field; `roles_field` a text
field or a link to Role. Read at each judged save from the framework's record cache, which the framework clears
at every save of that record, so a change is seen at the next save. ⚠ Bounds, stated: a number field cannot be
empty (it stores 0), so a 0 there means *use the rule's own `value`* — never a limit of 0; a missing record is
the same; the rule's `value` therefore stays required. An empty role field means the rule's `bypass_roles`; a
role every user holds (All, Guest, Desk User, Administrator) is ignored and logged once. A missing record — not
made yet, renamed (`value_from_name` is the name as written), or its record type removed with its package —
reads as no record, so the rule's own value and roles hold, logged once. `db.set_value` clears the record's cache too;
only a raw SQL write to it is seen when the cache next clears. A package update changes its
record type's fields, never its rows, so the shop's value survives; the update brings a rule it changed back
switched off, until a System Manager switches it on; a version that drops `value_from_*` or `judge_on_change`
from a rule clears them on the installed rule. Only the record's SHAPE is checked when the rule is saved
(the record type, the fields, a single's name), never the record itself, so a package can ship the rule before
the shop has made the row.

**Judged on change** (`judge_on_change`). The value before the save is the record's own as it was stored, the
value after is the one the save writes — including one a derived rule writes in the same save: a threshold
judged on change runs after every derived rule of its record type, whatever its `sequence`. A submit is judged
again; on a table, rows match by row name, and a new row is judged. ⚠ Bound, stated: a record whose value
broke the limit before the rule existed is judged at the first save that changes the value, not before — list
such records before switching the rule on.

**Two dates** (`days_between`). The days from `source` to `source_b` (negative when `source_b` is earlier);
the figure is **cleared** when either is empty (an empty date would otherwise read as today, and a value kept from
before — or typed by the saver — would be judged). `percent` clears the same way when either source is empty or its
base is 0 (since 2026-10-17; it used to keep its last figure). A cleared figure is stored as 0, and on a field the
shop made mandatory it is written 0 (never refused as missing — a booked sale included) — ⚠ and a limit judges
that 0 (it is not empty): never make a figure a limit judges mandatory (on Batch it refuses every receipt that makes
a batch). ⚠ Dated exception: `scale` and `days_until` read one source and still keep their last figure when it is
empty — unchanged in this release; never put a limit on a `scale` or `days_until` figure a saver can type into, or on
a figure derived from one. ⚠ **Sequence a derived rule — and a limit judged at every save — after the rules that
write its sources**: rules run in `sequence` order (only a limit judged on change is moved after them), so a
`percent` placed before the `days_between` it reads would read the value the saver typed. ⚠ Bound, stated: a save that empties a date passes a limit on the figure (an empty value passes) and leaves
the figure empty — so a batch with no shelf % is one to look at, and the kit's list of batches with an empty shelf %
finds it. `creation` — when the
record was made — may be the first source on a rule without a table; the framework stamps it at the insert and
refuses a changed one on every later save. ⚠ Bounds, stated: a row's own `creation` is kept as sent,
so a rule on a table cannot read it; an import of old records takes the import day as their `creation`
(switch the rules off for a history load); the target is a field the shop added, on any record type.

**A row rule that reads its record** (`parent.⟨field⟩`). The header field is read from the record being saved;
for a row saved on its own, from the record as stored (one read, only when a condition names `parent.`). Its
type is the record's, so a number or tick box compares as a number. A count of rows reads its rows only.

**Goods receipt and a batch's own rules, stated honestly.** When a receipt makes a new batch, the core inserts
it with only the item and the receipt, and fills its dates after the rules ran: at that insert a day count is
empty, a percentage is not written and an empty value passes a limit, so the receipt submits. The same holds
for a batch split off another (`split_batch`, inserted with no dates); a bulk batch insert (`make_batch_nos`)
runs no rule at all. The batch's
first later save writes its figures — a change, so a limit judged on change judges it then. A batch saved
with its dates (Desk, an import, the API) is judged at once. ⛔ Never make a batch's dates required by a save
rule: it refuses every receipt that makes a batch.

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

**No more than ten discount approvals a store a day.** `{"record_type": "Retail Override Request",
"kind": "count_per_day", "scope_field": "store", "day_field": "resolved_on", "cap": 10, "message": "This
store has given its 10 discount approvals today. Deny this one; the cashier can sell at the normal
price.", "conditions": [{"field": "request_type", "operator": "in", "value": "Markdown, Discount Stack,
Open Price, Sale Discount"}, {"field": "status", "operator": "in", "value": "Approved, Consumed"}]}` — the
eleventh approval a store's managers give that day is refused when the manager presses **Approve**, in the
approvals inbox or in person on the cashier's device, with that message; the request stays *Pending*, the
manager denies it, and the cashier sells at the normal price. What counts is an approval **given**: one
given and never used still counts; one that ran out and was given again counts twice (a manager gave two).
A sale using an approval never counts it again. Each approval request carries its `store` (the warehouse of
the register's POS Profile), set when it is made and never changed, so a store with several registers has
one count. Approvals given offline are not counted (§6).

**A minimum shelf life on a batch.** Three Batch fields the shop (or a package) adds: *days
left* (Int), *shelf days* (Int), *shelf %* (Percent) — every save rewrites them, and a split batch is a new
record, so none needs No Copy; and a settings record with a limit (Percent) and a role (link to Role). Five Batch rules, in this order: `days_between`
`creation` → `expiry_date` into days left (sequence 10); `days_between` `manufacturing_date` → `expiry_date`
into shelf days (20); `percent` of days left over shelf days into shelf % (30, 2 decimals); a threshold *shelf
days > 0* judged at every save (40 — an expiry before manufacture would otherwise read as more than 100 %, and an
expiry on the manufacturing day as an empty %; shelf days is recomputed at every save, so judging it every time
refuses only a real 0 or less — ⚠ switch it off together with the shelf-days rule: while that rule is off (or back off
after a package update) the limit judges the stored 0 of every batch with no expiry, and a batch whose expiry is on
or before its manufacturing date is refused at every save until its dates are fixed); a
threshold *shelf % ≥ 60* judged on change, its limit and role from the settings record (50). A batch made on 2
April, manufactured 1 January and expiring next 1 January has 274 of 365 days left: 75.07 %. At 40 % a Stock
User's save is refused (*"Shelf % must be at least 60."*, or the settings value), a person holding the
settings role saves it, a later edit of its description saves, and a later edit of its expiry is judged again.
And on Stock Entry: `{"child_table": "items", "kind": "required_when", "field": "material_request",
"conditions": [{"field": "parent.purpose", "operator": "=", "value": "Material Transfer"}]}` — a transfer
whose second row names no request is refused with *"Row 2: Material Request is required."*; an issue or a
receipt saves. A batch a receipt makes is judged at its first later save (§7): list batches with no shelf %
(Desk's Batch list, filtered on an empty shelf %) before switching the rules on.

## 9. Telling an AI assistant

> Write a Retail Save Rule for iVendNext POS, version 1, as JSON matching
> `save_rules.v1.schema.json#/$defs/declaration`; the samples under `samples/save_rules/` show accepted
> and refused records. Pick the one kind that does the job, give exactly the fields that kind needs, keep a
> written pattern anchored with at most two repeats or choices, never derive into a money or quantity
> field, and use `mode: "flag"` for anything on a booked sale. Name only fields that exist on the record
> type; a sum or count of rows, days between two dates (and any derived value on a record that carries a
> total) writes only a field the shop added, named `custom_…` or with your package's own prefix. A limit
> that should be judged only when its value changes takes `judge_on_change: 1`; a limit someone else tunes
> is read from a settings record (`value_from_type` …) and keeps its own `value` as the fallback; a row
> rule that depends on the document's kind names `parent.⟨field⟩` in its condition.
