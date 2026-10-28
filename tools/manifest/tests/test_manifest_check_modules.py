# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_modules.py,
# at development 60147699cce4f7bd35f73e111649ce108eb2dcc2; changed: the import, the fixture folder, and a row id in a comment.
# A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""A package that carries a certified module — stdlib only, no bench.

A manifest's ``extension_modules`` entry carries a module our certify service signed (its bytes
in base64, the certificate, the extension point, the version) and an ``extension_subscriptions``
entry with ``transport: "wasm"`` names it by its key. The checker checks the shape and that the
bytes are the ones the SHA-256 names; the signature is checked by the shop when it installs. Each
fixture passes; each forbidden element, planted into it, is refused with its own reason and
nothing else."""

import base64
import copy
import hashlib
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent

MODULE = json.loads((HERE / "fixtures/module_v2_ok.json").read_text())


def planted(base, change):
    m = copy.deepcopy(base)
    change(m)
    return validate(m)


def at(kind, i=0, **k):
    return lambda m: m[kind][i].update(k)


def drop(kind, key, i=0):
    return lambda m: m[kind][i].pop(key)


def _check_module(m):
    """The same manifest with a module for the check before payment beside the pricing one."""
    b = b"\0asm\1\0\0\0" + b"check"
    m["extension_modules"].append(
        dict(
            m["extension_modules"][0],
            key="basket_check",
            point="check",
            sha256=hashlib.sha256(b).hexdigest(),
            wasm=base64.b64encode(b).decode(),
        )
    )
    m["extension_subscriptions"].append(
        {
            "key": "basket_check",
            "point": "check",
            "label": "Basket check",
            "transport": "wasm",
            "module": "basket_check",
            "down_answer": "refuse",
        }
    )


class Good(unittest.TestCase):
    def test_the_module_fixture_passes(self):
        self.assertEqual(validate(MODULE), [])

    def test_its_bytes_are_the_ones_its_sha256_names(self):
        e = MODULE["extension_modules"][0]
        self.assertEqual(hashlib.sha256(base64.b64decode(e["wasm"])).hexdigest(), e["sha256"])

    def test_a_check_module_and_its_service_pass(self):
        self.assertEqual(planted(MODULE, _check_module), [])

    def test_a_pricing_service_may_carry_its_modules_settings(self):
        self.assertEqual(
            planted(MODULE, at("extension_subscriptions", settings={"groups": ["Members"]})), []
        )

    def test_the_partner_name_may_be_given_once_on_both(self):
        def both(m):
            m["extension_modules"][0]["partner_name"] = "Member Pricing Co"
            m["extension_subscriptions"][0]["partner_name"] = "Member Pricing Co"

        self.assertEqual(planted(MODULE, both), [])


TOO_BIG = b"\0asm\1\0\0\0" + b"\0" * (256 * 1024)
FORBIDDEN = [
    (
        "bytes that are not the SHA-256's",
        at("extension_modules", sha256="0" * 64),
        "is not the SHA-256 of the module's bytes",
    ),
    ("bytes that are not base64", at("extension_modules", wasm="not base64!"), "base64"),
    (
        "an extension point that runs no module",
        lambda m: (
            m["extension_modules"][0].update(point="desk_action"),
            m["extension_subscriptions"].clear(),
        ),
        "runs no module",
    ),
    ("version 0", at("extension_modules", version=0), "whole number from 1"),
    ("a version as text", at("extension_modules", version="1"), "whole number from 1"),
    ("a module without the kit's meters", at("extension_modules", metered=False), "meters"),
    (
        "a certificate that is not a signature",
        at("extension_modules", certificate="abc"),
        "certificate is our certify service's signature",
    ),
    (
        "a module larger than a till runs",
        at(
            "extension_modules",
            wasm=base64.b64encode(TOO_BIG).decode(),
            sha256=hashlib.sha256(TOO_BIG).hexdigest(),
        ),
        "at most 262144 bytes",
    ),
    (
        "a module that says it runs only on the server",
        at("extension_modules", server_only=1),
        "keys this kind may not carry",
    ),
    (
        "a key with capitals",
        lambda m: (
            m["extension_modules"][0].update(key="Member"),
            m["extension_subscriptions"][0].update(module="Member"),
        ),
        "key is lower-case",
    ),
    (
        "a key used twice",
        lambda m: m["extension_modules"].append(
            dict(m["extension_modules"][0], partner_name="Another Partner")
        ),
        "a module key is used twice",
    ),
    (
        "two modules of one partner for one extension point",
        lambda m: m["extension_modules"].append(dict(m["extension_modules"][0], key="second")),
        "one module per partner and extension point",
    ),
    (
        "two modules of one partner, named in another case, for one extension point",
        lambda m: m["extension_modules"].append(
            dict(m["extension_modules"][0], key="second", partner_name=" pp mod")
        ),
        "one module per partner and extension point",
    ),
    (
        "the shop's limit in the manifest",
        at("extension_subscriptions", max_discount_percent=5),
        "installed at 0 and the shop raises it",
    ),
    (
        # what leaves the shop is the shop's tick, never a package's
        "a check's lots-and-serials tick in the manifest",
        at("extension_subscriptions", check_send_lots=1),
        "keys this kind may not carry: ['check_send_lots']",
    ),
    (
        "a module named on a service with an address",
        lambda m: m["extension_subscriptions"][0].update(
            transport="remote", point="check", endpoint_url="https://partner.example/x"
        )
        or m.update(allowed_urls=["https://partner.example/x"]),
        "names a module, so its transport is wasm",
    ),
    (
        "an address on a module's service",
        lambda m: m["extension_subscriptions"][0].update(endpoint_url="https://partner.example/x")
        or m.update(allowed_urls=["https://partner.example/x"]),
        "has no address",
    ),
    (
        "a service naming a module the manifest does not carry",
        at("extension_subscriptions", module="nobody"),
        "names no module of this manifest",
    ),
    (
        "a module's service on another extension point",
        lambda m: (
            _check_module(m),
            m["extension_subscriptions"][1].update(module="member_price"),
        ),
        "is for the price extension point",
    ),
    (
        "another partner's module",
        at("extension_subscriptions", partner_name="Someone Else"),
        "another partner's",
    ),
    (
        "a pricing service at an address",
        lambda m: m["extension_subscriptions"][0].update(
            transport="remote", endpoint_url="https://partner.example/x", module=None
        )
        or m["extension_subscriptions"][0].pop("module")
        or m.update(allowed_urls=["https://partner.example/x"]),
        "takes a module only",
    ),
    (
        "a pricing service's down answer it cannot give",
        at("extension_subscriptions", down_answer="refuse"),
        "can only: no_adjustment",
    ),
    (
        "a module in a version 1 manifest",
        lambda m: (m.update(manifest_version=1), m.pop("extension_subscriptions")),
        "needs manifest_version 2",
    ),
]


class Refused(unittest.TestCase):
    def test_each_forbidden_element_is_refused_with_its_reason(self):
        for label, change, phrase in FORBIDDEN:
            with self.subTest(label):
                refusals = planted(MODULE, change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], label)

    def test_a_shop_switch_on_a_module_is_refused(self):
        refusals = planted(MODULE, at("extension_modules", withdrawn=0))
        self.assertEqual(
            [r["reason"] for r in refusals], ["keys this kind may not carry: ['withdrawn']"]
        )

    def test_a_partner_name_that_is_not_text_is_refused_on_the_module_and_its_service(self):
        def odd(m):
            m["extension_modules"][0]["partner_name"] = 5
            m["extension_subscriptions"][0]["partner_name"] = 5

        reasons = [r["reason"] for r in planted(MODULE, odd)]
        self.assertEqual(len(reasons), 2, reasons)
        self.assertIn("the module's partner name", reasons[0])
        self.assertIn("the service's partner name", reasons[1])


if __name__ == "__main__":
    unittest.main()
