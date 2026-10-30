<!-- Source: ivendnext/iVendNext_PWA docs/extending/partner_check.md @ c39b1449937a, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Partner check

**Contract:** [`partner_check.v1.schema.json`](../extension_contracts/partner_check.v1.schema.json)
· samples: [`samples/partner_check/`](../extension_contracts/samples/partner_check/)
· code: `business_logic/partner_check.py` (`run_check`, `build_context`, `fingerprint`, `validate_answer`,
`validate_subscription`, `assert_check_holds`), `business_logic/partner_point.py` (`call`), the till's
sheets in `public/js/mpos_partner_check.js`.

## 1. What it is and when it fires

The last word on a sale before money is taken. When the cashier presses Pay, the iVendNext POS server prices
the basket itself and asks your HTTPS service: allow it, allow it without some tenders, refuse it, ask the
cashier a question, or call a manager. Your answer is stored against a fingerprint of that priced basket,
and **every door that moves money prices the basket again and compares before anything is charged** (all
but those section 7 lists): the card push, each split leg, the refunds and the bookings. A basket changed after your answer is refused until
the cashier presses Pay again, which asks you again. **And no other door books around you:** for a POS
Profile with your check in scope, a sale booked on the iVendNext Desk POS screen, through the API or from the
Desk form is refused for every user — *"This sale needs a partner's check before it is paid. Ring it up on a
till."* (section 7).

It fires when the cashier presses Pay, before the payment sheet opens (`stage: "sale"`); before the refund
choices open on every refund the till pays (`stage: "return"`): a return against its sale, a return without
its sale, a layaway plan's refund (its credit paid back, or what a cancelled plan returns) and an order's
(its credit paid back after a change, or what a cancelled order returns); and for an exchange, on its
replacement basket and on its returned lines, before the credit note posts. **And on an order or a
layaway plan, at placement** (`stage: "sale"`, like any sale): before a layaway plan's deposit is taken
(by card, in cash at the till, or sent as cash to another till), before an order's deposit, when an order
for another store's stock or a quote converted to an order is placed (after any manager's approval of the
order), and before an order's change is saved (asked on the order the change leaves). You are sent the order's lines and its whole total, never the deposit; nothing in the
context tells an order from a sale.

⛔ **Never after money.** Once a card is charged nothing is refused: the sale books and a flagged row lands
on the *Sales to review* report.

## 2. Version

Version 1. Every call carries `X-iVendNext-Point: check/1`, and the body is `{"point": "check/1",
"context": {…}}` with `context.v = 1`. Within version 1 new `return_of.channel` values may appear (`"none"`
and `"layaway"` were added): treat one you do not know as a return you did not expect, by your own rule
(allow, refuse or ask), never as a malformed call.

## 3. What is sent, and what you answer

**Setting it up.** A System Manager adds a **Retail Extension Subscription** of extension point `check` in
iVendNext Desk: your HTTPS address, a signing secret, the label the cashier sees, the time to answer (3
seconds unless raised, 10 at most; the form shows both and stops a longer one before the save), what the
till does when you are down (`allow_and_flag`, the default · `refuse` · `ask`), the POS Profiles it serves
(none = all), its order (`sequence`), **May ask for a manager's approval** (off by default) and **Send each
line's lot and serial number** (off by default; an address check only, below). At most three
checks answer one POS Profile, ten seconds together (the form shows one check's limit; the save adds up the
checks of each POS Profile). Then they tick the consent (section 5).

**The call** — one signed `POST`, signed like every extension point's call: `X-iVendNext-Timestamp` and
`X-iVendNext-Signature` = base64 HMAC-SHA256 of `<timestamp>.<raw body>` (method and verifier:
[remote till key](remote_till_key.md), section 3):

```json
{"point":"check/1","context":{"v":1,"point":"check","stage":"sale","currency_exponent":2,
 "sale_ref":"…","store":"Stores - DXB","pos_profile":"Mall Branch","company":"Shop LLC",
 "currency":"AED","lang":"en","operator":"cashier@shop.example","customer":"CUST-0001",
 "customer_group":"Retail","price_list":"Standard Selling","coupon_codes":["WELCOME10"],
 "sale_attributes":[{"name":"Prescription No","value":"RX-551"}],
 "lines":[{"line_no":1,"item_code":"PARA-500","item_group":"Pharmacy","qty_milli":2000,"uom":"Nos",
           "rate_minor":1250,"amount_minor":2500,"discount_minor":0,"line_attributes":[]}],
 "totals":{"net_minor":2500,"tax_minor":125,"discount_minor":0,"grand_minor":2625},
 "offered_tenders":["Cash","Credit Card"],"pos_opening":"POS-OPE-2026-00071",
 "pos_terminal":"Mall Counter 2"}}
```

- The numbers are the **server's**, never the till's echo. Money is a whole number of minor units with the
  currency's own digits (`currency_exponent`: 2 for AED, 3 for KWD, 0 for JPY); quantity is in thousandths.
- A line carries its row number (`line_no`), not the till's line id: one till line can become several priced
  rows. At most 500 lines are sent; past that, only the first 500, while `totals` are the whole sale's.
- `pos_opening` names the POS day the sale or refund is taken under, and `pos_terminal` that day's POS
  Terminal, so one rule can hold per terminal without one POS Profile per terminal; each is `""` when there
  is none. A sale synced from offline names the day it was taken under (a sale a manager posts again after
  its sync failed names that manager's open day instead). They **are part of the
  fingerprint**: a day suspended at one terminal and resumed at another moves its terminal mid-sale, so
  an answer you gave for one terminal is not used at another before money moves — the till asks you
  again; a sale whose card was already charged, or one synced from offline, is booked and flagged for
  review instead.
  ⚠ Added after version 1 first shipped: a service that validates the request against an older copy of
  this contract (`additionalProperties: false`) refuses them until it takes this copy.
- `operator` is not part of the fingerprint, but your answer pays only for the cashier it was asked for: the
  cashier who answers your question, and the one whose sale is booked, is the `operator` you were sent. Another
  cashier taking over the sale (a held sale resumed, a teammate on the same POS day) is asked again; a sale
  whose card was already charged, or one synced from offline, is booked and flagged for review instead.
- On a return, `sale_ref` is the refund attempt's own key, not a sale id.
- On a return, `return_of`: `{"invoice", "channel", "paid_by": [the names of the payment methods that paid it]}`. `channel` is `"pos"` for
  a return against a sale · `"order"` for an order's refund (`invoice` is the order; `paid_by` every tender
  that paid into it, the deposit and the collections) and for a return of an order's delivered lines
  (`invoice` is the delivery's sale; `paid_by` that sale's own tenders and every tender that paid into the
  order) · `"none"` for a return without its
  sale (`invoice` empty, `paid_by` empty) · `"layaway"` for a plan's refund (`invoice` is the plan's order;
  `paid_by` every tender that paid into the plan, the deposit and the collections). An order here is one
  taken at the till (an endless-aisle order, a quote turned into an order); where an order came from is not
  sent. A return without its sale may also carry lines being sold (an exchange rung on the selling screen):
  their `qty_milli` is positive — judge them by your sale rule. A plan's or an order's credit paid back has
  no lines: its `totals.grand_minor` is the amount going back. ⚠ A cancelled plan's refund sends the cancel return's
  lines and their full value; the till pays back less where the plan keeps a cancellation fee.
- No card data is sent. A line's lot and serial numbers are sent only to a check whose subscription ticks
  **Send each line's lot and serial number** (`check_send_lots`): each line then also carries `batch_no` (its
  lot, `""` when none) and `serial_no` (its serial numbers, one to a line, `""` when none), on a sale and on a
  return. The lot is the one the sale books: the cashier's pick, a scanned pack's, or the store's own pick
  where its stock settings pick for the cashier (a pick from two lots is two lines, one lot each); nothing
  tells you which of the three it was. On a store that does not pick for the cashier, the till asks for the
  lot at Checkout, before you are asked. A set's parts are not sent: a set is one line, with no lot of its
  own. On a layaway plan's round the lot sent is the one picked when the plan is opened; the unit handed
  over at pickup is chosen then and is not checked. A line that books no unit at this store is sent `""`: an order's or a quotation's line, and a sale's
  line delivered from another store (that store picks the lot when the goods leave); so is a delivered
  order line whose lots sit on its stock record alone (an order delivered from two lots). A check without the tick receives each line
  exactly as before. Each line's lot is **part of the fingerprint** whether or not it is sent: a lot
  changed after your answer is asked again before money moves (on a store that picks lots for the
  cashier, another till can take the last of the picked lot in between); a sale whose card was already
  charged, or one synced from offline, is booked and flagged for review instead.
  ⚠ Added after version 1 first shipped: a service that validates the request against an older copy of
  this contract refuses `batch_no` and `serial_no` until it takes this copy.
- A scanned GS1 pack's lot reaches you as `batch_no` when the item tracks lots, and its own serial as
  `serial_no` when the item tracks serial numbers ([scan source](scan_source.md) section 10, units as
  serial numbers). ⚠ A unit's code can also arrive another way: a
  scan source set to **Record the code as** a line value puts the scanned code on the line, and it reaches you in
  that line's `line_attributes`.

**Your answer** — HTTP 2xx, a JSON object of at most 64 KB, one of five:

| Answer | Shape | The till |
|---|---|---|
| allow | `{"verdict":"allow"}` | the payment sheet opens |
| allow, some tenders off | `{"verdict":"allow","exclude_tenders":["Gift Certificate"],"reason":"…"}` | those tenders are drawn dimmed with *"Not for this sale: ⟨reason⟩"* |
| refuse | `{"verdict":"refuse","reason":"…"}` | *"This sale can't be paid"* (on a refund *"This refund can't go ahead"*) and your sentence; back where the payment or refund began |
| ask | `{"verdict":"ask","question":"…"}` | Yes / No; *No* goes back to the basket |
| approve | `{"verdict":"approve","reason":"…"}` | a manager who is not the cashier signs in on the till |

`approve` only for a subscription with **May ask for a manager's approval**; the manager needs **May Approve
a Partner's Check** on their Retail Permission and write access to Retail Override Request. With nobody but
the cashier able to approve, the approve stands as a refusal.

**Filling sale details.** `allow`, `ask` and `approve` may also carry `fill`, the sale details your
subscription lists in its settings, by name: `{"verdict":"allow","fill":{"Rx Date":"2026-10-01"}}`, for a
subscription whose settings read `{"fill_attributes":["Rx Date"]}` (1 to 10 sale details; a manifest
declares them on its check, and each must be a sale detail the manifest itself declares or the shop
already has, or the install stops at the check). iVendNext writes them onto the sale (a value the cashier typed is overwritten;
the other details stand), prices the sale again, which runs the store's own rule for each detail, and asks
every check **once more on the filled sale**. That second answer is the round's, and the till sends the
filled details from then on, so every door that moves money books the sale you answered for. Expect a
second call whenever your fill changes the sale, and answer it with the same values: a value that changes
again is dropped and the round flagged, and there is never a third call. Two checks filling one detail: the
first in `sequence` holds it, and the other's value is dropped. The payment screen tells the cashier what was
filled (section 4). Each value is judged alone by the store's own rule for its detail: a value it refuses is
not written and only that detail is named to the cashier (unless the cashier typed one, which stands), while
the others still fill. A detail the store
has switched off since your list was saved is skipped, never your whole answer. If the filled sale would
price differently (a store's pricing rule that reads a sale detail), nothing is filled. In each of these
cases your answer stands and the round is flagged. ⚠ A detail the store makes **required** is asked of
the cashier before any check runs, so your fill can only overwrite it. Nothing is filled on a return, on a
sale with a third-party payer on the split (the payer answered on the sale's details as they were), at a
placement (an order, a layaway plan or an order's change is asked as a sale, but its door composes its own
basket, so a fill there is not written and nobody is asked again), or by a module (section 6).

**Judged whole:** texts are plain, 1 to 140 characters, with no `<` `>`, control, line or paragraph
separator, direction-override, private-use or surrogate characters (the marks Arabic and Persian text
carries are fine); `exclude_tenders` names 1 to 20 different tenders of `offered_tenders` and needs a
`reason`; `fill` names 1 to 10 sale details, each one your subscription lists, each value plain text of 1
to 140 characters, and never rides `refuse`. Anything else refuses
the whole answer, and your down answer applies.

**Several checks** are asked in `sequence`: the first refusal ends the round, exclusions add up, questions
are asked in turn.

⚠ A card terminal cannot tell a credit card from a debit card before it charges. Excluding the store's
**first** card method stops card payments at the till and the exchange (the split screen checks the type
its leg names); excluding another card method lets the card through, and a sale the cashier then marks as
that type books and is flagged. An exchange's credit note books store credit whatever the replacement
costs, so excluding the store credit method on a return refuses every exchange. On an exchange and on a
return against its sale, the sale details sent are the ones carried over from the sale; a correction the
cashier makes when iVendNext refuses a carried detail is booked after your answer, without a new call. An
exchange's replacement is a sale: a `fill` there writes onto the replacement, never the return.

## 4. Every refusal, in the product's words

**What the cashier reads:**

| What happened | The cashier reads |
|---|---|
| The services are being asked | *"Checking this sale"* (on an order, a layaway plan or an order's change: *"Checking this order"*, *"Checking this plan"*, *"Checking this change"*) |
| You refused | *"This sale can't be paid"* and your `reason`, then *Back to the basket* (at placement: *"This order can't go ahead"* then *Back to the order*, or *Back to the quote* for a quote converted to an order; *"This plan can't go ahead"* then *Back to the plan*; *"This change can't go ahead"* then *Back to the change*); on a refund *"This refund can't go ahead"*, then *Back to the return* (or *Back to the plan*, *Back to the order*, or *Back to the basket* when the refund began on the selling screen); an exchange's returned lines keep the sale's words |
| A tender you excluded | *"Not for this sale: ⟨reason⟩"* on its row (dimmed) |
| The basket changed after your answer, no answer is stored for it, or your answer was for another cashier | *"The sale changed after the check. Press Pay again."* |
| A cashier tried to approve their own sale | *"A cashier never approves their own sale."* |
| Nobody can approve | *"Nobody can approve this sale. A manager needs May Approve a Partner's Check on their Retail Permission and write access to Retail Override Request."* |
| The approvers could not be read | *"The manager approval could not be checked. Press Pay again."* |
| Down, declared `refuse` | *"⟨label⟩ did not answer. This sale can't be paid until it does. Try again, or get a manager."* |
| Down, declared `ask` | *"⟨label⟩ did not answer. Continue anyway?"* |
| Offline, the till could not read its checks | *"This till could not read its checks. Reconnect, then press Pay again."* |
| You filled sale details | *"⟨label⟩ filled: ⟨detail⟩: ⟨value⟩"*, one sentence per check, its details joined by *·*, *"⟨detail⟩: ⟨old⟩ → ⟨new⟩"* where the cashier had typed one, as the payment screen opens |
| A detail you filled was not written (the store's own rule refused its value, or the sale would not price as it was) and the sale has no value of its own for it | *"⟨label⟩ could not fill ⟨detail⟩. The sale goes on without it."* (where the cashier typed one, theirs stands and nothing is said) |

**Why an answer was refused** — on the call's *Retail Extension Log* row (never your body or the secret):
*"the answer is empty or over 64 KB"* · *"the answer is not JSON"* · *"the answer is not a non-empty
object"* · *"the verdict is not one of the five"* · *"the answer carries a key ⟨verdict⟩ does not allow"* ·
*"this service may not ask for a manager"* · *"⟨reason / question⟩ must be plain text of 1 to 140
characters"* · *"⟨verdict⟩ needs a reason"* · *"ask needs a question"* · *"exclude_tenders must be 1 to 20
different names"* · *"exclude_tenders names a tender the sheet does not offer"* · *"exclude_tenders needs a
reason"* · *"allow carries a reason only with exclude_tenders"* · *"this service may not fill a sale detail"* ·
*"fill must name 1 to 10 sale details"* · *"fill names a sale detail the subscription does not let it fill"* ·
*"each value filled must be plain text of 1 to 140 characters"*.

**When the subscription is saved:** *"At most 3 checks may answer one POS Profile."* · *"The checks of one POS
Profile may take at most 10 seconds together."* · *"Nobody can approve a partner's check yet. A manager needs
May Approve a Partner's Check on their Retail Permission and write access to Retail Override Request."* ·
*"⟨profile⟩ has one user, and a cashier never approves their own sale. Let this check ask the cashier
instead."* · *"When the service is down, this extension point can only: allow_and_flag, refuse, ask."* ·
*"The time to answer must be more than 0 and at most 10 seconds."* · *"The settings of a check may only
carry fill_attributes."* · *"fill_attributes must list 1 to 10 different sale details."* · *"⟨detail⟩ is not an
active sale detail, so a check cannot fill it."* (when the list is written; a detail switched off later
does not stop the record saving) · *"A partner module cannot fill a sale detail: a fill is
checked again on the server, which a till offline cannot do."* · and the address and label rules every
extension point's subscription carries.

## 5. Consent, and when your service is down

The System Manager's tick records who ticked it, when, for which address and for this list, word for word:

> What the till sends to this address at each check, before a sale or a refund is paid: stage (sale or
> return) · sale_ref (the till's own id for the sale) · store · pos_profile · pos_opening (the POS day)
> and its pos_terminal · company ·
> currency and its currency_exponent · lang (the till's language) · operator (the signed-in cashier's user
> id, personal data) · customer and customer_group (personal data) · price_list · coupon_codes ·
> sale_attributes (the details the cashier captured, which may hold health data such as a prescription) ·
> each line's row number, item_code, item_group, quantity, unit, price, amount, discount and captured
> values · the sale's net, tax, discount and grand totals · the tenders offered · on a return, the original
> sale (none for a return without its sale; the plan's order for a layaway plan's refund), whether it was
> an order or a layaway plan, and its tender types. No card data, serial or batch is sent.

A unit's code a scan source records as a line value is among the captured values. For a check that ticks
**Send each line's lot and serial number**, the list's last sentence reads instead: *"Each line's lot
(batch_no) and serial numbers (serial_no) are sent. No card data is sent."* Ticking or clearing that box
changes the list, so that check's consent lapses until it is ticked again; a check that never ticks it keeps
the words above, and its consent.

A check whose settings list `fill_attributes` consents to one more sentence at the end: *"The answer may
fill these sale details: ⟨the names, as listed⟩."* Changing the list changes the text, so that check's
consent lapses until it is ticked again; a check that lists none keeps the words above, and its consent.

Adding `pos_opening` and `pos_terminal` changed this list, so a consent ticked before it lapses: a check
asks nobody until a System Manager ticks it again.

**Down, slow, or an answer refused whole:** the declared down answer — `allow_and_flag` (the sale goes on;
the round is flagged), `refuse` or `ask` — and one log row (no body, no secret).

## 6. Offline, and a check that runs on the till

**A remote check is not called offline.** The till applies each check's declared down answer, in
`sequence`, from its boot snapshot; the sale synced later is flagged, never refused.

**A rule that must hold offline runs as your module.** A check can also be answered by a WebAssembly
module: one file, certified and signed through the Partner Programme, which iVendNext POS runs inside the
shop, on the server online and on the till offline. It has no network: nothing it reads is sent to you.

- **Setting it up.** The file is attached in iVendNext Desk as a **Retail Extension Module** of extension point
  `check`. A module certified by iVendNext runs once a System Manager adds it here. It is admitted only
  under our certificate, only if it carries its own step counter, is at most
  256 KB and imports nothing but `read_input`, `write_output` and `log`; anything else is refused with the
  reason. A **Retail Extension Subscription** of transport `wasm` then names it (with the partner filled in,
  its module picker lists only that partner's newest `check` modules), with no address and no secret (an
  address typed in is cleared on save), and the same label, down answer, POS Profiles and `sequence` as a
  remote check. The consent lists what the module reads and says it is not sent anywhere.
  A new version is a new module record; the subscription names the newest. A package can carry the module and
  its subscription instead (installing a manifest §11), installed switched off.
- **A recall.** iVendNext can recall one certified module by its SHA-256, in a release. From the shop's next
  deploy the module is refused where it is added, the server stops running it, and the till's next snapshot
  names no module, so the check takes your down answer on every till. A till that stays offline runs the
  module it holds until it next reads a snapshot; such a sale syncs flagged, never refused.
- **What it reads.** The same `check/1` context as section 3, never a line's `batch_no` or `serial_no` (`offered_tenders` is empty on the till
  offline; a line priced above its list reads `discount_minor` 0; a remote service reads 0 for a price
  typed above or below the list too, since the typed price is the line's list, as in iVendNext Desk), written as canonical JSON: keys sorted, no spaces, raw UTF-8, whole
  numbers only from 0 to 2⁵³−1, nested at most 32 deep. Server and till write the same bytes for the same
  sale.
- **What it answers.** `run()` reads the context with `read_input`, writes one answer with `write_output`
  — the five answers of section 3, judged by the same rules — and returns 0. A module that traps, runs out
  of steps or writes an answer refused whole takes your down answer. A module never fills: a `fill` from it
is refused whole, since a fill is priced again on the server, which a till offline cannot do. The till names no tenders offline,
  so `exclude_tenders` there also takes the down answer, and so does `approve` (nobody approves in person
  offline).
- **When it cannot be asked.** A return asks no module. A sale that also pays money back (a returned item
  or a cash-out rung with it) carries a negative amount the encoding cannot write, so the module is not
  asked and your down answer applies in these words: declared `refuse`, *"⟨label⟩ can't check a sale that
  also pays money back. Ring that part on its own."*; declared `ask`, *"⟨label⟩ can't check a sale that
  also pays money back. Continue anyway?"*; declared `allow_and_flag`, the sale goes on, flagged.
- **One second.** A module still running after 1 000 ms is stopped and the sale is not allowed: *"⟨label⟩
  took too long to answer. Try again, or get a manager."* online, *"⟨label⟩ took too long on this till.
  Try again, or get a manager."* offline.
- **On the till.** While online the till keeps the module its checks name, by its SHA-256, and runs it only
  if the bytes still match; a module it cannot read refuses the sale with *"This till could not read its
  checks. Reconnect, then press Pay again."*
- **When the offline sale syncs.** The sale is never refused. The server runs again the version the till
  ran — only if that version was active for the sale, judged by the time the till rang the sale, which the
  server checks against the open POS day — and writes on the flagged row whether they agreed, disagreed
  (both answers), or why it could not run it (never admitted, not active for this sale, withdrawn or its
  file gone, recalled by iVendNext, or no answer from the till), and what the current version says when the till ran an older one
  and they answer differently.

**Measured:** the till starts a module in 21.3 ms on a throttled stand-in (6× CPU slow-down) against a
50 ms budget. That is a stand-in, not a measurement on a real low-end till.

## 7. Money and limits

The check reads money and sends it; your answer never moves any. It never adds a line, a discount or a
payment, and a door that already charged a card never refuses. A `fill` writes sale details only: a fill
that would change the sale's money is not filled. A third-party payer asked after a fill reads the filled
details, as its prescription.

Limits: texts 1 to 140 · `exclude_tenders` 1 to 20 · `fill` 1 to 10 sale details · 500 lines sent · answer 64 KB · 3 seconds unless
raised, at most 10 · at most 3 checks per POS Profile, 10 seconds together (a round that fills asks each check
twice, so allow up to twice that).

**A sale with a third-party payer is checked again on the plan's prices.** Your check is asked at Pay on the
sale's own prices (the customer's price list, else the store's), and again whenever the sale's payer changes:
when the payer's answer lands (the plan prices the lines on its own list), when the payer is asked again or
removed, and when the cashier comes back to the split from the payment screen. Going back from the split to the
payment screen with the payer still on asks again on the sale's own prices, since that screen books the sale
without the plan, unless the split already holds money (a payment sent, or a card payment started or taken;
that payment is still checked on the plan's round) or the till is offline. Expect more than one round per sale; each answers for the figures it was asked about, and a
question or a manager's approval is asked again with it. ⚠ `price_list` stays the sale's header list (the
customer's own) on a plan-priced round: the lines' rates are the plan's. A refusal, the cashier's No or no
manager's approval on the plan's prices takes the payer off the sale.

**Every door that books a sale or a return, on any screen.** At a POS Profile with your check in scope, a
sale or return booked anywhere but the till's own doors (the iVendNext Desk POS screen, the API, the Desk
form, a held sale submitted from either, an import) is refused for every user. Outside the till a line
leaving another store's stock also takes that store's checks. ⚠ **A check is per POS Profile:** a profile
of the same store left out of your scope sells unchecked — on its till and on the Desk alike. Scope your
check to every profile on that store's warehouse, or leave it unlimited (no profile rows).

**An order and a layaway plan are checked once, at placement** (and again when a change is saved; a change
is sent the store's tenders like any round, though it takes no money). An answer that no longer fits when
the order books is refused with *"The check no longer fits this order. Try again."* (trying again asks you
again). A cash deposit cannot be sent to another store's till that runs a check this till does not: *"⟨till⟩
runs a partner's check this till does not. Pick a till at this store, or take the deposit here."* A deposit
sent to a till of the SAME store books on that till's own POS Profile: scope your check to every profile of
the store (see below). An excluded tender binds only what is paid at placement (a deposit), never the balance
paid at the order's delivery or the plan's pickup, and an order placed at the till with nothing to pay ignores it. Their
delivery, a layaway plan's instalments, its final payment and its pickup go on that answer and are not
checked again — a rule that must hold at hand-over (a prescription that may have lapsed) cannot be held
there in this version. A deposit sent as cash to another till is checked here, before it is sent; the till
that takes the cash does not ask again. A card already charged when your answer no longer holds books the
order or plan and flags it on the *Sales to review* report, as a sale's does.

**Not in this version:** a sale parked to a till, account collections and a gift card's balance paid
out in cash are not checked. Two finishes move no money at the till, so nothing is checked: a cancelled layaway plan whose
refund was already paid back in iVendNext Desk, and an order cancel that pays nothing back (what stays on
the order covers what was paid).

## 8. Worked examples

**A prescription for a product group.** Your service answers
`{"verdict":"refuse","reason":"A prescription number is needed for Pharmacy items."}` when a line's
`item_group` is *Pharmacy* and `sale_attributes` carries no *Prescription No*, else `{"verdict":"allow"}`.
Declared down answer: `refuse`, so an outage never sells without the check.

**Online refund only for an order paid by card.** On a return whose `offered_tenders` carries *Online
Refund*, your service takes it off unless `return_of.channel = "order"` and every tender in `return_of.paid_by` is a card:
`{"verdict":"allow","exclude_tenders":["Online Refund"],"reason":"Online refund is only for an order paid by card."}`.
The refund chooser draws *Online Refund* dimmed with *"Not for this sale: Online refund is only for an
order paid by card."* An order here is one taken at the till (section 3).

## 9. Telling an AI assistant

> Build an HTTPS endpoint that answers iVendNext POS extension point `check`, version 1. The contract is
> `partner_check.v1.schema.json` (`$defs/request` in, `$defs/answer` out); the samples under
> `samples/partner_check/` are known-good and known-bad answers. Verify `X-iVendNext-Signature` (base64
> HMAC-SHA256 of `<timestamp>.<raw body>`) before parsing, refuse a timestamp more than 300 seconds off,
> and answer within 3 seconds. Read money as integer minor units with `currency_exponent`. Answer one of
> `allow`, `allow` with `exclude_tenders` and a `reason`, `refuse`, `ask` or `approve`; texts plain, 1 to
> 140 characters. Never return a price, a line or a payment. `allow`, `ask` and `approve` may carry
> `fill`, an object of the sale details the subscription's `fill_attributes` lists, each to a plain-text
> value; a sale your fill changes is sent again filled: fill the same values (a changed value is dropped).
> Nothing is filled on a return, beside a third-party payer, at a placement (an order — a quote converted to
> an order too — a layaway plan, an order's change), or by a module.
