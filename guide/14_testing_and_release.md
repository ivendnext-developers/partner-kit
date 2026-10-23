# 14. Testing and release

A release gate a customer runs before any change reaches a live site. It rings test sales on a staging site and turns red if a booked total differs, by even a cent, from what the till showed or from the answer you recorded.

**For:** every builder before submitting, and a customer's own team before every change reaches a live site.
**Reference implementation:** [The customer's release gate](../recipes/release_gate.md) with [`../samples/s12_release_gate/`](../samples/s12_release_gate/) (the script, the recorded-baskets file, an example pipeline) · [The money kit](../recipes/money_kit.md), the idea behind it · the manifest checker [`../tools/manifest/`](../tools/manifest/).

## When to use it

Before any change reaches a live site: an app, a manifest, a price or tax rule. A customer puts the gate in its **own** pipeline, so a red comes back to its team without us watching.

**The idea in one paragraph.** The till shows the customer a total **before** payment (the preview). The sale is then **booked**. The two must agree to the cent, on every basket. A difference means something moved money the customer never saw. The gate adds a second test: the booked totals must also equal the answers **you recorded**. So a change of ours or yours that shifts a price or tax shows up as a red basket.

## Steps

1. **Check a manifest locally, before anyone installs it** (chapter 7):

   ```bash
   python3 tools/manifest/validate.py samples/s2_bins/manifest.json      # VALID, exit 0
   ```

2. **Record your baskets with their answers.** A basket has a name, its lines, an optional sale discount and the answer you expect (grand total and tax).
   - Write them without answers.
   - Run the gate **once with `--record`** on a clean staging site. It is green when preview equals booking.
   - Fill the answers from that run's own record, never by hand arithmetic:

   ```bash
   python3 record_expect.py baskets.norecord.json runs/<run>.json > baskets.json
   ```

   Re-record only when a price or tax rule you control changes.
3. **Point the script at your staging site.** Only the block marked `HERE` in `release_gate.sh` is yours: the staging site's container, the command that runs a console script there, where it leaves its record, and the two commands that put your baskets file in and take it out.
   - ⚠ **Staging only, one gate at a time on a box:** it books real sales (simulated card) and closes real till days.
   - The script exits 2 until `GATE_CONSOLE`, `GATE_RUNS` and `GATE_CONTAINER` are set.
   - It expects the money kit ([`../tools/moneykit/`](../tools/moneykit/README.md)) inside that staging console, pointed at your site with a site file (`GATE_KIT_SETTINGS`).
   - If the customer is on our hosting, how it reaches its staging site's console is not covered by the kit yet.
4. **Put it in the pipeline.** `pipeline.example.yml` is a job for a runner that lives on the staging box; the job's exit code is the gate's. The example has not yet been run by a CI service: treat it as a starting point.
5. **Run it and read the lines:**

   ```bash
   bash samples/s12_release_gate/release_gate.sh --baskets baskets.json [--app DIR] [--manifest FILE]
   ```

   - `--app` runs a check of app code in the retailer's iVendNext. It is for apps our team builds, and is skipped (and says so) if you ship none.
   - `--manifest` is read only together with `--app`. A manifest on its own is checked by step 1, not by the gate.

   A red basket names itself with both figures:

   ```
   GATE   G002 RED "two leather cases, 10% markdown"  expected 2,339.20  booked 2,338.20  preview 2,338.20  <- diverged: grand_total: recorded answer 2339.20, booked 2338.20
   GATE RESULT RED — do not release
   ```

**It checks three things and shows all of them, red or green:**
- the app check (if run);
- the baskets: preview equals booking, and booked equals your recorded answer;
- every till day the gate opened is closed.

**Exit 0 only if all three are green. Exit 1 if any is red. Exit 2 if the gate could not run** (a baskets file in the wrong shape, a staging site it cannot reach, a console that rang nothing). Exit 2 is never a pass.

**Other tests.**
- Sizing is not release testing: no load test has been run (chapter 16).
- **At install**, the customer's site runs the same manifest checker again, and the site's own checks, before its administrator consents (chapter 7). A manifest is not submitted to us; a review of submissions belongs to the marketplace, when it opens (chapter 17).
- **When a build fails before one of our upgrades,** whether it is pinned or switched off for that customer is not covered by the kit yet.

## What is refused, and why

- **A pass that checked nothing.** A basket with no recorded answer, or a misspelled one, is refused with exit 2, so the gate cannot pass it silently. Only the one `--record` run is exempt.
- **A day left open,** or a day the gate cannot count: red. An open day poisons that cashier for every later test.
- **Changing money anywhere the preview cannot see.** The check compares figures rather than waiting for a refusal: with a planted fault taking 1.00 off a line, no sale was refused and every one booked below what the till showed.

## When your service is down, and when the till is offline

If your own service is down: not covered by the kit yet. The gate books online, through the till's own calls. By the till's design an offline sale is queued on the device and posted only when the operator confirms it in the reconnect review, through the same path as a live sale. **The kit did not run offline.**

## Technical notes

### What the kit has proven

- **The gate, on the test site:** green on five baskets, each line carrying equal expected, booked and previewed figures; a recorded answer one unit off turned exactly that basket red and named it; with the planted money fault installed, every basket turned red; with it removed, green again; a bad baskets file, an unreachable staging site and a missing file each exited 2; no till day was left open. Its laptop tests cover every outcome and exit code.
- **The money kit** rang 68 baskets; 67 matched on the plain site (the 68th was refused by the store's own discount limit, not a money result), and the planted fault turned it red with 0 of 67 matching. All of it **online**.

### What it has not

- **A customer's real pipeline:** the example file was not run by a CI service, and the staging site in the tests was a Docker-based test site. A staging site of another kind changes the four `HERE` lines.
- **How a customer on our hosting reaches its staging site's console** is not covered by the kit yet.
- **More than five baskets in a run** (the kit is built to close a day every 40 sales; that is untested, and only five were rung); a basket iVendNext itself refuses (red with the retailer's words, not tested); the merged back-office invoice drifting against a baseline (the gate checks only that the sale was merged); two gates at once on one box.
- **The till app's version:** the gate's results were taken at the test site's pinned version; later changes to cart, tender and discount are not re-checked.
- **Offline,** and load.

## See also

[7. Manifests](07_manifests.md) · [16. Possible, not possible, limits](16_possible_not_possible.md) · [17. Submitting, support, feedback](17_submit_support_feedback.md)
