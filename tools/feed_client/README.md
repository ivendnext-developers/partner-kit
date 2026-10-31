# The event-feed client — read a retailer's events reliably

A small client your service uses to read a retailer's events: it handles each event once, notes the ones that failed, and reconciles every night. It is one file, `feed_client.py`, Python standard library only — copy it into your own service. **The recipe:** `recipes/event_feed.md`.

**When to use it:** your service must act on what happens in a retailer's iVendNext and cannot afford to miss or repeat an event.

## Steps

1. Copy `feed_client.py` into your service.
2. Run its tests:

```bash
python3 -m unittest discover -s tools/feed_client/tests -p 'test_*.py'
```

| File | What |
|---|---|
| `feed_client.py` | the client: two transports (the engine's feed; the event feed's door), the seen-set, `failed` notes, the nightly `reconcile` (it lists a sale handled before a lost working folder as `unknown`, not `missing`); a CLI (`run`, `backlog`, `reconcile`, `dump`) |
| `tests/test_client.py` | laptop tests (32): every event once over small pages, a crash before `done`, a failed event, the labels, reconciliation, a lost working folder (handled sales read `unknown`, a skipped one `missing`), the two label tables agree, no redirect followed, the door asked with POST (its stand-in refuses a GET), and one reader for the parts of an app (`Handoff`: read once, handed by record type, done after every part, a waiting event never holding back a newer one, the lasting record) |

Both transports work on a retailer's iVendNext today. The `door` transport reads the event feed's door, which is live: it is scoped to your own application, and each of its three calls is a POST. The same POST call was read on a test site on 2026-10-09. The `engine` transport reads the older feed and is not scoped; use it only where you are the retailer's one consumer.

## Technical notes

On our test bench the client also passed the exit check — two applications, the client stopped while sales are booked, a crash, a restart — on both transports. The `door` transport ran against our stand-in for the door, which follows its published contract. On a real site the door's POST call was read on 2026-10-09; the crash-and-restart exit check has **not** been run against the live door.

## One feed, several readers in one app

An app made from several samples that each read the feed (`tools/manifest/start.py s22_customer_loyalty s25_gift_on_spend`)
has one registration and reads it once. Its service puts one `Handoff` where every part's `poll` finds it, then on the
schedule `feed` runs each reading part's own pass: the first part to poll a shop reads its not-done events, and each part
is handed the events of the record types its own sample registered. Each part's handled events are recorded in the
seen-list as `<part>|<event id>`, in the same transaction as the part's own writes, so a part that already handled an
event is never run again for it. An event is marked done only when every part that wants it has handled it; a part that
fails leaves its note on the event, which waits for the next run. An event left waiting is also written, with the parts
that handled it, to one record per shop in the app's shops store (`handoff|…`), because a new copy of a function starts
with an empty working folder: a part that handled the event is not run again there either. Every not-done event is read
each run, so an event waiting for a part never holds back a newer one. Nothing changes for a sample that runs alone.
