# The event-feed client — read a shop's events reliably

A small client your service uses to read a shop's events: it handles each event once, notes the ones that failed, and reconciles every night. It is one file, `feed_client.py`, Python standard library only — copy it into your own service. **The recipe:** `recipes/event_feed.md`.

**When to use it:** your service must act on what happens in a shop and cannot afford to miss or repeat an event.

## Steps

1. Copy `feed_client.py` into your service.
2. Run its tests:

```bash
python3 -m unittest discover -s tools/feed_client/tests -p 'test_*.py'
```

| File | What |
|---|---|
| `feed_client.py` | the client: two transports (the engine's feed; the event feed's door), the seen-set, `failed` notes, the nightly `reconcile` (it lists a sale handled before a lost working folder as `unknown`, not `missing`); a CLI (`run`, `backlog`, `reconcile`, `dump`) |
| `tests/test_client.py` | laptop tests (21): every event once over small pages, a crash before `done`, a failed event, the labels, reconciliation, a lost working folder (handled sales read `unknown`, a skipped one `missing`), the two label tables agree, no redirect followed, the door asked with POST (its stand-in refuses a GET) |

Both transports work on a shop today. The `door` transport reads the event feed's door, which is live: it is scoped to your own application, and each of its three calls is a POST. The same POST call was read on a test shop on 2026-10-09. The `engine` transport reads the older feed and is not scoped; use it only where you are the shop's one consumer.

## Technical notes

On our test bench the client also passed the exit check — two applications, the client stopped while sales are booked, a crash, a restart — on both transports. The `door` transport ran against our stand-in for the door, which follows its published contract. On a real shop the door's POST call was read on 2026-10-09; the crash-and-restart exit check has **not** been run against the live door.
