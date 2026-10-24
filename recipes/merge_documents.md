# Merge several documents into one, from a Desk list — the recipe

A retailer counts stock in parts — one count per aisle, per shift or per person — and wants **one** count to check and submit. This recipe builds a **Desk button on a list**: the user ticks the draft documents, presses the button, and your service writes **one new draft** that holds them all. The sources are never changed. The example is stock counts (*Stock Reconciliation*); the same shape merges any draft documents of one type. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who has read [the Desk action recipe](desk_action.md).

**Reference implementation:** `samples/s28_merge_and_history/` — *Merge counts* (its other door is a partner page).

**When to use it.** A person must check the merged document before it counts. Nothing in the retailer's settings merges counts: the count form only fetches items from a warehouse.

## Steps

1. **Declare the button on the list, for drafts only.** `placement` `list`, `on_draft` 1, `on_submitted` 0, roles of your own prefix, and a confirm sentence that says what will happen. Send only `name`: your service reads each record itself.

   ```json
   "desk_actions": [{"record_type": "Stock Reconciliation", "label": "Merge counts", "placement": "list",
                     "service": "merge", "roles": ["PP MHS Counts"], "on_draft": 1, "on_submitted": 0,
                     "send_fields": "name",
                     "confirm_text": "Merge the ticked draft counts into one new draft? The ticked counts are not changed; each gets a comment."}]
   ```

   iVendNext then refuses a submitted or cancelled record itself, in its words — *Merge counts does not run on ⟨name⟩ in this state.* — and never calls you.
2. **Add a field for the press key** on the document (`custom_fields`, a `Data` field starting with your prefix). The new draft carries the press's `idempotency_key` there.
3. **Check the press, then look for the key.** Verify the signature ([the Desk action recipe](desk_action.md), step 3). If a document of that type already carries this key, the press is a retry from the same dialog: answer with that draft and write nothing new (add only a missing comment).
4. **Re-read each ticked record** over `/api/resource/⟨type⟩/⟨name⟩` and refuse the whole press, with a warning message and no next step, when one is not a draft, when they differ in company or purpose, when a row cannot be merged (serial numbers, or its batch or serials kept in a bundle), or when only one is ticked. Never trust the list's copy: a record may have been submitted since.
5. **Merge the rows.** One row per item, warehouse and batch. The quantity: added, or the latest document's — the retailer's choice, read from your settings record. The rate: the latest document's that has one (a row counted at zero stores a rate of 0). "Latest" is the posting date and time; ⚠ iVendNext sends a time such as `9:00:00` without a leading zero, so compare times as numbers, never as text. Add quantities as decimals. Drop a row with no item or no warehouse; keep a counted zero.
6. **Write one new draft** (`docstatus` 0) with the key on it, then a comment on each source (`/api/resource/Comment`, `comment_type` *Comment*, `merged into ⟨new name⟩`). Never edit or delete a source.
7. **Answer** with a message and `open_record` on the new draft. Desk opens it.
8. **Stay inside the time.** Desk waits at most 10 seconds (declare `timeout_seconds` 10). Each record API call is a round trip: read the ticked records and the settings side by side, and on a fresh merge write the comments side by side without looking for them first. Run the service near the retailer's iVendNext.

## The settings

One record of your type `⟨PREFIX⟩ Settings`, named `Default`: the rule for the same item in the same warehouse (*Sum* or *Last*). S28's record also holds the number of sales its page shows.

## Bounds

- The sources stay drafts: tell the user to cancel or delete them, or the stock is counted twice.
- The new draft keeps the latest source's posting date and time.
- A handful of records per press: the list allows 100, but each is read and commented inside Desk's 10 seconds (two were measured).
- With create and write on the document, the service's key can change any draft of that type: give its role to the app's user alone.
- A timeout says *did not answer in time. Check the record before you try again.*; the draft may exist, and the retry from the same dialog finds it by its key — unless iVendNext saved it after your service stopped waiting for its own call, when a retry at that moment can write a second draft: look for one.

## What was proven where

On a sandbox site, 2026-10-16 (POS 2.0.0.648), pressed through the server call Desk makes, on the sample's first build (the review's changes after it ran on the laptop): two draft counts merged into one draft (12 + 7 = 19, at the 10:30 count's rate), *Last* kept 7, a retry after a timeout wrote no second draft, a submitted count was refused by iVendNext, an opening-stock count beside a count and a single count were refused by the service; the sources unchanged. The button and its dialog in Desk's own screen were not driven. Details: `samples/s28_merge_and_history/README.md`.

## Tell the customer

Tick the draft counts and press **Merge counts**: one new draft count holds them all, for a person to check and submit. The ticked counts are left as they were, each with a note; cancel them once the merged one is submitted.
