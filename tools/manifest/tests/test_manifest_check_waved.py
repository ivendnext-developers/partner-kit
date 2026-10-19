# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_waved.py,
# at development 8851258321b3b8c1aae565ff88cd7ca1f0c0404d; two lines changed: the import (the kit's copy of the checker is
# validate.py) and the fixture folder. A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""The Wave D kind (label layouts) — stdlib only, no bench.

P-LABEL (spec §3): a manifest installs a ``Retail Label Layout`` as ``label_layouts``. The fixture passes; each
forbidden element, planted into it, is refused with its own reason and nothing else. The checker carries a copy of the
product's layout rules (``label_print.validate_layout``); ``test_extension_package`` pins the copy equal, and the
product's own validate runs again at install."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
WAVED = json.loads((HERE / "fixtures/waved_v2_ok.json").read_text())


def planted(change, base=WAVED):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


def lay(**k):
    return lambda m: m["label_layouts"][0].update(k)


FORBIDDEN = [
    ("switched on by the manifest", lay(enabled=1), "installs it switched off"),
    ("a name without the prefix", lay(label_name="Shelf 50x25"), "must start with its prefix"),
    ("a key the kind may not carry", lay(printer="Zebra"), "keys this kind may not carry"),
    ("a kind the record has not", lay(kind="pdf"), "a label layout's kind is one of"),
    (
        "a zpl template not framed",
        lay(kind="zpl", template="^FD{price}^FS"),
        "^XA and ends with ^XZ",
    ),
    (
        "a zpl template asking for svg",
        lay(kind="zpl", template="^XA{barcode_svg}^XZ"),
        "not {barcode_svg}",
    ),
    ("no template", lay(template=" "), "A label layout needs a template."),
    ("code in the template", lay(template="{{ doc.cost }}"), "not code"),
    ("a placeholder off the list", lay(template="{cost_price}"), "is not a label placeholder"),
    ("a script", lay(template="<script>x()</script>{price}"), "cannot hold scripts"),
    ("a handler", lay(template='<img src=x onerror="x()">'), "cannot hold scripts"),
    (
        "a split javascript: URL",
        lay(template='<a href="java\nscript:x()">{price}</a>'),
        "cannot hold",
    ),
    ("a stock wider than 150 mm", lay(width_mm=151), "width_mm must be between 10 and 150 mm."),
    ("a stock lower than 10 mm", lay(height_mm=9), "height_mm must be between 10 and 150 mm."),
    ("eleven per row", lay(per_row=11), "Labels per row must be between 1 and 10."),
    ("a v1 manifest", lambda m: m.update(manifest_version=1), "needs manifest_version 2"),
]


class Good(unittest.TestCase):
    def test_the_waved_fixture_passes(self):
        self.assertEqual(validate(WAVED), [])

    def test_a_zebra_layout_passes(self):
        zpl = "^XA^FO20,20^FD{item_name}^FS^BCN,60^FD{barcode}^FS^XZ"
        self.assertEqual(planted(lay(kind="zpl", template=zpl)), [])

    def test_kind_and_per_row_may_be_left_out(self):
        def change(m):
            del m["label_layouts"][0]["kind"], m["label_layouts"][0]["per_row"]

        self.assertEqual(planted(change), [])


class Refused(unittest.TestCase):
    def test_each_forbidden_element_is_refused_with_its_reason(self):
        for label, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], label)


if __name__ == "__main__":
    unittest.main()
