#!/usr/bin/env python3
"""S13 — a standalone partner portal: "Sign in with iVendNext", then the person's own shop records. Python 3.9+, standard library only.

A small web app on the partner's OWN server. A shop's user opens it, signs in with their own iVendNext account (authorisation
code + PKCE, the recipe ``recipes/sign_in.md``), and sees only what THEIR permissions in the shop allow: the portal asks the shop
for the records with the person's own token, so the shop decides what comes back — a store user gets their store's sales and no
other store's, a user with no right gets nothing.

    PORTAL_SHOP=https://shop.example PORTAL_CLIENT_ID=… PORTAL_CLIENT_SECRET=… PORTAL_REDIRECT=https://portal.example/callback python3 portal.py
    optional: PORTAL_PORT (8141) · PORTAL_HOST (127.0.0.1) · PORTAL_SECURE=1 (the sign-in cookie is sent over HTTPS only) · PORTAL_KIT (a
    folder holding ivn-kit.css; default: next to this file, else the kit's own kit/design)

Routes
    GET  /          the sign-in page, or the person's records (a table with a link into the Desk record)
    GET  /login     starts the sign-in: a fresh verifier + state kept on THIS server, the browser sent to the shop
    GET  /callback  the shop's answer: the state must be the one sent to THIS browser, once; the code is exchanged WITH the verifier
    POST /logout    revokes the token at the shop and forgets the session
    GET  /ivn-kit.css, /ivn-kit.js   the kit's files (the pages load the kit from here: tokens only, no colour or font of their own)

What it keeps, and where: the token lives in the portal's memory, never in a page, a cookie or a log; the browser holds only a random
session id (HttpOnly, SameSite=Lax). A restart signs everyone out. One process, one server: this is a sample, not a session store.
The client secret stays on this server and goes only to the shop, with the code exchange and the revoke. The shop's token endpoint
does not check it on this build, so PKCE is what protects the code today; the portal sends it anyway, so it keeps working the day the
shop starts checking it.
A sign-in lasts as long as the shop's token (an hour on this build; SESSION_SECONDS is only the portal's own ceiling), and the token is
the person's whole account in the shop, writes included: the portal only reads, but whoever holds its memory holds every signed-in
person's account until their token ends. Disabling a person in the shop does not end a token already issued: revoke their tokens too.
"""

from __future__ import annotations

import base64
import decimal
import hashlib
import hmac
import html
import http.client
import http.cookies
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
O = "/api/method/frappe.integrations.oauth2"
COOKIE = "pp_sid"
MAX_SESSIONS = 1000          # pending and signed-in sessions together; at the cap the expired go first, then the oldest PENDING one (a flood of /login cannot sign real users out)
PENDING_SECONDS = 600        # a sign-in must come back within ten minutes
SESSION_SECONDS = 8 * 3600
LIST_LIMIT = 20
INVOICE_FIELDS = ["name", "posting_date", "customer", "grand_total", "currency", "pos_profile", "status"]
MINOR_UNITS = {**dict.fromkeys("BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF".split(), 0),
               **dict.fromkeys("BHD IQD JOD KWD LYD OMR TND".split(), 3), "CLF": 4, "UYW": 4}   # ISO 4217; every other currency uses 2
HEADERS = [("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff"),
           ("Content-Security-Policy", "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")]


class Response:
    def __init__(self, status=200, body=b"", headers=None, ctype="text/html; charset=utf-8"):
        self.status = status
        self.body = body if isinstance(body, bytes) else body.encode()
        self.headers = [("Content-Type", ctype)] + HEADERS + list(headers or [])


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):           # never follow a redirect with a token
        return None


def http_to_shop(base):
    """The default shop caller: (status, parsed JSON or {}) — status 0 when the shop cannot be reached."""
    opener = urllib.request.build_opener(_NoRedirect)

    def call(method, path, token=None, form=None):
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(base + path, data=data, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with opener.open(req, timeout=10) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            return 0, {}
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}
        return status, body if isinstance(body, dict) else {}
    return call


# ── pages: the kit's classes only ─────────────────────────────────────────────────────────────────────────────
def page(title, inner, signed_in=False):
    out = ('<form method="post" action="/logout"><button class="ivn-btn ivn-btn-sm" type="submit">Sign out</button></form>'
           if signed_in else "")
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{esc(title)}</title>\n<link rel="stylesheet" href="ivn-kit.css">\n</head>\n<body class="ivn">\n'
            '<header class="ivn-card"><div class="ivn-container ivn-row"><strong>Partner portal</strong>'
            f'<span class="ivn-spacer"></span>{out}</div></header>\n'
            f'<main class="ivn-container ivn-stack">\n{inner}\n</main>\n</body>\n</html>\n')


def signed_out_page(note=None):
    banner = f'<div class="ivn-banner" role="status">{esc(note)}</div>' if note else ""
    return page("Sign in", f'{banner}<div><h1 class="ivn-title">Your shop, from here</h1>'
                '<p class="ivn-muted">Sign in with your iVendNext account. You will see what your own account may see in the shop, and nothing more.</p></div>'
                '<div><a class="ivn-btn ivn-btn-primary" href="/login">Sign in with iVendNext</a></div>')


def error_page(title, text, back=True, signed_in=False):
    link = '<a class="ivn-btn ivn-btn-sm" href="/">Back</a>' if back else ""
    return page(title, f'<section class="ivn-error-state" role="alert"><div class="ivn-error-title">{esc(title)}</div><p>{esc(text)}</p>{link}</section>', signed_in)


def money(value, currency):
    """An amount as people read it: the currency's own decimals and a thousands separator, from Decimal(str(value)), never float arithmetic."""
    try:
        places = MINOR_UNITS.get(currency or "", 2)
        amount = decimal.Decimal(str(value)).quantize(decimal.Decimal(1).scaleb(-places), rounding=decimal.ROUND_HALF_UP)
        text = f"{amount:,.{places}f}"
    except (decimal.InvalidOperation, ValueError):        # not a number (None, text): shown as sent, escaped by the caller
        text = "" if value is None else str(value)
    return f"{text} {currency or ''}".strip() if text else ""


def records_page(profile, rows, desk):
    who = esc(profile.get("name") or profile.get("email") or "")
    signed = f"Signed in as {who}. " if who else "Signed in. "
    if not rows:
        body = ('<section class="ivn-card ivn-empty"><div class="ivn-empty-title">No sales to show</div>'
                '<p>Nothing in your store yet, or nothing your account may see.</p></section>')
    else:
        trs = "".join(
            '<tr><td><a href="{href}">{name}</a></td><td>{date}</td><td>{cust}</td><td>{store}</td><td class="ivn-num">{total}</td>'
            '<td><span class="ivn-pill">{status}</span></td></tr>'.format(
                href=esc(f"{desk}/app/pos-invoice/{urllib.parse.quote(str(r.get('name', '')), safe='')}"), name=esc(r.get("name")),
                date=esc(r.get("posting_date")), cust=esc(r.get("customer")), store=esc(r.get("pos_profile")),
                total=esc(money(r.get("grand_total"), r.get("currency"))), status=esc(r.get("status")))
            for r in rows)
        body = ('<section class="ivn-card"><div class="ivn-table-wrap"><table class="ivn-table"><thead><tr><th>Sale</th><th>Date</th><th>Customer</th>'
                f'<th>Store</th><th class="ivn-num">Total</th><th>Status</th></tr></thead><tbody>{trs}</tbody></table></div></section>')
    return page("Your sales", f'<div><h1 class="ivn-title">Your sales</h1><p class="ivn-muted">{signed}The latest {LIST_LIMIT}, as your account sees them.</p></div>{body}',
                signed_in=True)


class Portal:
    def __init__(self, conf, http=None, clock=time.time):
        self.shop = conf["PORTAL_SHOP"].rstrip("/")
        self.client_id, self.client_secret, self.redirect = conf["PORTAL_CLIENT_ID"], conf["PORTAL_CLIENT_SECRET"], conf["PORTAL_REDIRECT"]
        self.secure = conf.get("PORTAL_SECURE") == "1" or self.redirect.startswith("https://")      # an HTTPS portal never sends its cookie in the clear
        self.cookie_name = "__Host-" + COOKIE if self.secure else COOKIE                          # the browser then refuses a cookie planted from a sibling address
        self.lock = threading.RLock()                                                              # the session store is shared by the server's threads
        self.kit = conf.get("PORTAL_KIT") or (HERE if os.path.isfile(os.path.join(HERE, "ivn-kit.css")) else os.path.join(HERE, "..", "..", "kit", "design"))
        self.http, self.clock, self.sessions = http or http_to_shop(self.shop), clock, {}

    # sessions: {sid: {"made", "state", "verifier", "token"}}
    def _expired(self, s):
        return self.clock() - s["made"] > (SESSION_SECONDS if s.get("token") else PENDING_SECONDS)

    def _drop(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def _new_session(self, **fields):
        with self.lock:
            for k in [k for k, v in self.sessions.items() if self._expired(v)]:
                del self.sessions[k]
            while len(self.sessions) >= MAX_SESSIONS:
                pool = [k for k, v in self.sessions.items() if not v.get("token")] or list(self.sessions)
                del self.sessions[min(pool, key=lambda k: self.sessions[k]["made"])]
            sid = secrets.token_urlsafe(32)
            self.sessions[sid] = {"made": self.clock(), **fields}
            return sid

    def _rotate(self, sid):
        """A new session id at sign-in: an id planted in the browser before the sign-in is worth nothing after it."""
        with self.lock:
            if sid not in self.sessions:                           # dropped while the shop answered (evicted, or a second callback)
                return None
            new = secrets.token_urlsafe(32)
            self.sessions[new] = self.sessions.pop(sid)
            return new

    def _session(self, cookie):
        morsel = http.cookies.SimpleCookie(cookie or "").get(self.cookie_name)
        sid = morsel.value if morsel else None
        with self.lock:
            s = self.sessions.get(sid)
            if s is None:
                return None, None
            if self._expired(s):
                del self.sessions[sid]
                return None, None
            return sid, s

    def _cookie(self, sid, gone=False):
        return ("Set-Cookie", f"{self.cookie_name}={'' if gone else sid}; Path=/; HttpOnly; SameSite=Lax" + ("; Secure" if self.secure else "") + ("; Max-Age=0" if gone else ""))

    def handle(self, method, path, query=None, cookie=None):
        query = query or {}
        if path in ("/ivn-kit.css", "/ivn-kit.js") and method == "GET":
            return self._static(path[1:])
        if path == "/login" and method == "GET":
            return self._login(cookie)
        if path == "/callback" and method == "GET":
            return self._callback(query, cookie)
        if path == "/logout":
            return self._logout(cookie) if method == "POST" else Response(405, "use the Sign out button", [("Allow", "POST")], "text/plain")
        if path == "/" and method == "GET":
            return self._home(cookie)
        return Response(404, "not found", ctype="text/plain")

    def _static(self, name):
        f = os.path.join(self.kit, name)
        if not os.path.isfile(f):
            return Response(404, "not found", ctype="text/plain")
        return Response(200, open(f, "rb").read(), ctype="text/css" if name.endswith(".css") else "text/javascript")

    def _login(self, cookie=None):
        _, s = self._session(cookie)
        if s and s.get("token"):                                   # already signed in: a link to /login (forged or not) signs nobody out
            return Response(302, "", [("Location", "/")])
        verifier, challenge = pkce()
        state = secrets.token_urlsafe(24)
        sid = self._new_session(state=state, verifier=verifier)
        q = urllib.parse.urlencode({"client_id": self.client_id, "response_type": "code", "redirect_uri": self.redirect, "scope": "openid all",
                                    "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
        return Response(302, "", [("Location", f"{self.shop}{O}.authorize?{q}"), self._cookie(sid)])

    def _callback(self, query, cookie):
        sid, s = self._session(cookie)
        with self.lock:                                            # check and spend in one step: two callbacks at once cannot both pass
            pending, verifier = (s.get("state"), s.get("verifier")) if s else (None, None)
            if not (pending and verifier and hmac.compare_digest(pending.encode(), (query.get("state") or "").encode())):
                return Response(400, error_page("Sign-in could not be completed", "This sign-in was not started from this browser, or it has already been used. Please start again."))
            s.pop("state", None)                                   # a state is spent by the callback that carries it, whatever follows
            s.pop("verifier", None)
        if query.get("error") or not query.get("code"):
            self._drop(sid)
            return Response(403, error_page("The shop did not allow the sign-in", "Your account may not use this portal. Ask the shop's administrator."), [self._cookie(sid, gone=True)])
        code, tok = self.http("POST", f"{O}.get_token", form={"grant_type": "authorization_code", "code": query["code"], "redirect_uri": self.redirect,
                                                              "client_id": self.client_id, "client_secret": self.client_secret, "code_verifier": verifier})
        if code != 200 or not tok.get("access_token"):
            self._drop(sid)
            return Response(502, error_page("Sign-in failed", "The shop did not accept the sign-in. Please try again."), [self._cookie(sid, gone=True)])
        s["token"], s["made"] = tok["access_token"], self.clock()
        new = self._rotate(sid)
        if new is None:                                            # no session holds this token any more: revoke it, never leave it live
            self._revoke(tok["access_token"])
            return Response(400, error_page("Sign-in could not be completed", "This sign-in was not started from this browser, or it has already been used. Please start again."))
        return Response(302, "", [("Location", "/"), self._cookie(new)])

    def _revoke(self, token):
        self.http("POST", f"{O}.revoke_token", form={"token": token, "client_id": self.client_id, "client_secret": self.client_secret})

    def _logout(self, cookie):
        sid, s = self._session(cookie)
        if s and s.get("token"):
            self._revoke(s["token"])
        self._drop(sid)
        return Response(302, "", [("Location", "/"), self._cookie(sid or "", gone=True)])

    def _home(self, cookie):
        sid, s = self._session(cookie)
        if not s or not s.get("token"):
            return Response(200, signed_out_page())
        token = s["token"]
        q = urllib.parse.urlencode({"fields": json.dumps(INVOICE_FIELDS), "order_by": "posting_date desc, creation desc", "limit_page_length": LIST_LIMIT})
        code, body = self.http("GET", f"/api/resource/POS%20Invoice?{q}", token=token)
        if code == 401:                                            # revoked or expired at the shop
            self._drop(sid)
            return Response(200, signed_out_page("Your sign-in has ended. Please sign in again."), [self._cookie(sid, gone=True)])
        if code == 403:                                            # the shop's own answer: this account may not read sales
            return Response(200, error_page("You are not allowed to see sales", "Your account is not allowed to see sales in this shop. If you need to, ask the shop's administrator.", back=False, signed_in=True))
        if code != 200:
            return Response(502, error_page("The shop did not answer", "The shop could not be reached just now. Please try again in a moment.", signed_in=True))
        _, profile = self.http("GET", f"{O}.openid_profile", token=token)
        return Response(200, records_page(profile, body.get("data") or [], self.shop))


def make_handler(portal):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10
        server_version, sys_version = "portal", ""             # no software name or version in any response

        def _go(self, method):
            u = urllib.parse.urlparse(self.path)
            query = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if method == "POST":                                   # the sign-out form carries nothing: drain and ignore it
                try:
                    self.rfile.read(max(0, min(int(self.headers.get("Content-Length") or 0), 4096)))
                except ValueError:
                    pass
            r = portal.handle(method, u.path, query, self.headers.get("Cookie"))
            self.send_response(r.status)
            for k, v in r.headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(r.body)))
            self.end_headers()
            self.wfile.write(r.body)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, *a):                                 # no access log: a URL here would carry a code
            pass
    return Handler


def main():
    conf = {k: os.environ[k] for k in ("PORTAL_SHOP", "PORTAL_CLIENT_ID", "PORTAL_CLIENT_SECRET", "PORTAL_REDIRECT")}
    conf.update({k: os.environ[k] for k in ("PORTAL_SECURE", "PORTAL_KIT") if k in os.environ})
    srv = ThreadingHTTPServer((os.environ.get("PORTAL_HOST", "127.0.0.1"), int(os.environ.get("PORTAL_PORT", "8141"))), make_handler(Portal(conf)))
    print(f"portal on {srv.server_address}", file=sys.stderr, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
