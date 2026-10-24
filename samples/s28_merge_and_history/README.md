# S28 — Merge counts, and a customer's history on the till

## What the retailer does

One small app, two doors, one settings record.

**Merge counts (a Desk button).** A stock user ticks several **draft** stock counts on the *Stock Reconciliation* list and presses **Merge counts**. One **new draft** count appears, holding every item of the ticked counts; a person checks it and submits it. The ticked counts are never changed: each gets a comment, *merged into ⟨new count⟩*.

**Customer history (a partner page).** A cashier presses a key on the till with a customer on the sale, or a back-office user opens the page for a customer in Desk, and sees that customer's last sales: the date, the store, **who served**, the sale's discount and **each line's discount**.

| What happens | When |
|---|---|
| One new draft count: one row per item, warehouse and batch | two or more draft counts of one company and one purpose are ticked |
| The quantities are added | the settings say *Sum* (the default) |
| The quantity of the latest count is kept | the settings say *Last* (latest by posting date and time) |
| The valuation rate of the latest count that has one (a row counted at zero stores none), and the latest count's posting date and time | always |
| *Merge counts does not run on ⟨count⟩ in this state.* (iVendNext's words; the app is not called) | a submitted or cancelled count is ticked |
| *Nothing merged*, with the reason | one count only, two companies, two purposes (opening stock and a count), or a row with serial numbers or with its batch or serials in a bundle |
| The same new draft again, and no second one | the press is retried from the same dialog |
| The customer's last sales, newest first | the page opens for a customer |
| *No customer on this sale* | the till's sale has no customer |
| *No sales yet* | the customer has no submitted sale |

**Bounds, said plainly.**
- **The ticked counts stay drafts.** Cancel or delete them after the merge, or the stock is counted twice when they are submitted.
- **The new draft keeps the latest count's posting date and time.** Change them before submitting if the merged count should post today.
- **A row is one item in one warehouse and one batch.** A blank row (no item or no warehouse) is dropped; a counted zero is kept. A row with serial numbers, or with its batch or serials kept in a bundle rather than in the row, refuses the merge: merge those counts by hand.
- **A handful of counts per press.** The list allows 100, but every count is read and commented over the network inside Desk's 10 seconds: two counts were measured, many were not.
- **Desk waits 10 seconds at most for the merge.** On a sandbox in the US with the service on a laptop in India, a merge of two counts answered in 5.3 to 5.7 seconds; before its reads were made side by side it took 8 to 10, and twice ran out of time. Run the service near the retailer's iVendNext. If Desk says *did not answer in time*, the draft may already exist: press again from the same dialog and the app finds it.
- **A till whose profile puts a default walk-in customer on every sale** opens the page for that customer: the cashier sees the walk-in's sales, not *No customer on this sale*.
- **The page reads till sales and Desk sales.** *POS Invoice* and *Sales Invoice*, submitted only; a day's roll-up invoice (a consolidated *Sales Invoice*) repeats the till's sales and is skipped.
- **Who served is the user who made the sale**, by full name. The built-in Administrator's name is not readable by the app's key, so it shows as *Administrator*.
- **A line's discount is what it took off**: the discount per unit times the quantity, as the sale stored it. A line that stored a percentage but took nothing off shows *no discount* (seen on the sandbox).
- **How many sales:** the settings' number, 10 by default, at most 50.
- **Online only**, as every partner page. On the till the key needs an item on the sale and the customer on it. The page answers nothing to the sale: it only shows.
- **The page's context is used once.** Reopening the same address says *this page was already opened; open it again from the shop*. The used contexts are kept in memory: a restart forgets them (keep them in a database in production).
- **With these rights the app's key can change any draft count**, and read every sale and every user's full name. Give its role to the app's user alone. Anyone with **PP MHS History** sees, through the page, the sales the app's key can read, in every store and company, whatever their own rights. A retailer that uses one door only gives the app's role only that door's rights (the counts and comments for the merge; the sales and users for the page).
- **A return's discount** shows as the amount taken off, without its sign.

## What the retailer does to set it up

1. Install `manifest.json` (the retailer's administrator, on the install screen; on your sandbox, `tools/deploy/deploy.py`). It adds `PP MHS Settings`, a field on the count (*Merged by press*), the two services and the button (all switched off), and the roles **PP MHS Integration**, **PP MHS Counts** and **PP MHS History** (empty).
2. In **Role Permissions**, give PP MHS Integration **read, create and write** on Stock Reconciliation, **read and create** on Comment, and **read** on POS Invoice, Sales Invoice and User. A manifest grants rights only on its own record types ([the integration user recipe](../../recipes/integration_user.md)). On the sandbox, a read iVendNext gave to every user did not reach the app's key: give it to the role.
3. Make the app's integration user with that role and generate its API key.
4. Fill **PP MHS Settings** named `Default`: the rule for the same item in the same warehouse (*Sum* or *Last*) and the number of sales the page shows.
5. Give **PP MHS Counts** to the people who merge and **PP MHS History** to the people who open the page.
6. Open each service (*Retail Extension Subscription*), read what it receives, tick the consent and switch it on; switch the button on (*Retail Desk Action*).
7. Place the **Customer history** key in **POS Studio → Apps** for the till's theme.

**What leaves the retailer's iVendNext.** The press sends the ticked counts' names; the page receives the till's sale (with its customer and cashier) or, in Desk, the customer's name. The service **reads** the ticked counts, the settings, the customer's sales and the full names of the people who made them; it **writes** one draft count per press and a comment on each ticked count.

## Run it

```bash
python3 -m unittest discover -s samples/s28_merge_and_history/tests -p 'test_*.py'
python3 samples/s28_merge_and_history/tests/canaries.py
```

The service, with its settings in a file kept out of git (the integration user's key and the two secrets the install handed back):

```bash
cat > samples/s28_merge_and_history/service/.env.local <<'EOF'
PP_BASE=https://your-sandbox.example
PP_KEY=…
PP_SECRET=…
PP_ACTION_SECRET=…
PP_PAGE_SECRET=…
PP_PORT=8133
EOF
python3 samples/s28_merge_and_history/service/app.py samples/s28_merge_and_history/service/.env.local
```

iVendNext must reach it over HTTPS with a real certificate: put it behind your own host, and write that address in the manifest's `allowed_urls` and the two `endpoint_url`s.

## The files

| File | What |
|---|---|
| `merge.py` | the merge, pure: the press's signature, the refusals, the rows (sum or last), the new draft, the answer |
| `history.py` | the page, pure: the context's signature and expiry, the nonce once, the customer, the newest sales without roll-ups, each visit's discounts |
| `service/app.py` | the service: iVendNext over the record API with the app's key, the press, the page and its one read |
| `service/history.html` | the page, drawn with the design kit (`kit/design/`), which the service serves beside it |
| `manifest.json` | the settings, the field on the count, the two services, the button, the three roles |
| `tests/` | 52 laptop tests (`test_merge.py`, `test_history.py`, `test_shop.py`, `test_manifest.py`); `canaries.py` removes each guard in turn and its test must go RED (37 of 37) |

## Technical notes

- **Why a field on the count.** The press key goes on the new draft (`pp_mhs_press_key`), so a retry finds the draft by its key even after the service stopped between writing it and answering. It is copied if a person duplicates the draft; a retry then still finds the first.
- **Why the service re-reads each count.** The press sends only the names. A count submitted after the list was drawn is read as submitted and refused.
- **Times as numbers.** iVendNext sends a time such as `9:00:00` without a leading zero, which sorts after `10:30:00` as text: the first sandbox merge took the 09:00 count as the latest. The sample compares times as numbers.
- **A draft saved after the service gave up.** Each call waits 4 seconds. If iVendNext takes longer to save the new draft, the service answers an error and the draft may still appear; a retry at that moment can find nothing and write a second one. After *did not answer in time*, look for a second draft before submitting.
- **The used contexts are guarded by a lock** (`OnceSet`), as the server answers each request on its own thread; S17's copy has none. No test drives two opens at once.
- **Text sent as text.** A list query's `order_by` sent as JSON text (in quotes) is ignored by iVendNext, which then answers oldest first (read on the sandbox). The sample sends lists as JSON and text as it is.

### What was proven where

- **The laptop tests** (`tests/`): everything above against a stand-in iVendNext, with presses and contexts signed as iVendNext signs them.
- **A sandbox site** (2026-10-16, POS 2.0.0.648, the service on a laptop behind a temporary HTTPS tunnel, the site's integration user): installed with `tools/deploy`, switched on as a System Manager would. Two draft counts (EARBUDS 12 at 77.40 posted 09:00, and 7 at 78.00 posted 10:30, with two other items) pressed the way Desk presses: **one new draft with EARBUDS 19 at 78.00**, the other items as counted, posted at 10:30, made by the integration user; a comment on each count; the counts unchanged. With *Last*: EARBUDS 7. A press that ran out of time, retried with its key: the same draft, no second one, one comment each. A submitted count ticked: the retailer's own refusal, the app not called. An opening-stock count beside a count, and one count alone: *Nothing merged*, with the reason. The page, opened in a real browser with the context the retailer signed for a customer in Desk: three sales by three people from two stores, newest first, each discount as stored, the roll-up invoice skipped; a customer with none: *No sales yet*; the same context again: refused; a user without the page's role: *You can't open this page for that record.*; the settings' number at 2: two sales. Everything made was removed and the site compared with its state before.
- **The walk ran the first build.** The review's changes after it (the bundle refusal, the latest real rate, the lock, the Desk label, a return's sign) ran on the laptop only.
- **Not run on a sandbox:** the button on the list and its dialog in Desk, and the till's own key (no one was signed in to the site's screens: every press and context came through the same server calls). The till-shaped page was opened with a context signed by the walk script with the page's secret, not by the till. Not run at all: serial-numbered counts, a batch row or a bundle, a row counted at zero, more than two counts in a press, more than 10 sales, a till sale (the sandbox has none), a till with a default walk-in customer, a return.
