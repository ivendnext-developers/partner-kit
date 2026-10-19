# Receiving iVendNext webhooks safely — the recipe

![A covered phone sold at the till, and the warranty service's comment on the sale](../samples/s1_warranty/screenshots/s1_flow.gif)

*A phone sold at the till; seconds later the sample's warranty service, told by a signed webhook, has put its comment on the sale in Desk.*

> ⚠ **Since 2026-10-04 a webhook is the NUDGE, not the record.** To learn reliably what happened in a shop, read the **event feed** (`recipes/event_feed.md`): a queue you pull and mark done, so nothing is lost while you are down. Use a webhook only to be told to pull now (`event_feed.md` appendix A). This recipe stays for verifying a signed webhook — the nudge's signature is checked exactly as below.

This recipe is for an iVendNext Partner whose own server, in any language, must react when something happens in a shop — a sale is booked, stock moves. The sample to copy is `samples/s1_warranty/service/receiver.py` (verify, replay) and `service/app.py` (idempotent handling, reconciliation).

**When to use it:** your server receives webhooks from a shop, as a nudge to pull the event feed or on their own.

A webhook is a **doorbell, not a parcel**. Treat the call as "this sale changed", read the sale yourself over the API, and make every step safe to repeat. The five rules below follow from how iVendNext sends webhooks today.

## 1. Subscribe with a secret, and keep the payload thin

A shop's administrator (it needs the System Manager role) creates a **Webhook** for the record type and event. For a booked sale, that is *Sales Invoice* and *POS Invoice* on **Submit**, with:
- **Enable Security** on, and a long random **Webhook Secret** that only you and the shop know;
- **Request Structure: JSON**, with a body that names the record and when it changed, and nothing more:

```json
{"doctype": "{{ doc.doctype }}", "name": "{{ doc.name }}", "event": "on_submit",
 "modified": "{{ doc.modified }}", "company": "{{ doc.company }}"}
```

A thin body keeps the signature check simple (rule 2) and keeps customer data out of request logs. Everything else you read over the API, with your integration user's own permissions.

## 2. Verify the signature — over the raw body

Each call carries `X-Frappe-Webhook-Signature`: the **base64 of HMAC-SHA256(secret, body)**. Compute it over the **exact bytes you received**, and compare in constant time:

```python
expected = base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest())
ok = hmac.compare_digest(expected, request.headers["X-Frappe-Webhook-Signature"].encode())
```

Refuse anything else with `401`: a missing header, a wrong signature, a body changed after signing. Check the signature **before** parsing anything, and cap the body size (a thin body is a few hundred bytes).

⚠ **No `Content-Type` header is sent** unless the subscription adds one by hand. So read the raw body whatever the header says.

⚠ **Keep the body to plain JSON values.** The sender signs its payload serialised one way and sends it serialised a second way. For a body of plain JSON values, which is what rule 1's template produces, the two are byte-identical, and verifying over the raw body works. If you put a non-JSON value (a date object, a decimal) into a custom body, the two forms can differ. Then only a receiver that re-serialises exactly as the sender does would still verify.

## 3. Reject replays

Nothing time-bound is signed, so a captured call stays valid for ever. Keep a **seen-set** keyed on **record type + name + event + `modified`**. Answer a key you have already handled with `200`, and do nothing. Record the key only **after** you have handled the call; then a delivery that failed half-way is handled again on its retry.

## 4. Make the handling idempotent

The same sale can reach you more than once: a retry, a replay that slips past a lost seen-set, and the reconciliation pull (rule 5). So:
- keep your own record of the sales you have handled, and skip a handled one;
- before writing anything back into the shop (a Comment, say), check over the API whether **your** earlier write is already there. That way a crash between "wrote it" and "recorded it" can never write it twice;
- make your own writes keyed and unique (e.g. one warranty per serial number).

Answer within the webhook's **timeout** (our tests used 10 seconds). Slow work goes to your own queue. Answer `200` once the call is verified and recorded.

## 5. When your service is down — recover what never arrived with the reconciliation pull

iVendNext tries a delivery **three times within one background job** (a few seconds apart), writes a *Webhook Request Log* row per attempt, and then stops. There is no later retry. If your server is down for those few seconds, the event is lost. So run this pull on a schedule (nightly is enough for most partners) and after every restart of your service:

```
GET /api/resource/Sales Invoice          (and the same for POS Invoice, if you subscribe to till sales)
    ?fields=["name","modified"]
    &filters=[["docstatus","=",1],["modified",">=","<your watermark>"]]
    &order_by=modified asc&limit_page_length=200
```

Handle each sale idempotently (rule 4), then move your watermark to the newest `modified` you handled. Use `>=`, not `>`: two sales can share a timestamp, and rule 4 makes the overlap harmless. If one sale fails, stop there, so the watermark stays before it and the next pass retries it.

## What we would like to improve

Proposed to our product team: a signed timestamp (so a receiver can reject old calls without a seen-set), delivery that survives a receiver being down for longer than a few seconds, and self-service subscriptions that need no System Manager. Until then, rules 3 and 5 are not optional.

## Technical notes

- **The sample.** `samples/s1_warranty/service/receiver.py` and `service/app.py` are proven end to end on our test bench. The GIF is the sample's own walk (see `samples/s1_warranty/README.md` for its date, frames and pin).
- **Rule 2, `Content-Type`.** The signing code was re-read at framework `9c19f570`, the bench's pin.
- **Rule 2, plain JSON values.** ⚠ **Measured on our test bench.** The two serialisations were byte-identical for rule 1's template; our tests checked this on a real sale's delivery.
