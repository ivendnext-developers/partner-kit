#!/usr/bin/env python3
"""S49's canaries: each test that guards a retailer's secret, its key, the walk-in customer, a return, the rule's days
and tills, a customer asked once, a customer who asked to stop, where the next press starts, a press out of time, the
link's signature, an answer written once, or the service's words must go RED when that check is removed. For each
mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on the
unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must
compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S44's.

    python3 samples/s49_post_sale_feedback/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, S, D = "test_service.ServiceTest.", "test_service.ManyRetailers.", "service/app.py", "feedback.py"
R = "test_rules."

CANARIES = [
    ("the press's signature is checked", S, "        if not secrets or all(fb.verify(ts, sig, raw, s.decode()) for s in secrets):",
     "        if not secrets:", T + "test_s14_a_press_signed_with_another_secret_or_too_old_is_refused_before_any_read"),
    ("only rules are pressed", D, ' or rec.get("doctype") != RULE or not isinstance', " or not isinstance",
     T + "test_s15_a_press_on_anything_but_rules_is_refused_before_any_read"),
    ("each retailer's own user key, never Administrator's", S, ' and k != "user:Administrator")', ")",
     M + "test_each_retailer_is_checked_with_its_own_secret_and_written_with_its_own_key_under_the_librarys_prefix"),
    ("a refused user is said in words", S, "            if e.code in (401, 403):", "            if False:",
     T + "test_s13_the_apps_user_refused_by_the_retailer_is_said_in_words"),
    ("only submitted sales are read", S, '            f = [["docstatus", "=", 1], ["is_return", "=", 0],', '            f = [["is_return", "=", 0],',
     T + "test_s2_the_sales_read_asks_only_for_submitted_till_sales_of_the_rules_tills_and_days_oldest_first"),
    ("only submitted sales are asked", D, 'if s.get("docstatus") != 1 or s.get("is_return")', 'if s.get("is_return")',
     R + "Choose.test_only_the_rules_tills_and_days_and_never_a_walk_in_a_return_or_no_customer"),
    ("a return is never asked", D, ' or s.get("is_return") or not day', " or not day",
     R + "Choose.test_only_the_rules_tills_and_days_and_never_a_walk_in_a_return_or_no_customer"),
    ("the walk-in customer is never asked", D, "                or customer in walk_ins:", "                or False:",
     T + "test_s1_a_press_asks_each_customer_of_the_rules_new_sales_once_with_their_contact"),
    ("the rule's days", D, " or not day or day < first \\", " or not day \\",
     R + "Choose.test_only_the_rules_tills_and_days_and_never_a_walk_in_a_return_or_no_customer"),
    ("the rule's tills", D, '                or (rule.profiles and s.get("pos_profile") not in rule.profiles) or not customer',
     "                or not customer", R + "Choose.test_only_the_rules_tills_and_days_and_never_a_walk_in_a_return_or_no_customer"),
    ("a customer is asked once a press, their latest sale", D, "                latest[customer] = (s, mobile, email)",
     '                latest[s["name"]] = (s, mobile, email)', R + "Choose.test_a_customer_is_asked_once_their_latest_sale"),
    ("once across the press's rules", D, "    chosen = [v for k, v in latest.items() if k not in taken]",
     "    chosen = list(latest.values())", R + "Choose.test_a_customer_taken_by_another_rule_of_the_press_is_asked_by_that_rule_only"),
    ("a customer who asked to stop is never asked", D, "        if customer in stopped:", "        if False:",
     T + "test_s20_stop_these_messages_is_kept_even_without_an_answer_and_the_next_press_skips_them"),
    ("a sale already asked is never asked again", D, '        elif s["name"] in asked or customer in asked:', "        elif False:",
     T + "test_s3_a_second_press_starts_where_the_first_stopped_and_asks_nobody_twice"),
    ("a customer asked in the rule's days is not asked again", D, '        elif s["name"] in asked or customer in asked:',
     '        elif s["name"] in asked:', T + "test_s4_a_sale_already_asked_is_counted_never_asked_again"),
    ("the customer's own contact when the sale has none", D, '            mobile = phone_of(s.get("contact_mobile")) or c.get("mobile", "")',
     '            mobile = phone_of(s.get("contact_mobile"))', T + "test_s1_a_press_asks_each_customer_of_the_rules_new_sales_once_with_their_contact"),
    ("the next press starts where this one stopped", S, "            if mark != r.asked_up_to:", "            if False:",
     T + "test_s3_a_second_press_starts_where_the_first_stopped_and_asks_nobody_twice"),
    ("the press reads from its place", S, '                f.append(["creation", ">=", r.asked_up_to])', "                pass",
     T + "test_s3_a_second_press_starts_where_the_first_stopped_and_asks_nobody_twice"),
    ("a request not made holds the place", D, "    if stamps:\n        return min(stamps)", "    if False:\n        return min(stamps)",
     T + "test_s11_a_request_with_no_answer_is_tried_again_by_the_next_press"),
    ("only this request's own values are refused for good", S, "                if e.kind in REFUSED_ONE:",
     "                if e.code in (400, 417):", T + "test_s28_a_refusal_of_every_request_is_tried_again_by_the_next_press"),
    ("the reads go side by side", S, "            return list(pool.map(lambda f: f(), calls))", "            return [f() for f in calls]",
     "test_service.Together.test_the_reads_go_side_by_side"),
    ("the press says the reads took its time", S, "        if plan and not made and not failed:",
     "        if False:", T + "test_s29_reads_that_take_the_press_time_say_so"),
    ("no rule reaches past its links' life", D, "    if look > days:", "    if False:",
     T + "test_s6_a_rule_switched_off_or_misfilled_is_said_in_words_and_reads_no_sales"),
    ("a stop holds for the number and e-mail too", D, "            if (mobile and mobile in stopped) or (email and email.lower() in stopped):",
     "            if False:", T + "test_s31_a_customer_who_asked_to_stop_is_not_asked_on_another_record_with_the_same_number"),
    ("the stops read the number and e-mail", S, '''        stopped = {v for q in stops for v in (q.get("customer"), q.get("mobile"), (q.get("email") or "").lower()) if v}''',
     '''        stopped = {q.get("customer") for q in stops}''',
     T + "test_s31_a_customer_who_asked_to_stop_is_not_asked_on_another_record_with_the_same_number"),
    ("run's reads go side by side", S, "        got = self.together(\n", "        got = (lambda cs: [f() for f in cs])(\n",
     T + "test_s30_the_press_reads_side_by_side"),
    ("no last day on the sales read", S, '''["posting_date", ">=", fb.since(r, today).isoformat()]]''',
     '''["posting_date", ">=", fb.since(r, today).isoformat()], ["posting_date", "<=", today.isoformat()]]''',
     T + "test_s27_a_store_east_of_utc_whose_sale_is_dated_ahead_of_utcs_day_is_asked"),
    ("a refused request never holds the place", S, '                if how != "refused":', "                if True:",
     T + "test_s10_a_request_the_retailer_refuses_is_counted_and_never_holds_the_rules_place"),
    ("a request made meanwhile counts as made", S, "                if e.kind == DUPLICATE:", "                if False:",
     T + "test_s12_a_request_made_meanwhile_by_another_press_counts_as_made"),
    ("no request is started past WRITE_UNTIL", S, "            if self.clock() - t0 >= WRITE_UNTIL:", "            if False:",
     T + "test_s9_requests_not_started_in_time_wait_for_the_next_press_which_reads_them_again"),
    ("a press out of time after its reads writes nothing", S,
     "        self.left(t0)                                    # out of time after the reads: nothing is written\n", "",
     T + "test_s8_a_press_out_of_time_after_its_reads_writes_nothing"),
    ("the link is checked before any read", S, '        sale = fb.sale_of_token(site, body.get("t"), secrets) if site else None',
     '        sale = str(body.get("t") or "").rpartition(".")[0] or None', T + "test_s22_a_guessed_or_altered_link_never_reaches_the_retailer"),
    ("the signature is compared", D, "    return sale if any(hmac.compare_digest(sign(s, site, sale), sig) for s in secrets) else None",
     "    return sale", R + "Link.test_a_link_opens_for_its_own_site_and_sale_and_secret_only"),
    ("a link names its own retailer", D, '    mac = hmac.new(secret, f"psf1|{site}|{sale}".encode(), hashlib.sha256).digest()',
     '    mac = hmac.new(secret, f"psf1|{sale}".encode(), hashlib.sha256).digest()', R + "Link.test_a_link_opens_for_its_own_site_and_sale_and_secret_only"),
    ("an answer is written once, while open", S, '        if a is not None and page["state"] == "open":', "        if a is not None:",
     T + "test_s19_an_answer_is_written_once_in_english_with_its_comment"),
    ("a closed link takes no answer", S, '        if a is not None and page["state"] == "open":', "        if a is not None:",
     T + "test_s21_a_link_past_its_last_day_is_closed_and_takes_no_answer"),
    ("the answer carries the request as read", S, '        write = {"modified": req.get("modified")}', '        write = {"_": 1}',
     T + "test_s23_two_taps_at_once_keep_the_first_answer"),
    ("stop these messages is kept", S, '        if stop:\n            write["asked_to_stop"] = 1', "        if False:\n            pass",
     T + "test_s20_stop_these_messages_is_kept_even_without_an_answer_and_the_next_press_skips_them"),
    ("a comment is cut to 280", D, '    return a, " ".join((comment or "").split())[:COMMENT_MAX], bool(stop)',
     '    return a, " ".join((comment or "").split()), bool(stop)', R + "Page.test_an_answer_is_one_of_three_or_stop_alone"),
    ("only three answers", D, '    if a is not None and (isinstance(a, bool) or a not in (0, 1, 2)):', "    if False:",
     T + "test_s24_a_bad_answer_is_refused_and_writes_nothing"),
    ("a long press answer is cut", D, '"body": body if len(body) <= 280 else body[:279] + "…"', '"body": body',
     R + "Answers.test_every_press_answer_fits_and_says_why"),
    ("the prefix names the record types", D, '    PREFIX, RULE, REQUEST = prefix, f"{prefix} Rule", f"{prefix} Request"', "    pass",
     M + "test_each_retailer_is_checked_with_its_own_secret_and_written_with_its_own_key_under_the_librarys_prefix"),
    ("a redirect is not followed", S, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     "test_service.ShopApi.test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed"),
    ("an answer keeps its own direction", "service/page.js", '      b.dir = "auto";', "      b.title = '';",
     T + "test_s25b_the_retailers_words_keep_their_own_direction_on_an_arabic_page"),
    ("the question keeps its own direction", "service/page.html", '<h1 id="question" dir="auto">', '<h1 id="question">',
     T + "test_s25b_the_retailers_words_keep_their_own_direction_on_an_arabic_page"),
    ("a record name is one path segment", S, 'urllib.parse.quote(p, safe="")', "urllib.parse.quote(p)",
     "test_service.ShopApi.test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s49-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local", "screenshots"))
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
