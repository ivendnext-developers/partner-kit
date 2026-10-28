# Host with CitiXsys or run your own

Your app's outside service, the part iVendNext calls, has to run on a server iVendNext can reach. CitiXsys can run it for you on iVendNext App Hosting, or you can run it on your own cloud. Your code is the same either way and stays in your own repository: we run the image you build, never your source.

## Order hosting from this page

Sign in with GitHub, pick your repository and your customer, pick a plan and its copies, pay, and follow your app to live, all on this page. It does what the kit's `deploy_app.py order` does, with no command ([how it works](#host-with-citixsys)).

{{hosting: order}}

## Two ways, side by side

| | Host with CitiXsys | Run your own |
|---|---|---|
| **Where it runs** | Its own box at `https://<app>.ivendnext.app`, with its own logs and its own store for secrets | Any server you run, with a public HTTPS address |
| **Who runs the server** | CitiXsys; you own the code | You |
| **How a retailer connects** | By itself, when it installs your app from the App library: its public list, or one customer's *Made for you* shelf (the shelf carries your app's key for that customer's sites each time you publish) | By hand, for each retailer |
| **What it costs** | A price per app per month ([the plans](#host-with-citixsys)) | Your own hosting bill |
| **A new version** | You send us its tag | You deploy it |

Either way, you bill your customer what you choose ([Build your business on iVendNext's apps](business.md)).

The checks are the same on both: your app checks every call's signature, and a retailer's site checks only that your app is at a public HTTPS address, then your answer's time and shape ([Security and the handshake](security.md)).

## Who can host with CitiXsys

Anyone who builds for iVendNext, on one path: an iVendNext Partner, a licensed customer's IT team, and CitiXsys's own teams, such as the CitiXsys Consulting Team. Each hosted app has a named owner who orders it and pays for it.

## The builder's journey

1. **Get a sandbox.** [Request a sandbox](sandbox.md) and [get the kit](start.md).
2. **Build and check.** The kit's `check` tells you, before anyone else sees your app, whether it is allowed. Installing it on your sandbox with `tools/deploy` shows the exact words a retailer's administrator will be asked to agree to.
3. **Name it.** Under your company's own first word, given once when we register your company: `ACME LOYALTY` becomes `acme_loyalty`. Every app you name under it is yours, with no wait on us ([Publish your app](publish.md)).
4. **Publish.** Publishing signs your app onto your preview shelf at once. A customer's shelf follows when your publish names that customer. Publish with the kit's command, or from the App library's Publish page in your browser ([below](#publish-from-the-web-page)).
5. **Order hosting.** Build the service's image, or a function's package, and send a hosting order. We create its box and its address and switch it on.
6. **List it for every retailer.** Optional. One approval by us for its first listing, and again when a version sends data to a new address, adds an outside service with its own user or needs more Desk users, puts it on the public list with its card and its guide page.

## Host with CitiXsys

{{include guide/14b_deploying_your_app.md#Let CitiXsys host it}}

## Publish from the web page

{{include site/pages/publish.md#From the web page}}

## Run your own

{{include guide/14b_deploying_your_app.md#Where it can run}}

Every deployable app does the same eight things wherever it runs: [What every deployable app does](../../guide/14b_deploying_your_app.md#what-every-deployable-app-does). The template your app starts from: [`tools/app_template`](../../tools/app_template/README.md).

