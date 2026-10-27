#!/usr/bin/env python3
"""S22 — the member key, the till's button that shows the customer's plan, cash-back balance and next tier (a remote
till key), and Member cash, the cash back spent at the till (a wallet, ``service/wallet.py``). Standard library only.

    POST /lyl/member       the shop's signed press  →  200 {"message": {"title", "body", "level"}}
    POST /paygw/1/<verb>   the shop's payment app asks the wallet; signed with PP_WALLET_SECRET (off until it is set)
    GET  /health

The press is signed with the till key's own secret (handed back once at install as ``pp_lyl:pp_lyl_member``): it is
the shop calling out, so it uses no API key and no licence. The service reads the member's rows with the ONE
integration user's key (PP_KEY / PP_SECRET) to answer.

The wallet's route and its signature check are adapted from CitiXsys's private reference implementation @ 74c99d5; a
defect here may be a defect there — report it on the Partner feedback forms.

    python3 service/app.py service/.env.local      # ONE SHOP: PP_KEY_SECRET, PP_PORT (8152), PP_BASE, PP_KEY, PP_SECRET,
                                                   # PP_STATE; the wallet: PP_WALLET_SECRET, PP_WALLET_SITE, PP_WALLET_MERCHANT

MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b): set IVN_LIBRARY_APP
(the App library's id, ivendnext_lyl) and a store (IVN_SHOPS_TABLE on CitiXsys hosting, else IVN_SHOPS_FILE). Each shop
connects itself after its install (POST /ivendnext/connect) and hands over the member key's secret
("<app>:<app>_member") and its integration user's key ("user:<email>": "<api key>:<api secret>"). Every press names its
shop (X-iVendNext-Site) and is checked with THAT shop's secret, then answered from that shop's own records; the feed
worker runs beside it, one poll per connected shop (worker.py). The shop's settings stay in the shop (its
``… Settings`` record, read with its key). LYL_PREFIX names the record types (PP LYL; IVENDNEXT LYL for the library's
app). Member cash stays ONE shop's (PP_WALLET_*): the payments app calls it with the connector's own id and secret, not
the shop's site (README, Bounds).

On CitiXsys hosting, many shops run as a FUNCTION (app.json "runs": "function", "schedule"; ``lambda_handler`` below): a
press is one call, and each scheduled call is one feed pass of the shops it can claim, with each shop's daily jobs taken
once a day by whichever call claims that day first. Nothing is billed while no shop presses or has a sale to read.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import loyalty  # noqa: E402
import receipts  # noqa: E402
import shops  # noqa: E402
import money  # noqa: E402
import wallet  # noqa: E402
import worker  # noqa: E402
from shop import Shop, ShopError  # noqa: E402

SKEW_S, BODY_MAX = 300, 256 * 1024
HEALTH_GRACE_S = 180   # many shops: /health is 503 once no feed pass has finished for this long
WALLET_PREFIX, WALLET_BODY_MAX = "/paygw/1/", 64 * 1024
CLAIM_STALE_S = 150    # above the function's timeout (app.json "timeout": 120): a pass stopped by it frees its shops


def verify(timestamp, signature, raw: bytes, secret: str, now=None) -> str:
    """``""`` when the press is the shop's: base64 HMAC-SHA256 of ``<timestamp>.<raw body>`` (as in samples S16, S18)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    return "" if hmac.compare_digest(want, sig.encode()) else "the signature does not match"


def _plain(text: str, n: int) -> str:
    text = "".join(ch for ch in str(text) if ch.isprintable()).replace("<", "").replace(">", "")
    return text if len(text) <= n else text[: n - 1] + "…"


def member_key(t, s: loyalty.Settings, body: dict, today: str) -> dict:
    customer = ((body or {}).get("context") or {}).get("customer")
    if not customer or customer in s.walk_in:
        return json.loads(json.dumps(NO_MEMBER))
    m = t.get(loyalty.MEMBER, customer)
    if not m:
        return {"message": {"title": "Not a member yet", "body": "They join at their first sale.", "level": "info"}}
    plan = s.plan(m.get("plan"))
    credited, pending = loyalty.balance(t, customer)
    text = f"Cash back {s.money(credited)}" + (f" ({s.money(pending)} pending)." if pending else ".")
    nxt = next((p for p in sorted(s.plans.values(), key=lambda p: p.get("rank") or 0)
                if (p.get("rank") or 0) > (plan.get("rank") or 0)), None)
    if m.get("status") == "Inactive":            # the daily moves skip an inactive member: promise none
        text += " Plan moves are stopped for this member."
    elif nxt:
        gap = max(money.D(nxt.get("spend_threshold")) - loyalty.spend(t, s, customer, today), money.D(0))
        text += f" {s.money(gap)} more reaches {nxt['name']} (spend over the last {s.window_days} days)."
    else:
        text += " The top plan."
    disc = plan.get("discount_percent") or 0
    title = f"{m.get('plan')} member" + (f" · {disc:g}% off" if disc else "")
    return {"message": {"title": _plain(title, 60), "body": _plain(text, 280), "level": "success"}}


NO_MEMBER = {"message": {"title": "No member on this sale", "body": "Add the customer to the sale, then press again.",
                         "level": "info"}}


def use_prefix(prefix: str):
    """The record types' prefix, one per service: ``PP LYL`` (the sample) or ``IVENDNEXT LYL`` (the library's app)."""
    loyalty.LEDGER, loyalty.MEMBER, loyalty.PLAN, loyalty.SETTINGS, loyalty.BALANCE = (
        f"{prefix} {n}" for n in ("Ledger", "Member", "Plan", "Settings", "Balance"))
    receipts.PENDING, receipts.VERIFIED, receipts.VERIFY = (f"{prefix} {n}" for n in ("Pending Verification", "Verified", "Verify"))
    wallet.LEDGER = loyalty.LEDGER


def api_credentials(record: dict) -> tuple[str, str, str]:
    """(address, key, secret): the integration user's key the shop handed over at connect ("user:<email>")."""
    users = sorted(k for k in record.get("secrets") or {} if k.startswith("user:"))
    if not users or ":" not in record["secrets"][users[0]]:
        raise ShopError(0, "the shop has not handed over its integration user's key")
    key, secret = record["secrets"][users[0]].split(":", 1)
    return record["url"], key, secret


def shop_client(record: dict) -> Shop:
    return Shop(*api_credentials(record))


class Service:
    def __init__(self, conf: dict, shop=None, store=None, client=None, keys=None, scheduled: bool = False):
        self.conf, self.client, self.keys, self.started = conf, client or shop_client, keys, time.monotonic()
        self.scheduled = scheduled          # a function: each scheduled call is its own pass, logged as it ends
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        if conf.get("LYL_PREFIX"):
            use_prefix(conf["LYL_PREFIX"].strip())
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
            self.secret_name = f"{self.app}:{self.app}_member"
        else:                                           # one shop, from the settings
            self.secret = conf["PP_KEY_SECRET"]
            self.t = shop or Shop(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"])
        loyalty.LOCKS = os.path.join(conf.get("PP_STATE") or os.path.join(HERE, "state"), "locks")

    def caller(self, headers, raw: bytes):
        """(a way to open the shop's record API, "") for a press this service may answer, else (None, why)."""
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not self.app:
            return (lambda: self.t), verify(ts, sig, raw, self.secret)
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, self.secret_name)
        if not secrets:
            return None, "the signature does not match"         # the same words: an unknown site is not told apart
        if all(verify(ts, sig, raw, s.decode()) for s in secrets):
            return None, "the signature does not match"
        return (lambda: self.client(record)), ""

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            opened, why = self.caller(headers, raw)
        except Exception as e:        # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": f"unavailable ({type(e).__name__})"}
        if why:
            return 401, {"error": why}
        try:
            body = json.loads(raw)
            if not ((body or {}).get("context") or {}).get("customer"):
                return 200, json.loads(json.dumps(NO_MEMBER))     # nothing to read from the shop
            t = opened()
            return 200, member_key(t, loyalty.Settings.load(t), body, datetime.date.today().isoformat())
        except ValueError as e:
            return 400, {"error": str(e)}
        except ShopError as e:     # the shop could not be read: the till says the button could not finish
            return 503, {"error": f"the shop could not be read ({e.status})"}

    def wallet_answer(self, verb: str, headers, raw: bytes) -> tuple[int, dict]:
        """The wallet's routes answer only once the shop's Remote Connector record exists and its secret is here."""
        secret = self.conf.get("PP_WALLET_SECRET", "")
        if not secret or secret == "UNSET" or self.app:     # Member cash is one shop's (the module's docstring)
            return 404, {"error": "not found"}
        if len(raw) > WALLET_BODY_MAX:
            return 413, {"error": "too large"}
        why = verify(headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature"), raw, secret)
        if why:
            return 401, {"error": why}
        try:
            body = json.loads(raw or b"{}")
            s = loyalty.Settings.load(self.t) if verb not in ("declaration", "induce", "settle") else None
            return wallet.Wallet(self.t, self.conf).answer(verb, body, s)
        except (ValueError, KeyError, TypeError) as e:
            return 422, {"error": type(e).__name__}
        except ShopError as e:        # the shop could not be read or written: no answer the shop may act on
            return 503, {"error": f"the shop could not be read ({e.status})"}
        except TimeoutError:          # past the wallet's write deadline: nothing written, the shop asks status later
            return 503, {"error": "too late: nothing was taken"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """One request, for the web server and the function alike."""
    if method == "POST":
        if len(raw) > BODY_MAX:
            return 413, {"error": "too large"}
        if svc.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(svc.store, svc.app, path, headers, raw, svc.keys)
        if path.startswith(WALLET_PREFIX):
            return svc.wallet_answer(path[len(WALLET_PREFIX):], headers, raw)
        return svc.press(headers, raw) if path == "/lyl/member" else (404, {"error": "not found"})
    if path != "/health":
        return 404, {"error": "not found"}
    if (svc.app and not svc.scheduled and time.monotonic() - svc.started > HEALTH_GRACE_S
            and time.monotonic() - worker.HEARTBEAT[0] > HEALTH_GRACE_S):
        return 503, {"ok": 0, "why": "the feed worker has not finished a pass"}   # restart me
    return 200, {"ok": 1}


def scheduled(svc: Service, name: str, now: datetime.datetime | None = None) -> dict:
    """One scheduled pass (the function's worker): the shops this call claims, each to its end (the feed, then its daily
    jobs if this call is the first to claim that day), then their claims freed. A shop stuck past the function's
    timeout ends the call; its claim goes stale in CLAIM_STALE_S."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    store = function.Claimed(svc.store, CLAIM_STALE_S)
    state = svc.conf.get("PP_STATE") or os.path.join(HERE, "state")
    out = worker.pass_all(store, state, function.OncePerDay(svc.store, now), now=now, opener=worker.open_shop,
                          deadline=900.0)
    store.release(out)
    return out


lambda_handler = function.entry(lambda: Service(dict(os.environ), scheduled=True), handle, scheduled)


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > BODY_MAX:
                return self._send(413, {"error": "too large"})
            self._send(*handle(svc, "POST", self.path, self.headers, self.rfile.read(n)))

        def do_GET(self):
            self._send(*handle(svc, "GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):
            sys.stderr.write("s22 %s\n" % (fmt % args))   # the request line only: no header, no body, no secret

    return Handler


if __name__ == "__main__":
    import threading
    conf = worker.env(sys.argv[1]) if sys.argv[1:] else dict(os.environ)      # hosting: the environment
    svc = Service(conf)
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8152)), make_handler(svc))
    if svc.app:                                         # many shops: the feed worker runs beside the key
        threading.Thread(target=worker.serve_all, args=(svc.store, conf), daemon=True).start()
    print(f"s22 member key on :{srv.server_port}" + (f", many shops ({svc.app})" if svc.app else ""), flush=True)
    srv.serve_forever()
