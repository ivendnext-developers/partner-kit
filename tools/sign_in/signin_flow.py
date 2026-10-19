"""signin_flow.py — the partner app's side of "Sign in with iVendNext": authorisation code + PKCE (S256), standard
library only. The reference for recipes/sign_in.md, and our test bench's check.

A partner app: (1) makes a random verifier and its S256 challenge and a random state; (2) sends the person's browser to
the shop's authorize address; (3) the person signs in to THEIR OWN account and allows the app; (4) the shop redirects back
with a code and the state; (5) the app checks the state and exchanges the code WITH THE VERIFIER for a token; (6) every
call it then makes carries the token and runs with that person's permissions, nothing more.
Here a script plays the person's browser (it signs in with the persona's password and presses Allow).
"""
import base64
import hashlib
import http.cookiejar
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("IVN_BASE", "https://your-sandbox.example")   # the shop to sign in to: set IVN_BASE
APP = "PP Sign-in Sample"            # the OAuth client's app name: the consent page must name it
O = "/api/method/frappe.integrations.oauth2"


def pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def browser():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)


def call(opener, method, path, data=None, headers=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers or {})
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


def authorize(br, client_id, redirect, challenge, state, method="S256"):
    """The person's browser: authorize (the Allow/Deny page), then Allow (the page's own success link)."""
    q = {"client_id": client_id, "response_type": "code", "redirect_uri": redirect, "scope": "openid all",
         "state": state}
    if challenge:
        q |= {"code_challenge": challenge, "code_challenge_method": method}
    st, _, page = call(br, "GET", f"{O}.authorize?" + urllib.parse.urlencode(q))
    st2, hdr, _ = call(br, "GET", f"{O}.approve?" + urllib.parse.urlencode(q))
    loc = hdr.get("Location", "")
    got = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    return {"consent_page": st, "consent_shown": APP in page and "allow" in page.lower(), "approve_status": st2,
            "redirected_to": loc.split("?")[0], "code": (got.get("code") or [None])[0],
            "state_back": (got.get("state") or [None])[0]}


def exchange(client_id, redirect, code, verifier=None, secret=None):
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect, "client_id": client_id}
    if verifier is not None:
        data["code_verifier"] = verifier
    if secret is not None:
        data["client_secret"] = secret
    st, _, body = call(urllib.request.build_opener(NoRedirect), "POST", f"{O}.get_token", data)
    try:
        return st, json.loads(body)
    except ValueError:
        return st, {"raw": body[:200]}


def main():
    T = os.environ["SIGNIN_STATE_DIR"]   # our test bench: its secrets/ and runs/ folders
    sec = json.load(open(f"{T}/secrets/setup.local.json"))
    cid = sec["signin_client"]["client_id"]
    who = os.environ.get("PP_PERSONA", "associate@demo-retail.example")
    pw = sec["personas"][who]["password"]
    redirect = json.load(open(f"{T}/runs/l4_signin_setup.json"))["client"]["redirect"]
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f" — {json.dumps(detail, default=str)[:300]}"))

    def signed_in():
        br = browser()
        st, _, _ = call(br, "POST", "/api/method/login", {"usr": who, "pwd": pw})
        return br, st

    # 1. a guest is sent to sign in first
    st, hdr, _ = call(browser(), "GET", f"{O}.authorize?" + urllib.parse.urlencode(
        {"client_id": cid, "response_type": "code", "redirect_uri": redirect, "scope": "openid all", "state": "s"}))
    check("a person not signed in is sent to the shop's own sign-in page first", st in (301, 302, 303) and
          "/login" in hdr.get("Location", ""), [st, hdr.get("Location", "")[:80]])
    # 2. the happy path
    br, st = signed_in()
    check("the person signs in to their own account", st == 200, st)
    v, c = pkce()
    state = secrets.token_urlsafe(16)
    a = authorize(br, cid, redirect, c, state)
    check("the Allow/Deny page is shown to the person", a["consent_page"] == 200 and a["consent_shown"],
          {k: v for k, v in a.items() if k != "code"})
    check("Allow redirects back to the app with a code and the SAME state", a["code"] and a["state_back"] == state
          and a["redirected_to"] == redirect, {k: a[k] for k in ("redirected_to", "state_back")})
    st, tok = exchange(cid, redirect, a["code"], v)
    check("the code + the verifier give a token (no client secret is sent)", st == 200 and tok.get("access_token"),
          {"status": st, "keys": sorted(tok)})
    bearer = {"Authorization": f"Bearer {tok.get('access_token')}"}
    api = urllib.request.build_opener(NoRedirect)
    st, _, body = call(api, "GET", "/api/method/ivendnext_mpos.api.v1.get_logged_user", headers=bearer)
    check("the token acts as THAT person", st == 200 and json.loads(body).get("message") == who, body[:120])
    st, _, body = call(api, "GET", f"{O}.openid_profile", headers=bearer)
    prof = json.loads(body) if st == 200 else {}
    check("the profile names the person and their roles", st == 200 and prof.get("email") == who and
          "Retail Cashier" in (prof.get("roles") or []), {k: prof.get(k) for k in ("email", "roles")})
    st, _, _ = call(api, "GET", "/api/resource/Item?limit_page_length=1", headers=bearer)
    check("…reads what the person may read (items)", st == 200, st)
    st, _, _ = call(api, "GET", "/api/resource/Error%20Log?limit_page_length=1", headers=bearer)
    check("…and is refused what the person may not (the error log, System Manager only)", st == 403, st)
    st, _, _ = call(urllib.request.build_opener(NoRedirect), "POST", f"{O}.revoke_token",
                    {"token": tok.get("access_token")})
    st2, _, _ = call(api, "GET", "/api/method/ivendnext_mpos.api.v1.get_logged_user", headers=bearer)
    check("a revoked token works no more", st == 200 and st2 in (401, 403), [st, st2])
    # 3. PKCE is what protects the code (measured: the token endpoint does not check the client secret)
    for label, verifier, secret in (("a WRONG verifier", pkce()[0], None), ("NO verifier", None, None),
                                    ("NO verifier, the right secret", None, sec["signin_client"]["client_secret"])):
        v2, c2 = pkce()
        a2 = authorize(br, cid, redirect, c2, "s2")
        st, t2 = exchange(cid, redirect, a2["code"], verifier, secret)
        check(f"a code exchanged with {label} is refused", st != 200 or not t2.get("access_token"),
              {"status": st, "keys": sorted(t2)})
    a3 = authorize(br, cid, redirect, None, "s3")       # an app that skips PKCE
    st, t3 = exchange(cid, redirect, a3["code"], None, "not-the-secret")
    no_pkce = {"status": st, "token_issued": bool(t3.get("access_token"))}
    print(f"MEASURED (a finding, not a check): without PKCE, a code + a WRONG client secret → {no_pkce}")
    if t3.get("access_token"):
        call(urllib.request.build_opener(NoRedirect), "POST", f"{O}.revoke_token", {"token": t3["access_token"]})
    a4 = authorize(br, cid, redirect, c, "s4")
    st, t4 = exchange(cid, redirect, a4["code"], v)
    st5, t5 = exchange(cid, redirect, a4["code"], v)
    check("a code works once: the second exchange is refused", st == 200 and t4.get("access_token") and
          not t5.get("access_token"), [st, st5])
    if t4.get("access_token"):
        call(urllib.request.build_opener(NoRedirect), "POST", f"{O}.revoke_token", {"token": t4["access_token"]})
    a5 = authorize(br, cid, "http://evil.example/cb", c, "s5")
    check("a redirect address the app did not register is refused (no code is sent there)", not a5["code"] and
          "evil.example" not in a5["redirected_to"], {k: v for k, v in a5.items() if k != "code"})
    json.dump({"ok": all(c["ok"] for c in checks), "checks": checks, "measured_without_pkce": no_pkce},
              open(f"{T}/runs/l4_signin_check.json", "w"), indent=1)
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


if __name__ == "__main__":
    main()
