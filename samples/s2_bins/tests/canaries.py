#!/usr/bin/env python3
"""S2's canaries for its hosted till key (``service/where.py``): each test that guards the signature, a shop's own secret
and key, or the till's own store must go RED when that rule is broken. The runner is S23's (a defect there is a defect
here: samples/s23_till_guard/tests/canaries.py): copy, run the test unmutated (it must pass), apply ONE change (the anchor
must match once and the mutant compile), run it again, report RED (caught) or GREEN (a dead test).

    python3 samples/s2_bins/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = "service/where.py"

CANARIES = [
    ("the signature is checked", W, "if not secrets or not verified(secrets, headers, raw):", "if not secrets:",
     "test_where.OneShop.test_a_wrong_secret_or_an_old_timestamp_is_refused"),
    ("an old timestamp is refused", W, "abs(time.time() - int(ts)) > SKEW_S", "False",
     "test_where.OneShop.test_a_wrong_secret_or_an_old_timestamp_is_refused"),
    ("the signature covers the body", W, 'ts.encode() + b"." + raw', 'ts.encode() + b"."',
     "test_where.OneShop.test_a_body_changed_after_signing_is_refused"),
    ("only the till key's own secret", W, 'f"{self.app}:{KEY}"', 'f"{self.app}:{KEY}") + shops.secrets_for(record, "IVENDNEXT BLN x"',
     "test_where.ManyShops.test_only_the_till_keys_own_secret_and_only_for_its_shop"),
    ("each shop is read with its own key", W, 'shop = {"url": record["url"], "key": record["secrets"][users[0]]}',
     'shop = {"url": record["url"], "key": "ka:sa"}',
     "test_where.ManyShops.test_each_shop_is_answered_from_its_own_records_with_its_own_key"),
    ("another store's bin is never named (the read)", W, '[["store", "=", store]])',
     '[])', "test_where.OneShop.test_the_reads_ask_only_for_held_items_and_this_stores_locations"),
    ("another store's bin is never named (the Item In Bin read)", W, '[["item", "in", codes], ["qty", ">", 0], ["location", "in", sorted(kind_of)]])',
     '[["item", "in", codes], ["qty", ">", 0]])', "test_where.OneShop.test_the_reads_ask_only_for_held_items_and_this_stores_locations"),
    ("another store's bin is never named (held again)", W, "for r in held if r.get(\"location\") in kind_of]", "for r in held if r.get(\"location\")]",
     "test_where.OneShop.test_a_shop_that_answers_more_than_asked_still_never_names_another_stores_bin"),
    ("a location's store is held again", W, "if loc.get(\"store\") == store}", "if True}",
     "test_where.OneShop.test_a_shop_that_answers_more_than_asked_still_never_names_another_stores_bin"),
    ("the read asks only for a quantity above 0 (its wording; core drops 0 again)", W, '["qty", ">", 0], ["location"', '["qty", ">", -1], ["location"',
     "test_where.OneShop.test_the_reads_ask_only_for_held_items_and_this_stores_locations"),
    ("no user key: the set-up words, no read", W, "        if not shop:\n            note[\"shop\"] = \"no user\"\n            return 200, _warning(NOT_SET_UP)\n", "",
     "test_where.ManyShops.test_before_the_shop_hands_over_its_user_it_says_so"),
    ("the shop down: the words, not a 500", W, "        except ShopUnreadable as e:\n", "        except ZeroDivisionError as e:\n",
     "test_where.OneShop.test_the_shop_down_is_said_in_words"),
    ("a redirect is not followed", W, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     "test_where.ShopApi.test_a_redirect_is_not_followed"),
    ("a cut list is seen, never answered", W, "        if len(got) > ROWS_MAX:\n            raise TooMany(doctype)\n", "",
     "test_where.OneShop.test_more_rows_than_one_answer_takes_is_said_never_cut"),
    ("the reads share one deadline", W, "            if left <= 0:\n                raise ShopUnreadable(\"out of time\")\n", "",
     "test_where.OneShop.test_every_read_shares_one_deadline"),
    ("a refused key is a set-up problem", W, "words = {401: REFUSED, 403: NO_RIGHTS}.get(e.code, UNREADABLE)", "words = UNREADABLE",
     "test_where.OneShop.test_a_refused_key_is_a_set_up_problem_not_an_outage"),
    ("a non-ASCII digit is refused", W, "if not (ts.isascii() and ts.isdigit())", "if not ts.isdigit()",
     "test_where.OneShop.test_a_timestamp_that_is_not_plain_digits_is_refused_not_a_crash"),
    ("the wire asks one more row than an answer takes", W, '"limit_page_length": str(ROWS_MAX + 1)', '"limit_page_length": str(ROWS_MAX)',
     "test_where.ShopApi.test_a_list_read_sends_the_key_the_fields_and_the_filters"),
    ("a read gets only the time left", W, "timeout=min(READ_TIMEOUT, left)", "timeout=READ_TIMEOUT",
     "test_where.OneShop.test_a_read_gets_only_the_time_left"),
    ("the manifest fills Location from the bin", "manifest.json", '"fetch_from": "bin.location"', '"fetch_from": "aisle.location"',
     "test_where.TheManifest.test_what_is_in_each_bin_fills_its_location_from_the_bin"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s2-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local"))
        for sub in ("tools/app_template", "tools/contracts", "contracts"):
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
