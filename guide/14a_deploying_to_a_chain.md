# 14a. Deploying to a chain of stores

How your work reaches a customer with many stores and tills: what goes where, how the retailer switches it on store by store, and how you update it and roll it back.

**For:** a builder whose work goes to a customer with many stores and tills (say 10 stores with 10 tills each, in 10 cities), and the customer's own team that switches it on.
**Reference implementation:** [Building a connected app](../recipes/connected_app.md) and [A till key](../recipes/point_handler.md) (your application, connected by the retailer) · [Shipping your own data in a manifest](../recipes/manifest.md) and [a Desk action](../recipes/desk_action.md) (your data in the retailer's iVendNext) · [Set up fifty stores from one file](../recipes/estate_rollout.md) with [`../samples/s8_estate_rollout/`](../samples/s8_estate_rollout/) (configuration across stores) · [14. Testing and release](14_testing_and_release.md) (the gate before every change).

## When to use it

Read it before you plan a customer's go-live. Read it again before every update you ship to a customer that has more than one store.

## The one thing to know: one customer, one site

A customer's iVendNext is **one site**: one web address and one database. Every store is a set of records inside it: a warehouse and the store's till profiles. Every Desk browser in the back office and every till, whether a browser or the installed app, opens that same site. So 10 stores with 10 tills each is **100 tills on one site**, not 100 installations.

That decides how you deploy:
- **You never install anything on a till or a PC.**
- **What you set up in the customer's site is there for every store at the same moment.** Taking it to the stores one at a time is a **switch** the retailer turns, not an install. Some things have no such switch (below).
- **We upgrade our product for every customer on it together.** You never ship a copy of our code, so a store never runs an old one.

## Where your work lives: three layers

A customer's iVendNext, on our hosting, has three layers:

| Layer | What it is | Who changes it | Can your work touch it? |
|---|---|---|---|
| **Server** | our machines the site runs on (not the retailer's tills or PCs) | our hosting team | ⛔ never |
| **Installation** | the program code: iVendNext and its apps, built as one unit and **shared by many customers** | only our releases, for every customer on it | ⛔ never. Code here would be code for every customer on it |
| **Site** | **one customer's** database and files, at its web address | the customer's administrator, in Desk | **only as data**, through the doors in chapter 3 |

You never sign in to a server, and you never change code on an installation. Your work reaches a customer in one of two kinds today (Kinds 1 and 2), with a third, Kind 3, that runs only once we have certified it. **Only data ever enters the site:** your manifest, and a sandboxed function as a sealed file we have certified (Kind 3).

## The three kinds of work, and how each is deployed

### Kind 1: your application, which runs on your own servers
Your code runs on your servers or your cloud, in any language. It reaches the customer's site over the internet. To connect it, **the customer's administrator** creates records in Desk. They are settings, not software:
- **an integration user and its key**, so your application can read and write records ([recipe](../recipes/integration_user.md)). It is one desk-user licence;
- **a till key record**, so a button on the till calls your server ([recipe](../recipes/point_handler.md), step 6);
- **a Desk button and its service record**, so a button in Desk calls your server ([Desk action](../recipes/desk_action.md));
- **an event-feed registration**, so you hear about new sales and changes ([recipe](../recipes/event_feed.md)).

Nothing is installed, and nothing goes through us. **Deploying** means you release your own servers ([chapter 14b](14b_deploying_your_app.md)). **Rolling out** means the retailer switches the connection on store by store (below).

### Kind 2: your data, kept inside the customer's site
When your users should work on your records **inside iVendNext**, you describe them in a **manifest** ([chapter 7](07_manifests.md), [recipe](../recipes/manifest.md)). Bins and what is in them, warranty terms, a pick task, a field on Item, a print format: each with native screens. A manifest is a **description, not a program**. It can also declare the till keys, Desk buttons and services of Kind 1, so iVendNext does not have to type them in. A till key declared this way has been installed on our test site, switched off (from the release that carries the change it is ready in POS Studio > Apps once the app is installed, and the store switches it on there), but has not yet been pressed on a till; a key record the test bench wrote directly has been pressed on a till screen in a desktop browser, not on a physical till ([chapter 6](06_till_keys.md), [chapter 7](07_manifests.md)).
- **Our installer**, which is our code, reads the manifest and writes those records into the one site. Nothing is added to the installation, and no other customer's site changes.
- **Our code is the check, every time.** The installer runs the full manifest checker inside the site before it creates anything. It refuses:
  - code and scripts;
  - JavaScript conditions;
  - hidden ways data could leave the site;
  - record types that post to stock or the accounts;
  - changes to the retailer's own fields that could stop a sale.

  Run the same checker yourself before you hand the manifest over:

  ```bash
  python3 tools/manifest/validate.py manifest.json      # VALID, exit 0
  ```

- **Who installs it:** the **customer's own administrator**, from the **Retail Extension Package** screen in Desk. What it installs is a *package*, your whole app; a *module* is one small program that does one job at an extension point, and a package cannot install one: the retailer's administrator adds it in Desk, at the check before payment or pricing ([the package-or-module box in chapter 7](07_manifests.md)). The screen shows a summary the installer writes from your manifest (never from your description): what it creates, every address it sends to and what it sends, what runs from the moment of install, and every print format, as a template that runs on the server when printed, able to read, change and send the retailer's data. The administrator consents to that exact manifest. On your own sandbox, the kit's `deploy` command does the same over the API.
- **You can always avoid Kind 2** by keeping your data on your own server and using Kind 1 only.

### Kind 3: a sandboxed function
Compiled WebAssembly that runs inside the product, on the server and on an offline till, in a closed box: no network, no clock, no database, only the extension point's input in and an answer out (chapter 8). **Available at two extension points,** the check before payment and pricing, and only a module we have certified: the retailer's administrator adds it in Desk. A manifest cannot carry one yet.

## What the customer's users see

Your record types get **the native iVendNext screens**: form, list, report view, search, print and workflow buttons. Add workspaces, reports, cards, charts and Connections links that list your records under ours. A Desk button opens **our** dialog, and your answer shows in it. Users cannot tell a partner's screens from ours, because they are ours. When a screen cannot be native, your own page opens inside our frame, styled with the partner kit. On the till you get a key (a message or sale details) and a page in a sheet. You cannot redesign the till's own screens. The screen ladder, the approval rules and the limits are in [chapter 13a](13a_screens_and_ux.md).

**Instead of a new record type in a product release.** When our own team adds a feature, its record types ship in our code, in a release, to every customer. Yours ship as data in one customer's site, with the same native screens and no release of ours. What our code would do on the server comes from:
- **save rules**: a pattern, a length, a derived value, uniqueness, required-when, or locked in a state;
- **workflows** for approvals;
- **your own server**, called by a Desk button or told by a webhook or the event feed.

What our form scripts would do comes from:
- **simple field conditions**: show, require or lock a field when another has a value;
- **`fetch_from`**, to fill a value from a linked record.

A record type that posts to stock or the accounts cannot be yours. Your server creates our documents (a Sales Invoice, a Stock Entry) through the API instead (chapter 7).

## How each way in reaches the stores

| Way in (chapter 3) | Kind | How the retailer takes it store by store | Today |
|---|---|---|---|
| **1. Configure** | — (settings) | the [estate roll-out file](../recipes/estate_rollout.md) over the API names each store and region: `plan`, `apply`, `verify`, `remove` | available |
| **2. Outside app** | 1 | the integration user's role and user permissions decide which stores' records it reaches | available |
| **3. Till key** | 1 | switched on in **POS Studio → the theme → Apps**: **every till whose profile wears that theme** shows the key. Give the pilot store's till profiles their own theme, then move the other stores onto it | extension point |
| **Desk button** | 1 | the people who hold its role | extension point |
| **Your page** | 1 | on the till, its store setting lists the till profiles it opens on (empty means every till); in Desk, the people who hold its roles | extension point |
| **Check before payment, capture** | 1 | the POS Profiles each serves (empty means every till); at most three checks answer one profile | extension point |
| **Scan source** | 2 | switched on for the whole site; a source with a warehouse field finds only the till's own store's units | extension point |
| **Field rules** | 2 | by theme: every till whose profile wears the theme, at its next start; there is no switch | extension point |
| **4. Manifest** | 2 | its records and fields are present in the whole site and reached through roles; what it declares (keys, buttons, pages) follows the rows above | the customer's administrator installs it |
| **Label layout** | 2 | on for the whole site once switched on; whoever holds the Print right on *Retail Label Layout* prints | extension point |
| **Receipt lines** | — (settings) | set on each register, so store by store | settings |
| **5. Sandboxed function** | 3 | as for its extension point | the customer's administrator adds it in Desk, once we have certified it |

**What has no store switch.** These apply to the whole site the moment they are installed or switched on, so plan them as a site-wide step, at a quiet hour:
- a **manifest's webhooks and notifications**, which are installed **switched on**, its **workflows**, which are installed active, and its **sale details**, which every till starts asking for at once;
- display changes a manifest makes to the retailer's own fields;
- a **save rule**, which has no store setting. The exception is a *required-when* rule, whose conditions can name the sale's till profile;
- a **field rule**, which reaches every till on its theme at the till's next start (a rule that requires a field is enforced by the server at once);
- a **scan source** once switched on, which every till reads;
- a **fiscal reader**, one per source (each installed fiscal app, or one outside service), for every company it names;
- an **event-feed registration**;
- the **records and fields** a manifest adds.

## Steps: a safe roll-out across the chain

1. **Build and test on your sandbox** (chapter 2). The hosted sandbox opens to partners when the kit does.
2. **Test on the customer's staging site**, if it has one, and run the customer's release gate there (chapter 14). How a customer on our hosting gets a staging site is not covered by the kit yet.
3. **Put it in the customer's site:**
   - **Kind 1:** the administrator creates the connection records and ticks each service's consent.
   - **Kind 2:** your manifest is installed by the customer's administrator, from the install screen in Desk.
4. **What calls your service waits switched off**, apart from a manifest's webhooks (and its notifications, workflows and sale details, which are on from install). Each service that sends data waits for its own consent tick (chapter 7).
5. **Switch on one pilot store:**
   - **A till key:** put it in a theme that only the pilot store's till profiles wear. Plan on each till showing a key that was just switched on the next time it is opened.
   - **A page shown on the till:** list the pilot store's till profiles in its store setting, **and** put its till key in the pilot theme. The store setting alone leaves the key showing on every till that wears the theme, and outside the pilot a press says the button's app is not available.
   - **Desk screens and buttons:** give your role to the pilot store's staff only. ⚠ **Leave the store setting empty on a service a Desk button or Desk page calls.** A call from Desk names no till profile, so a service limited to some till profiles is never called from Desk.
6. **Watch the pilot.**
   - **Desk buttons and pages** write a row in the retailer's **Extension Log** on every call: the outcome (answered, answer refused, timeout, unreachable…), the time it took, and a one-line verdict, never the body or the secret. Rows about a page on the till also name the till profile.
   - **A till key's failures** reach only iVendNext's error log today.
   - **Webhooks and the event feed** write no Extension Log row.
   - **Your own server's log** is the full record of what you answered.
7. **Widen:** a region, then the whole chain. Move more till profiles onto the theme, add them to a page's store setting, or give the role to more staff.

### Worked example: 10 stores, 10 tills each
A partner ships a warranty service, with a Desk report of warranties sold (Kind 2, a manifest) and a till key that shows the warranty terms during the sale (Kind 1, the partner's server):
1. The partner tests both on its sandbox and on the customer's staging site.
2. The manifest is installed once into the customer's site. The warranty records, their screens and the report exist for all 10 stores at once, and appear only to people who hold the partner's role.
3. The key is switched on and given to the pilot store only: the administrator ticks the till key's consent in Desk (from the release that carries the change, the consent on the install screen is the key's, and the store switches the key on in POS Studio > Apps), then gives the 10 till profiles of the pilot store (Store 1) a theme carrying the key. Only Store 1's tills show it.
4. A week of Store 1's sales is read in the partner's own log and in iVendNext's error log.
5. The administrator moves the 30 till profiles of the next three stores onto the theme, then the rest. The warranty role goes to each store's staff as its tills get the key.
6. The partner later improves the terms on its server, first for Store 1 only, by reading `store` in each call's context, then for every store.

### Your own server's releases skip the retailer's switch
Your server answers every store at once. A change you release there reaches **every till on its next call**, whatever the retailer has switched on. Roll it out on your side the same way:
- **A call from a till names the store and the till profile.** A till key's context carries `store` and `pos_profile`, and a page opened on the till carries the till profile. Turn new behaviour on for the pilot store first, in your own code. A Desk button's call and a webhook's body carry no store.
- **Or run the new version at a new address**, and let the retailer move store by store. ⚠ A new address **clears the customer's consent** on that service until the administrator ticks it again. That is the point: the customer agrees to where its data goes.
- **Keep your old answers working** until every store has moved.

### Updating a manifest
- **Bring a higher version.** The administrator checks it on the same screen, sees what changes from the installed version, consents again, and updates in place. The update **adds and changes, and removes nothing** while it runs; what a new version drops is **switched off at once** (a webhook stops sending) and goes at uninstall.
- It **refuses** a field changing type, a record type or field dropped or renamed, or an option being removed (sales made offline may still carry the old option), so ship a new field or keep the option.
- **A service the update changes arrives switched off again**, and needs its consent again: plan the switch-on store by store, as above.
- A version is never installed over a newer one, so to go back, ship the old content as a new, higher version. A failed update undoes its own changes and the installed version keeps running.

### Rolling back
- **At once, per store:** switch it off. Take the till key out of the store's theme, take the till profile off a page's store setting, or take the role away.
- **Your server:** roll back your own release.
- **A manifest:** ship the earlier content as a new, higher version (an update removes nothing, and switches off what it drops), or uninstall it (it exports the retailer's records first).
- **Taking a manifest out:** the uninstall exports the customer's records first and leaves the site as it found it. Two things are kept on purpose: a sale detail that booked sales point at (kept, switched off) and a workflow state another workflow uses.

## When our release changes the product

We release one product to every customer. Your work keeps running because it only uses published ways in: the API, the event feed, the extension points and the manifest format (`manifest_version`). The calls for a Desk button, a check and a capture carry `X-iVendNext-Point: <point>/<version>`; a till key's call names its version in its `User-Agent` (`iVendNext-POS-AppKey/1`). How long a version keeps working is in [chapter 18](18_versioning_and_support.md). **Re-run the customer's release gate before every one of our upgrades** (chapter 14).

## What the retailer sees

- **In the customer's site**, read by the customer's administrator:
  - every manifest install, as the install record: what was installed, which version, when it was removed. The record is kept after an uninstall as iVendNext's log;
  - the Extension Log rows of Desk buttons and pages;
  - who consented, when, and to which summary: the package record keeps it, and an earlier version's record keeps its own.
- **Across customers (designed, not yet built):** because we host the sites, we can keep one list of which customer has which manifest installed, at which version, and when it was consented to. It holds names, versions, statuses and dates, never the customer's records. We would use it to re-test what customers actually run before each of our releases, and to tell exactly the customers who hold a manifest found to be bad.
- **The site sends nothing to us.** It sends data to you only through the channels the retailer can see and has consented to: your till key, your webhooks, your services, your integration user. A manifest cannot add a way for data to leave unseen (chapter 7).

## What is refused, and why

- **Installing anything on a till or a PC.** There is nothing to install there: the till runs only our code, from the customer's site.
- **Your own code inside the site, or your JavaScript in Desk or on the till** (the four rules, chapter 3).
- **A manifest the checker refuses**, whoever tries to install it: the screen, the API or our team.
- **A press for a till key that is not switched on** for that till.
- **A page opened on a till outside its store setting:** the press is refused (*the button's app is not available*).

## When your service is down, and when the till is offline

- **Your service is down:** the till never waits on it.
  - A till key is refused in words.
  - A Desk button waits for its time to answer (3 seconds unless raised), then says *"⟨label⟩ did not answer in time. Check the record before you try again."* ([Desk action](../recipes/desk_action.md), step 7).
  - An extension point applies its own declared down answer.
  - Your manifest's records and screens need nothing from your service: they are in the customer's site.
- **The till is offline:** your service is not called.
  - Till keys are dimmed offline, and a press is refused before any call.
  - A sale made offline is queued and uploaded later.
  - The check before payment and the capture are not called for a sale made offline: the till applies their declared down answer, the sale is flagged when it syncs, and the log says *not called offline*.
  - Only a sandboxed function we have certified runs on an offline till (the check before payment and pricing take one).
  - This offline behaviour is the product's design; the kit's own tests have not run it offline (a pricing module was walked offline on our test bench's three till screens: chapter 8).

## Technical notes

### What the kit has proven

- **Configuration across stores:** the estate roll-out made 51 stores' warehouses, till profiles, users and promotions from one file. Its plan wrote nothing, a second `apply` changed nothing, `verify` named every hand edit, and a regional promotion reached only its region's stores ([recipe](../recipes/estate_rollout.md)).
- **An application connected by the retailer:** an integration user's key working, refused outside its role, and rotated ([recipe](../recipes/integration_user.md)).
- **A till key switched on through a theme** worn by one till profile; a press for a key that is not switched on was refused ([recipe](../recipes/point_handler.md)).
- **A manifest installed with its Desk button switched off**, switched on by the retailer, and removed with the site as it was found; a Desk button refused for a user without its role ([Desk action](../recipes/desk_action.md), [manifest](../recipes/manifest.md)).

### What it has not

- **A manifest-declared till key:** installed on our test site, switched off, and read back (the ready-on-install change in the release that carries it has not been walked with a kit sample); it was not pressed on a till. The presses that were answered used a key record the bench wrote directly (through the till's own endpoint; S6's walk, on the till's screen), and no press came from a physical till device ([chapter 7](07_manifests.md)).
- **A real chain.** The test site has one real store. The 51 stores were records made for the test, and no till ran against them.
- **How soon an open till shows a key that was just switched on:** not measured. Plan on the next time each till is opened.
- **Offline:** the kit has not run a till key or a page offline, and a pricing module was walked offline on our test bench's three till screens (chapter 8). The offline behaviour above is otherwise the product's design, read in its code.
- **The install screen and updates in place** ran on our test site through `deploy` (2026-10-10); **the list across customers** is designed, not yet built. **Sandboxed functions:** two extension points take one; no module a partner built has run on a retailer's iVendNext yet (chapter 8).
- **A staging site on our hosting,** and load.

## See also

[3. The ladder and the four rules](03_ladder_and_never_list.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [6. Till keys](06_till_keys.md) · [7. Manifests](07_manifests.md) · [13a. Screens and user experience](13a_screens_and_ux.md) · [14. Testing and release](14_testing_and_release.md) · [17. Submitting, support, feedback](17_submit_support_feedback.md)
