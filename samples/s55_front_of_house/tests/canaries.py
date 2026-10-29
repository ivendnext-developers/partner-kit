#!/usr/bin/env python3
"""S55's canaries: each test that guards a shop's secret, its key, the double-booking guard, one check per party, the
guest's details staying in the shop, the floor, the door's refusals or the deposit's words must go RED when that check
is removed. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one
test named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once,
and the mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The
runner is S45's.

    python3 samples/s55_front_of_house/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, R, F = "test_service.ServiceTest.", "test_many_shops.", "test_rules.Rules.", "test_manifest.ManifestTest."
S, C = "service/app.py", "foh.py"

CANARIES = [
    # the press and the shop
    ("the signature is checked", S, "        if not secrets or all(foh.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", T + "test_p1_an_unsigned_or_wrongly_signed_press_is_refused"),
    ("each button its own secret", S, 'secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{sub}")]',
     'secrets = [v for k, v in (record or {}).get("secrets", {}).items() if ":sub:" in k]',
     M + "ManyShops.test_another_buttons_secret_another_shops_an_unknown_site_and_no_site_are_refused"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a press before the shop's key arrives is answered in words", S,
     "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n", "",
     M + "ManyShops.test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403):    # the shop refused the app's user: say so",
     "            if False:", T + "test_p3_the_apps_user_refused_is_said_in_words"),
    ("a press names its own record type", C, "    if not isinstance(rec, dict) or rec.get(\"doctype\") not in doctypes",
     "    if not isinstance(rec, dict)", T + "test_p2_a_press_on_the_wrong_record_is_refused_before_anything_is_read"),
    ("one record a press", C, "    if len(recs) != 1:", "    if not recs:",
     T + "test_p2_a_press_on_the_wrong_record_is_refused_before_anything_is_read"),
    ("a redirect is never followed", S, "host\n        return None\n", "host\n        return super().redirect_request(*a, **k)\n",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a record name is one path segment", S, '"/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))',
     'urllib.parse.quote(path, safe="/")', M + "ShopApi.test_a_record_name_is_one_path_segment"),
    # the double-booking guard
    ("Book reads the other bookings", S, "            clash = self._clash(door, r, row, start, exclude=name)\n            if clash:",
     "            clash = \"\"\n            if clash:", T + "test_b2_an_overlapping_booking_is_refused_and_named"),
    ("overlap is strict on both ends", C, "        if s < end and start < e:", "        if s <= end and start <= e:",
     R + "test_r2_overlap_is_strict_and_only_held_bookings_count"),
    ("only held bookings count", C, ' or o.get("status") not in HOLDING:', ":",
     R + "test_r2_overlap_is_strict_and_only_held_bookings_count"),
    ("a booking is not its own clash", C, '        if o.get("name") == exclude or', "        if",
     T + "test_b9_a_booked_reservation_pressed_again_stays_booked"),
    ("the other booking's own length", C, "        s, e = span(s, minutes_of(o, rows_by_store.get(o.get(\"store\")) or {}))",
     "        s, e = span(s, LENGTH)", R + "test_r2_overlap_is_strict_and_only_held_bookings_count"),
    ("the day before is read", C, " for k in (-1, 0, 1)]", " for k in (0, 1)]",
     T + "test_b5_a_booking_running_past_midnight_holds_the_next_day"),
    ("a clashing booking is released", S, '{"status": "Requested", "app_note": ("Not booked: " + clash)[:500]}',
     '{"app_note": ("Not booked: " + clash)[:500]}', T + "test_b2b_a_booked_reservation_moved_onto_another_is_released"),
    ("one press at a time", S, "        if age is not None and -LOCK_S < age < LOCK_S:\n            raise Busy()",
     "        if False:\n            raise Busy()", T + "test_b7_one_press_at_a_time_per_company"),
    ("the stamp is cleared", S, "        finally:\n            self._unlock(door, row[\"parent\"], mine)\n        end =",
     "        finally:\n            pass\n        end =", T + "test_b1_a_free_table_is_held"),
    ("a time is read as numbers", C, '        h, m, *s = (str(time_text or "").split(".")[0].split(":") + ["0"])[:3]',
     '        h, m, *s = str(time_text or "")[:8].split(":")', R + "test_r1_the_shops_times_are_read_as_numbers"),
    # one check per party
    ("the key is written only after the checks", S,
     '            try:                        # the key and the exact call, written only once the checks passed\n                door.update(doctype, name, {"seat_key": key, "seat_request": json.dumps(req, sort_keys=True),\n                                            "modified": r.get("modified")})',
     '            try:\n                pass', T + "test_s2_the_key_is_written_after_the_checks_and_before_the_door_under_the_stamp"),
    ("the stamp spans the door's call", S,
     "            return self._open(door, doctype, r, row, req, retry=False)\n        finally:\n            self._unlock(door, row[\"parent\"], mine)",
     "            pass\n        finally:\n            self._unlock(door, row[\"parent\"], mine)\n        return self._open(door, doctype, r, row, req, retry=False)",
     T + "test_s2_the_key_is_written_after_the_checks_and_before_the_door_under_the_stamp"),
    ("a retry sends the same call", S, "            if isinstance(req, dict):\n                return self._open(door, doctype, r, row, req, retry=True)",
     "            if False:\n                return self._open(door, doctype, r, row, req, retry=True)",
     T + "test_s3_a_lost_answer_then_a_second_press_opens_one_check"),
    ("a lost answer keeps the key", S, "            if not e.refused:\n                raise ", "            if False:\n                raise ",
     T + "test_s3_a_lost_answer_then_a_second_press_opens_one_check"),
    ("a refused retry keeps its key", S, "            if not retry:               # a first send the till refused opened nothing",
     "            if True:               # a first send the till refused opened nothing",
     T + "test_s10_a_refused_retry_keeps_its_key"),
    ("a seated party is not seated again", S, '        if r.get("check_name"):', "        if False:",
     T + "test_s4_a_seated_party_is_never_seated_twice"),
    ("a second press waits on the stamp", S, "        if age is not None and -LOCK_S < age < LOCK_S:\n            raise Busy()",
     "        if False:\n            raise Busy()", T + "test_s5_a_second_press_while_one_seats_is_told_to_wait_and_writes_no_key"),
    ("a record changed meanwhile is never keyed", S, "                if e.kind == STALE:     # the record changed since it was read",
     "                if False:     # the record changed since it was read",
     T + "test_s5_a_second_press_while_one_seats_is_told_to_wait_and_writes_no_key"),
    ("the floor is read before seating", S, "                    foh.place_busy(door.call(\"floor_status\", query={\"store\": r[\"store\"]}), r[\"place\"]):",
     "                    False:", T + "test_s6_a_table_with_an_open_check_is_refused_unless_the_store_allows_it"),
    ("the store may allow a second check", S, '            if not foh.num(row.get("second_check")) and \\',
     "            if \\", T + "test_s6_a_table_with_an_open_check_is_refused_unless_the_store_allows_it"),
    ("a walk-in checks the table's bookings", S, "            if clash:\n                raise Refusal(f\"Not seated:",
     "            if False:\n                raise Refusal(f\"Not seated:", T + "test_s7_a_walk_in_is_never_seated_on_a_table_booked_within_its_stay"),
    ("a refused first send clears the key", S, "                self._clear(door, doctype, name)\n                raise Refusal(self._door_words(e, r, row)) from None",
     "                raise Refusal(self._door_words(e, r, row)) from None", T + "test_s8_a_door_refusal_is_said_and_the_key_cleared"),
    ("the record takes the check's table", S, '        place = req.get("place") or r["place"]', '        place = r["place"]',
     T + "test_s12_a_retry_after_an_edit_seats_where_the_check_opened"),
    ("a seated party holds by its check, not its booking", C, 'HOLDING = ("Booked",) ', 'HOLDING = ("Booked", "Seated") ',
     T + "test_s13_a_party_seated_and_gone_does_not_hold_its_booked_time"),
    ("change releases the hold", S, '        door.update(foh.dt("Reservation"), name, {"status": "Requested",\n                                                  "app_note": "Changed:',
     '        door.update(foh.dt("Reservation"), name, {"status": "Booked",\n                                                  "app_note": "Changed:',
     T + "test_c1_change_booking_releases_the_hold_and_book_holds_the_new_slot"),
    ("change refuses a booking being seated", S, '        if r.get("status") != "Booked" or r.get("seat_key"):', '        if r.get("status") != "Booked":',
     T + "test_c2_only_a_booked_reservation_not_being_seated_is_changed"),
    ("an unfinished seat is never closed over", S, '        if r.get("seat_key"):\n            raise Refusal(f"A Seat for', '        if False:\n            raise Refusal(f"A Seat for',
     T + "test_n3_an_unfinished_seat_is_never_closed_over"),
    ("an unassigned user is told how to fix it", S, "        if e.kind in UNASSIGNED:", "        if False:",
     T + "test_s8_a_door_refusal_is_said_and_the_key_cleared"),
    ("the check carries the booking's reference", C, '"source": SOURCE, "source_ref": name[:TEXT_MAX]}', '"source": SOURCE}',
     R + "test_r5_the_check_carries_the_booking_never_the_guest"),
    ("the floor tile reads a table in use", C, '            return p.get("status") not in (None, "", "free") or bool(p.get("checks"))',
     "            return False", R + "test_r6_the_floor_shows_a_table_in_use"),
    # the guest stays in the shop
    ("the check never carries the guest's customer", C, '"label": label_of(name, party, deposit),',
     '"label": label_of(name, party, deposit), "suggested_customer": "CUST-ANA",',
     R + "test_r5_the_check_carries_the_booking_never_the_guest"),
    ("the guest's fields are the host's alone", "manifest.json",
     'the till.",\n   "read_roles": [\n    "PP FOH Host",', 'the till.",\n   "read_roles": [\n    "PP FOH Integration",',
     F + "test_m1_the_guests_details_are_the_hosts_alone"),
    ("no Version history of a guest", "manifest.json", '   "name": "PP FOH Reservation",\n', '   "name": "PP FOH Reservation",\n   "track_changes": 1,\n',
     F + "test_m9_no_version_history_and_a_booked_slot_is_read_only_in_the_form"),
    # the deposit
    ("the store's deposit rule is written", C, '    if (rule or "").startswith("Return"):', "    if False:",
     T + "test_n1_a_no_show_writes_the_stores_deposit_rule"),
    ("a closed booking stays closed", S, '        if r.get("status") not in foh.OPEN_STATES:\n            raise Refusal(f"{name} is {r.get(\'status\')}: only a requested or booked reservation can be marked',
     '        if False:\n            raise Refusal(f"{name} is {r.get(\'status\')}: only a requested or booked reservation can be marked',
     T + "test_n2_cancel_frees_the_table_and_a_closed_booking_stays_closed"),
    ("the function checks the signature too", S, "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'ok': 1}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     M + "AsAFunction.test_health_a_signed_press_either_body_form_and_a_refusal"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s55-canary-")
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
