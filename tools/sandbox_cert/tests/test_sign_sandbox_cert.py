"""The sandbox certificate tool, held by a known answer: Ed25519 is deterministic, so one fixed payload signed with the
published key has exactly one signature. It is checked against the pinned bytes AND verified with the key's public half
(the one the product holds for ``test-1``), so a wrong canonical form, a wrong key or a broken signer each fail here."""

import base64
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sign_sandbox_cert as tool  # noqa: E402

PUBLIC_TEST_1 = "vaZ0Fa/VUvZZwQh9i30EPBPOcb/dlKKva7IS+33mFdw="          # the product's public key for test-1
DECLARATION = {"v": 1, "display_name": "Member cash",
               "rails": {"wallet": {"settlement": "synchronous", "can_prove_absence": True}}}
ISSUED = "2026-10-12T00:00:00Z"
PINNED = "JcchYv8uENd/fwPNnnpMQRiM0W6mQFQkrC8Yyi7e13QNGEefvYUz5ezRz1amN4uRyXttLu8sSuVdj3leVjx7DQ=="
SPKI_ED25519 = bytes.fromhex("302a300506032b6570032100")             # the DER prefix of a raw 32-byte public key


def verifies(payload: dict, signature_b64: str) -> bool:
    with tempfile.TemporaryDirectory() as d:
        pub, msg, sig = (os.path.join(d, n) for n in ("p.der", "m.bin", "s.bin"))
        open(pub, "wb").write(SPKI_ED25519 + base64.b64decode(PUBLIC_TEST_1))
        open(msg, "wb").write(tool.canonical(payload))
        open(sig, "wb").write(base64.b64decode(signature_b64))
        r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-keyform", "DER", "-inkey", pub, "-rawin",
                            "-in", msg, "-sigfile", sig], capture_output=True, text=True)
        return r.returncode == 0


class KnownAnswer(unittest.TestCase):
    def setUp(self):
        self.cert = tool.certificate(DECLARATION, "acme", "cash", ISSUED)

    def test_a_fixed_payload_has_the_pinned_signature(self):
        self.assertEqual((self.cert["v"], self.cert["kid"], self.cert["payload"]["provider_key"]),
                         (1, "test-1", "remote_acme_cash"))
        self.assertEqual(self.cert["signature"], PINNED)

    def test_the_public_half_verifies_it_and_refuses_a_changed_payload(self):
        self.assertTrue(verifies(self.cert["payload"], self.cert["signature"]))
        changed = dict(self.cert["payload"], connector="cast")                   # one byte of the payload changed
        self.assertFalse(verifies(changed, self.cert["signature"]))

    def test_the_canonical_form_is_sorted_and_compact(self):
        self.assertEqual(tool.canonical({"b": 1, "a": "é"}), b'{"a":"\\u00e9","b":1}')

    def test_a_name_that_is_not_a_slug_is_refused(self):
        for bad in ("Acme", "a", "acme-pay", "1acme"):
            with self.assertRaises(ValueError):
                tool.certificate(DECLARATION, bad, "cash", ISSUED)


if __name__ == "__main__":
    unittest.main()
