#!/usr/bin/env python3
"""S28's canaries: each guard of the merge and the page must go RED when it is removed. For each mutation this copies
the sample (and the manifest checker it calls) to a temporary folder, runs the one test named on that unmutated copy
(it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs
the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S27's
(`samples/s27_stock_alerts/tests/canaries.py` @ fac54dd; a defect there is a defect here).

    python3 samples/s28_merge_and_history/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M, H, A = "merge.py", "history.py", "service/app.py"

CANARIES = [
    # the merge rules
    ("two drafts with the same item sum", M, 'row["qty"] = row["qty"] + _num(r.get("qty")) if rule == SUM else _num(r.get("qty"))',
     'row["qty"] = _num(r.get("qty"))', "test_merge.Rules.test_two_drafts_with_the_same_item_sum"),
    ("the last rule takes the last count", M, "for d in in_order(docs):", "for d in docs:",
     "test_merge.Rules.test_the_last_rule_takes_the_last_count_by_posting_time"),
    ("a time is compared as numbers", M, 'return (str(doc.get("posting_date") or ""), clock(doc.get("posting_time")), doc.get("name") or "")',
     'return (str(doc.get("posting_date") or ""), str(doc.get("posting_time") or ""), doc.get("name") or "")',
     "test_merge.Rules.test_a_time_without_a_leading_zero_is_still_earlier"),
    ("a sale's time is compared as numbers", H, 'return (str(row.get("posting_date") or ""), clock(row.get("posting_time")), row.get("name") or "")',
     'return (str(row.get("posting_date") or ""), str(row.get("posting_time") or ""), row.get("name") or "")',
     "test_history.Visits.test_the_same_day_sorts_by_time_as_numbers"),
    ("quantities add as decimals", M, 'return Decimal(str(value or 0))', 'return float(value or 0)',
     "test_merge.Rules.test_quantities_add_as_decimals"),
    ("the batch is part of the row", M, 'k = (item, wh, r.get("batch_no") or "")', "k = (item, wh)",
     "test_merge.Rules.test_another_warehouse_or_batch_is_its_own_row"),
    ("a blank row is dropped", M, "if not item or not wh:", "if not item:",
     "test_merge.Rules.test_blank_rows_are_dropped_and_a_counted_zero_is_kept"),
    ("the new draft keeps the last posting time", M, '"set_posting_time": 1,', '"set_posting_time": 0,',
     "test_merge.Rules.test_the_new_draft_keeps_company_purpose_and_the_last_posting_time"),
    # the refusals
    ("a submitted source refuses the whole request", M, "if d.get(\"docstatus\") == 1:", "if False:",
     "test_merge.Press.test_a_submitted_source_refuses_the_whole_request"),
    ("a single count is refused", M, "if len(docs) < 2:", "if len(docs) < 1:", "test_merge.Refusals.test_a_single_count_is_refused"),
    ("a cancelled count is refused", M, "if d.get(\"docstatus\") == 2:", "if False:",
     "test_merge.Refusals.test_a_cancelled_count_is_refused"),
    ("a bundle row is refused", M, ' or r.get("serial_and_batch_bundle")', "",
     "test_merge.Refusals.test_serial_numbers_and_bundles_are_refused"),
    ("a serial row is refused", M, '(r.get("serial_no") or "").strip() or ', "",
     "test_merge.Refusals.test_serial_numbers_and_bundles_are_refused"),
    ("a counted zero keeps the last real rate", M, 'if _num(r.get("valuation_rate")) or "valuation_rate" not in row:', "if True:",
     "test_merge.Rules.test_a_counted_zero_keeps_the_last_real_rate"),
    ("two companies are refused", M, 'if len({d.get("company") for d in docs}) > 1:', "if False:",
     "test_merge.Refusals.test_submitted_cancelled_company_purpose_and_serials_are_refused"),
    ("two purposes are refused", M, 'if len({d.get("purpose") for d in docs}) > 1:', "if False:",
     "test_merge.Refusals.test_submitted_cancelled_company_purpose_and_serials_are_refused"),
    ("the saved record is re-read", A, "docs = list(pool.map(self.shop.count, names))",
     "docs = [{**r[\"fields\"], \"docstatus\": 0, \"items\": []} for r in ctx[\"records\"]]",
     "test_merge.Press.test_the_service_rereads_the_saved_record_not_the_press"),
    # one draft per press
    ("a retry writes one draft", A, "made = self.shop.merged_by(key)", "made = None",
     "test_merge.Press.test_a_retry_writes_one_draft"),
    ("the key is written on the draft", M, "KEY_FIELD: key, ", "",
     "test_merge.Press.test_a_retry_after_a_failure_finds_the_draft_and_finishes_the_comments"),
    ("a comment is not written twice", A, "if s != made and (fresh or text not in self.shop.comments(s)):", "if s != made:",
     "test_merge.Press.test_a_retry_writes_one_draft"),
    ("the settings rule is used", A, '(settings.result().get("merge_rule") or merge.SUM)', "merge.SUM",
     "test_merge.Press.test_the_settings_rule_is_used"),
    ("the press signature is checked", M, "if not hmac.compare_digest(want, sig.encode()):", "if False:",
     "test_merge.Press.test_a_forged_or_stale_press_is_refused_before_anything_is_read"),
    ("a stale press is refused", M, "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     "test_merge.Press.test_a_forged_or_stale_press_is_refused_before_anything_is_read"),
    # the page
    ("only a Customer record opens in Desk", H, 'if payload["doctype"] == "Customer" and', "if",
     "test_history.Visits.test_desk_opens_for_a_customer_record_only"),
    ("a return's discount is what was taken off", H, 'off = abs(_num(it.get("discount_amount")) * qty)', 'off = _num(it.get("discount_amount")) * qty',
     "test_history.Visits.test_a_returns_discount_is_shown_as_taken_off"),
    ("the context signature is checked", H, "if not hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).digest(), got):",
     "if False:", "test_history.Context.test_a_bad_signature_is_refused"),
    ("an expired context is refused", H, 'now > payload["exp"]', "False", "test_history.Context.test_an_expired_context_is_refused"),
    ("a nonce is used once", A, 'if not self.opened.claim(payload["nonce"], payload["exp"]):', "if False:",
     "test_history.Context.test_a_reused_nonce_is_refused"),
    ("the roll-up invoice is skipped", H, 'for r in si_rows if not r.get("is_consolidated")]', "for r in si_rows]",
     "test_history.Visits.test_the_till_shows_the_sales_customers_visits_newest_first_without_the_roll_up"),
    ("the read asks for no roll-ups", A, '            filters.append(["is_consolidated", "=", 0])\n', "",
     "test_shop.Reads.test_the_sales_invoice_read_skips_roll_ups_and_asks_for_x"),
    ("no more than x are read", A, "limit_page_length=count)", "limit_page_length=0)",
     "test_shop.Reads.test_the_sales_invoice_read_skips_roll_ups_and_asks_for_x"),
    ("the order is sent as text", A, "{k: v if isinstance(v, str) else json.dumps(v) for k, v in params.items()}",
     "{k: json.dumps(v) for k, v in params.items()}", "test_shop.Reads.test_the_newest_are_asked_for_in_plain_text"),
    ("no more than x are shown", H, "return [(dt, r[\"name\"]) for dt, r in rows[:count]]", "return [(dt, r[\"name\"]) for dt, r in rows]",
     "test_history.Visits.test_no_more_than_the_settings_number_is_read_or_shown"),
    ("only the customer's sales are kept", H, 'if r.get("customer") == customer and r.get("docstatus") == 1]',
     'if r.get("docstatus") == 1]', "test_history.Visits.test_never_another_customers_sale"),
    ("a record of another customer is dropped", A, 'docs = [(dt, d) for dt, d in docs if d.get("customer") == customer]', "pass",
     "test_history.Visits.test_a_read_that_returns_another_customers_sale_is_dropped"),
    ("the read asks for this customer", A, 'filters = [["customer", "=", customer], ["docstatus", "=", 1]]',
     'filters = [["docstatus", "=", 1]]', "test_shop.Reads.test_the_sales_invoice_read_skips_roll_ups_and_asks_for_x"),
    ("the line discount is per unit times quantity", H, 'off = abs(_num(it.get("discount_amount")) * qty)', 'off = abs(_num(it.get("discount_amount")))',
     "test_history.Visits.test_each_visit_has_the_store_who_served_and_the_discounts"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s28-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env*"))
        shutil.copytree(os.path.join(kit, "tools", "manifest"), os.path.join(tmp, "r", "tools", "manifest"),
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
