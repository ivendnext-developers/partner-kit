"""S43's manifest passes the kit's checker; it installs only what runs without the payer door (three Desk buttons, the
records, the barred tick on Customer, the reports); the door's subscription and the bill-back wait in
door_declaration.json; members and claims are read by the claims clerk and the service only, never a till role; the
record types and fields are the ones the service reads and writes."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import app  # noqa: E402
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
LATER = json.loads((HERE.parent / "door_declaration.json").read_text())
P = MANIFEST["prefix"]
DT = {d["name"]: d for d in MANIFEST["doctypes"]}


def fields(dt):
    return {f["fieldname"] for f in DT[dt]["fields"]}


def roles(dt):
    return {p["role"] for p in DT[dt]["permissions"]}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_now_five_desk_buttons_and_the_door_s_two_later(self):
        self.assertEqual({s["key"]: s["point"] for s in MANIFEST["extension_subscriptions"]},
                         {k: "desk_action" for k in ("claims", "file", "remit", "ready", "settle")})
        self.assertEqual({s["key"]: s["point"] for s in LATER["extension_subscriptions"]},
                         {"payer": "payer", "billback": "desk_action"})
        self.assertEqual(sorted(app.NOW), sorted(s["key"] for s in MANIFEST["extension_subscriptions"]))
        for s in MANIFEST["extension_subscriptions"] + LATER["extension_subscriptions"]:
            self.assertEqual(app.ROUTES[s["endpoint_url"].split("8142", 1)[1]][0], s["key"])

    def test_the_door_s_point_is_refused_by_the_shop_s_checker_today(self):
        m = dict(MANIFEST, extension_subscriptions=MANIFEST["extension_subscriptions"] + LATER[
            "extension_subscriptions"][:1])
        self.assertTrue(validate.validate(m))

    def test_members_and_claims_are_never_a_till_roles(self):
        for dt in (f"{P} Member", f"{P} Claim", f"{P} Claim Batch", f"{P} Remittance"):
            self.assertEqual(roles(dt), {"System Manager", f"{P} Claims Clerk", f"{P} Integration"}, dt)

    def test_only_the_clerk_and_the_service_write_claims_and_no_one_deletes_one(self):
        for p in DT[f"{P} Claim"]["permissions"]:
            self.assertFalse(p["delete"], p["role"])
        self.assertTrue(next(p for p in DT[f"{P} Claim"]["permissions"] if p["role"] == f"{P} Integration")["create"])

    def test_a_claims_status_is_never_typed(self):
        status = next(f for f in DT[f"{P} Claim"]["fields"] if f["fieldname"] == "status")
        self.assertEqual(status.get("read_only"), 1)
        self.assertEqual(LATER["extension_subscriptions"][0]["settings"]["bill_back_role"], f"{P} Integration")

    def test_a_claims_name_is_its_reference_so_a_second_insert_is_refused(self):
        self.assertEqual(DT[f"{P} Claim"]["autoname"], "field:claim_ref")

    def test_the_fields_the_service_reads_and_writes_exist(self):
        self.assertTrue({"code", "title", "customer", "active", "valid_from", "valid_to", "needs_member_number",
                         "needs_card_serial", "needs_gtin", "needs_prescription", "needs_dose_frequency"}
                        <= fields(f"{P} Payer"))
        self.assertTrue({"payer", "price_list", "formulary", "covers", "copay_percent", "invoice_upper_limit",
                         "max_patient_amount", "discount_order", "copay_order", "no_partial_refund", "active"}
                        <= fields(f"{P} Plan"))
        self.assertTrue({"customer", "plan", "member_number", "card_serial", "policy_number", "valid_from",
                         "valid_to", "active"} <= fields(f"{P} Member"))
        self.assertTrue({"claim_ref", "status", "payer_share", "received", "billed_back", "batch", "returns",
                         "rejection_reason", "lines", "submitted_on", "incomplete_reason"} <= fields(f"{P} Claim"))
        self.assertTrue({"item_code", "item_group", "covered", "extra_pay", "max_qty"}
                        <= fields(f"{P} Formulary Item"))
        self.assertTrue({"claim_ref", "paid", "rejected", "reason", "expected", "result"}
                        <= fields(f"{P} Remittance Line"))
        cf = {c["fieldname"] for c in MANIFEST["custom_fields"]}
        self.assertEqual(cf, {"pp_icp_insurance_barred"})

    def test_the_plan_selects_carry_the_rules_own_words(self):
        import copay
        opts = {f["fieldname"]: f.get("options", "").split("\n") for f in DT[f"{P} Plan"]["fields"]}
        self.assertEqual(opts["discount_order"], [copay.BEFORE_LIMIT, copay.AFTER_LIMIT])
        self.assertEqual(opts["copay_order"], [copay.BEFORE_DISCOUNT, copay.AFTER_DISCOUNT])
        self.assertEqual(opts["covers"], [copay.FORMULARY_ONLY, copay.EVERY_ITEM])
        import claims
        status = next(f for f in DT[f"{P} Claim"]["fields"] if f["fieldname"] == "status")
        self.assertEqual(tuple(status["options"].split("\n")), claims.STATUSES)

    def test_nothing_is_required_on_the_shops_own_records(self):
        for c in MANIFEST["custom_fields"]:
            self.assertFalse(c.get("reqd"))


if __name__ == "__main__":
    unittest.main()
