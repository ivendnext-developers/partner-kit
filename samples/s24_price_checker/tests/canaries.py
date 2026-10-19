#!/usr/bin/env python3
"""S24's canaries: each test that guards a rule, the shop's key or the kiosk's page must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and a Python
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is
S23's (`samples/s23_till_guard/tests/canaries.py`; a defect there is a defect here).

    python3 samples/s24_price_checker/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("a kiosk code is the framework's random name only", "price.py", "return s if CODE.fullmatch(s) else None",
     "return s or None", "test_price.Inputs.test_a_kiosk_code_is_the_frameworks_random_name_only"),
    ("a switched-off kiosk is not used", "price.py",
     'if not isinstance(record, dict) or not int(record.get("enabled") or 0):', "if not isinstance(record, dict):",
     "test_price.KioskRecord.test_a_switched_off_kiosk_is_not"),
    ("the kiosk's date only within a day", "price.py", "abs((d - today).days) <= 1", "True",
     "test_price.Inputs.test_the_kiosks_date_is_used_within_a_day_else_the_services"),
    ("no price rule is applied", "price.py", '"transaction_date": date, "ignore_pricing_rule": 1}',
     '"transaction_date": date, "ignore_pricing_rule": 0}',
     "test_price.PricerArgs.test_no_price_rule_is_applied_the_kiosk_shows_the_list_price"),
    ("never a rate from the scan", "price.py", '(("uom", "uom"), ("batch_no", "batch_no"))',
     '(("uom", "uom"), ("batch_no", "batch_no"), ("rate", "rate"))',
     "test_price.PricerArgs.test_never_a_rate_so_the_shops_pricer_writes_no_price_row"),
    ("no price is never shown as free", "price.py", "if price <= 0:", "if price < 0:",
     "test_price.Answer.test_no_price_on_the_list_is_never_shown_as_free"),
    ("only a public picture", "price.py", "image if PUBLIC_FILE.fullmatch(image) else None", "image or None",
     "test_price.Answer.test_only_a_public_picture_is_shown"),
    ("a bad scan never reaches the shop", "service/app.py", "        if not text:\n", "        if False:\n",
     "test_service.OneShop.test_a_bad_scan_or_body_is_refused_without_reading_the_shop"),
    ("a switched-off kiosk stops before the shop's items", "service/app.py", "            if not kiosk:\n",
     "            if False:\n", "test_service.OneShop.test_an_unknown_or_switched_off_kiosk_is_not_set_up"),
    ("a shop that did not connect is not read", "service/app.py", "        if not shop:", "        if False:",
     "test_service.ManyShops.test_a_shop_that_did_not_connect_is_not_set_up_and_is_not_read"),
    ("each shop is read with its own key", "service/app.py", '"key": record["secrets"][users[0]]', '"key": "-"',
     "test_service.ManyShops.test_each_shop_is_read_at_its_own_address_with_its_own_key"),
    ("the kiosk record is kept a minute only", "service/app.py", "if hit and now - hit[0] < KIOSK_TTL:", "if hit:",
     "test_service.OneShop.test_the_kiosk_record_is_kept_a_minute_so_switching_off_stops_it_within_a_minute"),
    ("a guesser cannot hammer the shop", "service/app.py", "return len(q) >= MISSES_PER_MINUTE", "return False",
     "test_service.OneShop.test_a_guesser_cannot_make_the_service_hammer_the_shop"),
    ("a guesser cannot lock a real kiosk out", "service/app.py", "if not known and self._missed(name):",
     "if self._missed(name):", "test_service.OneShop.test_a_guesser_cannot_make_the_service_hammer_the_shop"),
    ("the shops store down is unavailable, not a crash", "service/app.py",
     "        except Exception:               # noqa: BLE001 — the shops store did not answer",
     "        except ZeroDivisionError:               # noqa: BLE001 — the shops store did not answer",
     "test_service.OneShop.test_the_shops_store_down_is_unavailable"),
    ("every price says offers are worked out at the till", "service/kiosk.html",
     "<p class=\"note\">Any offer is worked out at the till.</p>", "",
     "test_service.Page.test_every_price_says_offers_are_worked_out_at_the_till"),
    ("a 404 is 'no kiosk' only when it names the record", "service/app.py",
     'if e.code == 404 and f"{prefix} Kiosk {code}".encode() in body:', "if e.code == 404:",
     "test_service.ShopApi.test_a_404_that_does_not_name_the_record_is_unreadable_never_no_kiosk"),
    ("only the shop's 417 is 'not on sale'", "service/app.py", "if e.code == 417:       # the pricer",
     "if e.code in (404, 417):  # the pricer",
     "test_service.ShopApi.test_the_shops_refusals"),
    ("never a rate to the shop", "service/app.py",
     '        if "rate" in args:      # an explicit refusal', '        if False:      # an explicit refusal',
     "test_service.ShopApi.test_never_a_rate"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)",
     "urllib.request.build_opener()", "test_service.ShopApi.test_a_redirect_is_not_followed"),
    ("the page's content policy", "service/app.py", "\"default-src 'none'; script-src 'self'; ", "\"default-src *; ",
     "test_service.Page.test_the_page_is_served_with_a_strict_content_policy_and_no_inline_script"),
    ("the kiosk draws with text only", "service/kiosk.js", 'el("item").textContent = a.item;',
     'el("item").innerHTML = a.item;', "test_service.Page.test_the_script_draws_with_text_only"),
    ("a hosted copy is connected: the manifest names the service", "manifest.json",
     ' "allowed_urls": [\n  "https://prc.partner.example"\n ],\n', "",
     "test_manifest.Manifest.test_the_shop_sends_nothing_outside_but_the_handshake"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s24-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local"))
        for sub in ("tools/manifest", "tools/app_template"):
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
