# S12 — the customer's release gate

One script that says red or green before a change reaches a live shop. This sample is for a licensed customer's team (or an iVendNext Partner's) who ship changes to a shop — an app, a manifest, a price or tax rule — and want a pass or fail in their pipeline before every release.

**When to use it:** before every release, in your pipeline, against a **staging** shop.

**Door:** Outside app

`release_gate.sh --baskets baskets.json [--app DIR] [--manifest FILE]` runs, against a **staging** shop:

- your **recorded baskets** (with the totals they expect),
- the **money kit** (preview = booking),
- the **self-check** on your app.

It exits 0 only if all are green, 1 if any is red, 2 if it could not run. Recipe: `recipes/release_gate.md`.

⚠ **Staging only:** it books sales and closes till days.

## What the shop does

This is for the customer's own release team (or a partner's). The shop here is a **staging** shop, never the live one: the gate books sales and closes till days on it.

1. **Have a staging shop**, a copy of the shop where booking sales and closing till days does no harm.
2. **Put the money kit on the staging shop's server** and point it at that shop with a shop file: a cashier, an enrolled device, a POS profile and a terminal.
3. **Write your baskets.** They are the sales you care about: the lines, an optional sale discount and, once recorded, the totals you expect. Run the gate once with `--record` on a clean staging shop, then fill in the answers from that run with `record_expect.py`. Record again only when a price or tax rule you control changes.
4. **Point the gate at your staging shop** in the one block marked `HERE`.
5. **Run it before every release**, by hand or as a job in your pipeline, and read the result: green, red, or could not run. A red basket names itself with the figure you expected, the figure booked and the figure previewed.

**Where it shows.** In the gate's own lines in the terminal or the pipeline's log. On the staging shop it leaves the sales it booked and the till days it closed; a day left open makes the run RED. Nothing is added to the live shop, to its till, to POS Studio or to a print layout.

**What leaves the shop.** Nothing is installed in any shop and no outside address is named. The gate puts your baskets file into the staging box, rings each basket through the till's own calls on the staging shop (with a simulated card), reads the run's record and takes the file out again. With `--app` it also reads your app's files and manifest (the self-check reads files and runs nothing).

## The files

| File | What it is |
|---|---|
| `release_gate.sh` | the gate; the block marked `HERE` is the only part a customer changes |
| `baskets.norecord.json` → `baskets.json` | five baskets without, then with, their recorded answers |
| `record_expect.py` | fills the answers from a clean run's own record |
| `pipeline.example.yml` | the gate as a pipeline job (an example; not run by a CI service) |
| `tests/test_s12.py` | 13 laptop tests with a stub shop |

## What you need

The money kit, [`tools/moneykit/`](../../tools/moneykit/README.md), installed on the staging shop's server and pointed at your shop:

- a shop file (cashier, enrolled device, POS profile, terminal);
- if your console runs a script's text, the kit's folder.

Pass both through `GATE_KIT_SETTINGS` (`kit_dir:…;shop:…;record:…`). `GATE_KIT_SCRIPT` names the script as your console command does (default `tools/moneykit/kit.py`).

## How to run it

1. Write your baskets without answers (`baskets.norecord.json`). Run the gate once with `--record` on a clean staging shop, then fill in the answers from that run's own record with `record_expect.py`. That gives `baskets.json`.
2. Change the block marked `HERE` in `release_gate.sh` to point at your staging shop.
3. Run the gate, or put it in your pipeline (`pipeline.example.yml`):

```bash
cd samples/s12_release_gate
./release_gate.sh --baskets baskets.json --app path/to/your/app
```

## What you see

First a green run, then a run with one recorded answer one unit off (the self-check's rule lines trimmed):

```text
GATE   VERDICT PASS
GATE self-check GREEN
GATE   G001 OK  "two leather cases"  expected 2,598.00  booked 2,598.00  preview 2,598.00
GATE   G002 OK  "two leather cases, 10% markdown"  expected 2,338.20  booked 2,338.20  preview 2,338.20
GATE baskets GREEN: 5 of 5 matched
GATE open POS days: 0 GREEN
GATE RESULT GREEN — safe to release

GATE   G002 RED "two leather cases, 10% markdown"  expected 2,339.20  booked 2,338.20  preview 2,338.20  <- diverged: grand_total: recorded answer 2339.20, booked 2338.20
GATE baskets RED: 4 of 5 matched
GATE RESULT RED — do not release
```

A red basket names itself, with the figure you expected, the figure booked and the figure previewed.

## Technical notes

### What was run, and where

The output above is what the gate printed on our test bench (2026-10-07; the self-check's rule lines trimmed). The red run was without `--app`, so its self-check was skipped.

The money kit runs in the staging shop's bench.

### What was tested

| Where | What |
|---|---|
| `tests/test_s12.py` | 13 laptop tests with a stub shop |
| *our test bench's own run (not in the kit)* | 16 checks on our test bench |
