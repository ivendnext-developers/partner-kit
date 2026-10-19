# The scale-profile kit — what a project's volumes ask of the system, against what was measured

You give the kit a project's expected volumes — stores, tills, sales a day — and it tells you, in plain words, how they compare with what we have measured, and what has not been measured.

**When to use it:** when you fill a project's blueprint (`kit/blueprint.md` §c, the scale profile) and need to know whether the figures are within what has been measured.

⚠ **These are the only load figures there are for iVendNext, and they come from one till selling at a time.** Nothing has been measured for many tills at once, many stores, a large catalogue, a till catching up after being offline, or the production hosting. `report.py` prints these every time.

## Steps

1. Make your profile: copy `profile.example.json` and put in your project's figures.
2. Run the report against the measurement. The command below uses the example profile; give your own file in its place.

```bash
python3 tools/scale_profile/report.py tools/scale_profile/profile.example.json tools/scale_profile/measured_2026-10-04.json
```

| File | What |
|---|---|
| `profile.example.json` | a profile: stores, tills per store, products, sales per till per day, lines per sale, trading hours, peak-hour share, offline hours, feed applications |
| `bench_run.json` | the run we measured: how many sales, lines each, a day closed every 40 sales |
| `measured_2026-10-04.json` | the measurement: real till sales through the till's own calls (preview + booking, as the cashier), days opened and closed; the time per sale, the day close, what each sale leaves behind and the database's growth |
| `report.py` | your profile against the measurement, in plain words — and what was NOT measured |

## Technical notes

- ⚠ **No load test exists anywhere else in the estate** (searched 2026-10-04: no load, soak or concurrency harness). This kit's figures are the only ones, and they are **sequential**.
- `measured_2026-10-04.json` is the measurement, from our test bench.
- **Measured on 2026-10-04:** 120 of 120 sales booked, 3 lines each, 3 days; preview p50 81 ms / p95 93 ms; booking p50 568 ms / p95 606 ms; a day's close ≈ 1.5 s; one till stream ≈ 5 200 sales an hour; per sale: 1 POS Invoice, 3 lines, 7.4 GL entries, 3 stock ledger entries, 2 payment ledger entries, 3.1 versions, and **one back-office Sales Invoice per sale** (the Company on this bench posts one invoice per sale as the sale is rung — its posting method is "one to one, real-time posting" — so the close merges nothing: 120 for 120; measured 2026-10-07: six sales of the same shape with the Company on "roll up on shift closure" made one invoice, and the setting was put back).
- **Two guards:** a profile or measurement missing a field is refused in words (the field named, exit 2, no half report), and a profile whose peak hour is above the measured one-till rate gets a warning line. Tests: `tools/scale_profile/tests/`.
- **Not measured:** concurrency (many tills at once over HTTP), many stores, a large catalogue (the bench has 81 items), offline drains, the production hosting. `report.py` prints these every time.
