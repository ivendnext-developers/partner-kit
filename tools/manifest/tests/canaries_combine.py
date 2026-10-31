#!/usr/bin/env python3
"""The canaries of New app's merge rules and Add a sample (``tools/manifest/combine.py``): each must go RED when the rule
it guards is broken. For each mutation this copies the kit's ``tools/`` and the samples the tests use to a temporary
folder, runs the one test named on that unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must
match exactly once, and the mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a
dead test). The shape of ``tools/app_template/tests/canaries.py``.

    python3 tools/manifest/tests/canaries_combine.py      # exit 0 only when every canary is RED
"""
from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SAMPLES = ("s1_warranty", "s2_bins", "s3_price_audit", "s5_config_pack", "s11_approvals", "s20_capture", "s22_customer_loyalty",
           "s23_till_guard", "s25_gift_on_spend", "s32_coupon_rules", "s42_optical_prescriptions", "s46_payment_method_rules",
           "s57_donation_intake")
C = "tools/manifest/combine.py"
F = "tools/feed_client/feed_client.py"
T = "test_combine."

CANARIES = [
    ("a tagged Integration role is written", C,
     "    if tagged:\n        out = rename._walk(out, lambda s: re.sub(",
     "    if False:\n        out = rename._walk(out, lambda s: re.sub(",
     T + "Combine.test_canary_no_tagged_integration_role_is_written"),
    ("the dispatcher mounts two samples on the same route", C,
     "        strip = not all(p.startswith(f\"/{tag}/\") for p in paths)",
     "        strip = False",
     T + "Refusals.test_canary_two_samples_on_the_same_route_are_mounted_apart"),
    ("add overwrites a file the developer changed", C,
     "        if sha(cur) != rec[1]:                            # the developer changed it: kept, the sample's copy beside it",
     "        if False:",
     T + "Add.test_canary_add_never_overwrites_a_changed_file_or_entry"),
    ("add overwrites an entry the developer changed", C,
     "        elif sha(v) == rec[1]:                            # the sample does not change it: the developer's stays",
     "        elif False:",
     T + "Add.test_canary_add_never_overwrites_a_changed_file_or_entry"),
    ("an entry the developer changed is never refused", C,
     "        elif sha(cur) != rec[1]:                          # the developer changed it, and the sample must change it",
     "        elif False:",
     T + "Add.test_m04_refused_when_the_sample_must_change_an_entry_you_changed"),
    ("a link is followed", C,
     "    if links:\n        raise Refused(", "    if False:\n        raise Refused(",
     T + "ReviewFolds.test_add_never_writes_through_a_link"),
    ("an event is marked done before every part has handled it", F,
     "                       if all(p in by[ev[\"id\"]] for p in self.reads if self.wants(p, ev))]",
     "                       if any(p in by[ev[\"id\"]] for p in self.reads if self.wants(p, ev))]",
     T + "OneReader.test_a_part_that_fails_leaves_the_event_and_the_other_part_is_not_run_twice"),
    ("a part handled again for an event it has handled", F,
     "            if part in shop[\"handed\"].get(ev[\"id\"], ()) or store.seen(mine[\"id\"]) \\\n",
     "            if False and (part in shop[\"handed\"].get(ev[\"id\"], ()) or store.seen(mine[\"id\"])) \\\n",
     T + "OneReader.test_a_part_that_fails_leaves_the_event_and_the_other_part_is_not_run_twice"),
    ("a part handled again in a new copy of the function", F,
     "                kept = (self.ledger.get(self.record(feed)) or {}).get(\"events\") or {} if self.ledger is not None else {}",
     "                kept = {}",
     T + "OneReader.test_a_part_that_handled_an_event_is_not_run_again_in_a_new_copy_of_the_function"),
    ("S3's code is left out of the app", C, "SKIP_FILES = {\"outside/manifest.json\"}", "SKIP_FILES = set()\nSKIP_TOP.add(\"outside\")",
     T + "ReadersUnderTheirNames.test_s3_combines_with_another_reader_and_its_part_runs"),
    ("a part reads the feed on its own in an app", "tools/manifest/combined/app.py",
     "    sys.modules[HANDOFF_MODULE] = module\n", "    pass\n",
     T + "OneReader.test_one_sale_reaches_both_parts_from_one_read"),
    ("a sample with a server of its own and no hosting order is made into an app", C,
     "        if own_server(p) and not handler_of(p):", "        if routes(app_view(p)) and not handler_of(p):",
     T + "Refusals.test_m34_a_sample_that_answers_the_till_from_its_own_server"),
    ("add counts only the added sample against the limits", C, "    limits(others + [part])", "    limits([part])",
     T + "ReviewFolds.test_add_gives_the_limits_words_over_the_whole_app"),
    ("a refused add still writes", C,
     "        rc, verdict = kit_check(staged)\n        if rc:\n            raise Refused(f\"Not added",
     "        rc, verdict = kit_check(staged)\n        _finish(app_folder, staged)\n        if rc:\n            raise Refused(f\"Not added",
     T + "Add.test_a_refusal_by_the_kits_check_changes_nothing"),
]


def copy_kit(dest: str) -> None:
    shutil.copytree(os.path.join(KIT, "tools"), os.path.join(dest, "tools"),
                    ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    for s in SAMPLES:
        shutil.copytree(os.path.join(KIT, "samples", s), os.path.join(dest, "samples", s),
                        ignore=shutil.ignore_patterns("__pycache__"))


def run_test(root: str, test: str) -> tuple[bool, str]:
    env = dict(os.environ, PARTNER_KIT=root, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(root, "tools", "manifest", "tests"),
                       env=env, capture_output=True, text=True, timeout=1800)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]


def run(name, path, anchor, mutant, test) -> str:
    with tempfile.TemporaryDirectory() as d:
        copy_kit(d)
        ok, why = run_test(d, test)
        if not ok:
            return f"BROKEN {name} — {test} fails unmutated: {why}"
        f = os.path.join(d, path)
        text = open(f, encoding="utf-8").read()
        if text.count(anchor) != 1:
            return f"BROKEN {name} — the anchor matches {text.count(anchor)} times"
        open(f, "w", encoding="utf-8").write(text.replace(anchor, mutant))
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError as e:
            return f"BROKEN {name} — the mutant does not compile: {e}"
        ok, why = run_test(d, test)
        return f"{'GREEN ' if ok else 'RED   '} {name} — {test} — {why}"


def main() -> int:
    lines = [run(*c) for c in CANARIES]
    print("\n".join(lines))
    red = sum(l.startswith("RED") for l in lines)
    print(f"{red} of {len(lines)} canaries RED")
    return 0 if red == len(lines) else 1


if __name__ == "__main__":
    sys.exit(main())
