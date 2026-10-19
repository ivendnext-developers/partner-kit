"""The needs checker: a good card passes, and each planted fault turns it red.

    python3 -m unittest discover -s tools/needs/tests

Each test builds a small kit in a temporary folder (one recipe, one sample, one good card), plants one fault and runs the
checker over it. The same fixture without the fault is green, so each red is the fault's, not the fixture's.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "needs"))
import needs  # noqa: E402

GOOD = """---
id: line-cap
title: A limit on one line
area: till
topic: limits-on-a-sale
asks: No more than 50 of one item on a line
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule.md
sample: samples/s1_rule
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service answers the check before payment.

## Limits
- Answered at Pay.

## Tell the customer
The till stops the sale at Pay.
"""


def card(text: str = GOOD, **meta: str) -> str:
    for key, value in meta.items():
        key = key.replace("_", "-")
        lines = text.split("\n")
        text = "\n".join(f"{key}: {value}" if ln.startswith(key + ":") else ln for ln in lines)
    return text


class Kit:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "recipes").mkdir()
        (self.root / "recipes" / "rule.md").write_text("# A rule\n", "utf-8")
        (self.root / "samples" / "s1_rule").mkdir(parents=True)
        (self.root / "samples" / "s1_rule" / "README.md").write_text("# S1\n", "utf-8")
        (self.root / "needs" / "till").mkdir(parents=True)

    def add(self, text: str, area: str = "till", name: str = "") -> None:
        cid = next((ln[4:].strip() for ln in text.split("\n") if ln.startswith("id:")), "x")
        (self.root / "needs" / area).mkdir(parents=True, exist_ok=True)
        (self.root / "needs" / area / ((name or cid) + ".md")).write_text(text, "utf-8")

    def faults(self) -> list[str]:
        return needs.check(self.root)


class CheckerTests(unittest.TestCase):
    def kit(self, *cards: str) -> Kit:
        k = Kit()
        self.addCleanup(k.tmp.cleanup)
        for c in cards:
            k.add(c)
        return k

    def red(self, text: str, words: str, area: str = "till", name: str = "") -> None:
        k = self.kit()
        k.add(text, area, name)
        bad = k.faults()
        self.assertTrue(any(words in b for b in bad), bad)

    def test_related_naming_no_card_or_itself_or_five_is_red(self):
        rel = lambda v: GOOD.replace("verified:", f"related: {v}\nverified:")
        self.red(rel("no-such-card"), "related names no-such-card, which is not a card's id")
        self.red(rel("line-cap"), "related names the card itself")
        self.red(rel("a, b, c, d, e"), "related names 5 cards; at most 4")
        k = self.kit(GOOD, card(rel("line-cap").replace("id: line-cap", "id: other-cap"), title="Other"))
        self.assertEqual([b for b in k.faults() if "related" in b], [])

    def test_the_good_card_is_green(self):
        self.assertEqual(self.kit(GOOD).faults(), [])

    def test_a_recipe_that_does_not_exist_is_red(self):
        self.red(card(recipe="recipes/no_such_recipe.md"), "recipe recipes/no_such_recipe.md does not exist")

    def test_a_sample_that_does_not_exist_is_red(self):
        self.red(card(sample="samples/s99_gone"), "sample samples/s99_gone does not exist")

    def test_ready_with_limits_and_no_limit_line_is_red(self):
        self.red(GOOD.replace("- Answered at Pay.", "None."), "no '- ' line under Limits")

    def test_ready_with_a_limit_line_is_red(self):
        self.red(card(status="ready"), "ready, but its Limits section")

    def test_not_yet_with_no_blocked_by_is_red(self):
        self.red(card(status="not-yet", door="request", request="P-CHECK"), "not-yet needs blocked-by")

    def test_not_yet_on_an_extension_point_with_no_handle_is_red(self):
        self.red(card(status="not-yet", door="request", blocked_by="extension-point"), "names no request handle")

    def test_not_yet_on_product_work_with_no_ask_line_is_red(self):
        self.red(card(status="not-yet", door="request", blocked_by="product-work"), "no '**Ask us:**' line")

    def test_not_yet_with_its_handle_is_green(self):
        self.assertEqual(self.kit(card(status="not-yet", door="request", blocked_by="extension-point", request="P-CHECK")).faults(), [])

    def test_not_possible_with_no_instead_line_is_red(self):
        self.red(card(status="not-possible", door="none"), "no '**Instead:**' line")

    def test_not_possible_with_its_instead_line_is_green(self):
        text = card(status="not-possible", door="none").replace("- Answered at Pay.", "- **Instead:** a line the cashier adds.")
        self.assertEqual(self.kit(text).faults(), [])

    def test_an_unknown_door_is_red(self):
        self.red(card(door="back-door"), "unknown door 'back-door'")

    def test_a_card_with_no_topic_is_red(self):
        self.red(GOOD.replace("topic: limits-on-a-sale\n", ""), "no topic: line")

    def test_a_topic_off_its_areas_list_is_red(self):
        self.red(card(topic="counts"), "unknown topic 'counts' for area till")         # a stock topic on a till card

    def test_a_topic_with_one_card_is_a_warning_never_a_fault(self):
        k = self.kit(GOOD)
        self.assertEqual(k.faults(), [])
        self.assertIn("topic till/limits-on-a-sale has 1 card(s): a topic is meant to group two or more", needs.warnings(k.root))

    def test_every_area_has_at_most_six_topics_and_every_topic_a_label(self):
        self.assertEqual(set(needs.TOPICS), set(needs.AREAS))
        for area, topics in needs.TOPICS.items():
            self.assertTrue(0 < len(topics) <= 6, area)
            self.assertTrue(all(label for label in topics.values()), area)

    def test_an_unknown_area_is_red(self):
        self.red(card(area="garden"), "unknown area 'garden'", area="garden")

    def test_a_duplicate_id_is_red(self):
        k = self.kit(GOOD)
        k.add(GOOD, area="prices", name="line-cap")
        (k.root / "needs" / "prices" / "line-cap.md").write_text(card(area="prices"), "utf-8")
        self.assertTrue(any("id line-cap is also used by" in b for b in k.faults()), k.faults())

    def test_a_file_name_that_is_not_the_id_is_red(self):
        self.red(GOOD, "the file name other-name.md is not the id line-cap", name="other-name")

    def test_an_upstream_name_is_red(self):
        word = "Fr" + "appe"                                 # built from parts, so this file does not contain it
        self.red(GOOD.replace("Your service answers", f"Your {word} service answers"), "names an upstream product")
        word2 = "ERP" + "Next"
        self.red(GOOD.replace("Your service answers", f"Your {word2} service answers"), "names an upstream product")

    def test_a_card_of_41_lines_is_red_and_40_is_green(self):
        filler = 40 - GOOD.count("\n")
        self.assertEqual(self.kit(GOOD.replace("## Tell", "\n" * filler + "## Tell")).faults(), [])
        self.red(GOOD.replace("## Tell", "\n" * (filler + 1) + "## Tell"), "41 lines")

    def test_extension_point_shortened_is_red(self):
        self.red(GOOD.replace("Answered at Pay.", "Answered at Pay; a new point is coming."), "'point' on its own")
        self.red(GOOD.replace("Answered at Pay.", "Answered at Pay; two points are coming."), "'point' on its own")

    def test_extension_point_in_full_and_the_allowed_phrases_are_green(self):
        ok = GOOD.replace("Answered at Pay.", "Answered at Pay; an extension point, loyalty points, the point of sale.")
        self.assertEqual(self.kit(ok).faults(), [])

    def test_a_recipe_no_card_cites_and_not_listed_as_reference_is_red(self):
        k = self.kit(GOOD)
        (k.root / "recipes" / "orphan.md").write_text("# Orphan\n", "utf-8")
        self.assertTrue(any("recipes/orphan.md: no card cites it" in b for b in k.faults()), k.faults())
        (k.root / "needs" / "reference.txt").write_text("recipes/orphan.md — a technique, not a need\n", "utf-8")
        self.assertEqual(k.faults(), [])

    def test_a_sample_no_card_cites_and_not_listed_as_reference_is_red(self):
        k = self.kit(GOOD)
        (k.root / "samples" / "s2_orphan").mkdir()
        (k.root / "samples" / "s2_orphan" / "README.md").write_text("# S2\n", "utf-8")
        self.assertTrue(any("samples/s2_orphan: no card cites it" in b for b in k.faults()), k.faults())

    def test_a_ready_card_with_a_limit_written_as_a_sentence_is_red(self):
        self.red(card(status="ready").replace("- Answered at Pay.", "Answered at Pay, not before."), "ready, but its Limits section")

    def test_a_ready_card_with_none_known_is_green(self):
        self.assertEqual(self.kit(card(status="ready").replace("- Answered at Pay.", "None known.")).faults(), [])

    def test_a_missing_front_matter_line_is_red(self):
        self.red(GOOD.replace("recipe: recipes/rule.md\n", ""), "no recipe: line")

    def test_a_missing_section_is_red(self):
        self.red(GOOD.replace("## Tell the customer\nThe till stops the sale at Pay.\n", ""), "no '## Tell the customer' section")

    def test_an_unknown_status_is_red(self):
        self.red(card(status="maybe"), "unknown status 'maybe'")

    def test_a_card_in_another_areas_folder_is_red(self):
        self.red(GOOD, "area till but the card is in needs/prices/", area="prices")

    def test_a_not_yet_card_whose_door_is_not_request_is_red(self):
        self.red(card(status="not-yet", blocked_by="extension-point", request="P-CHECK"), "a not-yet card's door is request")

    def test_blocked_by_on_a_card_that_is_not_not_yet_is_red(self):
        self.red(card(blocked_by="extension-point"), "blocked-by is for not-yet cards only")

    def test_a_not_possible_card_whose_door_is_not_none_is_red(self):
        text = card(status="not-possible").replace("- Answered at Pay.", "- **Instead:** a line the cashier adds.")
        self.red(text, "a not-possible card's door is none")

    def test_door_none_on_a_card_that_is_not_not_possible_is_red(self):
        self.red(card(door="none"), "door none is for not-possible cards only")

    def test_door_request_on_a_card_that_is_not_not_yet_is_red(self):
        self.red(card(door="request"), "door request is for not-yet cards only")

    def test_a_reference_line_for_a_missing_path_or_with_no_reason_is_red(self):
        k = self.kit(GOOD)
        (k.root / "needs" / "reference.txt").write_text("recipes/gone.md — a reason\nrecipes/rule.md\n", "utf-8")
        bad = k.faults()
        self.assertTrue(any("reference.txt: recipes/gone.md does not exist" in b for b in bad), bad)
        self.assertTrue(any("reference.txt: recipes/rule.md gives no reason" in b for b in bad), bad)

    def test_a_bad_request_handle_is_red(self):
        self.red(card(request="CHECK"), "is not a handle such as P-CHECK")


class CommandTests(unittest.TestCase):
    """The commands a person types, run as a person runs them, on the repository's own cards."""
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "tools" / "needs" / "needs.py"), *args], capture_output=True, text=True)

    def test_search_finds_a_card_by_the_customers_words(self):
        r = self.run_tool("search", "limit", "quantity", "of", "one", "item")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("line-quantity-cap", r.stdout.split("\n")[0])
        self.assertIn("check the top card answers it as asked", r.stdout)
        self.assertIn("feedback/point_request.md", r.stdout)           # a near miss still shows the way to ask

    def test_search_with_no_match_says_so_and_points_to_the_request_form(self):
        r = self.run_tool("search", "zzzqqq")
        self.assertEqual(r.returncode, 1)
        self.assertIn("feedback/point_request.md", r.stdout)

    def test_show_and_blueprint(self):
        self.assertIn("id: line-quantity-cap", self.run_tool("show", "line-quantity-cap").stdout)
        r = self.run_tool("blueprint", "line-quantity-cap", "fee-or-surcharge")
        self.assertIn("| 1 | No more than 50 of one item on a line | line-quantity-cap | Ready, with limits (1) | Check before payment |", r.stdout)
        self.assertIn("| 2 |", r.stdout)
        self.assertEqual(self.run_tool("blueprint", "no-such-card").returncode, 1)

    def test_backlinks_and_stale(self):
        self.assertIn("recipes/till_guard.md: ", self.run_tool("backlinks").stdout)
        self.assertIn("a to-do, not a failure", self.run_tool("stale", "--days", "0").stdout)
        self.assertEqual(self.run_tool("stale", "--days").returncode, 2)          # no number: usage, not a crash

    def test_search_finds_a_two_letter_word_and_blueprint_prints_the_request_handle(self):
        self.assertIn("head-office-bi", self.run_tool("search", "BI").stdout)
        self.assertIn("ask for P-CAPTURE3", self.run_tool("blueprint", "question-on-quantity-change").stdout)


if __name__ == "__main__":
    unittest.main()
