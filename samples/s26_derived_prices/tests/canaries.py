#!/usr/bin/env python3
"""S26's canaries: each money, idempotency and ownership test must go RED when the rule it guards is broken. For each
mutation this copies the sample (and the feed client it imports) to a temporary folder, runs the one test named on that
unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must
compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S25's
(`samples/s25_gift_on_spend/tests/canaries.py` @ e68ede3; a defect there is a defect here).

    python3 samples/s26_derived_prices/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P, S = "prices.py", "sync.py"

CANARIES = [
    # the arithmetic
    ("a price is a Decimal through its text", P, "return Decimal(str(v if v not in (None, \"\") else 0))",
     "return Decimal(float(v if v not in (None, \"\") else 0))", "test_s26.Formula.test_rounding_table"),
    ("half up, not banker's rounding", P, '"Nearest": ROUND_HALF_UP', '"Nearest": __import__("decimal").ROUND_HALF_EVEN',
     "test_s26.Formula.test_rounding_table"),
    ("the offset is added", P, "raw = D(source_rate) * rule.factor + rule.offset", "raw = D(source_rate) * rule.factor",
     "test_s26.Formula.test_rounding_table"),
    ("the floor holds", P, "rate = max(rate, rule.floor)", "rate = rate", "test_s26.Formula.test_the_floor_raises_and_says_so"),
    ("a -0.00 is raised to the floor and said", P, "raised = rate < rule.floor or (rate == 0 and rate.is_signed())",
     "raised = rate < rule.floor", "test_s26.Formula.test_the_floor_raises_and_says_so"),
    ("the rule's decimal places", P, "return rate.quantize(Decimal(1).scaleb(-rule.places), rounding=ROUND_HALF_UP), raised",
     "return rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), raised", "test_s26.Formula.test_a_zero_decimal_currency"),
    # the rule checks
    ("a loop is refused", P, "for n in [n for n in ok if _closes_a_loop(ok, ok[n])]:", "for n in []:",
     "test_s26.Loop.test_a_loop_writes_nothing_and_is_reported"),
    ("one list has one rule", P, "        if len(names) > 1:", "        if False:",
     "test_s26.RuleChecks.test_two_rules_on_one_target_are_both_refused"),
    ("two currencies are refused", P, "elif currency[r.source] != currency[r.target]:", "elif False:",
     "test_s26.RuleChecks.test_each_bad_rule_is_refused_with_its_reason"),
    ("a step or floor finer than the places is refused", P,
     "elif max(_decimals(Decimal(r.step)), _decimals(r.floor)) > r.places:", "elif False:",
     "test_s26.RuleChecks.test_a_step_or_floor_finer_than_the_places_is_refused"),
    # one event, one row; a person's price
    ("the lookup by stamp (a replay finds its own row)", S, "mine = self.shop.stamped(rule.target, st)", "mine = []",
     "test_s26.Feed.test_one_event_twice_writes_one_row"),
    ("an unchanged price is not written again", S, "            if mine and P.D(mine[0][\"price_list_rate\"]) == rate and", "            if False and",
     "test_s26.Feed.test_one_event_twice_writes_one_row"),
    ("a person's price at the target is held", S, "            if theirs:\n", "            if False:\n", "test_s26.PersonsPrice.test_a_persons_price_at_the_target_is_held_and_reported"),
    ("a derived price a person changed is held", S, 'if mine and mine[0].get("modified_by") != self.me:', "if False:",
     "test_s26.PersonsPrice.test_a_derived_price_a_person_changed_is_held"),
    ("a row for one customer is not derived", P, 'return not (row.get("customer") or row.get("supplier") or row.get("batch_no"))',
     "return True", "test_s26.Feed.test_a_row_for_one_customer_is_not_derived"),
    ("an ended person's price does not block", S,
     'and (not r.get("valid_upto") or _day(r["valid_upto"]) >= today)]', "]",
     "test_s26.Folds.test_an_ended_persons_price_does_not_block"),
    ("another rule's row is named as such", S, 'if (row.get("note") or "").startswith(P.STAMP + " ")', "if False",
     "test_s26.Folds.test_a_row_left_by_another_rule_is_held_with_that_reason"),
    ("a rule back from off is worked out again", S,
     "            self.db.execute(f\"delete from backfill where rule not in ({','.join('?' * len(self.rules))})\", tuple(self.rules))",
     "            pass", "test_s26.Folds.test_a_rule_switched_off_and_on_again_is_worked_out_again"),
    ("a made row follows its source's unit", S, "    want = {\"item_code\": src[\"item_code\"], \"uom\": src[\"uom\"], \"price_list_rate\": str(rate),",
     "    want = {\"price_list_rate\": str(rate),", "test_s26.Folds.test_a_source_rows_unit_edited_moves_its_made_row"),
    ("a source row given a customer is no longer a source", S, "if row is None or not P.general(row):", "if row is None:",
     "test_s26.Folds.test_a_source_row_given_a_customer_ends_its_made_row"),
    ("a made row a person changed is not ended", S, "            if row.get(\"modified_by\") != self.me:\n                rep[\"held\"]",
     "            if False:\n                rep[\"held\"]", "test_s26.Folds.test_a_made_row_a_person_changed_is_not_ended_when_its_source_goes"),
    ("reconcile holds a changed row whose source is gone", S,
     "                if row.get(\"modified_by\") != self.me:\n                    held.append({\"rule\"",
     "                if False:\n                    held.append({\"rule\"", "test_s26.Folds.test_a_made_row_a_person_changed_is_not_ended_when_its_source_goes"),
    # chains and deletes
    ("the service carries its own write down the chain", S, "self.on_row(row, rep, depth=depth + 1)", "pass",
     "test_s26.Chain.test_a_chain_cascades_from_one_event"),
    ("a deleted source ends its made rows", S, "            self.on_gone(ev[\"doc_name\"], rep)", "            pass",
     "test_s26.Deleted.test_a_deleted_source_ends_only_the_rows_made_from_it"),
    # backfill
    ("a crash resumes at the saved page", S, "after = got[1] if got and got[0] == fp and not got[2] else \"\"", "after = \"\"",
     "test_s26.Backfill.test_a_crash_resumes_at_the_saved_page_and_writes_nothing_twice"),
    ("a changed rule is worked out again", S, "if got and got[0] == fp and got[2] and not only:", "if got and got[2] and not only:",
     "test_s26.Backfill.test_a_done_rule_is_not_run_again_until_its_numbers_change"),
    # reconcile
    ("reconcile names a wrong price", S, "elif P.D(row[\"price_list_rate\"]) != want:", "elif False:",
     "test_s26.Reconcile.test_each_planted_fault_is_named"),
    ("reconcile names a missing price", S, '                    diffs.append({**at, "what": "no target price", "want": str(want)})',
     "                    pass", "test_s26.Reconcile.test_each_planted_fault_is_named"),
    ("reconcile names a row whose source is gone", S, 'if note.split(" ")[-1] in names or', "if True or",
     "test_s26.Reconcile.test_each_planted_fault_is_named"),
    ("reconcile names a changed item or unit", S, "elif (row[\"item_code\"], row[\"uom\"]) != (s[\"item_code\"], s[\"uom\"]):",
     "elif False:", "test_s26.Reconcile.test_each_planted_fault_is_named"),
    ("reconcile names a lost end date", S, "elif _day(row.get(\"valid_upto\")) != _day(s.get(\"valid_upto\")):", "elif False:",
     "test_s26.Reconcile.test_each_planted_fault_is_named"),
    ("reconcile holds a person's change apart", S, "                elif row.get(\"modified_by\") != self.me:\n                    held.append",
     "                elif False:\n                    held.append", "test_s26.Reconcile.test_each_planted_fault_is_named"),
    ("the manifest names a rule by its name", "manifest.json", '"autoname": "field:rule_name"', '"autoname": "hash"',
     "test_manifest.Manifest.test_a_rule_is_named_by_its_short_name"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s26-canary-")
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
