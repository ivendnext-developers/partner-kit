<!-- Source: ivendnext/iVendNext_PWA docs/extending/event_feed.md @ 7d47d331a203, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Event feed

**Contract:** [`event_feed.v1.schema.json`](../extension_contracts/event_feed.v1.schema.json)
· samples: [`samples/event_feed/`](../extension_contracts/samples/event_feed/)
· code: `api/feed.py` (the three calls), `business_logic/feed.py` (every rule, the label table).

## 1. What it is and when it fires

Your app's own queue of what changed in the shop: a sale booked, a customer created, goods received. You
**pull** it — nothing is pushed at you — with your own API key, mark what you handled as done, and leave
what failed with a note. It is a queue, not a cursor: an event stays until you mark it done, so a change
a slow worker commits late is never skipped. **At least once**: be ready to see an event twice.

The engine writes one event per **document step** a change runs, per registered application that follows
that record type, after the change commits (a background job, so seconds later). So one change arrives as
**several events**: a booked sale writes `pos_invoice.on_update`, `sale.booked` and `pos_invoice.on_change`
(and `pos_invoice.after_insert` when it is inserted already submitted); a new customer writes
`customer.created`, `customer.updated` and `customer.on_change`. Act on the labels you need and mark the
rest done. A change saved by your own application's user
writes no event for you: you never receive an echo of your own writes.

**Setting it up.** In iVendNext Desk a **Registered Application** record names your application, the
user whose API key you call with (`application_user`), and the record types you follow (its event rows).
One user, one registration: a key registered to two applications is answered *"not registered"*.

Any record type can be followed, the till's own included: a registration that follows **Retail Override
Request** receives each manager approval as `retail_override_request.on_update` (requested, approved,
denied, used by a sale), with no code — for a partner that reports on approvals. The application's user
needs read access on Retail Override Request, which the shop grants.

## 2. Version

Version 1: the three calls and the label table below. A new label may be added in version 1; an existing
label never changes meaning.

## 3. What you send, and what comes back

Each call is a `POST` to `/api/method/ivendnext_mpos.api.feed.<call>` with your API key
(`Authorization: token <api_key>:<api_secret>`). The framework wraps every answer as
`{"message": <answer>}`.

| Call | You send | You get |
|---|---|---|
| `events` | `limit` (1 to 500, 100 when left out) · `page` (left out to start from the oldest) | `{"events": [...], "page": "<token>" or null, "backlog": <how many not done>}` |
| `done` | `ids`: 1 to 500 of your events | `{"done": <count>}` |
| `failed` | `id` and `error` (your note, 1 to 1000 characters) | `{"ok": true}` |

One event:

```json
{"id": "a1b2c3d4e5", "event": "sale.booked", "doc_type": "POS Invoice", "doc_name": "ACC-PSINV-2026-00042",
 "raw_event": "on_submit", "at": "2026-10-07T14:02:11"}
```

- `events` returns your events **not yet done**, oldest first. Without `page` a call always starts at the
  oldest one, so an event you neither mark done nor failed comes back. `page` only pages through the
  backlog of the call that gave it out.
- The event carries no payload. Read the record through the API, with your key's own rights.
- `failed` leaves the event undone, at the head of the queue, carrying your note for a support call;
  page past your failures.

**The label table** (`feed.LABELS`):

| Record type and raw event | `event` |
|---|---|
| POS Invoice · on_submit | `sale.booked`, or `return.booked` for a return |
| POS Invoice · on_cancel | `sale.cancelled` |
| Sales Invoice · on_submit / on_cancel | `invoice.booked` / `invoice.cancelled` |
| Sales Order · on_submit | `order.booked` |
| Customer · after_insert / on_update | `customer.created` / `customer.updated` |
| Item · after_insert / on_update | `item.created` / `item.updated` |
| Stock Entry · on_submit | `stock.moved` |
| Purchase Receipt · on_submit | `goods.received` |
| Stock Reconciliation · on_submit | `stock.counted` |
| anything else | `<record type in lower case, spaces as _>.<raw event>` |
| a record deleted since the event was written | `<record type in lower case, spaces as _>.deleted` (`pos_invoice.deleted`); a virtual record type's reads by its raw event |

⚠ **Two things that book sales twice if missed.** The day's roll-up Sales Invoices (`is_consolidated = 1`)
produce events too and read `invoice.booked`: if you follow both POS Invoice and Sales Invoice, skip the
roll-ups. And `at` is when the change committed: an offline sale's events appear when the till drains it,
which can be hours after the customer left.

## 4. Every refusal, in the product's words

| When | Words |
|---|---|
| Your key has no registration, or more than one | *"This key is not registered for events."* — nothing else is read |
| `limit` is not a whole number from 1 to 500 | *"limit must be a whole number from 1 to 500."* |
| `page` is not one the feed gave out | *"page is not one this feed gave out."* |
| `ids` names no event, or more than 500 | *"ids must name 1 to 500 events."* |
| One id in `done` or `failed` is not yours (another application's, or unknown) | *"One of these events is not yours."* — the whole call is refused; nothing is marked |
| `error` is blank or longer than 1000 characters | *"error must be 1 to 1000 characters."* |

And on the registration itself, for anyone who does not administer the feed:
*"Only the feed's administrator can change this application's user."* ·
*"This user already receives another application's events."* ·
*"Events from an earlier registration of this name are still kept."*

Through the framework's own permission layer (REST, Desk), a key reads and changes only its own
application's events.

## 5. Consent, and when your service is down

No consent text is recorded: nothing leaves the shop unasked. The shop's decision is the registration —
which user, which record types. Deleting the registration, or unticking a record type, stops your feed
visibly (*"not registered"*, or no new events).

**Down:** you pull, so a service that is down simply stops pulling. Your events wait, undone, for as long
as you are away. Events marked done are purged by the engine after 30 days.

## 6. Offline

The till's offline sales reach the feed when the till drains them, with `at` the time they committed. The
feed itself is a server call; it does not exist on the till.

## 7. Money and limits

**No money touch.** An event names a record and what happened to it; the amounts are on the record, read
with your key's own rights.

Limits: 1 to 500 events a call (100 by default) · 1 to 500 ids to `done` · a note of 1 to 1000 characters.

## 8. Worked examples

**An accounting sync.** Every five minutes: call `events` with `limit: 200`; for each `sale.booked` and
`return.booked`, read the POS Invoice and post it to your ledger, keyed on `doc_name` (an event may come
twice: skip an `id` you have handled); call `done` with the ids you posted; for one you could not post, call `failed` with
`"The customer has no tax id in our system yet."`. While `page` is not null, call again with it.

**A loyalty app that follows customers.** Follow Customer and POS Invoice. `customer.created` creates
the member on your side; `sale.booked` adds points after reading the invoice; `sale.cancelled` takes them
back. The `customer.updated`, `customer.on_change`, `pos_invoice.on_update` and `pos_invoice.on_change`
events that arrive beside them are marked done unread. Your own writes back to the Customer record, saved
by your application's user, write no event.

## 9. Telling an AI assistant

> Build a worker for the iVendNext POS event feed, version 1. The contract is `event_feed.v1.schema.json`:
> `events_request` / `events_answer`, `done_request` / `done_answer`, `failed_request` / `failed_answer`;
> the answers arrive inside `{"message": …}`. Pull with `events`, skip an event `id` you have already
> handled (delivery is at least once), make the work for a record idempotent on `doc_type` + `doc_name` +
> `event`, act on the labels you need (one change writes several events — mark the rest done), mark
> handled events with `done`, record a failure
> with `failed`, and follow `page` until it is null. Skip consolidated Sales Invoices if you also follow
> POS Invoice.
