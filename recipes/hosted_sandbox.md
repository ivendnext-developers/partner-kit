# The hosted sandbox site — what you receive, your first hour, and its limits — the recipe

A sandbox site is your own iVendNext shop, hosted by us and full of made-up demo data, where you build and test before you touch a customer's site. This recipe is for anyone who builds for an iVendNext customer and gets a sandbox site from us — an iVendNext Partner, a licensed customer's IT team, the CitiXsys Consulting Team. Every one of them receives the same site, made the same way.

**When to use it.** From step 2 of the path: right after you register, before you quote or build anything. It is where you try every rung of the ladder and run your tests.

## What you receive

- **An address** — your own site, in your name. We tell you the address when the site is ready.
- **An administrator login** for that site, with a one-time password. You choose your own password the first time you sign in.
- **Logins for the shop's people:** a store manager and two cashiers, each with a till sign-in ID, a password and a six-digit PIN.

Nothing else. You never receive the software, a server, a container or a connection to the database. Your own code runs on your own machine or server and talks to your site over HTTPS, exactly as it will talk to a customer's site.

Every sandbox site is its own database, so no builder sees or touches another's.

## What is on your site

| Part | What it holds |
|---|---|
| Company | **Demo Retail** — a US shop: US dollars, prices exclude sales tax, and 8% is added at checkout |
| Stores | **Demo Retail — Store 1, Store 2, Store 3**. Each has its own stock and one till profile, which serves the phone, the counter till and the tablet alike |
| Tills | two per store, six in all, free to claim by a till or a phone |
| Catalogue | phones, tablets and laptops in several colours and sizes, plus earbuds, chargers, cases, cables and a care plan (a service). Each of the demo shop's stocked items has a barcode and a price |
| Price list | **Demo Retail Price List** |
| Promotion | **DEMO-10-OFF** — 10% off the sale, in every store, switched on |
| Customers | a walk-in customer, a repeat customer and a VIP customer, with a loyalty programme |
| Gift cards | a gift card and a store credit, each with a balance |
| History | two past purchases by the VIP customer, so returns and reports have something to read |
| Extension points | every one present and **switched off**; nothing of ours is installed beyond the product itself |

**The shop's defaults, and what you will see:**

- **Items are returnable for 30 days.** This covers the demo shop's stocked items and, by default, every item you make. Untick *Returnable* on an item that is not. The care plan, the gift card and the store credit are not returnable.
- **An item you make gets no barcode.** Add one on the item's *Barcodes* table, or sell it at the till by searching its name or code.
- **Each store's `Till-1` has a cash drawer.** The till asks for a counted float when the day opens and a count when it closes. `Term-2` has none, so you can try both flows.
- **Cash pays refunds** in every store.

**The people on your site, and what each may do:**

| Who | Sign-in (Desk) · till ID | Roles it is given | What for |
|---|---|---|---|
| **You, the administrator** | `admin@demo-retail.example` | System Manager, Item Manager, Sales Master Manager, Stock User, Retail Manager | set up the shop as a customer's administrator does: items, prices and price lists, promotions, pricing rules, coupons, till profiles, POS Studio, receipts, workflows, reports, roles, users and keys; read the sales made at the till |
| **Store manager** | `manager@demo-retail.example` · `manager` | Retail Manager | a manager's work at the till: approvals, returns, closing the day |
| **Cashier 1 and Cashier 2** | `cashier1@demo-retail.example` · `cashier1`, `cashier2@demo-retail.example` · `cashier2` | Retail Cashier | selling at the till, in any of the three stores |
| **Integration user** | `integration@demo-retail.example` | Demo Integration — starts with one right: read items | your first connected app. It has no password and **no key yet**: you make its key (below) |

The e-mail addresses are made up. The site also gives every user its standard roles, and gives the administrator the right to edit the shared Desk workspaces. Each role in the table is there because the administrator needs it for at least one of the jobs listed, and together they cover all of them; our own check before hand-over proves both.

## Your first hour

1. **Sign in** at your address as `admin@demo-retail.example` with the one-time password we sent. Choose your own password when the site asks.
2. **Make your administrator's API key:** Desk → your user → Settings → API Access → **Generate Keys**. The secret is shown once; keep it in your secret store. If the shop answers *"Select at least one option: 'Is Desk User' or 'Is POS User'"*, tick **Is Desk User** on your user first (the field `custom_is_desk_user`), save, then generate.
3. **Check your site** with the kit's sandbox check (Python 3, plus bash, curl and jq):

   ```bash
   BASE=https://<your-site> KEY=<api key> SECRET=<api secret> python3 tools/sandbox_check/check.py
   ```

   It checks that the site answers, that your key signs in, that the POS apps are installed, the demo company and its three stores, the integration user, the extension points' record types, and the request collection's first three files. The last line says `SANDBOX CHECK GREEN` or `SANDBOX CHECK RED` and names what failed. If it is red, send us its output: it never prints your key or secret.

   **On a site you made yourself** (not the hosted sandbox), three checks read the hosted sandbox's own data: the demo company, its three stores and the integration user. Name your own in the environment, and the check reads those instead:

   ```bash
   SANDBOX_COMPANY="<your company>" SANDBOX_STORE_PREFIX="<the start of each store's name>" SANDBOX_STORES=<how many> \
   SANDBOX_INTEGRATION_USER=<your integration user> SANDBOX_INTEGRATION_ROLE="<its role>" \
   BASE=… KEY=… SECRET=… python3 tools/sandbox_check/check.py
   ```

   Each one left out keeps the hosted sandbox's value (`Demo Retail`, `Demo Retail — Store `, `3`, `integration@demo-retail.example`, `Demo Integration`). The other six checks are the same on every site.
4. **Give your connected app its key:** open the integration user and press **Generate Keys**. Its role starts with one right, reading items; widen it to what your app needs, as `recipes/integration_user.md` and guide chapter 2 show. Use this key in your app, never the administrator's.
5. **Sell on the till:** sign in to the till as a cashier with the till ID, password and PIN we sent, open a day, sell, and **close the day** before you stop.

## The limits

- **Developer mode is off,** as on a customer's site. Anything you make in Desk stays on your own site.
- **There is no server access** — no shell, no connection to the database (Desk's read-only reports aside), no container, no app source. You work in your own editor and language and call your site over HTTPS.
- **You install your own manifests** with the kit's `deploy` command (`tools/deploy/deploy.py`) and your administrator's key: it shows your site's summary and installs only when you consent. ⚠ A sandbox gets the install screen with its update to the POS app of 2026-10-10 or later; if `deploy` stops at the check with *Failed to get method*, ask us and we update your sandbox. There is no other way to install a manifest.
- **The data is test data.** Never put a real shopper's data, a real payment account, a real fiscal service or a real mail server on your site. None is connected. Your sandbox is hosted in the US. We may reset or remove a site that holds real personal data.
- **Mail is off.** The site never sends a message to anyone. A notification that would send mail (a purchase order's, for example) fails into the site's *Error Log*; the document itself still saves.
- **Server scripts are off.** They do not run on any of our sites.

| You may | You may not |
|---|---|
| Configure anything a customer's administrator can: prices, promotions, coupons, POS Studio, receipts, workflows, numbering, permissions, reports | Install a Python app on the site or the server |
| Make roles and users, and an API key for each connected app (one app, one user) | Reach a server, connect to the database, or reach a container or the app source |
| Call the API from your own machine or server over HTTPS, and run `api/collection/run.sh` | Run server scripts, or rely on client scripts, custom HTML blocks or script print formats (intake refuses them) |
| Check a manifest locally, then install, update or uninstall it on your site with `deploy` | Change a total after the cashier has seen it, or override or patch iVendNext (the four rules, guide chapter 3) |
| Register a feed reader and subscribe webhooks to your own public address | Use a hosted till key, which is for the CitiXsys Consulting Team only |
| Make a till key answered by your own public HTTPS server (private and loopback addresses are refused; use a tunnel or a public test server) | Ask for another builder's site or data |
| Open a POS day on a till and run sales to test your work | Leave a POS day open at the end of a test |

**Close every POS day you open.** An unclosed day holds its cashier in every later test and fails far from its cause. Your tests should close what they open.

## Reset and removal

- **Reset.** Ask us and we remake your site from the template. Everything you made is lost: configuration, users, keys, installed manifests and records. Keep your manifests, configuration and test data in your own repository, so a reset costs you minutes. All keys are new after a reset; give your services the new ones.
- **Removal.** When you leave the programme, your site is removed and its address released.
- ⚠ **Proposed, not ruled yet:** a site that has been quiet for a long spell is archived with notice. You can always ask for a fresh one.

## What is refused, and why

- **A copy of the site, the app source or a container for you.** A site on our hosting gives you everything you need to build, and nothing a customer's site would not.
- **A shared login or a default password.** Every site has its own logins, generated for it, and you choose your administrator's password yourself.
- **A sandbox with mail on.** It could write to a real person from made-up data.
- **Python inside a site.** Outsiders never write Python inside a customer's site. Their ways in are manifests and sandboxed functions (guide chapter 3).

## When your service is down, and when the till is offline

The sandbox does not change either rule. Your site is online whenever our hosting is. A till on your site that you take offline behaves as on any customer's site: your remote answers are not asked for, and the event feed holds what you have not collected. Use the sandbox to rehearse both.

## Technical notes

### How a sandbox site is made

- All sandbox sites run on one sandbox installation on our hosting. It runs the product's latest build, so it carries the extension points, and it runs with developer mode off.
- Each site is made fresh, then filled by one seed, the **sandbox template**. The template reuses the product team's US demo seed with neutral names and prices, so the tax, stock and till wiring are the product's own. It then adds the administrator, the integration user and its starter role, the promotion, the settings (mail off, the stores' time zone) and the shop's defaults (above: returnable items, the `Till-1` drawers, Cash refunds), with the site's default company stored. It installs nothing of ours and switches no extension point on.
- The template's own check runs on every site before hand-over. It fails on: the demo seed's tax check, or prices that include tax; a store without exactly one till profile and two tills; a stocked demo item without a barcode or a price; a user whose roles differ from the table above, or a till ID that differs; an administrator role that no listed job needs, or a job no role covers; developer mode, server scripts or mail switched on; an extension point or webhook switched on; an app of ours installed; an open POS day; the site's default company not stored; a demo item (the care plan and gift cards aside), or a new item's default, not returnable for 30 days; a store whose `Till-1` has no cash drawer; a store's till profile not allowing Cash in returns.
- **One seed per site, not a copy of a template site.** An earlier draft of this recipe proposed seeding one template site and restoring its backup for each builder. A fresh seed is simpler and always matches the installation's current product, so there is no template backup to refresh when the product moves. A reset is the same: a fresh site and the seed.
- The administrator is a named user, not the site's built-in Administrator: the site asks a named user for a new password at first sign-in.

### The sandbox check

- `tools/sandbox_check/check.py` — Python 3 standard library; the collection's own runner, on its first three files, needs bash, curl and jq.
- `--connect-to HOST:PORT` sends the requests to that address and keeps the site's own name, for a new site whose address has no DNS entry yet.
- `--record FILE` writes the answers the checks read; they carry no key or secret.
- **Tests:** `python3 -m unittest discover -s tools/sandbox_check/tests -p 'test_*.py'`. The whole script runs against a local stand-in that answers with a good site's answers: green. Then each planted fault turns it red: a wrong key, a missing store, a store without a till profile, a site without the POS apps, an integration user given administrator rights.
- The request collection's files 01 and 03 name no item group or company, so they run on any shop. Its later files book stock on test items and samples that a sandbox site does not carry; on a sandbox, run them after you have made those, or use them as examples.

### What was proven where

- The check and its planted faults: on the kit's own tests, against the stand-in.
- **The kit's check on a real sandbox site:** 9 of 9 passed on `demo-1` on 2026-10-12, and with a wrong secret it turned red. A later update that day moved the sites to a new installation; the check has not been run again since.
- **The template's own check, 2026-10-12:** once the shop's defaults were applied, it read 0 gaps on eleven of our twelve sandbox sites. The twelfth reported its builder's own changes. A site keeps what its builder changes. The check reads the demo shop as the template made it, so it reports a change to the demo shop's own records or an extension point switched on, but not an item or a user you add.
- **A refund paid in cash** was proven on our own rehearsal site only, not yet on a sandbox site.

### Not this recipe

It does not build the sandbox installation on our hosting, choose the sandbox domain, set the sandbox licence's limits, build the sign-up flow or the self-service reset, or add monitoring and backups.
