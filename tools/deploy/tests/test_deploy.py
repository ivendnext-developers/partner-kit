"""Laptop tests of deploy, no site: the whole tool, over real HTTP, against a local stand-in that answers as the
shop's install screen methods do (`docs/extending/package_install.md` §7) and records every request.

    python3 -m unittest discover -s tools/deploy/tests -v
"""

import http.client
import io
import json
import os
import pathlib
import sys
import threading
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import deploy as D  # noqa: E402

KIT = HERE.parent.parent.parent
GOOD = json.loads((KIT / "samples/s1_warranty/manifest.json").read_text())
SHA = "5" * 64
NAME = f"{GOOD['app']} {GOOD['version']}"


class StandIn(ThreadingHTTPServer):
    """The install screen's methods. `statuses` is what the package record reads on each poll, in order."""

    def __init__(self, check=None, install=None, statuses=("Queued", "Installing", "Installed"), secrets_403=False):
        super().__init__(("127.0.0.1", 0), Handler)
        self.calls, self.statuses, self.secrets_403 = [], list(statuses), secrets_403
        self.last, self.mod = None, 0  # the record's `modified` moves only when a job writes it (here: when the status changes)
        self.check = check or {"ok": 1, "name": NAME, "refusals": [], "summary": "Makes 1 record type",
                               "summary_sha256": SHA, "changes": "", "mode": "install", "warnings": []}
        self.install = install or {"ok": 1, "name": NAME, "status": "Queued", "action": "install"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, code=200):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _route(self, verb):
        s, u = self.server, urllib.parse.urlsplit(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        args = json.loads(self.rfile.read(n)) if n else dict(urllib.parse.parse_qsl(u.query))
        path = urllib.parse.unquote(u.path)
        s.calls.append((verb, path, args))
        if self.headers.get("Authorization") != "token k1:s1":
            return self._send({"exc_type": "AuthenticationError"}, 401)
        if path == "/api/method/" + D.API + "check":
            return self._send({"message": s.check})
        if path == "/api/method/" + D.API + "install":
            return self._send({"message": s.install})
        if path in ("/api/method/" + D.API + "uninstall", "/api/method/" + D.API + "finish"):
            return self._send({"message": {"ok": 1, "status": "Queued", "action": path.rsplit(".", 1)[1]}})
        if path == f"/api/resource/{D.PKG}/{NAME}":
            st = s.statuses.pop(0) if len(s.statuses) > 1 else s.statuses[0]
            if st != s.last:
                s.last, s.mod = st, s.mod + 1
            doc = {"name": NAME, "app": GOOD["app"], "status": st, "modified": str(s.mod), "todo": "Switch the key on" if st == "Installed" else None,
                   "error": "it stopped" if st == "Failed" else None, "export_file": "/private/files/x.json" if st == "Uninstalled" else None}
            return self._send({"data": doc})
        if path == f"/api/resource/Retail Extension Install/{GOOD['app']}":
            return self._send({"data": {"items": json.dumps([{"kind": "remote_key", "name": "pp_wrc:warranty"},
                                                              {"kind": "doctype", "name": "PP WRC Term"}])}})
        if path == "/api/method/ivendnext_mpos.api.v1.get_password":
            if s.secrets_403:
                return self._send({"exc_type": "PermissionError"}, 403)
            return self._send({"message": "the-secret"})
        return self._send({"exc_type": "DoesNotExistError"}, 404)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


class DeployTests(unittest.TestCase):
    def run_tool(self, argv, **kw):
        srv = StandIn(**kw)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        out = io.StringIO()
        env = {"BASE": f"http://127.0.0.1:{srv.server_address[1]}", "KEY": "k1", "SECRET": "s1"}
        with mock.patch.dict(os.environ, env), mock.patch.object(D.time, "sleep", lambda s: None), redirect_stdout(out):
            try:
                code = D.main(argv)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), srv.calls

    def methods(self, calls):
        return [p.rsplit(".", 1)[-1] for _, p, _ in calls if p.startswith("/api/method/" + D.API)]

    def test_without_consent_no_install_request(self):
        code, out, calls = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json")])
        self.assertEqual(code, 0)
        self.assertEqual(self.methods(calls), ["check"])
        self.assertIn("Makes 1 record type", out)
        self.assertIn(SHA, out)
        self.assertIn("not installed", out)

    def test_consent_echoes_exactly_what_check_returned(self):
        code, out, calls = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.methods(calls), ["check", "install"])
        install = [a for _, p, a in calls if p.endswith(".install")][0]
        self.assertEqual(install, {"name": NAME, "summary_sha256": SHA})
        sent = [a for _, p, a in calls if p.endswith(".check")][0]
        self.assertEqual(json.loads(sent["manifest"]), GOOD)
        self.assertIn("status: Installed", out)
        self.assertIn("Switch the key on", out)
        self.assertIn("secret · Retail Remote App Key pp_wrc:warranty: the-secret", out)

    def test_a_changed_fingerprint_is_echoed_never_a_typed_one(self):
        other = "a" * 64
        code, out, calls = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent"],
                                         check={"ok": 1, "name": NAME, "summary": "x", "summary_sha256": other,
                                                "mode": "upgrade", "changes": "adds a field"})
        install = [a for _, p, a in calls if p.endswith(".install")][0]
        self.assertEqual(install["summary_sha256"], other)
        self.assertIn("adds a field", out)

    def test_a_local_refusal_sends_nothing(self):
        bad = dict(GOOD)
        bad.pop("version")
        p = pathlib.Path(self.id().rsplit(".", 1)[1] + ".json")
        p.write_text(json.dumps(bad))
        self.addCleanup(p.unlink)
        code, out, calls = self.run_tool([str(p), "--consent"])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn(D.V.VERSION_REASON.split("{")[0][:20], out)

    def test_a_site_refusal_stops_before_install(self):
        code, out, calls = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent"],
                                         check={"ok": 0, "name": NAME, "refusals": [
                                             {"where": "app", "name": "pp_wrc", "reason": "taken on this site"}]})
        self.assertEqual(code, 1)
        self.assertEqual(self.methods(calls), ["check"])
        self.assertIn("REFUSED app (pp_wrc): taken on this site", out)

    def test_install_refused_by_the_site(self):
        code, out, calls = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent"],
                                         install={"ok": 0, "refusals": [{"where": "consent", "name": None,
                                                                         "reason": "the summary changed"}]})
        self.assertEqual(code, 1)
        self.assertNotIn("waiting", out)

    def test_the_poll_ends_on_every_final_status(self):
        finals = ["Installed", "Failed", "Refused", "Upgrade Failed", "Checked", "Superseded", "Uninstalled", "Draft"]
        for final in finals:
            with self.subTest(final=final):
                code, out, _ = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent", "--wait", "1"],
                                             statuses=("Queued", "Installing", "Upgrading", final))
                self.assertIn(f"status: {final}", out)
                self.assertEqual(code, 0 if final in D.DONE_OK else 1)

    def test_a_job_that_never_ends_times_out(self):
        code, out, _ = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent", "--wait", "0"],
                                     statuses=("Installing",))
        self.assertEqual(code, 3)
        self.assertIn("still Installing", out)

    def test_uninstall_prints_the_export_file(self):
        code, out, calls = self.run_tool(["uninstall", NAME], statuses=("Queued", "Uninstalling", "Uninstalled"))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.methods(calls), ["uninstall"])
        self.assertIn("export file: /private/files/x.json", out)

    def test_finish_waits_for_its_job_not_the_old_status(self):
        # Finish queues its job without changing the status: the record still reads Failed until the job writes it
        code, out, calls = self.run_tool(["finish", NAME], statuses=("Failed", "Failed", "Failed", "Uninstalled"))
        self.assertEqual(self.methods(calls), ["finish"])
        self.assertEqual(code, 0, out)
        self.assertIn("status: Uninstalled", out)
        self.assertNotIn("status: Failed", out)
        code, out, _ = self.run_tool(["finish", NAME, "--wait", "1"], statuses=("Failed",))
        self.assertEqual(code, 3)
        self.assertIn("still Failed", out)

    def test_an_install_key_that_may_not_read_secrets_still_succeeds(self):
        code, out, _ = self.run_tool([str(KIT / "samples/s1_warranty/manifest.json"), "--consent"], secrets_403=True)
        self.assertEqual(code, 0, out)
        self.assertIn("status: Installed", out)
        self.assertIn("secrets not read", out)

    def test_a_manifest_that_is_not_json_is_refused_in_plain_words_and_sends_nothing(self):
        p = pathlib.Path(self.id().rsplit(".", 1)[1] + ".json")
        p.write_text('{"app": "pp_broken", "version": "0.0.1", ')
        self.addCleanup(p.unlink)
        err = io.StringIO()
        with redirect_stderr(err):
            code, _, calls = self.run_tool([str(p)])
        self.assertEqual((code, calls), (2, []))
        self.assertIn("cannot read the manifest: the file is not valid JSON: something is missing or extra at line 1, "
                      "column 42", err.getvalue())
        self.assertNotIn("property name", err.getvalue())

    def test_finish_and_usage(self):
        code, _, calls = self.run_tool(["uninstall"])
        self.assertEqual((code, calls), (2, []))
        code, _, calls = self.run_tool(["uninstall", NAME, "--consent"])
        self.assertEqual((code, calls), (2, []))


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

    def test_a_site_answer_cut_short_stops_in_words_never_a_crash(self):
        site = D.Site("https://shop.example", "k", "s")
        with mock.patch.object(D.urllib.request, "urlopen", cut_answer):
            with self.assertRaises(SystemExit) as e:
                site._req("/api/resource/Item")
        self.assertIn("the site did not answer: IncompleteRead", str(e.exception))


if __name__ == "__main__":
    unittest.main()
