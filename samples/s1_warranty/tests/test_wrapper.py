"""S1's remote binding (``remote/wrapper.py``, the "Warranty" till key on your own server) answers the test call
(``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py): checked as a real call, then answered 200
{"test": "ok", "point": "warranty"} without looking anything up; a route it does not have is 404.

    python3 -m unittest discover -s samples/s1_warranty/tests -p 'test_wrapper.py' -v
"""

import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE, KIT = HERE.parent, HERE.parents[2]


class TestCall(unittest.TestCase):
    BAD = b"not a call"          # a body the binding cannot read: a real call with it is never answered 200
    routes = {"/point/warranty": ("warranty", "remote-point-secret")}

    def setUp(self):
        """A copy of the sample beside the template's service, with the two settings files the wrapper reads at start (the
        shop's address points nowhere: the binding, if it ran, could not read the item groups)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        copy = Path(d, "samples", SAMPLE.name)
        for part in ("core.py", "service", "remote"):
            src = SAMPLE / part
            (shutil.copytree(src, copy / part, ignore=shutil.ignore_patterns("__pycache__", ".env.local")) if src.is_dir()
             else (copy.mkdir(parents=True, exist_ok=True), shutil.copy(src, copy / part)))
        shutil.copytree(KIT / "tools" / "app_template" / "service", Path(d, "tools", "app_template", "service"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        port = self.free_port()
        (copy / "service" / ".env.local").write_text("PP_BASE=http://127.0.0.1:9\nPP_KEY=k\nPP_SECRET=s\n")
        (copy / "remote" / ".env.local").write_text(f"PP_POINT_SECRET=remote-point-secret\nPP_POINT_PORT={port}\n")
        self.serve([str(copy / "remote" / "wrapper.py")], str(copy), port)

    def serve(self, argv, cwd, port):
        """Run the server in its own process; it prints its line just before it serves its port."""
        import socket, subprocess
        self.port = port
        p = subprocess.Popen([sys.executable, "-I", "-B", *argv], cwd=cwd, env={"PATH": os.environ.get("PATH", "")},
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        def stop():
            p.kill()
            p.communicate()
        self.addCleanup(stop)
        self.assertIn(f":{port}", p.stdout.readline())
        for _ in range(200):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)

    @staticmethod
    def free_port():
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def call(self, path, raw, secret, test=True):
        import urllib.error, urllib.request
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=raw, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (urllib.error.URLError, OSError):     # the handler failed on the body: the connection closed unanswered
            return 0, None

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and failed
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
