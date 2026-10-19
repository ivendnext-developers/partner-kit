# 12. Handheld and our other apps

**For:** a builder whose customer uses Handheld for receiving, transfers and counts, and wants an outside app to react to what Handheld books.
**Reference implementation:** the event-feed loop of chapter 5 ([`../tools/feed_client/`](../tools/feed_client/)) and the system-sync sample of chapter 10 ([`../samples/s7_system_sync/`](../samples/s7_system_sync/)), which reads the feed the same way. Neither handles Handheld's documents yet: you add a handler for the labels below.

## The short answer

- **Handheld has no extension point of its own today.** There is nothing to install into it, no key for it to call, and no screen of yours inside it. Handheld does not print labels: it adds them to the back office's print list (an *Item Label Printing* draft), which a desktop utility prints, and it does not take the till's label layout. The scan source (chapter 9) is read by the till's scan, not by Handheld's.
- **What Handheld books is a normal stock document in the shop.** A count posts a Stock Reconciliation; receiving and transfers post the matching standard stock documents. So an outside app reads and reacts to them exactly as it reads anything else in the shop: over the record API and the event feed (chapter 5).
- **Handheld books online only in its first release.** Receiving, transfers and counts need a connection. Nothing is queued on the device to be sent later.

## When to use it

When a customer says "when the warehouse receives goods, our system must know", "when a count is posted, our ERP must update" or "when stock moves between stores, tell us". The need is met by your own service following the shop's feed, not by anything in Handheld.

If the need is to **change what a Handheld screen does or shows**, that is product work on Handheld: there is no door for it (below). Say so in the request form (chapter 9), naming the compositions you tried and why each falls short.

## Steps: react to what Handheld books

1. **The shop registers your application** on the event feed and names the record types you follow (chapter 5): the stock documents you care about. For receiving, transfers and counts that is a Purchase Receipt, a Stock Entry and a Stock Reconciliation.
2. **Pull the feed with the reference client** (chapter 5, step 7). Each change arrives as events that name the record and what happened to it:

   | The shop's document | Event label |
   |---|---|
   | Purchase Receipt submitted | `goods.received` |
   | Stock Entry submitted | `stock.moved` |
   | Stock Reconciliation submitted | `stock.counted` |

   A document type with no row in the label table arrives as its type in lower case, then the raw event (a Delivery Note submitted is `delivery_note.on_submit`).

   ⚠ **Read the document before you act on the label.** A return to a supplier is also a Purchase Receipt (marked as a return) and arrives as `goods.received`: a handler that adds stock on `goods.received` would book it as stock coming in, so check `is_return`. A receipt with no order, an issue and a transfer are all Stock Entries (`stock.moved`): read the entry's type. The kit has not yet seen Handheld book a document: which document each Handheld screen books is taken from Handheld's own design, not from a test.
3. **Read the document over the API** when you need its lines. An event carries no content, and the document is read with your own key's rights.
4. **Act once.** An event can arrive twice, and one change arrives as several events: act on the label you need and mark the rest done. Key your own write on the document's name, so a second delivery changes nothing (chapter 5).
5. **For a count, expect no approval inside Handheld.** Handheld's count has blind counting, serial and batch capture, a variance review and a head-office worklist, and then posts. There is **no in-app approval step**: if the customer needs a manager to approve a count, that is a rule in your own service or a workflow in the shop (chapter 4), applied before or after, not a button in Handheld.

## What is refused, and why

- **Your code inside Handheld, or a key in it.** There is no extension point and no app key. Everything is done from outside, through the shop.
- **Writing stock from your side as a quantity.** Book a movement the shop books; never set a quantity (chapter 10).
- **An approval step inside Handheld.** A count has none, and a partner cannot add one: the approval lives outside it (step 5).

## When your service is down, and when the till is offline

- **Your service is down:** your events wait in your queue and you catch up when you are back (chapter 5). Handheld is not affected: it books to the shop either way.
- **Handheld is offline:** it does not book. Receiving, transfers and counts need a connection in its first release, so nothing reaches the shop or your feed from a device with no network.
- **The till is offline:** unrelated to Handheld; a till's sales arrive when it syncs (chapter 5).

## Technical notes

### What the kit has proven

- **The feed itself,** with real events from the test shop, collected once and none from another application (chapter 5; on the engine transport only because the client filters to its own rows).

### What it has not

- **No Handheld document was booked in any kit test.** Handheld is not installed on the programme's test shop. Which standard document each Handheld screen books was read from Handheld's own count code and scoping, not run.
- **A sample that reacts to a stock document.** The system-sync sample handles sales and returns only; a stock-document handler is yours to write.
- **Handheld offline,** because it has no offline writes yet.

### Sources

- **Sources.** The event labels are the event feed page's label table in the extension-point library (POS app, 2026-10-07). Handheld has no extension point and no app key: read from its code at the stamped commit in the programme's capability map (`get_hooks` registers nothing). The online-only first release and the count's behaviour (single pass with variance review, blind count, serial and batch capture, head-office worklist, posts a Stock Reconciliation, no in-app approval step) are from the same map and Handheld's own count code.
- **Why the feed's grant matters.** Following Purchase Receipt, Stock Entry and Stock Reconciliation needs read on those whole record types: on the engine feed an unreadable document is labelled `….deleted` (chapter 5, step 7).

## See also

[5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [9. The extension points](09_points_and_requests.md) · [10. Integrations](10_integrations.md) · [16. Possible, not possible, limits](16_possible_not_possible.md)
