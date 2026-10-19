<!-- Source: ivendnext/iVendNext_PWA docs/extending/remote_till_key.md @ 8c955ffd9fcf, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Remote till key

**Contract:** [`remote_till_key.v1.schema.json`](../extension_contracts/remote_till_key.v1.schema.json)
· samples: [`samples/remote_till_key/`](../extension_contracts/samples/remote_till_key/)
· code: `business_logic/app_button.py` (`build_context`, `validate_result`, `validate_remote_record`),
`business_logic/outbound.py` (`sign`, `remote_call`).

## 1. What it is and when it fires

A key on the till that your own HTTPS service answers, with nothing installed on the shop's site. When
the cashier presses it, the iVendNext POS server sends your service a read-only picture of the sale in
progress. You answer with a message for the cashier, Sale Attribute rows for the sale, values for its
lines (Transaction Item Attributes), or any of them together. The
cashier sees a confirm sheet and says yes or no; only on yes does the till put your answer on the sale.
**You return; the till decides.** Your service never writes the sale.

It fires on a press, and only then: never before payment, never at booking, never on a schedule. The till
asks nobody while it is offline or the basket is empty (section 4).

## 2. Version

Version 1. The request carries `User-Agent: iVendNext-POS-AppKey/1`. A change that would break a
version-1 service is a new version, published beside this one.

## 3. What is sent, and what you answer

**Installed from an app's package** (a manifest's `remote_keys`, package_install.md), the key
arrives ready: the install screen shows this section 5 list word for word, and that consent is the key's (who
consented to the install and when). The store then switches it on in **POS Studio → Apps**.

**Setting it up by hand — two people, two places.** A System Manager adds one **Retail Remote App Key** record
per key in iVendNext Desk: your name as the partner, an app name and a key (lowercase letters, digits
and `_`), the label the cashier sees, what the key may return (`message`, `sale_attributes`,
`line_attributes`), your HTTPS
address, a signing secret you both hold, and the time to answer. Then they tick the customer's consent
(section 5). The store switches the key on for its theme in **POS Studio → Apps**. It shows on the
counter and the tablet; the phone places no app keys.

**The request** — one `POST` to your address at each press:

```http
POST /your/path HTTP/1.1
Content-Type: application/json; charset=utf-8
X-iVendNext-Timestamp: 1759484400
X-iVendNext-Signature: 3q2+7w…base64…
X-iVendNext-Request-Id: 9f2c1a7e4b…32 hex characters, new at every press
User-Agent: iVendNext-POS-AppKey/1

{"app":"acme_loyalty","key":"loyalty_check","returns":["message","sale_attributes"],
 "context":{"sale_ref":"…","store":"…","pos_profile":"…","company":"…","currency":"USD",
            "operator":"cashier@shop.example","customer":"CUST-0001",
            "lines":[{"item_code":"SKU-1","qty":2.0,"uom":"Nos","luid":"…"}]}}
```

- `store`, `pos_profile`, `company`, `currency` and `operator` are the server's. `sale_ref`, `customer`
  and `lines` are what the till sent: the sale is still a draft on the device. Look things up by them;
  never grant or record value on them alone.
- `customer` is `null` when the sale has none, or names one this site does not have.
- No price, total, payment, serial or batch is sent. The body is ASCII JSON.
- The request id is new at every press, so a cashier pressing twice asks you twice. Key on `sale_ref` if
  your service must not do its work twice.

**The signature.** `X-iVendNext-Signature` is the base64 HMAC-SHA256 of the timestamp, a dot and the raw
request body bytes, with the shared secret. Verify against the raw bytes before you parse, and refuse a
timestamp more than five minutes from your clock:

```python
import base64, hashlib, hmac, time

def verified(secret: str, headers: dict, raw_body: bytes, window: int = 300) -> bool:
    ts = headers.get("X-iVendNext-Timestamp", "")
    if not ts.isdigit() or abs(time.time() - int(ts)) > window:
        return False
    mac = hmac.new(secret.encode(), ts.encode() + b"." + raw_body, hashlib.sha256)
    return hmac.compare_digest(base64.b64encode(mac.digest()).decode(),
                               headers.get("X-iVendNext-Signature", ""))
```

It is the same method as the iVendNext webhook signature over a different string, so a webhook
verifier rejects it.

**The answer** — HTTP 2xx with a JSON object of at most 64 KB, holding only the kinds in `returns`:

| Kind | Shape |
|---|---|
| `message` | `{"title": ≤ 60 characters, "body": ≤ 280, "level": "info" \| "success" \| "warning"}` — `level` reads `info` when left out |
| `sale_attributes` | 1 to 20 rows of exactly `{"sale_attribute", "attribute_value"}`: each name an active Sale Attribute on the site, once; each value ≤ 140 characters |
| `line_attributes` | 1 to 10 rows of exactly `{"line_no", "name", "value"}`: `line_no` is the line's place in `context.lines`, from 1; each name an active Transaction Item Attribute on the site, once per line; each value plain text of 1 to 140 characters that matches the attribute's own pattern when it has one |

A line value is written only onto the line it names, and only while that line is still the item it was
at the press: a line the cashier removed or moved meanwhile takes nothing, and the cashier reads *"A line
changed, so some details were not added. Press the button again."* An attribute whose own pattern could
take the server too long to check refuses a
value you send for it: a repeat or a choice inside a repeat, more than two variable repeats or choices
(a fixed `{n}` does not count), a back-reference or a look-around, or a pattern over about 94 characters.

**One bad kind, row or value refuses the whole answer.** Nothing is dropped quietly, so the confirm sheet
never promises a row the sale would lose.

## 4. Every refusal, in the product's words

**What the cashier reads at a press** (and nothing is added to the sale):

| What happened | The cashier reads |
|---|---|
| The till is offline (you are not called) | *"This button needs a connection."* |
| The basket is empty (you are not called) | *"Add an item to the sale first, then press this button."* |
| The till could not reach our server | *"This button could not be reached. Nothing was added to the sale."* |
| No answer inside the time to answer (lookup, connection, TLS, request and reading share one deadline) | *"⟨label⟩ did not answer in time. Nothing was added to the sale."* |
| The address does not resolve, resolves to a private address the site does not allow, refuses, fails TLS, answers a non-2xx, or redirects (never followed) | *"⟨label⟩ could not finish. Nothing was added to the sale."* |
| An answer over 64 KB, shorter than its stated length, not JSON, or refused by the checks below | *"⟨label⟩ answered in a way this till cannot use. Nothing was added to the sale."* |
| The record was switched off, lost its consent, or its address stopped being callable after the key was drawn | *"This button's app is not available right now. Nothing was added to the sale."* (you are not called) |
| The key is not switched on for this till's theme | *"This button is not switched on for this till. Nothing was added to the sale."* |

**Why an answer was refused** — written to the Error Log with the sale's reference and the request id,
never the secret or your body:

- *"not a JSON answer (⟨error⟩)"*
- *"the result is not a non-empty dict"*
- *"the result kind '⟨kind⟩' is not one this button declared"*
- *"message must be {title, body, level}"*
- *"message needs a title, a body within the caps, and a known level"*
- *"sale_attributes must be a list of 1 to 20 rows"*
- *"each row must be exactly {sale_attribute, attribute_value}"*
- *"a sale attribute name or value is blank or too long"*
- *"'⟨name⟩' is not an active Sale Attribute on this site"*
- *"'⟨name⟩' is returned twice"*
- *"line_attributes must be a list of 1 to 10 rows"*
- *"each line attribute row must be exactly {line_no, name, value}"*
- *"a line attribute is not an active Transaction Item Attribute"*
- *"a line attribute value must be plain text of 1 to 140 characters"*
- *"line_no must name a line of this sale"*
- *"a line attribute is returned twice for one line"*
- *"the attribute's own pattern is too complex to check a partner's value"*
- *"a line attribute value does not match its master's pattern"*

**When the record is saved** (Retail Remote App Key):

- *"The app name must be 1 to 80 of: a-z, 0-9, underscore."* · *"The key must be 1 to 40 of: a-z, 0-9,
  underscore."*
- *"The name ⟨app⟩ belongs to an app. Choose another app name."* (an installed app's name, or one kept
  for an iVendNext app)
- *"The label must be 1 to 40 characters."* · *"Choose at least one thing the key may return."*
- *"The address cannot be used."* followed by one of: *"It must be an HTTPS address of at most 500
  characters."* · *"It is not an address."* · *"It must start with https:// and name a host."* · *"It must
  not carry a user name, a password or a # part."* · *"It must not contain spaces or control characters."*
- *"The time to answer must be more than 0 and at most 10 seconds."*

**In POS Studio → Apps**, a key that cannot be switched on is listed with its reason: *"Its label is
missing or longer than 40 characters."* · *"An installed app already uses the name ⟨app⟩."* · *"The name
⟨app⟩ is kept for an iVendNext app."* · *"It is switched off on its record."* · *"The customer's consent to
send the sale details is not recorded."* · *"Its address is not an HTTPS address this till can call."* ·
*"Its address is inside a private network, which this site does not allow."* · *"Its time to answer must
be more than 0 and at most 10 seconds."* · *"It names a result this till does not know."*

## 5. Consent, and when your service is down

The System Manager's tick — or, for a key an app's package brings, the consent to that install — records who agreed,
when, for which address and for this list, word for word:

> What the till sends to this address at each press: sale_ref (the till's own id for the sale) · store ·
> pos_profile · company · currency · operator (the signed-in cashier's user id, personal data) · customer
> (the customer's id when one is on the sale, personal data) · lines (item_code, qty, uom and the line's
> own id for each item). No price, total, payment, serial or batch is sent.

Changing the address clears the consent, and so does a release that changes the list; the key cannot be
switched on again until someone ticks it again.

**Down:** there is no down answer to choose. A service that is down, slow or answers badly gets the
cashier's sentence from section 4, nothing is added, and the sale goes on. No retry, no queue.

## 6. Offline

Online only: the key is dimmed while the till is offline, and nothing is queued for later.

## 7. Money and limits

**No money touch.** No amount is sent and no answer kind carries one; a discount is never an answer (an
app that wants to give one creates an engine promotion or pricing rule).

Limits: label 40 · title 60 · body 280 · 1 to 20 Sale Attribute rows · 1 to 10 line rows · value 140 ·
500 lines sent · answer
64 KB · time to answer 3 seconds unless raised, at most 10. HTTPS only, the certificate checked against
your host name; a host that resolves to a private, loopback or link-local address is refused unless the
site sets `"mpos_remote_app_allow_private": 1` (a test bench, off by default).

## 8. Worked examples

**A loyalty tier check.** The key `loyalty_check` returns both kinds. Your service looks the customer up
by `customer`, and answers:

```json
{"message": {"title": "Gold member", "body": "120 points on this sale.", "level": "success"},
 "sale_attributes": [{"sale_attribute": "Loyalty Tier", "attribute_value": "Gold"}]}
```

The cashier confirms; the sale carries *Loyalty Tier: Gold*, and the invoice books it. Points are booked
by your own code when the sale is booked (an additive document hook, or the event feed), never from the
press.

**A courier booking number.** The key `book_courier` returns `sale_attributes` only. Your service books a
pickup keyed on `sale_ref` (a second press finds the booking and returns the same number) and answers
`{"sale_attributes": [{"sale_attribute": "Delivery Order", "attribute_value": "TB-88123"}]}`. Had it
answered a `message` too, the whole answer would be refused: the key did not declare one.

**A warranty number per handset.** The key `register_warranty` returns `line_attributes`. Your service
registers each handset in `context.lines` and answers
`{"line_attributes": [{"line_no": 1, "name": "Warranty ID", "value": "W-88213"}]}`. The cashier confirms;
the first line carries *Warranty ID: W-88213* and the invoice books it on that item's row.

## 9. Telling an AI assistant

> Build an HTTPS endpoint that answers an iVendNext POS remote till key, version 1. The contract is
> `remote_till_key.v1.schema.json` (`$defs/request` in, `$defs/answer` out); the samples under
> `samples/remote_till_key/` are known-good and known-bad answers (a line sample names the request's
> lines in `given.lines`). Verify `X-iVendNext-Signature`
> (base64 HMAC-SHA256 of `<timestamp>.<raw body>`) before parsing, refuse a timestamp more than 300
> seconds off, answer within 3 seconds, return only the kinds listed in `returns`, and key any side
> effect on `context.sale_ref`. Never return a price or discount.
