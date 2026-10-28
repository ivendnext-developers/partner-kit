# 14b. Deploying your app

How to run your own service so a retailer can reach it: what it must do, how to package it, where it can run, and how to update it without breaking a retailer.

**For:** a builder whose work includes an outside app (chapters 5 and 6): a service that answers a till key, reads the event feed, or reacts to a webhook, and must run on a server a retailer can reach.
**Reference implementation:** [`../tools/app_template/`](../tools/app_template/README.md) — a small service, a Dockerfile, a settings file and a checker, ready to copy.

## The short answer

- **The one idea:** an iVendNext app is data that goes into the customer's iVendNext, plus, if it needs one, a single web service that serves every customer ([1a. How it all works](01a_how_it_all_works.md)).
- **Your app runs on a server you choose,** in any cloud or on your own machines. Nothing of yours is installed in the customer's iVendNext (chapter 3, rule 3).
- **iVendNext calls your app over HTTPS** (a till key, a Desk button, a webhook) and **your app calls iVendNext's API** with the key you were given. Till keys and Desk buttons are extension points (chapter 9).
- **Package it as a container.** One image runs the same on your laptop, on a test copy and in production.
- **Or let CitiXsys host it.** Send us the image, or a function's package (the files it runs), and its settings file, never your repository; we run it at `https://<app>.ivendnext.app` ([below](#let-citixsys-host-it)).
- **iVendNext checks nothing about where you run it.** It checks your answers: the signature, the time to answer and the shape of the reply.

## When to use it

When your app is ready to leave your laptop: before a retailer's sandbox calls it for the first time, and again for each customer's production.

## What every deployable app does

1. **Has a public HTTPS address with a valid certificate.** iVendNext checks the certificate against your host name, and an address that resolves to a private network is refused (`recipes/point_handler.md`).
2. **Answers inside the time.** A till key has 3 seconds unless iVendNext raises it, 10 at most. Do the slow work before the call, or after it.
3. **Verifies every call before it reads it.** The signature is `base64(HMAC-SHA256(secret, "<timestamp>.<raw body>"))` over the raw body, and a timestamp more than five minutes from your clock is refused. Answer a body over 64 KB with 413.
4. **Keeps secrets out of the image and the repository.** The signing secret and the API key arrive as environment variables from the host's secret store.
5. **Has a health address** (`/health`) that answers without a signature and says nothing about retailers.
6. **Logs one line per call:** the request id, the status and the milliseconds. Never the body, the sale, the customer, the secret or the signature.
7. **Is safe to run twice.** A webhook is tried three times and then dropped, and a call can arrive again. Handle each event so a repeat changes nothing, and run a reconciliation pull on a schedule (chapter 5).
8. **Stops cleanly.** A host stops a container with a termination signal: finish the call in hand, then exit.

The template does all eight. Replace its `core.py` with your logic and keep the rest.

## Steps

1. **Copy the template** folder to your own repository and rename the app in `app.json`.
2. **Run it on your laptop** and test it without a retailer's iVendNext:

   ```bash
   python3 -m unittest discover -s tools/app_template/tests -p 'test_*.py' -v
   ```

   ```bash
   IVN_POINT_SECRET=any-long-random-string docker compose up --build
   ```

   For many retailers against an iVendNext site on your own machine (`http://shop.localhost:8000`, say), use the template's local mode, `IVN_LOCAL=1`, and send the connect yourself ([the template's README](../tools/app_template/README.md#local-mode-many-retailers-on-your-laptop)).

3. **Call it the way the till does** with the stand-in caller (`tools/standin_caller/`), which signs a call and judges the answer as the remote till key does.
4. **Check the settings file and the Dockerfile:**

   ```bash
   python3 tools/app_template/validate_app.py
   ```

   It refuses a container that runs as root, has no health check, exposes a port the settings file does not name, or has a secret baked into it; and a settings file with a value in it.
5. **Publish the image** to a container registry you control, with a version tag (`1.0.0`), never only `latest`.
6. **Run the image on a host** (below) with the settings from `app.json`.
7. **Tell iVendNext where you are.** Put your HTTPS address and the signing secret in the retailer's record for the key, the webhook or the feed (chapters 5 to 7). `tools/deploy` prints a generated secret once: store it in your host's secret store the same minute.
8. **Call it once from iVendNext** (press the key, or send a test webhook) and read your log line.

## Where it can run

Any host that runs a container and gives it a public HTTPS address will do. What to set:

| Setting | Value |
|---|---|
| Image | your registry and version tag |
| Port | the one in `app.json` (8080 in the template) |
| Health check | `GET /health`, expect 200 |
| Environment | the names in `app.json`; secrets from the host's secret store, never typed into a file |
| Instances | at least one always running (a till key waits seconds, not a cold start) |
| Address | HTTPS with a certificate for your own host name |
| Region | near the retailer's site, and where the customer's data may live |
| Restart | automatic, on a failed health check |

A managed container service in your own cloud account is the least work. A small server running `docker compose` also works. If your app keeps its own data, give it its own database with daily backups, and write down how you restore it.

## Let CitiXsys host it

If you would rather not run a server, CitiXsys runs your app for you on our own cloud, beside iVendNext. **Your code stays in your own repository.** We never need access to your code repository: we run the image you build, or your function's package, which holds only the files the function runs.

**Build the image for ARM64** (`docker build --platform linux/arm64 …`). Our hosting runs ARM processors; an image built only for x86 does not start.

**What you send us** — one hosting order:

- your app's `app.json` and `Dockerfile` (names only, never a value, and no secret in either);
- your app's licence file and its list of third-party components (`LICENSE` and `THIRD_PARTY.md`, as in the template). We host a component under the GNU Affero GPL only when you publish its source: its line names the `https://` address where you do;
- where your image is: the image registry, the version tag, and how we may pull it. Never put a token in the order: your partner manager tells you how to send a read-only token safely. We copy that version into your app's own registry with us;
- the plan: Starter, Standard or Managed (below);
- your partner name, and the customer the app is for, if it is built for one.

**Check it first, on your machine.** The same checks we run, and what we would create; it changes nothing:

```bash
python3 tools/deploy_app/deploy_app.py <your app folder> --image <registry>/<repository>:1.0.0 --plan starter --partner <your name>
```

**Order it online** (below), or from your CitiXsys partner manager. A licensed customer's IT team and CitiXsys's own teams, such as the CitiXsys Consulting Team, order hosting the same way. Not an iVendNext Partner yet? Start with the [iVendNext Partner form](https://www.ivendnext.com/partners/apply/).

**What it costs:** a price per app per month, in US dollars (below), covering the copies the plan runs (sandbox, staging). It is billed monthly, in whole months from the month the app goes live, with no minimum term: either side can stop at any month end. Whoever orders the hosting pays: you, or the customer the app is built for when that customer orders it. App Hosting is sold online by CitiXsys Singapore, through Stripe, with its own invoices and receipts, and is never a line on an iVendNext subscription invoice. An app that runs as a function (it only answers presses, or works in short runs) and is listed in the App library carries no hosting charge; a container is always charged. The managed database, when it is offered, is priced separately.

**What you get** (for a container; a function's list is in [A function or a container](14b_deploying_your_app.md#a-function-or-a-container)): the address `https://<app>.ivendnext.app` with its certificate; your secrets kept in our secret store (we ask you for them when the app goes live; they are never in a file); a restart when the health check fails; a firewall that lets in only our load balancer; and no rights in our cloud for your app's code. Your app's log lines are kept for the plan's days, and we send them to you when you ask.

| Plan | Per app, per month | For | What the platform sets |
|---|---|---|---|
| **Starter** | $49 | a till key or check handler, low volume | size small · one instance · logs kept 14 days · a sandbox copy on request |
| **Standard** | $129 | a connected app | small or medium · one instance · logs kept 30 days · a staging copy |
| **Managed** | $399 | apps built by the CitiXsys Consulting Team, and anyone who wants us to run it | any size · two instances · logs kept 90 days · we check the app before it is connected and test it before each iVendNext upgrade, and patch the apps whose source we hold |

**What hosting runs:** your app's service. A hosted app has no database or lasting disk of its own for its data: keep its data in the retailer's own records (your manifest's record types), or in a store of your own. The one table a hosted app has (always for a function; for a container with `"shops": true`) holds each retailer's connection, its address, its secrets and its key's id, encrypted, and a scheduled run's short claims; no retailer's records ([One app, many retailers](14b_deploying_your_app.md#one-app-many-retailers)).

**An app that only answers presses runs as a function**, run only when called, not as an always-on container: see [A function or a container](14b_deploying_your_app.md#a-function-or-a-container) in this chapter.

**A new version:** push it from your GitHub ([Updates from your GitHub](14b_deploying_your_app.md#updates-from-your-github)), or, for an app we put live by hand, send the new version's tag on the same order.

## Order and pay online

One command orders the hosting, signed with the key you already publish to the App library with (`tools/publish`, `keygen`). Your company's hosting account holds its monthly spending cap and how many apps it holds; the web page's *Request access* makes one ([From the web page](#from-the-web-page)). The command also needs your signing key registered in the App library, under your hosting account's code.

```bash
python3 tools/deploy_app/deploy_app.py order <your app folder> --plan starter --partner <your code> \
    --github <owner>/<repository> --github-subject <its sign-in subject prefix> --accept-schedule
```

1. **It checks your app** exactly as planning does (above), and refuses what the hosting refuses.
2. **Name your app under your maker word.** Your app's name is your first word in the App library, or that word and a hyphen: `acme-points` for the maker word `acme`.
3. **You accept the App Hosting Schedule** with `--accept-schedule`: the terms that hosting runs under: [Schedule 1 of the iVendNext Developer Terms](https://legal.ivend.com/ivendnext-developer-terms/), version 1.0 of 2026-10-21. The order carries the Schedule's version.
4. **One order covers the plan's copies, at one price.** Production and its sandbox on Starter, and staging too on Standard and Managed: one subscription at the plan's price, not one per copy. To run fewer, name them: `--copies prod,sandbox`.
5. **You pay.** It prints a Stripe checkout address: pay monthly by card. With `--invoice --email <address>` you get an invoice with payment terms instead; the app is built once the invoice is paid. An app that runs as a function and is listed in the App library carries no charge, so its order needs no payment.
6. **We build it, with no person.** Once it is paid, the hosting makes each copy's address, its own registry or package folder, its secret store and its firewall. `deploy_app.py status --partner <your code>` shows where each copy stands: building, waiting for its secrets, live, held, or stopped, with the reason when one of your versions was refused or did not start, and the date the hosting stops if you cancelled.
7. **Put each secret** your `app.json` marks `"secret": true` (a container), on each copy: `deploy_app.py secret --partner <your code> --order <id> --env sandbox --name <NAME>`, with the value on standard input. Each copy has its own values. It is never shown, never in a file, and kept only in that copy's own secret store.
8. **Push the first version** from your GitHub (below). The app goes live once its image or package and its secrets are there, and its health check answers.

Plain (not secret) settings go on the order: `--set LOG_LEVEL=info`. Each must be a setting your `app.json` names.

**Stopping.** `deploy_app.py cancel --partner <your code> --order <id>` stops the app, every copy, at the end of the month you paid for. If a payment fails and Stripe gives up retrying, the app stops then too. A stopped app keeps what you supplied and its data for 30 days, then is removed.

**If the build fails after you paid,** the payment is refunded, nothing is left half-built, and CitiXsys is told.

## From the web page

The same order runs with no command on the developer site's hosting page, `https://developer.ivendnext.com/hosting`. Every screen of it, with a real example: [Host your app from the web page](../recipes/host_from_the_web_page.md).

1. **Sign in with GitHub,** with your own GitHub account. Your hosting account says which company you order for and what it pays. CitiXsys's own people come straight in. Anyone else, the first time, presses **Request access** and gives the company's name, a work email and a line on what it builds; a CitiXsys person approves it on the same page, which makes your company's hosting account, and the page opens it. **You never need to join our GitHub organisation.** If your GitHub account orders for more than one hosting account, you choose one, and you pay that account's price.
2. **Your app:** pick your repository from your list, or type it, with its branch and the folder that holds `app.json`, and drop in your `app.json`. The page checks it with the hosting and shows the command that checks the Dockerfile, the licence files and the package on your computer.
3. **Your customer** (their code: the one on the customer's *Made for you* shelf; the page offers the ones your earlier orders named), **then the plan, its copies and the App Hosting Schedule,** as with the command. Check the order, then order it.
4. **Pay** in Stripe's checkout, which opens in a new tab, or by an invoice. The page follows the order while you pay.
5. **Follow it to live.** Once it is paid, the page sets your workflow's two Variables on the order's repository (or lists them for you to copy), takes each copy's secrets (each value sent once, never shown), and shows each copy's state until it is live. Then it shows the Publish button and the `publish.py` command that put the app on your customer's shelf. It does not publish. Next, publish the app to that customer's shelf; its administrator installs it from *Made for you* on the customer's site, and your app answers there at its address.
6. **My apps** lists every order with its copies, where each stands, and its plan; cancel one at the end of the paid month from there.

**The page's GitHub App.** To list your repositories and set the Variables, install the *iVendNext App Hosting* GitHub App on your app's repository (the page links it). It can write that repository's Actions variables and nothing else: it never reads your code. Without it, type the repository and set the Variables yourself. Your GitHub sign-in stays on our server and ends when you sign out or after three hours. The page keeps the steps you filled in, in that browser tab, and, while GitHub signs you in, a one-use check value it throws away when you come back; never your sign-in or a secret.

## Updates from your GitHub

Copy [`tools/deploy_app/hosting-workflow.yml`](../tools/deploy_app/hosting-workflow.yml) to `.github/workflows/` in your app's repository and set the variable it names (`IVN_HOSTING_ROLES`, the line `status` prints: one role per copy). Each push to the branch your order names pushes the version in your `app.json` to every copy listed, and the hosting puts it live on each through the same checks as the first one. Each copy gets its own build of the same commit. To try a version on the sandbox first, list only the sandbox's role; when it is right, add the others and run the workflow again by hand: a copy that already has that version is left as it is. No secret is stored in GitHub: GitHub signs each run in to one role of ours, which can push only your app's new version.

- **Raise the version for every release.** A version is never overwritten. To go back, release the earlier code under a new version number.
- **A version above your plan's limits is refused** (a package over 50 MB).
- **The role trusts your repository and branch exactly.** A repository made since 2025 signs in to AWS with a subject that carries its owner's and its own numeric ids: give it with the order, `--github-subject "$(gh api repos/<owner>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix)"`. Then a repository deleted and made again under the same name can never push your app. Without it, the role trusts the older subject, `repo:<owner>/<name>`. If your organisation has changed the subject's other parts, set them back for this repository, or the sign-in is refused.

**The part inside the retailer's iVendNext is separate.** Your manifest reaches each customer's site through its administrator's install screen, with the customer's consent (chapter 14a); `tools/deploy` puts it on your own sandbox. Hosting runs only your outside service. An app that is not a container in this template's shape is a Managed job: ask us.

What the checks refuse, and the technical notes: [`tools/deploy_app`](../tools/deploy_app/README.md).

## One app, three copies

Run the same image as **sandbox**, **staging** and **production**. Each copy has its own iVendNext address, its own API key and its own signing secret. Never share a secret between copies. Use `tools/deploy` to put your manifest on your sandbox; on staging and production the retailer's administrator installs it (chapter 14a). Register each copy's address in that retailer's iVendNext only.

## One app, many retailers

An app listed in the App library is installed by retailers you have never met. Each retailer's install makes its own secrets, so your app has to learn them from iVendNext. It does that with one handshake, and the template has it built in.

- **After the install, the retailer's site connects itself.** It sends your app its library key, its own address and the secrets the install made.
- **Your app checks the key and remembers the retailer.** The key must be signed by iVendNext, for your app, for that site. Nothing else is checked.
- **Every later call names its retailer,** and your app checks it with that retailer's own secret. A retailer your app does not know gets 401, and so does a call signed with another retailer's secret.
- **When the retailer uninstalls your app,** its site says goodbye and your app forgets it.
- **Reinstalling, or pressing *Connect again*, replaces the retailer's secrets.** The old ones keep working while the retailer moves over, like the rotation below, until the next connect. So to stop a leaked secret working, the retailer connects **twice**.
- **What we keep on purpose:** a library key works like a password for its retailer. Whoever holds it can connect as that retailer and replace its secrets. The retailer's next install of your app connects it again. A key that has ended or been withdrawn still connects here (only the retailer's site checks those), so keep keys out of tickets and chats.

**Note.** The site connects by itself only to an app hosted at one `*.ivendnext.app` address (the only such address its manifest names) and installed from the App library: from its public list, or from a customer's *Made for you* shelf. Each time you publish a hosted app to a shelf, the shelf carries that app's own key for the customer's sites that hold the shelf's key. A site the customer adds later gets its key the next time you publish that app to the shelf; a site that installed the app before its key arrived connects once you publish a higher version and the retailer takes the update. For an app on your own server, the retailer's secrets reach you by hand, and you run the template for that one retailer (`IVN_POINT_SECRET`).

To switch the template to many retailers, set `IVN_LIBRARY_APP` to your app's id in the App library, give it a store (`IVN_SHOPS_FILE`, or `"shops": true` in `app.json` on CitiXsys hosting, which makes your app its own encrypted table), and name your till key in `app.py` (`KEY`). On your laptop, `IVN_LOCAL=1` lets an iVendNext site on your own machine connect with a key you sign yourself, in a connect you send yourself (a site connects by itself only to an `*.ivendnext.app` address) ([local mode](../tools/app_template/README.md#local-mode-many-retailers-on-your-laptop)). Sample [S22](../samples/s22_customer_loyalty/README.md) runs this way: one service for every retailer, with a feed poll for each.

**Technical notes**

| Call | What the site sends | Your app answers |
|---|---|---|
| `POST /ivendnext/connect` | header `X-iVendNext-Site: <site>`; body `{"key": "IVN1-…", "site": "<site>", "secrets": {"<name>": "<value>", …}}`, unsigned | `200 {"connected": "<site>"}` · `403 {"refused": "key_form" \| "key_signature" \| "key_other_app" \| "key_other_site"}` · `400 {"refused": "bad_request"}` · `503 {"refused": "unavailable"}` |
| `POST /ivendnext/disconnect` | the same header; body `{"key": "IVN1-…", "site": "<site>"}` | `200 {"disconnected": "<site>"}`, or the refusals above |
| every other call | `X-iVendNext-Site: <site>` beside the signature headers | the call's own answer; `401` for a site it does not know or a signature that is not that retailer's |

- **`<site>`** is the retailer's key address, as the App library shows it (*This site's key address*), in lower case. The header and the body name the same one, and so does the key's `host`. Your app calls iVendNext back at `https://<site>`, never at an address the call names. The one exception is the template's local mode (`IVN_LOCAL=1`, never on hosting): an iVendNext site on your own machine (`localhost`, `<name>.localhost`, `127.0.0.1` or `[::1]`) is named with its port, if it has one, and called back at `http://<site>`.
- **The secrets' names** are the install's own: a till key's secret is `<app>:<key>`, a Desk action's service `<app>:sub:<key>`, a webhook's its name. A user's key is named by this contract: `user:<email>`, with the value `<api key>:<api secret>`. For the app's own feed user the install makes the key at the first connect; any other user's key is sent once the shop has made it (the install never makes it). At most 100, each name up to 200 characters and each value up to 2,048, and the whole call within your app's body limit (the template's is 64 KB).
- **The key check** is `tools/app_template/service/shops.py` `check_key`: the line starts `IVN1-`, its payload is the App library's key (`typ` `applib-key`, `v` 1), its `kid` is one of the two pinned keys and that key may sign its `kind` (`L1` paid keys, `F1` free keys only), its Ed25519 signature verifies, its `app` is `IVN_LIBRARY_APP` and its `host` is the site. The end date and the withdrawn list are not checked: the site checked both at install.
- **Rotation:** a second connect keeps the retailer's previous secrets, and a call signed with either is accepted, so the overlap is one connect long. A third connect drops the first set.
- **When iVendNext adds or retires a public key,** add it to or remove it from `LIBRARY_KEYS` in `shops.py`. A retired key stays trusted by your copy until you remove it.
- **Ed25519 without a package:** `ed25519.py` is RFC 8032's reference code, checked against the RFC's test vector and against a line the App library really signed.

## A function or a container

When CitiXsys hosts your app, it runs in one of two ways. Your code is the same in both.

- **A function** for an app that answers presses (a till key, a check before payment, a webhook), and for an app whose own work comes in short runs: it reads the event feed every minute, or runs a daily job. It runs only when iVendNext calls it or when its schedule does, so it costs nothing in between: a million calls cost us about as much as one always-on container costs in a day.
- **A container** for an app that needs a process that stays up (a connection it holds open, a queue it serves), or a single job longer than 15 minutes. It runs all the time.

**How to choose:** if every piece of work your app does fits in a call of 15 minutes or less, it is a function, on a schedule if it has work of its own. Otherwise it is a container. Sample [S18](../samples/s18_rule_guard/README.md), the members-only rule guard, answers presses as a function. Samples [S22](../samples/s22_customer_loyalty/README.md) (customer-owned loyalty), [S25](../samples/s25_gift_on_spend/README.md) (gift card on spend) and [S3](../samples/s3_price_audit/README.md) (price-deviation audit) read the feed as functions on a schedule.

**A function on a schedule** names its runs in `app.json`: `"schedule": {"pass": "rate(1 minute)"}` runs it once a minute, and `"timeout": 120` lets each run take up to two minutes (900 seconds at most). Each run is one pass of your work. Two runs can overlap, so a run takes a claim on each retailer it works in the shops table first, frees it as soon as that retailer is done, and leaves a retailer another run is still working. Give a daily job the full 900 seconds (S22 does): a run stopped by its limit does not try that day again. A scheduled app is put live by CitiXsys: ordering online does not carry a schedule yet, so `deploy_app.py order` refuses one.

**A function serves many retailers** (the handshake above) and keeps no secret of its own: each retailer hands over its own when it connects, whether it installed your app from the public list or from its *Made for you* shelf. An app that needs its own secret runs as a container.

**Say which in `app.json`:** `"runs": "function"`, with `"handler"` (the file and function the call goes to) and `"package"` (the files it is made from). An app that says nothing runs as a container, exactly as before. `deploy_app` checks it and writes the package; send that file instead of an image.

**Technical notes**

- **The entry:** `tools/app_template/service/function.py` turns the load balancer's call into your app's own `handle(conf, method, path, headers, raw)`, and its answer back. The body reaches the signature check as the exact bytes the retailer signed (base64-decoded when the load balancer sends it so, otherwise the UTF-8 text). Headers are found whatever their case. Your settings and the shops table are opened once per copy, on its first call. In `app.py`: `lambda_handler = function.entry(lambda: settings(os.environ), handle)`.
- **`app.json`:** `"runs": "container"` (the default) or `"function"`. A function also has `"handler"` (for example `service/app.lambda_handler`), `"package"` (relative paths of the files and folders it is zipped from; files whose names start with a dot and `__pycache__` are left out), `"shops": true`, and no variable marked `"secret"`. It needs no `Dockerfile`; one that is present is still checked.
- **What we run:** Python 3.13 on ARM64, 512 MB, a 10-second limit per call (your `"timeout"` on a schedule), at most 10 copies at once (a flood stops there, and so does its cost), behind the same load balancer and address `https://<app>.ivendnext.app`. Its log lines are kept for the plan's days. It has no rights in our cloud except its own shops table.
- **The package:** `python3 tools/deploy_app/deploy_app.py <folder> --zip <file> [--root <folder>] --plan … --partner …` writes the same bytes for the same files, and prints its sha256. `--root` is the folder the package paths start from: for S18, the kit's root, because it uses the template's handshake from there.
- **The first call** of a new copy takes longer than the rest, while it starts. Keep it within your manifest's `timeout_seconds` (S18's check allows 3 seconds).
- **A schedule:** `"schedule"` maps a name (1 to 11 lower-case letters, digits, hyphens) to when it runs, in UTC: `rate(<n> minute(s)|hour(s)|day(s))` or `cron(<minutes> <hours> <day of month> <month> <day of week> <year>)`. Each run calls your function with `{"ivn_schedule": "<name>"}`, and the entry hands the name and the seconds the run has left to your `scheduled(conf, name, seconds)`: `lambda_handler = function.entry(load, handle, scheduled)`. A run that fails is not retried, by the scheduler or by the function service; the next run picks up what it left. The scheduler's role may call your function and nothing else.
- **Claims:** `function.Claimed(store, seconds)` wraps your shops store for one run: its `sites()` lists only the retailers this run claimed, and `release(site)` frees one as soon as its work ends (the samples' `pass_all` calls it through `finished`). A claim lasts the run's own time left plus 30 seconds, so no other run takes a retailer while the run that holds it can still be working. `function.OncePerDay(store, now)` stands in for a container's "ran today" note: the first run to claim a retailer's day runs its daily jobs. S22, S25 and S3 show both.
- **What a run keeps:** nothing between runs, except a copy's `/tmp` while that copy lives. A feed's handled-events note there is only a cache: the feed is a queue on the retailer's side, and each record your app writes is named so that the retailer refuses a second one.

## Updating without breaking a retailer

- **Release the new version beside the old one,** check its health, then move the address to it. Roll back by running the previous version tag.
- **Keep every answer valid for the version iVendNext calls.** A call names its version (the `X-iVendNext-Point` header, or the till key's `User-Agent`): serve the versions you have told retailers you serve.
- **Rotate a secret without a gap.** Set the new secret in the retailer's iVendNext, then set the old one as `IVN_POINT_SECRET_PREVIOUS` and the new one as `IVN_POINT_SECRET` in your app. Both are accepted. Remove the old one after a day.
- **Re-run the customer's release gate** (chapter 14) before each of our upgrades reaches that customer.

## What is refused, and why

- **Code inside the customer's site.** Your logic stays on your server (chapter 3).
- **An address on a private network,** and **plain HTTP,** for a till key. iVendNext calls only a public HTTPS address.
- **A secret in an image or a repository.** The checker above refuses it, and a leaked secret lets anyone call your app as the retailer.

## When your server is down

The retailer keeps selling. A till key shows the cashier *"⟨key⟩ could not finish. Nothing was added to the sale."* A webhook is tried three times and then dropped; your reconciliation pull catches up when you are back (chapter 5). Chapters 5 and 6 list what the cashier reads in each case.

## The tests

Your app is ready to connect when the template's checks pass for your copy, `validate_app.py` says READY, the stand-in caller gets your answer, a call with the wrong secret gets 401, and the first real press from a sandbox shows one clean log line.

## See also

[Security and the handshake](../site/pages/security.md) · [Host with CitiXsys or run your own](../site/pages/hosting.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [6. Till keys](06_till_keys.md) · [14. Testing and release](14_testing_and_release.md) · [14a. Deploying to a chain of stores](14a_deploying_to_a_chain.md) · [A till key](../recipes/point_handler.md)
