#!/usr/bin/env python3
"""The template's canaries: each check of the handshake and of a shop's call must go RED when it is removed. For each
mutation this copies the template to a temporary folder, runs the one test named on the UNMUTATED copy first (BROKEN
unless it passes: a test that fails for another reason proves nothing), applies ONE change (the anchor must match
exactly once, and the mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead
test).
The shape of samples/s22_customer_loyalty/tests/canaries.py.

    python3 tools/app_template/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("a key for another app", "service/shops.py", '    if payload["app"] != app:', "    if False:",
     "test_shops.KeyCheck.test_canary_a_key_for_another_app"),
    ("a key for another site", "service/shops.py", '    if payload["host"] != site:', "    if False:",
     "test_shops.KeyCheck.test_canary_a_key_for_another_site"),
    ("a paid key signed by F1", "service/shops.py", 'if public is None or payload["kind"] not in may_sign:', "if public is None:",
     "test_shops.KeyCheck.test_canary_a_paid_key_signed_by_f1"),
    ("a bad signature", "service/shops.py", "if sig is None or not ed25519.verify(base64.b64decode(public), pb, sig):", "if sig is None:",
     "test_shops.KeyCheck.test_canary_a_bad_signature"),
    ("a site the app does not know", "service/app.py", 'conf["store"].get(site), ',
     'conf["store"].get((conf["store"].sites() or [site])[0]), ',
     "test_shops.Service.test_canary_a_site_the_app_does_not_know"),
    ("another shop's secret", "service/app.py", 'conf["store"].get(site), ',
     'conf["store"].get((conf["store"].sites() or [site])[0]), ',
     "test_shops.Service.test_canary_another_shops_secret"),
    ("the route's own secret only", "service/app.py",
     "shops.secrets_for(conf[\"store\"].get(site), f\"{conf['app']}:{KEY}\")",
     '[v.encode() for v in ((conf["store"].get(site) or {}).get("secrets") or {}).values()]',
     "test_shops.Service.test_canary_another_records_secret_does_not_sign_this_route"),
    ("the header and the body name one site", "service/shops.py", 'if not site or body.get("site") != site:',
     "if not site:", "test_shops.Service.test_the_header_and_the_body_must_name_the_same_site"),
    ("disconnect checks the key", "service/shops.py", "    site, _ = _site_and_key(header_site, body, app, keys)\n",
     "    site = site_of(header_site)\n", "test_shops.Service.test_canary_disconnect_needs_this_shops_key"),
    ("a rotation keeps the old secret", "service/shops.py", '"previous": (old or {}).get("secrets") or {},',
     '"previous": {},', "test_shops.Service.test_a_second_connect_rotates_and_keeps_the_old_secret_for_the_overlap"),
    ("the shop is called back at its own address", "service/shops.py",
     '"url": f"{\'http\' if local else \'https\'}://{site}",',
     '"url": body.get("url") or f"{\'http\' if local else \'https\'}://{site}",',
     "test_shops.Service.test_the_shop_is_called_back_at_its_own_address_never_one_the_call_names"),
    ("a shop on this machine connects in local mode only", "service/shops.py",
     'if local and not getattr(store, "local", False):', "if False:",
     "test_shops.LocalMode.test_canary_a_shop_on_this_machine_without_local_mode"),
    ("a local key signs for a shop on this machine only", "service/shops.py",
     'if local and getattr(store, "local_keys", None):', 'if getattr(store, "local_keys", None):',
     "test_shops.LocalMode.test_canary_a_local_key_never_signs_for_another_site"),
    ("every other site keeps https in local mode", "service/shops.py",
     "f\"{'http' if local else 'https'}://{site}\"", "f\"{'http' if store.local else 'https'}://{site}\"",
     "test_shops.LocalMode.test_every_other_site_keeps_https_in_local_mode"),
    ("local mode never runs with the hosting's table", "service/shops.py",
     'if local and (env.get("IVN_SHOPS_TABLE") or "").strip():', "if False:",
     "test_shops.LocalMode.test_local_mode_is_refused_where_it_does_not_belong"),
    ("a shop connected in local mode is ignored without it", "service/shops.py",
     "        if not self.local and is_local(site):", "        if False:",
     "test_shops.LocalMode.test_canary_a_shop_connected_in_local_mode_is_ignored_without_it"),
    ("the shops listed outside local mode leave local ones out", "service/shops.py",
     " and (self.local or not is_local(n)))", ")",
     "test_shops.LocalMode.test_canary_a_shop_connected_in_local_mode_is_ignored_without_it"),
    ("a local key disconnects a shop on this machine only", "service/shops.py",
     'if site and is_local(site) and getattr(store, "local", False) and getattr(store, "local_keys", None):',
     'if getattr(store, "local_keys", None):',
     "test_shops.LocalMode.test_canary_a_local_key_never_disconnects_another_site"),
    ("a local keys file never names a pinned key", "service/shops.py",
     "    if set(keys) & set(LIBRARY_KEYS):", "    if False:",
     "test_shops.LocalMode.test_canary_a_local_keys_file_never_names_a_pinned_key"),
    ("keygen never replaces a pair unasked", "local_key.py",
     "    if secret_file.exists() and not force:", "    if False:",
     "test_shops.LocalMode.test_canary_keygen_never_replaces_a_pair_unasked"),
    ("an older secret file is made private too", "local_key.py",
     "    os.chmod(secret_file, 0o600)", "    pass",
     "test_shops.LocalMode.test_canary_keygen_never_replaces_a_pair_unasked"),
    ("local mode is never a hosting setting", "validate_app.py",
     '        if name in ("IVN_LOCAL", "IVN_LOCAL_LIBRARY_KEYS"):', "        if False:",
     "test_validate_app.Settings.test_canary_local_mode_is_never_a_hosting_setting"),
    ("a store that does not answer is never a pass", "service/app.py", "            code = 503\n"
     "            return code, {\"error\": \"unavailable\"}\n", "            secrets = []\n",
     "test_shops.Service.test_a_store_that_does_not_answer_is_503_never_a_pass"),
    # The function entry (service/function.py, LIB16): the load balancer's event must reach the signature check as the
    # exact bytes the shop signed, and its lower-case headers must still be found.
    ("the body's exact bytes", "service/function.py", 'else body.encode("utf-8")', 'else body.encode("ascii", "replace")',
     "test_function.OneShop.test_canary_the_bodys_exact_bytes_reach_the_signature_check"),
    ("a base64 body is decoded", "service/function.py",
     'raw = base64.b64decode(body) if event.get("isBase64Encoded") else', "raw = body.encode() if False else",
     "test_function.OneShop.test_canary_a_base64_body_is_decoded"),
    ("headers in any case", "service/function.py", "return self._h.get(name.lower(), default)",
     "return self._h.get(name, default)", "test_function.OneShop.test_canary_headers_are_found_in_any_case"),
    ("another shop's secret, as a function", "service/app.py", 'conf["store"].get(site), ',
     'conf["store"].get((conf["store"].sites() or [site])[0]), ',
     "test_function.ManyShops.test_canary_another_shops_secret_is_refused"),
    ("a claim the table refuses is not taken", "service/dynamo.py",
     'if str(e).endswith(" ConditionalCheckFailedException"):\n                return False',
     'if str(e).endswith(" ConditionalCheckFailedException"):\n                return True',
     "test_shops.Table.test_a_claim_is_one_conditional_write_and_a_refusal_is_false"),
    ("the table never lists a claim", "service/dynamo.py", ' if "|" not in i["site"]["S"]]', "]",
     "test_shops.Table.test_the_tables_sites_never_list_a_claim"),
    ("a fresh claim is held (file)", "service/shops.py", '.get("at", 0) > now - stale_s:', '.get("at", 0) > now:',
     "test_shops.FileClaim.test_a_claim_is_held_until_deleted_or_stale_and_never_listed"),
    ("the file never lists a claim", "service/shops.py", "if CLAIM_MARK not in n and (", "if (",
     "test_shops.FileClaim.test_a_claim_is_held_until_deleted_or_stale_and_never_listed"),
    ("a cut answer from the table is a store error, never a crash", "service/dynamo.py", 'ConnectionError, http.client.HTTPException) as e:',
     'ConnectionError) as e:',
     "test_shops.AnswerCutShort.test_a_table_answer_cut_short_is_a_store_error_never_a_crash"),
]


def run(name, path, anchor, mutant, test):
    tmp = tempfile.mkdtemp(prefix="template-canary-")
    try:
        dest = os.path.join(tmp, "app_template")
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:
            return "BROKEN", "the test fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f).read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        with open(f, "w") as out:
            out.write(src.replace(anchor, mutant))
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
