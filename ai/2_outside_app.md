# An outside app: your service on the API and the event feed (way in 2)

**Goal.** A service that runs on your own server (any language) and reads and writes a retailer's records, or reacts to what happens in the retailer's iVendNext: a booked sale, a changed customer, a stock movement.

**Read.** [guide/05_outside_apps_and_event_feed.md](../guide/05_outside_apps_and_event_feed.md) · [recipes/connected_app.md](../recipes/connected_app.md) · [recipes/event_feed.md](../recipes/event_feed.md) · [recipes/integration_user.md](../recipes/integration_user.md) · [recipes/webhook_receiver.md](../recipes/webhook_receiver.md) · [api/README.md](../api/README.md) and `api/openapi.yaml`.

**Samples to copy.**
- React to every sale and write a comment on it: [samples/s1_warranty/](../samples/s1_warranty/) (its `service/`).
- Read the feed and record what breaks a rule: [samples/s3_price_audit/](../samples/s3_price_audit/).
- Keep a customer's own system in step: [samples/s7_system_sync/](../samples/s7_system_sync/).
- Send sales to a warehouse file, picking up where it stopped: [samples/s9_bi_feed/](../samples/s9_bi_feed/).
- The feed client to copy into your service: [tools/feed_client/](../tools/feed_client/).

**Steps.**
1. Decide what the service reacts to. Prefer the event feed (it catches up after downtime and reconciles) over a bare webhook; a webhook carries only a thin body and the service reads the record itself.
2. The service reads as its own user with only the rights it needs. If it follows an event feed (step 1), the retailer's install makes that user, `<app>@integration.invalid`, and its role: the retailer gives the role the reads, and you make no user. For a service with no feed, give it its own **integration user** (the recipe says how). The key comes from the environment; never from a file you write.
3. Write the logic as a **pure core** that imports nothing from iVendNext, with unit tests that need no retailer. Copy the shape of the sample's core and of its tests (S1, S3, S7 and S9 each have a `tests` folder; S3's core is `outside/core.py`); keep their shape, not their names.
4. Add the thin part: the feed client or the signed-webhook check, and the API calls you need. Take each call from `api/openapi.yaml`, or from the `/api/method/ivendnext_mpos.api.v1.<name>` names `api/README.md` lists; do not invent a call.
5. Make it safe to run twice: handle each event once, note failures, reconcile every night (the feed client does this; use it).
6. Read-only calls may run on a sandbox with the person's key. Any call that writes goes to the person's own sandbox and needs their yes; show the request first. A write to any other retailer is never yours to make.

**Check.** `python3 -m unittest discover -s <your tests folder>` for your core, and `python3 tools/check/check.py <project folder>` for anything it recognises (app code with a `hooks.py`, a manifest, sample answers). A service that sits outside the retailer's iVendNext has no `hooks.py`, so the check prints `NOTHING FOUND` and exits 2 for it. That is not a verdict: say so, and name the tests you ran instead.

**Done looks like.** The core's tests pass; the service handles a sample event twice with one effect; it says what it does when iVendNext is unreachable and when it is slow; no key is in any file; the person has read the first write request before it was sent.

**Never.** Put your service's code inside the retailer's iVendNext, hook a record's save, or change a sale's price or total. If the cashier must see an answer during the sale, that is a till key (way 3), not this.
