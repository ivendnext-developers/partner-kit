# 2. Getting started — your sandbox, your keys, and the first call in five steps

This chapter gets you from nothing to your first working call against an iVendNext site: a hosted sandbox, a user and key for your app, and one request. It is for a builder starting their first project, in any language.

**Reference implementation:** the request collection [`../api/collection/`](../api/collection/) and the API description [`../api/openapi.yaml`](../api/openapi.yaml); the recipes [Making the integration user](../recipes/integration_user.md) and [Building a connected app](../recipes/connected_app.md).

## When to use it

Before any build. The sandbox is where you try every rung of the ladder (chapter 3) and where you run your tests.

## Your sandbox

### How to ask

Fill in the iVendNext Partner form on ivendnext.com: <https://www.ivendnext.com/partner/#be-a-partner>. You do not need a GitHub account to ask. A licensed customer's IT team may use the same form, or ask its account manager; either way its account owner talks to it. Our team talks to every builder first.

### When access comes

Access means the kit's GitHub organisation and a sandbox site. It comes with onboarding, once our team has talked to you.

### What you receive

We host a sandbox site for you — your own address on our sandbox domain, your own database and your own demo company — on a shared sandbox installation, the same kind of shared installation a customer's site runs on, with developer mode off as on a customer's site. One site per builder:
- demo stores, tills, products, customers and users, in a US shop with prices in US dollars and sales tax added at checkout;
- outgoing e-mail switched off;
- an administrator login for you, so you can configure anything a customer's administrator can;
- no customer data, ever.

You make your own API key, as the five steps below show. There is nothing to install and no copy of our software on your machine. You work in your own editor and your own language. Your code runs on your own machine or server and talks to the sandbox over HTTPS, exactly as it will talk to a customer's site. You get no access to the server, the database or anyone else's site.

**Installing a manifest.** You install your own, with the kit's `deploy` command and your sandbox administrator's key: it shows the site's summary and installs only when you consent (chapter 7). ⚠ A sandbox gets the install screen with its update to the POS app of 2026-10-10 or later: if `deploy` stops at the check with *Failed to get method*, ask us through the [feedback](../feedback/README.md) form and we update your sandbox. There is no other way to install a manifest.

## The first call, in five steps

1. **Make a role for your app** (Desk → Role → New, then Role Permissions Manager). Give it read on *Item* only, for now.
2. **Make one user for your app** (Desk → User → New): an e-mail that names the app; tick *Is Desk User*; give it only your role; set no password. One app, one user — it takes one user licence on a customer's site, and the customer decides when to switch it off.
3. **Generate its API key and secret** (User → Settings → API Access → *Generate Keys*). The secret is shown once; put it in your secret store.
4. **Make the call:**

   ```bash
   curl -s "https://<your-sandbox>/api/resource/Item?limit_page_length=5" \
     -H "Authorization: token <api key>:<api secret>"
   ```

   You get back the first five items as JSON. A missing key answers `403`; a wrong one `401`.
5. **Run the whole collection.** It holds every call the samples make, sent with `curl` and checked with `jq`, with no client library:

   ```bash
   BASE=https://<your-sandbox> KEY=<api key> SECRET=<api secret> bash api/collection/run.sh
   ```

Then read [Building a connected app](../recipes/connected_app.md) and widen your role to exactly what your app reads and writes.

## What is refused, and why

- **A shared or borrowed key.** Every app has its own user, so its access can be seen and switched off on its own.
- **Starting from a broad role** such as a stock user's. It carries far more than your app needs.
- **A key in code, a ticket or a chat.** Keep it in a secret store and rotate it at any doubt.
- **Server-to-server sign-in grants and scoped keys** do not exist today: a key acts with its user's role, nothing narrower. Narrow the role instead.

## When your service is down, and when the till is offline

Nothing in this chapter runs at the till. Your service's own outage handling starts in chapter 5 (the event feed) and chapter 6 (till keys).

## Technical notes

### What has not been proven

- **The hosted sandbox is built, and opens to partners when the kit does.** Its sites run with developer mode off, and the kit's sandbox check passed on two of them on 2026-10-09. `deploy` installs a manifest there only once the sandbox's POS app carries the manifest install screen (the POS app from commit `87812e14`). The five steps themselves were run on our test shop, not on a hosted sandbox site.

### The tests

- The five-step call answers `200` with five items.
- The same call with a wrong secret answers `401`.
- `run.sh` passes every call in the collection.
- A call your role does not allow (for example, reading *Sales Invoice* before you grant it) is refused.
