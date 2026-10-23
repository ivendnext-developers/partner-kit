#!/usr/bin/env python3
"""S39's canaries: each test that guards a rule, a secret, a reservation or a read of the shop must go RED when that rule is
broken. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test
named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S37's
(``samples/s37_age_check/tests/canaries.py``), itself S23's, copied: a defect there is a defect here.

    python3 samples/s39_pharmacy_counter/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M = "test_rules.", "test_service.", "test_manifest.ManifestTest."
RX, SV = "rxrules.py", "service/app.py"

CANARIES = [
    # who may sell
    ("a counter assistant is stopped", RX, 'if not ph or not ph["active"] or ph.get("delegate"):', "if False:",
     R + "WhoMaySell.test_a_counter_assistant_is_stopped_and_a_pharmacist_served"),
    ("a lapsed licence is refused", RX, 'ph["valid_until"] < today:', 'ph["valid_until"] < today - datetime.timedelta(days=9):',
     R + "WhoMaySell.test_a_pharmacist_past_valid_until_is_refused_on_the_day_after"),
    ("an inactive pharmacist is none", RX, 'not ph["active"] or ph.get("delegate")', 'ph.get("delegate")',
     R + "WhoMaySell.test_an_inactive_pharmacist_is_no_pharmacist"),
    ("the front sends medicine to the dispensary", RX, 'if route == "front":', 'if route == "nowhere":',
     R + "WhoMaySell.test_the_front_sends_prescription_medicine_to_the_dispensary"),
    # prescriptions
    ("no number is refused", RX, "        if not named:\n", "        if False:\n",
     R + "Prescriptions.test_no_prescription_number_is_refused"),
    ("another patient's prescription", RX, 'if rx["customer"] != ctx["customer"]:', "if False:",
     R + "Prescriptions.test_another_patients_prescription_is_refused"),
    ("the walk-in customer", RX, 'and shop["walk_in"]:', "and False:",
     R + "Prescriptions.test_the_walk_in_customer_is_refused"),
    ("a cancelled prescription", RX, 'if not rx["active"]:', "if False:",
     R + "Prescriptions.test_a_cancelled_prescription_is_refused"),
    ("validity from the date written", RX, 'today >= written + datetime.timedelta(days=r["validity"])',
     'today > written + datetime.timedelta(days=r["validity"])',
     R + "Prescriptions.test_validity_is_the_classes_from_the_date_written_and_its_last_day_sells"),
    ("refills are spent", RX, "        if left <= 1e-9:\n", "        if left < -1:\n",
     R + "Prescriptions.test_refills_are_spent_by_counted_dispensings"),
    ("a released dispensing gives its fill back", RX, 'return d["status"] == RETURNED if give_back else d["status"] in (RESERVED, DISPENSED)',
     'return d["status"] == RETURNED if give_back else d["status"] in (RESERVED, DISPENSED, RELEASED)',
     R + "Prescriptions.test_a_released_dispensing_gives_its_fill_back"),
    ("this sale's own reservation is not counted twice", RX, 'if counts(d) and d["sale_ref"] != ctx["sale_ref"]]', "if counts(d)]",
     R + "Prescriptions.test_this_sales_own_earlier_reservation_is_not_counted_twice"),
    ("a sale dispenses at most one fill", RX, 'if want > min(left, per_fill) + 1e-9:', "if want > left + 1e-9:",
     R + "Prescriptions.test_a_sale_dispenses_at_most_one_fill"),
    ("the schedule caps the fills", RX, '            fills = min(fills, r["max_fills"])\n', "            pass\n",
     R + "Prescriptions.test_the_schedule_caps_the_fills_a_prescription_authorises"),
    ("a retained prescription dispenses once", RX, 'if (rx["retained"] and mine) or', "if (False and mine) or",
     R + "Prescriptions.test_a_retained_prescription_dispenses_once_even_partly"),
    ("a changed prescription is refused", RX, 'if first and first["fingerprints"][rx["name"]] != fp:', "if False:",
     R + "Prescriptions.test_a_prescription_changed_after_its_first_dispense_is_refused"),
    ("the fingerprint holds the fills", RX, 'raw = json.dumps([rx["customer"], rx["date_written"], rx["fills"], rx["retained"], items])',
     'raw = json.dumps([rx["customer"], rx["date_written"], rx["retained"], items])',
     R + "Prescriptions.test_a_prescription_changed_after_its_first_dispense_is_refused"),
    ("the paper reference is the customer's", RX, 'if r["reference"] == ref and r["customer"] == customer]', 'if r["reference"] == ref]',
     R + "Prescriptions.test_the_paper_reference_finds_the_customers_record"),
    ("a register item off the prescription goes in its own sale", RX,
     'if r and r["own_sale"] and not any(it["item"] == lines[i]["item"] for x in found for it in x["items"]):', "if False:",
     R + "Prescriptions.test_a_register_item_not_on_the_prescription_goes_in_a_sale_of_its_own"),
    # the patient and the limits
    ("the identity fields", RX, 'if r and field in r["ids"] and not shop["customer_fields"].get(field):', "if False:",
     R + "Patient.test_a_controlled_sale_needs_the_customers_identity_fields"),
    ("a schedule may need the patient's consent", RX, '\n            ("needs_consent", "consent_date", "consent to keep their records"))', ")",
     R + "Patient.test_a_schedule_that_needs_consent_waits_for_the_patients_dated_consent"),
    ("the service reads the consent tick", SV, ' "needs_authority", "needs_consent",', ' "needs_authority",',
     S + "People.test_a_schedule_that_needs_consent_reads_only_whether_the_patients_consent_date_has_come"),
    ("a field answered both ways is unreadable", SV, '                if on_record and got["set"] == got["unset"]:\n', '                if False:\n',
     S + "People.test_a_shop_that_drops_a_filter_on_a_patient_field_is_unreadable_never_a_field_filled_in"),
    ("a consent dated ahead is no consent", SV, "if f in rxrules.DATED else", "if False else",
     S + "People.test_a_schedule_that_needs_consent_reads_only_whether_the_patients_consent_date_has_come"),
    ("a walk-in is refused a schedule that needs a patient field", RX, 'r["rx"] or r["freq"] or r["ids"]) and shop["walk_in"]',
     'r["rx"] or r["freq"]) and shop["walk_in"]', R + "Patient.test_a_walk_in_is_refused_a_schedule_that_needs_a_patient_field"),
    ("no market's code compared in the code", RX, 'RESERVED, DISPENSED, RELEASED, RETURNED = "Reserved",',
     'KEEP_IN = ("AE",)\nRESERVED, DISPENSED, RELEASED, RETURNED = "Reserved",', M + "test_no_market_in_the_apps_code_or_names"),
    ("no market's name in the service's code", SV, "KEPT_TTL = ", "SFDA_TTL = KEPT_TTL = ", M + "test_no_market_in_the_apps_code_or_names"),
    ("no market's name in the manifest's names", "manifest.json", '"fieldname": "pp_rxc_consent_by"', '"fieldname": "pp_rxc_sa_consent_by"',
     M + "test_no_market_in_the_apps_code_or_names"),
    ("no market's name in the code", RX, "REFS_MAX = 5 ", "KE_REFS = REFS_MAX = 5 ", M + "test_no_market_in_the_apps_code_or_names"),
    ("the cap adds the item's lines", RX, 'per_item[lines[i]["item"]] = per_item.get(lines[i]["item"], 0.0) + qty[i]',
     'per_item[lines[i]["item"]] = qty[i]', R + "Patient.test_the_quantity_cap_per_sale_adds_the_items_lines"),
    ("the frequency window", RX, "since = today - datetime.timedelta(days=days - 1)", "since = today - datetime.timedelta(days=days + 5)",
     R + "Patient.test_the_frequency_cap_counts_the_patients_window_and_this_sale"),
    ("directions from the item's default", RX, 'or (shop["items"].get(line["item"]) or {}).get("directions", "")', 'or ""',
     R + "Patient.test_directions_and_a_doctor_per_group_from_the_details_the_prescription_or_the_item"),
    ("the strictest validity", RX, "        return min(vals) if vals else 0\n", "        return max(vals) if vals else 0\n",
     R + "Schedules.test_the_strictest_of_two_axes_applies"),
    ("give-back only when every schedule says so", RX, '"gives_back": all(r["gives_back"] for r in rules)',
     '"gives_back": any(r["gives_back"] for r in rules)', R + "Schedules.test_the_strictest_of_two_axes_applies"),
    ("a reclassification waits for its date", RX, "if name and since <= today:", "if name:",
     R + "Schedules.test_an_items_own_rows_win_one_per_axis_the_latest_effective"),
    ("a strip counts in stock units", RX, 'return line["qty"] * f if f else None', 'return line["qty"] if f else None',
     R + "Schedules.test_a_unit_with_no_conversion_is_none_and_a_strip_counts_in_stock_units"),
    # returns
    ("dispensed medicine is not taken back", RX, 'if rules[i] and not rules[i]["returnable"]:', "if False:",
     R + "Returns.test_dispensed_medicine_is_not_taken_back"),
    ("a Desk return is judged whatever it came from", RX, 'if not (x["linked"] and x["qty"] > 0)]', 'if not x["linked"]]',
     R + "Returns.test_a_desk_line_from_a_linked_parent_is_not_checked_but_its_return_is"),
    ("a give-back counts only once booked", RX, 'return d["status"] == RETURNED if give_back', 'return True if give_back',
     R + "Counting.test_a_give_back_counts_only_once_its_return_is_booked"),
    # what the shop says
    ("a sale reference is compared lower-cased", RX, 'booked = shop["sales"].get(d["sale_ref"].strip().lower())',
     'booked = shop["sales"].get(d["sale_ref"])', R + "Counting.test_a_booked_sale_is_dispensed_a_cancelled_one_released"),
    ("an unbooked sale is released only when its day closes", RX, 'if d["pos_opening"] and d["pos_opening"] in shop["closed_days"]:',
     'if d["pos_opening"]:', R + "Counting.test_an_unbooked_sale_holds_until_its_day_closes_never_on_a_timer"),
    ("a deleted Desk document releases", RX, "if status is None or status == 2:", "if status == 2:",
     R + "Counting.test_a_desk_dispensing_follows_its_document"),
    # the service
    ("each route takes only its own secret", SV, "return \"-\", [self.secrets[route_key]], self.shop",
     "return \"-\", list(self.secrets.values()), self.shop", S + "Calls.test_each_route_takes_only_its_own_secret"),
    ("a shop that cannot be read is 503", SV, "        except (ShopUnreadable, ValueError) as e:       # the shop did not answer",
     "        except (ValueError,) as e:       # the shop did not answer",
     S + "Calls.test_a_shop_that_cannot_be_read_is_503_so_the_down_answer_applies"),
    ("an allowed prescription reserves", SV, "                        keep = self.reserve(shop, ctx, dispensings, answer[\"record\"], today)",
     "                        keep = None", S + "Dispensing.test_an_allowed_prescription_reserves_the_patients_next_number"),
    ("Pay pressed again keeps the reservation", SV, 'keep = next((d["name"] for d in mine if rxrules.same_record(d, answer["record"])), None)',
     "keep = None", S + "Dispensing.test_pay_pressed_again_keeps_the_same_reservation"),
    ("a changed basket releases the old reservation", SV, '            if d["sale_ref"] == ctx["sale_ref"] and d["status"] == rxrules.RESERVED and d["name"] != keep:',
     "            if False:", S + "Dispensing.test_a_changed_basket_replaces_and_releases_its_earlier_reservation"),
    ("the medicine taken off releases", SV, "            self.release_earlier(shop, ctx, keep=None)\n            return {\"verdict\": \"allow\"}",
     "            return {\"verdict\": \"allow\"}", S + "Dispensing.test_the_medicine_taken_off_releases_the_reservation"),
    ("another till took the number: decide again", SV, "                        continue                         # another till",
     "                        return {\"verdict\": \"allow\"}                         # another till",
     S + "Dispensing.test_two_tills_one_fill_one_insert_wins_and_the_other_decides_again"),
    ("a closed day is read back", SV, 'out["closed_days"] = {r["name"] for r in rows if r.get("status") == "Closed"}',
     'out["closed_days"] = set()', S + "Dispensing.test_an_unbooked_sale_releases_its_fill_only_when_its_day_closes"),
    ("a booked sale is read back", SV, '["is_return", "=", 0]])))', '["is_return", "=", 9]])))',
     S + "Dispensing.test_a_booked_sale_reads_dispensed_and_its_status_is_written_back"),
    ("the profile's own customer is a walk-in", SV, 'custs = {r.get("customer") for r in self._list(shop, "POS Profile", ["name", "customer"]) if r.get("customer")}',
     "custs = set()", S + "People.test_the_profiles_own_default_customer_is_a_walk_in"),
    ("a strip is converted with the item's units", SV, "items, item_rows, units = self.item_data(shop, codes, any(x[\"uom\"] for x in ctx[\"lines\"]), today)",
     "items, item_rows, units = self.item_data(shop, codes, False, today)", S + "People.test_a_strip_counts_seven_against_the_prescription"),
    ("a cancelled order gives its fill back", SV, 'rows = {r["name"]: (r.get("docstatus"), r.get("customer"))',
     'rows = {r["name"]: (1, r.get("customer"))', S + "Desk.test_a_cancelled_order_gives_its_fill_back"),
    ("a draft's save is never judged", SV, 'if point == "doccheck" and ctx["event"] != "submit":', "if False:",
     S + "Desk.test_a_drafts_save_is_never_judged"),
    # the Tier-S reviews' folds
    ("a variant's own row never hides its template's class", RX,
     '    for axis, n in own((items.get(item) or {}).get("template") or "").items():\n        per_axis.setdefault(axis, n)\n', "",
     R + "Schedules.test_a_variants_own_row_never_hides_its_templates_class_on_another_axis"),
    ("a delegate is not a pharmacist", RX, ' or ph.get("delegate"):', ":",
     R + "WhoMaySell.test_a_delegate_is_not_a_pharmacist_until_the_rule_is_ruled"),
    ("a post-dated prescription is refused", RX, "        if written > today:\n", "        if False:\n",
     R + "Prescriptions.test_a_prescription_dated_after_today_is_refused"),
    ("occasions are counted", RX, ' or (r["max_occasions"] and len(mine) >= r["max_occasions"])', "",
     R + "Prescriptions.test_occasions_are_counted_however_small_each_dispensing"),
    ("one drug per prescription", RX, 'if r["one_drug"] and len(', "if False and len(",
     R + "Prescriptions.test_one_drug_per_prescription"),
    ("the patient's name is never a record's name", RX, "return hashlib.sha256(customer.encode()).hexdigest()[:16]", "return customer",
     R + "Counting.test_the_next_number_and_the_same_record"),
    ("a paper number may hold a space", RX, 're.split(r"[,;]+"', 're.split(r"[\\s,;]+"',
     R + "Prescriptions.test_several_numbers_in_one_detail"),
    ("a variant's unit from its template", RX,
     ' or conversions.get(((items.get(line["item"]) or {}).get("template") or "", uom))', "",
     R + "Schedules.test_a_unit_with_no_conversion_is_none_and_a_strip_counts_in_stock_units"),
    ("the cap adds only lines with a rule", RX, "    for i in sold:\n        if rules[i]:\n            per_item[",
     "    for i in sold:\n        if True:\n            per_item[", R + "Schedules.test_an_unscheduled_line_in_an_unknown_unit_never_breaks_the_cap"),
    ("two equal capped lines are both recorded", RX, "        if i not in recorded:",
     '        if not any(x["item"] == lines[i]["item"] and x["qty"] == qty[i] for x in record_lines):',
     R + "Patient.test_two_equal_lines_of_a_capped_item_are_both_recorded"),
    ("a Desk line is linked only by its row", RX, 'if _text(x.get(k)) and _text(x.get(row))), "")', 'if _text(x.get(k))), "")',
     R + "Shapes.test_a_desk_check_reads_stock_qty_parents_and_the_apps_fields"),
    ("no sale reference, no judgement", RX, '    if not _text(ctx.get("sale_ref")):\n        raise ValueError',
     "    if False:\n        raise ValueError", R + "Shapes.test_a_till_check_with_no_sale_reference_is_not_judged"),
    ("a reused document name is not this one", RX, 'and owner != d["customer"]:', "and False:",
     R + "Counting.test_a_desk_document_the_shop_hides_is_never_read_as_gone"),
    ("a hidden document keeps its fill", SV, 'rows[n] = ("hidden", None)', "rows[n] = None",
     S + "Desk.test_a_document_the_shop_will_not_show_keeps_its_fill"),
    ("identity: whether set, never the value", SV, 'pool.submit(self._list, shop, self.dt("Patient"), ["name", "customer"], mine + c)',
     'pool.submit(self._list, shop, self.dt("Patient"), ["name", "customer", "id_number"], mine + c)',
     S + "People.test_the_identity_values_never_leave_the_shop_only_whether_they_are_set"),
    ("every profile's default customer is a walk-in", SV, '                or ctx["customer"] in self.profile_customers(name, shop))', ")",
     S + "People.test_another_profiles_default_customer_is_a_walk_in_on_the_desk_too"),
    ("no reservation after the till's budget", SV, "if self.clock() - started > RESERVE_BY:", "if False:",
     S + "Desk.test_a_reservation_is_never_made_after_the_tills_budget"),
    # the last review's folds
    ("an item not on the prescription", RX, '            return _refuse(line, "is not on the prescription this sale names.")\n',
     '            continue\n', R + "Prescriptions.test_an_item_not_on_the_prescription_is_refused"),
    ("a scheduled line in an unconvertible unit is refused", RX, 'if rules[i] and qty[i] is None:', "if False:",
     R + "Prescriptions.test_a_scheduled_line_in_a_unit_with_no_conversion_is_refused"),
    ("an older press of Pay is released", RX, 'if newest is not None and newest.get(d["sale_ref"], d["name"]) != d["name"]:', "if False:",
     R + "Counting.test_only_the_newest_dispensing_of_a_sale_is_its_booking"),
    ("a status set by hand never outlives the shop", RX, '    newest = shop.get("newest")\n',
     '    newest = shop.get("newest")\n    if d["status"] == RELEASED:\n        return RELEASED\n',
     R + "Counting.test_a_status_set_by_hand_never_outlives_what_the_shop_shows"),
    ("a quantity is given back once", RX, 'take = min(left, x["qty"] - given.get((d["name"], x["item"]), 0.0))', 'take = min(left, x["qty"])',
     R + "Returns.test_a_quantity_is_given_back_once_and_only_by_a_return_that_moves_stock"),
    ("only a stock-moving return gives back", RX, 'for i in back if ctx.get("moves_stock", True) else ():', "for i in back:",
     R + "Returns.test_a_quantity_is_given_back_once_and_only_by_a_return_that_moves_stock"),
    ("a delivery made from an invoice is in the chain", RX, '("against_sales_invoice", "si_detail"), ', "",
     R + "Shapes.test_a_desk_check_reads_stock_qty_parents_and_the_apps_fields"),
    # the manifest
    ("the dispensary refuses when down", "manifest.json", '"timeout_seconds": 5,\n   "down_answer": "refuse"\n  },\n  {\n   "key": "front"',
     '"timeout_seconds": 5,\n   "down_answer": "allow_and_flag"\n  },\n  {\n   "key": "front"',
     M + "test_five_services_switched_off_with_the_designs_down_answers"),
    ("only the pharmacist-in-charge writes the list", "manifest.json",
     "\"permissions\": [\n    {\n     \"role\": \"PP RXC Pharmacist in Charge\",\n     \"read\": 1,\n     \"write\": 1,\n     \"create\": 1,\n     \"delete\": 1,\n     \"report\": 1,\n     \"export\": 1,\n     \"share\": 0,\n     \"print\": 1,\n     \"email\": 0\n    },\n    {\n     \"role\": \"System Manager\",\n     \"read\": 1,\n     \"write\": 0,\n     \"create\": 0,\n     \"delete\": 0,\n     \"report\": 1,\n     \"export\": 1,\n     \"share\": 0,\n     \"print\": 1,\n     \"email\": 0\n    },\n    {\n     \"role\": \"PP RXC Pharmacist\",\n     \"read\": 1,\n     \"write\": 0,\n     \"create\": 0,\n     \"delete\": 0,\n     \"report\": 1,\n     \"export\": 1,\n     \"share\": 0,\n     \"print\": 1,\n     \"email\": 0\n    },\n    {\n     \"role\": \"PP RXC Integration\",\n     \"read\": 1,\n     \"write\": 0,\n     \"create\": 0,\n     \"delete\": 0,\n     \"report\": 0,\n     \"export\": 0,\n     \"share\": 0,\n     \"print\": 0,\n     \"email\": 0\n    }\n   ",
     "\"permissions\": [\n    {\n     \"role\": \"PP RXC Pharmacist in Charge\",\n     \"read\": 1,\n     \"write\": 1,\n     \"create\": 1,\n     \"delete\": 1,\n     \"report\": 1,\n     \"export\": 1,\n     \"share\": 0,\n     \"print\": 1,\n     \"email\": 0\n    },\n    {\n     \"role\": \"System Manager\",\n     \"read\": 1,\n     \"write\": 1,\n     \"create\": 0,\n     \"delete\": 0,\n     \"report\": 1,\n     \"export\": 1,\n     \"share\": 0,\n     \"print\": 1,\n     \"email\": 0\n    },\n    {\n     \"role\": \"PP RXC Pharmacist\",\n     \"read\": 1,\n     \"write\": 0,\n     \"create\": 0,\n     \"delete\": 0,\n     \"report\": 1,\n     \"export\": 1,\n     \"share\": 0,\n     \"print\": 1,\n     \"email\": 0\n    },\n    {\n     \"role\": \"PP RXC Integration\",\n     \"read\": 1,\n     \"write\": 0,\n     \"create\": 0,\n     \"delete\": 0,\n     \"report\": 0,\n     \"export\": 0,\n     \"share\": 0,\n     \"print\": 0,\n     \"email\": 0\n    }\n   ",
     M + "test_who_writes_what"),
    ("the pharmacist-in-charge cannot delete a prescription", "manifest.json",
     '"role": "PP RXC Pharmacist in Charge",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 0,\n     "report": 1,\n     "export": 1,',
     '"role": "PP RXC Pharmacist in Charge",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,\n     "report": 1,\n     "export": 1,',
     M + "test_only_the_records_officer_destroys_a_prescription_or_a_dispensing"),
    # 0.1.2 (PH-B1d): the patient's own record
    ("the patient's fields are read off the patient record", SV, 'has = {f: {k: pool.submit(self._list, shop, self.dt("Patient"), ["name", "customer"], mine + c)',
     'has = {f: {k: pool.submit(self._list, shop, "Customer", ["name", "customer"], mine + c)', S + "People.test_the_identity_values_never_leave_the_shop_only_whether_they_are_set"),
    ("a customer with no patient record has nothing on record", SV, "                filled[f] = got[\"set\"] and got.get(\"due\", True)",
     "                filled[f] = (got[\"set\"] or not on_record) and got.get(\"due\", True)",
     S + "People.test_a_customer_with_no_patient_record_has_nothing_on_record"),
    ("an answer for an unlisted patient record is unreadable", SV, "                if not on_record and (got[\"set\"] or got[\"unset\"]):\n",
     "                if False:\n", S + "People.test_a_shop_that_answers_a_field_for_a_patient_record_it_does_not_list_is_unreadable"),
    ("the patient record is named by a hash, never its customer", "manifest.json", '"autoname": "hash",\n   "track_changes": 1,\n   "title_field": "customer"',
     '"autoname": "field:customer",\n   "track_changes": 1,\n   "title_field": "customer"',
     M + "test_the_patient_record_holds_every_field_a_schedule_may_need_and_only_the_pharmacists_read_it"),
    ("the service only reads a patient", "manifest.json",
     '"role": "PP RXC Integration",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 0,\n     "report": 0,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    },\n    {\n     "role": "PP RXC Records Officer",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 1,\n     "report": 1,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    },\n    {\n     "role": "System Manager",',
     '"role": "PP RXC Integration",\n     "read": 1,\n     "write": 1,\n     "create": 0,\n     "delete": 0,\n     "report": 0,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    },\n    {\n     "role": "PP RXC Records Officer",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 1,\n     "report": 1,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    },\n    {\n     "role": "System Manager",',
     M + "test_the_patient_record_holds_every_field_a_schedule_may_need_and_only_the_pharmacists_read_it"),
    ("the site's administrator only reads a patient", "manifest.json",
     '    {\n     "role": "System Manager",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 0,\n     "report": 0,\n     "export": 0,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    }\n   ]',
     '    {\n     "role": "System Manager",\n     "read": 1,\n     "write": 0,\n     "create": 0,\n     "delete": 0,\n     "report": 1,\n     "export": 1,\n     "share": 0,\n     "print": 0,\n     "email": 0\n    }\n   ]',
     M + "test_the_patient_record_holds_every_field_a_schedule_may_need_and_only_the_pharmacists_read_it"),
    ("an answer about another customer is unreadable", SV, '                if any(r.get("customer") != cust for r in rows):\n',
     '                if False:\n', S + "People.test_an_answer_about_another_customers_patient_record_is_unreadable"),
    ("no market's name in an f-string", SV, "KEPT_TTL = ", 'PH_NOTE = f"Kenya {1}"\nKEPT_TTL = ', M + "test_no_market_in_the_apps_code_or_names"),
    ("the identity refusal fits whole", RX, '"needs the customer\'s {words}. Add it on their patient record on the Desk."',
     '"needs the customer\'s {words}. Add it on their patient record, on the Desk, as the pharmacist on duty, today, before you press Pay."',
     R + "Patient.test_every_identity_refusal_fits_the_tills_sentence_whole"),
    ("one patient record per customer", "manifest.json", '"label": "Customer (the patient)",\n     "options": "Customer",\n     "reqd": 1,\n     "unique": 1,',
     '"label": "Customer (the patient)",\n     "options": "Customer",\n     "reqd": 1,\n     "unique": 0,',
     M + "test_the_patient_record_holds_every_field_a_schedule_may_need_and_only_the_pharmacists_read_it"),
    ("0.1.1's Customer fields show only while they hold a value", "manifest.json", '"depends_on": "pp_rxc_consent_by"', '"depends_on": ""',
     M + "test_the_customer_fields_of_0_1_1_stay_empty_and_show_only_while_they_hold_a_value"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s39-canary-")
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
