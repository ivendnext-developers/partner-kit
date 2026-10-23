# "Sign in with iVendNext" — for a partner app

This recipe lets the users of a partner app outside the retailer's iVendNext — a web page, a mobile app, a portal — sign in with **their own iVendNext account**. Every call the app then makes runs with **that person's permissions and nothing more**. It uses the standard **authorisation code flow with PKCE** (S256). The reference is `tools/sign_in/signin_flow.py` (Python, standard library only).

**When to use it:** your app acts for a named person in the retailer's iVendNext, not for a shared integration user.

## 1. The retailer registers your app (once)
The retailer's administrator creates an **OAuth Client** for you, with:
- the app's name;
- **your exact redirect address(es)**;
- grant type *Authorization Code*, response type *Code*;
- scopes `openid all`.

They give you its **client id** and its **client secret**. Optionally, *Allowed Roles* limits which of the retailer's users may sign in to your app. Keep the secret on your server and send it (§4); do not rely on it alone.

## 2. The flow
1. Your app makes a random **verifier** (43–128 characters) and its **challenge** = base64url(SHA-256(verifier)), and a random **state**. Keep both on your side for this sign-in.
2. Send the person's browser to `https://<shop>/api/method/frappe.integrations.oauth2.authorize` with `client_id`, `response_type=code`, `redirect_uri`, `scope=openid all`, `state`, `code_challenge`, `code_challenge_method=S256`.
3. The person signs in to iVendNext **with their own account**. A person not yet signed in is sent to the retailer's own sign-in page first. iVendNext then shows an **Allow / Deny** page naming your app — unless the client is set to skip it, or the retailer's *OAuth Provider Settings* say *Auto*: then, once any token is active anywhere in the retailer's iVendNext, nobody is asked.
4. On Allow, iVendNext redirects to your redirect address with `code` and the **same** `state`. **Refuse the callback if `state` is not the one you sent.**
5. Your server exchanges the code at `…/frappe.integrations.oauth2.get_token` (form fields: `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, **`code_verifier`**, and, from a server, `client_secret`). You get an `access_token` (and a `refresh_token`).
6. Every call then carries `Authorization: Bearer <access_token>` and runs **as that person**. `…/frappe.integrations.oauth2.openid_profile` names them and their roles.

## 3. What is refused, and why
iVendNext refuses each of these, so a replayed code or a revoked token gets nothing (section 4: always use PKCE):
- a code exchanged with a **wrong** verifier, or **no** verifier — even with the right client secret;
- a code used a second time (a code works once);
- a redirect address your app did not register (it gets no code);
- a token after it was revoked;
- a call for something the person may not read (a 403).

## 4. ⚠ Always use PKCE — and send the secret too
On this build the token endpoint **does not check the client secret**. So for a partner app, **PKCE is the only thing that makes a stolen code useless.** Use it for every sign-in, from every kind of app. An app with a server keeps the secret there — never in a page, a mobile app or a log — and sends it with the code exchange and the revoke: it is ignored today, and an app that leaves it out stops working the day iVendNext starts checking it. Do not rely on it alone until then.

## 5. Your duties
- Keep tokens on your **server**, never in a page's storage; refresh them there.
- Ask for the person's consent on **your** side for anything you store about them.
- Revoke the token when the person signs out of your app (`…/frappe.integrations.oauth2.revoke_token`, form fields `token`, and from a server `client_id` and `client_secret`).
- The token is the person's **whole account**, writes included, whatever your app reads; it lasts an hour on this build. Disabling a person does not end a token already issued.
- Use the retailer's address over HTTPS only, and follow no redirect with a token.

## Technical notes

**Proven** on our test bench on 2026-10-04: 15 checks, every one passing, and one measurement (§4). The table groups the 15 checks into nine rows.

### What was proven on the bench
| | Checks | Result |
|---|---|---|
| A guest is sent to the retailer's own sign-in page first, and signs in to their own account | 2 | ✅ |
| The Allow/Deny page is shown; Allow returns a code and the same state to the registered address | 2 | ✅ |
| Code + verifier → a token, **no client secret sent** | 1 | ✅ |
| The token acts as that person; the profile names them and their roles (a Retail Cashier) | 2 | ✅ |
| …reads what they may read (items) and is refused what they may not (the error log: 403) | 2 | ✅ |
| A revoked token works no more | 1 | ✅ |
| A code exchanged with a **wrong** verifier, with **no** verifier, or with no verifier and the right client secret, is refused | 3 | ✅ |
| A code works once | 1 | ✅ |
| A redirect address the app did not register gets no code | 1 | ✅ |

### The measurement behind §4
On this build a code issued **without** PKCE was exchanged with a **wrong** secret and a token came back.

### Bounds, stated
- Our test bench is reached over plain HTTP on a private network; a real site is HTTPS.
- The person's browser was played by a script (signing in with the persona's password, pressing Allow); the pages themselves were not looked at by a person.
- The refresh token was issued but not exercised. *Allowed Roles* was exercised later, by S13 (`recipes/portal.md`): a user outside the roles is stopped at the retailer's Allow step.
