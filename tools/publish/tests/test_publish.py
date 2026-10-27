"""Tests of the publish command (tools/publish). Standard library only; the library is a local stand-in server.

    python3 -m unittest discover -s tools/publish/tests -p 'test_*.py'
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import http.server
import io
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ed25519  # noqa: E402
import publish  # noqa: E402

# RFC 8032 §7.1, tests 1 and 2: (secret, public, message, signature)
RFC = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]
# a throwaway 4096-bit RSA public key's PEM is not needed: the command only hashes it, so any PEM-shaped key will do
PEM = ("-----BEGIN PUBLIC KEY-----\n" + base64.b64encode(b"\x30\x82" + b"k" * 60).decode() + "\n-----END PUBLIC KEY-----\n")
MANIFEST = {"manifest_version": 1, "app": "pp_stn", "prefix": "PP STN", "title": "Stand-in notes", "version": "1.2.0"}
CARD = {"app": "pp_stn", "title": {"en": "Stand-in notes (test)"}, "summary": {"en": "A test app."},
        "category": "Stock", "used_by": ["Stock Clerk"],
        "changelog": [{"version": "1.2.0", "date": "2026-10-14", "en": "This version."}]}


def project(d: pathlib.Path, manifest=None, conf=None) -> pathlib.Path:
    lib = d / "proj" / "library"
    lib.mkdir(parents=True)
    (lib / "app.json").write_text(json.dumps(CARD))
    (lib / "manifest.json").write_text(json.dumps(manifest or MANIFEST))
    (lib / "library.json").write_text(json.dumps(conf or {"public": True, "preview_sites": ["sandbox-cd-07.staging.ivendnext.com"]}))
    (lib / "recipient.pem").write_text(PEM)
    (d / "proj" / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026 Stand-in\n")
    (d / "proj" / "THIRD_PARTY.md").write_text("None\n")
    return d / "proj"


class Library(http.server.BaseHTTPRequestHandler):
    """A stand-in for the library's door: it checks the signature the way the library does and answers."""
    public: bytes = b""
    reply: tuple = (200, {})
    seen: list = []

    def do_POST(self):  # noqa: N802
        env = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        body, sig = publish.unb64u(env["body"]), publish.unb64u(env["sig"])
        ok = env["key"] == publish.key_id(self.public) and ed25519.verify(self.public, publish.DOMAIN + body, sig)
        Library.seen.append(json.loads(body) if ok else None)
        status, out = Library.reply if ok else (401, {"refused": "bad_signature", "words": "no"})
        data = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Ed25519Tests(unittest.TestCase):
    def test_rfc_8032_vectors(self):
        for sk, pk, msg, sig in RFC:
            sk, pk, msg, sig = (bytes.fromhex(x) for x in (sk, pk, msg, sig))
            self.assertEqual(ed25519.public_key(sk), pk)
            self.assertEqual(ed25519.sign(sk, msg), sig)
            self.assertTrue(ed25519.verify(pk, msg, sig))
            self.assertFalse(ed25519.verify(pk, msg + b"x", sig))

    @unittest.skipUnless(shutil.which("openssl") and subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519"],
                                                                     capture_output=True).returncode == 0,
                         "no openssl with Ed25519 (macOS's LibreSSL has none)")
    def test_openssl_verifies_our_signature(self):
        """Where OpenSSL 3 is installed (it is on the kit's CI): our signer against an independent implementation."""
        sk = os.urandom(32)
        msg = publish.DOMAIN + b'{"a":1}'
        der = bytes.fromhex("302a300506032b6570032100") + ed25519.public_key(sk)
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p / "k.pem").write_text("-----BEGIN PUBLIC KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PUBLIC KEY-----\n")
            (p / "m").write_bytes(msg)
            (p / "s").write_bytes(ed25519.sign(sk, msg))
            r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(p / "k.pem"), "-rawin",
                                "-in", str(p / "m"), "-sigfile", str(p / "s")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class KeygenTests(unittest.TestCase):
    def test_keygen_writes_a_private_file_and_prints_only_the_public_line(self):
        with tempfile.TemporaryDirectory() as d:
            k = pathlib.Path(d) / "sub" / "k.key"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(publish.main(["keygen", "--key", str(k)]), 0)
            self.assertEqual(stat.S_IMODE(k.stat().st_mode), 0o600)
            secret = publish.load_key(str(k))
            line = publish.PUBLIC_PREFIX + publish.b64u(ed25519.public_key(secret))
            self.assertIn(line, out.getvalue())
            self.assertNotIn(publish.b64u(secret), out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(publish.main(["keygen", "--key", str(k)]), 1)  # never over an existing key
            self.assertEqual(publish.load_key(str(k)), secret)

    def test_the_key_can_come_from_the_environment(self):
        line = publish.SECRET_PREFIX + publish.b64u(b"\x01" * 32)
        with mock.patch.dict(os.environ, {"IVN_LIBRARY_KEY": line}):
            self.assertEqual(publish.load_key(None), b"\x01" * 32)
        with mock.patch.dict(os.environ, {"IVN_LIBRARY_KEY": "ssh-ed25519 AAAA"}), self.assertRaises(publish.Stop):
            publish.load_key(None)


class PayloadTests(unittest.TestCase):
    def test_the_payload_carries_the_library_folder_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as d:
            p = project(pathlib.Path(d))
            (p / "src.py").write_text("SECRET_SOURCE = 1\n")
            pl = publish.payload(p, "standin", [{"customer": "c", "name": "C", "sites": ["c.ivendnext.com"]}])
            self.assertEqual((pl["version"], pl["card"], pl["manifest"]), ("1.2.0", CARD, MANIFEST))
            self.assertEqual(pl["recipient_sha256"],
                             hashlib.sha256(base64.b64decode(PEM.splitlines()[1])).hexdigest())
            self.assertNotIn("SECRET_SOURCE", json.dumps(pl))
            self.assertEqual(len(publish.unb64u(pl["nonce"])), 16)
            self.assertLess(abs(pl["at"] - time.time()), 5)

    def test_the_signature_covers_the_exact_bytes_sent(self):
        sk = os.urandom(32)
        with tempfile.TemporaryDirectory() as d:
            env = json.loads(publish.envelope(publish.payload(project(pathlib.Path(d)), "standin"), sk))
        body, sig = publish.unb64u(env["body"]), publish.unb64u(env["sig"])
        pk = ed25519.public_key(sk)
        self.assertEqual(env["key"], publish.key_id(pk))
        self.assertTrue(ed25519.verify(pk, publish.DOMAIN + body, sig))
        self.assertFalse(ed25519.verify(pk, body, sig))  # the domain line is part of what is signed
        self.assertFalse(ed25519.verify(pk, publish.DOMAIN + body.replace(b"1.2.0", b"1.2.1"), sig))

    def test_customer_addresses_come_from_a_file_or_the_environment(self):
        d = [{"customer": "c", "name": "C", "sites": ["c.ivendnext.com"]}]
        with mock.patch.dict(os.environ, {"LIBRARY_DELIVERIES": json.dumps(d)}):
            self.assertEqual(publish._json_from("LIBRARY_DELIVERIES", None), d)
        with mock.patch.dict(os.environ, {"LIBRARY_DELIVERIES": "{oops"}), self.assertRaises(publish.Stop):
            publish._json_from("LIBRARY_DELIVERIES", None)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(publish._json_from("LIBRARY_KEYS", None), [])

    def test_an_unknown_field_in_library_json_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = project(pathlib.Path(d), conf={"public": True, "maker": "Someone"})
            with self.assertRaises(publish.Stop):
                publish.payload(p, "standin")


class PublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Library)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/v1/publish"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_publish(self, d: pathlib.Path, proj: pathlib.Path, *extra) -> tuple[int, str]:
        key = d / "k.key"
        if not key.exists():
            with contextlib.redirect_stdout(io.StringIO()):
                publish.main(["keygen", "--key", str(key)])
        Library.public = ed25519.public_key(publish.load_key(str(key)))
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"IVN_LIBRARY_URL": self.url, "LIBRARY_DELIVERIES": ""}), \
                mock.patch.object(publish, "REMEMBER_DIR", d / "mem"), contextlib.redirect_stdout(out):
            code = publish.main(["publish", str(proj), "--partner", "standin", "--key", str(key),
                                 "--out", str(d / "library-keys.json"), *extra])
        return code, out.getvalue()

    def test_a_publish_signs_uploads_and_writes_sealed_keys_to_a_private_file(self):
        Library.seen, Library.reply = [], (200, {
            "upload": "U1", "partner": "standin", "app": "pp_stn", "version": "1.2.0", "preview": {"shelf": "S", "serial": 2},
            "preview_keys": [{"id": "K1", "sealed": "SEALED-ONE"}], "delivered": [], "keys": [],
            "public": "awaiting_approval", "request": "R1", "why": "first listing"})
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            code, out = self.run_publish(d, project(d))
            self.assertEqual(code, 0, out)
            self.assertEqual(Library.seen[0]["partner"], "standin")
            self.assertIn("WAITING for iVendNext's approval, request R1", out)
            self.assertNotIn("SEALED-ONE", out)  # keys go to the file, never the screen
            kf = d / "library-keys.json"
            self.assertEqual(stat.S_IMODE(kf.stat().st_mode), 0o600)
            self.assertEqual(json.loads(kf.read_text())["preview_keys"][0]["sealed"], "SEALED-ONE")

    def test_a_refusal_prints_the_librarys_words_and_exits_1(self):
        Library.seen, Library.reply = [], (403, {"refused": "not_your_app", "words": "this app's name is not yours: it is not under your company's first word or reserved to it"})
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            code, out = self.run_publish(d, project(d))
        self.assertEqual(code, 1)
        self.assertIn("not_your_app — this app's name is not yours: it is not under your company's first word or reserved to it", out)

    def test_the_kits_checks_refuse_before_anything_is_sent(self):
        Library.seen = []
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            proj = project(d, manifest={**MANIFEST, "app": "Not An App Name"})
            code, out = self.run_publish(d, proj)
            self.assertEqual(code, 1)
            self.assertIn("nothing was sent", out)
            (proj / "LICENSE").unlink()
            (proj / "library" / "manifest.json").write_text(json.dumps(MANIFEST))
            code, out = self.run_publish(d, proj)
            self.assertEqual(code, 1)
        self.assertEqual(Library.seen, [])

    def test_an_existing_keys_file_is_narrowed_and_an_unreachable_library_is_a_refusal(self):
        Library.seen, Library.reply = [], (200, {
            "upload": "U2", "partner": "standin", "app": "pp_stn", "version": "1.2.0", "preview": {"shelf": "S", "serial": 3},
            "preview_keys": [{"id": "K1", "sealed": "SEALED-TWO"}], "delivered": [], "keys": []})
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            kf = d / "library-keys.json"
            kf.write_text("{}")
            kf.chmod(0o644)
            code, out = self.run_publish(d, project(d))
            self.assertEqual(code, 0, out)
            self.assertEqual(stat.S_IMODE(kf.stat().st_mode), 0o600)
            with mock.patch.object(publish, "URL", "http://127.0.0.1:9/v1/publish"), \
                    mock.patch.dict(os.environ, {"IVN_LIBRARY_URL": ""}), contextlib.redirect_stdout(io.StringIO()) as o:
                os.environ.pop("IVN_LIBRARY_URL")
                code = publish.main(["publish", str(d / "proj"), "--partner", "standin", "--key", str(d / "k.key")])
            self.assertEqual(code, 1)
            self.assertIn("could not be reached", o.getvalue())

    def test_keys_wanted_without_a_recipient_pem_are_refused_before_sending(self):
        Library.seen = []
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            proj = project(d)
            (proj / "library" / "recipient.pem").unlink()
            code, out = self.run_publish(d, proj)
        self.assertEqual(code, 1)
        self.assertIn("recipient.pem is missing", out)
        self.assertEqual(Library.seen, [])

    def test_a_dry_run_sends_nothing(self):
        Library.seen = []
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            code, out = self.run_publish(d, project(d), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("DRY RUN: pp_stn 1.2.0", out)
        self.assertEqual(Library.seen, [])


    # ── the customers a publish remembers for the next one ──────────────────────

    SHOPS = [{"customer": "shop-a", "name": "Shop A", "sites": ["shop-a-test.staging.ivendnext.com", "shop-a.ivendnext.com"]},
             {"customer": "shop-b", "name": "Shop B", "sites": ["shop-b.ivendnext.com"]}]
    OK = {"upload": "U", "partner": "standin", "app": "pp_stn", "version": "1.2.0", "preview": {"shelf": "S", "serial": 1},
          "preview_keys": [], "delivered": [], "keys": [], "public": "unchanged"}

    def publish_with(self, d, mem, *extra, shops=None):
        if shops is not None:
            (d / "shops.json").write_text(json.dumps(shops))
            extra = (*extra, "--deliveries", str(d / "shops.json"))
        with mock.patch.object(publish, "REMEMBER_DIR", mem):
            return self.run_publish(d, d / "proj" if (d / "proj").exists() else project(d), *extra)

    def test_a_publish_that_names_customers_is_remembered_for_the_next_one(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            code, out = self.publish_with(d, mem, shops=self.SHOPS)
            self.assertEqual(code, 0, out)
            [f] = list(mem.glob("*.json"))
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)          # shop addresses: yours to read, nobody else's
            self.assertEqual(json.loads(f.read_text()), self.SHOPS)           # each entry as given: customer, name, sites
            self.assertNotIn("shop-a.ivendnext.com", out)                    # never printed
            code, out = self.publish_with(d, mem)                              # an update, no list given
            self.assertEqual(code, 0, out)
            self.assertEqual(Library.seen[-1]["deliveries"], self.SHOPS)
            self.assertIn("including 2 customers remembered from your last publish", out)
            self.assertNotIn("shop-a.ivendnext.com", out)

    def test_a_list_you_give_replaces_the_remembered_one(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            self.publish_with(d, mem, shops=self.SHOPS)
            self.publish_with(d, mem, shops=self.SHOPS[1:])
            self.assertEqual(Library.seen[-1]["deliveries"], self.SHOPS[1:])
            self.publish_with(d, mem)
            self.assertEqual(Library.seen[-1]["deliveries"], self.SHOPS[1:])
            self.publish_with(d, mem, shops=[])                                # an empty list, given: none, and forgotten
            self.assertEqual(Library.seen[-1]["deliveries"], [])
            self.publish_with(d, mem)
            self.assertEqual(Library.seen[-1]["deliveries"], [])

    def test_the_flag_publishes_to_none_and_keeps_what_is_remembered(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            self.publish_with(d, mem, shops=self.SHOPS)
            code, out = self.publish_with(d, mem, "--no-remembered-deliveries")
            self.assertEqual(code, 0, out)
            self.assertEqual(Library.seen[-1]["deliveries"], [])
            self.assertNotIn("remembered", out)
            self.publish_with(d, mem)
            self.assertEqual(Library.seen[-1]["deliveries"], self.SHOPS)

    def test_a_dry_run_writes_nothing_and_names_the_count_not_an_address(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            code, out = self.publish_with(d, mem, "--dry-run", shops=self.SHOPS)
            self.assertEqual(code, 0, out)
            self.assertFalse(mem.exists())                                     # nothing remembered from a dry run
            self.publish_with(d, mem, shops=self.SHOPS[:1])
            before = [(f.name, f.read_bytes()) for f in mem.glob("*")]
            code, out = self.publish_with(d, mem, "--dry-run")
            self.assertIn("including 1 customer remembered", out)
            self.assertIn("1 customer(s)", out)
            self.assertNotIn("shop-a", out)
            self.assertEqual([(f.name, f.read_bytes()) for f in mem.glob("*")], before)
            code, out = self.publish_with(d, mem, "--dry-run", shops=self.SHOPS)
            self.assertEqual([(f.name, f.read_bytes()) for f in mem.glob("*")], before)

    def test_a_publish_the_library_refuses_remembers_nothing_new(self):
        Library.seen, Library.reply = [], (403, {"refused": "not_your_app", "words": "no"})
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            code, out = self.publish_with(d, mem, shops=self.SHOPS)
            self.assertEqual(code, 1)
            self.assertFalse(mem.exists())

    def test_a_remembered_file_that_cannot_be_read_stops_the_publish_instead_of_dropping_customers(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            self.publish_with(d, mem, shops=self.SHOPS)
            [f] = list(mem.glob("*.json"))
            f.write_text("{not json")
            Library.seen = []
            code, out = self.publish_with(d, mem)
            self.assertEqual(code, 1)
            self.assertIn("--no-remembered-deliveries", out)
            self.assertEqual(Library.seen, [])

    def test_a_smaller_list_says_it_replaces_the_remembered_one_and_a_blank_file_names_no_one(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            self.publish_with(d, mem, shops=self.SHOPS)
            code, out = self.publish_with(d, mem, shops=self.SHOPS[1:])
            self.assertIn("this list leaves out 1 of the 2 customers remembered", out)
            self.assertNotIn("shop-", out)
            self.publish_with(d, mem, shops=self.SHOPS)
            (d / "blank.json").write_text("\n")
            code, out = self.publish_with(d, mem, "--deliveries", str(d / "blank.json"))
            self.assertEqual(Library.seen[-1]["deliveries"], self.SHOPS)         # the blank file did not wipe it

    def test_a_swapped_list_and_a_dry_run_both_say_who_is_left_out(self):
        Library.seen, Library.reply = [], (200, self.OK)
        swap = [self.SHOPS[0], {"customer": "shop-c", "name": "Shop C", "sites": ["shop-c.ivendnext.com"]}]
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            mem = d / "mem"
            self.publish_with(d, mem, shops=self.SHOPS)
            code, out = self.publish_with(d, mem, "--dry-run", shops=swap)         # same length, one customer different
            self.assertIn("this list leaves out 1 of the 2 customers remembered", out)
            self.assertNotIn("shop-", out)
            self.assertEqual(json.loads(next(mem.glob("*.json")).read_text()), self.SHOPS)

    def test_a_memory_that_cannot_be_written_does_not_fail_a_publish_the_library_accepted(self):
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "mem").write_text("a file where the folder should be")
            code, out = self.publish_with(d, d / "mem", shops=self.SHOPS)
            self.assertEqual(code, 0, out)
            self.assertIn("could not be remembered", out)

    def test_canary_without_the_write_the_next_publish_misses_the_customers(self):
        """If the write is dropped, the scenario of the first test above goes red: the second publish carries nobody."""
        Library.seen, Library.reply = [], (200, self.OK)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(publish, "remember", lambda *a: None):
            d = pathlib.Path(d)
            self.publish_with(d, d / "mem", shops=self.SHOPS)
            self.publish_with(d, d / "mem")
            self.assertEqual(Library.seen[-1]["deliveries"], [])
            self.assertNotEqual(Library.seen[-1]["deliveries"], self.SHOPS)


if __name__ == "__main__":
    unittest.main()
