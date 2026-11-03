#!/usr/bin/env python3
"""S1 — the *Warranty* till key on its own, for CitiXsys hosting (standard library only).

    POST /point/warranty      the till key's call (signed by the shop)   →  200 {"message": {...}}
    GET  /health              200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses. It is the till key alone, as S2's hosted form is: it READS the retailer's own terms (``PP WRC Warranty
Term``) and the sale's item groups with the app's own user, and writes nothing. ``app.py`` beside it is the whole S1 service
for your own server: it registers a warranty per serial number from a webhook, in a store of its own.

When the app has no user's key yet, the shop refuses that key, or the shop cannot be read in time, the cashier is told so
in words (200, a warning message), never a guess.

MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the app's id in the App library, with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE. Each shop
                       connects itself after its install and hands over the till key's secret and the key of the app's own
                       user ("user:<email>"); every call names its shop (X-iVendNext-Site).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path[:0] = [SAMPLE, HERE]
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import core  # noqa: E402  (the sample's pure core, unchanged)
import function  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402
from tenant import Tenant, TenantError  # noqa: E402  (the sample's only door into iVendNext)

ROUTE, KEY = "/point/warranty", "warranty"     # the manifest's remote_keys[].key; its secret is "<app>:<key>"
TERM = "PP WRC Warranty Term"
BODY_MAX, SKEW_S, READ_S, TERMS_MAX = 64 * 1024, 300, 1.2, 1000     # two reads, inside the till's 3 seconds
TITLE = "Warranty"
NOT_SET_UP = ("Warranty terms is not set up yet: no key from this site has reached it. Ask your manager to press Connect "
              "again on the app.")
CANNOT_READ = "The warranty terms cannot be read right now. Try again in a moment."
NO_RIGHTS = "The app's user may not read items. Ask your manager to give its role read on Item."


def verified(secrets: list[bytes], headers, raw: bytes) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:
        return False
    return any(hmac.compare_digest(base64.b64encode(hmac.new(s, ts.encode() + b"." + raw, hashlib.sha256).digest()),
                                   sig.encode()) for s in secrets)


def terms_of(rows: list[dict]) -> dict:
    """The retailer's term rows, in the shape ``core`` reads."""
    out = {"items": {}, "groups": {}}
    for r in rows:
        if r.get("applies_to") == "Item" and r.get("item"):
            out["items"][r["item"]] = r.get("months")
        elif r.get("applies_to") == "Item Group" and r.get("item_group"):
            out["groups"][r["item_group"]] = r.get("months")
    return out


def _warning(body: str) -> dict:
    return {"message": {"title": TITLE, "body": body, "level": "warning"}}


class Service:
    def __init__(self, conf: dict, store=None, tenant_of=None):
        self.app = oneshop.value(conf, oneshop.MANY)
        if not self.app:
            raise SystemExit("this form is for many shops: set IVN_LIBRARY_APP. For one shop run service/app.py")
        self.store = store or shops.open_store(conf)
        self.tenant_of = tenant_of or (lambda url, key, secret: Tenant(url, key, secret, timeout=READ_S))

    def tenant(self, record: dict):
        users = sorted(k for k in (record.get("secrets") or {}) if k.startswith("user:"))
        key, _, secret = (record["secrets"][users[0]] if users else "").partition(":")
        return self.tenant_of(record["url"], key, secret) if key and secret else None

    def answer(self, headers, raw: bytes) -> tuple[int, dict]:
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, f"{self.app}:{KEY}")
        if not secrets or not verified(secrets, headers, raw):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(KEY)
        try:
            context = json.loads(raw)["context"]
            if not isinstance(context, dict):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return 400, {"error": "bad request"}
        codes = sorted({line["item_code"] for line in context.get("lines") or []
                        if isinstance(line, dict) and line.get("item_code")})
        door = self.tenant(record)
        if not door:
            return 200, _warning(NOT_SET_UP)
        try:
            rows = door.list(TERM, ["applies_to", "item", "item_group", "months"], [], "modified asc", TERMS_MAX)
            terms = terms_of(rows)
            rest = [c for c in codes if c not in terms["items"]]    # an item's own term needs no group, and no right on Item
            terms["item_group"] = door.item_groups(rest) if rest else {}
        except TenantError as e:
            return 200, _warning(NO_RIGHTS if "403" in str(e) else CANNOT_READ)
        return 200, core.warranty_answer(context, terms)

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > BODY_MAX:
            return 413, {"error": "too large"}
        if path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.answer(headers, raw) if path == ROUTE else (404, {"error": "not found"})


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line (never the body, the context, a secret or a signature)."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    print(json.dumps({"request": (headers.get("X-iVendNext-Request-Id") or "-")[:40], "route": path[:40], "status": code,
                      "ms": int((time.monotonic() - t0) * 1000)}), flush=True)
    return code, out


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b): settings from the environment.
lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle)
