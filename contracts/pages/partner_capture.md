<!-- Source: ivendnext/iVendNext_PWA docs/extending/partner_capture.md @ 60147699cce4, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Partner capture

**Contract:** [`partner_capture.v1.schema.json`](../extension_contracts/partner_capture.v1.schema.json)
· samples: [`samples/partner_capture/`](../extension_contracts/samples/partner_capture/)
· code: `business_logic/partner_capture.py` (`on_scan`, `customer_round`, `select_round`, `qty_round`, `verify`,
`gate_customer`, `assert_customer_checked`,
`validate_answer`, `validate_verify`, `validate_subscription`), `business_logic/partner_point.py` (`call`),
the till's sheets and the quantity gather in `public/js/mpos_partner_capture.js`.

## 1. What it is and when it fires

Your HTTPS service is asked at a moment the cashier did not choose, at one of four events:

- **On scan** — when the cashier scans an item your filter names (its item group, a group below it, or an
  item field that is set), after the item is found and **before** its line goes on the sale. You answer
  *allow* (nothing shown), *confirm* (a beep and a yes / no; *No* leaves the item off — under the camera the
  pause offers *Yes, add it*, and skipping it is the *No*), *refuse* (the item
  is not added; your sentence is shown), or *allow* with values to put on the line or the sale (the
  cashier sees them on a confirm sheet first). Every other scan is untouched and calls nobody (an item field
  the filter names that is later removed from Item, or changed to a field that holds no value of its own,
  matches nothing; a capture that cannot run for an item the filter names applies your declared down answer,
  flagged, and a filter that cannot be read lets the item on). A scan of
  an item coming back on a return, and an item the cashier picked from a list, are never asked about.
- **On customer add** — when the cashier adds a new customer, **before** the customer is created. You
  answer *allow*, *refuse*, or *challenge*: you have sent the customer a one-time code, and the till shows
  a code field. The cashier types what the customer reads out; the till sends it to you with the
  `challenge_id` (the `verify` step), and you answer *ok* or *refuse*. Three wrong codes end the check.
- **On customer select** — when the cashier puts an EXISTING customer on the sale (picked from the list,
  found by a scan of their card or code, matched by the phone typed into quick-create, or brought by a
  resumed sale, a quote turned into a sale or an order, or an exchange). Never for the
  store's walk-in, and never for a customer this cashier created in the last ten minutes while a customer
  add service is switched on (the add already asked). You answer as on customer add: *allow* (a CRM told who is at the counter), *refuse* (a customer
  locked to another store: the till shows your sentence and takes them off the sale — the sale goes on
  without a customer, or with another), or *challenge* (a one-time code, checked through `verify`).
- **On a quantity change** — when the quantity of a line your filter names changes on a sale: the ＋ / −
  buttons, a typed quantity, the basket's `+` / `-` keys, or a repeat scan that merges into the line.
  A burst of presses or scans is asked **once, 600 ms after the last**, with the final quantity; a typed quantity once, when it is entered. You are sent the line's
  **last allowed quantity** and the new one, and answer as on scan: *allow* (the new quantity stands; you
  may put values on the line, which the cashier sees on a confirm sheet first), *confirm* (a beep and a
  yes / no), or *refuse* (your sentence is shown). A refusal or a *No* puts back the **last allowed
  quantity** — never the quantity just before the change, so a quantity you refused can never come back.
  The line shows *"Checking a quantity…"* while your answer is out, and the basket re-prices as now.
  **Every door that moves the sale on asks first:** Pay (every way into the payment screen: Park, send to
  a till, the card and split screens, and a basket with a returned item before its refund), Hold, Save as
  quote, a layaway plan, an order, and an exchange's settle each ask any line whose quantity is not yet allowed and wait (*"Checking a quantity…"*); a
  refusal keeps the sale on the basket, at the allowed quantity. Never asked: a return's quantities, an
  offer's companion item, a weighed or scale-label line, a set, a gift card, a serial- or lot-tracked line
  (version 1: a lot pick splits and joins lines on its own), and a quantity equal to the last allowed one.

**On scan and on a quantity change you shape the cashier's flow; you are not a booking gate.** The basket lives on the device, so a
rule that must hold when the sale is booked is a partner check (extension point `check`), which the server
enforces at every door that moves money.

**On customer add the server is the gate.** With a customer service switched on, the server refuses to
create a customer until it has recorded your answer for that cashier, that name and that phone. A refusal
makes no customer. A phone that already belongs to a customer attaches that customer, and you are not
asked. ⚠ The gate holds on iVendNext POS's own doors; a customer made in iVendNext Desk or through another
API is outside it.

**On customer select the server holds the payment.** With a select service switched on, every door that
charges or books the sale — the card push, a split's card leg, a wallet, the payment itself, the cash park a
till settles, a layaway plan and its deposit, a cross-store order and its deposit, a basket where items come
back and new ones go out for a refund or an even swap — refuses until the server
has recorded your *allow* or a checked code for **that cashier and that customer, at that POS Profile, from
your service**: an answer at one store never pays at another. A code checked for one customer never passes
another, and a customer picked again is asked again. The booking — or a cash sale sent to a till — uses the
record up, so one check pays one sale. A customer that arrives without a pick is asked when it arrives — a resumed
sale, a quote turned into a sale or an order, an exchange's replacement sale; anything else (a quote
opened to edit it, an answer lost, a sale paid twelve hours later) is refused at payment with *"This
customer has not been checked. Pick them again, or sell without a customer."* — picking them again asks
you. A payment on something the customer already holds — a layaway plan's later payment, an order's
balance, their account — is not a new pick and is not held. A payment pressed before your answer arrives
is refused with those same words, and picking the customer again asks you again. One cashier sends you at most 60 select rounds in ten
minutes, counted from the first; past that the till shows *"Too many attempts. Try again in a few
minutes."* without asking you, and a customer you already let on stays on.

## 2. Version

Version 1. Every call carries `X-iVendNext-Point: capture/1`, and the body is `{"point": "capture/1",
"context": {…}}` with `context.v = 1`. A change that would break a version-1 service is a new version,
published beside this one.

**The answer `notice` was added to version 1** (additive: nothing you already send changes). The first POS
build that accepts it is the first whose release notes list *the capture answer `notice`*. An older build
refuses `notice` as an unknown verdict and applies your declared down answer, so with `refuse` declared the
item is blocked with *"⟨label⟩ did not answer…"*: don't send `notice` to an older build. The other way round
is safe: an older till given a newer server's notice adds the line silently, with nothing shown.

## 3. What is sent, and what you answer

**Setting it up.** A System Manager adds one **Retail Extension Subscription** per event in iVendNext Desk:
extension point `capture`, your HTTPS address, a signing secret, the label the cashier sees, what the till
does when you are down (`allow_and_flag`, the default, or `refuse`), the POS Profiles it serves (none = all)
and `settings`, a JSON object:

- on scan: `{"event": "scan", "item_groups": ["Restricted"], "item_field": "is_age_restricted"}` — item
  groups (at most 50; a group names every group below it too), an item field that holds a value (`Check`,
  `Data`, `Select`, `Link`, `Int` or `Small Text`, at permission level 0), or both; at least one;
- on customer add: `{"event": "customer_add"}`;
- on customer select: `{"event": "customer_select"}`;
- on a quantity change: `{"event": "qty_change", "item_groups": ["Sold in sixes"]}` — the scan's filter,
  with the scan's rules.

One service answers each event for a POS Profile. The form shows the time to answer for the event the
settings name (section 5's table) and stops a longer one before the save. Then the System Manager ticks the
consent (section 5).

**The call** — one signed `POST` per event, signed like every extension point's call: `X-iVendNext-Timestamp`
(Unix seconds) and `X-iVendNext-Signature` = base64 HMAC-SHA256 of `<timestamp>.<raw body>` with the
shared secret (the method and a verifier: [remote till key](remote_till_key.md), section 3). On scan:

```json
{"point":"capture/1","context":{"v":1,"point":"capture","event":"scan","sale_ref":"…",
 "store":"Stores - DXB","pos_profile":"Mall Branch","operator":"cashier@shop.example",
 "customer":"CUST-0001","lang":"en",
 "line":{"item_code":"PHONE-X","item_group":"Handsets","qty_milli":1000,"uom":"Nos",
         "batch_no":"","serial_no":"","scanned_code":"5901234123457"}}}
```

- `sale_ref` is the till's own id for the sale. It is empty on a sale's first scan: an empty basket is no
  sale yet. `customer` is the sale's customer as the till sent it, or `null`.
- `qty_milli` is the quantity in thousandths (one scan = 1000). The line has no till id yet: it does not
  exist until your answer lets it on.
- No price, total or tender is sent.

On customer add:

```json
{"point":"capture/1","context":{"v":1,"point":"capture","event":"customer_add",
 "challenge_id":"9f2c…32 hex…","store":"Stores - DXB","pos_profile":"Mall Branch",
 "operator":"cashier@shop.example","lang":"en",
 "customer":{"customer_name":"Ana Diaz","phone":"+971501234567","email":"","customer_group":""}}}
```

On customer select — `sale_ref` is empty before the sale's first line, and `customer` names the record:

```json
{"point":"capture/1","context":{"v":1,"point":"capture","event":"customer_select",
 "challenge_id":"7a1e…32 hex…","sale_ref":"sale-3f9c","store":"Stores - DXB","pos_profile":"Mall Branch",
 "operator":"cashier@shop.example","lang":"en",
 "customer":{"customer":"CUST-00041","customer_name":"Ana Diaz","phone":"+971501234567",
 "email":"ana@example.com","customer_group":"Retail"}}}
```

On a quantity change — `line.line_ref` is the till's own id for the line, stable while the sale stays on
the till's basket; `qty_milli_answered` is the quantity last allowed, `qty_milli` the new one (thousandths);
`seq` rises with each change to the line, and the till drops an answer to an older one:

```json
{"point":"capture/1","context":{"v":1,"point":"capture","event":"qty_change","seq":4,
 "sale_ref":"sale-3f9c","store":"Stores - DXB","pos_profile":"Mall Branch",
 "operator":"cashier@shop.example","customer":"CUST-0001","lang":"en",
 "line":{"line_ref":"q8k2v0d1mz","item_code":"WATER-500","item_group":"Sold in sixes","uom":"Nos",
         "qty_milli_answered":6000,"qty_milli":7000}}}
```

Keep `challenge_id` if you answer *challenge*: the code comes back with it. **Verify:**

```json
{"point":"capture/1","context":{"v":1,"point":"capture","event":"verify",
 "challenge_id":"9f2c…32 hex…","code":"482913"}}
```

**Your answer** — HTTP 2xx, a JSON object of at most 64 KB:

| Answer | Shape | Event | The till |
|---|---|---|---|
| allow | `{"verdict":"allow"}` | all | goes on, nothing shown |
| confirm | `{"verdict":"confirm","question":"…"}` | scan, qty_change | a beep and the question, Yes / No; *No* leaves the item off, or puts the last allowed quantity back |
| refuse | `{"verdict":"refuse","reason":"…"}` | all | the item is not added, the customer not created, the customer taken off the sale, or the last allowed quantity put back; your sentence is shown |
| challenge | `{"verdict":"challenge","prompt":"…","length":4–8}` | customer add, customer select | the code field, with your prompt |
| notice | `{"verdict":"notice","message":"…"}` | all | goes on with no tap, and shows *"⟨label⟩: your message"* (below); on scan it may carry `line_attributes` / `sale_attributes` and on a quantity change `line_attributes`, as *allow* may: then the confirm sheet opens with your message as its first line |
| capture | `{"verdict":"allow","line_attributes":[{"name","value"}],"sale_attributes":[{"sale_attribute","attribute_value"}]}` | scan | a confirm sheet; on *Add with these details* the values land on this line and the sale |
| capture | `{"verdict":"allow","line_attributes":[{"name","value"}]}` | qty_change | a confirm sheet; *Add with these details* keeps the quantity with the values on the line; *Keep the old quantity* puts the last allowed quantity back |

**A notice warns without stopping the sale** — a shorter-dated batch in stock, points about to expire, a
promotion tier one unit away. It is *allow* plus a sentence, so every gate reads it as *allow* (the
customer add's token, the select's recorded answer). Something that must stop the cashier — a recall — is a
*confirm* or a *refuse*, never a notice. A notice is never a down answer, and offline there is none (you are
not called).

- **Where it shows.** Off the camera, in its own slot below the till's warnings for 8 seconds, your label
  first; a tap or a swipe up closes it. It never replaces the till's own heads-up or warning, and they never
  replace it; a second notice replaces the first. Under the camera, the run's pause, your label as the
  chip, with *Got it*.
- **When.** On scan, once the line is added — after *"Added ⟨item⟩"* and the till's own heads-ups. A weighed item's, once it is weighed and added. A line the
  till refuses after your answer shows nothing. On a quantity change, when your answer arrives. On customer
  add, once the customer is created; on customer select, once the customer is on the sale (before an order,
  an exchange or a hand-off to a till that sale goes on to: if that later step fails, the notice has still
  shown). An exchange's
  replacement shows it once, when it lands.
- **What can be lost.** Under the camera with a pause already up (the till's own heads-up, or an earlier
  notice), your notice is dropped; and a till heads-up arriving while your notice is up replaces it: the
  till's warning wins, in either order. The camera's pause names your label, not the item — name the item in
  your sentence. A repeat scan that merges into a line can draw a
  scan answer and a quantity answer; the till shows one notice per scan, the scan's. Two notices in a row:
  off the camera only the later is on screen; under the camera the earlier stays and the later is dropped. Every call still has its log row.
- **The sentence is never logged**, and the till never reads it: the row says *"⟨label⟩: answered with a
  notice"*.

**No answer sets a quantity or a price.** A `set_qty`, a `qty`, a price, `sale_attributes` on a quantity
change, or any other key refuses the whole answer, and your declared down answer applies.

**Verify** answers `{"verdict":"ok"}` or `{"verdict":"refuse","reason":"…"}`.

**Judged whole:** one bad key or value refuses the whole answer, and your declared down answer applies.
Texts (`question`, `reason`, `prompt`, `message`) are plain, 1 to 140 characters: no `<` or `>`, no control
characters, line or paragraph separators, bidi embedding, override or isolate controls, private-use or
surrogate characters (the marks Arabic and Persian text carries are fine). `length` is a whole number from 4 to 8. `line_attributes`: 1 to 10 rows of
exactly `{"name", "value"}`, each an active Transaction Item Attribute, once, its value matching the
attribute's own pattern when it has one; never on customer add or select. `sale_attributes` as the
[remote till key](remote_till_key.md)'s. A code the cashier types is checked before you are called: the
till checks its length, the server checks the length and that it is ASCII letters and digits.

A line carrying your values is its own line: a later scan of the same item never merges into it. A scanned
unit's own code (a [scan source](scan_source.md)) is never overwritten by a value you send for the same
attribute.

## 4. Every refusal, in the product's words

**What the cashier reads:**

| What happened | The cashier reads |
|---|---|
| You refused a scanned item | *"This item can't be added"* and your `reason`, then *Back to the basket* |
| You refused a customer | *"This customer can't be added"* and your `reason`, then *Back* |
| A wrong code, tries left | your `reason` and *"⟨n⟩ tries left."* |
| The third wrong code | *"This customer can't be added"* and your `reason` |
| You refused a customer put on a sale | *"This customer can't be on this sale"*, your `reason` and *"Sell without a customer, or pick another one."*, then *Back to the basket*; the customer is off the sale |
| A select's code check is over (three wrong codes, or down and declared `refuse`) | *"This customer can't be on this sale"* and the reason; the customer is off the sale. A *Cancel* at the code field takes them off too |
| Payment for a customer you have not let on | *"This customer has not been checked. Pick them again, or sell without a customer."* |
| Down on customer select, declared `refuse` | *"⟨label⟩ did not answer. The customer can't be on this sale until it does."* |
| A code of the wrong length | *"Enter the ⟨length⟩-character code."* |
| The code check is over (ten minutes passed, it ended, or another cashier's) | *"This code check has ended. Add the customer again."* |
| A create without your recorded answer — the till's own first step: it tries the create, the server refuses, and the till then asks you and sends the create again with the server's token | *"Check the customer's code first."* (the cashier does not see it: the round starts) |
| Down on scan, declared `refuse` | *"⟨label⟩ did not answer. The item can't be added until it does."* |
| Down on customer add, declared `refuse` | *"⟨label⟩ did not answer. The customer can't be added until it does."* |
| You refused a quantity | your `reason` and *"The quantity is back to ⟨n⟩."* (the last allowed quantity); the sale goes on |
| You answered `notice` | *"⟨label⟩: ⟨message⟩"* for 8 seconds, below the till's warnings; under the camera the pause, chip ⟨label⟩, line ⟨message⟩, *Got it* |
| Down on a quantity change, declared `refuse` | *"⟨label⟩ did not answer. The quantity can't change until it does. The quantity is back to ⟨n⟩."* |
| Offline, a quantity change, declared `refuse` | *"⟨label⟩ needs a connection to change this quantity. The quantity is back to ⟨n⟩."* |
| A door waiting on your answer | *"Checking a quantity…"* |
| Offline, the till could not read its declared answers (customer add) | *"This till could not read its checks. Reconnect, then add the customer again."* |

**Why an answer was refused** — written to the *Retail Extension Log* row of the call (never your body or
the secret): *"the verdict is not one ⟨event⟩ allows"* · *"the answer carries a key ⟨verdict⟩ does not allow
here"* · *"⟨question / reason / prompt / message⟩ must be plain text of 1 to 140 characters"* · *"confirm needs a
question"* · *"notice needs a message"* · *"refuse needs a reason"* · *"challenge needs a prompt"* · *"length must be a whole number"* ·
*"length must be 4 to 8"* · *"line_attributes must be a list of 1 to 10 rows"* · *"each line attribute row
must be exactly {name, value}"* · *"a line attribute is not an active Transaction Item Attribute"* · *"a line
attribute value must be plain text of 1 to 140 characters"* · *"a line attribute is returned twice for one
line"* · *"the attribute's own pattern is too complex to check a partner's value"* · *"a line attribute value
does not match its master's pattern"* · the sale attribute refusals of the remote till key · *"verify
answers ok, or refuse with a reason"* · *"the answer is empty or over 64 KB"* · *"the answer is not JSON"* ·
*"the answer is not a non-empty object"*.

**When the subscription is saved:** *"Name the event in the settings: scan, customer_add, customer_select or
qty_change."* · *"The settings of a ⟨event⟩ capture may only carry: ⟨keys⟩."* · *"item_groups must be a list of
item group names."* · *"A ⟨event⟩ capture names at most 50 item groups."* · *"No item group named ⟨group⟩."* ·
*"item_field must be the name of one field on Item."* · *"Item has no field ⟨field⟩ that holds a value."* ·
*"⟨field⟩ is set on ⟨n⟩ items; a ⟨event⟩ capture's field may name at most 2000. Name item groups instead."* ·
*"Say which items a ⟨event⟩ capture asks about: item groups, an item field, or both."* · *"⟨subscription⟩ already answers ⟨event⟩
for these POS Profiles. One service answers each."* · *"The time to answer must be more than 0 and at most
⟨3 or 10⟩ seconds."* · *"When the service is down, this extension point can only: allow_and_flag,
refuse."* · and the address and label rules every extension point's subscription carries.

## 5. Consent, and when your service is down

The System Manager's tick records who ticked it, when, for which address and for the event's list, word
for word. On scan:

> What the till sends to this address when an item this service's filter names is scanned, before the
> line is added: event · sale_ref (the till's own id for the sale) · store · pos_profile · lang (the till's
> language) · operator (the signed-in cashier's user id, personal data) · customer (personal data) · the
> line: its item_code, item_group, quantity, unit, batch, serial and the code scanned. No price, total or
> tender is sent.

On customer add:

> What the till sends to this address when a cashier adds a new customer, before the customer is created:
> event · challenge_id · store · pos_profile · lang (the till's language) · operator (the signed-in
> cashier's user id, personal data) · the customer's name, phone, email and customer group (personal data).
> To check a code the customer gives: the challenge_id and the code. No price, total or tender is sent.

On customer select:

> What the till sends to this address when a cashier puts an existing customer on a sale, before the sale
> can be paid: event · challenge_id · sale_ref (the till's own id for the sale) · store · pos_profile · lang
> (the till's language) · operator (the signed-in cashier's user id, personal data) · the customer's id,
> name, phone, email and customer group (personal data). To check a code the customer gives: the
> challenge_id and the code. No price, total or tender is sent.

On a quantity change:

> What the till sends to this address when the quantity of a line this service's filter names changes,
> before the sale moves on: event · sale_ref (the till's own id for the sale) · store · pos_profile · lang
> (the till's language) · operator (the signed-in cashier's user id, personal data) · customer (personal
> data) · a sequence number (seq) · the line: its line id, item_code, item_group, unit, the quantity last
> allowed and the new quantity. No price, total or tender is sent.

A quantity-change subscription consented with the scan's text has no consent: each event's own text is
required.

Changing the address, or the event, clears the consent until someone ticks it again.

**Down, slow, or an answer refused whole** — your declared down answer:

| | `allow_and_flag` (default) | `refuse` |
|---|---|---|
| On scan (1.5 seconds unless raised, 3 at most) | the line goes on; the log row is flagged | the item is not added (section 4) |
| On customer add (3 seconds unless raised, 10 at most) | the customer may be created; the log row is flagged | the customer is not created (section 4) |
| On customer select (3 seconds unless raised, 10 at most) | the customer stays on and the sale may be paid; the log row is flagged | the customer is taken off the sale (section 4) |
| On a quantity change (1.5 seconds unless raised, 3 at most) | the new quantity stands and becomes the allowed one; the log row is flagged (a request whose answer never came back to the till is marked on the line and flagged as *"quantity changed offline, not asked"* when the sale is paid online or synced; if the server did answer, late, that change carries two rows) | the last allowed quantity is put back (section 4) |
| At `verify` | the code counts as checked; flagged | the check ends |

Every call leaves one *Retail Extension Log* row (outcome, the verdict, flagged or not, and the call's
`request_id` — the call's `X-iVendNext-Request-Id` header, so you can match your own record), listed on the *Sales to review*
report when flagged. The till's routine first create (refused until your answer is
recorded) leaves no row; a create carrying a token that does not hold — spent, expired, another cashier's,
another name or phone — leaves a flagged one.

## 6. Offline

You are not called. The till carries each service's declared down answer, and the scan filter (its item
groups and the items whose field is set), in its boot snapshot. On scan: an item the filter names goes on
(`allow_and_flag`, marked on the line, and the sale's sync writes one flagged row naming it) or is refused
(`refuse`). On customer add: `allow_and_flag` lets the cashier take the name and phone for the sale;
`refuse` stops it on the till. On customer select: `allow_and_flag` keeps the customer on the sale; `refuse`
takes them off. A sale paid offline with a customer you were not asked about books when it syncs, flagged
once (*"customer on the sale offline, not asked"*); paid after the connection returns, it is refused until
the customer is picked again. If the till could not read its declared answers, every scanned item goes on
and is flagged (the scan's answer is advisory), and a new customer waits for a connection.
**At sync a customer is never refused:** the sale was paid hours ago, so a customer created through the
sync without your recorded answer is created and flagged. The receipt's *add a contact* after a walk-in sale
posted today or yesterday is created and flagged too — one customer per paid sale (the same name and phone
again, a receipt retried after a failed send, goes on, flagged); another one named on the same sale, or one on
an older sale, gets your code check, as the quick-create sheet does.

A line let on offline is flagged once for its sale: when the sale syncs, or when the cashier presses Pay
after the connection returns.

On a quantity change: an item the filter names keeps its new quantity (`allow_and_flag`, marked on the line;
the sale's sync, or Pay after the connection returns, writes one flagged row, *"quantity changed offline, not
asked: ⟨item⟩ (⟨label⟩)"*, beside any scan's row) or goes back to its last allowed quantity (`refuse`). The
till names a line by its item group, as it was scanned; a line whose group the till does not hold (one
brought back by a resumed sale) is not asked offline, and its new quantity counts as allowed — it is not asked
or flagged later. The till's offline list of items named by an item field is capped at 2000 (the save's cap).

**Bounds of the quantity change (version 1).** The till keeps each line's last allowed quantity in the sale's
draft, so it survives a reload. A held or parked sale comes back from the server rebuilt line by line, and
each line starts at the quantity it arrives with: what keeps a refused quantity out of a held or parked sale
is that Hold and Park ask first. The server's own fold of a resumed sale's lines can change quantities
without asking you. A service switched on after a till started reaches that till at its next start. A
serial- or lot-tracked line is outside the event. An order's change and a return's quantities are outside it too.
An exchange's replacement basket is asked (a repeat scan merging in, and its settle waits), but its rows show no
*"Checking a quantity…"* mark; the settle's busy sheet is what the cashier sees. A change marked on the line
offline (or when the till's request got no answer) is flagged when the sale is paid online or synced as a sale;
a sale that leaves by Hold, Save as quote, a layaway plan, an order or an exchange comes back rebuilt without
the mark, so that change is not flagged (the scan's own offline mark has the same bound). A quantity
added to a line while its sale is being paid carries over to the next sale as a line of its own, at that
quantity, neither asked nor flagged.

## 7. Money and limits

**No money touch.** No price, total or tender is sent, and nothing you answer changes one. A value you put
on a line is annotation: it moves no money.

Limits: texts 1 to 140 · `length` 4 to 8 · 1 to 10 line rows · line value 140 · 1 to 20 sale rows · 3000
quantity changes per 10 minutes from one address · item
groups 50 · an item field set on at most 2000 items · three tries per code, counted before you are called ·
60 customer adds and 3000 customer selects per 10 minutes from one address (a till asks on every pick while
online), and 60 select rounds per cashier · a challenge, and the token it earns,
live ten minutes (the token is spent by the create) · a select's recorded answer lives twelve hours and is
spent by the sale it pays · answer 64 KB ·
on scan or a quantity change 1.5 seconds unless raised, 3 at most · on customer add or select 3 seconds unless raised, 10 at
most · one
service per event per POS Profile. HTTPS only, the certificate checked against your host name; a host that
resolves to a private, loopback or link-local address is refused unless the site allows it (a test bench).

## 8. Worked examples

**An age check.** A scan service with `{"event": "scan", "item_groups": ["Restricted"]}`. A bottle of wine
(group *Wines*, below *Restricted*) is scanned; you answer
`{"verdict":"confirm","question":"Age-restricted. Has the customer shown ID?"}`. The till beeps and asks.
*No* leaves the bottle off; *Yes* adds it. A loaf of bread is scanned and you are not called. Your service
is down for a moment: with `allow_and_flag` the bottle goes on and the *Sales to review* report lists it.

**A one-time code when a customer is added.** A customer service with `{"event": "customer_add"}`. The
cashier adds *Ana Diaz, +971501234567*; you send her a code by SMS and answer
`{"verdict":"challenge","prompt":"Ask the customer for the 6-digit code we just sent.","length":6}`. Ana
reads out *482913*; the till sends `verify` with it and you answer `{"verdict":"ok"}`. The customer is
created. Had she given a wrong code three times, you would answer
`{"verdict":"refuse","reason":"Wrong code."}` each time and the third would end the check: no customer.

**A customer locked to a store, and a code for a known customer.** A select service with
`{"event": "customer_select"}`. The cashier at the Mall picks *CUST-00041*, whose account belongs to the
Sandton store: you answer `{"verdict":"refuse","reason":"This customer buys at the Sandton store only."}`;
the till shows it and takes her off the sale, which carries on without a customer. Another customer holds a
loyalty account that needs a code: you send it and answer `challenge`; until `verify` answers *ok*, the card
push and the payment are refused on the server.

**A pack-size rule.** A quantity service with `{"event": "qty_change", "item_groups": ["Sold in sixes"]}`.
The cashier scans a bottle of water and presses ＋ six times quickly to 7; 600 ms after the last press you
are asked once, `qty_milli_answered` 1000 and `qty_milli` 7000. You answer
`{"verdict":"refuse","reason":"Sold in sixes. Sell 6 or 12."}`: the line goes back to 1 and the cashier reads
your sentence. They press ＋ to 6 and you answer *allow*. Had they pressed Pay while you were still deciding,
Pay would have waited for your answer.

## 9. Telling an AI assistant

> Build an HTTPS endpoint that answers iVendNext POS extension point `capture`, version 1. The contract is
> `partner_capture.v1.schema.json`: `$defs/scan_request`, `$defs/customer_request`,
> `$defs/select_request`, `$defs/qty_request` and `$defs/verify_request` in; `$defs/scan_answer`,
> `$defs/customer_answer`, `$defs/select_answer`, `$defs/qty_answer` and `$defs/verify_answer` out.
> The samples under `samples/partner_capture/` are known-good and known-bad answers. Verify
> `X-iVendNext-Signature` (base64 HMAC-SHA256 of `<timestamp>.<raw body>`) before parsing and refuse a
> timestamp more than 300 seconds off. Dispatch on `context.event`. On `scan` and `qty_change`, answer
> within 1.5 seconds (on `qty_change` judge `line.qty_milli` against `line.qty_milli_answered`, and never
> answer a quantity);
> on `customer_add` or `customer_select` within 3: to send a code, store it against `context.challenge_id`, answer `challenge`
> with its length, and answer `verify` for that id with `ok` or `refuse`. Texts are plain, 1 to 140
> characters. Never return a price.
