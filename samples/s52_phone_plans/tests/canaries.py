#!/usr/bin/env python3
"""S52's canaries: each test that guards a rule, a secret or a retailer's account must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S51's
(``samples/s51_refund_rules/tests/canaries.py``, S23's before it), copied: a defect there is a defect here.

    python3 samples/s52_phone_plans/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = "test_service."
P, A, W = "service/plans.py", "service/app.py", "service/worker.py"

CANARIES = [
    # the plan's line is priced before payment: the price list follows the telecom company's price for the account
    ("a new plan price is written to the price list", P,
     '            out.append({"item_code": p["code"], "rate": rate, "name": None})', "            pass",
     T + "AfterPayment.test_the_plans_prices_follow_this_retailers_account"),
    ("a moved price moves the existing row", P,
     '            out.append({"item_code": p["code"], "rate": rate, "name": row["name"]})', "            pass",
     T + "AfterPayment.test_a_price_the_telecom_company_moves_moves_the_existing_row"),
    ("the till key carries no money", P,
     '    return {"message": {"title": plain(f"Plans for {o[\'phone\']}", 60),',
     '    return {"sale_attributes": [], "message": {"title": plain(f"Plans for {o[\'phone\']}", 60),',
     T + "PlansKey.test_the_key_answers_a_message_only_and_never_money"),
    # the price comes from the right retailer's account
    ("a price that no longer holds is refused", P, "        if charged != int(plan[\"price_minor\"]):", "        if False:",
     T + "CheckAtPay.test_the_price_comes_from_this_retailers_account_not_another"),
    ("the call is answered for the retailer that signed it", A,
     "        record = self.store.get(site) if site else None",
     "        record = self.store.get(self.store.sites()[0]) if site else None",
     T + "TwoRetailersAtOnce.test_two_retailers_at_the_same_moment_each_answered_with_its_own_account_only"),
    ("the account is read at the call, never kept", A,
     "            s = self.settings(self.shop(who))",
     "            s = getattr(self, '_kept', None) or self.settings(self.shop(who)); self._kept = s",
     T + "TwoRetailersAtOnce.test_the_service_holds_no_account_between_calls"),
    ("a plan needs the customer", P, '    if not customer or customer in s.get("walk_in", ()):', "    if False:",
     T + "CheckAtPay.test_a_plan_needs_the_customer_on_the_sale"),
    ("the walk-in customer is no customer", P, '    if not customer or customer in s.get("walk_in", ()):', "    if not customer:",
     T + "CheckAtPay.test_the_tills_walk_in_customer_is_no_customer_for_a_plan"),
    ("a plan needs a phone it fits", P, "        if phone is None:\n            return refuse(",
     "        if False:\n            return refuse(", T + "CheckAtPay.test_a_plan_needs_a_phone_it_fits"),
    # activation after payment
    ("the activation number is written back", W,
     '"activation_number": str(out.get("activation") or "")[:60]', '"activation_number": ""',
     T + "AfterPayment.test_activation_after_payment_writes_the_number_back"),
    ("the same line asks with the same key", W, 'w["sale"], idem=f"{site}/{w[\'key\']}")',
     'w["sale"], idem=f"{site}/{w[\'key\']}/{time.time()}")',
     T + "AfterPayment.test_the_telecom_company_answers_late_after_the_sale_is_paid"),
    ("a failed activation is not retried", W, 'row.get("status") in ("Activated", "Failed")',
     'row.get("status") in ("Activated",)',
     T + "AfterPayment.test_a_refused_activation_is_written_as_failed_with_the_reason_and_not_retried"),
    ("each plan goes on its own phone's serial", P, "        serial = serials[k] if k < len(serials) else \"\"",
     "        serial = serials[0] if serials else \"\"",
     T + "AfterPayment.test_two_plans_on_a_line_of_two_phones_each_go_on_its_own_phone"),
    ("a plan in an exchange is refused", P, "        if any(int(ln.get(\"qty_milli\") or 0) > 0 for ln in wanted):",
     "        if False:", T + "CheckAtPay.test_a_plan_sold_in_an_exchange_is_refused_never_sold_unconfirmed"),
    ("the activation key names the retailer", W, 'idem=f"{site}/{w[\'key\']}")', 'idem=w["key"])',
     T + "AfterPayment.test_the_activation_key_names_the_retailer_so_two_retailers_never_share_one"),
    ("prices only for the plans' item group", W, '    catalogue = [p for p in catalogue if p["code"] in ours]', "    pass",
     T + "AfterPayment.test_a_catalogue_code_outside_the_plans_group_never_gets_a_price"),
    ("a refused telecom key is retried", "service/telecom.py", "e.code in (401, 403, 429)", "e.code in (429,)",
     T + "AfterPayment.test_a_refused_telecom_key_is_retried_not_failed"),
    # the telecom company down
    ("down at the key is a plain message", A, "        except telecom.TelecomDown:\n            return plans.down_message()\n", "",
     T + "PlansKey.test_the_telecom_company_down_is_a_plain_message_and_nothing_is_added"),
    ("down at Pay refuses the plan", A, "        except telecom.TelecomDown:\n            return plans.refuse(",
     "        except telecom.TelecomDown:\n            return {'verdict': 'allow'} or plans.refuse(",
     T + "CheckAtPay.test_the_telecom_company_down_refuses_the_plan_in_plain_words"),
    # who may call
    ("an unknown retailer gets 401", A, "        if not secrets or not any(verify(ts, sig, raw, s) for s in secrets):",
     "        if secrets and not any(verify(ts, sig, raw, s) for s in secrets):",
     T + "Callers.test_an_unknown_retailer_gets_401"),
    ("the key's secret never signs the check", A,
     '        name = f"{self.app}:{self.app}_{KEY}" if route == PLANS else f"{self.app}:sub:{CHECK}"',
     '        name = f"{self.app}:{self.app}_{KEY}"', T + "Callers.test_the_keys_secret_does_not_sign_the_check"),
    ("a cut answer from the shop is unreachable, never a crash", "service/shop.py", 'ConnectionError, http.client.HTTPException) as e:',
     'ConnectionError) as e:',
     T + "AnswerCutShort.test_a_shop_answer_cut_short_is_the_shop_unreachable_never_a_crash"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s52-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local", "state"))
        for sub in ("tools/app_template", "tools/feed_client"):
            shutil.copytree(os.path.join(kit, sub), os.path.join(tmp, "r", sub), ignore=shutil.ignore_patterns("__pycache__"))
        cmd = [sys.executable, "-W", "ignore", "-m", "unittest", test]
        base = subprocess.run(cmd, cwd=os.path.join(dest, "tests"), capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f).read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        open(f, "w").write(src.replace(anchor, mutant))
        py_compile.compile(f, doraise=True)
        p = subprocess.run(cmd, cwd=os.path.join(dest, "tests"), capture_output=True, text=True, timeout=120)
        last = (p.stderr.strip().splitlines() or [""])[-1]
        return ("RED" if p.returncode else "GREEN"), last
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    bad = 0
    for c in CANARIES:
        verdict, last = run(*c)
        bad += verdict != "RED"
        print(f"{verdict:6} {c[0]} — {c[4]} — {last}", flush=True)
    print(f"{len(CANARIES) - bad} of {len(CANARIES)} canaries RED")
    sys.exit(1 if bad else 0)
