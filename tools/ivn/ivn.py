#!/usr/bin/env python3
"""ivn — make, try, publish and keep your app going from a terminal, over the same server as My apps in your browser.

    ivn doctor                                what this computer has, whether it is signed in, and what to run next
    ivn login                                 sign this computer in, by a code in your browser
    ivn new acme_store_rules                  a blank app: add what you need from its README's list
    ivn new acme_member_till --from s23 --from s22
    ivn download acme_member_till             write the server's copy into apps/acme_member_till/
    ivn check                                 the kit's check and the app's own tests
    ivn push                                  check the folder and upload it as the next draft
    ivn pull                                  bring the server's latest draft in and keep your changes
    ivn add s11 · ivn take s22                add a sample · take a sample's newer version
    ivn secret NAME · ivn secrets [--site S]  set one of the app's settings · print each point's secret on a site
    ivn sites [add|use|label|remove]          your company's sites (My sites): list, add, make default, label, remove
    ivn try [--site SITE] [--show-wording]    install the latest draft on a site, free, and test each connection point
    ivn test [--local]                        test each connection point again (--local: on this laptop)
    ivn publish [--to SITE ...] [--public]    send it to a customer's sites, or list it for every retailer
    ivn status · ivn logs                     where it stands · what its service logged
    ivn rollback 1.0.1 · ivn remove-site SITE · ivn cancel · ivn handover WORD
    ivn key SITE · ivn token new NAME [--app APP] · ivn package
    ivn update                                bring the kit and ivn up to date

It acts on the app in the current folder (any folder holding an `app.json`), or `--app <folder>`. The page and the
command change one copy of the app on our server. Words are the ones My apps uses. Exit code: 0 done · 1 refused ·
2 usage. Standard library only; Python 3.9 or newer. A build server sets `IVN_TOKEN` to a token from My apps > Tokens; a person's token is kept
in `~/.ivendnext/token`, readable by them alone. A secret is never printed unless it is what you asked for, and `.env`
files never leave this computer.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import http.client
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
KIT = HERE.parents[1]
sys.path.insert(0, str(KIT / "tools" / "manifest"))
sys.path.insert(0, str(KIT / "tools" / "deploy_app"))

HOSTING = "https://hosting.ivendnext.app"
SAMPLES_INDEX = "https://developer.ivendnext.com/samples/index.json"
DOMAIN = "ivendnext.app"
TOKEN_FILE = pathlib.Path.home() / ".ivendnext" / "token"
WHO_FILE = pathlib.Path.home() / ".ivendnext" / "who.json"  # who signed this computer in (no secret): ivn doctor says it
MIN_PYTHON = (3, 9)  # the oldest Python the kit's own tests pass under (a Mac's own python3 is 3.9.6)
MIN_GIT = (2, 0)  # ivn pull's git merge-file -L
KIT_ARCHIVE = "https://github.com/ivendnext-developers/partner-kit/archive/refs/heads/main.zip"
KIT_COMMIT_FILE = ".kit-commit"  # the commit of a kit fetched as GitHub's archive (the installer and ivn update write it)
KIT_FILES_FILE = ".kit-files"  # the files that archive held: an update removes only those the new one no longer has
ON_WINDOWS = os.name == "nt"  # ivn.cmd runs py, the Windows launcher: doctor says whether it is there
TOKEN_RE = re.compile(r"ivn_tok_[A-Za-z0-9_-]{43}")
STATE = ".ivn-state"  # what this folder held when it last matched the server's copy (never uploaded)
POLL_SECONDS = 5
POLL_MAX = 3600  # how long the command follows one try or publish (a build, a checkout)
LOCAL_URL = "http://localhost:8000"
ADDRESSES = (("extension_subscriptions", "endpoint_url"), ("remote_keys", "endpoint_url"), ("webhooks", "url"))

# the spec's words the command itself owns (§0b: a line the command prints is always this tool's item)
WORDS = {
    "no_app_json": "No app.json here. Run this in your app's folder, or pass --app ⟨folder⟩.",  # J3-11
    "login_start": "Opening your browser to sign in. Code: {code}. Waiting…",  # J2-11
    "login_open": "Open https://developer.ivendnext.com/device and type {code}.",  # J2-11
    "login_done": "Signed in as {login} for {name} ({company}).",  # J2-11
    "folder": "Folder: apps/{app}/ ({parts}). Read its README.md: what is in it and what you can change.",  # J2-12
    "next_try": "Next: ivn try",  # J2-12
    "get_sandbox_first": "Get a sandbox of your own, in one press: My sites on My apps. Until then, try on a site by name: "
                         "ivn try --site.",
    "capture_none": "Nothing is left to write: --only and --skip left out everything the site had.",
    "captured": "Captured {n} from {site} into {folder}/manifest.json:",
    "capture_red": "Nothing written, the folder is as it was: {verdict}",
    "capture_nothing": "Nothing written to {folder}.",
    "capture_next": "Next: ivn try --site <another site> installs it there, and it behaves the same.",
    "blank_folder": "Folder: apps/{app}/ (manifest.json, app.json, tests/). Read its README.md: what you can add, each kind "
                    "with an example. Then: ivn check, ivn try",  # J1 DEVSTART: the blank start's last line
    "downloaded": "{version} ({state}made by {who} {how}) into apps/{app}/.",  # J11-01
    "check_green": "CHECK GREEN · {n} tests run, {n} passed",  # J3-04
    "check_red": "CHECK RED: {what}",  # J3-04
    "m06": "Not kept: the kit's check refused this folder. {verdict}. Nothing changed on the server. Fix it, run ivn check, "
           "and upload again.",  # J8-06
    "pushed": "Checked: CHECK GREEN. Uploaded as {version} (draft: on our server, on no site yet).",  # J3-07
    "uploaded": "Uploaded as {version}. ",  # J2-15
    "changes_head": "What installing it changes",  # J4-02, J4-06
    "m31": "Add a site: any iVendNext site's address, with ivn sites add <address>. No site yet? Request one: "
           "https://developer.ivendnext.com/sandbox.html",  # J8-29, SITEPICK
    "tested_local": "Tested on http://localhost:8000 with the test secret in .env.local.",  # J3-10
    "type_plan": "Type 1, 2 or 3:",  # J5-17
    "pay_by": "Pay by 1 your company's card · 2 invoice to {email}",  # J5-17
    "published": "{version} published to {sites}. Published means waiting on the customer's shelf: it is installed when their "
                 "administrator installs it.",  # J5-17
    "send_head": "Send this to the customer's administrator:",  # J5-17
    "published_n": "{version} published to {n} site{s}.",  # J6-03, J2-15
    "published_listed": "{version} published to the App library and {n} site{s}.",  # J7-06
    "m33_token": "Nothing new to publish: {version} is on every site. Upload a new version, or add a sample, first.",  # J8-31
    "newer": "A newer version of {number} is available: {version} (yours {yours}).",  # J6-09
    "changes": " Changes: {lines}",  # J6-09
    "m27": "Could not check for newer sample versions: no connection.",  # J8-25
    "offline_add": "Changed your folder; it reaches the server with your next ivn push.",  # J6-07
    "m29": "Brought in {version} from the server. {n} file{s} changed on both sides: they are marked in {files}, as git marks "
           "a conflict. Fix them, run ivn check, then ivn push.",  # J8-27
    "secrets_head": "Each connection point's secret on {site}. On any other site, Copy secret on the point gives it.",  # J10-03
    "handover": "They accept on their My apps. The app keeps its name; its versions, sites, secrets and hosting move to them, "
                "and their card pays from the next month.",  # J5-14, J5-18
    "type_name": "Type the app's name to confirm.",  # J5-18, J13-04, J13-05
    # this tool's own words (no row writes them), in plain words
    "trying_on": "Trying it on {site}.",  # SITEPICK: the site, named before anything else
    "on_site": "On {site}.",
    "site_row": "{site}  {how}",
    "one_press": "one press",
    "its_admin": "its administrator installs it from the shelf key ivn try prints",
    "your_last": " · ivn try uses it",  # the person's last site, else the first: true for a first-timer too
    # MYSITES (J2): the company's own list of sites
    "how_ours": "one press, with our key",
    "how_own": "one press, with your key",
    "how_live": "a customer's live site: ivn publish sends it the production copy",
    "site_key": "API key (Enter for none: its administrator then installs from the shelf key):",
    "site_secret": "API secret:",
    "key_where": "Make the key on that site under your own user: your User record, its Settings tab, API Access, Generate Keys (not on Administrator).",
    "sites_usage": "ivn sites [add <address> | use <address or label> | label <address> \"<label>\" | remove <address>]",
    "removed_mine": "{site} is off your list, with the key you added for it. (ivn remove-site stops an app reaching a site.)",
    "still_listed": "{site} is still on your list: it is one of our sandboxes, given to you or your company.",
    "installing_on": "Installing {version} on {site}…",
    "no_key_install": "{site}: we hold no key there, so its administrator installs it from the message above.",
    "install_hint": "{name}: your company holds its key, so nothing goes to its administrator. Press Install now on "
                    "My apps (the app's Publish screen) to install it in one press; next time, ivn publish --to \"{to}\" "
                    "--install publishes and installs in one go.",
    "sign_in": "Sign in first: ivn login (a build server: a token from My apps > Tokens, in IVN_TOKEN).",
    "bad_token": "This token is not one My apps made. Run ivn login again, or make a new token on My apps > Tokens.",
    "no_reach": "Could not reach iVendNext: no connection. Nothing was changed. Try again.",
    "no_login": "The code was not entered in time. Run ivn login again.",
    "not_same": "Not done: that is not the app's name. Nothing was changed.",
    "exists": "apps/{app} exists already. Move it away, or run ivn pull inside it.",
    "unchanged": "Nothing changed in this folder since {version}: nothing was uploaded.",
    "up_to_date": "Already up to date: {version}.",
    "pulled": "Brought in {version} from the server. Your changes are kept.",
    "no_git": "ivn pull merges with git, and git is not on this computer. Install git, or download the app again into another "
              "folder and bring your changes across.",
    "never_on_server": "This folder is not on our server yet: run ivn push first.",
    "version_differs": "Not published: manifest.json says {manifest} and app.json says {app}. Run ivn push, which sets them "
                       "alike, then publish again.",
    "gave_up": "This is still going on our side. Run ivn status to see where it stands.",
    "stopped": "Stopped.",
    "behind": "Your folder is behind: the server is now at {version}. Run ivn pull to bring it in and keep your changes.",
    "marked": "Not uploaded: {files} still marked as a conflict. Fix them, run ivn check, then ivn push.",
    "port_taken": "Port 8000 is taken by something else on this computer, so the service could not start. Stop it, then run this "
                  "again.",
    "no_plan": "Choose a plan with --plan starter, --plan standard or --plan managed.",
    "card_asks": "The card for the App library. What you type is kept in app.json, so you are asked once.",
    "card_stop": "Fill the card first: run ivn publish --public in a terminal, or put these in app.json's card: {fields}.",
    "ask_again": "This one is needed.",
    "bad_picture": "Not a picture this command can read: {path}. Use a PNG or JPEG: fix it in app.json, under card, pictures.",
    "not_function": "This app runs all the time, so it has no package: build it with docker (README: Run it on your own "
                    "server).",
    "package_done": "Wrote package.zip for your own function host.",
    "local_secret": "No test secret: .env.local has no IVN_TEST_SECRET.",
    "local_401": "Failed: the app did not recognise the test secret in .env.local (401).",
    "local_404": "Failed: nothing answered at this address (404). This version of the app does not have this point yet.",
    "local_other": "Failed: the app answered {status}.",
    "local_down": "Failed: the service did not answer on http://localhost:8000. Read what it printed above.",
    "no_points": "This app has no connection points to test.",
    # J1 DEVSTART: ivn doctor and ivn update
    "old_python": "ivn needs Python {need} or newer, and this is Python {have} ({path}). Install a newer one from "
                  "https://www.python.org/downloads/ and run ivn again.",
    "dr_python": "Python {have} ({path}): {ok}",
    "dr_py": "py, the Windows launcher the kit's own ivn.cmd runs: {ok}",
    "dr_git": "git {have}: {ok}",
    "dr_no_git": "git: not found. ivn pull and updating a clone need it: install it from https://git-scm.com/downloads",
    "dr_kit": "The kit: {where} ({how})",
    "dr_signed": "Signed in as {login} for {name} ({company}).",
    "dr_signed_token": "Signed in by IVN_TOKEN, a build server's token.",
    "dr_signed_unknown": "Signed in on this computer.",
    "dr_signed_out": "Not signed in yet.",
    "dr_bad_token": "Signed out: this computer's sign-in was revoked or has expired. Run ivn login.",
    "dr_sites": "Sites you can try on: {sites}",
    "dr_no_sites": "Sites you can try on: none yet. Add one you administer with ivn sites add <address>, or request a "
                   "sandbox: https://developer.ivendnext.com/sandbox.html",
    "dr_no_reach": "Sites you can try on: could not reach iVendNext (no connection).",
    "dr_next": "Next: {cmd}",
    "new_enough": "new enough",
    "too_old": "too old: {need} or newer is needed",
    "found": "found",
    "missing": "not found. The installer's ivn runs with the Python above; for the kit's ivn.cmd, install Python from "
               "https://www.python.org/downloads/ with its py launcher ticked",
    "up_clone": "Updating the kit in {where} with git pull.",
    "up_archive": "Updating the kit in {where} from GitHub's main.",
    "up_moved": "The kit moved from {old} to {new}.",
    "up_same": "The kit is up to date: {new}.",
    "up_dirty": "Not updated: git pull stopped ({why}). If it names a file you changed in the kit, keep that change aside; "
                "otherwise check your connection. Then run ivn update again.",
    "up_no_git": "Not updated: the kit is a git clone and git is not on this computer. Install git, then run ivn update again.",
}


class Stop(Exception):
    """A refusal, in words: printed, exit 1."""


class Offline(Exception):
    """Nothing answered."""


class Refused(Stop):
    """A door's refusal: its code and its own words."""

    def __init__(self, code, words, status=400):
        super().__init__(words or code)
        self.code, self.status = code, status


# ── the token and the doors ──────────────────────────────────────────────────


def token_now() -> str | None:
    """A build server's token (`IVN_TOKEN`), else this computer's (`ivn login`), else none."""
    t = os.environ.get("IVN_TOKEN", "").strip()
    if not t and TOKEN_FILE.is_file():
        t = TOKEN_FILE.read_text("utf-8").strip()
    if t and not TOKEN_RE.fullmatch(t):
        raise Stop(WORDS["bad_token"])
    return t or None


def keep_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")


def keep_who(who: dict) -> None:
    try:
        WHO_FILE.parent.mkdir(parents=True, exist_ok=True)
        WHO_FILE.write_text(json.dumps(who) + "\n", "utf-8")
    except OSError:  # only doctor reads it
        pass


def _send(method: str, url: str, data: bytes | None, headers: dict, timeout: float = 90) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "iVendNext-kit-ivn/1", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.read()
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        raise Offline(str(e)) from None


def door(path: str, body: dict | None = None, token: str | None = None, method: str = "POST", need_token: bool = True) -> dict:
    """One door, as the page calls it, with the token in place of the page's session."""
    token = token or (token_now() if need_token else None)
    if need_token and not token:
        raise Stop(WORDS["sign_in"])
    base = os.environ.get("IVN_HOSTING_URL", HOSTING).rstrip("/")
    headers = {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})}
    data = None if method == "GET" else json.dumps(body or {}).encode()
    status, raw = _send(method, base + path, data, headers)
    try:
        out = json.loads(raw or b"{}")
    except ValueError:
        raise Stop(f"iVendNext answered {status}, not in JSON. Nothing is known to have changed: try again.") from None
    if status != 200:
        raise Refused(out.get("refused") or f"http_{status}", out.get("words") or f"iVendNext answered {status}.", status)
    return out


def online(fn, *a, **k):
    """A door that needs the network: no answer is said in plain words."""
    try:
        return fn(*a, **k)
    except Offline:
        raise Stop(WORDS["no_reach"]) from None


# ── the app's folder ─────────────────────────────────────────────────────────


def read_json(path: pathlib.Path) -> dict:
    try:
        v = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", "utf-8")


def app_folder(a) -> pathlib.Path:
    """The app this command acts on: `--app`, else the current folder, else the one app under `apps/` here (the folder
    `ivn new` and `ivn download` just wrote, J2-12's *Next: ivn try*)."""
    given = getattr(a, "app", None)
    if given:
        f = pathlib.Path(given)
        if (f / "app.json").is_file():
            return f.resolve()
        raise Stop(WORDS["no_app_json"])
    cwd = pathlib.Path.cwd()
    if (cwd / "app.json").is_file():
        return cwd
    apps = [p for p in (cwd / "apps").glob("*") if (p / "app.json").is_file()] if (cwd / "apps").is_dir() else []
    if len(apps) == 1:
        return apps[0]
    raise Stop(WORDS["no_app_json"])


def app_id(folder: pathlib.Path) -> str:
    """The app's name: the manifest's (`acme_member_till`), or the settings file's with its hyphens read back."""
    m = read_json(folder / "manifest.json")
    return m.get("app") or str(read_json(folder / "app.json").get("app") or folder.name).replace("-", "_")


def hosted_address(app: str) -> str:
    return f"https://{app.replace('_', '-')}.{DOMAIN}"  # one name, written two ways


LEFT_OUT = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea", ".vscode", ".pytest_cache"}


def _left_out(rel: str) -> bool:
    """What never leaves this computer and is never part of the app's copy on the server."""
    parts = rel.split("/")
    return (rel == STATE or rel == "package.zip" or parts[0] == ".local" or bool(LEFT_OUT & set(parts))
            or rel.endswith(".pyc") or parts[-1] == ".DS_Store" or parts[-1] == ".env" or parts[-1].startswith(".env."))


def files_of(folder: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    return sorted((p.relative_to(folder).as_posix(), p) for p in folder.rglob("*")
                  if p.is_file() and not p.is_symlink() and not _left_out(p.relative_to(folder).as_posix()))


def _canonical(rel: str, data: bytes) -> bytes:
    """The two files tools write, read as what they say, so a re-indent is not a change."""
    if rel in ("app.json", "manifest.json"):
        try:
            return json.dumps(json.loads(data), sort_keys=True, ensure_ascii=False).encode()
        except ValueError:
            pass
    return data


def tree_hash(folder: pathlib.Path) -> str:
    h = hashlib.sha256()
    for rel, p in files_of(folder):
        h.update(rel.encode() + b"\0" + hashlib.sha256(_canonical(rel, p.read_bytes())).digest())
    return h.hexdigest()


def remember(folder: pathlib.Path, source: pathlib.Path | None = None) -> None:
    """This folder (or `source`, the server's copy it was merged with) as what the server holds."""
    (folder / STATE).write_text(json.dumps({"tree": tree_hash(source or folder)}) + "\n", "utf-8")


def changed(folder: pathlib.Path) -> bool:
    return read_json(folder / STATE).get("tree") != tree_hash(folder)


def zip_folder(folder: pathlib.Path) -> bytes:
    """The folder as the server keeps it: the same bytes for the same files, with `.env` files and caches left out."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, p in files_of(folder):
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr, info.compress_type, info.create_system = 0o644 << 16, zipfile.ZIP_DEFLATED, 3
            z.writestr(info, p.read_bytes())
    return buf.getvalue()


def unzip_into(data: bytes, into: pathlib.Path) -> pathlib.Path:
    """A zip the server gave into a folder; never outside it, never through a link."""
    root = into.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for i in z.infolist():
            target = (root / i.filename).resolve()
            if i.is_dir() or (i.external_attr >> 16) & 0o170000 == 0o120000 or root not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(i))
    return root


def fetch_version(app: str, version: str | None) -> bytes:
    """One version's folder, as *Download the app folder* gives it."""
    got = door("/v1/download", {"app": app, **({"version": version} if version else {})})
    status, raw = _send("GET", got["url"], None, {})
    if status != 200:
        raise Stop(f"The folder could not be fetched (it answered {status}). Nothing was changed: try again.")
    return raw


def set_version(folder: pathlib.Path, version: str) -> None:
    """The version the server gave, in both files (J3-09: never written twice). A file with conflict marks is edited where
    the line stands."""
    for name, keys in (("app.json", ("version", "base")), ("manifest.json", ("version",))):
        p = folder / name
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text("utf-8"))
        except ValueError:
            text = p.read_text("utf-8")
            for k in keys:
                text, n = re.subn(rf'^(\s*"{k}":\s*)"[^"]*"', rf'\g<1>"{version}"', text, count=1, flags=re.M)
                if not n and k == "base":
                    text = re.sub(r'^(\s*"version":\s*"[^"]*",?)$', rf'\1\n "base": "{version}",', text, count=1, flags=re.M)
            p.write_text(text, "utf-8")
            continue
        for k in keys:
            d[k] = version
        write_json(p, d)


def sync_version(folder: pathlib.Path) -> None:
    """A developer may set a higher number in app.json: the manifest follows it, before anything is sent."""
    a, mp = read_json(folder / "app.json"), folder / "manifest.json"
    m = read_json(mp)
    if m and a.get("version") and m.get("version") != a["version"]:
        m["version"] = a["version"]
        write_json(mp, m)


def same_version(folder: pathlib.Path) -> None:
    """Nothing is published from a folder whose two files name different versions (UX-34)."""
    a, m = read_json(folder / "app.json"), read_json(folder / "manifest.json")
    if m and a.get("version") != m.get("version"):
        raise Stop(WORDS["version_differs"].format(manifest=m.get("version"), app=a.get("version")))


def own_paths(folder: pathlib.Path) -> set:
    """The routes the app's own service answers: its parts' points, else every point's address in the manifest. COPY of the
    server's rule (ivendnext/partner-hosting-infra, selfserve/functions/myapps_try.py `own_paths`): a defect here is a defect
    there; report it on the Partner Programme board."""
    d = read_json(folder / "service" / "dispatch.json")
    paths = {p for mount in (d.get("mounts") or {}).values() if isinstance(mount, dict) for p in (mount.get("points") or {})}
    if paths:
        return paths
    m = read_json(folder / "manifest.json")
    return {urllib.parse.urlsplit(x.get(f) or "").path for g, f in ADDRESSES for x in m.get(g) or []
            if isinstance(x, dict) and x.get(f)}


def apply_address(folder: pathlib.Path, address: str) -> None:
    """The service's address in `app.json` and the manifest. Entries the developer did not change stay unchanged in the
    samples record: a moved address is not an edit (*Add a sample*)."""
    import combine  # noqa: PLC0415
    ap, mp, dp = folder / "app.json", folder / "manifest.json", folder / "service" / "dispatch.json"
    a, m, d = read_json(ap), read_json(mp), read_json(dp)
    before = json.loads(json.dumps(combine.entries_of(m, a, d))) if d.get("mounts") else {}
    base, paths = urllib.parse.urlsplit(address), own_paths(folder)

    def move(u):
        if not isinstance(u, str):
            return u
        p = urllib.parse.urlsplit(u)
        return urllib.parse.urlunsplit((base.scheme, base.netloc, p.path, p.query, "")) if p.path in paths else u
    for group, field in ADDRESSES:
        for x in m.get(group) or []:
            if isinstance(x, dict) and field in x:
                x[field] = move(x[field])
    moved = {}
    if isinstance(m.get("allowed_urls"), list):  # an allowed address is its own entry's id, so the record follows it
        moved = {f"manifest:allowed_urls:{u}": f"manifest:allowed_urls:{move(u)}" for u in m["allowed_urls"] if isinstance(u, str)}
        m["allowed_urls"] = sorted({move(u) for u in m["allowed_urls"]})
    a["address"] = address
    if before:
        after = combine.entries_of(m, a, d)
        for rec in a.get("samples") or []:
            entries = {}
            for i, h in (rec.get("entries") or {}).items():
                now = moved.get(i, i)
                untouched = i in before and now in after and h == combine.sha(before[i])
                entries[now] = combine.sha(after[now]) if untouched else h
            rec["entries"] = entries
    write_json(mp, m)
    write_json(ap, a)


def write_published(folder: pathlib.Path, version: str, address: str) -> None:
    """J3-09: the version and the service's address, in both files, so nothing is written twice."""
    apply_address(folder, address)
    set_version(folder, version)
    remember(folder)


def ask_or_none(prompt: str) -> str | None:
    """A person's answer; None when nobody is there to answer (a build server)."""
    try:
        return input(prompt + " ").strip()
    except EOFError:
        return None


def ask(prompt: str) -> str:
    return ask_or_none(prompt) or ""


def ask_secret(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt + " ").strip()
    return ask(prompt)


def confirm(app: str) -> None:
    """J5-18, J13-04, J13-05: the app's name, typed, before a change that cannot be undone (a hand-over, a cancel, a site removed)."""
    print(WORDS["type_name"])
    if ask(">") not in (app, app.replace("_", "-"), app.replace("_", " ").upper()):
        raise Stop(WORDS["not_same"])


# ── login, tokens ────────────────────────────────────────────────────────────


def cmd_login(a) -> int:
    d = online(door, "/v1/device", {}, need_token=False)
    code = d["user_code"]
    print(WORDS["login_start"].format(code=code), flush=True)
    try:
        opened = webbrowser.open(d["verification_uri_complete"])
    except webbrowser.Error:
        opened = False
    if not opened:
        print(WORDS["login_open"].format(code=code), flush=True)
    every = max(0, int(d.get("interval", 5))) if POLL_SECONDS else 0
    for _ in range(max(1, int(d.get("expires_in", 600)) // max(1, every or 1))):
        time.sleep(every)
        try:
            r = online(door, "/v1/device/token", {"device_code": d["device_code"]}, need_token=False)
        except Refused as e:
            if e.code == "device_pending":
                continue
            raise
        keep_token(r["token"])
        keep_who({k: r.get(k) for k in ("login", "name", "company")})
        print(WORDS["login_done"].format(login=r.get("login"), name=r.get("name") or r.get("company"), company=r.get("company")))
        return 0
    raise Stop(WORDS["no_login"])


def cmd_token(a) -> int:
    out = online(door, "/v1/tokens/make", {"name": a.name, **({"app": a.for_app} if a.for_app else {})})
    print(out["token"])
    print(out["words"])
    return 0


# ── a new app, and bringing it down ──────────────────────────────────────────


def repo_root() -> pathlib.Path:
    """the current repository (the nearest folder up holding `.git`), else the current folder."""
    cwd = pathlib.Path.cwd()
    return next((p for p in [cwd, *cwd.parents] if (p / ".git").exists()), cwd)


def local_env_if_missing(folder: pathlib.Path) -> None:
    """A folder whose last version came by an upload has no `.env.local` on the server (`.env` files stay on the laptop)."""
    if not (folder / ".env.local").is_file():
        import combine  # noqa: PLC0415
        (folder / ".env.local").write_text(combine.env_local(app_id(folder), read_json(folder / "app.json")), "utf-8")


def bring_down(app: str, version: str | None) -> pathlib.Path:
    target = repo_root() / "apps" / app
    if target.exists() and any(target.iterdir()):
        raise Stop(WORDS["exists"].format(app=app))
    data = online(fetch_version, app, version)
    target.mkdir(parents=True, exist_ok=True)
    unzip_into(data, target)
    remember(target)
    local_env_if_missing(target)
    return target


def folder_line(folder: pathlib.Path, app: str) -> str:
    """J2-12's list of what is in the folder."""
    tags = sorted(p.name for p in (folder / "service").glob("*") if p.is_dir() and not p.name.startswith(("_", ".")))
    parts = [f"service/{t}/" for t in tags] or ["service/"] if (folder / "service").is_dir() else []
    parts += [n for n in ("manifest.json", "app.json") if (folder / n).is_file()]
    if (folder / "tests").is_dir():
        parts.append("tests/")
    return WORDS["folder"].format(app=app, parts=", ".join(parts))


MARK = b"<<<<<<< your "  # the label `ivn pull` gives git's conflict marks, so nothing else reads as one


def still_marked(folder: pathlib.Path) -> list[str]:
    return [rel for rel, p in files_of(folder) if MARK in p.read_bytes()]


def check_folder(folder: pathlib.Path) -> tuple[bool, str]:
    """J3-04: the kit's check over the folder and the app's own tests, one verdict line."""
    import combine  # noqa: PLC0415
    marked = still_marked(folder)
    if marked:
        return False, WORDS["check_red"].format(what=f"{', '.join(marked)} still marked as a conflict")
    rc, verdict = combine.kit_check(folder)
    if rc:
        return False, WORDS["check_red"].format(what=verdict)
    if not (folder / "tests").is_dir():
        return True, WORDS["check_green"].format(n=0)
    ok, n, log = combine.run_tests(folder)
    if not ok:
        lines = [x for x in log.strip().splitlines() if x.startswith(("FAIL:", "ERROR:"))]
        failed = sum(1 for _ in lines)
        return False, WORDS["check_red"].format(what=f"{failed or 'some'} of {n} tests failed"
                                                     + (f": {lines[0]}" if lines else ""))
    return True, WORDS["check_green"].format(n=n)


def cmd_new(a) -> int:
    samples = list(a.from_samples or [])  # none: the blank app (J1 DEVSTART), through the same door
    prefix = a.name.replace("_", " ").replace("-", " ").strip().upper()
    out = online(door, "/v1/new", {"samples": samples, "name": prefix})
    app = out["app"]
    lines = out.get("lines") or out.get("words") or []
    target = bring_down(app, out.get("version"))
    ok, verdict = check_folder(target)
    head = lines[0] if lines else ""
    if ok and "CHECK GREEN" in head:
        head = re.sub(r"CHECK GREEN\.?$", verdict + ".", head)
    elif not ok:
        head = re.sub(r"CHECK GREEN\.?$", "", head).rstrip() + " " + verdict
    print(head)
    for line in lines[1:]:
        print(line)
    print(folder_line(target, app) + " " + WORDS["next_try"] if samples else WORDS["blank_folder"].format(app=app))
    return 0


def unpack(read: dict) -> dict:
    """The site's set-up as the hosting sends it: packed (`packed`: gzip, then base64, of the JSON), so a chain's print
    formats and layouts pass the load balancer's 1 MB, or plain."""
    if "packed" not in read:
        return read
    import gzip  # noqa: PLC0415
    return {**{k: v for k, v in read.items() if k != "packed"},
            **json.loads(gzip.decompress(base64.b64decode(read["packed"])).decode("utf-8"))}


def cmd_capture(a) -> int:
    """J3: what a person made in Desk on a site (`--site`, an address or a label on My sites), written into the app in this
    folder, or into a new blank app (`--new <name>`). The site is read with the key our hosting keeps for it; nothing is
    written there. `--only` and `--skip` take record types, kinds or `Type/name` ids, as the list prints them."""
    import capture  # noqa: PLC0415
    import blank  # noqa: PLC0415
    prefix = a.new.replace("_", " ").replace("-", " ").strip().upper() if a.new else None
    if a.new:  # the name first (F18): a name My apps refuses is said before the site is read
        try:
            online(door, "/v1/name", {"app": capture.app_for(prefix)})
        except Refused as e:
            if e.status != 404:  # a hosting without the command's name door: the new app's own door says it
                raise
    read = unpack(online(door, "/v1/capture/read", {"site": a.site}))
    folder = None if a.new else app_folder(a)
    # a new app is made only once the site has something to capture: never an empty app left behind
    manifest = blank.manifest(prefix, capture.app_for(prefix)) if a.new else read_json(folder / "manifest.json")
    res = capture.capture(read.get("records") or {}, read.get("installs") or [], manifest, read["site"], read.get("others"),
                          read.get("unread"))
    for line in capture.lines(res, read["site"]):
        print(line)
    if not res["items"]:
        print(WORDS["capture_nothing"].format(folder="a new app (none was made)" if a.new else "this app"))
        return 0
    if a.new:
        made = online(door, "/v1/new", {"samples": [], "name": prefix})
        folder = bring_down(made["app"], made.get("version"))
        manifest = read_json(folder / "manifest.json")
        res = capture.capture(read.get("records") or {}, read.get("installs") or [], manifest, read["site"], read.get("others"),
                              read.get("unread"))
    m, ids = capture.write(manifest, res, skip=a.skip or [], only=a.only or [])
    if not ids:
        raise Stop(WORDS["capture_none"])
    before = (folder / "manifest.json").read_text("utf-8")
    (folder / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", "utf-8")
    ok, verdict = check_folder(folder)
    if not ok:  # the folder stays as it was: nothing half-written
        (folder / "manifest.json").write_text(before, "utf-8")
        raise Stop(WORDS["capture_red"].format(verdict=verdict))
    where = f"apps/{folder.name}" if folder.parent.name == "apps" else str(folder)
    print(WORDS["captured"].format(n=len(ids), site=read["site"], folder=where) + " " + verdict)
    if ok:
        print(WORDS["capture_next"])
    return 0 if ok else 1


def cmd_download(a) -> int:
    row = online(door, "/v1/app", {"app": a.name})
    v = next((x for x in reversed(row.get("versions") or []) if not a.version or x.get("version") == a.version), None)
    if not v:
        raise Stop(f"This app has no version {a.version}." if a.version else "This app has no version yet.")
    target = bring_down(a.name, v["version"])
    who = {"page": "on the page", "ivn_cmd": "with ivn", "ivn": "with ivn", "upload": "by an upload"}.get(v.get("how"), "")
    print(WORDS["downloaded"].format(version=v["version"], state="draft, " if not v.get("sites") else "", who=v.get("by"),
                                     how=who, app=a.name).replace("  ", " "))
    print(folder_line(target, a.name))
    return 0


def cmd_check(a) -> int:
    ok, verdict = check_folder(app_folder(a))
    print(verdict)
    return 0 if ok else 1


# ── push, pull, add, take ────────────────────────────────────────────────────


def bring_in_newer(folder: pathlib.Path, app: str) -> None:
    """J8-09, J11-03: a version on the server newer than the one the folder started from (a colleague's sample, an upload
    on the page) is brought in first, as `ivn pull` does, so the push carries both; only a real conflict stops (M29)."""
    base = read_json(folder / "app.json").get("base")
    if not base:
        return
    try:
        latest = latest_of(door("/v1/app", {"app": app}))
    except Refused as e:
        if e.code == "no_app":
            return
        raise
    if latest and latest != base:
        conflicts = merge_latest(folder, app, latest)
        if conflicts:
            n = len(conflicts)
            raise Stop(WORDS["m29"].format(version=latest, n=n, s="" if n == 1 else "s", files=", ".join(conflicts)))
        print(WORDS["pulled"].format(version=latest))


def upload(folder: pathlib.Path, app: str) -> str:
    """The folder as the next draft (J3-07): the kit's check first, then the same two doors as the page. A folder made away
    from My apps (an app older than My apps) becomes an app of the company's at its first upload."""
    marked = still_marked(folder)
    if marked:
        raise Stop(WORDS["marked"].format(files=", ".join(marked)))
    sync_version(folder)
    ok, verdict = check_folder(folder)  # J3-04: green is the kit's check and the app's own tests
    if not ok:
        raise Stop(WORDS["m06"].format(verdict=verdict.removeprefix("CHECK RED: ").rstrip(".")))
    bring_in_newer(folder, app)  # after the check, so a folder it refuses never reaches the server (the server checks again)
    data = zip_folder(folder)
    try:
        u = door("/v1/draft/url", {"app": app, "size": len(data)})
    except Refused as e:
        if e.code != "no_app":
            raise
        prefix = read_json(folder / "manifest.json").get("prefix") or app.replace("_", " ").upper()
        door("/v1/new", {"own_folder": True, "name": prefix})
        u = door("/v1/draft/url", {"app": app, "size": len(data)})
    status, raw = _send(u.get("method") or "PUT", u["url"], data, u.get("headers") or {}, timeout=600)
    if status not in (200, 201, 204):
        raise Stop(f"The upload was not accepted (it answered {status}). Nothing changed on the server: try again.")
    kept = door("/v1/draft/keep", {"app": app, "key": u["key"]})
    if kept.get("note"):  # a version made between the check above and this upload (J8-09): said, never a refusal
        print(kept["note"])
    set_version(folder, kept["version"])
    remember(folder)
    return kept["version"]


def cmd_push(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    if not changed(folder) and read_json(folder / "app.json").get("base"):
        print(WORDS["unchanged"].format(version=read_json(folder / "app.json").get("version")))
        return 0
    print(WORDS["pushed"].format(version=online(upload, folder, app)))
    return 0


def catch_up(folder: pathlib.Path, app: str) -> None:
    """J2-15: a build server starts each build from a clean checkout, whose `base` is the version last committed, not the
    one its last build uploaded. The repository holds what a command uploaded, so it goes on from there. Something changed
    on the page is not in the repository: that is brought in, and a conflict stops the build (M29)."""
    a = read_json(folder / "app.json")
    base = a.get("base")
    if (folder / STATE).exists() or not base:  # a folder that has matched the server here is not a clean checkout
        return
    row = door("/v1/app", {"app": app})
    latest = latest_of(row)
    if not latest or latest == base:
        return
    if all(v.get("how") in ("ivn", "ivn_cmd") for v in row.get("versions") or [] if _vt(v.get("version")) > _vt(base)):
        a["base"] = latest
        write_json(folder / "app.json", a)
        return
    conflicts = merge_latest(folder, app, latest)
    if conflicts:
        n = len(conflicts)
        raise Stop(WORDS["m29"].format(version=latest, n=n, s="" if n == 1 else "s", files=", ".join(conflicts)))


def push_first(folder: pathlib.Path, app: str) -> str | None:
    """J3-07: `ivn try` and `ivn publish` upload first when the folder changed, and say so."""
    online(catch_up, folder, app)
    if changed(folder) or not read_json(folder / "app.json").get("base"):
        return online(upload, folder, app)
    return None


def is_binary(b: bytes | None) -> bool:
    return b is not None and b"\0" in b[:8192]


def _merge_one(ours: pathlib.Path, base: bytes, theirs: bytes, rel: str) -> bool:
    """git merges one file in place, marking a conflict as git marks one; True when it left a conflict."""
    with tempfile.TemporaryDirectory() as tmp:
        b, t = pathlib.Path(tmp, "base"), pathlib.Path(tmp, "theirs")
        b.write_bytes(base)
        t.write_bytes(theirs)
        r = subprocess.run(["git", "merge-file", "-L", f"your {rel}", "-L", "the version you started from", "-L", "the server's",
                            str(ours), str(b), str(t)], capture_output=True)
    if r.returncode == 0:
        return False
    if 1 <= r.returncode <= 127 and MARK in ours.read_bytes():
        return True
    raise Stop(f"git could not merge {rel}: {r.stderr.decode(errors='replace')[:200]}")


def _plain_json(data: bytes | None, rel: str, base_version: str | None) -> bytes | None:
    """The two tool-written files, each in one form with the base's own version on it, so the version lines never conflict."""
    if data is None or rel not in ("app.json", "manifest.json"):
        return data
    try:
        d = json.loads(data)
    except ValueError:
        return data
    if base_version:
        d["version"] = base_version
        if rel == "app.json":
            d["base"] = base_version
    return (json.dumps(d, indent=1, ensure_ascii=False) + "\n").encode()


def bring_in(folder: pathlib.Path, base_dir: pathlib.Path, theirs_dir: pathlib.Path, version: str) -> list[str]:
    """A three-way merge per file: the folder keeps its changes and takes the server's; files both changed are merged by
    git, and what git cannot join is marked. The answer names the files left with a conflict."""
    base_version = read_json(base_dir / "app.json").get("version")
    conflicts = []
    rels = {r for r, _ in files_of(base_dir)} | {r for r, _ in files_of(theirs_dir)}
    for rel in sorted(rels):
        o_p, b_p, t_p = folder / rel, base_dir / rel, theirs_dir / rel
        o = o_p.read_bytes() if o_p.is_file() else None
        b = b_p.read_bytes() if b_p.is_file() else None
        t = t_p.read_bytes() if t_p.is_file() else None
        o, b_n, t_n = _plain_json(o, rel, base_version), _plain_json(b, rel, base_version), _plain_json(t, rel, base_version)
        if t_n == b_n:  # the server did not change it: the folder's stands
            if o is not None and rel in ("app.json", "manifest.json"):
                o_p.write_bytes(o)
            continue
        if o == b_n or o == t_n:  # only the server changed it, or both the same way
            if t is None:
                o_p.unlink(missing_ok=True)
            else:
                o_p.parent.mkdir(parents=True, exist_ok=True)
                o_p.write_bytes(t_n)
            continue
        if o is None or t is None or is_binary(o) or is_binary(t_n) or is_binary(b_n):  # nothing git could mark
            if o is None and t is not None:
                o_p.parent.mkdir(parents=True, exist_ok=True)
                o_p.write_bytes(t_n)
            conflicts.append(rel)
            continue
        o_p.write_bytes(o)
        if _merge_one(o_p, b_n or b"", t_n, rel):
            conflicts.append(rel)
    set_version(folder, version)
    return conflicts


def has_git() -> bool:
    """git that answers: a Mac's stand-in, which only offers to install the developer tools, is not git."""
    if shutil.which("git") is None:
        return False
    return subprocess.run(["git", "--version"], capture_output=True).returncode == 0


def _vt(v) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def keep_raised(folder: pathlib.Path, version: str) -> None:
    """The base follows the server; the higher number the developer set in `app.json` stays, and the manifest with it."""
    for name in ("app.json", "manifest.json"):
        p = folder / name
        try:
            d = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        d["version"] = version
        write_json(p, d)


def merge_latest(folder: pathlib.Path, app: str, latest: str) -> list[str]:
    """The server's `latest` into the folder, against the version the folder was based on."""
    base = read_json(folder / "app.json").get("base")
    if not base:
        raise Stop(WORDS["never_on_server"])
    if not has_git():
        raise Stop(WORDS["no_git"])
    mine = read_json(folder / "app.json")
    raised = mine.get("version") if _vt(mine.get("version")) > _vt(latest) else None  # a higher number the developer set
    with tempfile.TemporaryDirectory() as tmp:
        b, t = pathlib.Path(tmp, "base"), pathlib.Path(tmp, "theirs")
        b.mkdir()
        t.mkdir()
        unzip_into(fetch_version(app, base), b)
        unzip_into(fetch_version(app, latest), t)
        if mine.get("address"):  # the server's copies as this folder holds them once published, or nobody's edit would conflict
            apply_address(b, mine["address"])
            apply_address(t, mine["address"])
        conflicts = bring_in(folder, b, t, latest)
        remember(folder, t)
    if raised:
        keep_raised(folder, raised)
    return conflicts


def say_merge(folder: pathlib.Path, latest: str, conflicts: list[str], quiet: bool = False) -> int:
    if conflicts:
        n = len(conflicts)
        print(WORDS["m29"].format(version=latest, n=n, s="" if n == 1 else "s", files=", ".join(conflicts)))
        return 1
    if not quiet:
        print(WORDS["pulled"].format(version=latest))
    return 0


def latest_of(row: dict) -> str | None:
    vs = row.get("versions") or []
    return vs[-1].get("version") if vs else None


def cmd_pull(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    latest = latest_of(online(door, "/v1/app", {"app": app}))
    if latest == read_json(folder / "app.json").get("base"):
        print(WORDS["up_to_date"].format(version=latest))
        return 0
    return say_merge(folder, latest, online(merge_latest, folder, app, latest))


def cmd_add(a, take: bool = False) -> int:
    """Online the server keeps the one copy: its door adds the sample and the result comes down, keeping what you changed
    here. Offline (J6-07) the folder changes by the same rules and reaches the server at your next push."""
    folder = app_folder(a)
    app = app_id(folder)
    try:
        out = door("/v1/add", {"app": app, "sample": a.sample, **({"take": True} if take else {})})
    except Offline:
        if take:
            raise Stop(WORDS["no_reach"]) from None
        import combine  # noqa: PLC0415
        try:
            combine.add(a.sample, folder, out=sys.stdout)
        except combine.Refused as e:
            raise Stop(e.text) from None
        print(WORDS["offline_add"])
        return 0
    for line in out.get("words") or []:
        print(line)
    return say_merge(folder, out["version"], online(merge_latest, folder, app, out["version"]), quiet=True)


# ── the sandbox: connect, settings, secrets, try, test ───────────────────────


def cmd_secret(a) -> int:
    folder = app_folder(a)
    value = ask_secret(f"The value of {a.name}:")
    print(online(door, "/v1/settings", {"app": app_id(folder), "values": {a.name: value}})["words"])
    return 0


def cmd_secrets(a) -> int:
    folder = app_folder(a)
    try:
        out = online(door, "/v1/secrets", {"app": app_id(folder), **({"site": a.site} if a.site else {})})
    except Refused as e:
        if e.code == "no_sandbox":
            raise Stop(WORDS["m31"]) from None
        raise
    print(WORDS["secrets_head"].format(site=out.get("site")))
    if not out.get("points"):
        print(WORDS["no_points"])
    for x in out.get("points") or []:
        print(f"{x['key']}  {x['plain']}: {x.get('secret') or '(not read: run it again)'}")
    return 0


RESULT = re.compile(r"^(\S+) \((.*?)\): (.*)$", re.S)
PASSED = re.compile(r"^Passed(?:, answered in|: reached, signature accepted, answered in) ([\d.]+) s\.?$")


# the doors speak the page's words; a terminal has no button to press
PAGE_WORDS = (("press Try again", "run ivn try"), ("Press Try again", "Run ivn try"), ("press Test again", "run ivn test"),
              ("Press Test again", "Run ivn test"), ("Press Publish again", "Run ivn publish again"),
              ("then press it again", "then run it again"))


def terminal(words: str) -> str:
    for page, command in PAGE_WORDS:
        words = words.replace(page, command)
    return words


def result_rows(lines: list[str]) -> list[str]:
    """J4-06: one line per connection point, its plain name beside its key: `tgr_check   a check at Pay      Passed  0.31 s`."""
    rows = [(m.group(1), m.group(2), m.group(3)) if (m := RESULT.match(x)) else (x, "", "") for x in map(terminal, lines)]
    wide_k = max((len(r[0]) for r in rows if r[1] or r[2]), default=0)
    wide_p = max((len(r[1]) for r in rows), default=0)
    out = []
    for key, plain, rest in rows:
        if not plain and not rest:
            out.append(key)
            continue
        p = PASSED.match(rest)
        out.append(f"{key:<{wide_k}}   {plain:<{wide_p}}   " + (f"Passed  {p.group(1)} s" if p else rest))
    return out


SHELF_LINE = "Published means waiting on the customer's shelf: it is installed only when their administrator installs it."


def follow(path: str, app: str) -> dict:
    """A try or a publish, one step per call, as the page polls it: each new line as it comes, and the card checkout's
    address when one opens. Ends done, or stops in the door's own words."""
    said, paid, waited, out = set(), False, 0, {}
    while waited < POLL_MAX:
        try:
            out = door(path, {"app": app})
        except (Offline, KeyboardInterrupt):  # it was accepted: it goes on on our side
            raise Stop(WORDS["gave_up"]) from None
        for line in out.get("lines") or []:
            if line not in said and line != SHELF_LINE:  # the row's own line says it, and a listing has no customer's shelf
                said.add(line)
                print(line, flush=True)
        if out.get("checkout_url") and not paid:
            paid = True
            print(f"{out.get('pay') or 'Pay with your card'}: {out['checkout_url']}", flush=True)
        if out.get("step") == "stopped":
            words = out.get("stop") or "It stopped."
            lines = out.get("build_lines") or []
            raise Stop("\n".join([words, *lines]))
        if out.get("done") or out.get("step") == "done" or out.get("invoice_waiting"):
            return out
        try:
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            raise Stop(WORDS["gave_up"]) from None
        waited += max(1, POLL_SECONDS)
    raise Stop(WORDS["gave_up"])


def choose_plan(money: dict, given: str | None) -> str | None:
    """J5-15: the three plans, the first time; the plan the door suggests comes first and is what an empty answer takes."""
    plans = money.get("plans")
    if given or not plans:
        return given
    want = money.get("suggested")
    plans = sorted(plans, key=lambda p: p.get("plan") != want)
    for i, p in enumerate(plans, 1):
        print(f"{i}  {p['words']}")
    typed = ask_or_none(WORDS["type_plan"])
    if typed in ("1", "2", "3") and int(typed) <= len(plans):
        return plans[int(typed) - 1]["plan"]
    if typed == "" and want:  # a person pressed Enter; a build server's silence never chooses a charge
        return want
    raise Stop(WORDS["no_plan"])


def cmd_try(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    version = push_first(folder, app)
    try:
        start = online(door, "/v1/try", {"app": app, **({"site": a.site} if a.site else {})})
    except Refused as e:
        if e.code == "no_sandbox":
            raise Stop(WORDS["m31"]) from None
        raise
    print(WORDS["trying_on"].format(site=start.get("site")))  # the site first: the one asked for, else the person's last
    if version:
        print(WORDS["pushed"].format(version=version))
    if start.get("sections"):  # on a site its administrator installs, its own install shows them
        print(WORDS["changes_head"])
    for sec in start.get("sections") or []:
        print(f"  {sec['title']}")
        for line in sec.get("lines") or []:
            print(f"    {line}")
    if a.show_wording:
        print(start.get("wording") or "")
    if (start.get("money") or {}).get("line"):  # trying is free: nothing is asked
        print(start["money"]["line"])
    online(door, "/v1/try/install", {"app": app, "sha": start.get("sha"), "site": start.get("site")})
    done = follow("/v1/try/status", app)
    if done.get("installed_on"):  # where it went: the site's own Desk and till, and the app's own address
        print(done["installed_on"])
    if done.get("shelf_key"):
        print(done["shelf_key"])
    for x in ("desk", "till_url", "address"):
        if done.get(x):
            print(done[x])
    for line in done.get("head") or []:
        if line != done.get("installed_on"):
            print(line)
    rows = result_rows(done.get("results") or [])
    if not rows and done.get("press"):  # on a site its administrator installs, the site's own Test connection tests it
        print(WORDS["no_points"])
    for line in rows:
        print(line)
    for line in done.get("till") or []:
        print(line)
    return 0 if all("Passed" in x for x in rows) else 1


def _local_secret(folder: pathlib.Path) -> str:
    local_env_if_missing(folder)
    for line in (folder / ".env.local").read_text("utf-8").splitlines():
        name, sep, val = line.strip().partition("=")
        if sep and name == "IVN_TEST_SECRET" and val.strip():
            return val.strip().strip('"')
    raise Stop(WORDS["local_secret"])


def _plain_words() -> dict:
    spec = importlib.util.spec_from_file_location("kit_calllog", KIT / "tools" / "app_template" / "service" / "calllog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PLAIN


def _local_points(folder: pathlib.Path) -> list[dict]:
    d = read_json(folder / "service" / "dispatch.json")
    plain = _plain_words()
    out = [{"path": path, "key": p.get("key") or path, "plain": plain.get(p.get("kind"), p.get("kind") or "")}
           for m in (d.get("mounts") or {}).values() if isinstance(m, dict) for path, p in (m.get("points") or {}).items()]
    if out:
        return out
    m = read_json(folder / "manifest.json")
    for group, field, kind in (("extension_subscriptions", "endpoint_url", None), ("remote_keys", "endpoint_url", "remote_key"),
                               ("webhooks", "url", "webhook")):
        for x in m.get(group) or []:
            if isinstance(x, dict) and x.get(field):
                k = kind or x.get("point")
                out.append({"path": urllib.parse.urlsplit(x[field]).path, "key": x.get("key") or x.get("name") or x[field],
                            "plain": plain.get(k, k or "")})
    return out


def _local_alive() -> bool:
    try:
        return _send("GET", LOCAL_URL + "/health", None, {}, timeout=1)[0] == 200
    except Offline:
        return False


def local_test(folder: pathlib.Path) -> list[str]:
    """J3-10: each point on this laptop's service, signed with the test secret as the site signs. The service is started for
    the test when nothing answers yet, and stopped after."""
    secret = _local_secret(folder)
    points = _local_points(folder)
    proc = None
    if not _local_alive():
        proc = subprocess.Popen([sys.executable, str(folder / "service" / "app.py"), "--local"], cwd=folder,
                                stdout=subprocess.DEVNULL, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        for _ in range(100):
            if _local_alive() or proc.poll() is not None:
                break
            time.sleep(0.1)
        if proc.poll() is not None:
            raise Stop(WORDS["port_taken"])
    try:
        lines = []
        for p in points:
            ts, body, t0 = int(time.time()), b"{}", time.monotonic()
            sig = base64.b64encode(hmac.new(secret.encode(), str(ts).encode() + b"." + body, hashlib.sha256).digest()).decode()
            where = f"{p['key']} ({p['plain']}): "
            try:
                status, _ = _send("POST", LOCAL_URL + p["path"], body, {
                    "Content-Type": "application/json", "X-iVendNext-Test": "1", "X-iVendNext-Timestamp": str(ts),
                    "X-iVendNext-Signature": sig, "X-iVendNext-Site": "localhost"}, timeout=10)
            except Offline:
                lines.append(where + WORDS["local_down"])
                continue
            if status == 200:
                lines.append(where + f"Passed, answered in {time.monotonic() - t0:.2f} s")
            elif status in (401, 403):
                lines.append(where + WORDS["local_401"])
            elif status == 404:
                lines.append(where + WORDS["local_404"])
            else:
                lines.append(where + WORDS["local_other"].format(status=status))
        return lines
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def cmd_test(a) -> int:
    folder = app_folder(a)
    if a.local:
        lines = local_test(folder)
        print(WORDS["tested_local"])
        if not lines:
            print(WORDS["no_points"])
        for line in result_rows(lines):
            print(line)
        return 0 if all("Passed" in x for x in lines) else 1
    out = online(door, "/v1/test", {"app": app_id(folder)})  # the finished try's own site
    if out.get("site"):
        print(WORDS["on_site"].format(site=out["site"]))
    for line in out.get("head") or []:
        print(line)
    rows = result_rows(out.get("results") or [])
    if not rows and out.get("press"):
        print(WORDS["no_points"])
    for line in rows:
        print(line)
    return 0 if all("Passed" in x for x in rows) else 1


# ── publish ──────────────────────────────────────────────────────────────────


def picture(app: str, path: pathlib.Path) -> dict:
    """One picture of the card into the App library, by the library's own rules (the page's *Pictures*)."""
    try:
        data = path.read_bytes()
    except OSError:
        raise Stop(WORDS["bad_picture"].format(path=path)) from None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        kind, (w, h) = "image/png", struct.unpack(">II", data[16:24])
    elif data[:2] == b"\xff\xd8":
        kind, w, h, i = "image/jpeg", 0, 0, 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                break
            mark, size = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= mark <= 0xCF and mark not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                break
            i += 2 + size
        if not w:
            raise Stop(WORDS["bad_picture"].format(path=path))
    else:
        raise Stop(WORDS["bad_picture"].format(path=path))
    return online(door, "/v1/publish/picture", {"app": app, "type": kind, "data": base64.b64encode(data).decode(), "w": w, "h": h})


def split_list(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"\s*\|\s*", text) if x.strip()]


def ask_card(folder: pathlib.Path, app: str, industries: list[str]) -> dict:
    """J7-06: the card's fields not yet in app.json are asked, and kept there."""
    a = read_json(folder / "app.json")
    card = dict(a.get("card") or {})
    asks = (("title", "Title:", str), ("summary", "One line:", str), ("what", "What it does (three short lines, split by |):", split_list),
            ("pictures", "Pictures (up to four files, split by |; leave empty for none):", split_list),
            ("industries", f"Industries, split by | ({', '.join(industries)}):", split_list),
            ("price", "Price (free, or key: With a key: retailers ask you):", str),
            ("guide", "Guide link (any https page, your repository's README too):", str))
    if [f for f, _, _ in asks if f not in card]:
        print(WORDS["card_asks"])
    for field, prompt, read in asks:
        if card.get(field) or (field == "pictures" and field in card):
            continue
        for _ in range(3):
            typed = ask_or_none(prompt)
            if typed is None:
                raise Stop(WORDS["card_stop"].format(fields=", ".join(f for f, _, _ in asks if not card.get(f) and f != "pictures")))
            value = read(typed)
            if field == "price":
                value = value.lower() if value.lower() in ("free", "key") else ""
            if field == "industries" and industries:  # a wrong one kept in app.json would never be asked again
                value = value if value and set(value) <= set(industries) else []
            if value or field == "pictures":
                card[field] = value
                break
            print(WORDS["ask_again"])
        else:
            raise Stop(WORDS["card_stop"].format(fields=field))
    if card != a.get("card"):
        a["card"] = card
        write_json(folder / "app.json", a)
    return card


def pay_choice(money: dict) -> str | None:
    """J5-17: card or invoice, on a first order that is charged with no card on file; the answer is the invoice's address."""
    if not money.get("asks_pay"):
        return None
    print(WORDS["pay_by"].format(email="your accounts e-mail"))
    if ask("Type 1 or 2:") == "2":
        return ask("Your accounts e-mail:") or None
    return None


def cmd_publish(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    uploaded = push_first(folder, app)
    same_version(folder)
    version = read_json(folder / "app.json").get("version")
    start = online(door, "/v1/publish/start", {"app": app})
    if start.get("m16"):
        raise Stop((WORDS["uploaded"].format(version=uploaded) if uploaded else "") + start["m16"])
    sites = list(a.to or [])
    public = a.public or bool(start.get("listed"))
    if start.get("nothing_new") and not sites and not a.public:
        raise Stop(WORDS["m33_token"].format(version=start.get("version") or version))
    money = start.get("money") or {}
    for line in money.get("lines") or []:
        print(line)
    plan = None if money.get("own_only") and not a.own else choose_plan(money, a.plan)
    invoice = pay_choice(money)
    body = {"app": app, "to": "everyone" if public else "customer", "sites": sites, "own": a.own,
            **({"plan": plan} if plan else {}), **({"invoice": invoice} if invoice else {})}
    if a.public:
        card = ask_card(folder, app, start.get("industries") or [])
        pics = [picture(app, folder / p) for p in (card.get("pictures") or [])[:4]]
        body["card"] = {**card, "pictures": pics}
    done = None
    try:
        online(door, "/v1/publish", body)
        done = follow("/v1/publish/status", app)
    except Stop as e:
        if uploaded:
            raise Stop(WORDS["uploaded"].format(version=uploaded) + str(e)) from None
        raise
    if done.get("invoice_waiting"):  # it goes on when the invoice is paid; `ivn status` carries it on
        return 0
    shipped = done.get("version") or version
    behind = shipped != read_json(folder / "app.json").get("base")  # the server's latest went out: a colleague's, say
    if not behind:
        write_published(folder, shipped, start.get("service") or hosted_address(app))
    row = online(door, "/v1/app", {"app": app})
    went = next((v.get("sites") or [] for v in row.get("versions") or [] if v.get("version") == shipped), [])
    n, lead = len(went), WORDS["uploaded"].format(version=uploaded) if uploaded else ""
    waiting = str(done.get("public_words") or "").startswith("Waiting")  # a later version while the first listing still waits
    if (a.public or waiting) and done.get("public_words"):
        print(lead + str(done["public_words"]) + (f" {done['card_url']}" if done.get("card_url") else ""))
    elif public and done.get("public_words"):  # a request closed earlier answers no words, and lists nothing
        print(lead + WORDS["published_listed"].format(version=shipped, n=n, s="" if n == 1 else "s"))
    elif sites:  # the customer's: never the sandbox; a label is named with its address
        named = {x.get("label"): x["site"] for x in online(door, "/v1/sites", {}).get("company") or [] if x.get("label")}
        shown = [f"{s} ({named[s]})" if s in named else s for s in sites]
        print(lead + WORDS["published"].format(version=shipped, sites=", ".join(shown)))
    else:
        print(lead + WORDS["published_n"].format(version=shipped, n=n, s="" if n == 1 else "s"))
    keyed = {x.get("key_address") or x["site"]: x for x in done.get("install_now") or [] if not x.get("installed")}  # J6f F2
    if sites and done.get("send"):  # the message, line by line, the key on its own line and unindented, so it copies clean
        ready = [x for x in done["send"] if "1. " in (x.get("message") or "") and x.get("site") not in keyed]
        for x in done["send"]:
            if x.get("site") in keyed:  # the company holds its key: Install now, never a message to forward
                continue
            if x not in ready:  # no key yet, or one we withdrew: the library's words are for the developer, not to forward
                print(f"{x.get('site')}: {x.get('message')}")
        if ready:
            print(WORDS["send_head"])
        for x in ready:
            if len(ready) > 1:
                print(f"{x.get('site')}:")
            print(x.get("message") or "")
    if a.install:
        install_now(app, done, sites)
    else:
        for x in keyed.values():
            name = x.get("label") or x["site"]
            print(WORDS["install_hint"].format(name=f"{x['label']} ({x['site']})" if x.get("label") else x["site"], to=name))
    if behind:
        print(WORDS["behind"].format(version=shipped))
    return 0


def install_now(app: str, done: dict, named: list) -> None:
    """`--install`: on each customer's site this publish went to where the company holds its key (only the `--to` sites
    when some are named), the site's own install words, then the install (the flag is the yes, as ivn try installs
    after its words), until it is installed."""
    held = {x["site"] for x in done.get("install_now") or []}
    for x in done.get("send") or []:
        if x.get("site") and x["site"] not in held:  # no key there: the message above is the way
            print(WORDS["no_key_install"].format(site=x["site"]))
    for x in done.get("install_now") or []:
        if x.get("installed") or named and not {x["site"], x.get("label")} & set(named):
            continue
        words = online(door, "/v1/publish/install", {"app": app, "site": x["site"]})
        if words.get("done"):  # it has this version already
            print(words.get("words") or "")
            continue
        print(WORDS["installing_on"].format(version=words.get("version"), site=x["site"]))
        for sec in words.get("sections") or []:
            print(f"  {sec['title']}")
            for line in sec.get("lines") or []:
                print(f"    {line}")
        out = online(door, "/v1/publish/install", {"app": app, "site": x["site"], "sha": words.get("sha")})
        for _ in range(100):
            if out.get("step") != "installing":
                break
            time.sleep(3)
            out = online(door, "/v1/publish/install", {"app": app, "site": x["site"], "sha": words.get("sha")})
        print(out.get("words") or "")


# ── status, logs, keep it going ──────────────────────────────────────────────


def _published_index() -> dict:
    status, raw = _send("GET", SAMPLES_INDEX if "IVN_SAMPLES_INDEX" not in os.environ else os.environ["IVN_SAMPLES_INDEX"],
                        None, {}, timeout=10)
    if status != 200:
        raise Offline(f"the index answered {status}")
    return json.loads(raw)


def newer_lines(folder: pathlib.Path) -> str:
    """J6-09: each sample with a newer published version, with its *Versions* lines; it only tells. M27 when it cannot read
    the published index."""
    import combine  # noqa: PLC0415
    try:
        found = combine.newer(folder, _published_index())
    except (Offline, ValueError):
        return WORDS["m27"]
    out = []
    for n in found:
        lines = " ".join(x for _, ls in n.lines for x in ls)
        out.append(WORDS["newer"].format(number=combine.number(n.sample), version=n.version, yours=n.yours)
                   + (WORDS["changes"].format(lines=lines) if lines else ""))
    return " ".join(out)


def cmd_status(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    try:
        rows = door("/v1/apps", method="GET").get("apps") or []
    except Offline:
        print(f"{app} {read_json(folder / 'app.json').get('version')} in this folder.")
        print(WORDS["m27"])
        return 0
    row = next((r for r in rows if r.get("app") == app), None)
    line = (row or {}).get("line") or "not on our server yet: run ivn push"
    tail = newer_lines(folder)
    sites = []
    if row:
        try:
            sites = door("/v1/where", {"app": app}).get("sites") or []
        except (Refused, Offline):
            pass
    for s in sites:  # §14: a draft a try installed is on the sandbox, not on no site
        if s.get("sandbox") and s.get("version"):
            line = line.replace(f"{s['version']} a draft, on no site yet", f"{s['version']} a draft, tried, not yet published")
    print(f"{app} {line}." + (f" {tail}" if tail else ""))
    for s in sites:  # J5-16: has it been installed?
        if s.get("customer") and s.get("state"):
            print(f"{s['site']}: {s['state']}")
    if row:
        for path in ("/v1/publish/status", "/v1/try/status"):
            try:
                s = door(path, {"app": app})
            except (Refused, Offline):
                continue
            if s.get("invoice_waiting"):
                print((s.get("lines") or [""])[-1])
            elif s.get("step") in ("order", "copy", "upload", "build"):
                print(f"Building {s.get('version')}…")
            if s.get("step") == "stopped" and s.get("stop"):
                print("\n".join([terminal(s["stop"]), *(s.get("build_lines") or [])]))
    return 0


def cmd_logs(a) -> int:
    out = online(door, "/v1/logs", {"app": app_id(app_folder(a)), "hours": a.hours, **({"q": a.search} if a.search else {})})
    for line in out.get("lines") or []:
        print(line)
    if out.get("words"):
        print(out["words"])
    return 0


def cmd_rollback(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    first = online(door, "/v1/rollback", {"app": app, "to": a.version})
    print(first["words"])  # no typed name: every version stays, and each site's administrator presses Update (GUARDSWEEP)
    out = online(door, "/v1/rollback", {"app": app, "to": a.version, "go": True})
    follow("/v1/publish/status", app)
    for x in out.get("messages") or []:
        print(f"{x['site']}: {x['message']}")
    return 0


def site_line(x: dict, default) -> str:
    """One of the company's sites: its label (a sandbox of ours names its owner) and address, how Try installs there,
    whether ivn try uses it, and, for a pool sandbox, the date it goes back unless someone signs in to it."""
    if x.get("stale"):  # the key the developer added no longer signs in: the hosting's own words
        how = x["stale"]
    elif x.get("live"):
        how = WORDS["how_live"]
    elif x.get("route") in ("ours", "own"):
        how = WORDS["how_" + x["route"]]
    else:
        how = WORDS["one_press" if x.get("press") else "its_admin"]
    name = f"{x['label']} · {x['site']}" if x.get("label") else x["site"]
    line = WORDS["site_row"].format(site=name, how=how) + (WORDS["your_last"] if x["site"] == default else "")
    return line + ("\n    " + x["back_words"] if x.get("back_words") else "")  # a pool sandbox: when it goes back


def cmd_sites(a) -> int:
    """The company's sites, from the same door as the page's list (*My sites*): each one, its label, and how Try installs
    there. `add`, `use`, `label` and `remove` change the list, as the page's buttons do."""
    act, target = a.action, a.target
    if act and not target or act == "label" and a.label is None:
        raise Stop(WORDS["sites_usage"])
    if act == "add":
        key = os.environ.get("IVN_SITE_KEY", "")
        secret = os.environ.get("IVN_SITE_SECRET", "")
        if not key and sys.stdin.isatty():  # read without echo; a build server sets the two variables
            print(WORDS["key_where"])
            key = ask_secret(WORDS["site_key"])
            secret = ask_secret(WORDS["site_secret"]) if key else ""
        out = online(door, "/v1/sites/add", {"site": target, **({"key": key, "secret": secret} if key else {}),
                                             **({"label": a.as_label} if a.as_label else {})})
    elif act == "use":
        out = online(door, "/v1/sites/default", {"site": target})
    elif act == "label":
        out = online(door, "/v1/sites/label", {"site": target, "label": a.label})
    elif act == "remove":
        out = online(door, "/v1/sites/remove", {"site": target, "mine": True})
        kept = any(target in (x.get("site"), x.get("key_address"), x.get("label")) for x in out.get("company") or [])
        out["words"] = WORDS["still_listed" if kept else "removed_mine"].format(site=target)
    else:
        out = online(door, "/v1/sites", {})
    if out.get("words") and act:
        print(out["words"])
    if out.get("sandbox") == "get" and not act:  # J6 F15: one of our developers with no sandbox of their own: first
        print(WORDS["get_sandbox_first"])
    if not out.get("company") and not act:
        print(out.get("words") or WORDS["m31"])
    for x in out.get("company") or []:
        print(site_line(x, out.get("default")))
    return 0


def cmd_remove_site(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    have = online(door, "/v1/sites", {"app": app}).get("sites") or []
    row = next((s for s in have if s.get("site") == a.site), None)
    if row:
        print(row["remove_words"])
    confirm(app)
    print(online(door, "/v1/sites/remove", {"app": app, "site": a.site})["words"])
    return 0


def cmd_cancel(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    print(online(door, "/v1/cancel", {"app": app})["words"])
    confirm(app)
    print(online(door, "/v1/cancel", {"app": app, "go": True})["words"])
    return 0


def cmd_handover(a) -> int:
    folder = app_folder(a)
    app = app_id(folder)
    print(WORDS["handover"])
    confirm(app)
    print(online(door, "/v1/handover", {"app": app, "to": a.word})["words"])
    return 0


def cmd_key(a) -> int:
    print(online(door, "/v1/key", {"app": app_id(app_folder(a)), "site": a.site})["words"])
    return 0


def cmd_package(a) -> int:
    folder = app_folder(a)
    m = read_json(folder / "app.json")
    if m.get("runs") != "function":
        raise Stop(WORDS["not_function"])
    import deploy_app  # noqa: PLC0415
    deploy_app.write_zip(m, folder, folder / "package.zip")
    print(WORDS["package_done"])
    return 0


# ── the command line ─────────────────────────────────────────────────────────


# ── J1 DEVSTART: doctor and update ───────────────────────────────────────────


def platform_python() -> str:
    return ".".join(str(n) for n in sys.version_info[:3])


def version_of(text: str) -> tuple:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x) for x in m.groups() if x is not None) if m else ()


def git_version() -> tuple | None:
    if shutil.which("git") is None:
        return None
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return version_of(r.stdout) if r.returncode == 0 else None


def kit_is_clone(kit: pathlib.Path = KIT) -> bool:
    return (kit / ".git").exists()


def kit_version(kit: pathlib.Path = KIT) -> str:
    """The kit's commit: the clone's, else the one the installer or ivn update wrote for GitHub's archive."""
    if kit_is_clone(kit) and has_git():
        r = subprocess.run(["git", "-C", str(kit), "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    try:
        return (kit / KIT_COMMIT_FILE).read_text("utf-8").strip()[:8] or "unknown"
    except OSError:
        return "unknown"


def _who() -> dict:
    return read_json(WHO_FILE)


def _company_apps() -> list:
    """The company's apps on our server (the command's own list), or none when it cannot be read."""
    try:
        return [r["app"] for r in door("/v1/apps", method="GET").get("apps") or [] if r.get("app")]
    except (Offline, Refused):
        return []


def cmd_doctor(a) -> int:
    """One screen: the Python and git found, the kit, the sign-in, the sites, and the one command to run next."""
    need = ".".join(map(str, MIN_PYTHON))
    print(WORDS["dr_python"].format(have=platform_python(), path=sys.executable, ok=WORDS["new_enough"]))
    if ON_WINDOWS:
        print(WORDS["dr_py"].format(ok=WORDS["found"] if shutil.which("py") else WORDS["missing"]))
    gv = git_version()
    if gv is None:
        print(WORDS["dr_no_git"])
    else:
        ok = WORDS["new_enough"] if gv >= MIN_GIT else WORDS["too_old"].format(need=".".join(map(str, MIN_GIT)))
        print(WORDS["dr_git"].format(have=".".join(map(str, gv)), ok=ok))
    print(WORDS["dr_kit"].format(where=KIT, how=("a git clone" if kit_is_clone() else "GitHub's archive") + ", "
                                 + kit_version()))
    signed, said = False, None
    try:
        token = token_now()
    except Stop:
        token = None
    if token:  # the sites answer first, so a revoked sign-in is never also called signed in
        try:
            out = door("/v1/sites", {}, token=token)
            signed = True
            sites = [x["site"] + (" (" + WORDS["one_press"] + ")" if x.get("press") else "") for x in out.get("company") or []
                     if not x.get("live")]  # a customer's live site is Publish's, never tried on
            said = WORDS["dr_sites"].format(sites=", ".join(sites)) if sites else WORDS["dr_no_sites"]
        except Offline:
            signed, said = True, WORDS["dr_no_reach"]
        except Refused as e:
            if e.status != 401:
                raise
    if signed and os.environ.get("IVN_TOKEN", "").strip():
        print(WORDS["dr_signed_token"])
    elif signed:
        who = _who()
        print(WORDS["dr_signed"].format(login=who["login"], name=who.get("name") or who.get("company"),
                                        company=who.get("company")) if who.get("login") else WORDS["dr_signed_unknown"])
    elif token or TOKEN_FILE.is_file() or os.environ.get("IVN_TOKEN", "").strip():
        print(WORDS["dr_bad_token"])
    else:
        print(WORDS["dr_signed_out"])
    if said:
        print(said)
    here = sorted(p.parent.name for p in (pathlib.Path.cwd() / "apps").glob("*/app.json"))
    if not signed:
        nxt = "ivn login"
    elif (pathlib.Path.cwd() / "app.json").is_file() or len(here) == 1:
        nxt = "ivn check, then ivn try"
    elif here:  # J6f F10: apps made already: work on one of them, never a new one
        nxt = f"ivn check, then ivn try, in apps/{here[0]}" + (f" (your apps here: {', '.join(here)})" if len(here) > 1 else "")
    elif theirs := _company_apps():
        nxt = f"ivn download {theirs[0]}" + (f" (your company's apps: {', '.join(theirs)})" if len(theirs) > 1 else "")
    else:
        word = (_who().get("company") or "<yourword>").lower()   # the company's first word, once ivn login has said it
        nxt = f"ivn new {word}_first_app (a blank app), or ivn new {word}_first_app --from s11 (from a sample)"
    print(WORDS["dr_next"].format(cmd=nxt))
    return 0


def _sync_from_archive(kit: pathlib.Path, data: bytes) -> str:
    """GitHub's archive of the kit's main, written over the kit in place: each file the archive has; a file the previous
    archive brought and this one has not is removed, and nothing else (your own files in the kit's folder stay: an
    editor's settings, notes, ``apps/``). Returns the archive's commit."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    commit = (zf.comment or b"").decode("ascii", "replace").strip()
    names = [n for n in zf.namelist() if not n.endswith("/")]
    top = names[0].split("/", 1)[0] + "/" if names else ""
    wanted = set()
    for n in names:
        rel = n[len(top):]
        if not rel or ".." in pathlib.PurePosixPath(rel).parts:
            continue
        wanted.add(rel)
        target = kit / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        body = zf.read(n)
        if not target.is_file() or target.read_bytes() != body:
            target.write_bytes(body)
            mode = (zf.getinfo(n).external_attr >> 16) & 0o777
            if mode & 0o111:
                target.chmod(target.stat().st_mode | 0o755)
    try:
        before = set((kit / KIT_FILES_FILE).read_text("utf-8").splitlines())
    except OSError:
        before = set()  # a kit with no list: nothing is removed
    for rel in sorted(before - wanted, reverse=True):
        p = kit / rel
        if ".." in pathlib.PurePosixPath(rel).parts or not p.is_file():
            continue
        p.unlink()
        for d in p.parents:
            if d == kit or any(d.iterdir()):
                break
            d.rmdir()
    (kit / KIT_FILES_FILE).write_text("\n".join(sorted(wanted)) + "\n", "utf-8")
    (kit / KIT_COMMIT_FILE).write_text(commit + "\n", "utf-8")
    return commit


def cmd_update(a) -> int:
    """The kit and ivn up to date: git pull in a clone, else GitHub's main archive written over the kit in place."""
    kit = KIT
    old = kit_version(kit)
    if kit_is_clone(kit):
        if not has_git():
            raise Stop(WORDS["up_no_git"])
        print(WORDS["up_clone"].format(where=kit), flush=True)
        r = subprocess.run(["git", "-C", str(kit), "pull", "--ff-only", "--quiet"], capture_output=True, text=True)
        if r.returncode:
            why = (r.stderr.strip().splitlines() or ["git answered " + str(r.returncode)])[-1]
            raise Stop(WORDS["up_dirty"].format(why=why.removeprefix("fatal: ").removeprefix("error: ")))
    else:
        print(WORDS["up_archive"].format(where=kit), flush=True)
        url = os.environ.get("IVN_KIT_ARCHIVE") or KIT_ARCHIVE
        status, data = _send("GET", url, None, {}, timeout=600)
        if status != 200 and not (status is None and url.startswith("file:")):   # a file: address is a test's stand-in
            raise Stop(f"Not updated: GitHub answered {status}. Your kit is as it was: try again.")
        _sync_from_archive(kit, data)
    new = kit_version(kit)
    print(WORDS["up_same" if new == old else "up_moved"].format(old=old, new=new))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ivn", description="Make, try, publish and keep your app going, over the same server as "
                                                         "My apps.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, fn, help_, in_app=True):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        if in_app:
            p.add_argument("--app", help="the app's folder (default: the current folder)")
        return p

    cmd("doctor", cmd_doctor, "what this computer has, whether it is signed in, and what to run next", in_app=False)
    cmd("update", cmd_update, "bring the kit and ivn up to date", in_app=False)
    cmd("login", cmd_login, "sign this computer in, by a code in your browser", in_app=False)
    p = cmd("new", cmd_new, "make a blank app, or an app from one sample or several", in_app=False)
    p.add_argument("name", help="the app's name, like acme_member_till: your first word, then your words")
    p.add_argument("--from", dest="from_samples", action="append", metavar="SAMPLE",
                   help="a sample, like s23; once per sample (none: a blank app)")
    p = cmd("capture", cmd_capture, "write what was made in Desk on a site into this app, or a new one")
    p.add_argument("--site", required=True, help="the site's address, or its label on My sites")
    p.add_argument("--new", metavar="NAME", help="make a new blank app for it, like acme_po_rules")
    p.add_argument("--only", action="append", metavar="WHAT", help="only these: a record type, a kind or a Type/name")
    p.add_argument("--skip", action="append", metavar="WHAT", help="leave these out: a record type, a kind or a Type/name")
    p = cmd("download", cmd_download, "write the server's copy into apps/<app>/", in_app=False)
    p.add_argument("name")
    p.add_argument("--version")
    cmd("check", cmd_check, "the kit's check and the app's own tests")
    cmd("push", cmd_push, "check the folder and upload it as the next draft")
    cmd("pull", cmd_pull, "bring the server's latest draft in and keep your changes")
    p = cmd("add", cmd_add, "add a sample to this app")
    p.add_argument("sample")
    p = cmd("take", lambda a: cmd_add(a, take=True), "take a sample's newer version")
    p.add_argument("sample")
    p = cmd("secret", cmd_secret, "set one of the app's own settings")
    p.add_argument("name")
    p = cmd("secrets", cmd_secrets, "print each connection point's secret on a site")
    p.add_argument("--site", help="the site's address (default: the site you last tried on)")
    p = cmd("try", cmd_try, "install the latest draft on a site and test it")
    p.add_argument("--site", help="any iVendNext site's address, or a label (default: your default site)")
    p.add_argument("--show-wording", action="store_true", help="print the exact wording the install shows")
    p = cmd("sites", cmd_sites, "your company's sites (My sites): list, add, use, label or remove one", in_app=False)
    p.add_argument("action", nargs="?", choices=("add", "use", "label", "remove"),
                   help="add <address>: with a key you made there (asked without echo, or IVN_SITE_KEY and IVN_SITE_SECRET); "
                        "use <address or label>: your default; label <address> \"<label>\": a customer's name and test or "
                        "live; remove <address>: off your list, with its key (ivn remove-site stops an app reaching a site)")
    p.add_argument("target", nargs="?", help="the site's address, or its label")
    p.add_argument("label", nargs="?", help="label: the label, such as \"Acme test\" ('' takes it off)")
    p.add_argument("--label", dest="as_label", metavar="LABEL",
                   help="add: its label at once, such as \"Acme live\" (a customer's live site never joins Try's list)")
    p = cmd("test", cmd_test, "test each connection point again")
    p.add_argument("--local", action="store_true", help="on this laptop, with the test secret in .env.local")
    p = cmd("publish", cmd_publish, "send it to a customer's sites, or list it for every retailer")
    p.add_argument("--to", action="append", metavar="SITE", help="a customer's site address or its label; once per site")
    p.add_argument("--install", action="store_true",
                   help="where you hold the customer site's key (ivn sites add), install it there now, after its words")
    p.add_argument("--public", action="store_true", help="list it for every retailer")
    p.add_argument("--own", action="store_true", help="these sites are your own company's")
    p.add_argument("--plan", choices=("starter", "standard", "managed"))
    cmd("status", cmd_status, "where it stands, and any newer sample version")
    p = cmd("logs", cmd_logs, "what its service logged, newest first")
    p.add_argument("--hours", type=int, default=1)
    p.add_argument("--search")
    p = cmd("rollback", cmd_rollback, "publish an earlier version's content as a new version")
    p.add_argument("version")
    p = cmd("remove-site", cmd_remove_site, "stop sending new versions to a site")
    p.add_argument("site")
    cmd("cancel", cmd_cancel, "stop its service at the month's end")
    p = cmd("handover", cmd_handover, "hand this app to another company")
    p.add_argument("word", help="their company's first word")
    p = cmd("key", cmd_key, "a paid listed app's key for one retailer's site")
    p.add_argument("site")
    p = cmd("token", cmd_token, "make a token for a build server", in_app=False)
    p.add_argument("action", choices=("new",))
    p.add_argument("name")
    p.add_argument("--app", dest="for_app", help="this app only (default: all your company's apps)")
    cmd("package", cmd_package, "write package.zip for your own function host")
    return ap


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # a Windows build server's redirected output: the words hold ⟨ ⟩ and ·
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.version_info[:2] < MIN_PYTHON:
        print(WORDS["old_python"].format(need=".".join(map(str, MIN_PYTHON)), have=platform_python(), path=sys.executable))
        return 1
    try:
        a = parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        return a.fn(a)
    except Stop as e:
        print(terminal(str(e)))
        return 1
    except Offline:
        print(WORDS["no_reach"])
        return 1
    except KeyboardInterrupt:
        print(WORDS["stopped"])
        return 1


if __name__ == "__main__":
    sys.exit(main())
