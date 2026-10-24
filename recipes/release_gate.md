# The customer's release gate — the recipe

This recipe gives a licensed customer's IT team (or an iVendNext Partner's) one script for their pipeline. It says **red or green** before any change reaches a live site, without us watching. A change can be an app, a manifest, or a price or tax rule. The sample to copy is `samples/s12_release_gate/` (`release_gate.sh`, `record_expect.py`, an example pipeline file, the tests). The gate is the money kit (`recipes/money_kit.md`) and the self-check (`tools/selfcheck/`) with your own baskets, in one command.

**When to use it:** your team ships changes to a retailer's iVendNext and wants a pass or fail before every release.

## What it checks, in order — and shows all of it, red or green

1. **Self-check** on your app folder (and manifest). It reads your files and runs nothing. Only an app the CitiXsys Consulting Team builds inside a retailer's iVendNext has code to check; a partner's build ships no app code into the retailer's iVendNext (a sandboxed module, which does run inside it, is certified separately by CitiXsys), so it is skipped, and says so.
2. **Baskets.** You keep *recorded* baskets in a file shaped like the sample's `baskets.json`: a name, the lines, an optional sale discount, and the **answer you expect** (grand total and tax). The gate rings each one on the **staging** site through the till's own calls: the till's **preview**, the **booked** sale, and the back-office invoice it is merged into. A basket is **RED** if its preview and its booking differ, **or** if its booked totals differ from your recorded answer. Each basket gets one line: the figure you expected, the figure booked, the figure previewed.
3. **Till days.** Every day the gate opened must be closed. Any day left open is RED.

**Exit 0 only if all three are green. Exit 1 if any is red. Exit 2 if the gate could not run** (a baskets file in the wrong shape, a staging box it cannot reach, a console that rang nothing) — **that is never a pass.**

```
GATE   G002 RED "two leather cases, 10% markdown"  expected 2,339.20  booked 2,338.20  preview 2,338.20  <- diverged: grand_total: recorded answer 2339.20, booked 2338.20
GATE RESULT RED — do not release
```

## Steps

1. **Record your baskets with their answers.** Write the baskets without answers (`baskets.norecord.json`). Run the gate **once with `--record`** on a clean staging site; it is green when preview = booking. Then fill the answers from that run's own record — never by hand arithmetic:

   `python3 record_expect.py baskets.norecord.json runs/<run>.json > baskets.json`

   Re-record only when a price or tax rule you control changes.

2. **Point the script at your staging box.** Only the block marked `HERE` in `release_gate.sh` is yours. It names:
   - the staging box's container;
   - the command that runs a console script there;
   - where that script leaves its record;
   - the two commands that put your baskets file into the box and take it out (`GATE_PUT`, `GATE_RM`; Docker's `cp` and `exec` by default).

   The money kit itself ([`tools/moneykit/`](../tools/moneykit/README.md)) must be on that box, pointed at your site. `GATE_KIT_SCRIPT` names it as your console does. `GATE_KIT_SETTINGS` passes its settings (`kit_dir:…;shop:…;record:…` — only these three).

   ⚠ **Staging only, one gate at a time on a box.** The gate books real sales (with a simulated card) and closes real till days.

3. **Put it in the pipeline.** `samples/s12_release_gate/pipeline.example.yml` is an example for a job on a runner that lives on the staging box. The job's exit code is the gate's.

4. **Read the lines.** A RED basket names itself, with both figures and the kit's words (*"grand total: till showed 2598.00, booked 2596.00"*). A red self-check lists the finding with its file and line.

## What it refuses, and why

- **A kit setting other than the three above is refused, with exit 2.** So a setting that could ring sales or seed data cannot be passed through the gate.
- **Without `--record`, a basket with no recorded answer (or a misspelled one) is refused — exit 2 — so the gate cannot pass a basket it checked nothing for.**
- The record the gate reads is named for its own run, and so is its baskets file on the box. So it cannot read an old run's record or another's. A console command of your own must still clear its one shared output file before each run, as ours does.

## Limits

- It has not yet been run by a real CI service, or on a staging box that is not Docker-based (there, the `HERE` block's four lines change).
- It has been tried with at most five baskets in one run. Details of what is and is not covered are in Technical notes.

## Technical notes

### Recording
On the bench the first three baskets recorded **the same figures** as the money kit's own recording a day earlier. The quoted RED line in step 4 (*"grand total: till showed 2598.00, booked 2596.00"*) is the planted trap's own line on the bench.

### What was proven where

- **Laptop, 13 tests** (`tests/test_s12.py`, stand-in iVendNext): the lines and the exit codes for every outcome — all green; a basket off its recorded answer (named, with both figures); a day left open; an unknown open-day count; a red self-check (the self-check's own money plant: a hook that changes a line's rate, named in the output) and a clean one; every could-not-run case exits 2; the recorder fills answers only from a clean run; the kit's settings reach the console, one step each, before the gate's steps, and a setting that could ring or seed is refused.
- **Our test bench, 16 checks** (through its bench driver, which runs `release_gate.sh` itself, the money kit read from `tools/moneykit/` with the bench's site file passed as a setting): green on 5 baskets and a clean app, each line carrying equal expected, booked and previewed figures; a recorded answer **one unit off** turns exactly that basket red and names it; **with the money kit's planted trap installed every basket turns red** and the self-check on the trap's folder is red naming the money rule; with the trap uninstalled it is green again; a bad baskets file, an unreachable bench and a missing file each exit 2; the count of POS days not truly closed is 0 after every run and on the whole bench at the end.
- ⚠ **Not proven:** a customer's real pipeline (the example file was not run by a CI service); a bench that is not Docker-based like ours (the `HERE` block's four lines are what changes); more than 5 baskets in one run (only 5 were rung, so a run long enough for the kit to close a day, every 40 sales, is untested too); a basket iVendNext refuses (e.g. a discount needing a manager) is RED with iVendNext's words, not tested on the bench; offline behaviour; the merged back-office invoice's drift against a baseline (the gate checks only that the sale was merged).
