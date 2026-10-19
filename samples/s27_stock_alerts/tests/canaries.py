#!/usr/bin/env python3
"""S27's canaries: each idempotency, ownership, window and never-submit test must go RED when the rule it guards is
broken. For each mutation this copies the sample (and the tools it imports) to a temporary folder, runs the one test
named on that unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is
S26's (`samples/s26_derived_prices/tests/canaries.py` @ 63c5422; a defect there is a defect here).

    python3 samples/s27_stock_alerts/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A, R = "alerts.py", "run.py"

CANARIES = [
    # one alert per key, one request
    ("a key written today is not written again", R, "if self.shop.alert(a[\"key\"]) is None:", "if True:",
     "test_s27.Idempotent.test_a_run_twice_makes_one_alert_per_key_and_one_request"),
    ("the key holds the day", A, "return f\"{day.isoformat()} {'LOW' if kind == LOW else 'EXP'} {h}\"",
     "return f\"{'LOW' if kind == LOW else 'EXP'} {h}\"",
     "test_s27.Idempotent.test_the_next_day_is_a_new_alert_but_no_second_line_while_the_draft_is_open"),
    ("the key holds the store", A, "\"\\x1f\".join((kind, store or \"\", item, batch or \"\"))", "\"\\x1f\".join((kind, item, batch or \"\"))",
     "test_s27.Expiry.test_one_alert_per_store_that_holds_the_batch_and_each_has_its_key"),
    ("a line already on an open draft is not added again", R, "                if on:\n", "                if False:\n",
     "test_s27.Idempotent.test_the_next_day_is_a_new_alert_but_no_second_line_while_the_draft_is_open"),
    ("a stopped run finds its lines on the draft", R, "                if on:\n", "                if False:\n",
     "test_s27.Idempotent.test_a_run_that_stopped_before_its_alerts_adds_no_line_twice"),
    ("a clearance line names its batch", A, "line[\"description\"] = f\"{STAMP} batch {a['batch']}\"", "pass",
     "test_s27.Expiry.test_a_second_batch_of_the_same_item_gets_its_own_line"),
    ("outward rows are taken off", R, "out[k] = out.get(k, 0.0) + float(r.get(\"qty\") or 0)",
     "out[k] = out.get(k, 0.0) + abs(float(r.get(\"qty\") or 0))", "test_s27.ShopReads.test_outward_rows_are_taken_off_and_each_store_is_apart"),
    ("a till's unmerged sale is left out", R, ', ["voucher_type", "!=", "POS Invoice"]', "",
     "test_s27.ShopReads.test_outward_rows_are_taken_off_and_each_store_is_apart"),
    ("an update never sends a docstatus", R, 'body={"items": items})', 'body={"items": items, "docstatus": 1})',
     "test_s27.ShopReads.test_an_update_sends_the_rows_and_nothing_else"),
    ("the batches are read in parts", R, "for i in range(0, len(names), 100):", "for i in range(0, len(names), 1000):",
     "test_s27.ShopReads.test_many_batches_are_read_in_parts"),
    ("two batches of one item share a row", A, "        elif batches_of(ln) and all(row.get(k) == ln[k] for k in (\"from_warehouse\", \"warehouse\")):",
     "        elif False:", "test_s27.Expiry.test_two_batches_of_one_item_share_one_row_naming_both"),
    ("a batch already named on the row is not added again", A, "and batches_of(a) <= batches_of(b)", "and batches_of(a) == batches_of(b)",
     "test_s27.Expiry.test_two_batches_of_one_item_share_one_row_naming_both"),
    ("an item is on a request once", A, "        row = next((i for i in rows if i.get(\"item_code\") == ln[\"item_code\"]), None)", "        row = None",
     "test_s27.Expiry.test_one_item_for_two_moves_keeps_the_first_and_alerts_the_other"),
    # the stamp
    ("today's stamped draft gains the lines", R, "doc = next((d for d in mine if d[\"title\"] == title and d.get(\"docstatus\") == 0), None)", "doc = None",
     "test_s27.Stamp.test_an_existing_stamped_request_gains_lines"),
    ("a request without the stamp is a person's", A, "return (title or \"\").startswith(f\"{STAMP} {store} \")", "return True",
     "test_s27.Stamp.test_an_unstamped_request_is_never_touched"),
    ("a submitted request is never changed", R, 'if d["title"] == title and d.get("docstatus") == 0), None)',
     'if d["title"] == title), None)', "test_s27.Stamp.test_a_submitted_request_is_left_alone"),
    # never submitted
    ("the draft is made as a draft", R, "\"docstatus\": 0, \"items\": rows", "\"docstatus\": 1, \"items\": rows",
     "test_s27.NeverSubmitted.test_the_draft_is_never_submitted"),
    # the rules
    ("the last day is in the window", A, "if exp > last:", "if exp >= last:", "test_s27.Expiry.test_the_window_edges"),
    ("the window is the settings' days", A, "return today + _dt.timedelta(days=days)", "return today + _dt.timedelta(days=days + 1)",
     "test_s27.Expiry.test_the_window_edges"),
    ("a row with no level is no reorder row", A, "if store not in watched or level <= 0:", "if store not in watched:",
     "test_s27.LowStock.test_an_item_with_no_reorder_row_raises_nothing"),
    ("only watched stores", A, "if store not in watched or level <= 0:", "if level <= 0:",
     "test_s27.LowStock.test_a_row_for_a_warehouse_not_watched_raises_nothing"),
    ("at the level is not low", A, "if projected >= level:", "if projected > level:", "test_s27.LowStock.test_at_the_level_is_not_low"),
    ("the shortfall when it is larger", A, "qty = max(_f(r.get(\"warehouse_reorder_qty\")), level - projected)",
     "qty = _f(r.get(\"warehouse_reorder_qty\"))", "test_s27.LowStock.test_a_row_below_its_level_makes_an_alert_and_a_line_from_the_source"),
    ("only a Transfer row makes a line", A, "\"move\": qty if r.get(\"material_request_type\") == \"Transfer\" else 0", "\"move\": qty",
     "test_s27.LowStock.test_a_purchase_row_alerts_without_a_line"),
    ("no clearance line without a clearance warehouse", A, "elif a[\"kind\"] == EXPIRY and clear:",
     "elif a[\"kind\"] == EXPIRY:", "test_s27.Expiry.test_alert_only_without_a_clearance_warehouse"),
    ("switched off does nothing", R, "if not st or not st.get(\"enabled\"):", "if not st:", "test_s27.Settings.test_switched_off_does_nothing"),
    ("the manifest names an alert by its key", "manifest.json", '"autoname": "field:alert_key"', '"autoname": "hash"',
     "test_manifest.Manifest.test_an_alert_is_named_by_its_key"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s27-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("state", "__pycache__"))
        for tool in ("feed_client", "manifest"):
            shutil.copytree(os.path.join(kit, "tools", tool), os.path.join(tmp, "r", "tools", tool),
                            ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f).read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        open(f, "w").write(src.replace(anchor, mutant))
        if f.endswith(".py"):
            py_compile.compile(f, doraise=True)
        p = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                           capture_output=True, text=True, timeout=120)
        last = (p.stderr.strip().splitlines() or [""])[-1]
        return ("RED" if p.returncode else "GREEN"), last
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    bad = 0
    for c in CANARIES:
        verdict, last = run(*c)
        bad += verdict != "RED"
        print(f"{verdict:6} {c[0]} — {c[4]} — {last}")
    print(f"{len(CANARIES) - bad} of {len(CANARIES)} canaries RED")
    sys.exit(1 if bad else 0)
