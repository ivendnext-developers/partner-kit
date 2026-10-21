# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_listmark.py,
# at development 7d47d331a203fd8b2794f83270a4190b3c1908e8; changed: the import, the fixture folder, and the lane id in the docstring and in its fixture's title.
# A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""The list mark kind — stdlib only, no bench.

P-LISTMARK (spec §3): a manifest installs a ``Retail List Mark`` as ``list_marks``. The fixture passes; each
forbidden element, planted into it, is refused with its own reason and nothing else. The checker carries a copy of the
product's rules that need no site (``list_mark.validate_mark``); ``test_list_mark`` pins the copy equal, and the
product's own validate runs again at install (the record type, its fields)."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
LISTMARK = json.loads((HERE / "fixtures/listmark_v2_ok.json").read_text())


def planted(change, base=LISTMARK):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


def mark(**k):
    return lambda m: m["list_marks"][0].update(k)


def cond(**k):
    return lambda m: m["list_marks"][0]["conditions"][0].update(k)


def six(m):
    m["list_marks"] = [dict(m["list_marks"][0], label=f"Mark {n}") for n in range(6)]


FORBIDDEN = [
    ("switched on by the manifest", mark(enabled=1), "installs it switched off"),
    ("a key the kind may not carry", mark(background="yellow"), "keys this kind may not carry"),
    ("no record type", mark(record_type=None), "names its record type"),
    ("a 25-character label", mark(label="A" * 25), "1 to 24 characters"),
    ("a label with a space after it", mark(label="Stock kept "), "no space before or after"),
    ("a record type with a space after it", mark(record_type="Item "), "no space before or after"),
    ("markup in a label", mark(label="<b>Promo</b>"), "The label is plain text"),
    ("a quote in a label", mark(label="Tom's pick"), "The label is plain text"),
    ("colour black", mark(colour="black"), "Choose one of the colours"),
    ("a sequence that is not a number", mark(sequence="first"), "sequence is a whole number"),
    ("no condition", mark(conditions=[]), "Give one to 3 conditions."),
    (
        "four conditions",
        mark(conditions=[{"field": "disabled", "operator": "=", "value": "0"}] * 4),
        "Give one to 3 conditions.",
    ),
    ("an operator off the list", cond(operator="like"), "a condition's operator is one of"),
    ("a comparison on a word", cond(operator=">", value="lots"), "needs a number"),
    ("a condition key off the list", cond(join="or"), "keys this kind may not carry"),
    ("a sixth mark on one record type", six, "Item holds at most 5 marks."),
    (
        "one label twice on one record type",
        lambda m: m["list_marks"].append(dict(m["list_marks"][0])),
        "two marks on one record type need two labels",
    ),
    ("a v1 manifest", lambda m: m.update(manifest_version=1), "needs manifest_version 2"),
]


class Good(unittest.TestCase):
    def test_the_listmark_fixture_passes(self):
        self.assertEqual(validate(LISTMARK), [])

    def test_is_set_needs_no_value_and_sequence_may_be_left_out(self):
        def change(m):
            m["list_marks"][0]["conditions"] = [{"field": "image", "operator": "is set"}]
            del m["list_marks"][0]["sequence"]

        self.assertEqual(planted(change), [])

    def test_five_marks_on_one_record_type_pass(self):
        def five(m):
            m["list_marks"] = [dict(m["list_marks"][0], label=f"Mark {n}") for n in range(5)]

        self.assertEqual(planted(five), [])


class Refused(unittest.TestCase):
    def test_each_forbidden_element_is_refused_with_its_reason(self):
        for label, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], label)


if __name__ == "__main__":
    unittest.main()
