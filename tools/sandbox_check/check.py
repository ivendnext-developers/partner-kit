#!/usr/bin/env python3
"""sandbox_check — is my sandbox site ready to build on?

Run it with your site's address and an API key of your site's administrator (Desk → your user → API Access →
Generate Keys). Python 3 standard library only; the last check also needs bash, curl and jq, as the request
collection does.

    BASE=https://<your-sandbox-site> KEY=<api key> SECRET=<api secret> python3 tools/sandbox_check/check.py

Each check can fail: the site answers · your key signs in · the POS apps are installed · the demo company · its three
stores, each with one till profile · the integration user · the extension points' record types · the install screen (for `tools/deploy`) · the request
collection's first three files. The last line is the verdict; the exit code is 0 only when every check passes.

  --connect-to HOST:PORT   send the requests to that address and keep the site's own name (a new site whose name has
                           no DNS entry yet)
  --record FILE            write the answers the checks read (they carry no key or secret) to FILE

Three checks read the hosted sandbox's own data: the demo company, its three stores and the integration user. On a
site you made yourself, name your own in the environment (each defaults to the hosted sandbox's value):

    SANDBOX_COMPANY          the company                       (default: Demo Retail)
    SANDBOX_STORE_PREFIX     the start of each store's name    (default: Demo Retail — Store )
    SANDBOX_STORES           how many stores                   (default: 3)
    SANDBOX_INTEGRATION_USER the integration user              (default: integration@demo-retail.example)
    SANDBOX_INTEGRATION_ROLE the integration user's role       (default: Demo Integration)
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

# The hosted sandbox's own data (recipes/hosted_sandbox.md); a builder's own site names its own (Shop.from_env)
COMPANY = "Demo Retail"
STORE_PREFIX = "Demo Retail — Store "
STORES = 3
INTEGRATION_USER = "integration@demo-retail.example"
INTEGRATION_ROLE = "Demo Integration"
APPS = ["ivendnext_pos", "ivendnext_mpos"]
# The record types a builder fills in to use the extension points — the POS installer's POINT_DT, plus the call log
# (a test holds the two lists equal)
POINT_TYPES = ["Retail Extension Subscription", "Retail Desk Action", "Retail Save Rule", "Retail Fiscal Reader",
               "Retail Extension Log"]
COLLECTION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "api", "collection")
FIRST_FILES = ["01_list_items.http", "02_get_item.http", "03_list_warehouses.http"]


class Shop:
    """The data three checks read: the hosted sandbox's by default, or the builder's own from SANDBOX_* variables."""

    def __init__(self, company=COMPANY, store_prefix=STORE_PREFIX, stores=STORES,
                 integration_user=INTEGRATION_USER, integration_role=INTEGRATION_ROLE):
        self.company, self.store_prefix, self.stores = company, store_prefix, stores
        self.integration_user, self.integration_role = integration_user, integration_role

    @classmethod
    def from_env(cls, env):
        """Reads SANDBOX_*; an unset or empty one keeps the hosted sandbox's value. Raises ValueError on a bad count."""
        stores = env.get("SANDBOX_STORES") or str(STORES)
        if not stores.isdigit() or int(stores) < 1:
            raise ValueError(f"SANDBOX_STORES is a whole number of stores, 1 or more, not {stores!r}")
        return cls(env.get("SANDBOX_COMPANY") or COMPANY, env.get("SANDBOX_STORE_PREFIX") or STORE_PREFIX,
                   int(stores), env.get("SANDBOX_INTEGRATION_USER") or INTEGRATION_USER,
                   env.get("SANDBOX_INTEGRATION_ROLE") or INTEGRATION_ROLE)

    @property
    def hosted(self):
        return (self.company, self.store_prefix, self.stores, self.integration_user, self.integration_role) == \
            (COMPANY, STORE_PREFIX, STORES, INTEGRATION_USER, INTEGRATION_ROLE)


def resource(doctype, name=None, **query):
    path = "/api/resource/" + urllib.parse.quote(doctype) + ("/" + urllib.parse.quote(name, safe="") if name else "")
    return path + ("?" + urllib.parse.urlencode({k: json.dumps(v) for k, v in query.items()}) if query else "")


class _SiteHttps(http.client.HTTPSConnection):
    """HTTPS to another address (--connect-to) that still names the SITE to TLS (SNI) and checks the site's certificate.
    The standard connection would name the address it dials, and a good site would fail its certificate check."""

    def __init__(self, host, port, site_name, **kw):
        super().__init__(host, port, **kw)
        self.site_name = site_name

    def connect(self):
        http.client.HTTPConnection.connect(self)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.site_name)


class Site:
    """GET over HTTP(S) with the key; answers are (status, parsed JSON or None)."""

    def __init__(self, base, key, secret, connect_to=None):
        u = urllib.parse.urlsplit(base.rstrip("/"))
        self.https, self.host = u.scheme == "https", u.netloc
        self.target = connect_to or u.netloc
        self.auth = f"token {key}:{secret}"
        self.record = {}

    def _conn(self):
        host, _, port = self.target.partition(":")
        port = int(port) if port else None
        return (_SiteHttps(host, port, self.host.split(":")[0], timeout=60) if self.https
                else http.client.HTTPConnection(host, port, timeout=60))

    def get(self, path, auth=True):
        conn = self._conn()
        headers = {"Host": self.host, "Accept": "application/json", **({"Authorization": self.auth} if auth else {})}
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            status, raw = resp.status, resp.read()
        except OSError as e:
            return 0, {"error": str(e)}
        finally:
            conn.close()
        try:
            body = json.loads(raw or b"null")
        except ValueError:
            body = None
        self.record[path.split("?")[0]] = [status, body]
        return status, body


OLD_RELEASE = "the shop's release has no ivendnext_mpos.api.v1 yet: update its POS app"


def _no_v1(status, body) -> bool:
    """The shop does not know the call (its release predates the iVendNext names): it answers 417
    'Failed to get method', which is not a key or an app problem."""
    return status == 417 and "Failed to get method" in json.dumps(body or {})


def run_checks(site, shop=None):
    """Yields (passed, label, detail) for each check."""
    shop = shop or Shop()
    status, body = site.get("/api/method/ping", auth=False)
    yield status == 200 and (body or {}).get("message") == "pong", "the site answers", f"HTTP {status}"

    status, body = site.get("/api/method/ivendnext_mpos.api.v1.get_logged_user")
    user = (body or {}).get("message")
    detail = OLD_RELEASE if _no_v1(status, body) else f"as {user}" if status == 200 else f"HTTP {status}"
    yield status == 200 and bool(user), "your key signs in", detail

    status, body = site.get("/api/method/ivendnext_mpos.api.v1.get_versions")
    have = set(((body or {}).get("message") or {}) if status == 200 else ())
    missing = [a for a in APPS if a not in have]
    yield (status == 200 and not missing, "the POS apps are installed",
           OLD_RELEASE if _no_v1(status, body) else f"missing {missing}" if missing else "")

    status, _ = site.get(resource("Company", shop.company))
    yield status == 200, "the demo company", f"{shop.company}: HTTP {status}"

    status, body = site.get(resource("Warehouse", fields=["name", "warehouse_name", "company"], limit_page_length=100,
                                     filters=[["company", "=", shop.company], ["is_group", "=", 0]]))
    stores = sorted(w["name"] for w in (body or {}).get("data", [])
                    if w.get("warehouse_name", "").startswith(shop.store_prefix))
    pstatus, pbody = site.get(resource("POS Profile", fields=["name", "warehouse"], limit_page_length=100,
                                       filters=[["company", "=", shop.company], ["disabled", "=", 0]]))
    per_store = {s: [p["name"] for p in (pbody or {}).get("data", []) if p.get("warehouse") == s] for s in stores}
    bad = {s: p for s, p in per_store.items() if len(p) != 1}
    yield (status == 200 and pstatus == 200 and len(stores) == shop.stores and not bad,
           f"{shop.stores} stores, each with one till profile", f"found {len(stores)}" + (f"; profiles {bad}" if bad else ""))

    status, body = site.get(resource("User", shop.integration_user))
    data = (body or {}).get("data") or {}
    roles = sorted(r.get("role") for r in data.get("roles", []))
    yield (status == 200 and data.get("enabled") == 1 and shop.integration_role in roles and "System Manager" not in roles,
           "the integration user", f"HTTP {status}, roles {roles}" if status == 200 else f"HTTP {status}")

    status, body = site.get(resource("DocType", fields=["name"], limit_page_length=50,
                                     filters=[["name", "in", POINT_TYPES]]))
    absent = sorted(set(POINT_TYPES) - {d["name"] for d in (body or {}).get("data", [])})
    yield status == 200 and not absent, "the extension points' record types", f"absent {absent}" if absent else ""

    # the install screen, which `tools/deploy` calls (the POS app from development 87812e14): it names the roles that may install
    status, body = site.get("/api/method/ivendnext_mpos.api.extension_package.holders")
    yield (status == 200 and isinstance((body or {}).get("message"), list), "the install screen (for tools/deploy)",
           "" if status == 200 else f"HTTP {status}: the site's POS app predates the install screen")


def run_collection(base, key, secret, connect_to=None):
    """The collection's own runner (api/collection/run.sh) on its first three files, in a scratch copy."""
    with tempfile.TemporaryDirectory() as tmp:
        for f in ["run.sh", *FIRST_FILES]:
            shutil.copy(os.path.join(COLLECTION, f), tmp)
        env = {**os.environ, "BASE": base.rstrip("/"), "KEY": key, "SECRET": secret, "CURL_HOME": tmp}
        if connect_to:      # curl reads $CURL_HOME/.curlrc: the same redirection as this script's own requests
            with open(os.path.join(tmp, ".curlrc"), "w") as rc:
                rc.write(f'connect-to = "::{connect_to}"\n')
        p = subprocess.run(["bash", os.path.join(tmp, "run.sh")], env=env, capture_output=True, text=True, timeout=300)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith(("PASS", "FAIL", "COLLECTION"))]
    return p.returncode == 0, "; ".join(lines[-4:]) or (p.stderr.strip()[-200:] or f"exit {p.returncode}")


def main(argv=None, out=sys.stdout):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--connect-to")
    ap.add_argument("--record")
    a = ap.parse_args(argv)
    base, key, secret = (os.environ.get(k, "") for k in ("BASE", "KEY", "SECRET"))
    if not (base and key and secret):
        print("set BASE, KEY and SECRET (your site's address and an API key and secret of its administrator)", file=out)
        return 2
    try:
        shop = Shop.from_env(os.environ)
    except ValueError as e:
        print(e, file=out)
        return 2
    if not shop.hosted:
        print(f"Your own shop's data: company {shop.company!r}, {shop.stores} stores named {shop.store_prefix!r}…, "
              f"integration user {shop.integration_user!r} with role {shop.integration_role!r}", file=out)
    site = Site(base, key, secret, a.connect_to)
    results = list(run_checks(site, shop))
    ok, detail = run_collection(base, key, secret, a.connect_to)
    results.append((ok, "the request collection's first three files", detail))
    for ok, label, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""), file=out)
    if a.record:
        with open(a.record, "w") as fh:
            json.dump(site.record, fh, indent=1, ensure_ascii=False)
    failed = [label for ok, label, _ in results if not ok]
    print(f"SANDBOX CHECK {'GREEN' if not failed else 'RED'} — {len(results) - len(failed)} of {len(results)} passed"
          + (f"; failed: {', '.join(failed)}" if failed else ""), file=out)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
