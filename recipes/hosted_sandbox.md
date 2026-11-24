# The hosted sandbox site — what you receive, your first hour, and its limits — the recipe

A sandbox site is your company's iVendNext site, hosted by us, where you build and test before you touch a customer's site. It starts empty, and you choose its made-up demo data. This recipe is for any company in the iVendNext partner programme, and anyone whose partner application we approve. Every one of them receives the same site, made the same way.

**When to use it.** From step 2 of the path: right after you register, before you quote or build anything. It is where you try every rung of the ladder and run your tests.

## What you receive

- **An address** — your company's site: every developer of your company sees it on **My sites**, and its owners see it on the partner portal home.
- **An administrator login** for that site, with a one-time password. Your company's first sandbox shows its logins on the partner portal home, to your company's owners (a referral partner's owner accepts the iVendNext Developer Terms there first); a sandbox handed to a developer shows them once on that developer's **My sites**. You choose your own password the first time you sign in.
- **Demo data when you choose it.** The site starts with no company, store or item. You load a demo pack on **My sites** (**Demo data**) or with `ivn demo load`, and the pack brings the retailer's people with it: Multi-category retail, the pack to start with, brings a store manager and two cashiers, each with a till sign-in ID and a password.

Nothing else. You never receive the software, a server, a container or a connection to the database. Your own code runs on your own machine or server and talks to your site over HTTPS, exactly as it will talk to a customer's site.

Every sandbox site is its own database, so no builder sees or touches another's.

## What is on your site

**Before you load anything:** the product itself and the site's own set-up. There is no company, store, till, item or sale yet. Sign-in by user name is on, mail is off, and every extension point is present with nothing of ours installed beyond the product.

**After you load Multi-category retail** you have one chain, **Demo Retail**: a US company in US dollars with 8% sales tax added at checkout, three stores with two tills each, about 220 items in ten departments with barcodes, prices and stock, a price list, the promotion `DEMO-10-OFF`, customers with a loyalty programme, a gift card, a store credit and two past sales. [Demo data for your sandbox](../site/pages/demo_data.md) lists every part, and every other pack.

**The retailer's defaults, and what you will see:**

- **Items are returnable for 30 days.** This covers the pack's items and, by default, every item you make. Untick *Returnable* on an item that is not. The gift card and the store credit are not returnable.
- **An item you make gets no barcode.** Add one on the item's *Barcodes* table, or sell it at the till by searching its name or code.
- **Each store's `Till-1` has a cash drawer.** The till asks for a counted float when the day opens and a count when it closes. `Term-2` has none, so you can try both flows.
- **Cash pays refunds** in every store.

**The people on your site, and what each may do:**

| Who | Sign-in (Desk) · till ID | Roles it is given | What for |
|---|---|---|---|
| **You, the administrator** | `admin@demo-retail.example` | System Manager, Item Manager, Sales Master Manager, Stock User, Retail Manager | set up iVendNext as a customer's administrator does: items, prices and price lists, promotions, pricing rules, coupons, till profiles, POS Studio, receipts, workflows, reports, roles, users and keys; read the sales made at the till |
| **Store manager** (with Multi-category retail) | `manager@demo-retail.example` · `manager` | Retail Manager | a manager's work at the till: approvals, returns, closing the day |
| **Cashier 1 and Cashier 2** (with Multi-category retail) | `cashier1@demo-retail.example` · `cashier1`, `cashier2@demo-retail.example` · `cashier2` | Retail Cashier | selling at the till, in any of the three stores |
| **Integration user** | `integration@demo-retail.example` | Demo Integration — starts with one right: read items | your first connected app. It has no password and **no key yet**: you make its key (*Your first hour*, in the hosted sandbox recipe) |

The e-mail addresses are made up. The site also gives every user its standard roles, and gives the administrator the right to edit the shared Desk workspaces. Each role in the table is there because the administrator needs it for at least one of the jobs listed, and together they cover all of them; our own check before hand-over proves both.

## Your first hour

1. **Sign in** at your address as `admin@demo-retail.example` with the one-time password **My sites** showed you. Choose your own password when the site asks.
2. **Load your demo data:** on **My sites**, press **Demo data** on your sandbox, then **Load** on Multi-category retail (or run `ivn demo load multi-category`). It takes a few minutes; the screen then shows the store manager's and the cashiers' logins.
3. **Check your site** with the kit's sandbox check (Python 3, plus bash, curl and jq):

   ```bash
   BASE=https://<your-site> KEY=<api key> SECRET=<api secret> python3 tools/sandbox_check/check.py
   ```

   It checks that the site answers, that your key signs in, that the POS apps are installed, the demo company and its three stores, the integration user, the extension points' record types, and the request collection's first three files. On an empty sandbox the company, the stores and the collection each pass and say no demo data is loaded yet. With another pack alone on the site, the company and the stores fail: load Multi-category retail, or name that pack's company and stores with the variables below. The last line says `SANDBOX CHECK GREEN` or `SANDBOX CHECK RED` and names what failed. If it is red, send us its output: it never prints your key or secret.

   **On a site you made yourself** (not the hosted sandbox), three checks read the hosted sandbox's own data: the demo company, its three stores and the integration user. Name your own in the environment, and the check reads those instead:

   ```bash
   SANDBOX_COMPANY="<your company>" SANDBOX_STORE_PREFIX="<the start of each store's name>" SANDBOX_STORES=<how many> \
   SANDBOX_INTEGRATION_USER=<your integration user> SANDBOX_INTEGRATION_ROLE="<its role>" \
   BASE=… KEY=… SECRET=… python3 tools/sandbox_check/check.py
   ```

   Each one left out keeps the hosted sandbox's value (`Demo Retail`, `Demo Retail — Store `, `3`, `integration@demo-retail.example`, `Demo Integration`). The other six checks are the same on every site.
4. **Give your connected app its key:** open the integration user and press **Generate Keys**. Its role starts with one right, reading items; widen it to what your app needs, as `recipes/integration_user.md` shows. Use this key in your app, never the administrator's.
5. **Sell on the till:** sign in to the till as a cashier with the till ID and password the pack showed, open a day, sell, and **close the day** before you stop.

## The limits

- **Developer mode is off,** as on a customer's site. Anything you make in Desk stays on your own site.
- **There is no server access** — no shell, no connection to the database (Desk's read-only reports aside), no container, no app source. You work in your own editor and language and call your site over HTTPS.
- **You install your own apps** with `ivn try` (or Try on My apps): on your sandbox in one press, with no key, no plan, no card and no questions. Pick a site, or add one.
- **The data is test data.** Never put a real shopper's data, a real payment account, a real fiscal service or a real mail server on your site. None is connected. Your sandbox is hosted in the US. We may reset or remove a site that holds real personal data.
- **Mail is off.** The site never sends a message to anyone. A notification that would send mail (a purchase order's, for example) fails into the site's *Error Log*; the document itself still saves.
- **Server scripts are off.** They do not run on any of our sites.

| You may | You may not |
|---|---|
| Configure anything a customer's administrator can: prices, promotions, coupons, POS Studio, receipts, workflows, numbering, permissions, reports | Install a Python app on the site or the server |
| Make roles and users, and an API key for each connected app (one app, one user) | Reach a server, connect to the database, or reach a container or the app source |
| Call the API from your own machine or server over HTTPS, and run `api/collection/run.sh` | Run server scripts, or rely on client scripts, custom HTML blocks or script print formats (intake refuses them) |
| Check an app with `ivn check`, then install it on your sandbox with `ivn try` | Change a total after the cashier has seen it, or override or patch iVendNext (the four rules) |
| Register a feed reader and subscribe webhooks to your own public address | Use a hosted till key, which is for the CitiXsys Consulting Team only |
| Make a till key answered by your own public HTTPS server (private and loopback addresses are refused; use a tunnel or a public test server) | Ask for another builder's site or data |
| Open a POS day on a till and run sales to test your work | Leave a POS day open at the end of a test |

**Close every POS day you open.** An unclosed day holds its cashier in every later test and fails far from its cause. Your tests should close what they open.

## Reset and removal

- **Reset your demo data** yourself: **Reset** on a pack puts it back to the start of its demo script, and **Remove** takes it off and leaves what you made ([Demo data for your sandbox](../site/pages/demo_data.md)).
- **A fresh site.** Ask us and we remake your site from the template. Everything you made is lost: configuration, users, keys, installed manifests and records. Keep your manifests, configuration and test data in your own repository, so a fresh site costs you minutes. All keys are new afterwards; give your services the new ones.
- **Sixty days with no sign-in.** A sandbox we hand out goes back to us if nobody signs in to it for 60 days: **My sites** and `ivn sites` show the date under it, and anyone at work on the site moves it on.
- **Removal.** When you leave the programme, your site is removed and its address released.

## What is refused, and why

- **A copy of the site, the app source or a container for you.** A site on our hosting gives you everything you need to build, and nothing a customer's site would not.
- **A shared login or a default password.** Every site has its own logins, generated for it, and you choose your administrator's password yourself.
- **A sandbox with mail on.** It could write to a real person from made-up data.
- **Python inside a site.** Outsiders never write Python inside a customer's site. Their ways in are manifests and sandboxed functions.

## When your service is down, and when the till is offline

The sandbox does not change either rule. Your site is online whenever our hosting is. A till on your site that you take offline behaves as on any customer's site: your remote answers are not asked for, and the event feed holds what you have not collected. Use the sandbox to rehearse both.

## Technical notes

### How a sandbox site is made

- All sandbox sites run on one sandbox installation on our hosting. It runs the product's latest build, so it carries the extension points, and it runs with developer mode off.
- Each site is made fresh, then set up by the **sandbox template**, which makes no demo data. It writes what a new site's set-up would (the root records, US dollars, the fiscal years), the site's time zone, sign-in by user name, mail off, a new item returnable for 30 days, the administrator, and the integration user with its starter role. It installs nothing of ours.
- The template's own check runs on every site before hand-over. It fails on: a company, store, till or sale already on the site; a user whose roles differ from the table above; an administrator role that no listed job needs, or a job no role covers; developer mode, server scripts or mail switched on; an extension point or webhook switched on; an app of ours installed; a new item's default not returnable for 30 days.
- **A demo pack is loaded by us, on our side**, when you press **Load**: the same steps that build our own demo sites. Each Load and Reset ends with the pack's own check, so a load that ends well is a pack that passed it.
- The administrator is a named user, not the site's built-in Administrator: the site asks a named user for a new password at first sign-in.

### The sandbox check

- `tools/sandbox_check/check.py` — Python 3 standard library; the collection's own runner, on its first three files, needs bash, curl and jq.
- `--connect-to HOST:PORT` sends the requests to that address and keeps the site's own name, for a new site whose address has no DNS entry yet.
- `--record FILE` writes the answers the checks read; they carry no key or secret.
- **Tests:** `python3 -m unittest discover -s tools/sandbox_check/tests -p 'test_*.py'`. The whole script runs against a local stand-in that answers with a good site's answers: green. Then each planted fault turns it red: a wrong key, a missing store, a store without a till profile, a site without the POS apps, an integration user given administrator rights. An empty sandbox, with no company at all, stays green and says no demo data is loaded yet.
- The request collection's files 01 and 03 name no item group or company, so they run on any retailer. Its later files book stock on test items and samples that a sandbox site does not carry; on a sandbox, run them after you have made those, or use them as examples.

### What was proven where

- The check and its planted faults: on the kit's own tests, against the stand-in.
- **The kit's check on a real sandbox site:** passed on `demo-1` on 2026-10-12, and with a wrong secret it turned red. A later update that day moved the sites to a new installation; the check has not been run again since.
- **The template's own check, 2026-10-12:** once the retailer's defaults were applied, it read 0 gaps on eleven of our twelve sandbox sites. The twelfth reported its builder's own changes. A site keeps what its builder changes. That check read the demo data the template then made; the template makes none now, and each pack carries its own check.
- **The demo packs, 2026-11-24:** each pack was loaded, checked, reset, checked again and removed on a sandbox of ours through the same door **My sites** calls; two packs were loaded side by side and the first one removed with the other still passing its check; and after the last remove the sandbox held what it held before the first load. Multi-category retail was also loaded on a new, empty site made by the template.
- **A refund paid in cash** was proven on our own rehearsal site only, not yet on a sandbox site.

### Not this recipe

It does not build the sandbox installation on our hosting, choose the sandbox domain, set the sandbox licence's limits, build the sign-up flow or the self-service reset, or add monitoring and backups.
