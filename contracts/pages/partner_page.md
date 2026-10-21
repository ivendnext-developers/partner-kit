<!-- Source: ivendnext/iVendNext_PWA docs/extending/partner_page.md @ 7d47d331a203, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Partner page

**Contract:** [`partner_page.v1.schema.json`](../extension_contracts/partner_page.v1.schema.json)
· samples: [`samples/partner_page/`](../extension_contracts/samples/partner_page/)
· code: `business_logic/partner_page.py` (`validate_declaration`, `address_problem`, `sign_context`,
`submit`, `desk_context`), `business_logic/partner_point.py` (`validate_subscription`),
`business_logic/app_button.py` (`validate_result`, which judges the answer).

## 1. What it is and when it fires

Your own page, inside our frame: a delivery partner's order board in a sheet over the sale on the till
(counter and tablet), or a console in Desk at `/app/partner-page/<page>`. Your page learns who is looking
at what from a **signed, one-time, five-minute context** in its address, and on the till your server may
**answer once** — a message, Sale Attribute rows, or both — which the cashier confirms like any till key.

It fires when the cashier presses the page's key on the till, or when a Desk user opens the page (a link
or shortcut the shop adds, or a [Desk action's](desk_action.md) `open_page` answer).

## 2. Version

Version 1: the context carries `"v": 1`.

## 3. What is declared, what the page receives, what you answer

**The declaration** — a **Retail Extension Subscription** of extension point `page`: your page's address
(HTTPS; its host is the only one we frame, never the shop's own), a secret, where it opens (*Till key*,
*Desk page*, or *Till key and Desk page*), who may open the Desk page (roles), whether the signed-in
user's id and the sale are sent, what the page may answer on the till (`message`, `sale_attributes`), its
height on the counter (40 to 100 percent), and optionally the POS Profiles whose tills may open it — ⚠ a
page limited to POS Profiles never opens in Desk, nor from a Desk action's `open_page`. On the
till the page is a key like any app key: switch it on in **POS Studio → Apps** (the phone places no app
keys).

**What the page receives** rides the URL fragment, never the query, so it reaches no server log and no
`Referer`: `…/board#ctx=<payload>.<signature>`, both parts base64url without padding. The payload:

```json
{"v": 1, "page": "8a1f0c2d3e", "nonce": "0123456789abcdef0123456789abcdef",
 "iat": 1759845600, "exp": 1759845900, "lang": "en",
 "theme": {"mode": "light", "vars": {"--ivn-accent": "#0b6bcb", "--ivn-radius": "8px"}},
 "store": "Main Store - AC", "pos_profile": "Counter 1",
 "sale": {"sale_ref": "…", "store": "…", "pos_profile": "…", "company": "…", "currency": "AED",
          "operator": "cashier@shop.example", "customer": null, "lines": [ … ]},
 "user": "cashier@shop.example"}
```

- On the till: `store`, `pos_profile`, and `sale` (the [remote till key's](remote_till_key.md) moneyless
  picture) when declared. In Desk: `doctype` and `name` when opened for a record. `user` when declared.
- **Your duties:** send the fragment to your own server; there, recompute HMAC-SHA256 of the decoded
  payload bytes with the secret and compare in constant time, refuse an `exp` in the past, and **refuse a
  `nonce` you have already seen**.
- **The frame:** `sandbox="allow-scripts allow-forms allow-same-origin"`, `referrerpolicy="no-referrer"`,
  `allow=""`. Your page keeps its own origin, so it cannot read ours; it cannot navigate the top window or
  open pop-ups. `/pos` sends `frame-src 'self' <your origin>` while your page is placed on a till. Let the
  shop frame you (`frame-ancestors` / `X-Frame-Options`), and never redirect to another origin.
- **Your address:** declare the FOLDER your pages live under (`https://partner.example/pos/`): Desk opens
  only an address on the same origin at or below it, with no `.` or `..` segment. One Desk page per
  address: a link under two declared addresses goes to the deeper one, and two pages declared at the
  same address share its links (the first in the subscriptions' sequence order takes them).

**Answering (till only).** Your SERVER posts `{"ctx_nonce": "<nonce>", "result": {…}}` to
`/api/method/ivendnext_mpos.api.page.submit`, signed like every extension point's call:
`X-iVendNext-Timestamp` (Unix seconds, within 300 seconds of ours) and `X-iVendNext-Signature` = base64
HMAC-SHA256 of `<timestamp>.<raw body>`. `result` is judged exactly as a [remote till key's
answer](remote_till_key.md#3-what-is-sent-and-what-you-answer): only the kinds the page may answer, one
bad part refuses the whole. One answer per nonce. **Then** your page posts `{"type": "ivendnext:done"}`
to its parent; the till hears it only from your frame on your origin, closes the sheet, picks the answer
up and shows its confirm sheet.

## 4. Every refusal, in the product's words

**Your server's answer** (`api/page.submit`):

- *"The answer must be a JSON object of exactly ctx_nonce and result."*
- *"This page is closed, or its time ran out. Nothing was added to the sale."* (an unknown or expired
  context, or one the cashier closed)
- *"The answer's signature does not match."* (a wrong secret, or a timestamp more than 300 seconds off)
- *"This page is switched off. Nothing was added to the sale."*
- *"This page has already answered."*
- *"This answer cannot be used: ⟨why⟩"* — the reason is one of the [remote till key's](remote_till_key.md#4-every-refusal-in-the-products-words).
  A refused answer may be corrected and sent again while the context lives.

**On the till:** *"Add an item to the sale first, then press this button."* · *"This button's app is not
available right now. Nothing was added to the sale."* · *"This button is not switched on for this till.
Nothing was added to the sale."* · *"The sale changed. Nothing was added. Press the button again."* (the
sale changed while the confirm sheet was open) · *"⟨label⟩ did not send an answer. Nothing was added to
the sale."* (your page posted `ivendnext:done` before your server's answer was stored: the pick-up closes
the context, so ⚠ post `done` only after `submit` returned `{"ok": 1}`) · *"⟨label⟩ could not be checked.
Nothing was added to the sale."* (the pick-up itself failed) · a page that has not loaded in 10 seconds:
*"⟨label⟩ isn't answering."* with Close.

**In Desk:** *"You can't open this page for that record."* (no role, no read right on the record, a
page not placed on Desk, or one limited to POS Profiles) · *"This address is not the partner page's own."* · *"This page cannot be opened
right now."*

**When the declaration is saved:**

- *"The label must be 1 to 40 characters."* · *"Choose where the page opens."* · *"Only a partner
  service address can answer this extension point."* (any transport but `remote`)
- *"The address cannot be used."* followed by one of: *"It must be an HTTPS address of at most 500
  characters."* · *"It is not an address."* · *"It must start with https:// and name a host."* · *"It must
  not carry a user name, a password or a # part."* · *"It must not contain spaces or control
  characters."* · *"Write its host in plain letters (a name in another script in its xn-- form)."* · *"Its
  path must not contain . or .. parts, a backslash, ; or an encoded / or %."* · *"A partner page cannot be
  on this site's own address."*
- *"Choose who may open the Desk page."* · *"Choose at least one thing the page may answer on the till."* ·
  *"The height on the till must be from 40 to 100."*
- *"The time to answer must be more than 0 and at most 10 seconds."* · *"When the service is down, this
  extension point can only: refuse."* · *"The extension point's settings must be a JSON object."*

**In POS Studio → Apps:** *"Its record name is not one the till can use."* · *"It is switched off on its
record."* · *"The customer's consent is not recorded, or its address is not one this till can open."* ·
*"It names a result this till does not know."*

## 5. Consent, and when your page is down

The consent text is built from the declaration, word for word, from these parts:

> What the page receives in its address each time it opens, signed with the secret, usable once and for
> 5 minutes: the page's id, a one-time number, when it was made and when it runs out, the screen's
> language and its colours.

then *"On the till: the store and the POS Profile."* (with the sale, the sale's fields in words) when it
opens on the till, *"In Desk: the record type and name the page is opened for."* when it opens in Desk,
*"The signed-in user's id (personal data)."* when the user is sent, and always *"No price, total or
payment is sent."* Changing the address or any of those choices clears the consent until a System Manager
ticks it again.

**Down:** the one down answer is `refuse`. A page that does not load in 10 seconds shows *"⟨label⟩ isn't
answering."* with Close; nothing is added to the sale.

## 6. Offline

Online only: the key is dimmed while the till is offline.

## 7. Money and limits

**No money touch.** The context carries no price, and no answer kind carries money.

Limits: label 40 · height 40 to 100 percent · context usable once, for 5 minutes · one answer per nonce ·
your answer's timestamp within 300 seconds · the answer's message and Sale Attribute caps are the
[remote till key's](remote_till_key.md#7-money-and-limits).

## 8. Worked examples

**A delivery board on the till.** Declared *Till key*, sending the sale, answering `sale_attributes`. The
cashier presses *Deliveries*; your board shows the basket, the cashier books a courier slot, and your
server posts `{"ctx_nonce": "…", "result": {"sale_attributes": [{"sale_attribute": "Delivery Order",
"attribute_value": "TB-88123"}]}}`. Your page posts `{"type": "ivendnext:done"}`; the cashier confirms and
the sale carries the order number.

**A console in Desk for a record.** Declared *Desk page* at `https://partner.example/console/`, for the
role *Stock Manager*. A Desk user opens `/app/partner-page/<page>?doctype=Sales%20Order&name=SO-0042`;
the server checks the role and the user's read right on SO-0042 before it signs anything, and your
console receives `doctype` and `name` in its context. In Desk there is no answer: your console works
through your own API calls.

## 9. Telling an AI assistant

> Build a page for iVendNext POS's partner page extension point, version 1. The contract is
> `partner_page.v1.schema.json`: `$defs/context` is the payload of the `#ctx=<payload>.<signature>`
> fragment (base64url, HMAC-SHA256 over the payload bytes with the shared secret), `$defs/submit` is the
> signed body your server posts to `/api/method/ivendnext_mpos.api.page.submit`, `$defs/declaration` the
> Retail Extension Subscription. Verify the context on your server, refuse an expired one or a nonce you
> have seen, never read the context in the browser's storage or query, answer once, then post
> `{"type": "ivendnext:done"}` to the parent window.
