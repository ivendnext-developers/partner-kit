<!-- Source: ivendnext/iVendNext_PWA docs/extending/open_check.md @ c39b1449937a, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Open check — a table's running order, paid once (`open_check/1`)

**Who this is for:** a partner building a front-of-house app (reservations, a waiting list) or a guest
ordering app (a QR menu, a kiosk) on iVendNext POS, and the AI assistant working with them.

**Status of this version:** the door and its records — open, add, change, move, merge, split, hand over,
close and read — the kitchen (send, a manager's void of a sent line, a manager's comp), and payment at a
till: a till's Checkout claims a check's lines and books them as an ordinary sale, the day's close lists
open checks and refuses while a payment is held, and the floor and Pay screens are on every till frame.
A kit never claims or pays (§2, §2b).

---

## 1. What it is

An **open check** is a table's (or a bar seat's, or a named tab's, or a pre-order's) running order. Any till
of the store adds to it all evening; at the end the table pays together or guest by guest, as an ordinary
sale. A check holds **what was ordered, never a price**: the place, the party size, the server, the service
mode and the lines (item, quantity, choices, a note, seat, course, whether it went to the kitchen). The shop
prices the lines when they are paid, with every promotion, tax and charge, exactly as for any sale.

The floor is set up in iVendNext Desk: **Floor Sections** (the terrace, the bar) and their **Floor Places**
(Table 12, Seat 3, Room 204). A check may sit at a place, or at none (a tab or a pre-order, named by its
label). A place may hold several checks. The register's **Table Service** switch (POS Profile, off by
default) turns the whole thing on.

## 2. The calls

Every verb is a call on the partner API: `/api/method/ivendnext_mpos.api.v1.<verb>`, `POST` (the two reads
take `GET` too). Each runs the shop's own function, under the rights of the user your app signs in as.

| Verb | Right it asks | What it does |
|---|---|---|
| `check_open(store, pos_profile, key, place?, label?, covers?, server?, service_mode?, suggested_customer?, source?, source_ref?)` | open a check | opens a check at `place`, or a tab or pre-order named `label` (one at least); returns the check, version 1 |
| `check_add_lines(check, lines, key)` | add to a check | appends lines; two callers adding at once both land |
| `check_change_line(check, line_id, version, …, weighed?)` · `check_remove_line(check, line_id, version, reason?)` | change own lines / change any line | an unsent line nobody is paying (`concession_note`, `seat` and `course` alone: a sent line too; `concession_note` a till only); `weighed` weighs a line again (alone, a sent line's first weighing too) |
| `check_move(check, place?, label?)` · `check_move_lines(check, into, line_ids)` · `check_merge(check, into)` · `check_split_line(check, line_id, qty, version)` | move, merge or split | — |
| `check_transfer_server(check, server)` | hand a check over | a shift's handover |
| `check_edit(check, version, covers?, label?, suggested_customer?, service_mode?)` | change any line | the service mode only until a line has gone to the kitchen |
| `check_close(check)` | close an empty check | a check with no open line |
| `check_mark_sent(check, key, line_ids?, counter_till?)` | send to the kitchen | *Send*: the unsent lines (or the named ones) go to their kitchens on the till's kitchen tickets; see §2a |
| `check_void_line(check, line_id, version, key?, approver_user?, passwd?, counter_till?, reason?)` | void a line the kitchen already has (the kitchen's manager right), or a manager signs in at the till | a whole sent line; a VOID ticket tells its kitchen to stop; one approval record either way |
| `check_comp_line(check, line_id, version, key?, approver_user?, passwd?, reason?)` | comp a line (the Manager preset holds it), or a manager signs in at the till | sent or not: the line comes off the check and is never on the sale; no ticket (the guest still gets the dish); one approval record either way |
| `check_get(check)` · `floor_status(store)` | see the checks | reads; never lock anything |
| `check_preview(check, line_ids?)` | see the checks | the shop's own price of the open lines (or the named ones) at your register, with no customer: `rows` and `total`. Computed when asked, never stored; the bill is priced again when it is paid |
| `check_claim` · `check_release` · `check_note_pending` · `check_clear_pending` · `check_break_claim` | pay a check / end another till's payment | a till's only: see §2b. ⛔ Your app is refused, whatever it is granted |
| `check_print(check, version?)` | print a table's check | a till's only: the printed check — see §2c. ⛔ Your app is refused, whatever it is granted |

A move of lines takes each named line as it is at that moment (no version: a line split meanwhile moves only its own part).
Moved lines keep their `seat`, unless the receiving check already has a guest with that number; a merge seats
the whole party that joins after the one there. Either way a `seat` that is a whole number is raised by the
larger of the receiving check's party size and its highest numbered seat, so its *1* is never the other
party's *1*; a seat that is not a number is kept as written.

`lines` is a list of `{item_code, qty?, uom?, weighed?, options?, note?, seat?, course?}` (`seat`: whose dish it is, `"2"`,
shown on the till as *Guest 2*; `course`: when it is served, in the shop's word, e.g. *Mains*, compared as
written, so *main* and *Mains* are two courses; each up to 140 characters, and an empty value clears it); `options` is the dish's
choices, `[{item_code, option_group?}]`, checked against the item's choice groups when the line is added.
⛔ A line with a `rate`, `price`, `amount` or `discount` key is refused, and so is a kit's line carrying a
`concession_note` (what a server promised a guest: only a till notes it). A unit sold in whole numbers takes a
whole quantity.

**A weighed article** (fruit, cheese, anything sold by the kilo) is paid at a scale reading, so its line
carries one: `weighed` is `{source, weight, tare?}`. Your app's reading is recorded as a typed weight
(`manual`), whatever source it names: it needs the manual-weight right, the cashier who takes the payment
needs it again, and the sale marks the line. The weight is the line's quantity, in the article's stock unit.
The check keeps the reading and the sale takes it from there. A line with a reading changes its weight only
with a new one (`check_change_line(…, weighed=…)`, before it is sent) and is never split. A weighed article
added by name with no reading is refused at Pay until it is weighed; that first weighing may come after the
line went to the kitchen. An article that also tracks lots or serials is sold by its lot or serial and takes
no reading. Each line the check returns says `sold_by_weight` (`true` with a reading or without one yet), so
your app knows which lines to offer a weighing on; a till offers *Weigh it* or *Weigh it again* on them to a
cashier who may change the line, except on a sent line that already holds a reading (a manager voids that one).

**`key`** is one per press of your button: a fresh random value (a UUID), ⛔ never one built from an order
number or a table, which comes round again. A request repeated with the same key — a lost answer, a retry,
a double press arriving at once — returns the first answer and writes nothing twice. A retry re-sends exactly
what it sent: the same key sent for another check, or with other arguments, is refused (`CheckRequestError`). **`version`** is the version of the check (or of the
line) you last saw: a change is refused when someone changed it since, and you read the check again.

**What you get back:** the check, as `open_check.v1.schema.json` `check` states it — never a payment token
or a sale key, and to your app no staff identity (who opened, serves, added or is paying), no register and
no concession note; the suggested customer only on a check your own user opened.
A line's `options` come back with each choice's `item_name` and its `per` (how many of it go with one of its
dish) beside `item_code` and `option_group`, so a screen can draw the choice lines; send only `item_code` and
`option_group`.

**`floor_status(store)`** answers the store's sections, its active places (each with its status, derived from
its open checks: *free*, *seated*, *ordered*, *paying*) and its tabs. Each check's summary carries
`last_write_at`, when it was last written by any till or app. A till also gets the server's name, the till of
that last write (*"Updated 20:41 at Till 3"*), `servers` (the store's operators a check can be handed to) and
`realtime` (the live wiring it listens on); to your app those are absent or null.

## 2a. The kitchen

A check keeps its own **kitchen order** (`Retail Kitchen Order`), the same record and the same tickets as a
sale sent from the till: one ticket per kitchen, headed with the place (or the tab's name) and the till that
sent it. A line is marked `sent` only when its kitchen took the ticket — handed to its network printer, or
returned to the till's own print agent (`counter_till`, a till only); a kitchen with no printer, or whose
printer refused, marks nothing, and the answer's `results` says why: send again. A line whose ticket the
till's agent could not print is sent again by the next send — a split part with it (the till reports it
with `check_ack(check, ticket, ok, kitchen_order)` — `kitchen_order` required, as the answer named it, since
ticket numbers are per order — a till's call only, never the sale's kitchen report:
every till of the table writes the one order). `results` lists each kitchen's
answer (`handed`, `agent` with the ticket's text, or `failed` with a reason); your app reads only the
kitchen, the line count, the state and the ticket number.

Each dish on a ticket carries the line's guest and course under it (*Guest 2 · Mains*). To send one course
while the next waits, name its lines in `line_ids`: the till's *Send* asks which course when the lines
waiting span more than one. A send that names lines is still the next send: a line whose ticket the till's
agent could not print goes with it.

A sent line's dish cannot be changed, and the line cannot be removed; its `seat` and `course` can (they
change nothing the kitchen makes, and a guest is who pays for it). It leaves the check only by a void, a comp (each asks its own
right, which the shop gives its managers, or a manager signing in at the till; either way it writes an
approval record naming the check, and the line is on the check's history), or being paid. A void goes to
the kitchen order the line was sent on, even after the line moved to another check, to the kitchen that send went to,
and is read with that order's place and register of its last send (a check moved since then is not
renamed on the void); a void of a line whose ticket never printed prints nothing. Once any line has gone to the kitchen the check's service mode is fixed. A kitchen
display reads the check's tickets like any other, with each dish's guest and course
([Station ticket](station_ticket.md)).

⛔ The kitchen order of a check is never the paying sale's: paying some lines of a check is never refused
because the kitchen has the others.

## 2b. Paying a check (a till's calls, never an app's)

When Pay opens on a check, the till **claims** the lines it is paying — all of them or the chosen ones,
all or none — with `check_claim(check, key, line_ids?)`. The answer carries a **token**, once: it is stored
only as a hash, never read back, published or written to the check's history. A second till that asks for
the same lines is refused with *"Being paid at Till 2 by Sam since 21:04."* and can pay the others. A retry
of a lost answer, with the same key from the same device and POS day while the claim is held, gets the
same claim and a fresh token (the old one stops working).

The basket the till pays is built from the claim, never from the till's list: each line names its check
line (`check_line`), and its item, quantity, unit and choices must be the check's; how it is paid — a
markdown asked of a manager, a lot, the customer, *served by*, the tenders — is the till's, as on any sale.
Every card push asserts the claim before the terminal is asked, and the sale's own booking closes exactly
the claimed lines. A cancelled check sale gives its lines back to the check; it is never amended.

A till claims only at a register of the check's own store that rings the check's service mode; another
till of the store takes the payment otherwise.

Guest by guest, each payer's part is its own sale from some of the check's lines: several claims on one
check may be held at once, each with its own token, and the check stays open with the rest. The engine
prices each sale on its own lines, so a promotion or charge that counts a quantity or a total can make the
parts come to more or less than the check paid together; `check_preview(check, line_ids)` gives the
engine's price of any set of open lines, and the till shows that difference before a guest pays. Nothing
shares the money out to make the parts agree.

No clock ends a claim. **Back** (`check_release(claim, token)`) frees the lines unless a card payment under
the claim is live or money noted on the bank's own machine is not cleared. Each slip is noted on its own
before it runs (`check_note_pending(claim, token, tender, amount, ref?)` — `ref` names the slip, the split
leg's key; a split's own bank's-machine check notes its leg itself) and cleared on its own when it was not
paid there (`check_clear_pending(claim, token, ref?)`; with two slips open, name the one; a second slip of
one sale must be named). No slip is noted while a card under the claim is live. A manager
with *end another till's payment* breaks a dropped till's claim with a reason
(`check_break_claim(claim, reason, confirm?)`): refused while a card payment is live, and, with money noted
on the bank's machine, refused until the manager confirms the guest was not charged there.

## 2c. The printed check and the day's close (a till's)

**The printed check** (`check_print`) is the shop's price of the open lines at the till's register, in the
store's language, headed *Check, not a receipt*, with the place, the server, the party size, the time and
*"Prices at payment time. Discounts are applied at payment."* It goes to the till's printer through the
receipt's print path, with the shop's layout *mPOS Open Check*; the answer carries the same paper for a
till with no printer of its own. It is never stored: the bill is priced again when it is paid. ⛔ It never
shows a line's `concession_note`. Each print raises the check's `printed_count` and writes a `check_print`
event (the version and the lines, never a figure), so a check printed and then changed shows in its history.
`version` (optional) refuses a check that changed since the till showed it.

**The day's close.** A check belongs to the store, not to a POS day: an open check carries to the next day,
and the close counts only the sales that booked. A day is not closed — at the till or in iVendNext Desk —
while a payment taken under it is still held on a check (*"A payment is open on Table 12 at Till 2. Finish it
or go back first, or ask a manager to end it."*). A register can also refuse the store's last close of the
day while any check is open (POS Profile *Refuse the Last Close While Checks Are Open*, beside *Table
Service*: ticked on any register of the store that serves tables; off by default). The till's close lists the store's open checks and the payments held under its day.

## 3. Refusals

A refusal comes back as the framework's error with `exc_type` set to a stable code, and the shop's words:

| `exc_type` | When |
|---|---|
| `TableServiceOffError` | the register's Table Service is off (open, add, move, merge, split and a till's claim only; a removal, a close of an empty check, Back, a break, the bank's-machine note and its clear, and every read still work) |
| `CheckNotOpenError` | the check is closed, merged into another, or gone |
| `CheckChangedError` | the line or the check changed since `version`: *"Table 12 changed on another till. Here it is now."* — read it again with `check_get` (the refusal carries no check) |
| `LineClaimedError` | a till is taking payment for that line: *"Being paid at Till 2."* (to a claiming till: *"Being paid at Till 2 by Sam since 21:04."*) |
| `LineSentError` | the line went to the kitchen; a manager voids it |
| `LineNotOpenError` | the line was paid, removed or voided, or is not on this check |
| `LineNotSentError` | voiding a line that never went to the kitchen: take it off with `check_remove_line` |
| `ItemRefusedError` | the item cannot be sold (disabled, not a sales item, a template, a gift card, a choice on its own) or its choices break the item's groups |
| `ServiceModeMismatchError` | merging or moving lines between checks in different service modes, or paying a check at a register that does not ring its mode |
| `CheckHasOpenLinesError` | closing a check that still has lines |
| `CheckRequestError` | a missing or malformed argument (no `key`, no place and no label, a price on a line, a version newer than the check's, a server who does not work at the store, a key already used for something else) |
| `PermissionError` | your user lacks the right, or the store — or your app sent a manager's sign-in (*"A manager approves this in person, at a till."*: a manager approves at a till, never through an app) |
| `ProfileNotAssignedError` | `pos_profile` is not your user's register at that store |
| `AssignedProfileDisabledError` · `DuplicateStoreAssignmentError` · `StoreAssignmentIncompleteError` | your user's assignment at that store is disabled, doubled or incomplete (the shop's administrator fixes it) |
| `UOMMustBeIntegerError` | a quantity that is a fraction of a unit sold in whole numbers (the engine's own rule and words) |
| `DeviceRequiredError` | your user has had a till device enrolled: a till's user is never a kit, so use an integration user that never signs in to a till |
| `WrittenOutsideDoorError` | a write to a check, a line, a claim or an event that did not come through these calls |
| `ClaimRefusedError` | (a till) the payment presented is not one this till holds: another till's, an ended one, or the wrong token, device or day |
| `PaymentInProgressError` | (a till) Back, or a break, while a card payment is live or money is noted on the bank's machine |
| `ConfirmPendingError` | (a till) a break of a payment with money noted on the bank's machine: the manager confirms the guest was not charged |
| `CheckBasketMismatchError` | (a till) the basket differs from the lines being paid |
| `CheckCartError` | a check's basket sent to a door that does not take its payment (hold, park, order, layaway, quote, return): *"A table's check is paid at a till, not held or ordered."*; a till's basket bound to a table's order (`open_check`, written lines or not) sent to a paying door: *"This is a table's order, kept on its check. Tap Checkout on the table to take its payment."* (the till's *Checkout* on a table's order claims its lines first, so only a caller that skipped the claim meets this); or a sale naming a check that the till's own payment did not build |
| `OpeningRequiredError` | (a till) paying a check with no POS day open, or with a day that closed (or is closing) meanwhile |
| `CheckPaymentOpenError` | (a till, Desk) closing or cancelling a POS day while a payment taken under it is still held on a check |
| `ChecksOpenAtCloseError` | (a till, Desk) the store's last close while checks are open, where the store refuses that |
| `OfflineCheckSaleError` | (a till's offline review, never a call) a sale for a check queued without a connection: never booked; pay it on the check |

## 4. Who may do what

Each verb asks its own right. The shop grants them in **Retail Permission**, group *Open Checks*, and links
that record to your integration user; the floor's administrator (anyone with write on Floor Sections —
System Manager unless the shop changes it) holds them all. ⚠ So grant write on Floor Sections only to someone
you would trust with every check verb — comping a line included. When your app's own user holds a void
or comp right, the approval record names your integration user as the one who approved it.

**Recommended grants** (the shop decides; these are not a fence):

| Your app | Rights |
|---|---|
| front of house (reservations) | open a check · see the checks |
| guest ordering (a QR menu, a kiosk) | open a check · add to a check · see the checks |

⛔ Never ask the shop for move, merge, close, change, send, void, comp, pay, break or print:
those are a person's decisions, and an app granted them has made a person's decision a machine's.

**One integration user per kit app:** the door tells a check your user opened from any other user's, never one
app from another behind the same user, so two apps sharing a user see each other's suggested customers.
**Your user is fenced to its stores:** it must have the store, and `pos_profile` must be its register there.
The shop gives it the store in iVendNext Desk, on the user: keep *Is Desk User* ticked, tick *Is POS User*, choose a
*Shift Profile*, link the Retail Permission, add a row under the store access table with the store and that register,
then Save; *Generate Keys* after that. The store table shows only with *Is POS User* ticked, and a user without it
loses its store rows at its next save (*Generate Keys* is a save), so its key works but every call is refused
*"You are not assigned to this outlet."* An app's own user (`…@integration.invalid`) takes the same ticks; it still
takes no password and no other role.
**Which guest may see which check is your app's job:** the door scopes by store, and cannot tell one guest
from another behind one integration user.

A check your app opens with no `server` stays unassigned until the first till writes to it.

## 5. Written only by these calls

No role holds create, write or delete on the check's records. A save from iVendNext Desk (an administrator
included), the generic record calls (the framework's own record methods, `/api/resource`), a data import or a write of one
line is refused with `WrittenOutsideDoorError`. ⚠ Code installed inside the site can still write them; the
fence is against outside writers.

## 6. Live and offline

After each change the door tells each till of the store `{check, version, status, store, place, label,
summary}` (never a customer, a token or a sale key; the label is there because a tab has no place to show);
a till ignores an older version. Your app polls
`floor_status` or `check_get`. The till's own floor reads `floor_status` again on each message, polls every 30
seconds while its live link is down, and says *"Not live. Last updated 20:41."* after 90 seconds without one. A check needs a connection: nothing here works offline. A sale for a check
that a till queued while it had no connection is never booked: the till's offline review shows it as
`OfflineCheckSaleError` (pay it on the check; discard the queued one), and the check carries
`offline_flag` (*"A sale for Table 12 was queued offline at Till 3."*) for a manager. Your app never sees
that flag.

## 7. Money

None. A check is never priced, discounted or charged here; the shop prices its lines when they are paid,
as an ordinary sale (`check_preview` shows that price when asked; it is never kept). A line's `concession_note` (what the server promised, *"birthday, dessert 50% off"*)
is a note a manager reads at payment, never a discount, and your app never sees it. A comp is not a price
either: the line comes off the check, so the sale never carries it.

## 8. Two worked examples

**A reservation seated.** `check_open(store, pos_profile, key="⟨a fresh UUID⟩", place="⟨Table 12's id⟩",
covers=4, source="front_of_house", source_ref="RES-2210", suggested_customer="⟨the guest⟩")` → version 1,
server unassigned. The first till that adds a round becomes its server.

**A kiosk order.** `check_open(…, key="⟨a fresh UUID⟩", label="Order 42", covers=1, source="guest_ordering")`,
then `check_add_lines(check, [{"item_code": "LATTE", "options": [{"item_code": "OAT-MILK"}]}], key="⟨another
fresh UUID⟩")`.
A latte whose *Milk* group needs a choice and gets none is refused at the add, not at the counter.

## 9. Telling an AI assistant

"Call `ivendnext_mpos.api.v1.check_*` with a fresh `key` per user action and the `version` you last read; on
`CheckChangedError` read the check again with `check_get`. Never send a price; never reuse a key. Never ask for move, close,
change, send, void, comp, pay or break rights. Validate requests against `open_check.v1.schema.json`."

Contract: [`open_check.v1.schema.json`](../extension_contracts/open_check.v1.schema.json) ·
samples under `tests/extension_contracts/samples/open_check/` · code `business_logic/open_check.py`.
