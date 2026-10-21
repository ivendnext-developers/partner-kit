"""S34's answers and calls against the published contract, ``doccheck.v1`` in ``contracts/`` (read by
``tools/contracts/check.py``): every answer the service gives holds, the product's own accepted samples hold, and a
builder that answers ``fill`` with no fields, or a verdict that is not one of the five, is refused by the same check."""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts")]
import check  # noqa: E402
import erp  # noqa: E402
import po_check  # noqa: E402
from test_po_check import FIELD, body, context  # noqa: E402

SAMPLES = ROOT / "contracts" / "extension_contracts" / "samples" / "doccheck"


def answers():
    e = erp.StandIn()
    return {"refuse": po_check.on_check(context(supplier="Acme Supplies"), e, FIELD),
            "approve": po_check.on_check(context(minor=900000), e, FIELD),
            "fill": po_check.on_check(context(), e, FIELD),
            "allow": po_check.on_check(context(event="validate"), e, FIELD)}


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        self.assertEqual(check.errors("doccheck", "request", body(context())), [])

    def test_every_answer_the_service_gives_holds(self):
        for verdict, a in answers().items():
            self.assertEqual(a["verdict"], verdict)
            self.assertEqual(check.errors("doccheck", "answer", a), [], verdict)

    def test_the_products_accepted_samples_hold(self):
        found = sorted((SAMPLES / "accepted").glob("*.json"))
        self.assertEqual(len(found), 4)
        for p in found:
            self.assertEqual(check.errors("doccheck", "answer", json.loads(p.read_text())["payload"]), [], p.name)

    def test_the_manifests_settings_hold(self):
        m = json.loads((HERE.parent / "manifest.json").read_text())
        self.assertEqual(check.errors("doccheck", "settings", m["extension_subscriptions"][0]["settings"]), [])

    def test_canary_a_fill_with_no_fields_and_an_unknown_verdict_are_refused(self):
        """The builder made wrong, two ways, as the product's refused samples 05 and 03 are: the contract check refuses."""
        fill = answers()["fill"]
        no_fields = dict(fill, fields={})
        unknown = {"verdict": "hold"}
        for name, bad in (("05_fill_nothing", no_fields), ("03_unknown_verdict", unknown)):
            self.assertTrue(check.errors("doccheck", "answer", bad), name)
            product = json.loads((SAMPLES / "refused" / f"{name}.json").read_text())["payload"]
            self.assertEqual(bad, product if name == "03_unknown_verdict" else dict(product, verdict="fill"), name)


if __name__ == "__main__":
    unittest.main()
