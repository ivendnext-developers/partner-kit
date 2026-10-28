# Keep a customer's own system in step with iVendNext — the system-sync recipe

This recipe keeps a retailer's own **ERP, order system or warehouse system**, running outside our cloud, in step with iVendNext. Items, prices and stock go **out** to iVendNext; sales and returns come **in** to the ERP; and nothing is lost or doubled. It is for the IT team of a large licensed customer, or an iVendNext Partner working for them. The sample to copy is `samples/s7_system_sync/`: `erp.py` is a stand-in ERP and `sync.py` is the sync (Python, standard library only — any language can do the same). It is built on the event-feed client (`tools/feed_client/`, `recipes/event_feed.md`).

**When to use it:** an outside system owns items, prices or stock, and must also hold every sale and return iVendNext books.

**How the data travels, hop by hop:** [guide chapter 1c](../guide/01c_how_the_data_travels.md) traces two links to outside systems (a chain's own loyalty system, and a phone retailer's telecom company): every endpoint, what data crosses it, what signs it, where each chain's account is kept, and two chains in the same second.

## The picture

```
 ERP ──(numbered changes)──► sync OUT ──► items · prices · Stock Entries ──► the shop
 ERP ◄── orders · returns ◄── sync IN ◄── the event feed (sale.booked, return.booked, sale.cancelled) ◄── the shop
                              sync keeps: a CURSOR · an IDENTITY MAP · the feed's SEEN-SET        nightly RECONCILE reads both sides
```

## 1. Register the sync (the retailer does this once)
The retailer creates a **Registered Application** for the sync, following **POS Invoice** (`recipes/event_feed.md` §1), and an integration user with its own API key. Give that user this grant:
- the feed's log: read + write (to mark events done);
- POS Invoice: read;
- Item and Item Price: create + write;
- Stock Entry: create + write + submit;
- Bin and Warehouse: read.

A retailer that wants to grant less must say which call it refuses. ⚠ **Today the feed grant cannot be scoped to one application** (`recipes/event_feed.md` §3). Use it where the sync is the retailer's one consumer. The event feed's door, which is live, removes the right on the log.

## 2. OUT — what the ERP changed goes to iVendNext
The ERP numbers every change it makes that iVendNext must learn: an item, a price, a stock movement. The sync's **cursor** is the last number done. The sync takes each change, oldest first:

| Change | What the sync writes | How a retry finds its own work |
|---|---|---|
| an item | an **Item** (code = the ERP id behind a prefix; the identity map is the authority, the prefix a convention) — created, renamed, or **disabled** when the ERP deleted it. **Never deleted**: a booked sale points at its item | the item exists under that code |
| a price | an **Item Price** in the named price list (create, or change the rate) | the row for item + list |
| a stock movement | a **Stock Entry the engine books** (Material Receipt for goods in, Material Issue for goods out). **The sample never sets a quantity** | a key in the entry's *remarks* — `PP-SYNC <the ERP's own id> mv:<movement number>` — looked up before every write. ⚠ **The ERP's own id is part of the key.** A key of the movement number alone can find an *earlier system's* entry with the same number, and then no stock is written at all |

## When your service is down: why a crash is harmless
The cursor moves only *after* a change is fully written. A crash between the write to iVendNext and the cursor leaves the cursor one behind. The restart repeats that change and **finds it by its key**, so nothing is written twice.

The run stops at the first failure, and the cursor stays. An item comes before its price and its stock. A price or a stock movement for an item **the ERP has since deleted** is skipped (its iVendNext item is disabled, or was never made). Otherwise an item added and deleted between two passes would stall every change after it.

## 3. IN — what iVendNext booked comes to the ERP, once each
The sync runs the feed client's loop: pull the oldest events not yet done, act on them, mark them done. Its handler does this:
- for `sale.booked` and `return.booked`, it **reads the invoice over the API** and records it in the ERP;
- for `sale.cancelled`, it marks the ERP's order cancelled;
- everything else the feed names is recorded as seen and marked done.

Rules that keep it exact:
- **The ERP write is keyed on the retailer's invoice number** (a unique column). A second delivery — a replay after a crash, a repeated event — writes nothing and returns the same ERP id.
- **The identity map** links ERP item ↔ item code, and ERP order ↔ invoice. Order rows are written in the feed client's own transaction; item rows by the OUT pass.
- **A return links to its sale** through `return_against`. If the sale is not in the ERP (it predates the sync), the return is stored unlinked, and the reconciliation names it.
- **The ERP's own stock** is what it moved in, less what the retailer sold. A return carries a negative quantity, so it adds back. A cancelled sale is not a sale.

## 4. The nightly reconciliation — it reports, it never fixes
```bash
SYNC_KEY=… SYNC_SECRET=… python3 samples/s7_system_sync/sync.py reconcile --base … --app … --erp … --state … --warehouse … --company … --since "2026-10-04 00:00:00"
```
It is read-only on both sides. It lists, **by name**:
- a sale or return booked in the retailer's iVendNext and not in the ERP;
- one in the ERP and not booked in the retailer's iVendNext;
- a total that differs (both figures);
- a return not linked to its sale;
- an ERP item the sync **never pushed**;
- each day's counts and totals on both sides;
- stock on hand on both sides;
- an item deleted in the ERP and still enabled in the retailer's iVendNext;
- a price that differs.

A sale whose event is **still in the queue** (late, or failed and waiting) is listed apart, not as a difference. **A difference in money is a person's decision**: the report never "fixes" it. Run it after a pass that ended with backlog 0.

## 5. Run it
```bash
SYNC_KEY=… SYNC_SECRET=… python3 samples/s7_system_sync/sync.py run --base https://shop.example --app "My Sync" --erp erp.sqlite --state sync.sqlite \
    --warehouse "Store - X" --company "My Company" --watch 30
```
Keys come from the environment, never the command line. No redirect is followed with the key. One `run` pass pushes OUT, then collects IN.

## When the till is offline
**Offline sales arrive late.** Their events appear when the till drains. At the day's close, till sales are merged into a back-office Sales Invoice. The sync follows **POS Invoice** only, so it never counts a sale twice.

## Limits
- **One instance per ERP per retailer.** The sync takes no lock. Two passes at once (the `--watch` service and a manual `out`) can both find a movement's key absent and book it twice. Run one.
- **One warehouse, one company, items in Nos, selling price lists only.** More stores = one sync per warehouse, or a map from the ERP's location to a warehouse (not built).
- **The sale's lines are the retailer's.** The ERP records item, quantity and amount from the invoice. It does not recompute tax or discount (a price is never written onto a sale).
- **The feed grant is not scoped today** (§1).
- The sync is sequential. It has been tried with tens of invoices; for a bigger retailer, measure first (Technical notes).
- A price change, an item rename and a second price list have not yet been tried against a real site (Technical notes).

## Technical notes

The recipe's reference implementation is **proven** on our test bench.

### What was proven where
- **The grant** in §1 is the one the sync works with, **measured on the bench**.
- **Item rename** is laptop-tested only. **Price:** create on the bench; change the rate — laptop-tested only, the same kind of call the roll-out got wrong once.
- **The stock key** (measured: a key of the movement number alone found an *earlier system's* entry 1 and wrote no stock at all).
- **A crash in OUT.** Proven: crashed after the second of four stock movements, restarted: **8 movements, 8 Stock Entries, no key twice; stock on hand equal on both sides**.
- **A crash in IN.** Proven: killed after 15 handled events and before marking them done, restarted — **all four sales in the ERP exactly once**, the replayed events skipped as seen; a sale and its return — **the return arrived once, linked to its sale, and the units went back into stock**.
- **The reconciliation. Proven (canaries — a check that cannot fail proves nothing):** a sale deleted from the ERP is named, with the day it breaks · a total one unit off is named with both figures · stock the ERP moved and the sync has not pushed is named with both figures, and clean again after the push · the report changed neither file nor a single Stock Entry.

### With the money kit
The sync ran as a service **while the money kit rang** the retailer's baskets, plus two baskets of the sync's own items (dedicated rungs in the kit's set): **GREEN, 69 of 69 matched** (the 67 shared baskets and the two extra ones), 33 with a discount, no POS day left open. The service itself handled **414 events in 27 passes, from the kit's start until the service was stopped**, the final drain found nothing left, and the reconciliation afterwards was clean with **69 sales on each side**. Items, prices and stock written by the sync belong to its own synthetic items only — **never to a kit item** — so the kit's recorded totals are untouched.

### Bounds, stated
- **Not run on the bench:** a price change, an item rename, a second price list (laptop tests only); the identity map's reverse lookup by site name has no unique constraint behind it; the extra baskets' merged back-office invoice was **not checked** (one differs by 0.01 from its sale — the platform's own merge re-rounding).
- **Volume:** tens of invoices on the bench (the kit's run is the largest: 69 sales, 414 events through the service); the sync is sequential. The scale-profile kit (`tools/scale_profile/`) is where a bigger shape is measured.
- **The feed grant is not scoped today** (§1); the door that fixes it is live (the event feed recipe, §3); its crash-and-restart test ran only against the programme's stand-in.
- Not exercised: a sale of an item the sync did not create (its lines are recorded unmapped, with no stock effect — covered by the kit's run); a stock count (Stock Reconciliation) made in the retailer's iVendNext; an ERP that changes an item's group; a negative stock the engine refuses on a Material Issue (the run stops and says so).
