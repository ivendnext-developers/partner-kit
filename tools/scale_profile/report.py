"""report.py — the scale-profile kit's report: a project's scale profile (the blueprint's §c, e.g.
profile.example.json) against what the bench measured (runs/l4_scale.json). Standard library only.

    python3 tools/scale_profile/report.py <profile.json> <measured.json> > report.md

It states what was measured, what the profile needs, and — plainly — what was NOT measured. ⚠ No load test exists
anywhere else in the estate: searched 2026-10-04 (locust, k6, jmeter, "load test", wrk, vegeta, artillery) over the POS
app and the engine at the bench's pins and Test Automation's folder — the only hits were "reload" and "upload test
report". This kit's figures are the only ones, and they are sequential.
"""
import contextlib
import io
import json
import sys


PROFILE_FIELDS = ("name", "stores", "tills_per_store", "products", "sales_per_till_per_day", "lines_per_sale",
                  "peak_hour_share")


def refuse(why):
    print(f"REFUSED: {why}", file=sys.stderr)
    sys.exit(2)


def main(profile_path, measured_path):
    p, m = json.load(open(profile_path)), json.load(open(measured_path))
    missing = [f for f in PROFILE_FIELDS if f not in p]
    if missing:
        refuse(f"the profile {profile_path} has no {', '.join(missing)} — copy profile.example.json and fill every field")
    out = io.StringIO()                                  # printed only when whole: a refusal leaves no half report
    try:
        with contextlib.redirect_stdout(out):
            report(p, m)
    except KeyError as e:
        refuse(f"the measurement {measured_path} has no field {e} — use the measured_*.json the kit ships")
    sys.stdout.write(out.getvalue())


def report(p, m):
    tills = p["stores"] * p["tills_per_store"]
    per_day = tills * p["sales_per_till_per_day"]
    peak_hour = per_day * p["peak_hour_share"]
    per_sale_ms = m["per_sale_ms"]["preview_plus_book_mean"] + m["day_close_ms"]["per_sale_mean"]
    seq_hour = m["sequential_capacity"]["sales_per_hour_one_till_stream"]
    g = m["growth_per_sale"]
    feed = g.get("Integration Sync Log", 0)
    print(f"# Scale profile — {p['name']}\n")
    print("## The profile (from the blueprint)\n")
    print(f"| Stores | Tills | Products | Sales a day | Peak hour ({p['peak_hour_share']:.0%}) | Lines a sale |")
    print("|---|---|---|---|---|---|")
    print(f"| {p['stores']} | {tills} | {p['products']:,} | {per_day:,} | {peak_hour:,.0f} | {p['lines_per_sale']} |\n")
    print("## Measured on our test bench\n")
    r = m["run"]
    print(f"- {r['sales_booked']} of {r['sales_attempted']} sales booked through the till's own calls, {r['lines_per_sale']} "
          f"lines each, over {r['days']} POS days; {r['refused']} refused.")
    s = m["per_sale_ms"]
    print(f"- **Per sale (server side):** preview p50 {s['preview_p50']} ms / p95 {s['preview_p95']} ms; booking p50 "
          f"{s['book_p50']} ms / p95 {s['book_p95']} ms (max {s['book_max']}).")
    print(f"- **Closing a day:** {m['day_close_ms']['per_day']} ms (≈ {m['day_close_ms']['per_sale_mean']} ms per sale).")
    print(f"- **One till stream, one after another:** about **{seq_hour:,} sales an hour** — {m['box']['note']}. "
          "Not a till's real throughput: a till also waits on its network, its cashier and the other tills.")
    print(f"- **Left behind per sale:** " + ", ".join(f"{k} {v}" for k, v in g.items() if v) +
          f"; ≈ {m['db_bytes_per_sale']:,} bytes of database (COARSE: the database's own size figures are estimates "
          f"and grow in whole pages, and {r['sales_booked']} sales are too few — read it as an order of magnitude, "
          "not a bound).")
    if g.get("Sales Invoice", 0) >= 0.9:
        print("- ⚠ **One back-office Sales Invoice per sale** on this bench: the shop's Company is set to post one invoice "
              "per sale as the sale is rung (its posting method, \"one to one, real-time posting\"), so the day's close has "
              "nothing left to merge. A Company set to \"roll up on shift closure\" makes one invoice a day: the GL and "
              "database figures here carry the per-sale setting, and a roll-up site's would be lower. Check the Company "
              "setting of the site you are sizing.")
    print(f"- Catalogue on the bench: {m['catalogue']['items']:,} items ({m['catalogue']['items_used']} used); "
          f"the profile has {p['products']:,}.\n")
    print("## What the profile needs, against that\n")
    need = peak_hour * per_sale_ms / 3_600_000
    print(f"- **Peak hour:** {peak_hour:,.0f} sales × {per_sale_ms:.0f} ms = **{need:.2f} server-hours of booking work in "
          f"one hour** — i.e. at least **{max(1, -(-need // 1)):.0f} sale(s) in flight at every moment** of the peak, if "
          "the server handled concurrent sales as fast as single ones (NOT measured).")
    if peak_hour > seq_hour:
        print(f"- ⚠ **The profile's peak hour is above what was measured:** {peak_hour:,.0f} sales against about "
              f"{seq_hour:,} an hour for one till stream. No figure here covers it: the peak needs many sales at once, "
              "which was NOT measured.")
    print(f"- **A year of data:** about {per_day * 365 * m['db_bytes_per_sale'] / 1e9:,.0f} GB of database growth at "
          "this coarse rate (an order of magnitude; see the per-sale caveats above).")
    print(f"- **The event feed:** {per_day * p.get('feed_applications', 1) * 6:,.0f} feed rows a day for "
          f"{p.get('feed_applications', 1)} application(s) — 6 rows a sale per application following till sales "
          f"(measured by the feed client's test: 24 rows for 4 sales); on this run {feed} per sale (none registered). "
          "Each application must mark its rows done, or the engine never clears them.\n")
    print("## NOT measured — say so before anyone quotes a figure\n")
    print("- **Concurrency:** many tills booking at once over HTTP (locks, worker count, the database under contention).")
    print("- **Many stores:** one store, one till profile, one cashier on the bench; no per-store warehouse spread.")
    print(f"- **A catalogue of {p['products']:,} items:** the bench has {m['catalogue']['items']:,}; item lookup and the "
          "offline snapshot grow with it.")
    print(f"- **Offline drains:** {p.get('offline_hours_expected', 0)} hours of queued sales arriving at once.")
    print("- **The production box:** the bench is a shared test machine, not the hosting the customer runs on.")
    print("- ⚠ **No load test exists anywhere else in the estate**; these are the only figures, and they are sequential.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        refuse("usage: report.py <profile.json> <measured.json>")
    main(*sys.argv[1:3])
