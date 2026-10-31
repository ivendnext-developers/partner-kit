"""Many shops: the handshake, the key check and each shop's own secret, with no cloud and no shop. Run
    python3 -m unittest discover -s tools/app_template/tests -p 'test_*.py' -v

The library's signing keys never leave AWS, so these tests make their own key pair for each of L1 (paid) and F1 (free),
as the POS app's own tests do, and pin it in place of ours. Two tests use the real pins: a key signed by a test key is
refused by them, and a line our library really signed (the catalogue head, serial 24) verifies with L1.
"""
import base64
import datetime
import hashlib
import hmac
import http.client
import io
import json
import os
import pathlib
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE.parent))
import app  # noqa: E402
import dynamo  # noqa: E402
import ed25519  # noqa: E402
import local_key  # noqa: E402
import shops  # noqa: E402

PAID_SECRET, FREE_SECRET = hashlib.sha256(b"test L1").digest(), hashlib.sha256(b"test F1").digest()
KEYS = {"L1": (base64.b64encode(ed25519.public_key(PAID_SECRET)).decode(), frozenset({"paid"})),
        "F1": (base64.b64encode(ed25519.public_key(FREE_SECRET)).decode(), frozenset({"free"}))}
APP, A, B = "ivendnext_hello", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
NAME = f"{APP}:{app.KEY}"
# Served by https://library.ivendnext.app/catalogue.head (serial 24, 2026-10-13): signed in AWS KMS with L1.
REAL_HEAD = ("IVNC1-eyJraWQiOiJMMSIsInB1Ymxpc2hlZCI6IjIwMjYtMTAtMTNUMDg6Mzg6NTVaIiwic2VyaWFsIjoyNCwic2hhMjU2IjoiNGQxZDliNDA1"
             "ZTgwNWZhMDI3YzcyMzU2YWZjODk3Y2I4MDAzOWIzNDBjYzM3MzBkOGI0YzBmYTZmNTEwOWM5YiIsInR5cCI6ImFwcGxpYi1jYXRhbG9ndWUi"
             "LCJ2IjoxfQ.trx4TVcHN4JFIfYLkg27l1IBUp0OgT17WofKtqyPx7NWJrxH80XbTFu1z167B9Shmwfh-yc16PilovG97n0AAQ")


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_key(host=A, app_id=APP, kind="paid", kid=None, secret=None, **extra) -> str:
    kid = kid or ("L1" if kind == "paid" else "F1")
    secret = secret or (PAID_SECRET if kid == "L1" else FREE_SECRET)
    payload = {"typ": "applib-key", "v": 1, "kid": kid, "id": "K7Q2M9XW4TPA", "app": app_id, "host": host,
               "to": "free" if kind == "free" else "customer:test", "kind": kind, "iat": "2026-10-13", "exp": None, **extra}
    pb = json.dumps(payload, separators=(",", ":")).encode()
    return f"IVN1-{b64u(pb)}.{b64u(ed25519.sign(secret, pb))}"


def sign(secret: str, ts: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).digest()).decode()


class Signature(unittest.TestCase):
    RFC = [  # RFC 8032 §7.1, tests 1 to 3: secret, public key, message, signature
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
         "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
         "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
        ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
         "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
         "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ]

    def test_rfc_8032_tests_1_to_3(self):
        for sk, pk, msg, sig in ((bytes.fromhex(x) for x in v) for v in self.RFC):
            self.assertEqual(ed25519.public_key(sk), pk)
            self.assertEqual(ed25519.sign(sk, msg), sig)
            self.assertTrue(ed25519.verify(pk, msg, sig))

    def test_what_must_not_verify(self):
        _, pk, msg, sig = (bytes.fromhex(x) for x in self.RFC[1])
        self.assertFalse(ed25519.verify(pk, msg + b"x", sig))                        # another message
        self.assertFalse(ed25519.verify(pk, msg, sig[:63] + bytes([sig[63] ^ 1])))   # another signature
        other = bytes.fromhex(self.RFC[2][1])
        self.assertFalse(ed25519.verify(other, msg, sig))                            # another key
        y_too_big = int.to_bytes(ed25519.p + 1, 32, "little")                        # a point encoding with y >= p
        self.assertFalse(ed25519.verify(pk, msg, y_too_big + sig[32:]))
        self.assertFalse(ed25519.verify(y_too_big, msg, sig))
        self.assertFalse(ed25519.verify(pk[:31], msg, sig))
        self.assertFalse(ed25519.verify(pk, msg, sig[:63]))

    def test_a_line_our_library_signed_verifies_with_l1_and_not_f1(self):
        pb, sig = (base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)) for p in REAL_HEAD[6:].split("."))
        self.assertTrue(ed25519.verify(base64.b64decode(shops.LIBRARY_KEYS["L1"][0]), pb, sig))
        self.assertFalse(ed25519.verify(base64.b64decode(shops.LIBRARY_KEYS["F1"][0]), pb, sig))

    def test_a_signature_with_s_out_of_range_is_refused(self):
        pk, sig = ed25519.public_key(PAID_SECRET), ed25519.sign(PAID_SECRET, b"m")
        bad = sig[:32] + int.to_bytes(int.from_bytes(sig[32:], "little") + ed25519.L, 32, "little")
        self.assertFalse(ed25519.verify(pk, b"m", bad))

    def test_the_cryptography_library_agrees_when_present(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("the cryptography package is not installed (the template does not need it)")
        for n in range(5):
            sk, msg = os.urandom(32), os.urandom(n * 31)
            self.assertEqual(Ed25519PrivateKey.from_private_bytes(sk).sign(msg), ed25519.sign(sk, msg))


class KeyCheck(unittest.TestCase):
    def check(self, line, site=A):
        return shops.check_key(line, APP, site, KEYS)

    def refused(self, line, site=A):
        with self.assertRaises(shops.Refused) as c:
            self.check(line, site)
        return c.exception.code

    def test_a_paid_key_and_a_free_key_for_this_app_and_site(self):
        self.assertEqual(self.check(make_key())["kind"], "paid")
        self.assertEqual(self.check(make_key(kind="free"))["kind"], "free")
        self.assertEqual(self.check("  " + make_key()[:40] + "\n " + make_key()[40:])["host"], A)   # a mail client's breaks

    def test_canary_a_key_for_another_app(self):
        self.assertEqual(self.refused(make_key(app_id="pp_lyl")), "key_other_app")

    def test_canary_a_key_for_another_site(self):
        self.assertEqual(self.refused(make_key(host=B)), "key_other_site")
        self.assertEqual(self.refused(make_key(), site=B), "key_other_site")

    def test_canary_a_paid_key_signed_by_f1(self):
        self.assertEqual(self.refused(make_key(kind="paid", kid="F1", secret=FREE_SECRET)), "key_signature")

    def test_canary_a_free_key_signed_by_l1(self):
        self.assertEqual(self.refused(make_key(kind="free", kid="L1", secret=PAID_SECRET)), "key_signature")

    def test_canary_a_bad_signature(self):
        line = make_key()
        payload, sig = line[5:].split(".")
        forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
        forged["host"] = B                                            # the same signature over other bytes
        self.assertEqual(self.refused("IVN1-" + b64u(json.dumps(forged).encode()) + "." + sig, site=B), "key_signature")
        self.assertEqual(self.refused(make_key(secret=hashlib.sha256(b"someone else").digest())), "key_signature")

    def test_canary_a_kid_this_app_does_not_pin(self):
        self.assertEqual(self.refused(make_key(kid="L9", secret=PAID_SECRET)), "key_signature")

    def test_the_real_pins_refuse_a_key_our_library_did_not_sign(self):
        with self.assertRaises(shops.Refused):
            shops.check_key(make_key(), APP, A)

    def test_what_is_not_a_key(self):
        for line in ("", None, "IVN1-", "IVN1-a.b.c", "IVNS1-" + make_key()[5:], make_key().replace("IVN1-", "IVN2-"),
                     "IVN1-" + b64u(b"[]") + "." + b64u(b"x" * 64), "IVN1-" + b64u(b"{" * 2000) + "." + b64u(b"x" * 64)):
            self.assertEqual(self.refused(line), "key_form")
        self.assertEqual(self.refused(make_key(typ="applib-shelf-key")), "key_form")

    def test_nothing_else_is_checked(self):
        # No end date and no withdrawn list here: the site checked both at install.
        self.assertEqual(self.check(make_key(exp="2020-01-01"))["exp"], "2020-01-01")


class Service(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.file = os.path.join(d, "shops.json")
        self.log = io.StringIO()
        conf = app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.file})
        conf["keys"] = KEYS
        self.srv = app.make_server(conf, port=0, log=self.log)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def post(self, path, body: dict, site=A, secret=None):
        raw = json.dumps(body).encode()
        ts = str(int(time.time()))
        h = {"Content-Type": "application/json"}
        if site is not None:
            h[app.SITE] = site
        if secret is not None:
            h.update({"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sign(secret, ts, raw)})
        req = urllib.request.Request(self.base + path, data=raw, method="POST", headers=h)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def connect(self, site=A, secret="secret-a", key=None, **extra):
        body = {"key": key or make_key(host=site), "site": site, "secrets": {NAME: secret, "other:record": "x"}, **extra}
        return self.post(app.CONNECT, body, site=site)

    def press(self, site=A, secret="secret-a"):
        return self.post(app.ROUTE, {"context": {"lines": []}}, site=site, secret=secret)

    def test_connect_then_a_call_signed_with_the_shops_secret(self):
        self.assertEqual(self.connect(), (200, {"connected": A}))
        code, out = self.press()
        self.assertEqual(code, 200)
        self.assertEqual(out["message"]["body"], "There are no items on this sale yet.")
        stored = json.loads(pathlib.Path(self.file).read_text())[A]
        self.assertEqual((stored["url"], stored["kind"], stored["secrets"][NAME]), (f"https://{A}", "paid", "secret-a"))

    def test_the_shop_is_called_back_at_its_own_address_never_one_the_call_names(self):
        self.connect(url="https://elsewhere.example.com")
        self.assertEqual(json.loads(pathlib.Path(self.file).read_text())[A]["url"], f"https://{A}")

    def test_canary_a_site_the_app_does_not_know(self):
        self.connect()
        self.assertEqual(self.press(site=B)[0], 401)
        self.assertEqual(self.press(site=None)[0], 401)
        self.assertEqual(self.press(site="not a site")[0], 401)

    def test_canary_another_shops_secret(self):
        self.connect(A, "secret-a")
        self.connect(B, "secret-b")
        self.assertEqual(self.press(A, "secret-b")[0], 401)           # B's call that names A's site
        self.assertEqual(self.press(B, "secret-a")[0], 401)
        self.assertEqual((self.press(A, "secret-a")[0], self.press(B, "secret-b")[0]), (200, 200))

    def test_canary_another_records_secret_does_not_sign_this_route(self):
        self.connect()
        self.assertEqual(self.press(secret="x")[0], 401)              # "other:record" is the shop's, not this route's

    def test_canary_the_same_key_from_another_sites_address(self):
        key = make_key(host=A)
        self.assertEqual(self.connect(site=B, key=key), (403, {"refused": "key_other_site"}))
        self.assertEqual(self.press(B, "secret-a")[0], 401)

    def test_the_header_and_the_body_must_name_the_same_site(self):
        body = {"key": make_key(host=A), "site": A, "secrets": {NAME: "s"}}
        self.assertEqual(self.post(app.CONNECT, body, site=B), (400, {"refused": "bad_request"}))
        self.assertEqual(self.post(app.CONNECT, body, site=None), (400, {"refused": "bad_request"}))
        self.assertEqual(self.post(app.CONNECT, dict(body, site=A.upper()), site=A), (400, {"refused": "bad_request"}))

    def test_a_connect_that_is_not_one(self):
        for body in ({"key": make_key(), "site": A}, {"key": make_key(), "site": A, "secrets": {NAME: 1}},
                     {"key": make_key(), "site": A, "secrets": {f"n{i}": "s" for i in range(101)}}):
            self.assertEqual(self.post(app.CONNECT, body)[0], 400)
        self.assertEqual(self.connect(key=make_key(app_id="pp_lyl")), (403, {"refused": "key_other_app"}))
        self.assertFalse(os.path.exists(self.file))

    def test_disconnect_forgets_the_shop(self):
        self.connect()
        self.assertEqual(self.post(app.DISCONNECT, {"key": make_key(host=A), "site": A}), (200, {"disconnected": A}))
        self.assertEqual(self.press()[0], 401)
        self.assertEqual(self.post(app.DISCONNECT, {"key": make_key(host=A), "site": A})[0], 200)   # twice: the same

    def test_canary_disconnect_needs_this_shops_key(self):
        self.connect(A)
        self.assertEqual(self.post(app.DISCONNECT, {"key": make_key(host=B), "site": A})[0], 403)
        self.assertEqual(self.press()[0], 200)

    def test_a_second_connect_rotates_and_keeps_the_old_secret_for_the_overlap(self):
        self.connect(secret="first")
        self.connect(secret="second")
        self.assertEqual((self.press(secret="second")[0], self.press(secret="first")[0]), (200, 200))
        self.connect(secret="third")
        self.assertEqual((self.press(secret="third")[0], self.press(secret="second")[0], self.press(secret="first")[0]),
                         (200, 200, 401))

    def test_a_free_key_connects_a_free_app(self):
        self.assertEqual(self.connect(key=make_key(kind="free"))[0], 200)
        self.assertEqual(json.loads(pathlib.Path(self.file).read_text())[A]["kind"], "free")

    def test_the_file_is_readable_by_this_user_alone_and_the_log_holds_no_secret(self):
        self.connect(secret="secret-a")
        self.press()
        self.assertEqual(stat.S_IMODE(os.stat(self.file).st_mode), 0o600)
        self.assertNotIn("secret-a", self.log.getvalue())
        self.assertNotIn("IVN1-", self.log.getvalue())

    def test_a_store_that_does_not_answer_is_503_never_a_pass(self):
        class Down:
            def get(self, site):
                raise dynamo.StoreError("down")
            put = delete = get
        conf = app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.file})
        conf.update(store=Down(), keys=KEYS)
        srv = app.make_server(conf, port=0, log=io.StringIO())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertEqual(self.press()[0], 503)
        self.assertEqual(self.connect(), (503, {"refused": "unavailable"}))


class Settings(unittest.TestCase):
    def test_many_shops_needs_a_store(self):
        with self.assertRaises(SystemExit):
            app.settings({"IVN_LIBRARY_APP": APP})
        self.assertIsInstance(app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": "/tmp/x.json"})["store"], shops.FileStore)
        with self.assertRaises(SystemExit):
            app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_TABLE": "t"})          # a table needs its region
        self.assertIsInstance(app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_TABLE": "t", "AWS_REGION": "us-east-1"})["store"],
                              dynamo.TableStore)


class LocalMode(unittest.TestCase):
    """IVN_LOCAL=1: a shop on this machine connects and is called back over http; every other site is as before."""
    LOCAL = "shop.localhost:8000"

    def setUp(self):
        d = tempfile.mkdtemp()
        self.file = os.path.join(d, "shops.json")
        secret_file, self.keys_file = local_key.keygen(pathlib.Path(d) / "keys")
        self.seed = base64.b64decode(secret_file.read_text().strip())

    def serve(self, **env):
        conf = app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.file, **env})
        conf["keys"] = KEYS
        srv = app.make_server(conf, port=0, log=io.StringIO())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        svc = Service()
        svc.base = f"http://127.0.0.1:{srv.server_address[1]}"
        return svc

    def local(self):
        return self.serve(IVN_LOCAL="1", IVN_LOCAL_LIBRARY_KEYS=str(self.keys_file))

    def stored(self, site):
        return json.loads(pathlib.Path(self.file).read_text())[site]

    def test_a_shop_on_this_machine_connects_and_is_called_back_over_http(self):
        svc = self.local()
        key = local_key.sign(self.seed, APP, self.LOCAL)
        self.assertEqual(svc.connect(self.LOCAL, key=key), (200, {"connected": self.LOCAL}))
        self.assertEqual(self.stored(self.LOCAL)["url"], f"http://{self.LOCAL}")
        self.assertEqual(svc.press(self.LOCAL)[0], 200)
        self.assertEqual(svc.post(app.DISCONNECT, {"key": key, "site": self.LOCAL}, site=self.LOCAL)[0], 200)
        self.assertEqual(svc.press(self.LOCAL)[0], 401)

    def test_every_other_site_keeps_https_in_local_mode(self):
        svc = self.local()
        self.assertEqual(svc.connect(A)[0], 200)
        self.assertEqual(self.stored(A)["url"], f"https://{A}")

    def test_canary_a_shop_on_this_machine_without_local_mode(self):
        svc = self.serve()
        self.assertEqual(svc.connect(self.LOCAL, key=make_key(host=self.LOCAL)), (400, {"refused": "bad_request"}))
        self.assertFalse(os.path.exists(self.file))

    def test_canary_a_local_key_never_signs_for_another_site(self):
        svc = self.local()
        key = make_key(host=A, kid=local_key.KID, secret=self.seed)
        self.assertEqual(svc.connect(A, key=key), (403, {"refused": "key_signature"}))

    def test_canary_a_local_key_without_its_keys_file(self):
        svc = self.serve(IVN_LOCAL="1")
        key = local_key.sign(self.seed, APP, self.LOCAL)
        self.assertEqual(svc.connect(self.LOCAL, key=key), (403, {"refused": "key_signature"}))

    def test_what_is_on_this_machine(self):
        for s in ("localhost", "localhost:8000", "shop.localhost:8000", "a.b.localhost", "127.0.0.1:8000", "[::1]:8000"):
            self.assertTrue(shops.is_local(s), s)
            self.assertEqual(shops.site_of(s.upper()), s)
        for s in ("localhost.evil.com", "evil.com:8000", "127.0.0.2", "10.0.0.1:8000", "localhost:", "shop.localhost/x"):
            self.assertFalse(shops.is_local(s), s)
        self.assertIsNone(shops.site_of("evil.com:8000"))

    def test_local_mode_is_refused_where_it_does_not_belong(self):
        with self.assertRaises(SystemExit):
            app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_TABLE": "t", "AWS_REGION": "us-east-1", "IVN_LOCAL": "1"})
        with self.assertRaises(SystemExit):
            app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.file, "IVN_LOCAL_LIBRARY_KEYS": str(self.keys_file)})
        bad = pathlib.Path(self.file).with_name("bad.json")
        bad.write_text('{"LOCAL": ["not a key", ["paid"]]}')
        with self.assertRaises(SystemExit):
            app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.file, "IVN_LOCAL": "1",
                          "IVN_LOCAL_LIBRARY_KEYS": str(bad)})

    def test_canary_a_shop_connected_in_local_mode_is_ignored_without_it(self):
        svc = self.local()
        self.assertEqual(svc.connect(self.LOCAL, key=local_key.sign(self.seed, APP, self.LOCAL))[0], 200)
        self.assertEqual(svc.press(self.LOCAL)[0], 200)
        plain = self.serve()        # the same shops file, local mode off
        self.assertEqual(plain.press(self.LOCAL)[0], 401)
        self.assertEqual(shops.FileStore(self.file).sites(), [])
        self.assertEqual(shops.FileStore(self.file, local=True).sites(), [self.LOCAL])

    def test_canary_a_local_key_never_disconnects_another_site(self):
        svc = self.local()
        self.assertEqual(svc.connect(A)[0], 200)
        key = make_key(host=A, kid=local_key.KID, secret=self.seed)
        self.assertEqual(svc.post(app.DISCONNECT, {"key": key, "site": A}, site=A), (403, {"refused": "key_signature"}))
        self.assertEqual(svc.press(A)[0], 200)

    def test_canary_a_local_keys_file_never_names_a_pinned_key(self):
        named = pathlib.Path(self.file).with_name("pinned.json")
        named.write_text(json.dumps({"L1": json.loads(self.keys_file.read_text())[local_key.KID]}))
        with self.assertRaises(SystemExit):
            app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.file, "IVN_LOCAL": "1",
                          "IVN_LOCAL_LIBRARY_KEYS": str(named)})

    def test_canary_keygen_never_replaces_a_pair_unasked(self):
        out = self.keys_file.parent
        before = (out / "library.secret").read_text()
        with self.assertRaises(SystemExit):
            local_key.keygen(out)
        self.assertEqual((out / "library.secret").read_text(), before)
        os.chmod(out / "library.secret", 0o644)
        local_key.keygen(out, force=True)
        self.assertNotEqual((out / "library.secret").read_text(), before)
        self.assertEqual(stat.S_IMODE(os.stat(out / "library.secret").st_mode), 0o600)

    def test_the_local_secret_is_readable_by_this_user_alone(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.keys_file.with_name("library.secret")).st_mode), 0o600)

    def test_local_key_signs_only_for_this_machine(self):
        with self.assertRaises(SystemExit):
            local_key.sign(self.seed, APP, A)


class Table(unittest.TestCase):
    def test_the_request_signature_matches_aws_own_library(self):
        # Recorded from botocore 1.43.112 SigV4Auth on the same request (2026-10-13), so this needs no package.
        h = dynamo.sign("POST", "dynamodb.us-east-1.amazonaws.com", "/", "us-east-1", "dynamodb",
                        {"content-type": "application/x-amz-json-1.0", "x-amz-target": "DynamoDB_20120810.GetItem"},
                        b'{"TableName":"t","Key":{"site":{"S":"a.b"}}}',
                        {"key": "AKIDEXAMPLE", "secret": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "token": "TOKEN/abc+="},
                        datetime.datetime(2026, 10, 13, 11, 7, 31, tzinfo=datetime.timezone.utc))
        self.assertTrue(h["authorization"].endswith("Signature=a51af1bf9203c253828c382b84abba648d41e255325b0314cdebc2c18715b3d1"))

    def test_a_claim_is_one_conditional_write_and_a_refusal_is_false(self):
        t, sent = dynamo.TableStore("t", "us-east-1"), []

        def call(op, payload):
            sent.append((op, payload))
            if len(sent) > 1:
                raise dynamo.StoreError(f"{op} answered 400 ConditionalCheckFailedException")
            return {}

        t._call = call
        self.assertTrue(t.claim("press|a.b|k", 1000.0, 60))
        self.assertFalse(t.claim("press|a.b|k", 1001.0, 60))
        op, q = sent[0]
        self.assertEqual((op, q["Item"]["site"], q["Item"]["at"]), ("PutItem", {"S": "press|a.b|k"}, {"N": "1000.0"}))
        self.assertEqual(q["ConditionExpression"], "attribute_not_exists(site) OR #at <= :stale")
        self.assertEqual(q["ExpressionAttributeValues"], {":stale": {"N": "940.0"}})

    def test_a_claim_the_table_cannot_take_is_an_error_never_a_pass(self):
        t = dynamo.TableStore("t", "us-east-1")

        def call(op, payload):
            raise dynamo.StoreError(f"{op} answered 400 AccessDeniedException")

        t._call = call
        with self.assertRaises(dynamo.StoreError):
            t.claim("press|a.b|k", 1000.0, 60)

    def test_the_tables_sites_never_list_a_claim(self):
        t = dynamo.TableStore("t", "us-east-1")
        t._call = lambda op, q: {"Items": [{"site": {"S": "a.b"}}, {"site": {"S": "press|a.b|k"}}]}
        self.assertEqual(t.sites(), ["a.b"])

    @unittest.skipUnless(os.environ.get("IVN_TEST_SHOPS_TABLE"), "a real table: set IVN_TEST_SHOPS_TABLE and AWS_* to run")
    def test_a_real_table(self):
        t = dynamo.TableStore(os.environ["IVN_TEST_SHOPS_TABLE"], os.environ.get("AWS_REGION", "us-east-1"))
        site = f"test-{os.getpid()}.example.com"
        t.put(site, {"site": site, "secrets": {"n": "v"}})
        self.assertEqual(t.get(site)["secrets"], {"n": "v"})
        self.assertIn(site, t.sites())
        t.delete(site)
        self.assertIsNone(t.get(site))
        name, now = f"press|{site}|k", time.time()
        self.assertTrue(t.claim(name, now, 60))
        self.assertFalse(t.claim(name, now + 1, 60))          # held: the table refuses the second copy
        self.assertTrue(t.claim(name, now + 61, 60))          # stale: taken over
        self.assertNotIn(name, t.sites())
        t.delete(name)


class FileClaim(unittest.TestCase):
    def test_a_claim_is_held_until_deleted_or_stale_and_never_listed(self):
        f = shops.FileStore(os.path.join(tempfile.mkdtemp(), "shops.json"))
        f.put(A, {"site": A})
        self.assertTrue(f.claim("press|x|k", 1000.0, 60))
        self.assertFalse(f.claim("press|x|k", 1059.0, 60))
        self.assertTrue(f.claim("press|x|k", 1061.0, 60))
        self.assertEqual(f.sites(), [A])
        f.delete("press|x|k")
        self.assertTrue(f.claim("press|x|k", 1062.0, 60))


def cut_answer(*args, **kwargs):
    """What ``urlopen`` / ``opener.open`` give back when the answer starts and the connection closes before its end: reading it
    raises ``http.client.IncompleteRead``, an ``HTTPException`` that is not an ``OSError``."""
    class Answer:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *n):
            raise http.client.IncompleteRead(b"")
    return Answer()


class AnswerCutShort(unittest.TestCase):
    """An answer cut short (``http.client.IncompleteRead``) is handled on the path a refused connection already takes."""

    def test_a_table_answer_cut_short_is_a_store_error_never_a_crash(self):
        t = dynamo.TableStore("t", "us-east-1", creds=mock.Mock(get=lambda: {"key": "AKIDEXAMPLE", "secret": "x", "token": "t"}))
        with mock.patch.object(dynamo.urllib.request, "urlopen", cut_answer):
            with self.assertRaises(dynamo.StoreError) as e:
                t.get("a.b")
        self.assertIn("unreachable (IncompleteRead)", str(e.exception))


if __name__ == "__main__":
    unittest.main()
