#!/usr/bin/env python3
"""S3's canaries: each test of the hosted service's rules must go RED when the rule it guards is broken. For each mutation
this copies the sample (and the kit tools it uses) to a temporary folder, runs the one test named on that unmutated copy
(it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs
the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S25's
(`samples/s25_gift_on_spend/tests/canaries.py` @ 4128c03; a defect there is a defect here).

    python3 samples/s3_price_audit/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S, W, A, M = "outside/service.py", "outside/worker.py", "outside/app.py", "outside/manifest.json"
T = "test_service."

CANARIES = [
    # the shop's own threshold
    ("each shop is judged at its own threshold", W, "lambda: service.threshold_of(api, fallback))", "lambda: fallback)",
     T + "Threshold.test_each_shop_is_judged_at_its_own_threshold"),
    ("no settings record: 10", S, '        if str(e).startswith("404") and "Default" in str(e):\n            return float(fallback)',
     '        if False:\n            return float(fallback)', T + "Threshold.test_a_shop_with_no_settings_record_is_judged_at_10"),
    ("a refused settings read is never a silent default", S, "            return float(fallback)\n        raise\n",
     "            return float(fallback)\n        return float(fallback)\n",
     T + "Threshold.test_a_refused_settings_read_leaves_the_sale_not_done_and_writes_nothing"),
    ("the threshold is read once a pass", S, "        if not got:\n", "        if True:\n",
     T + "Threshold.test_the_threshold_is_read_once_a_pass_and_only_when_a_sale_is_judged"),
    ("the threshold is read only when a sale is judged", S, "    got = []\n",
     "    got = [float(threshold() if callable(threshold) else threshold)]\n",
     T + "Threshold.test_the_threshold_is_read_once_a_pass_and_only_when_a_sale_is_judged"),
    # writes
    ("a second delivery writes nothing", S, 'if not str(e).startswith("409"):', "if True:",
     T + "Writes.test_a_second_delivery_writes_nothing_and_the_event_is_done"),
    ("a line handed back is never judged", S, 'sold = [it for it in items if float(it["qty"] or 0) > 0]',
     'sold = list(items)', T + "Writes.test_an_exchange_is_judged_for_what_it_sells_and_a_line_handed_back_never"),
    ("an exchange is judged for what it sells", S, 'if sale.get("is_consolidated") or sale.get("docstatus") != 1:',
     'if sale.get("is_return") or sale.get("is_consolidated") or sale.get("docstatus") != 1:',
     T + "Writes.test_an_exchange_is_judged_for_what_it_sells_and_a_line_handed_back_never"),
    ("a return's event reaches the rule", S, '("sale.booked", "return.booked", "invoice.booked")', '("sale.booked", "invoice.booked")',
     T + "Writes.test_an_exchange_is_judged_for_what_it_sells_and_a_line_handed_back_never"),
    ("a roll-up is not judged", S, 'if sale.get("is_consolidated") or sale.get("docstatus") != 1:', 'if sale.get("docstatus") != 1:',
     T + "Writes.test_a_return_a_roll_up_and_a_draft_are_not_judged"),
    ("a price the key cannot read fails the sale", S, 'if any(k not in it for it in items for k in ("qty", "price_list_rate", "rate")):',
     'if any(k not in it for it in items for k in ("price_list_rate", "rate") if float(it.get("qty") or 0) > 0):', T + "Writes.test_a_price_the_key_cannot_read_fails_the_sale_never_reads_0"),
    ("only the record's own 404 falls back", S, ' and "Default" in str(e)', "",
     T + "Threshold.test_only_the_records_own_404_falls_back_to_10"),
    ("a translated no-record answer still falls back", S, ' and "Default" in str(e)', ' and "Default not found" in str(e)',
     T + "Threshold.test_a_translated_no_record_answer_still_falls_back_to_10"),
    ("the prefix names the settings too", S, '    DT, SETTINGS = f"{prefix} Deviation", f"{prefix} Settings"',
     '    DT, SETTINGS = f"{prefix} Deviation", SETTINGS', T + "Prefix.test_every_record_type_name_follows_the_prefix"),
    ("the prefix names the deviations", S, '    DT, SETTINGS = f"{prefix} Deviation", f"{prefix} Settings"',
     '    DT, SETTINGS = DT, f"{prefix} Settings"', T + "Prefix.test_the_librarys_app_reads_and_writes_its_own_record_types"),
    # many shops
    ("each shop's own user key", W, 'if k.startswith("user:"))', 'if ":" in k)',
     T + "ManyShops.test_each_shop_is_served_with_its_own_key_and_one_without_a_user_stops_none"),
    ("one shop's failure stops no other", W,
     "        except Exception as e:                   # noqa: BLE001 — one shop's failure never stops the others",
     "        except ZeroDivisionError as e:", T + "ManyShops.test_each_shop_is_served_with_its_own_key_and_one_without_a_user_stops_none"),
    ("a shop with no user is named so", W, '        raise NoUser("no_user")', '        raise KeyError("no_user")',
     T + "ManyShops.test_each_shop_is_served_with_its_own_key_and_one_without_a_user_stops_none"),
    ("a shop gone during the pass is logged as gone", W, '                out[site] = {"error": "gone"}           # disconnected during this pass',
     "                pass", T + "ManyShops.test_a_shop_gone_during_the_pass_is_logged_as_gone"),
    ("a notes folder it cannot write stops the start", A, "        except OSError as e:\n            raise SystemExit(f\"PP_STATE",
     "        except ZeroDivisionError as e:\n            raise SystemExit(f\"PP_STATE",
     T + "Service.test_without_the_librarys_id_or_a_writable_notes_folder_it_refuses_to_start"),
    ("a deleted sale never blocks the feed", S, '            if str(e).startswith("404") and ev["doc_name"] in str(e):',
     "            if False:", T + "Writes.test_a_sale_deleted_before_it_is_read_never_blocks_the_feed"),
    ("the log names a refusal's status", W, '            out[site] = {"error": f"FeedError {str(e).split(\' \', 1)[0]}"}',
     '            out[site] = {"error": type(e).__name__}', T + "ManyShops.test_each_shop_is_served_with_its_own_key_and_one_without_a_user_stops_none"),
    ("a busy shop is never run twice", W, "        if th is not None and th.is_alive():", "        if False:",
     T + "ManyShops.test_a_shop_busy_past_the_limit_is_stuck_and_never_run_twice"),
    ("a store that does not answer is not a healthy pass", W, "        return None                              # not a pass",
     "        return {}                              # not a pass", T + "ManyShops.test_a_shops_store_that_does_not_answer_is_not_a_healthy_pass"),
    ("a stuck shop is not a healthy pass", W, 'return out is not None and not any((v or {}).get("stuck") for v in out.values())',
     "return out is not None", T + "ManyShops.test_a_shops_store_that_does_not_answer_is_not_a_healthy_pass"),
    ("/health says when the worker stalls", A, "return not (time.monotonic() - self.started > HEALTH_GRACE_S and stale)",
     "return True", T + "Service.test_health_is_503_once_the_worker_stalls_and_nothing_else_is_answered"),
    ("the handshake answers only the library's app", A, '        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()',
     '        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip() and "ivendnext_gcs"',
     T + "Service.test_a_shop_connects_with_its_own_key_and_the_goodbye_forgets_it"),
    # the manifest
    ("the service's role writes no deviation", M, '"PP PDO Integration", "read": 1, "write": 0, "create": 1,',
     '"PP PDO Integration", "read": 1, "write": 1, "create": 1,', T + "Manifest.test_the_services_role_reads_the_settings_and_creates_deviations_only"),
    ("a deviation is named by its sale line", M, '"autoname": "field:line_key"', '"autoname": "hash"',
     T + "Manifest.test_a_deviation_is_named_by_its_sale_line_so_the_shop_refuses_a_second"),
    ("the manifest names the one service its site connects", M, '"https://pdo.partner.example"', '"https://pdo.partner.example/x"',
     T + "Manifest.test_the_shop_calls_nothing_outside_and_names_the_one_service_its_site_connects"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s3-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("state", "__pycache__"))
        for tool in ("feed_client", "manifest", "app_template"):     # app.py imports the template's handshake
            shutil.copytree(os.path.join(kit, "tools", tool), os.path.join(tmp, "r", "tools", tool),
                            ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120,
                              env=dict(os.environ, PP_BEFORE=os.path.join(tmp, "before0.json")))
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
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PP_BEFORE=os.path.join(tmp, "before.json")))
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
