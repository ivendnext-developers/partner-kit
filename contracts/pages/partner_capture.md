<!-- Source: ivendnext/iVendNext_PWA docs/extending/partner_capture.md @ 8c955ffd9fcf, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Partner capture

**Contract:** [`partner_capture.v1.schema.json`](../extension_contracts/partner_capture.v1.schema.json)
· samples: [`samples/partner_capture/`](../extension_contracts/samples/partner_capture/)
· code: `business_logic/partner_capture.py` (`on_scan`, `customer_round`, `verify`, `gate_customer`,
`validate_answer`, `validate_verify`, `validate_subscription`), `business_logic/partner_point.py` (`call`),
the till's sheets in `public/js/mpos_partner_capture.js`.

## 1. What it is and when it fires

Your HTTPS service is asked at a moment the cashier did not choose, at one of two events:

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

**On scan you shape the cashier's flow; you are not a booking gate.** The basket lives on the device, so a
rule that must hold when the sale is booked is a partner check (extension point `check`), which the server
enforces at every door that moves money.

**On customer add the server is the gate.** With a customer service switched on, the server refuses to
create a customer until it has recorded your answer for that cashier, that name and that phone. A refusal
makes no customer. A phone that already belongs to a customer attaches that customer, and you are not
asked. ⚠ The gate holds on iVendNext POS's own doors; a customer made in iVendNext Desk or through another
API is outside it.

## 2. Version

Version 1. Every call carries `X-iVendNext-Point: capture/1`, and the body is `{"point": "capture/1",
"context": {…}}` with `context.v = 1`. A change that would break a version-1 service is a new version,
published beside this one.

## 3. What is sent, and what you answer

**Setting it up.** A System Manager adds one **Retail Extension Subscription** per event in iVendNext Desk:
extension point `capture`, your HTTPS address, a signing secret, the label the cashier sees, what the till
does when you are down (`allow_and_flag`, the default, or `refuse`), the POS Profiles it serves (none = all)
and `settings`, a JSON object:

- on scan: `{"event": "scan", "item_groups": ["Restricted"], "item_field": "is_age_restricted"}` — item
  groups (at most 50; a group names every group below it too), an item field that holds a value (`Check`,
  `Data`, `Select`, `Link`, `Int` or `Small Text`, at permission level 0), or both; at least one;
- on customer add: `{"event": "customer_add"}`.

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

Keep `challenge_id` if you answer *challenge*: the code comes back with it. **Verify:**

```json
{"point":"capture/1","context":{"v":1,"point":"capture","event":"verify",
 "challenge_id":"9f2c…32 hex…","code":"482913"}}
```

**Your answer** — HTTP 2xx, a JSON object of at most 64 KB:

| Answer | Shape | Event | The till |
|---|---|---|---|
| allow | `{"verdict":"allow"}` | both | goes on, nothing shown |
| confirm | `{"verdict":"confirm","question":"…"}` | scan | a beep and the question, Yes / No; *No* leaves the item off |
| refuse | `{"verdict":"refuse","reason":"…"}` | both | the item is not added, or the customer not created; your sentence is shown |
| challenge | `{"verdict":"challenge","prompt":"…","length":4–8}` | customer add | the code field, with your prompt |
| capture | `{"verdict":"allow","line_attributes":[{"name","value"}],"sale_attributes":[{"sale_attribute","attribute_value"}]}` | scan | a confirm sheet; on *Add with these details* the values land on this line and the sale |

**Verify** answers `{"verdict":"ok"}` or `{"verdict":"refuse","reason":"…"}`.

**Judged whole:** one bad key or value refuses the whole answer, and your declared down answer applies.
Texts (`question`, `reason`, `prompt`) are plain, 1 to 140 characters: no `<` or `>`, no control
characters, line or paragraph separators, bidi embedding, override or isolate controls, private-use or
surrogate characters (the marks Arabic and Persian text carries are fine). `length` is a whole number from 4 to 8. `line_attributes`: 1 to 10 rows of
exactly `{"name", "value"}`, each an active Transaction Item Attribute, once, its value matching the
attribute's own pattern when it has one; never on customer add. `sale_attributes` as the
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
| A code of the wrong length | *"Enter the ⟨length⟩-character code."* |
| The code check is over (ten minutes passed, it ended, or another cashier's) | *"This code check has ended. Add the customer again."* |
| A create without your recorded answer — the till's own first step: it tries the create, the server refuses, and the till then asks you and sends the create again with the server's token | *"Check the customer's code first."* (the cashier does not see it: the round starts) |
| Down on scan, declared `refuse` | *"⟨label⟩ did not answer. The item can't be added until it does."* |
| Down on customer add, declared `refuse` | *"⟨label⟩ did not answer. The customer can't be added until it does."* |
| Offline, the till could not read its declared answers (customer add) | *"This till could not read its checks. Reconnect, then add the customer again."* |

**Why an answer was refused** — written to the *Retail Extension Log* row of the call (never your body or
the secret): *"the verdict is not one ⟨event⟩ allows"* · *"the answer carries a key ⟨verdict⟩ does not allow
here"* · *"⟨question / reason / prompt⟩ must be plain text of 1 to 140 characters"* · *"confirm needs a
question"* · *"refuse needs a reason"* · *"challenge needs a prompt"* · *"length must be a whole number"* ·
*"length must be 4 to 8"* · *"line_attributes must be a list of 1 to 10 rows"* · *"each line attribute row
must be exactly {name, value}"* · *"a line attribute is not an active Transaction Item Attribute"* · *"a line
attribute value must be plain text of 1 to 140 characters"* · *"a line attribute is returned twice for one
line"* · *"the attribute's own pattern is too complex to check a partner's value"* · *"a line attribute value
does not match its master's pattern"* · the sale attribute refusals of the remote till key · *"verify
answers ok, or refuse with a reason"* · *"the answer is empty or over 64 KB"* · *"the answer is not JSON"* ·
*"the answer is not a non-empty object"*.

**When the subscription is saved:** *"Name the event in the settings: scan or customer_add."* · *"The
settings of a ⟨event⟩ capture may only carry: ⟨keys⟩."* · *"item_groups must be a list of item group names."*
· *"A scan capture names at most 50 item groups."* · *"No item group named ⟨group⟩."* · *"item_field must be
the name of one field on Item."* · *"Item has no field ⟨field⟩ that holds a value."* · *"⟨field⟩ is set on ⟨n⟩
items; a scan capture's field may name at most 2000. Name item groups instead."* · *"Say which items a
scan capture asks about: item groups, an item field, or both."* · *"⟨subscription⟩ already answers ⟨event⟩
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

Changing the address, or the event, clears the consent until someone ticks it again.

**Down, slow, or an answer refused whole** — your declared down answer:

| | `allow_and_flag` (default) | `refuse` |
|---|---|---|
| On scan (1.5 seconds unless raised, 3 at most) | the line goes on; the log row is flagged | the item is not added (section 4) |
| On customer add (3 seconds unless raised, 10 at most) | the customer may be created; the log row is flagged | the customer is not created (section 4) |
| At `verify` | the code counts as checked; flagged | the check ends |

Every call leaves one *Retail Extension Log* row (outcome, the verdict, flagged or not), listed on the
*Sales to review* report when flagged. The till's routine first create (refused until your answer is
recorded) leaves no row; a create carrying a token that does not hold — spent, expired, another cashier's,
another name or phone — leaves a flagged one.

## 6. Offline

You are not called. The till carries each service's declared down answer, and the scan filter (its item
groups and the items whose field is set), in its boot snapshot. On scan: an item the filter names goes on
(`allow_and_flag`, marked on the line, and the sale's sync writes one flagged row naming it) or is refused
(`refuse`). On customer add: `allow_and_flag` lets the cashier take the name and phone for the sale;
`refuse` stops it on the till. If the till could not read its declared answers, every scanned item goes on
and is flagged (the scan's answer is advisory), and a new customer waits for a connection.
**At sync a customer is never refused:** the sale was paid hours ago, so a customer created through the
sync without your recorded answer is created and flagged. The receipt's *add a contact* after a walk-in sale
posted today or yesterday is created and flagged too — one customer per paid sale (the same name and phone
again, a receipt retried after a failed send, goes on, flagged); another one named on the same sale, or one on
an older sale, gets your code check, as the quick-create sheet does.

A line let on offline is flagged once for its sale: when the sale syncs, or when the cashier presses Pay
after the connection returns.

## 7. Money and limits

**No money touch.** No price, total or tender is sent, and nothing you answer changes one. A value you put
on a line is annotation: it moves no money.

Limits: texts 1 to 140 · `length` 4 to 8 · 1 to 10 line rows · line value 140 · 1 to 20 sale rows · item
groups 50 · an item field set on at most 2000 items · three tries per code, counted before you are called ·
60 customer rounds per 10 minutes from one address · a challenge, and the token it earns, live ten minutes
(the token is spent by the create) · answer 64 KB ·
on scan 1.5 seconds unless raised, 3 at most · on customer add 3 seconds unless raised, 10 at most · one
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

## 9. Telling an AI assistant

> Build an HTTPS endpoint that answers iVendNext POS extension point `capture`, version 1. The contract is
> `partner_capture.v1.schema.json`: `$defs/scan_request`, `$defs/customer_request` and
> `$defs/verify_request` in; `$defs/scan_answer`, `$defs/customer_answer` and `$defs/verify_answer` out.
> The samples under `samples/partner_capture/` are known-good and known-bad answers. Verify
> `X-iVendNext-Signature` (base64 HMAC-SHA256 of `<timestamp>.<raw body>`) before parsing and refuse a
> timestamp more than 300 seconds off. Dispatch on `context.event`. On `scan`, answer within 1.5 seconds;
> on `customer_add` within 3: to send a code, store it against `context.challenge_id`, answer `challenge`
> with its length, and answer `verify` for that id with `ok` or `refuse`. Texts are plain, 1 to 140
> characters. Never return a price.
