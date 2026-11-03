# S12 — the customer's release gate

One script that says red or green before a change reaches a live site. A customer's team, or a partner's, runs it against a **staging** iVendNext before every release of an app, a manifest, a price or a tax rule. It rings your recorded baskets, checks that preview equals booking, and runs the self-check on your app. It exits 0 only if all are green, 1 if any is red, 2 if it could not run.

**Industries:** every industry

**When to use it:** before every release, in your pipeline, against a **staging** site.

**Door:** Outside app

## Start from it

**Copy by hand: not an app made here.** Copy this folder into your release pipeline's repository; nothing is installed in any retailer.

## What to change

What a partner usually changes:

- `baskets.json`: the sales you care about, with the totals they expect. Write `baskets.norecord.json`, run the gate once with `--record` on a clean staging site, then fill in the answers with `record_expect.py`. Record again only when a price or tax rule you control changes.
- the block marked `HERE` in `release_gate.sh`: the staging site. It is the only part a customer changes.
- `pipeline.example.yml`: the gate as a pipeline job.

More: the [recipe](../../recipes/release_gate.md).

**The customer sets:** a staging site, a copy of the retailer's iVendNext where booking sales and closing till days does no harm, with the [money kit](../../tools/moneykit/README.md) on its server and a site file (a cashier, an enrolled device, a POS profile and a terminal), passed through `GATE_KIT_SETTINGS`.

## Run it

```bash
cd samples/s12_release_gate
./release_gate.sh --baskets baskets.json --app path/to/your/app
```

Staging only: it books sales and closes till days. A day left open makes the run red.

## Versions

### 1.0.0

- First version in the kit: the customer's release gate, red or green before a change reaches a live site.
