# Prove your app moves no money: the money kit — the recipe

The money kit rings real baskets through a shop's till, with your app installed and without it, and checks that your app changes **no** price, tax or total. It is for iVendNext Partners, and for the CitiXsys Consulting Team, who have built anything that reaches a sale: a till key, a manifest with webhooks, a service that writes to the shop. **Reference implementation:** [`tools/moneykit/`](../tools/moneykit/README.md) — the console script, its till harness and its settings, pointed at any staging shop by a shop file. **From a pipeline** you run it through the release gate, `samples/s12_release_gate/` ([its recipe](release_gate.md)), which calls the kit's `gate` steps with your recorded baskets.

**When to use it.** Before submitting any app that runs inside a shop, and again at every release of ours: rungs 3, 4 and 5 of the build ladder. A connected app (rung 2) cannot change a booking in the moment, but if it writes back into the shop, run the kit too.

**The idea in one line.** The till shows the customer a total **before** payment (the preview). The sale is then **booked**. If your app is installed, both must still agree to the cent, on every basket, and with your app taken out they must agree too. A difference means your app moved money the customer never saw.

## Steps

1. **Use the shop's real calls, as a cashier.** Preview with the till's `ivendnext_mpos.api.mpos_cart.recompute`; book with `ivendnext_mpos.api.mpos_tender.submit_tender`, signed in as a cashier with an enrolled device. Never build an invoice yourself: you would test your copy, not the till.

   ```python
   pv  = recompute(json.dumps(cart))                                  # what the till shows
   res = submit_tender(json.dumps(cart), json.dumps([card]), device_id=DEVICE, idempotency_key=key)
   inv = frappe.get_doc("POS Invoice", res["name"])                   # what was booked
   ```

2. **Open a day, ring every basket, close the day.** A booking needs an open day on a till. Open it, and **always** close it, even when a basket fails (`till.day()` closes in a `finally`). A day left open poisons that cashier for every later test, and fails nowhere near its cause:

   ```python
   with till.simulated_card(), till.day() as opening:     # the till takes the test card; the day always closes
       for basket in baskets:
           ring(basket)
   ```

   Closing is iVendNext's own: build the closing from the opening, set counted = expected, submit. At the close each till sale is merged into a back-office invoice; your app must not count it again.
   - ⚠ **Keep a day under 50 sales.** A day of 50 or more till sales is merged by a background job. On a shop whose scheduler is off, that job is refused and the closing is left "Queued" with the day still open. Where the scheduler is on, the day closes later, not when your test ends. The kit closes a day every 40 sales.
   - **A day counts as closed only when a submitted closing in status Submitted points back at it and the opening itself reads Closed.** A submitted closing alone is not enough.
   - **Commit each sale** if you drive the till's calls from a console or a script. A web request commits on success, a console does not, and the day's close would otherwise roll your sales back.

3. **Compare three things, preview against booking:** the **grand total** (and the rounded total), the **tax**, and **every line amount**, summed per item. Totals alone can hide two lines that moved in opposite directions. Summing per item keeps a promotion that splits one line into two from reading as a difference.

   **Then, after the day closes, check the back-office invoice each sale was merged into** — that is where the accounts post. The platform itself re-rounds at the merge: with nothing installed, about one sale in four comes out 0.01 apart. So the rule is relative: the baseline records each basket's merge difference, and with your app installed it must be **exactly the same**. An app that changes the merged invoice's money moves it.

4. **Ring a basket set that exercises money.** The kit's set has two parts:
   - **shapes** — the golden baskets the till's own offline tests use (several lines, quantities up to 70, markdowns, a percent or amount off the whole sale), mapped onto this shop's real items, with the ones the shop cannot express skipped and the reason recorded;
   - **offers** — one basket per promotion fixture, rung with only that offer switched on: percent off, amount off, buy one get one, a fixed price, a free item, a bill threshold, a coupon issued.

   **Add your own, with the answers you expect.** If your app reacts to particular items, customers or offers, record baskets for them in your own baskets file (the shape of `samples/s12_release_gate/baskets.json`) and ship that file with your app. The kit rings them in every run beside the shared set, and **fails a booking whose total or tax differs from your recorded answer**. So a change of ours that would move your money is caught when we replay your baskets at each of our releases:

   ```json
   {"baskets": [
     {"name": "two leather cases, 10% markdown", "lines": [["CASE-LEATHER", 2, 10]], "sale_discount": null,
      "expect": {"grand_total": 2338.20, "tax": 304.98}}
   ]}
   ```

   Record the expected figures from a baseline run's own record (each booked basket's `booked` totals), never by hand arithmetic. Re-record only when a price or tax rule you control changes.

5. **Run it with your app out, then in.**
   - Each run first tops up the stock its baskets need, so no basket is refused for stock.
   - Each run makes exactly one app installed: it removes the others and installs its own only if it is missing.
   - Declare your own `required_apps` as `ivendnext/<app>`. A bare name makes an install ask GitHub who owns it (60 anonymous calls an hour), and an install that fails that way leaves an empty error.
   - The first run, with no sample installed, is the **baseline**: it decides which baskets the shop can book at all. A basket the shop's own rules refuse (for example, a discount stack above the store's limit that needs a manager) is recorded with its words and left out: it is not a money result.
   - Every later run rings exactly the baseline's booked baskets with **one** app installed.

   On your own staging shop, the release gate runs the kit for you with your recorded baskets: `samples/s12_release_gate/` and [its recipe](release_gate.md).

6. **Read the result.** One line per run: `GREEN`, `RED` or `INVALID`, and how many baskets matched, diverged, or were refused at booking.
   - **INVALID** means the run did not have exactly its one app installed (or the baseline had one). Its colour proves nothing, so run it again.
   - The run's record also says what the app **did** during the run — records written, webhooks delivered — so a green run on an app that never fired is visible.
   - A RED row says what moved: *"grand total: till showed 2,598.00, booked 2,596.00"*.
   - A refusal at booking that the baseline booked is RED too — for example, the till's own guard catching a total that changed after the preview (*"The total changed in the back office…"*). The kit reports it as a failure, never as a crash.

   An app that moves money is not always stopped at the till. That is why the kit compares figures rather than waiting for a refusal.

7. **Prove the kit can go red.** Install a planted trap — an app whose one `validate` hook takes 1.00 off a line and re-totals ([the kit's README](../tools/moneykit/README.md#prove-it-can-go-red) shows the hook) — and run the kit. The till's preview never runs `validate`, so only the booking moves: **the kit must go RED.** Uninstall the trap afterwards. A kit that has never gone red proves nothing about an app that touches no money by design.

## What is refused, and why

- **Changing money anywhere the preview cannot see** (`validate`, `before_save`, `on_submit` writing a rate or a total): the customer pays one figure and the books show another.
- **A hook on the till's sale composition** (`set_missing_values`, `calculate_taxes_and_totals`): it changes the preview **and** the booking alike, so this kit cannot see it. The self-check (`tools/selfcheck/`) refuses it instead.
- **Leaving a day open**, or a promotion switched on after a run: the kit's own teardown closes every day and switches every offer back off.

## When your service is down, and when the till is offline

The kit books online, through the till's tender call. Offline, by the till's design (not run by this kit), the till queues the sale and replays it through its drain. The drain books at the engine's own total and sends any difference to review rather than posting it. If your app calls a service of yours, run the kit once with that service stopped: the bookings must match exactly as before.

## What is coming

- **Partner baskets as a release gate**: each app ships its baskets and expected answers, and we replay them all before each release of ours, so a change of ours that would break a partner's money is caught before it ships.
- A **preview that runs the same save-time rules as the booking**, or a published list of what the preview does not run, so a partner knows exactly where the two can differ.
- The kit as a **command in the developer tools**, pointed at a sandbox shop.

## Technical notes

### Where the kit has run

- `tools/moneykit/`: proven on our test bench since 2026-10-03; in this repository since 2026-10-07, pointed at any staging shop by a shop file.
- A day counts as closed only when a submitted closing in status Submitted points back at it and the opening itself reads Closed — a submitted closing alone is not enough (measured).
- The merge re-rounding (with nothing installed, about one sale in four came out 0.01 apart, measured).
- On our test bench the same runs were: a setup (offers seeded, stock topped up), a baseline, then one run per app.
- (On the bench the planted trap was not refused at all: every sale booked at the wrong total, which is why the kit compares figures rather than waiting for a refusal.)
- The planted trap: [the kit's README](../tools/moneykit/README.md#prove-it-can-go-red) shows the hook; ours stays on our test bench.

### What the bench showed

One basket set, five runs, one baseline (2026-10-03, our test bench at that day's product release). The set: **68 baskets** — 40 golden shapes mapped onto shop items (37 skipped, each with its reason: a cross-sell line, a test customer, a pack unit, built to be refused, or the same as one kept), 25 offer fixtures each rung with only its offer on, and 3 recorded baskets with their expected answers.

| Run | Installed | Rung · matched | Recorded answers | What the app did during the run | Verdict |
|---|---|---|---|---|---|
| 1 baseline | nothing | 68 · 67 (1 refused by the store's own discount limit — needs a manager, so not a money result, and left out of the runs below) | 3 of 3 | — | **GREEN** |
| 2 | the warranty till key + its webhooks | 67 · 67 | 3 of 3 | 134 webhook deliveries on its own sales | **GREEN** |
| 3 | the bin till key + its webhooks | 67 · 67 | 3 of 3 | 134 webhook deliveries on its own sales | **GREEN** |
| 4 | the price-deviation audit | 67 · 67 | 3 of 3 | 22 deviation records written | **GREEN** |
| 5 | the planted trap (a `validate` hook taking 1.00 off a line) | 67 · **0** | **0 of 3** | — | **RED** |

In run 5 every sale booked below what the till showed — *"grand total: till showed 2,598.00, booked 2,596.00"* — and the recorded answers caught it too (*"recorded answer 2,598.00, booked 2,596.00"*). **None of those sales was refused by the till.** That is why the kit compares figures: an app that moves money is not necessarily stopped at the till. 32 of the 67 baskets carried a discount (offers, markdowns, a percent or amount off the sale). After each day's close, every sale's merged back-office invoice matched the platform's own merge to the cent.

### Tests

**A check before payment** (`recipes/rule_guard.md`): with one switched on, the kit rings each sale as the till pays it — the check, the cashier's Yes to a question, the card push's own gate — and a refusal books nothing. Prove both halves: every basket your check allows books exactly as without it, and the one it must refuse is refused (`expect_refused:<basket id>:<words>`). A sample that puts a batch or a line value on a sale proves it on the booked line (`expect_batch`, `expect_line_value`), its basket line carrying what the till's scan put there (`line_extras`).

The kit runs in the shop's console with the steps `seed`, `stock`, `samples`, `run:<label>` and `pos_day_check`, after its settings (its folder, the shop, the record; on our test bench also the golden file, the seeder and our recorded baskets — [the kit's README](../tools/moneykit/README.md)); each of our runs leaves its record as `kit_<label>.json`. Its settings have laptop tests (`tools/moneykit/tests/`). The release gate (`samples/s12_release_gate/release_gate.sh`) is the way to run it from a pipeline.
