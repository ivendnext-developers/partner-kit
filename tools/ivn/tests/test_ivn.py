"""`ivn` against a stub server: the same doors, paths and refusals as hosting.ivendnext.app, with real folders made by the
kit's own `combine` and `add`, so what a test reads back is what the command really printed and really wrote. The words
quoted here are the experience spec's rows; the row is named beside each test.

    python3 -m unittest discover -s tools/ivn/tests
"""
from __future__ import annotations

import contextlib
import http.server
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock
import unittest.mock

KIT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(KIT / "tools" / "ivn"))
sys.path.insert(0, str(KIT / "tools" / "manifest"))
sys.path.insert(0, str(KIT / "tools" / "app_template"))
import combine  # noqa: E402
import ivn  # noqa: E402
import validate_app  # noqa: E402

TOKEN = "ivn_tok_" + "a" * 43
ONE_APP = "ivn_tok_" + "b" * 43
REVOKED = "ivn_tok_" + "c" * 43
SITE = "retailer.ivendnext.com"
M09 = ("Note: {v} ({what} by {who}, 3 Nov 2026 10:00 UTC) came in after the version this folder started from, so its "
       "change is not in this one: run ivn pull to bring it in.")
M28 = "This token was revoked or has expired. Run ivn login again, or make a new token on My apps > Tokens."


class Refuse(Exception):
    def __init__(self, code, words, status=409):
        self.code, self.words, self.status = code, words, status


class Stub:
    """The doors. `apps`: {app: {versions: [{version, by, how, what, sites, zip}], ...}}."""

    def __init__(self, tmp: pathlib.Path):
        self.tmp, self.apps, self.calls, self.polls, self.sandbox = tmp, {}, [], {}, {"site": "acme.sandbox.ivend.co"}
        self.objects, self.pending = {}, {}
        self.test_results = ["tgr_guard (a check at Pay): Passed, answered in 0.31 s",
                             "lyl_member (a till key): Passed, answered in 0.42 s"]
        self.money = {"lines": ["Publishing is free.", "This app runs all the time: Starter $49, Standard $129, Managed $399 a "
                                                       "month; the first month on your card at checkout, then monthly; cancel "
                                                       "at any month end."],
                      "plan": None, "plans": [{"plan": "starter", "words": "Starter $49: a till key or a check, low volume"},
                                              {"plan": "standard", "words": "Standard $129: a connected app"},
                                              {"plan": "managed", "words": "Managed $399: we also test it before each iVendNext upgrade"}],
                      "asks_pay": True}
        self.listed = False
        self.message = ("Acme has sent you an app, ACME MEMBER TILL 1.0.0.\n\n1. In iVendNext Desk open App library and press "
                        "Open your shelf at the top of the page.\n2. Paste this key:\n\nIVNS1-the-key\n\n3. Press Install. You will "
                        "see what it changes before anything is installed.")  # the library's own shape

    # ── the app's folders ──

    def keep(self, app, version, data, by, how, what):
        self.objects[f"folders/{app}/{version}.zip"] = data
        row = self.apps.setdefault(app, {"versions": []})
        row["versions"].append({"version": version, "by": by, "how": how, "what": what, "sites": [], "at": 0,
                                "key": f"folders/{app}/{version}.zip"})
        row["latest"] = version

    def with_version(self, folder: pathlib.Path, version: str) -> bytes:
        for name, keys in (("app.json", ("version", "base")), ("manifest.json", ("version",))):
            d = json.loads((folder / name).read_text("utf-8"))
            for k in keys:
                d[k] = version
            (folder / name).write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", "utf-8")
        return ivn.zip_folder(folder)

    def row(self, app):
        if app not in self.apps:
            raise Refuse("no_app", "This app is not one of your company's apps on My apps.", 404)
        return self.apps[app]

    # ── the doors ──

    def device(self, b):
        return {"device_code": "d" * 43, "user_code": "BCDF-GHJK", "interval": 0, "expires_in": 5,
                "verification_uri_complete": "https://developer.ivendnext.com/apps?code=BCDF-GHJK"}

    def device_token(self, b):
        self.polls["device"] = self.polls.get("device", 0) + 1
        if self.polls["device"] < 2:
            raise Refuse("device_pending", "authorization_pending", 428)
        return {"token": TOKEN, "company": "acme", "login": "acme-dev", "name": "Acme Retail Solutions"}

    def new(self, b):
        if b.get("own_folder"):
            app = b["name"].replace(" ", "_").lower()
            self.apps[app] = {"versions": [], "latest": None}
            return {"app": app, "version": None}
        samples, prefix = b["samples"], b["name"]
        with tempfile.TemporaryDirectory() as tmp:
            try:
                folder = combine.combine(samples, prefix, pathlib.Path(tmp))
            except combine.Refused as e:
                raise Refuse(e.code or "refused", e.text) from None
            app = folder.name
            self.keep(app, "1.0.0", self.with_version(folder, "1.0.0"), "acme-dev", "ivn_cmd", f"made from {len(samples)} samples")
        if not samples:  # the blank app: the hosting's lines are the kit's (kitrun.command_lines)
            return {"app": app, "version": "1.0.0", "lines": combine.summary_lines([], "CHECK GREEN", None)}
        return {"app": app, "version": "1.0.0", "lines": [f"Made. {len(samples)} sample{'s' if len(samples) > 1 else ''}, 1 app. CHECK GREEN.",
                                                          "What is in it: Till guard rules (tgr): a check at Pay, a capture on scan. One service, one feed, one app user."]}

    def app(self, b):
        r = self.row(b["app"])
        return {"app": b["app"], "versions": r["versions"], "line": self.line(b["app"])}

    def line(self, app):
        vs = self.row(app)["versions"]
        sent = [v for v in vs if v["sites"]]
        out = []
        if sent:
            n = len(sent[-1]["sites"])
            out.append(f"{sent[-1]['version']} sent to {n} site{'' if n == 1 else 's'}")
        if vs and (not sent or vs[-1]["version"] != sent[-1]["version"]):
            out.append(f"{vs[-1]['version']} a draft, on no site yet")
        return " · ".join(out)

    def apps_list(self, b):
        return {"apps": [{"app": a, "line": self.line(a), "newer": []} for a in self.apps]}

    def download(self, b):
        r = self.row(b["app"])
        v = b.get("version") or r["latest"]
        return {"url": f"{self.base}/object/folders/{b['app']}/{v}.zip", "file": f"{b['app']}-{v}.zip"}

    def draft_url(self, b):
        self.row(b["app"])
        key = f"incoming/{b['app']}/{len(self.pending)}.zip"
        self.pending[key] = None
        return {"key": key, "url": f"{self.base}/object/{key}", "method": "PUT", "headers": {"Content-Type": "application/zip"}}

    def draft_keep(self, b):
        r, app = self.row(b["app"]), b["app"]
        data = self.objects[b["key"]]
        with tempfile.TemporaryDirectory() as tmp:
            folder = ivn.unzip_into(data, pathlib.Path(tmp))
            a = ivn.read_json(folder / "app.json")
            latest = r.get("latest")
            vt = lambda v: [int(x) for x in str(v).split(".")]  # noqa: E731
            other = [v for v in r["versions"] if a.get("base") and vt(v["version"]) > vt(a["base"]) and v["by"] != "acme-dev"]
            note = M09.format(v=other[-1]["version"], what=other[-1]["what"], who=other[-1]["by"]) if other else ""
            last = [int(x) for x in (latest or "0.0.0").split(".")]
            have = [int(x) for x in a.get("version", "0.0.0").split(".")]
            version = a["version"] if have > last else f"{last[0]}.{last[1]}.{last[2] + 1}"
            self.keep(app, version, self.with_version(folder, version), "acme-dev", "ivn", "upload")
        return {"app": app, "version": version, "words": f"Kept as {version}", **({"note": note} if note else {})}

    def add(self, b):
        r, app = self.row(b["app"]), b["app"]
        with tempfile.TemporaryDirectory() as tmp:
            folder = ivn.unzip_into(self.objects[f"folders/{app}/{r['latest']}.zip"], pathlib.Path(tmp))
            try:
                added = combine.add(b["sample"], folder)
            except combine.Refused as e:
                raise Refuse(e.code or "refused", e.text) from None
            self.keep(app, added.version, self.with_version(folder, added.version), "acme-dev", "ivn_cmd", f"{b['sample']} added")
            return {"app": app, "version": added.version,
                    "words": added.lines(json.loads((folder / "manifest.json").read_text("utf-8")))}

    def settings(self, b):
        return {"words": "Saved."}

    def try_start(self, b):
        if not self.sandbox:
            raise Refuse("no_sandbox", "Add a site: any iVendNext site's address. No site yet? Request one: "
                                       "https://developer.ivendnext.com/sandbox.html")
        self.last_site = b.get("site") or getattr(self, "last_site", None) or "acme.sandbox.ivend.co"  # the person's last
        if self.last_site == "shop.acme.example":  # a site its administrator installs: no check of ours, no sections
            return {"site": self.last_site, "press": False, "sections": [], "sha": None,
                    "money": {"line": "Trying it is free.", "charged": False, "plans": None}}
        return {"site": self.last_site, "press": True, "sections": [{"title": "New in Desk", "lines": ["Till guard rules: a new list"]},
                             {"title": "Who can use it", "lines": ["Stock Manager"]},
                             {"title": "Changes to what you already have", "lines": ["Nothing"]},
                             {"title": "Print layouts", "lines": []},
                             {"title": "Connects outside your site", "lines": ["No outside address named."]}],
                "wording": "THE EXACT WORDING", "sha": "f" * 64,
                "money": {"line": "Trying it is free.", "charged": False, "plans": None}}

    def try_install(self, b):
        self.installed = b
        self.polls["try"] = 0
        return {}

    def try_status(self, b):
        if "try" not in self.polls:
            return {"step": None, "lines": []}
        self.polls["try"] += 1
        if self.polls["try"] < 2:
            return {"step": "build", "version": self.row(b["app"])["latest"], "lines": ["Starting the sandbox copy of your app…"]}
        if self.last_site == "shop.acme.example":
            return {"step": "done", "done": True, "press": False, "lines": [], "results": [], "shelf_key": "SHELF-KEY-1",
                    "installed_on": "On shop.acme.example, open App library, paste this key into Open your shelf, then press Install.",
                    "head": ["On shop.acme.example, its own Test connection tests each connection point (App library, the app, "
                             "Test connection)."], "desk": "https://shop.acme.example/app", "till_url": "https://shop.acme.example/pos"}
        return {"step": "done", "done": True, "press": True, "lines": ["Starting the sandbox copy of your app…", "Connecting…"],
                "installed_on": f"Installed on {self.last_site}", "desk": f"https://{self.last_site}/app",
                "till_url": f"https://{self.last_site}/pos", "address": "https://acme-points-sandbox.ivendnext.app",
                "head": ["Tested from our server, as your sandbox would call it.", "Passed: your sandbox reached your app and it answered."],
                "results": self.test_results, "till": ["Try it at the till of acme.sandbox.ivend.co (sign in as cashier1)", "Close the till day when you are done."]}

    def test(self, b):
        if getattr(self, "last_site", None) == "shop.acme.example":
            return {"site": self.last_site, "press": False, "head": ["On shop.acme.example, its own Test connection tests it."], "results": []}
        return {"site": getattr(self, "last_site", None), "press": True, "head": ["Tested from our server, as your sandbox would call it."], "results": self.test_results}

    def secrets(self, b):
        if not self.sandbox:
            raise Refuse("no_sandbox", "Add a site first.")
        return {"site": b.get("site") or "acme.sandbox.ivend.co", "points": [{"key": "tgr_guard", "plain": "a check at Pay", "secret": "the-secret"}]}

    def publish_start(self, b):
        r = self.row(b["app"])
        last = r["versions"][-1]
        live = sorted({s for v in r["versions"] for s in v["sites"]})
        out = {"app": b["app"], "version": r["latest"], "money": self.money, "sites": live, "listed": self.listed,
               "industries": ["fashion", "pharmacy"], "service": getattr(self, "own_server", None)}
        if live and last["sites"]:
            out["nothing_new"] = "Nothing new to publish: on the page's form."
        return out

    def publish(self, b):
        self.sent = b
        r = self.row(b["app"])
        last = r["versions"][-1]
        had = sorted({s for v in r["versions"] for s in v["sites"]})
        last["sites"] = sorted(set(b.get("sites") or []) | set(had)) or last["sites"]
        self.listed = self.listed or b["to"] == "everyone"
        self.polls["pub"] = 0
        return {"step": "order"}

    def publish_status(self, b):
        if "pub" not in self.polls:
            return {"step": None, "lines": []}
        r = self.row(b["app"])
        self.polls["pub"] += 1
        if getattr(self, "pub_stop", None):
            return {"step": "stopped", "stop": self.pub_stop, "lines": []}
        if self.polls["pub"] < 2:
            return {"step": "copy", "version": r["latest"], "lines": [], "checkout_url": "https://checkout.example/c1",
                    "pay": "Pay $49 a month with your card"}
        out = {"step": "done", "done": True, "version": r["latest"], "lines": ["Publishing…"],
               "send": [{"site": SITE, "message": self.message}], "published": "door's form"}
        if self.sent.get("to") == "everyone":
            if getattr(self, "closed", False):
                out.update(public="withdrawn")
            elif self.listed and "card" not in self.sent and not getattr(self, "awaiting", False):  # a first listing carries its card
                out.update(public="listed", public_words="Listed in the App library.")
            else:
                out.update(public="awaiting_approval", public_words="Waiting for our approval. Only the first listing waits.")
        return out

    def picture(self, b):
        self.pic = b
        return {"sha256": "a" * 64, "type": b["type"], "w": b["w"], "h": b["h"]}

    def sites(self, b):
        company = [{"site": "acme.sandbox.ivend.co", "key_address": "sandbox-acme.staging.ivendnext.com", "press": True},
                   {"site": "shop.acme.example", "key_address": "acme.ivendnext.com", "press": False}]
        return {"company": company, "default": getattr(self, "last_site", None) or company[0]["site"],
                "sites": [{"site": SITE, "remove_words": f"{SITE} gets no new versions. The app stays on the site until its administrator uninstalls it."}]}

    def sites_remove(self, b):
        self.removed = b["site"]
        return {"removed": b["site"], "words": f"{b['site']} gets no new versions. The app stays on the site until its administrator uninstalls it."}

    def handover(self, b):
        if b["to"] == "nobody":
            raise Refuse("no_such_company", "No company uses that word. Ask them to sign in to My apps once.", 404)
        self.handed = b["to"]
        return {"words": f"Sent. {b['to']}'s owner sees: Acme wants to hand you ACME MEMBER TILL. Accept / Refuse."}

    def rollback(self, b):
        r = self.row(b["app"])
        reached = [v["version"] for v in r["versions"] if v["sites"]]
        if b.get("to") not in reached[:-1]:
            raise Refuse("M30", "There is no earlier version to go back to.")
        new = "9.9.9"
        if not b.get("go"):
            return {"words": f"This publishes {b['to']}'s content as {new} to every site the app is on now: {SITE}. Going back is for every site at once."}
        self.polls["pub"] = 5
        self.sent = {"to": "customer"}
        self.keep(b["app"], new, self.objects[f"folders/{b['app']}/{b['to']}.zip"], "acme-dev", "ivn_cmd", f"goes back to {b['to']}")
        r["versions"][-1]["sites"] = [SITE]
        return {"messages": [{"site": SITE, "message": f"Please press Update on ACME MEMBER TILL in App library: {new} goes back to {b['to']}."}]}

    def cancel(self, b):
        if b.get("go"):
            self.cancelled = True
            return {"words": "Cancelled at month end. The service stops on 1 Dec 2026."}
        return {"words": f"The service stops on 1 Dec 2026. 1 site still uses it: {SITE}. Their till calls will get each point's answer for when the service is down."}

    def key(self, b):
        return {"words": f"Key for {b['site']}: IVN1-a-key. Send it to the retailer's administrator."}

    def logs(self, b):
        return {"lines": ["14:31 Acme Retail · a check at Pay · answered in 0.31 s · sale POS-0001"], "words": None}

    def tokens_make(self, b):
        return {"token": ONE_APP if b.get("app") else TOKEN, "for": b.get("app") or "*",
                "words": "Shown once: copy it into your build server's secret IVN_TOKEN."}

    ROUTES = {"/v1/device": device, "/v1/device/token": device_token, "/v1/new": new, "/v1/app": app, "/v1/apps": apps_list,
              "/v1/download": download, "/v1/draft/url": draft_url, "/v1/draft/keep": draft_keep, "/v1/add": add,
              "/v1/settings": settings, "/v1/try": try_start,
              "/v1/try/install": try_install, "/v1/try/status": try_status, "/v1/test": test, "/v1/secrets": secrets,
              "/v1/publish/start": publish_start, "/v1/publish": publish, "/v1/publish/status": publish_status,
              "/v1/publish/picture": picture, "/v1/sites": sites, "/v1/sites/remove": sites_remove,
              "/v1/handover": handover, "/v1/rollback": rollback, "/v1/cancel": cancel, "/v1/key": key, "/v1/logs": logs,
              "/v1/tokens/make": tokens_make}
    OPEN = {"/v1/device", "/v1/device/token"}


def serve(stub: Stub) -> http.server.ThreadingHTTPServer:
    class H(http.server.BaseHTTPRequestHandler):
        def _json(self, status, d):
            raw = json.dumps(d).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _door(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            if self.path.startswith("/object/"):
                if self.command == "PUT":
                    stub.objects[self.path[8:]] = raw
                    return self._json(200, {})
                data = stub.objects.get(self.path[8:])
                self.send_response(200 if data is not None else 404)
                self.send_header("Content-Length", str(len(data or b"")))
                self.end_headers()
                return self.wfile.write(data or b"")
            stub.calls.append(self.path)
            auth = self.headers.get("Authorization") or ""
            if self.path not in Stub.OPEN:
                tok = auth[7:]
                if tok == REVOKED:
                    return self._json(401, {"refused": "token_revoked", "words": M28})
                if tok not in (TOKEN, ONE_APP):
                    return self._json(401, {"refused": "not_signed_in", "words": "sign in"})
                stub.last_token = tok
            fn = Stub.ROUTES.get(self.path)
            if not fn:
                return self._json(404, {"refused": "not_found"})
            try:
                self._json(200, fn(stub, json.loads(raw or b"{}")))
            except Refuse as e:
                self._json(e.status, {"refused": e.code, "words": e.words})

        do_GET = do_POST = do_PUT = _door

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.stub = Stub(self.tmp)
        self.srv = serve(self.stub)
        self.addCleanup(self.srv.shutdown)
        self.stub.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.work = self.tmp / "repo"
        self.work.mkdir()
        env = {"IVN_HOSTING_URL": self.stub.base, "IVN_TOKEN": TOKEN, "IVN_SAMPLES_INDEX": self.stub.base + "/object/index.json"}
        for p in (unittest.mock.patch.dict(os.environ, env), unittest.mock.patch.object(ivn, "POLL_SECONDS", 0),
                  unittest.mock.patch.object(ivn, "TOKEN_FILE", self.tmp / "home" / "token")):
            p.start()
            self.addCleanup(p.stop)
        old = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, old)
        self.index({"samples": []})

    def index(self, d):
        self.stub.objects["index.json"] = json.dumps(d).encode()

    def run_ivn(self, *argv, stdin=""):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(stdin)):
            rc = ivn.main(list(argv))
        return rc, out.getvalue()

    def made(self, *samples, name="acme_member_till"):
        flags = [x for s in samples or ("s23",) for x in ("--from", s)]
        rc, out = self.run_ivn("new", name, *flags)
        self.assertEqual(rc, 0, out)
        return self.work / "apps" / name, out

    def in_app(self, folder):
        os.chdir(folder)

    def edit(self, path: pathlib.Path, line="# my own line\n"):
        path.write_text(path.read_text("utf-8") + line, "utf-8")


class LoginAndTokens(Base):
    def test_login_says_the_rows_words_and_keeps_a_token_only_the_person_reads(self):  # UX-22 (J2-11)
        with unittest.mock.patch("webbrowser.open", return_value=True) as opened, unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": ""}):
            rc, out = self.run_ivn("login")
        self.assertEqual(rc, 0, out)
        self.assertIn("Opening your browser to sign in. Code: BCDF-GHJK. Waiting…", out)
        self.assertIn("Signed in as acme-dev for Acme Retail Solutions (acme).", out)
        opened.assert_called_once()
        self.assertEqual(oct((self.tmp / "home" / "token").stat().st_mode & 0o777), "0o600")
        self.assertNotIn(TOKEN, out)

    def test_a_browser_that_does_not_open_gets_the_address_and_the_code(self):  # UX-22 (J2-11)
        with unittest.mock.patch("webbrowser.open", return_value=False):
            _, out = self.run_ivn("login")
        self.assertIn("Open https://developer.ivendnext.com/device and type BCDF-GHJK.", out)

    def test_a_token_made_for_a_build_server_is_shown_once_with_the_rows_words(self):  # UX-143 (J2-15)
        rc, out = self.run_ivn("token", "new", "ci", "--app", "acme_member_till")
        self.assertEqual(rc, 0)
        self.assertIn(ONE_APP, out)
        self.assertIn("Shown once: copy it into your build server's secret IVN_TOKEN.", out)

    def test_a_revoked_token_prints_m28(self):  # J8-26
        with unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": REVOKED}):
            rc, out = self.run_ivn("new", "acme_x", "--from", "s23")
        self.assertEqual((rc, out.strip()), (1, M28))

    def test_no_token_says_how_to_sign_in(self):
        with unittest.mock.patch.dict(os.environ, {"IVN_TOKEN": ""}):
            rc, out = self.run_ivn("new", "acme_x", "--from", "s23")
        self.assertEqual(rc, 1)
        self.assertIn("ivn login", out)


class NewAndDownload(Base):
    def test_new_prints_j2_07_then_the_folder_and_points_at_its_readme(self):  # ⭐ UX-23 (J2-12)
        folder, out = self.made("s23", "s22")
        self.assertRegex(out, r"Made\. 2 samples, 1 app\. CHECK GREEN · (\d+) tests run, \1 passed\.")
        self.assertIn("What is in it: Till guard rules (tgr): a check at Pay, a capture on scan.", out)
        self.assertIn("Folder: apps/acme_member_till/ (service/lyl/, service/tgr/, manifest.json, app.json, tests/). "
                      "Read its README.md: what is in it and what you can change. Next: ivn try", out)
        self.assertTrue((folder / "README.md").is_file())

    def test_next_ivn_try_works_where_new_left_you(self):  # J2-12's Next, from the folder the person is in
        self.made()
        rc, out = self.run_ivn("try")  # from the repository's root: the one app under apps/
        self.assertIn("What installing it changes", out)

    def test_download_says_who_made_it_and_writes_the_repositorys_apps_folder(self):  # ⭐ UX-26 (J3-01, J11-01)
        self.made()
        shutil.rmtree(self.work / "apps")
        self.stub.apps["acme_member_till"]["versions"][0].update(by="Priya", how="page")
        (self.work / ".git").mkdir()
        sub = self.work / "deep"
        sub.mkdir()
        os.chdir(sub)
        rc, out = self.run_ivn("download", "acme_member_till")
        self.assertEqual(rc, 0, out)
        self.assertIn("1.0.0 (draft, made by Priya on the page) into apps/acme_member_till/.", out)
        self.assertTrue((self.work / "apps" / "acme_member_till" / "manifest.json").is_file())
        self.assertIn("Read its README.md", out)

    def test_download_never_writes_over_a_folder(self):
        folder, _ = self.made()
        rc, out = self.run_ivn("download", "acme_member_till")
        self.assertEqual(rc, 1)
        self.assertIn("exists already", out)
        self.assertTrue((folder / "manifest.json").is_file())


class Anywhere(Base):
    def test_every_command_refuses_in_a_folder_with_no_app_json_in_the_rows_words(self):  # ⭐ UX-154 (J3-11)
        for argv in (["check"], ["push"], ["publish"], ["pull"], ["status"], ["try"], ["test"], ["add", "s11"], ["take", "s11"],
                     ["logs"], ["secrets"], ["rollback", "1.0.0"], ["remove-site", SITE], ["cancel"], ["handover", "x"],
                     ["key", SITE], ["package"], ["secret", "X"]):
            with self.subTest(argv=argv):
                rc, out = self.run_ivn(*argv)
                self.assertEqual((rc, out.strip()), (1, "No app.json here. Run this in your app's folder, or pass --app ⟨folder⟩."))

    def test_check_push_and_publish_run_in_a_folder_moved_outside_the_kit(self):  # ⭐ UX-154, J3-11
        folder, _ = self.made()
        moved = self.tmp / "their_repository" / "my_app"
        moved.parent.mkdir()
        shutil.move(str(folder), moved)
        self.in_app(moved)
        self.assertEqual(self.run_ivn("check")[0], 0)
        self.edit(moved / "service" / "app.py")
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 0, out)
        self.assertIn("Uploaded as 1.0.1", out)
        os.chdir(self.tmp)
        rc, out = self.run_ivn("check", "--app", str(moved))  # and from anywhere, by --app
        self.assertEqual(rc, 0, out)


class CheckAndPush(Base):
    def test_check_says_how_many_tests_ran(self):  # ⭐ UX-29 (J3-04)
        folder, _ = self.made()
        self.in_app(folder)
        rc, out = self.run_ivn("check")
        self.assertEqual(rc, 0, out)
        self.assertRegex(out.strip(), r"^CHECK GREEN · (\d+) tests run, \1 passed$")

    def test_check_red_says_what(self):  # UX-29 (J3-04)
        folder, _ = self.made()
        self.in_app(folder)
        (folder / "manifest.json").write_text("{broken", "utf-8")
        rc, out = self.run_ivn("check")
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("CHECK RED: "), out)

    def test_a_failing_test_is_check_red(self):  # UX-29 (J3-04)
        folder, _ = self.made()
        self.in_app(folder)
        (folder / "tests" / "test_mine.py").write_text("import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n", "utf-8")
        rc, out = self.run_ivn("check")
        self.assertEqual(rc, 1)
        self.assertIn("CHECK RED: ", out)
        self.assertIn("test_x", out)

    def test_push_prints_the_row_and_the_version_comes_back_into_both_files(self):  # ⭐ UX-32, UX-34 (J3-07, J3-09)
        folder, _ = self.made()
        self.in_app(folder)
        self.edit(folder / "service" / "app.py")
        rc, out = self.run_ivn("push")
        self.assertEqual(out.strip(), "Checked: CHECK GREEN. Uploaded as 1.0.1 (draft: on our server, on no site yet).")
        a, m = ivn.read_json(folder / "app.json"), ivn.read_json(folder / "manifest.json")
        self.assertEqual((a["version"], a["base"], m["version"]), ("1.0.1", "1.0.1", "1.0.1"))
        self.assertEqual(self.run_ivn("push")[1].strip(), "Nothing changed in this folder since 1.0.1: nothing was uploaded.")

    def test_a_folder_the_check_refuses_is_never_uploaded_m06(self):  # J8-06
        folder, _ = self.made()
        self.in_app(folder)
        (folder / "manifest.json").write_text("{broken", "utf-8")
        before = list(self.stub.calls)
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("Not kept: the kit's check refused this folder. "), out)
        self.assertTrue(out.strip().endswith("Nothing changed on the server. Fix it, run ivn check, and upload again."), out)
        self.assertEqual(self.stub.calls, before)

    def test_env_files_never_leave_this_computer(self):  # the developer's own outside keys
        folder, _ = self.made()
        (folder / ".env.local").write_text("IVN_TEST_SECRET=x\nMY_WALLET_KEY=real-secret\n", "utf-8")
        (folder / ".env").write_text("OTHER=1\n", "utf-8")
        import zipfile
        names = zipfile.ZipFile(io.BytesIO(ivn.zip_folder(folder))).namelist()
        self.assertFalse([n for n in names if ".env" in n or n == ivn.STATE], names)
        self.assertNotIn(b"real-secret", ivn.zip_folder(folder))

    def test_a_folder_made_away_from_my_apps_arrives_at_its_first_push(self):  # J3-11: start.py, then ivn push
        folder = combine.combine(["s23"], "ACME OWN", self.work)
        self.in_app(folder)
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 0, out)
        self.assertIn("Uploaded as 1.0.", out)
        self.assertEqual(self.stub.apps["acme_own"]["versions"][0]["what"], "upload")
        self.assertIn("/v1/new", self.stub.calls)

    def test_a_folder_behind_a_colleagues_version_is_kept_with_m09s_note(self):  # J8-09 as a note (KK 2026-11-04)
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.add({"app": "acme_member_till", "sample": "s11"})  # Priya adds a sample on the page
        self.stub.row("acme_member_till")["versions"][-1]["by"] = "priya"
        self.edit(folder / "service" / "app.py")
        rc, out = self.run_ivn("push")  # Priya's 1.1.0 comes in first, then both go up together
        self.assertEqual(rc, 0, out)
        self.assertIn("Brought in 1.1.0 from the server. Your changes are kept.", out)
        self.assertNotIn("Note:", out)
        self.assertEqual(self.stub.row("acme_member_till")["latest"], "1.1.1")
        self.assertIn("s11", json.dumps(ivn.read_json(folder / "app.json").get("samples")))

    def test_a_folder_behind_your_own_version_is_kept_with_no_note(self):  # KK 2026-11-04 (Healthkart2)
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.add({"app": "acme_member_till", "sample": "s11"})  # the same developer's own 1.1.0
        self.edit(folder / "service" / "app.py")
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Note:", out)


class Pull(Base):
    def test_different_files_keep_both_sides_then_push_works(self):  # ⭐ UX-117 (J11-03)
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.add({"app": "acme_member_till", "sample": "s11"})  # the page adds a sample: 1.1.0
        self.edit(folder / "service" / "app.py")
        mine = (folder / "service" / "app.py").read_text("utf-8")
        rc, out = self.run_ivn("pull")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip(), "Brought in 1.1.0 from the server. Your changes are kept.")
        self.assertEqual((folder / "service" / "app.py").read_text("utf-8").count("# my own line"), 1)
        self.assertIn("# my own line", mine)
        self.assertTrue((folder / "tests" / "apr").is_dir(), sorted(p.name for p in (folder / "tests").iterdir()))  # S11's files arrived
        a = ivn.read_json(folder / "app.json")
        self.assertEqual((a["version"], a["base"]), ("1.1.0", "1.1.0"))
        self.assertIn("s11_approvals", [s["name"] for s in a["samples"]])
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 0, out)
        self.assertIn("Uploaded as 1.1.1", out)

    def test_the_same_lines_are_marked_with_the_rows_words(self):  # ⭐ UX-106 (J8-27)
        folder, _ = self.made()
        self.in_app(folder)
        readme = folder / "README.md"
        first = readme.read_text("utf-8").splitlines()[0]
        with tempfile.TemporaryDirectory() as tmp:  # a colleague changes the first line of the README: 1.0.1
            theirs = ivn.unzip_into(self.stub.objects["folders/acme_member_till/1.0.0.zip"], pathlib.Path(tmp))
            (theirs / "README.md").write_text((theirs / "README.md").read_text("utf-8").replace(first, first + " THEIRS"), "utf-8")
            self.stub.keep("acme_member_till", "1.0.1", self.stub.with_version(theirs, "1.0.1"), "Priya", "page", "an edit")
        readme.write_text(readme.read_text("utf-8").replace(first, first + " MINE"), "utf-8")
        rc, out = self.run_ivn("pull")
        self.assertEqual(rc, 1)
        self.assertEqual(out.strip(), "Brought in 1.0.1 from the server. 1 file changed on both sides: they are marked in "
                                      "README.md, as git marks a conflict. Fix them, run ivn check, then ivn push.")
        text = readme.read_text("utf-8")
        self.assertIn("<<<<<<<", text)
        self.assertIn("MINE", text)
        self.assertIn("THEIRS", text)
        self.assertIn(">>>>>>>", text)
        self.assertEqual(ivn.read_json(folder / "app.json")["base"], "1.0.1")

    def test_marks_left_in_a_file_stop_check_and_every_upload(self):  # ⭐ review: a marked service never reaches a shelf
        folder, _ = self.made()
        self.in_app(folder)
        self.edit(folder / "service" / "app.py", "<<<<<<< your service/app.py\nx = 1\n=======\nx = 2\n>>>>>>> the server's\n")
        rc, out = self.run_ivn("check")
        self.assertEqual((rc, out.strip()), (1, "CHECK RED: service/app.py still marked as a conflict"))
        before = list(self.stub.calls)
        for argv in (["push"], ["publish", "--to", SITE], ["try"]):
            rc, out = self.run_ivn(*argv)
            self.assertEqual((rc, out.strip()), (1, "Not uploaded: service/app.py still marked as a conflict. Fix them, run ivn check, then ivn push."))
        self.assertEqual(self.stub.calls, before)

    def test_a_git_that_fails_is_said_and_the_folder_stays_where_it_was(self):  # review: exit 128 is no conflict
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.add({"app": "acme_member_till", "sample": "s11"})
        self.edit(folder / "README.md")
        real = ivn.subprocess.run

        def fail(cmd, **k):
            if cmd[:2] == ["git", "merge-file"]:
                return ivn.subprocess.CompletedProcess(cmd, 128, b"", b"fatal: not a git thing")
            return real(cmd, **k)
        with unittest.mock.patch.object(ivn.subprocess, "run", fail):
            rc, out = self.run_ivn("pull")
        self.assertEqual(rc, 1)
        self.assertIn("git could not merge README.md", out)
        self.assertEqual(ivn.read_json(folder / "app.json")["base"], "1.0.0")

    def test_a_higher_number_the_developer_set_survives_a_pull(self):  # review
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.add({"app": "acme_member_till", "sample": "s11"})
        a = ivn.read_json(folder / "app.json")
        a["version"] = "2.0.0"
        ivn.write_json(folder / "app.json", a)
        self.assertEqual(self.run_ivn("pull")[0], 0)
        a, m = ivn.read_json(folder / "app.json"), ivn.read_json(folder / "manifest.json")
        self.assertEqual((a["version"], a["base"], m["version"]), ("2.0.0", "1.1.0", "2.0.0"))
        self.assertIn("Uploaded as 2.0.0", self.run_ivn("push")[1])

    def test_without_git_it_refuses_and_says_to_download_again(self):  # §1: no git, no merge
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.add({"app": "acme_member_till", "sample": "s11"})
        with unittest.mock.patch("shutil.which", return_value=None):
            rc, out = self.run_ivn("pull")
        self.assertEqual(rc, 1)
        self.assertIn("download the app again", out)
        self.assertEqual(ivn.read_json(folder / "app.json")["base"], "1.0.0")

    def test_up_to_date_says_so(self):
        folder, _ = self.made()
        self.in_app(folder)
        self.assertEqual(self.run_ivn("pull")[1].strip(), "Already up to date: 1.0.0.")


class AddAndTake(Base):
    def test_add_keeps_a_hand_edit_and_the_server_keeps_the_one_copy(self):  # ⭐ UX-70 (J6-07), Done when
        folder, _ = self.made()
        self.in_app(folder)
        self.edit(folder / "service" / "app.py")
        rc, out = self.run_ivn("add", "s11")
        self.assertEqual(rc, 0, out)
        self.assertIn("Added to a new draft 1.1.0, on no site yet.", out)
        self.assertIn("/v1/add", self.stub.calls)
        self.assertIn("# my own line", (folder / "service" / "app.py").read_text("utf-8"))
        self.assertIn("s11_approvals", [s["name"] for s in ivn.read_json(folder / "app.json")["samples"]])
        self.assertEqual(ivn.read_json(folder / "app.json")["base"], "1.1.0")

    def test_offline_it_changes_the_folder_by_the_same_rules_and_says_so(self):  # ⭐ UX-70 (J6-07)
        folder, _ = self.made()
        self.in_app(folder)
        self.edit(folder / "service" / "app.py")
        self.srv.shutdown()
        self.srv.server_close()
        rc, out = self.run_ivn("add", "s11")
        self.assertEqual(rc, 0, out)
        self.assertIn("Added to a new draft", out)
        self.assertIn("Changed your folder; it reaches the server with your next ivn push.", out)
        self.assertIn("# my own line", (folder / "service" / "app.py").read_text("utf-8"))

    def test_take_prints_the_new_draft_and_a_refusal_is_m04_in_the_doors_words(self):  # ⭐ UX-147 (J6-13)
        folder, _ = self.made("s23", "s22")
        self.in_app(folder)
        rc, out = self.run_ivn("take", "s22")
        self.assertEqual(rc, 0, out)
        self.assertIn("Added to a new draft", out)
        with unittest.mock.patch.object(Stub, "ROUTES", {**Stub.ROUTES, "/v1/add": lambda s, b: (_ for _ in ()).throw(Refuse(
                "M04", "Not added: S22 Customer-owned loyalty must change the entry x, which you changed. Nothing in your app was "
                       "changed. Put that entry back as it was, or add S22's part by hand."))}):
            rc, out = self.run_ivn("take", "s22")
        self.assertEqual(rc, 1)
        self.assertIn("Put that entry back as it was, or add S22's part by hand.", out)


class FoundOnTheRealDoors(Base):
    """What the live walk found (EASY3b): a door's words name a command, and a test of nothing does not read as a test."""

    def test_a_refusal_names_the_command_not_a_button(self):
        self.assertEqual(ivn.terminal("Uninstall an app, then press Try again."), "Uninstall an app, then run ivn try.")
        self.assertEqual(ivn.terminal("Not tested yet: the time for one test ran out. Press Test again."),
                         "Not tested yet: the time for one test ran out. Run ivn test.")

    def test_a_wrong_industry_is_asked_again_never_kept(self):
        folder, _ = self.made()
        answers = iter(["T", "S", "a|b|c", "", "Retail", "grocery", "free", "one", "https://x.example/g"])
        with mock.patch.object(ivn, "ask_or_none", lambda _: next(answers)):
            card = ivn.ask_card(folder, "acme_member_till", ["grocery", "fashion"])
        self.assertEqual(card["industries"], ["grocery"])

    def test_a_build_server_publishes_every_build_from_a_clean_checkout(self):  # ⭐ UX-143 (J2-15), a review's first
        folder, _ = self.made("s23")
        self.in_app(folder)
        self.assertEqual(self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")[0], 0)
        repo = self.tmp / "gitrepo"  # what the repository holds: never a build's own upload
        shutil.copytree(folder, repo, ignore=shutil.ignore_patterns(".ivn-state"))
        self.stub.money = {"lines": ["Publishing is free."], "plan": "starter", "plans": None}
        for build in (1, 2, 3):
            with (repo / "README.md").open("a") as f:
                f.write(f"commit {build}\n")
            ci = self.tmp / f"ci{build}"
            shutil.copytree(repo, ci)
            os.chdir(ci)
            rc, out = self.run_ivn("publish")
            self.assertEqual(rc, 0, out)
            self.assertRegex(out, r"Uploaded as \d+\.\d+\.\d+\. \d+\.\d+\.\d+ published to 1 site\.")
        self.stub.apps["acme_member_till"]["versions"][-1]["how"] = "page"  # a colleague changes it on the page: never lost
        with (repo / "README.md").open("a") as f:
            f.write("commit 4\n")
        ci = self.tmp / "ci4"
        shutil.copytree(repo, ci)
        os.chdir(ci)
        rc, out = self.run_ivn("publish")
        self.assertEqual(rc, 1, out)
        self.assertIn("as git marks a conflict", out)

    def test_push_is_not_green_with_a_failing_test(self):  # ⭐ UX-32 (J3-07), J3-04's green
        folder, _ = self.made()
        self.in_app(folder)
        (folder / "tests" / "test_mine.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n")
        rc, out = self.run_ivn("push")
        self.assertEqual(rc, 1, out)
        self.assertNotIn("CHECK GREEN", out)
        self.assertIn("test_x", out)

    def test_the_sites_own_test_prints_as_the_row(self):  # ⭐ UX-42 (J4-06), with J4-09's head
        rows = ivn.result_rows(["guard (a check at Pay): Passed: reached, signature accepted, answered in 0.1 s."])
        self.assertEqual(rows, ["guard   a check at Pay   Passed  0.1 s"])

    def test_a_feed_with_nothing_to_read_yet_is_not_a_failure(self):  # W227 F-FA-15, as My apps paints it
        rows = ivn.result_rows(["F (an event feed): Inconclusive: Events waiting: 0 · Last read: never No events yet.",
                                "guard (a check at Pay): Passed: reached, signature accepted, answered in 0.1 s."])
        self.assertTrue(ivn.points_ok(rows))
        self.assertFalse(ivn.points_ok(ivn.result_rows(["F (an event feed): Failed: Events waiting: 3 · Last read: never"])))

    def test_status_says_the_sandbox_and_each_customers_install(self):  # ⭐ UX-72 (§14's J2-10), J5-16
        folder, _ = self.made()
        self.in_app(folder)
        version = self.stub.apps["acme_member_till"]["versions"][-1]["version"]
        sites = {"sites": [{"site": SITE, "customer": True, "state": "Waiting for their administrator to install."},
                           {"site": "acme.sandbox.ivend.co", "sandbox": True, "version": version, "state": f"Installed {version}."}]}
        with unittest.mock.patch.dict(Stub.ROUTES, {"/v1/where": lambda s, b: sites}):  # the door `where`, as the live walk found
            rc, out = self.run_ivn("status")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"{version} a draft, tried, not yet published.", out)
        self.assertIn(f"{SITE}: Waiting for their administrator to install.", out)

    def test_test_with_nothing_to_test_says_so(self):
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.test_results = []
        rc, out = self.run_ivn("test")
        self.assertEqual(rc, 0, out)
        self.assertIn("This app has no connection points to test.", out)


class Status(Base):
    INDEX = {"samples": [{"name": "s22_customer_loyalty", "short": "Customer-owned loyalty", "version": "9.9.0",
                          "versions": [{"version": "9.9.0", "lines": ["A better wallet."]}]}]}

    def test_status_says_sent_to_and_the_newer_version_with_its_lines(self):  # ⭐ UX-72 (J6-09), §14
        folder, _ = self.made("s23", "s22")
        self.in_app(folder)
        self.stub.apps["acme_member_till"]["versions"][0]["sites"] = [SITE, "two.ivendnext.com"]
        self.index(self.INDEX)
        rc, out = self.run_ivn("status")
        self.assertEqual(rc, 0, out)
        self.assertIn("acme_member_till 1.0.0 sent to 2 sites.", out)
        self.assertRegex(out, r"A newer version of S22 is available: 9\.9\.0 \(yours \d+\.\d+\.\d+\)\. Changes: A better wallet\.")
        self.assertNotIn(" on 2 sites", out)

    def test_up_to_date_prints_no_notice(self):  # UX-72
        folder, _ = self.made()
        self.in_app(folder)
        self.assertNotIn("newer", self.run_ivn("status")[1])

    def test_an_ide_folder_and_a_venv_are_not_part_of_the_app(self):  # review
        folder, _ = self.made()
        self.in_app(folder)
        for d in (".venv/lib", ".idea", "node_modules/x", ".vscode"):
            (folder / d).mkdir(parents=True)
            (folder / d / "f.txt").write_text("x", "utf-8")
        self.assertFalse(ivn.changed(folder))

    def test_offline_it_says_it_cannot_check(self):  # ⭐ UX-104 (J8-25)
        folder, _ = self.made()
        self.in_app(folder)
        self.srv.shutdown()
        self.srv.server_close()
        rc, out = self.run_ivn("status")
        self.assertEqual(rc, 0)
        self.assertIn("Could not check for newer sample versions: no connection.", out)

    def test_the_index_alone_down_says_it_cannot_check(self):  # UX-104
        folder, _ = self.made()
        self.in_app(folder)
        del self.stub.objects["index.json"]
        self.assertIn("Could not check for newer sample versions: no connection.", self.run_ivn("status")[1])

    def test_a_stopped_build_is_shown_with_its_last_lines(self):  # J3-08, M07 in ivn status
        folder, _ = self.made()
        self.in_app(folder)
        self.stub.polls["pub"] = 0
        self.stub.sent = {"to": "customer"}
        self.stub.pub_stop = "1.0.0 did not build. The last 50 lines of the build are below."
        self.assertIn("did not build", self.run_ivn("status")[1])


class Sandbox(Base):
    def test_there_is_no_sandbox_command_to_paste_a_key_into(self):  # a sandbox we hand over takes no pasted key
        rc, out = self.run_ivn("sandbox", "https://acme.sandbox.ivend.co")
        self.assertEqual(rc, 2, out)

    def test_secret_sets_a_setting_and_logs_print_newest_first(self):  # UX-132
        folder, _ = self.made()
        self.in_app(folder)
        self.assertIn("Saved.", self.run_ivn("secret", "HKD_WALLET_SECRET", stdin="value\n")[1])
        self.assertIn("14:31 Acme Retail · a check at Pay · answered in 0.31 s · sale POS-0001", self.run_ivn("logs")[1])

    def test_secrets_prints_each_point_with_j10_03s_words(self):  # ⭐ UX-115 (J10-03)
        folder, _ = self.made()
        self.in_app(folder)
        rc, out = self.run_ivn("secrets")
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[0], "Each connection point's secret on acme.sandbox.ivend.co. On any other site, "
                                              "Copy secret on the point gives it.")
        self.assertIn("tgr_guard  a check at Pay: the-secret", out)
        self.assertIn("on shop.acme.example.", self.run_ivn("secrets", "--site", "shop.acme.example")[1])


class Try(Base):
    def setUp(self):
        super().setUp()
        self.folder, _ = self.made()
        self.in_app(self.folder)

    def test_try_shows_the_five_sections_asks_nothing_and_ends_with_each_point(self):  # ⭐ UX-41 (J4-06)
        with unittest.mock.patch("builtins.input", side_effect=AssertionError("asked")) as asked, \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = ivn.main(["try"])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        asked.assert_not_called()  # no yes, no plan, no card: trying is free
        for title in ("What installing it changes", "New in Desk", "Who can use it", "Changes to what you already have",
                      "Print layouts", "Connects outside your site"):
            self.assertIn(title, out)
        self.assertIn("Trying it is free.", out)
        self.assertEqual(self.stub.installed, {"app": self.stub.installed["app"], "sha": "f" * 64, "site": "acme.sandbox.ivend.co"})
        self.assertEqual(out.splitlines()[0], "Trying it on acme.sandbox.ivend.co.")  # the site, named before anything else
        for line in ("Installed on acme.sandbox.ivend.co", "https://acme.sandbox.ivend.co/app", "https://acme.sandbox.ivend.co/pos",
                     "https://acme-points-sandbox.ivendnext.app"):
            self.assertIn(line, out)
        self.assertIn("Tested from our server, as your sandbox would call it.", out)
        self.assertRegex(out, r"tgr_guard\s+a check at Pay\s+Passed  0\.31 s")
        self.assertRegex(out, r"lyl_member\s+a till key\s+Passed  0\.42 s")
        self.assertIn("Try it at the till of acme.sandbox.ivend.co", out)

    def test_sites_then_a_site_then_no_flag_names_the_same_site_first(self):  # SITEPICK: the walk's terminal step
        rc, out = self.run_ivn("sites")
        self.assertEqual((rc, out.splitlines()), (0, ["acme.sandbox.ivend.co  one press · ivn try uses it",
                                                      "shop.acme.example  its administrator installs it from the shelf key ivn try prints"]))
        rc, out = self.run_ivn("try", "--site", "shop.acme.example")
        self.assertEqual((rc, out.splitlines()[0]), (0, "Trying it on shop.acme.example."))
        self.assertEqual(self.stub.installed["site"], "shop.acme.example")
        self.assertIn("On shop.acme.example, open App library, paste this key into Open your shelf, then press Install.\nSHELF-KEY-1", out)
        self.assertNotIn("What installing it changes", out)  # its administrator's own install shows them
        self.assertNotIn("This app has no connection points to test.", out)  # the site's own Test connection tests it
        self.assertEqual(self.run_ivn("try")[1].splitlines()[0], "Trying it on shop.acme.example.")  # the person's last
        self.assertEqual(self.run_ivn("test")[1].splitlines()[0], "On shop.acme.example.")  # the finished try's own site

    def test_show_wording_prints_it(self):  # J4-06
        self.assertIn("THE EXACT WORDING", self.run_ivn("try", "--show-wording")[1])

    def test_no_sandbox_is_m31(self):  # ⭐ UX-138 (J8-29)
        self.stub.sandbox = None
        rc, out = self.run_ivn("try")
        self.assertEqual((rc, out.strip()), (1, "Add a site: any iVendNext site's address, with ivn sites add <address>. "
                                                "No site yet? Request one: https://developer.ivendnext.com/sandbox.html"))

    def test_a_changed_folder_uploads_first_and_says_so(self):  # ⭐ UX-32 (J3-07)
        self.edit(self.folder / "service" / "app.py")
        _, out = self.run_ivn("try")
        self.assertIn("Checked: CHECK GREEN. Uploaded as 1.0.1 (draft: on our server, on no site yet).", out)
        self.assertIn("/v1/draft/keep", self.stub.calls)

    def test_try_with_a_point_failed_exits_one(self):  # review
        self.stub.test_results = ["tgr_guard (a check at Pay): Failed: nothing answered at this address (404)."]
        self.assertEqual(self.run_ivn("try")[0], 1)

    def test_test_prints_a_result_per_point_and_the_refused_signature_words(self):  # ⭐ UX-42 (J4-06), Done when
        m18 = ("tgr_guard (a check at Pay): Failed: the app did not recognise the site's secret (401). In the site's Desk, search "
               "Extension Subscription, open Till guard rules (x) and press Connect again. Then press Test again.")
        rc, out = self.run_ivn("test")
        self.assertEqual(rc, 0, out)
        self.assertIn("Tested from our server, as your sandbox would call it.", out)
        self.stub.test_results = [m18, self.stub.test_results[1]]
        rc, out = self.run_ivn("test")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"tgr_guard\s+a check at Pay\s+Failed: the app did not recognise the site's secret \(401\)\.")
        self.assertRegex(out, r"lyl_member\s+a till key\s+Passed  0\.42 s")


class TestLocal(Base):
    def test_test_local_answers_on_the_laptop_with_the_test_secret(self):  # ⭐ UX-144 (J3-10)
        folder = combine.combine(["s23"], "ACME LOC", self.work)
        self.in_app(folder)
        rc, out = self.run_ivn("test", "--local")
        self.assertEqual(rc, 0, out)
        self.assertIn("Tested on http://localhost:8000 with the test secret in .env.local.", out)
        self.assertRegex(out, r"guard\s+a check at Pay\s+Passed  \d+\.\d+ s")

    def test_port_8000_taken_is_said_plainly(self):  # review: not blamed on the app
        folder = combine.combine(["s23"], "ACME LOC", self.work)
        self.in_app(folder)
        (folder / "service" / "app.py").write_text("raise SystemExit(1)\n", "utf-8")
        rc, out = self.run_ivn("test", "--local")
        self.assertEqual(rc, 1)
        self.assertIn("Port 8000 is taken", out)

    def test_a_wrong_secret_says_so(self):  # J3-10
        folder = combine.combine(["s23"], "ACME LOC", self.work)
        self.in_app(folder)
        with unittest.mock.patch.object(ivn, "_local_secret", lambda f: "not-the-secret"):
            rc, out = self.run_ivn("test", "--local")
        self.assertEqual(rc, 1)
        self.assertIn("Failed: the app did not recognise the test secret in .env.local (401).", out)


class Publish(Base):
    def setUp(self):
        super().setUp()
        self.folder, _ = self.made()
        self.in_app(self.folder)

    def test_a_first_publish_asks_the_plan_and_who_pays_and_prints_the_message(self):  # ⭐ UX-145 (J5-17), Done when
        rc, out = self.run_ivn("publish", "--to", SITE, stdin="2\n1\n")
        self.assertEqual(rc, 0, out)
        for line in ("Starter $49: a till key or a check, low volume", "Standard $129: a connected app",
                     "Managed $399: we also test it before each iVendNext upgrade", "Publishing is free.",
                     "Pay by 1 your company's card · 2 invoice to your accounts e-mail",
                     "Pay $49 a month with your card: https://checkout.example/c1",
                     f"1.0.0 published to {SITE}. Published means waiting on the customer's shelf: it is installed when their "
                     "administrator installs it.", "Send this to the customer's administrator:"):
            self.assertIn(line, out)
        self.assertEqual(self.stub.sent["plan"], "standard")
        self.assertNotIn("invoice", self.stub.sent)

    def test_the_key_stands_on_its_own_line_unindented_so_it_copies_clean(self):  # §14 (K177), EASYLOOK's note
        _, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertIn("\n\nIVNS1-the-key\n\n", out)
        self.assertIn("\n2. Paste this key:\n", out)

    def test_an_invoice_is_asked_for_with_its_address(self):  # J5-17
        self.run_ivn("publish", "--to", SITE, stdin="1\n2\naccounts@acme.example\n")
        self.assertEqual(self.stub.sent["invoice"], "accounts@acme.example")

    def test_the_door_suggested_plan_comes_first(self):  # §14 (K176), EASYLOOK's note
        self.stub.money = {**self.stub.money, "suggested": "standard", "asks_pay": False}
        rc, out = self.run_ivn("publish", "--to", SITE, stdin="\n")
        self.assertEqual(rc, 0, out)
        self.assertLess(out.index("1  Standard $129"), out.index("2  Starter $49"))
        self.assertEqual(self.stub.sent["plan"], "standard")

    def test_publish_writes_the_version_and_the_address_into_both_files(self):  # ⭐ UX-34 (J3-09)
        self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        a, m = ivn.read_json(self.folder / "app.json"), ivn.read_json(self.folder / "manifest.json")
        hosted = "https://acme-member-till.ivendnext.app"
        self.assertEqual((a["version"], a["base"], a["address"], m["version"]), ("1.0.0", "1.0.0", hosted, "1.0.0"))
        urls = [x["endpoint_url"] for x in m["extension_subscriptions"]]
        self.assertTrue(urls and all(u.startswith(hosted + "/") for u in urls), urls)
        self.assertEqual(validate_app.check_settings(a), [])
        self.assertFalse(ivn.changed(self.folder))  # no needless upload next time
        self.assertEqual(combine.kit_check(self.folder)[0], 0)

    def test_a_moved_address_is_not_an_edit_add_a_sample_still_works_after_a_publish(self):  # J3-09 with J6-05
        self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        added = combine.add("s11", self.folder)
        self.assertEqual(added.kept_entries, [])

    def test_after_a_publish_ivn_add_and_a_page_add_bring_no_false_conflict(self):  # ⭐ review: nobody edited these files
        self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        rc, out = self.run_ivn("add", "s11")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("as git marks a conflict", out)
        rc, out = self.run_ivn("check")
        self.assertEqual(rc, 0, out)
        a = ivn.read_json(self.folder / "app.json")
        self.assertEqual((a["base"], a["address"]), ("1.1.0", "https://acme-member-till.ivendnext.app"))
        urls = [x["endpoint_url"] for x in ivn.read_json(self.folder / "manifest.json")["extension_subscriptions"]]
        self.assertTrue(any(u.startswith("https://acme-member-till.ivendnext.app/") for u in urls), urls)  # S23's stay moved
        self.stub.add({"app": "acme_member_till", "sample": "s2"})  # now on the page
        rc, out = self.run_ivn("pull")
        self.assertEqual(rc, 0, out)
        self.assertIn("Your changes are kept.", out)

    def test_canary_a_manifest_whose_version_differs_is_never_published(self):  # ⭐ Done when, UX-34
        m = ivn.read_json(self.folder / "manifest.json")
        m["version"] = "7.7.7"
        ivn.write_json(self.folder / "manifest.json", m)
        with unittest.mock.patch.object(ivn, "push_first", lambda f, a: None):  # nothing has set them alike
            rc, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertEqual(rc, 1)
        self.assertIn("Not published: manifest.json says 7.7.7 and app.json says 1.0.0.", out)
        self.assertNotIn("/v1/publish", self.stub.calls)

    def test_a_version_set_in_app_json_alone_reaches_the_manifest_at_the_upload(self):  # J3-09: never written twice
        a = ivn.read_json(self.folder / "app.json")
        a["version"] = "2.0.0"
        ivn.write_json(self.folder / "app.json", a)
        rc, out = self.run_ivn("push")
        self.assertIn("Uploaded as 2.0.0", out)
        self.assertEqual(ivn.read_json(self.folder / "manifest.json")["version"], "2.0.0")

    def test_a_changed_folder_uploads_first_a_build_servers_line(self):  # ⭐ UX-143 (J2-15), Done when
        self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.stub.money = {"lines": ["Publishing is free."], "plan": "starter", "plans": None}
        self.edit(self.folder / "service" / "app.py")
        rc, out = self.run_ivn("publish")
        self.assertEqual(rc, 0, out)
        self.assertIn("Uploaded as 1.0.1. 1.0.1 published to 1 site.", out)

    def test_a_later_publish_says_j6_03(self):  # ⭐ UX-65 (J6-03)
        self.run_ivn("publish", "--to", SITE, "--to", "two.ivendnext.com", stdin="1\n1\n")
        self.stub.money = {"lines": ["Publishing is free."], "plan": "starter", "plans": None}
        self.stub.keep("acme_member_till", "1.0.1", self.stub.objects["folders/acme_member_till/1.0.0.zip"], "x", "page", "edit")
        rc, out = self.run_ivn("publish")
        self.assertIn("1.0.1 published to 2 sites.", out)

    def test_nothing_new_is_the_librarys_own_m33(self):  # J8-31, EASYLOOK's note
        self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        rc, out = self.run_ivn("publish")
        self.assertEqual((rc, out.strip()), (1, "Nothing new to publish: 1.0.0 is on every site. Upload a new version, or add a sample, first."))

    def test_public_asks_for_the_card_keeps_it_in_app_json_and_prints_j7_02(self):  # ⭐ UX-146 (J7-06), Done when
        png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (600).to_bytes(4, "big") + (400).to_bytes(4, "big") + b"\0" * 20
        (self.folder / "shot.png").write_bytes(png)
        answers = "1\n1\nACME Till\nOne line about it\nFirst|Second|Third\nshot.png\nfashion|pharmacy\nfree\nStep one|Step two\nhttps://acme.example/guide\n"
        rc, out = self.run_ivn("publish", "--public", stdin=answers)
        self.assertEqual(rc, 0, out)
        self.assertIn("Waiting for our approval. Only the first listing waits.", out)
        card = ivn.read_json(self.folder / "app.json")["card"]
        self.assertEqual((card["title"], card["what"], card["industries"], card["price"], card["pictures"]),
                         ("ACME Till", ["First", "Second", "Third"], ["fashion", "pharmacy"], "free", ["shot.png"]))
        self.assertEqual(self.stub.sent["to"], "everyone")
        self.assertEqual(self.stub.sent["card"]["pictures"][0], {"sha256": "a" * 64, "type": "image/png", "w": 600, "h": 400})
        self.assertEqual(validate_app.check_settings(ivn.read_json(self.folder / "app.json")), [])

    def test_a_later_version_of_a_listed_app_goes_to_the_list_too(self):  # ⭐ UX-146 (J7-05, J7-06)
        self.stub.listed = True
        self.stub.money = {"lines": ["Publishing is free."], "plan": "starter", "plans": None}
        rc, out = self.run_ivn("publish")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.stub.sent["to"], "everyone")
        self.assertRegex(out, r"1\.0\.0 published to the App library and \d+ sites?\.")

    def test_a_closed_listing_request_never_claims_the_list(self):  # K181: a request closed earlier answers no words
        self.stub.listed, self.stub.closed = True, True
        self.stub.money = {"lines": ["Publishing is free."], "plan": "starter", "plans": None}
        rc, out = self.run_ivn("publish")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("published to the App library", out)

    def test_a_later_version_while_the_first_listing_waits_says_it_waits(self):  # UX-146: EASY3b's live walk
        self.stub.listed, self.stub.awaiting = True, True
        self.stub.money = {"lines": ["Publishing is free."], "plan": "starter", "plans": None}
        rc, out = self.run_ivn("publish")
        self.assertEqual(rc, 0, out)
        self.assertIn("Waiting for our approval. Only the first listing waits.", out)
        self.assertNotIn("published to the App library", out)

    def test_a_message_with_no_key_yet_is_said_to_the_developer_not_under_send_this(self):  # J5-04's library words
        self.stub.message = "Its key is not ready yet: publish again in a minute."
        rc, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"{SITE}: Its key is not ready yet", out)
        self.assertNotIn("Send this to the customer's administrator:", out)

    def test_published_names_the_customers_sites_never_the_sandbox(self):  # J5-17: the sandbox is on no customer's shelf
        real = Stub.publish

        def with_sandbox(stub, b):
            out = real(stub, b)
            stub.row(b["app"])["versions"][-1]["sites"].append("acme.sandbox.ivend.co")
            return out
        with unittest.mock.patch.dict(Stub.ROUTES, {"/v1/publish": with_sandbox}):
            _, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertIn(f"1.0.0 published to {SITE}. Published means", out)

    def test_publish_from_a_folder_behind_the_server_never_marks_it_up_to_date(self):  # ⭐ review: a colleague's work is not dropped
        self.stub.add({"app": "acme_member_till", "sample": "s11"})  # the page adds a sample: 1.1.0, and publish sends that
        rc, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertEqual(rc, 0, out)
        self.assertIn("1.1.0 published to", out)
        self.assertIn("Your folder is behind: the server is now at 1.1.0. Run ivn pull", out)
        self.assertEqual(ivn.read_json(self.folder / "app.json")["base"], "1.0.0")  # the next push says so (M09), not lost
        self.stub.row("acme_member_till")["versions"][-1]["by"] = "priya"
        self.edit(self.folder / "service" / "app.py")
        self.assertIn("Brought in 1.1.0 from the server.", self.run_ivn("push")[1])

    def test_a_build_server_never_chooses_a_charge_by_its_silence(self):  # review: closed stdin
        self.stub.money = {**self.stub.money, "suggested": "starter"}
        rc, out = self.run_ivn("publish", "--to", SITE)
        self.assertEqual(rc, 1)
        self.assertIn("Choose a plan with --plan", out)
        self.assertNotIn("/v1/publish", self.stub.calls)

    def test_a_card_with_nobody_to_answer_stops_and_says_what_is_missing(self):  # J7-06, review
        rc, out = self.run_ivn("publish", "--public", "--plan", "starter", stdin="1\n")
        self.assertEqual(rc, 1)
        self.assertIn("put these in app.json's card: title, summary", out)

    def test_a_blank_card_answer_is_asked_again_and_a_wrong_price_too(self):  # review
        answers = "1\n\nACME Till\nOne line\nFirst\n\nfashion\nFree of charge\nFREE\nStep\nhttps://acme.example/guide\n"
        rc, out = self.run_ivn("publish", "--public", "--plan", "starter", stdin=answers)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count("This one is needed."), 2)
        self.assertEqual(ivn.read_json(self.folder / "app.json")["card"]["price"], "free")

    def test_an_invoice_order_ends_the_wait_and_says_what_comes_next(self):  # review: up to 14 days on terms
        real = Stub.publish_status

        def waiting(stub, b):
            return {"step": "copy", "version": "1.0.0", "invoice_waiting": True,
                    "lines": ["Your invoice is on its way to accounts@acme.example. Run ivn status once it is paid."]}
        with unittest.mock.patch.dict(Stub.ROUTES, {"/v1/publish/status": waiting}):
            rc, out = self.run_ivn("publish", "--to", SITE, stdin="1\n2\naccounts@acme.example\n")
            self.assertEqual(rc, 0, out)
            self.assertIn("Your invoice is on its way", out)
            self.assertNotIn("published to", out)
            status = self.run_ivn("status")[1]
        self.assertIn("Your invoice is on its way", status)
        self.assertNotIn("Building", status)
        del real

    def test_a_dropped_connection_after_the_door_took_it_never_says_nothing_changed(self):  # review
        def down(stub, b):
            raise ConnectionError
        calls = []
        real = ivn.door

        def door(path, *a, **k):
            calls.append(path)
            if path == "/v1/publish/status":
                raise ivn.Offline("gone")
            return real(path, *a, **k)
        with unittest.mock.patch.object(ivn, "door", door):
            rc, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertEqual(rc, 1)
        self.assertIn("still going on our side", out)
        self.assertNotIn("Nothing was changed", out)
        del down

    def test_a_stopped_publish_prints_the_doors_words(self):  # M16, M07, M23 reach the person as given
        self.stub.pub_stop = "The payment did not go through: declined. Nothing was started. Try another card."
        rc, out = self.run_ivn("publish", "--to", SITE, stdin="1\n1\n")
        self.assertEqual(rc, 1)
        self.assertIn("The payment did not go through: declined.", out)


class KeepGoing(Base):
    def setUp(self):
        super().setUp()
        self.folder, _ = self.made()
        self.in_app(self.folder)
        self.stub.apps["acme_member_till"]["versions"][0]["sites"] = [SITE]
        self.stub.keep("acme_member_till", "1.0.1", self.stub.objects["folders/acme_member_till/1.0.0.zip"], "x", "page", "edit")
        self.stub.apps["acme_member_till"]["versions"][1]["sites"] = [SITE]

    def test_rollback_prints_the_lines_and_republishes_higher_with_no_typed_name(self):  # UX-121 (J12-03); GUARDSWEEP
        rc, out = self.run_ivn("rollback", "1.0.0")
        self.assertEqual(rc, 0, out)
        self.assertIn("This publishes 1.0.0's content as 9.9.9 to every site the app is on now", out)
        self.assertNotIn("Type the app's name", out)
        self.assertIn("Please press Update on ACME MEMBER TILL in App library: 9.9.9 goes back to 1.0.0.", out)
        self.assertEqual(self.stub.apps["acme_member_till"]["latest"], "9.9.9")

    def test_m30_is_the_doors(self):  # UX-121
        self.assertIn("There is no earlier version to go back to.", self.run_ivn("rollback", "1.0.1")[1])

    def test_remove_site_asks_the_name(self):  # ⭐ UX-148 (J13-05), Done when
        rc, out = self.run_ivn("remove-site", SITE, stdin="nope\n")
        self.assertEqual(rc, 1)
        self.assertFalse(hasattr(self.stub, "removed"))
        rc, out = self.run_ivn("remove-site", SITE, stdin="acme_member_till\n")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"{SITE} gets no new versions. The app stays on the site until its administrator uninstalls it.", out)
        self.assertEqual(self.stub.removed, SITE)

    def test_handover_prints_j5_14_asks_the_name_and_says_who_was_told(self):  # ⭐ UX-149 (J5-18), Done when
        rc, out = self.run_ivn("handover", "retailer", stdin="nope\n")
        self.assertEqual(rc, 1)
        self.assertFalse(hasattr(self.stub, "handed"))
        rc, out = self.run_ivn("handover", "retailer", stdin="acme_member_till\n")
        self.assertEqual(rc, 0, out)
        self.assertIn("They accept on their My apps. The app keeps its name; its versions, sites, secrets and hosting move to them, and their card pays from the next month.", out)
        self.assertIn("Sent. retailer's owner sees: Acme wants to hand you ACME MEMBER TILL. Accept / Refuse.", out)
        self.assertIn("No company uses that word.", self.run_ivn("handover", "nobody", stdin="acme_member_till\n")[1])

    def test_cancel_prints_j13_03_and_asks_the_name(self):  # ⭐ UX-125 (J13-04), Done when
        rc, out = self.run_ivn("cancel", stdin="acme_member_till\n")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"The service stops on 1 Dec 2026. 1 site still uses it: {SITE}.", out)
        self.assertIn("Cancelled at month end. The service stops on 1 Dec 2026.", out)

    def test_key_prints_j7_07(self):  # ⭐ UX-155 (J7-07)
        rc, out = self.run_ivn("key", SITE)
        self.assertEqual(out.strip(), f"Key for {SITE}: IVN1-a-key. Send it to the retailer's administrator.")

    def test_package_writes_a_function_package_and_a_container_is_told_why_not(self):  # J10-02
        rc, out = self.run_ivn("package")
        self.assertEqual(rc, 0, out)
        self.assertTrue((self.folder / "package.zip").is_file())
        self.assertFalse(ivn.changed(self.folder) and "package.zip" in [r for r, _ in ivn.files_of(self.folder)])
        a = ivn.read_json(self.folder / "app.json")
        a["runs"] = "container"
        ivn.write_json(self.folder / "app.json", a)
        self.assertIn("build it with docker", self.run_ivn("package")[1])


class TheOneFile(unittest.TestCase):
    """Every sample's `app.json` in the one shape; the samples record and `base` survive it (Done when)."""

    def test_every_samples_app_json_validates_and_no_sample_has_a_library_folder(self):  # ⭐ Done when
        for f in sorted((KIT / "samples").glob("*/app.json")):
            with self.subTest(sample=f.parent.name):
                self.assertEqual(validate_app.check_settings(json.loads(f.read_text("utf-8"))), [])
        self.assertEqual(list((KIT / "samples").glob("*/library")), [])
        self.assertFalse((KIT / "tools" / "publish").exists())

    def test_the_card_and_the_address_are_part_of_the_shape_and_are_checked(self):
        a = json.loads((KIT / "samples" / "s23_till_guard" / "app.json").read_text("utf-8"))
        good = {**a, "address": "https://acme.ivendnext.app", "card": {"title": "T", "what": ["x"], "price": "free"}}
        self.assertEqual(validate_app.check_settings(good), [])
        self.assertTrue(validate_app.check_settings({**a, "card": {"nope": 1}}))
        self.assertTrue(validate_app.check_settings({**a, "card": {"price": "paid"}}))
        self.assertTrue(validate_app.check_settings({**a, "address": "http://plain.example"}))

    def test_the_samples_record_and_base_survive_every_sample_that_makes_an_app(self):  # ⭐ Done when
        made = 0
        for sample in sorted(p.name for p in (KIT / "samples").iterdir() if p.is_dir()):
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as tmp:
                try:
                    folder = combine.combine([sample], "ACME ONE", pathlib.Path(tmp))
                except combine.Refused as e:
                    self.assertEqual(e.code, "M35", e.text)  # no manifest of its own (J8-33); every other sample makes an app
                    continue
                a = json.loads((folder / "app.json").read_text("utf-8"))
                self.assertEqual(a["samples"][0]["name"], sample)
                self.assertTrue(a["samples"][0]["files"] or a["samples"][0]["entries"])
                a["base"], a["card"], a["address"] = "1.0.0", {"title": "T"}, "https://acme-one.ivendnext.app"
                (folder / "app.json").write_text(json.dumps(a), "utf-8")
                self.assertEqual(validate_app.check_settings(a), [])
                self.assertEqual(combine.kit_check(folder)[0], 0)
                self.assertEqual(json.loads((folder / "app.json").read_text("utf-8"))["samples"], a["samples"])
                made += 1
        self.assertGreater(made, 30)

    def test_nothing_in_the_tools_or_samples_names_a_key_file_any_more(self):  # ⭐ Done when (EASY5's grep covers the pages)
        words = ("recipient" + ".pem", "library-signing" + ".key", "LIBRARY_" + "DELIVERIES")
        found = []
        for root in (KIT / "tools", KIT / "samples"):
            for p in root.rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".md", ".json", ".yml", ".txt", ".js", ".sh", ".toml"):
                    text = p.read_text("utf-8", errors="replace")
                    found += [f"{p.relative_to(KIT)}: {w}" for w in words if w in text]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
