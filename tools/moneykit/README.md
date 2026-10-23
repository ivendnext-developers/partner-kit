# The money kit — preview against booking, on your staging site

The money kit checks that what the till shows a customer is what iVendNext books. It rings baskets through the till's own calls — the **preview** the customer sees, then the **booked** sale, then the back-office invoice the sale is merged into when the day closes — and fails any basket whose total, tax or line amounts differ. Why and how: [the recipe](../../recipes/money_kit.md).

**When to use it:** to check, on a staging site with your app installed, that no basket books a different amount from the one the till showed. From a pipeline you run it through the release gate, [`samples/s12_release_gate/`](../../samples/s12_release_gate/README.md).

⚠ **Staging only.** It books real sales (simulated card) and opens and closes real till days. Every day it opens, it closes.

**Licence.** These files are under the kit's Apache 2.0 licence. When they run, they call iVendNext code inside your site; the licence covers these files only and grants nothing in the code they call.

| File | What it is |
|---|---|
| `kit.py` | the console script: its steps and settings are listed at its top |
| `till.py` | the till harness: open a day, preview, book, close the day, list the days not truly closed |
| `baskets.py` | builds a basket set (golden shapes and offer baskets, both optional) and counts every basket kept or skipped |
| `printcheck.py` | does a printed receipt show the booked total and tax next to their labels |
| `shop.example.json` | the shape of your site file |
| `tests/test_settings.py` | laptop tests of the settings, with a stub console |

## Point it at your site

Nothing in the kit names a site. Before it rings anything it needs:

1. **The site it rings at** — a cashier (a user who sells at the till), a device enrolled for that user, the POS profile they sell on, and a terminal name (made on the profile's store if it does not exist). Copy `shop.example.json` to a file named shop.json beside `till.py` and fill it in. Or keep the file elsewhere on the retailer's server and give the step `shop:<file>`. A value left out fails before any day is opened, naming it.
2. **Where the kit sits** — if your console runs the script as a file, the kit finds its own folder; if it runs the script's text (as ours does), give the step `kit_dir:<folder>`.
3. **Where the record goes** — a file named pp_out.json in the console user's home, or the step `record:<file>`. Your console command collects it from there.

Settings are steps, given before the others (a `kit_dir:` or `shop:` after them is refused), because a console started from a script does not pass environment variables through. The release gate passes them for you from `GATE_KIT_SETTINGS` (`kit_dir:…;shop:…;record:…`).

## The steps

- `gate_stock:<baskets file>`, `gate:<baskets file>`, `pos_day_check` — what the release gate runs: your recorded baskets, each with the answer you expect.

On your own site, these are the steps to use, with your own recorded baskets. The kit has other steps for our own test site; they are listed under Technical notes.

## Prove it can go red

Before you trust a green result, check that the kit catches a wrong amount:

1. Install a planted fault on the staging site: an app whose one `validate` hook on POS Invoice takes 1.00 off the first line's rate and re-totals. Its hook is the whole of it (below).
2. Run the release gate once (or the steps `gate_stock:` and `gate:` with your baskets). The till's preview never runs `validate`, so only the booking moves, and **every basket must turn red**.
3. Uninstall it afterwards.

The kit does not ship this app: the kit holds no app that runs inside a retailer's iVendNext.

```python
def shave(doc, method=None):            # hooks.py: doc_events = {"POS Invoice": {"validate": "<your_app>.trap.shave"}}
    if not doc.get("items") or doc.get("is_return"):
        return
    line = doc.items[0]
    line.rate = flt(line.rate) - 1
    doc.calculate_taxes_and_totals()
```

## Technical notes

### Where the site file can live

Copy `shop.example.json` to a file named shop.json beside `till.py` and fill it in, or keep the file anywhere in the bench and give the step `shop:<file>`.

### The other steps (our test site's runs)

- `stock`, `run:<label>` — our test bench's whole runs (its labels name our samples; a run with none of its baskets rung is INVALID), with a **baseline** first (nothing installed) and then one run per app installed (`baseline:<file>` keeps what the baseline booked). A run rings your recorded baskets (`recorded:<file>`) and two optional shared sets: golden shapes from a golden baskets file (`golden:<file>`; on our test bench, the POS app's own offline-test fixture) and one basket per offer (`seeder:<file>` and the step `seed`). Without them a run says so in its counts (`golden_used`, `promotion_used`): a run that rang little is visible, never green by default.
- `samples:<s1>:<s2>`, `print_format:<name>`, `extra:<file>` — our samples' own runs (webhooks on or off, every sale also printed, extra baskets).
- `expect_line:<item>:<net>[:<list price>]`, after `run:` — when a sample changes one item's price or promotion: the run rings that item in an extra basket only (a basket with a recorded answer or a baseline would move with the change), and the run is RED unless that line was booked at the new price. It proves the change was live while the baskets rang.
- `expect_detail:<attribute>:<value>`, after `run:` — when a sample puts a sale detail on a till sale: the extra basket sends it as the till's sheet does (`sale_attributes` in the extra file), and the run is RED unless every booked sale carries it.

The shared sets name our test site's catalogue: on your own site, ring your own recorded baskets.

### The planted fault on our bench

On our bench, the planted fault turned 5 of 5 baskets red through the gate and 69 of 69 through a whole run. Ours is a small test app on our test bench, kept out of this repository on purpose (the kit holds no app that runs inside a retailer's iVendNext).
