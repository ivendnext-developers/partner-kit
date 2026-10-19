"""The extension-point kinds (row KINDS) — stdlib only, no bench:  python3 -m unittest discover -s tools/manifest/tests -v

Save rules, Desk actions, extension subscriptions (Desk action and page) and the fiscal reader install from a manifest;
a package cannot install a module yet, so a manifest that carries one is refused, with the reason that says where a module goes. Each fixture passes; each forbidden element, planted
into it, is refused with its own reason and nothing else; the fiscal reader's warnings name what the shop must do."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate, warnings  # noqa: E402

KINDS = json.loads((HERE / "fixtures/kinds_v2_ok.json").read_text())
FISCAL = json.loads((HERE / "fixtures/fiscal_v2_ok.json").read_text())


def planted(base, change):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


def at(kind, i=0, **k):
    return lambda m: m[kind][i].update(k)


def drop(kind, key, i=0):
    return lambda m: m[kind][i].pop(key)


class Good(unittest.TestCase):
    def test_the_kinds_fixture_passes(self):
        self.assertEqual(validate(KINDS), [])

    def test_the_fiscal_fixture_passes_with_only_the_level_zero_warning(self):
        self.assertEqual(validate(FISCAL), [])
        self.assertEqual([w["what"] for w in warnings(FISCAL)], ["level_zero"])

    def test_a_desk_action_input_of_each_listed_type_passes(self):
        # the product's own case (iVendNext_PWA test_manifest_check_kinds.py at development 06c9d483): the eight types
        # its Desk-action page lists (partner-feedback #9)
        for t in ("Data", "Int", "Float", "Date", "Select", "Link", "Check", "Small Text"):
            with self.subTest(t):
                self.assertEqual(planted(KINDS, lambda m, t=t: m["desk_actions"][0]["inputs"][0].update(fieldtype=t)), [])

    def test_a_transport_named_remote_passes(self):
        self.assertEqual(planted(KINDS, at("extension_subscriptions", transport="remote")), [])

    def test_a_reader_with_a_qr_field_at_its_level_passes(self):
        def qr(m):
            m["custom_fields"].append(dict(m["custom_fields"][0], fieldname="pp_fbr_qr", label="FBR QR"))
            m["fiscal_readers"][0]["qr_field"] = "pp_fbr_qr"
        self.assertEqual(planted(FISCAL, qr), [])

    def test_the_new_kinds_need_version_2(self):
        m = dict(copy.deepcopy(KINDS), manifest_version=1)
        reasons = {r["where"]: r["reason"] for r in validate(m)}
        for k in ("extension_subscriptions", "desk_actions", "save_rules"):
            self.assertIn("needs manifest_version 2", reasons.get(k, ""), k)


FORBIDDEN = [
    # extension subscriptions — the remote_keys words
    ("a subscription switched on", KINDS, at("extension_subscriptions", enabled=1), "ticks the consent"),
    ("a subscription already consented", KINDS, at("extension_subscriptions", consent_given=1), "ticks the consent"),
    ("a subscription stamping its consent", KINDS, at("extension_subscriptions", consent_on="2026-10-07"), "ticks the consent"),
    ("a subscription carrying its secret", KINDS, at("extension_subscriptions", secret="s3cret"), "carries no secret"),
    ("a subscription declaring its consent text", KINDS, at("extension_subscriptions", consent_fields="x"), "stamped by the server"),
    ("a subscription on plain http", KINDS, lambda m: (m["allowed_urls"].append("http://partner.example/knd/x"),
                                                         m["extension_subscriptions"][0].update(endpoint_url="http://partner.example/knd/x")),
     "https address"),
    ("a subscription to an address not listed", KINDS, at("extension_subscriptions", endpoint_url="https://other.example/x"),
     "https address"),
    ("a subscription slower than its extension point allows", KINDS, at("extension_subscriptions", timeout_seconds=11), "at most 10"),
    ("a subscription with a long label", KINDS, at("extension_subscriptions", label="x" * 41), "label is 1 to 40"),
    ("a subscription with a bad key", KINDS, lambda m: (m["extension_subscriptions"][0].update(key="Route Key"),
                                                       m["desk_actions"][0].update(service="Route Key")), "key is lower-case"),
    ("two subscriptions with one key", KINDS, at("extension_subscriptions", 1, key="route"), "used twice"),
    ("a subscription to an extension point not on this product", KINDS, at("extension_subscriptions", 1, point="wallet"),   # check shipped in Wave B (row WAVEB); the wallet has not
     "one of the extension points"),
    ("page settings on a Desk action subscription", KINDS, at("extension_subscriptions", page_height=50), "page subscription"),
    ("a subscription choosing the stores", KINDS, at("extension_subscriptions", scope=["Store 1"]), "which stores"),
    ("a subscription answered by a module", KINDS, at("extension_subscriptions", transport="wasm"), "sandboxed"),
    ("a key a subscription may not carry", KINDS, at("extension_subscriptions", settings="{}"), "keys this kind may not carry"),
    ("a page opened to visitors", KINDS, at("extension_subscriptions", 1, page_roles=["Guest"]), "visitors"),
    ("a page opened to every staff user", KINDS, at("extension_subscriptions", 1, page_roles=["Desk User"]), "Desk User"),
    # Desk actions
    ("a Desk action switched on", KINDS, at("desk_actions", enabled=1), "switches it on"),
    ("a Desk action whose service the manifest does not install", KINDS, at("desk_actions", service="elsewhere"),
     "extension_subscriptions"),
    ("a Desk action answered by a page subscription", KINDS, at("desk_actions", service="bins"), "extension_subscriptions"),
    ("a Desk action every signed-in user sees", KINDS, at("desk_actions", roles=["All"]), "Desk User"),
    ("a Desk action visitors see", KINDS, at("desk_actions", roles=["Guest"]), "visitors"),
    ("a Desk action role spelled to slip past", KINDS, at("desk_actions", roles=["Àll"]), "plain letters"),
    ("a key a Desk action may not carry", KINDS, at("desk_actions", script="x"), "keys this kind may not carry"),
    ("a Desk action without a record type", KINDS, drop("desk_actions", "record_type"), "names its record type"),
    ("Desk action states that are not a list", KINDS, at("desk_actions", states="Open"), "is a list"),
    # save rules
    ("a save rule switched on", KINDS, at("save_rules", enabled=1), "switches it on"),
    ("a save rule named without the prefix", KINDS, at("save_rules", rule_name="Customer name length"), "must start with its prefix"),
    ("a save rule nobody may bypass but Administrator", KINDS, at("save_rules", 1, bypass_roles=["Administrator"]), "Administrator"),
    ("a key a save rule may not carry", KINDS, at("save_rules", python="x"), "keys this kind may not carry"),
    ("a save rule without a record type", KINDS, drop("save_rules", "record_type"), "names its record type"),
    ("a save rule message carrying script", KINDS, at("save_rules", message="<img src=x onerror=alert(1)>"),
     "carrying script"),
    ("locked fields that are not a list", KINDS, at("save_rules", locked_fields="customer_name"), "is a list"),
    # the fiscal reader
    ("a reader switched on", FISCAL, at("fiscal_readers", enabled=1), "switches the reader on"),
    ("a reader naming its companies", FISCAL, at("fiscal_readers", companies=["Demo Retail"]), "own company"),
    ("a reader reading an installed app", FISCAL, at("fiscal_readers", source="zatca_erpgulf"), "outside service"),
    ("two readers", FISCAL, lambda m: m["fiscal_readers"].append(copy.deepcopy(m["fiscal_readers"][0])), "one fiscal reader"),
    ("a writer role without the prefix", FISCAL, at("fiscal_readers", writer_role="FBR Writer"), "must start with its prefix"),
    ("results at level 0", FISCAL, lambda m: (m["fiscal_readers"][0].update(writer_level=0),
                                                [f.update(permlevel=0) for f in m["custom_fields"]]), "writer_level is"),
    ("a result field the manifest does not add", FISCAL, lambda m: (m["custom_fields"].pop(1),
                                                                     m["fiscal_readers"][0].update(ref_field="pp_fbr_other")),
     "the manifest's own field"),
    ("a result field on another record type", FISCAL, lambda m: m["custom_fields"][1].update(
        dt="Sales Invoice", permlevel=None) or [m["custom_fields"][1].pop(k) for k in ("permlevel", "no_copy")],
     "the manifest's own field"),
    ("a result field at another level", FISCAL, at("custom_fields", 1, permlevel=3), "must sit at writer_level"),
    ("a status map that is not rows", FISCAL, at("fiscal_readers", status_map={"Accepted": "CLEARED"}), "status_map is"),
    ("writer users with a bad key", FISCAL, at("fiscal_readers", writer_users=["FBR Service"]), "writer_users is"),
    ("a key a reader may not carry", FISCAL, at("fiscal_readers", writer_users_extra=1), "keys this kind may not carry"),
    ("a field level set outside a reader", KINDS, lambda m: m.update(custom_fields=[{
        "dt": "Customer", "fieldname": "pp_knd_note", "fieldtype": "Data", "label": "Note", "permlevel": 2}]),
     "keys a field may not carry"),
    # coverage: every remaining refusal the new kinds add
    ("a subscription naming a module", KINDS, at("extension_subscriptions", module="PP KND mod"), "sandboxed"),
    ("Desk action conditions that are not objects", KINDS, at("desk_actions", conditions=["customer_name"]), "list of objects"),
    ("Desk action inputs that are not objects", KINDS, at("desk_actions", inputs=["note"]), "list of objects"),
    ("a Desk action input of a type the product refuses", KINDS,
     lambda m: m["desk_actions"][0]["inputs"][0].update(fieldtype="Attach"), "Data, Int, Float, Date, Select, Link, Check, Small Text"),
    ("a Desk action input typed as money (partner-feedback #9)", KINDS,
     lambda m: m["desk_actions"][0]["inputs"][0].update(fieldtype="Currency"), "Data, Int, Float, Date, Select, Link, Check, Small Text"),
    ("save rule states that are not a list", KINDS, at("save_rules", states="Open"), "is a list"),
    ("save rule conditions that are not objects", KINDS, at("save_rules", conditions=["x"]), "list of objects"),
    ("one writer user named twice", FISCAL, at("fiscal_readers", writer_users=["fbr_service", "fbr_service"]), "writer_users is"),
    ("a QR field the manifest does not add", FISCAL, at("fiscal_readers", qr_field="pp_fbr_qr"), "qr_field names"),
    # the kinds still waiting, and the placeholder that was renamed
    ("a module", KINDS, lambda m: m.update(extension_modules=[{"point": "desk_action"}]), "cannot install a sandboxed module"),
    ("the old placeholder name", KINDS, lambda m: m.update(point_subscriptions=[{}]), "extension_subscriptions"),
]


class Refused(unittest.TestCase):
    def test_each_forbidden_element_is_refused_with_its_reason(self):
        for label, base, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(base, change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], label)


class Warned(unittest.TestCase):
    def test_level_1_is_named(self):
        m = copy.deepcopy(FISCAL)
        m["fiscal_readers"][0]["writer_level"] = 1
        for f in m["custom_fields"]:
            f["permlevel"] = 1
        self.assertEqual(validate(m), [])
        self.assertIn("level_one", [w["what"] for w in warnings(m)])

    def test_no_copy_off_and_not_allow_on_submit_are_named(self):
        m = copy.deepcopy(FISCAL)
        m["custom_fields"][0].pop("no_copy")
        m["custom_fields"][1].pop("allow_on_submit")
        self.assertEqual(validate(m), [])
        whats = [w["what"] for w in warnings(m)]
        self.assertIn("no_copy", whats)
        self.assertIn("allow_on_submit", whats)

    def test_no_integration_user_is_named(self):
        m = copy.deepcopy(FISCAL)
        m["fiscal_readers"][0]["writer_users"] = []
        self.assertEqual(validate(m), [])
        self.assertIn("no_writer_user", [w["what"] for w in warnings(m)])


if __name__ == "__main__":
    unittest.main()
