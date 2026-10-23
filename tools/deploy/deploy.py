#!/usr/bin/env python3
"""deploy — put your manifest on your own site, through the shop's install screen's methods.

The shop holds the checker and the installer; this tool only calls them, as the install screen does. It checks the
manifest here first, sends it to the site, prints the site's own summary and stops. Only when you add --consent
does it install: it checks again and echoes the fingerprint of the summary the site returns in that run (never one you type). It then waits
for the install job and prints the result, any secrets and the to-do list. Python 3 standard library only.

    BASE=https://<your-site> KEY=<api key> SECRET=<api secret> python3 tools/deploy/deploy.py manifest.json
    ... python3 tools/deploy/deploy.py manifest.json --consent       # install, or update to a higher version
    ... python3 tools/deploy/deploy.py uninstall "<app> <version>"   # export, then uninstall; prints the export file
    ... python3 tools/deploy/deploy.py finish "<app> <version>"      # complete or take back a failed or killed job

The key is a user's who may install packages on that site (System Manager by default). Exit code: 0 done (or
checked, without --consent) · 1 refused or failed · 2 usage · 3 the job had not finished within --wait seconds.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "manifest"))
import site_rules as SR  # noqa: E402  what the shop's install refuses that its checker passes
import validate as V  # noqa: E402  the kit's copy of the shop's checker

API = "ivendnext_mpos.api.extension_package."
PKG = "Retail Extension Package"
RUNNING = ("Queued", "Installing", "Upgrading", "Uninstalling")
DONE_OK = ("Installed", "Uninstalled")
# where each secret the installer makes lives (the install record's item kind -> record type, field)
SECRET_AT = {"webhook": ("Webhook", "webhook_secret"), "remote_key": ("Retail Remote App Key", "secret"),
             "extension_subscription": ("Retail Extension Subscription", "secret")}


class Site:
    def __init__(self, base, key, secret):
        self.base, self.auth = base.rstrip("/"), f"token {key}:{secret}"

    def _req(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET",
                                     headers={"Authorization": self.auth, "Accept": "application/json",
                                              **({"Content-Type": "application/json"} if data is not None else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raise SystemExit(f"the site answered HTTP {e.code} to {path.split('?')[0]}: {_why(e.read())}")
        except urllib.error.URLError as e:
            raise SystemExit(f"the site did not answer: {e.reason}")

    def call(self, method, **args):
        return (self._req("/api/method/" + API + method, args) or {}).get("message")

    def get(self, doctype, name):
        q = urllib.parse.quote
        return (self._req(f"/api/resource/{q(doctype)}/{q(name, safe='')}") or {}).get("data") or {}

    def password(self, doctype, name, field):
        qs = urllib.parse.urlencode({"doctype": doctype, "name": name, "fieldname": field})
        return (self._req("/api/method/ivendnext_mpos.api.v1.get_password?" + qs) or {}).get("message")


def _why(raw):
    try:
        b = json.loads(raw or b"{}")
        msgs = [json.loads(m).get("message", m) for m in json.loads(b.get("_server_messages") or "[]")]
        return "; ".join(msgs) or b.get("exception") or b.get("exc_type") or "no reason given"
    except (ValueError, AttributeError, TypeError):
        return raw[:300].decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)


def _refusals(rs, out):
    for r in rs:
        out(f"REFUSED {r.get('where')}{' (' + str(r['name']) + ')' if r.get('name') else ''}: {r.get('reason')}")


def wait(site, name, out, seconds, step=2.0, since=None):
    """Poll the package record until its status leaves the running ones — and, given `since` (the record's `modified` before
    the call), until the job has written it: Finish queues its job without changing the status. None on time-out."""
    end = time.monotonic() + seconds
    while True:
        doc = site.get(PKG, name)
        if doc.get("status") not in RUNNING and (since is None or doc.get("modified") != since):
            return doc
        if time.monotonic() >= end:
            out(f"still {doc.get('status')} after {seconds:g} s: read the package record later, or run finish")
            return None
        time.sleep(step)


def report(site, doc, out, secrets=False):
    out(f"status: {doc.get('status')}")
    for k in ("error", "refusals", "todo"):
        if doc.get(k):
            out(f"{k}:\n  " + doc[k].replace("\n", "\n  "))
    if secrets and doc.get("status") == "Installed":
        try:  # reading a secret back needs System Manager; a key that may only install still installed
            rec = site.get("Retail Extension Install", doc.get("app"))
            for it in json.loads(rec.get("items") or "[]"):
                if it.get("kind") in SECRET_AT:
                    dt, field = SECRET_AT[it["kind"]]
                    out(f"secret · {dt} {it.get('key') or it['name']}: {site.password(dt, it['name'], field)}")
        except SystemExit as e:
            out(f"secrets not read ({e}): the user who installed sees each once in Desk; each stays on its own record")
    if doc.get("export_file"):
        out(f"export file: {doc['export_file']}")
    return 0 if doc.get("status") in DONE_OK else 1


def deploy(site, manifest, consent, out=print, seconds=900):
    local = V.validate(manifest) or SR.refusals(manifest)
    if local:
        _refusals(local, out)
        out(f"{len(local)} refusal(s) here: nothing was sent")
        return 1
    res = site.call("check", manifest=json.dumps(manifest)) or {}
    if not res.get("ok"):
        _refusals(res.get("refusals") or [], out)
        out("the site refused it: nothing was installed")
        return 1
    out(f"package: {res['name']} ({res.get('mode')})")
    out("summary — what you consent to:\n  " + str(res.get("summary") or "").replace("\n", "\n  "))
    if res.get("changes"):
        out("changes on this site:\n  " + str(res["changes"]).replace("\n", "\n  "))
    for w in res.get("warnings") or []:
        out(f"WARNING {w.get('where')}: {w.get('text')}")
    out(f"fingerprint: {res.get('summary_sha256')}")
    if not consent:
        out("not installed: run again with --consent; it checks again and installs with the summary it prints then")
        return 0
    got = site.call("install", name=res["name"], summary_sha256=res.get("summary_sha256")) or {}
    if not got.get("ok"):
        _refusals(got.get("refusals") or [], out)
        return 1
    out(f"{got.get('action')} queued; waiting for the job")
    doc = wait(site, res["name"], out, seconds)
    return 3 if doc is None else report(site, doc, out, secrets=True)


def act(site, action, name, out=print, seconds=900):
    before = site.get(PKG, name).get("modified")
    got = site.call(action, name=name) or {}
    if not got.get("ok"):
        _refusals(got.get("refusals") or [], out)
        return 1
    out(f"{action} queued; waiting for the job")
    doc = wait(site, name, out, seconds, since=before)
    return 3 if doc is None else report(site, doc, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", help="manifest.json, or 'uninstall' / 'finish'")
    ap.add_argument("name", nargs="?", help="the package name '<app> <version>' (uninstall, finish)")
    ap.add_argument("--consent", action="store_true", help="install with the summary the site just showed")
    ap.add_argument("--wait", type=float, default=900, help="seconds to wait for the job (default 900)")
    a = ap.parse_args(argv)
    base, key, secret = (os.environ.get(k, "") for k in ("BASE", "KEY", "SECRET"))
    if not (base and key and secret):
        ap.error("set BASE, KEY and SECRET (a user who may install packages on that site)")
    site = Site(base, key, secret)
    if a.target in ("uninstall", "finish"):
        if not a.name or a.consent:
            ap.error(f"{a.target} takes the package name, and no --consent")
        return act(site, a.target, a.name, seconds=a.wait)
    try:
        manifest = json.loads(pathlib.Path(a.target).read_text("utf-8"))
    except json.JSONDecodeError as e:   # the place in plain words, not the parser's own message
        ap.error(f"cannot read the manifest: the file is not valid JSON: something is missing or extra at line {e.lineno}, "
                 f"column {e.colno}")
    except (OSError, ValueError) as e:
        ap.error(f"cannot read the manifest: {e}")
    return deploy(site, manifest, a.consent, seconds=a.wait)


if __name__ == "__main__":
    sys.exit(main())
