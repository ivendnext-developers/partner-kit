"""Start an app's one service with --local and send each of its connection points a signed test call, then a mis-signed
one: what a developer's ``ivn test --local`` does. Used by test_combine.py.

    python3 tools/manifest/tests/local_call.py apps/<your app>
"""
import base64
import hashlib
import hmac
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _post(url: str, secret: str) -> tuple[int, dict]:
    body, ts = b"{}", str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).digest()).decode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "X-iVendNext-Site": "localhost", "X-iVendNext-Test": "1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            return e.code, json.loads(e.read() or b"{}")


def call_every_point(app: pathlib.Path) -> list:
    """[(route, (status, answer) signed, (status, answer) mis-signed)] for every connection point of the app."""
    app = pathlib.Path(app).resolve()
    values = dict(l.split("=", 1) for l in (app / ".env.local").read_text(encoding="utf-8").splitlines()
                  if "=" in l and not l.startswith("#"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen([sys.executable, "-I", str(app / "service" / "app.py"), "--local"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env={"PATH": os.environ.get("PATH", ""), "PORT": str(port)})
    try:
        if '"listening"' not in p.stdout.readline():
            raise RuntimeError(p.stderr.read()[-1500:])
        dispatch = json.loads((app / "service" / "dispatch.json").read_text(encoding="utf-8"))
        out = []
        for m in dispatch["mounts"].values():
            for path in m.get("points") or {}:
                url = f"http://localhost:{port}{path}"
                out.append((path, _post(url, values["IVN_TEST_SECRET"]), _post(url, "not-the-test-secret")))
        return out
    finally:
        p.terminate()
        p.communicate(timeout=10)


if __name__ == "__main__":
    for row in call_every_point(pathlib.Path(sys.argv[1])):
        print(*row)
