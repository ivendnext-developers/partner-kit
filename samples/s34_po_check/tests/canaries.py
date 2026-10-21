#!/usr/bin/env python3
"""S34's canaries: each test that guards a rule or the secret must go RED when that rule is broken. For each mutation
this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on the unmutated
copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile),
runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's.

    python3 samples/s34_po_check/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CANARIES = [
    ("the signature is checked", "service/app.py", "if not secrets or all(po_check.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", "test_service.OneShop.test_a_wrong_secret_or_an_old_call_is_401"),
    ("each shop signs with its own secret", "service/app.py",
     'return [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{SUB}")]',
     'return [s.decode() for n in self.store.sites() for s in shops.secrets_for(self.store.get(n), f"{self.app}:sub:{SUB}")]',
     "test_service.ManyShops.test_each_shop_signs_with_its_own_secret"),
    ("an old timestamp is refused", "po_check.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     "test_service.OneShop.test_a_wrong_secret_or_an_old_call_is_401"),
    ("a held supplier is refused", "po_check.py", "    if hold:\n", "    if False:\n",
     "test_po_check.Rules.test_a_held_supplier_is_refused_with_the_erps_reason"),
    ("the hold is asked before the budget", "po_check.py", "    hold = erp.supplier_hold(f[\"supplier\"])\n",
     "    hold = None if f[\"grand_total\"][\"minor\"] > 1000000 else erp.supplier_hold(f[\"supplier\"])\n",
     "test_po_check.Rules.test_the_hold_is_asked_before_the_budget"),
    ("over the budget asks a purchase manager", "po_check.py", 'total["minor"] > left', 'total["minor"] > left * 10',
     "test_po_check.Rules.test_an_order_over_the_companys_budget_asks_a_purchase_manager"),
    ("the budget is the company's, never the submitter's", "po_check.py", 'erp.budget_left(ctx["company"], total["currency"])',
     'erp.budget_left(ctx["user"], total["currency"])', "test_po_check.Rules.test_the_budget_is_the_companys_whoever_submits"),
    ("exactly the budget left is filled", "po_check.py", 'total["minor"] > left', 'total["minor"] >= left',
     "test_po_check.Rules.test_an_order_just_inside_the_budget_is_filled"),
    ("a clear order is filled", "po_check.py", 'return {"verdict": "fill", "fields": {field: erp.order_number(ctx["name"])}}',
     'return {"verdict": "fill", "fields": {}}', "test_contract.ContractTest.test_every_answer_the_service_gives_holds"),
    ("the same order gets the same number", "erp.py", "            if po_name not in self.numbers:\n",
     "            if True:\n", "test_po_check.Rules.test_a_clear_order_is_filled_with_the_erps_number_once"),
    ("a draft is never held", "po_check.py", '    if ctx["event"] != "submit":\n', "    if False:\n",
     "test_po_check.Rules.test_a_draft_save_is_allowed"),
    ("sentences are plain", "po_check.py", '.replace("<", "").replace(">", "")', "",
     "test_po_check.Rules.test_sentences_are_plain_text_and_short"),
    ("a purchase order only", "po_check.py", 'if ctx.get("doctype") != "Purchase Order":', "if False:",
     "test_po_check.Shape.test_a_call_this_app_cannot_read_is_refused"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s34-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local"))
        for sub in ("tools/manifest", "tools/app_template", "tools/contracts", "contracts"):
            shutil.copytree(os.path.join(kit, sub), os.path.join(tmp, "r", sub), ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f).read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        open(f, "w").write(src.replace(anchor, mutant))
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
