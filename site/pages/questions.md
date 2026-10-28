# Questions developers ask — Docker, tenants, data, endpoints, fields, screens, cost

The questions a developer from a conventional background asks first, each answered in a few sentences with a link to the page that proves it. New to iVendNext? Read [1a. How it all works](../../guide/01a_how_it_all_works.md) first, ten minutes with a picture per section, or download it as a [PDF](https://developer.ivendnext.com/downloads/how_ivendnext_apps_work.pdf). Linking the till to an outside system? Read [1c. How the data travels](../../guide/01c_how_the_data_travels.md), also as a [PDF](https://developer.ivendnext.com/downloads/how_the_data_travels.pdf).

**Jump to:** [Where it runs](#where-it-runs) · [Data](#data) · [Many customers](#many-customers) · [Talking to iVendNext](#talking-to-ivendnext) · [Outside systems](#outside-systems) · [What you can use](#what-you-can-use) · [Publishing and hosting](#publishing-and-hosting) · [Cost and day to day](#cost-and-day-to-day)

## Where it runs

### Where does my app actually run? Is it in a Docker container, and who runs it?

The part inside the retail chain's iVendNext is only data (your manifest), never code. Your app's web service, if it has one, runs on your own server (a Docker container is fine; the kit's template ships one), or on iVendNext App Hosting, where CitiXsys runs it as a function or as a container at `https://<app>.ivendnext.app`. An app that is only settings and records runs nowhere. [1a, section 3](../../guide/01a_how_it_all_works.md#3-where-your-service-runs-and-whether-that-is-docker).

### What is the difference between a function and a container on App Hosting?

A function runs only when a till or a schedule calls it, for an app that answers presses or works in runs of 15 minutes or less, priced per app per month like any hosted app (free when it is listed in the App library). A container runs all the time, for an app that holds a connection open, serves a queue or runs a longer job. Your code is the same in both. [Chapter 14b, *A function or a container*](../../guide/14b_deploying_your_app.md#a-function-or-a-container).

### Is anything of mine installed on the customer's servers?

No. The chain's administrator installs your manifest, and iVendNext creates the records it lists; no code of yours runs in the chain's site. The one exception is a sandboxed function, a sealed WebAssembly module certified by CitiXsys, at the two extension points that take one. [1a, section 2](../../guide/01a_how_it_all_works.md#2-what-your-app-is-made-of-data-records-fields-screens-plus-an-optional-service).

### Which programming languages can I write my app's service in?

Any, on your own server: iVendNext only calls a public HTTPS address and checks your answers. On App Hosting a container can be any language built as an ARM64 image; a function runs Python 3.13. The kit's template and samples are Python with the standard library only. [Chapter 14b](../../guide/14b_deploying_your_app.md#a-function-or-a-container).

### In which region does App Hosting run my app?

AWS `us-east-1`, for App Hosting and the App library. Other regions are added when a customer needs its data there. On your own server you choose the region. [1a, section 4](../../guide/01a_how_it_all_works.md#4-where-the-customers-data-lives).

## Data

### Does the app keep any of the retail chain's data? Where does that data live?

Not by default. The chain's data, and your app's own record types, live in the chain's own iVendNext, and your service reads them through the API. A hosted app keeps each chain's connection (its address, secrets and key's id) in its own encrypted table, and none of the chain's sales or customers. Anything you store elsewhere is yours to declare, and the chain sees where its data goes before it installs. [1a, section 4](../../guide/01a_how_it_all_works.md#4-where-the-customers-data-lives).

### If my app talks to iVendNext and to an outside system, or only calculates, where does the data stay while it does?

A calculation at a till key or at Pay keeps nothing: iVendNext sends your service the sale, your service answers and forgets it. A link to an outside system sends only the fields your manifest declares, to the address it declares, and each such service waits switched off until the chain's administrator reads exactly what is sent and ticks consent. Whatever your service needs to remember lives in the chain's own records or in a store you declare. [1a, section 4](../../guide/01a_how_it_all_works.md#4-where-the-customers-data-lives).

### Can my app query the customer's database directly?

No. No app connects to the chain's database. Your service reads and writes through the API at the chain's own address, as your app's own user, and sees only what that user's role allows. [API reference](api.md) · [Security and the handshake](security.md).

### Can my app see another customer's data?

No. Each chain's site gives your app a key and secrets for that site only, and your app's user exists only on that site. Every call into your service names its chain and is checked with that chain's own secret; one signed with another chain's secret is refused. The design rule on your side: keep nothing between calls, or keep it by chain. [1a, section 6](../../guide/01a_how_it_all_works.md#6-one-app-many-customers-why-calls-never-collide).

### When a customer uninstalls my app, what happens to the data?

The chain's site first saves your app's records to a private file, then removes what the install added: record types, fields, roles, buttons, the event feed and your app's user with its key. Two things stay on purpose: a sale detail that booked sales point at (switched off) and a workflow state another workflow uses. The chain's own records stay. A hosted app is told goodbye and forgets that chain and its secrets; a store of your own is yours to clear. [1b, step 8](../../guide/01b_one_app_end_to_end.md#8-an-update-then-a-removal) · [Chapter 14a](../../guide/14a_deploying_to_a_chain.md).

## Many customers

### Two different retail chains run the same app, and a cashier at each presses the same button at the same moment. Is there a conflict?

No. Each press is its own call: it names its chain and is signed with that chain's secret, and your service checks it with that chain's secret and answers from that chain's data only. Your service runs several copies at once (up to 10 for a hosted function), so the two calls are answered side by side. [1a, section 6](../../guide/01a_how_it_all_works.md#6-one-app-many-customers-why-calls-never-collide).

### Does each customer need its own container, or its own copy of the app?

No. One app, and one service, serves every chain that installs it; it is multi-tenant by design, through the template's handshake. Run a copy for one chain only if you choose to: its own rules, its own release dates, or a contract that asks for it. [1a, section 7](../../guide/01a_how_it_all_works.md#7-how-many-apps-how-many-boxes).

### How does my service know which chain a call is from?

Every call carries the header `X-iVendNext-Site` with the chain's site and is signed with that chain's own secret, which your service received when the chain connected. A site your service does not know gets 401, and so does a call signed with another site's secret. [Chapter 14b, *One app, many retailers*](../../guide/14b_deploying_your_app.md#one-app-many-retailers).

### What should my service keep in memory between calls?

Nothing that belongs to a chain, unless it is keyed by that chain. A hosted function keeps nothing between runs except a copy's `/tmp`, which is only a cache; each chain's connection is in your app's own table, one row per site. [Chapter 14b, *What a run keeps*](../../guide/14b_deploying_your_app.md#a-function-or-a-container).

### A partner builds four apps for one customer. Four containers, or all four in one to save cost?

Usually one app: one manifest can carry many till keys, checks, record types and Desk buttons, served by one service. On App Hosting each app is one box, priced per app, so four apps are four prices; on your own server, apps can share one container. Split only what needs its own version, consent and removal. [1a, section 7](../../guide/01a_how_it_all_works.md#7-how-many-apps-how-many-boxes).

## Talking to iVendNext

### How does an app talk to the customer's iVendNext, and how do its own record types and fields get created there?

The chain's administrator installs your manifest, and iVendNext creates each record type, field, role and button it lists, and your app's own user. For a hosted app installed from the App library, the chain's site then connects to your service and hands it the secrets and your app's user's key. Your service calls the API; the till calls your service; the event feed tells your service what changed. [1a, section 8](../../guide/01a_how_it_all_works.md#8-how-your-app-reaches-the-customers-ivendnext).

### Which address, key and secret does each call use?

Your service calls the chain's API at `https://<chain site>/api/…` with your app's key. The chain's iVendNext calls your service at your one address, signed with that chain's own secret. Your service calls an outside system with that chain's own account for it. [1a, section 5](../../guide/01a_how_it_all_works.md#5-the-three-directions-of-a-call-and-which-endpoint-key-and-secret-each-uses).

### Where does my app's user and key come from?

From POS version 2.1.0.667, installing a manifest with an event feed makes your app's own user, `<app>@integration.invalid`, which works through the API only, with one role. A hosted app receives its key when the chain connects; for a service on your own server, the chain's administrator generates the key on that user and gives it to you. An app with no event feed is given a user the chain makes by hand. [Chapter 5](../../guide/05_outside_apps_and_event_feed.md).

### Is there a webhook when something changes?

Use the event feed: your service reads, from the chain's site, every change to the record types your manifest follows, in order, and nothing is lost while your service is down. A webhook exists too, as a nudge, but it is tried three times and then dropped, so the feed is the source of truth. [Chapter 5](../../guide/05_outside_apps_and_event_feed.md).

### How long does iVendNext wait for my service's answer?

A till key waits 3 seconds unless the manifest raises it, 10 at most; a check at Pay waits what its manifest says, also 10 at most. Do the slow work before the call or after it. [Chapter 14b, *What every deployable app does*](../../guide/14b_deploying_your_app.md#what-every-deployable-app-does).

## Outside systems

### My app links the till to an outside system, such as a loyalty or telecom system. How does the data travel?

Till, then the chain's iVendNext, then your service (signed for that chain), then the outside system with that chain's own account, then back onto the sale before payment. After payment, the event feed tells your service, which updates the outside system. The worked examples, hop by hop with two chains at once, are [chapter 1c, *How the data travels*](../../guide/01c_how_the_data_travels.md), on samples [S22](../../samples/s22_customer_loyalty/README.md) (a chain's own loyalty system) and [S52](../../samples/s52_phone_plans/README.md) (a telecom company's plans).

### Where does each chain's account at the outside system go?

Each chain's own account details stay with that chain, never shared between chains: a chain's call carries that chain's site, so your service picks that chain's account and no other. They are kept in the chain's own iVendNext, in the app's settings record, which only the System Manager and the app's own role read, and your service reads them there with that chain's key at each call ([chapter 1c, *How the data travels*](../../guide/01c_how_the_data_travels.md), proved on our test bench).

### What does the chain see about an outside system before it installs?

The App library card names every address your app sends data to, and the install screen, written by iVendNext from your manifest, lists each service and the address it calls. Each service waits switched off until the administrator reads which fields it sends and ticks consent. [Chapter 14a](../../guide/14a_deploying_to_a_chain.md) · [Publish your app, *What a retailer sees*](publish.md#what-a-retailer-sees).

## What you can use

### Is there a list of all the iVendNext endpoints, fields and screens an app can use?

Yes, in four places today: the [API reference](api.md) for the record calls, [`api/README.md`](../../api/README.md) for the `ivendnext_mpos.api.v1` methods, [chapter 9](../../guide/09_points_and_requests.md) for every extension point iVendNext calls on your service, and [chapter 13a](../../guide/13a_screens_and_ux.md) for the screens. The developer's map, *What you can use* (`map.html`), puts them on one page with every record type and its fields.

### Can my app add a field to the sale, or its own record types and fields?

Yes, as data in your manifest: a field on an existing record such as the sale, your own record types with their fields, and their native forms and lists in Desk. The install creates them and the uninstall removes them; a field the till shows or asks for is set with field rules. [Chapter 7](../../guide/07_manifests.md) · [1a, section 2](../../guide/01a_how_it_all_works.md#2-what-your-app-is-made-of-data-records-fields-screens-plus-an-optional-service).

### What screens can my app add?

On the till: a sheet over the sale, sheets at the scan, the customer and the quantity, and extra fields on a sale. In Desk: buttons, your own pages and the native screens of your own record types. And a standalone page. [Chapter 13a](../../guide/13a_screens_and_ux.md).

### Can my app change how iVendNext itself works?

No: no app changes iVendNext itself. Your app adds data and answers at the extension points iVendNext opens; money enters a sale only before payment, where the cashier sees it. [Chapter 3, the four rules](../../guide/03_ladder_and_never_list.md#the-four-rules--what-every-build-keeps-and-why).

### What if an extension point I need does not exist?

Combine the ones that exist first, and say the combination's limit to your customer. If none meets the customer's outcome, ask for a new extension point. [Chapter 9](../../guide/09_points_and_requests.md#asking-for-a-new-extension-point-or-for-more-from-one).

## Publishing and hosting

### When I publish an app for a customer, do I give CitiXsys an image of the app? What exactly do I hand over, to whom?

Publishing sends the App library your manifest and your app's card, signed with your key: never your code. Hosting is a separate, optional step: only if CitiXsys runs your service, you send a hosting order with your `app.json` and either an image you built or a function's package (the files it runs), never your repository. [1a, section 9](../../guide/01a_how_it_all_works.md#9-publishing-is-not-handing-us-your-code).

### Who owns the code?

You do. Your code stays in your own repository, and we never need access to it; a hosted function's package holds only the files it runs. The kit's samples are Apache 2.0: copy them, change them, sell them and keep your changes private. [Build your business on iVendNext's apps](business.md#what-stays-yours).

### From finding an app to using it at the till, what does the customer's administrator do, and what does the cashier see?

The administrator finds your app in the App library, reads its card, installs it, reads *What it will do*, ticks consent, writes any settings, and switches each service on for the stores it should serve. The cashier sees your till key on the till, or your answer at Pay, never where your service runs. [1a, section 10](../../guide/01a_how_it_all_works.md#10-what-the-customer-sees) · [1b](../../guide/01b_one_app_end_to_end.md).

### How do I roll back a bad version?

Release the earlier code under a new, higher version number: a version is never overwritten. For your service on App Hosting, push the earlier code under the new version (on your own server, run the previous tag); for your manifest, publish the earlier content as a higher version, which each chain takes as an update. [Chapter 14b, *Updates from your GitHub*](../../guide/14b_deploying_your_app.md#updates-from-your-github) · [Chapter 14a](../../guide/14a_deploying_to_a_chain.md).

### How do I test my app on my laptop before I touch a customer?

Run the template's and your app's tests with no iVendNext at all, call your service the way the till does with the kit's stand-in caller (`tools/standin_caller/`), and run many retailers against an iVendNext site on your own machine with the template's local mode (`IVN_LOCAL=1`). Then install on your own sandbox site, which we host for you. [Chapter 14b, *Steps*](../../guide/14b_deploying_your_app.md#steps) · [Chapter 14](../../guide/14_testing_and_release.md) · [Request a sandbox](sandbox.md).

## Cost and day to day

### What does it cost, and who pays?

The kit, a sandbox site, publishing and listing in the App library are free. App Hosting is per app per month (Starter $49, Standard $129, Managed $399), paid by whoever orders it, and an app that runs as a function and is listed in the App library carries no hosting charge. You bill your customer what you choose. [Build your business on iVendNext's apps, *What it costs*](business.md#what-it-costs) · [Hosting](hosting.md).

### Where do I see my app's logs?

On your own server, wherever you send them. On App Hosting your app's log lines are kept for the plan's days (14 on Starter, 30 on Standard, 90 on Managed) and sent to you when you ask. Log one line per call, never the sale, the customer or a secret. [Chapter 14b](../../guide/14b_deploying_your_app.md#let-citixsys-host-it).

### What does the cashier see when my service is slow or down?

The till keeps selling. For a till key, chapter 6 publishes these words (*Warranty* is the example key's name):

{{include guide/06_till_keys.md#When your service is down, and when the till is offline}}

A check at Pay applies what your manifest's `down_answer` says: allow the sale, or refuse it until your service answers. [Chapter 6](../../guide/06_till_keys.md).

### What happens when the till is offline?

A till key is dimmed and the sale goes on without it. A check at Pay applies its down answer, and a sandboxed function still runs on the till. [1a, section 10](../../guide/01a_how_it_all_works.md#10-what-the-customer-sees).

### What do you mean by tenant, plugin and deployment?

{{include guide/01a_how_it_all_works.md#11. Words we use}}

### What happens when iVendNext is upgraded?

Each version of the extension points and the API is served for 12 months after its successor ships, every change is a dated entry in the kit's changelog, and App Hosting sends a notice before each iVendNext upgrade. Re-run your customer's release gate before an upgrade reaches that customer. [Chapter 18](../../guide/18_versioning_and_support.md) · [Chapter 14](../../guide/14_testing_and_release.md).
