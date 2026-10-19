# A standalone portal with "Sign in with iVendNext" — the recipe

![A shop user signs in to a portal, allows it, sees their store's sales; a user with no right is told so](../samples/s13_portal/screenshots/s13_flow.gif)

This recipe builds a **web app of your own, on your own server**, for people who already have accounts in a shop: a head-office view, a franchise portal, a manager's dashboard. The person signs in with their iVendNext account, and the portal shows only what **that person's own permissions** allow. **Reference implementation:** `samples/s13_portal/` (the portal, its tests).

**When to use it.** When the screen cannot live inside the shop. If it can, use the shop's own screens first (guide chapter 13a, rung 1–4); a portal is rung 5.

## Steps

1. **Ask the shop to register your app** (`recipes/sign_in.md` §1): an *OAuth Client* with your exact redirect address (`https://your.server/callback`), scopes `openid all`. They give you the client id and the client secret: keep the secret on your server, never in a page. To let only some roles into your app, they list them under *Allowed Roles*: the shop then stops anyone else at its own Allow step.

2. **Run the portal** with four settings:

   `PORTAL_SHOP=https://shop.example PORTAL_CLIENT_ID=… PORTAL_CLIENT_SECRET=… PORTAL_REDIRECT=https://your.server/callback python3 portal.py`

   The secret goes only to the shop, with the code exchange and the sign-out. The shop does not check it on this build (`recipes/sign_in.md` §4), but send it: a portal without it stops signing anyone in the day the shop starts checking.

   Put it behind HTTPS and set `PORTAL_SECURE=1`, so the session cookie is never sent in the clear.

   What a person sees: the portal's button ![the portal's sign-in page](../samples/s13_portal/screenshots/01_portal_sign_in.png) leads to the shop's own sign-in and then its Allow page, which names your app ![the Allow page](../samples/s13_portal/screenshots/03_shop_allow_page.png). The portal never sees the password.

3. **Give each person the permissions you want them to have — in the shop.** The portal does no filtering of its own. A store user is fenced to their store by a *User Permission* on the store (the same way S8 and S14 do); the portal's list then holds only that store's sales. Change who sees what in the shop and the portal follows.

4. **Make your own pages with the kit.** The sample's pages carry the kit's classes only, no colour or font of your own. Run the screen check on every page you ship: `kit/design/tools/check_kit.sh your-page.html`.

   The same portal with a store user ![the sales list](../samples/s13_portal/screenshots/04_sales_list.png), a link into the shop's Desk ![the record behind a link](../samples/s13_portal/screenshots/05_desk_record.png), and a user with no right ![not allowed](../samples/s13_portal/screenshots/06_not_allowed.png).

5. **Decide what to list.** The sample lists the latest 20 sales (*POS Invoice*) with a link into the shop's Desk record. Replace it with the records your people need; ask only for the fields you show.

## What is refused, and why

- **A sign-in that did not start in this browser:** the portal refuses the callback (400) and asks the shop for nothing.
- **A stolen code:** useless without the verifier the portal made, which never leaves its memory.
- **A person the shop does not allow into your app:** the shop stops them; your server never sees a code.
- **A person who may not see sales:** the shop answers 403 to the portal's request; the page says so in a sentence.
- **A signed-out or ended sign-in:** the page is the sign-in page again; nothing of the shop is shown.
- **A link to the sign-in in a browser that is already signed in:** it goes to the sales page, so a forged link signs nobody out.

## Your duties

- Keep tokens on your server; never in a page, cookie, URL or log. (The sample keeps none in a log: it writes no access log.)
- Revoke the token when the person signs out (the sample does).
- Know what you hold: the token is the person's **whole account** in the shop, writes included, for as long as it lasts (an hour on this build). A sign-in lasts as long as the token, not longer.
- When a person leaves, disabling them in the shop does not end a token already issued: revoke their OAuth tokens too.
- A flood of sign-in starts can stop new sign-ins while it lasts: rate-limit `/login` in front of the portal.
- A restart signs everyone out in the sample (memory only). Keep sessions in a store you control if that is not enough, and expire them.
- Ask for consent on **your** side for anything you store about a person.

## Technical notes

### What was proven, and where

- **Laptop, 32 tests** (`samples/s13_portal/tests/test_s13.py`): a guest costs the shop nothing; the sign-in sends PKCE S256, a state and the exact redirect; the callback exchanges the code with the verifier that matches the challenge, and the client secret, which goes to the shop and nowhere else (sign-in and sign-out); a portal without its secret does not start; the page uses the person's own token and never shows it; a wrong state, a callback from another browser and a reused callback are refused with nothing exchanged; a refused person reads nothing and the shop's error text is not echoed; markup in a record name is escaped; sign-out is a POST and revokes; an ended sign-in goes back to the sign-in page; the shop unreachable is a clean page; the sessions are capped, and a flood of sign-in starts cannot sign a real person out; the session id is new after sign-in; an HTTPS portal's cookie is `Secure` by itself; a wrong state spends nothing; a shop's redirect is not followed with the token; a link to the sign-in in a signed-in browser signs nobody out; a token whose sign-in was dropped while the shop answered is revoked; no response names the server software.
- **Our test bench, 25 checks** (store names here are the demo shop's): the portal ran as a real process, and a script played each person's browser. The Store 1 user saw exactly the 20 latest sales the shop holds for that store and none of the other store's; the other store's user saw exactly their store's 4 and none of the first's; the record behind the link opened for the person's own store's sale and was refused for the other store's; a desk user holding an unrelated role signed in and was told in words they may not see sales; the portal's code, exchanged with no verifier or a wrong one, was refused; a callback from another browser, one with the wrong state and one used twice were refused and issued no token; the session id was new after sign-in; sign-out cut the shop's active tokens by exactly one; the portal served the kit's stylesheet (`/ivn-kit.css` answered 200); everything the run made was removed.
- **The screen check** (`kit/design/tools/check_kit.sh` on the portal's seven pages — signed out, signed out with a note, sales, sales with no name, none, refused, error): tokens only, kit version 0.1.0, contrast, right-to-left: PASS.

### Measured

- A **website user** (no desk role) cannot sign in to any app: the shop stops them at its Allow step with "Invalid client_id parameter value" (400).
- With **Allowed Roles** on the client, a desk user without the role is stopped the same way; the user with the role signs in.

- **Screenshots** (our test bench, 2026-10-10; frame: the portal and Desk, 1440 wide, light mode; the sales list in dark mode is `07_sales_list_dark.png`): *Zanele Dube*, a cashier fenced to *Store 1 — R1* of the kit's demo shop, and *Ruan Pretorius*, the desk user with an unrelated role. A real browser drove them, unlike the 25 checks above. The portal's stylesheet is the kit's own file, served by the portal.

### Not proven

The token's lifetime (an hour, read from the shop's code; the ended token's path is proven on the laptop only); a person disabled while signed in; the refresh token; HTTPS (the bench is plain HTTP on its own network); two portals on one client; many users at once; a person's browser was played by a script (the pages were checked by the screen check, not looked at by a person).
