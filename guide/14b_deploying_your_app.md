# 14b. Deploying your app

How to run your own service so a shop can reach it: what it must do, how to package it, where it can run, and how to update it without breaking a shop.

**For:** a builder whose work includes an outside app (chapters 5 and 6): a service that answers a till key, reads the event feed, or reacts to a webhook, and must run on a server a shop can reach.
**Reference implementation:** [`../tools/app_template/`](../tools/app_template/README.md) — a small service, a Dockerfile, a settings file and a checker, ready to copy.

## The short answer

- **Your app runs on a server you choose,** in any cloud or on your own machines. Nothing of yours is installed in the customer's shop (chapter 3, rule 3).
- **The shop calls your app over HTTPS** (a till key, a Desk button, a webhook) and **your app calls the shop's API** with the key you were given. Till keys and Desk buttons are extension points (chapter 9).
- **Package it as a container.** One image runs the same on your laptop, on a test copy and in production.
- **Or let CitiXsys host it.** Send us the image and its settings file, never your source; we run it at `https://<app>.ivendnext.app` ([below](#let-citixsys-host-it)).
- **The shop checks nothing about where you run it.** It checks your answers: the signature, the time to answer and the shape of the reply.

## When to use it

When your app is ready to leave your laptop: before a shop's sandbox calls it for the first time, and again for each customer's production.

## What every deployable app does

1. **Has a public HTTPS address with a valid certificate.** The shop checks the certificate against your host name, and an address that resolves to a private network is refused (`recipes/point_handler.md`).
2. **Answers inside the time.** A till key has 3 seconds unless the shop raises it, 10 at most. Do the slow work before the call, or after it.
3. **Verifies every call before it reads it.** The signature is `base64(HMAC-SHA256(secret, "<timestamp>.<raw body>"))` over the raw body, and a timestamp more than five minutes from your clock is refused. Answer a body over 64 KB with 413.
4. **Keeps secrets out of the image and the repository.** The signing secret and the API key arrive as environment variables from the host's secret store.
5. **Has a health address** (`/health`) that answers without a signature and says nothing about shops.
6. **Logs one line per call:** the request id, the status and the milliseconds. Never the body, the sale, the customer, the secret or the signature.
7. **Is safe to run twice.** A webhook is tried three times and then dropped, and a call can arrive again. Handle each event so a repeat changes nothing, and run a reconciliation pull on a schedule (chapter 5).
8. **Stops cleanly.** A host stops a container with a termination signal: finish the call in hand, then exit.

The template does all eight. Replace its `core.py` with your logic and keep the rest.

## Steps

1. **Copy the template** folder to your own repository and rename the app in `app.json`.
2. **Run it on your laptop** and test it without a shop:

   ```bash
   python3 -m unittest discover -s tools/app_template/tests -p 'test_*.py' -v
   ```

   ```bash
   IVN_POINT_SECRET=any-long-random-string docker compose up --build
   ```

   For many shops against a shop's site on your own machine (`http://shop.localhost:8000`, say), use the template's local mode, `IVN_LOCAL=1` ([the template's README](../tools/app_template/README.md#local-mode-many-shops-on-your-laptop)).

3. **Call it the way the till does** with the stand-in caller (`tools/standin_caller/`), which signs a call and judges the answer as the remote till key does.
4. **Check the settings file and the Dockerfile:**

   ```bash
   python3 tools/app_template/validate_app.py
   ```

   It refuses a container that runs as root, has no health check, exposes a port the settings file does not name, or has a secret baked into it; and a settings file with a value in it.
5. **Publish the image** to a container registry you control, with a version tag (`1.0.0`), never only `latest`.
6. **Run the image on a host** (below) with the settings from `app.json`.
7. **Tell the shop where you are.** Put your HTTPS address and the signing secret in the shop's record for the key, the webhook or the feed (chapters 5 to 7). `tools/deploy` prints a generated secret once: store it in your host's secret store the same minute.
8. **Call it once from the shop** (press the key, or send a test webhook) and read your log line.

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
| Region | near the shop's site, and where the customer's data may live |
| Restart | automatic, on a failed health check |

A managed container service in your own cloud account is the least work. A small server running `docker compose` also works. If your app keeps its own data, give it its own database with daily backups, and write down how you restore it.

## Let CitiXsys host it

If you would rather not run a server, CitiXsys runs your app for you on our own cloud, beside iVendNext. **Your code stays in your own repository.** We never need your source code or access to your code repository: we run the image you build.

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

**Order it** from your CitiXsys partner manager. A licensed customer's IT team and CitiXsys's own teams, such as the CitiXsys Consulting Team, order hosting the same way. Not an iVendNext Partner yet? Start with the [iVendNext Partner form](https://www.ivendnext.com/partner/#be-a-partner).

**What it costs:** a price per app per month, in US dollars (below), covering the copies the plan runs (sandbox, staging). It is billed monthly, in whole months from the month the app goes live, with no minimum term: either side can stop at any month end. Whoever orders the hosting pays: you, or the customer the app is built for when that customer orders it. App Hosting is billed on its own, never as a line on an iVendNext subscription invoice. An app that only answers presses and is listed in the App library carries no hosting charge. The managed database, when it is offered, is priced separately.

**What you get** (for a container; a function's list is in [A function or a container](14b_deploying_your_app.md#a-function-or-a-container)): the address `https://<app>.ivendnext.app` with its certificate; your secrets kept in our secret store (we ask you for them when the app goes live; they are never in a file); a restart when the health check fails; a firewall that lets in only our load balancer; and no rights in our cloud for your app's code. Your app's log lines are kept for the plan's days, and we send them to you when you ask.

| Plan | Per app, per month | For | What the platform sets |
|---|---|---|---|
| **Starter** | $49 | a till key or check handler, low volume | size small · one instance · logs kept 14 days · a sandbox copy on request |
| **Standard** | $129 | a connected app | small or medium · one instance · logs kept 30 days · a staging copy |
| **Managed** | $399 | apps built by the CitiXsys Consulting Team, and anyone who wants us to run it | any size · two instances · logs kept 90 days · we check the app before it is connected and test it before each iVendNext upgrade, and patch the apps whose source we hold |

**What hosting runs:** your app's service. A hosted app has no database or disk of its own: keep its data in the shop's own records (your manifest's record types), or in a store of your own.

**An app that only answers presses runs as a function**, paid per call, not as an always-on container: see [A function or a container](14b_deploying_your_app.md#a-function-or-a-container) in this chapter.

**A new version:** send the new version's tag on the same order.

**The part inside the shop is separate.** Your manifest reaches each customer's site through its administrator's install screen, with the customer's consent (chapter 14a); `tools/deploy` puts it on your own sandbox. Hosting runs only your outside service. An app that is not a container in this template's shape is a Managed job: ask us.

What the checks refuse, and the technical notes: [`tools/deploy_app`](../tools/deploy_app/README.md).

## One app, three copies

Run the same image as **sandbox**, **staging** and **production**. Each copy has its own shop address, its own API key and its own signing secret. Never share a secret between copies. Use `tools/deploy` to put your manifest on your sandbox; on staging and production the shop's administrator installs it (chapter 14a). Register each copy's address in that shop only.

## One app, many shops

An app listed in the App library is installed by shops you have never met. Each shop's install makes its own secrets, so your app has to learn them from the shop. It does that with one handshake, and the template has it built in.

- **After the install, the shop's site connects itself.** It sends your app its library key, its own address and the secrets the install made.
- **Your app checks the key and remembers the shop.** The key must be signed by iVendNext, for your app, for that site. Nothing else is checked.
- **Every later call names its shop,** and your app checks it with that shop's own secret. A shop your app does not know gets 401, and so does a call signed with another shop's secret.
- **When the shop uninstalls your app,** its site says goodbye and your app forgets it.
- **Reinstalling, or pressing *Connect again*, replaces the shop's secrets.** The old ones keep working while the shop moves over, like the rotation below, until the next connect. So to stop a leaked secret working, the shop connects **twice**.
- **What we keep on purpose:** a library key works like a password for its shop. Whoever holds it can connect as that shop and replace its secrets. The shop's next install of your app connects it again. A key that has ended or been withdrawn still connects here (only the shop's site checks those), so keep keys out of tickets and chats.

⚠ The site connects by itself only to an app hosted at an `*.ivendnext.app` address and installed from the App library. For an app on your own server, or one delivered on a customer's *Made for you* shelf, the shop's secrets reach you by hand, and you run the template for that one shop (`IVN_POINT_SECRET`).

To switch the template to many shops, set `IVN_LIBRARY_APP` to your app's id in the App library, give it a store (`IVN_SHOPS_FILE`, or `"shops": true` in `app.json` on CitiXsys hosting, which makes your app its own encrypted table), and name your till key in `app.py` (`KEY`). On your laptop, `IVN_LOCAL=1` lets a shop's site on your own machine connect with a key you sign yourself ([local mode](../tools/app_template/README.md#local-mode-many-shops-on-your-laptop)). Sample [S22](../samples/s22_customer_loyalty/README.md) runs this way: one service for every shop, with a feed poll for each.

**Technical notes**

| Call | What the site sends | Your app answers |
|---|---|---|
| `POST /ivendnext/connect` | header `X-iVendNext-Site: <site>`; body `{"key": "IVN1-…", "site": "<site>", "secrets": {"<name>": "<value>", …}}`, unsigned | `200 {"connected": "<site>"}` · `403 {"refused": "key_form" \| "key_signature" \| "key_other_app" \| "key_other_site"}` · `400 {"refused": "bad_request"}` · `503 {"refused": "unavailable"}` |
| `POST /ivendnext/disconnect` | the same header; body `{"key": "IVN1-…", "site": "<site>"}` | `200 {"disconnected": "<site>"}`, or the refusals above |
| every other call | `X-iVendNext-Site: <site>` beside the signature headers | the call's own answer; `401` for a site it does not know or a signature that is not that shop's |

- **`<site>`** is the shop's key address, as the App library shows it (*This site's key address*), in lower case. The header and the body name the same one, and so does the key's `host`. Your app calls the shop back at `https://<site>`, never at an address the call names. The one exception is the template's local mode (`IVN_LOCAL=1`, never on hosting): a shop on your own machine (`localhost`, `<name>.localhost`, `127.0.0.1` or `[::1]`) is named with its port and called back at `http://<site>`.
- **The secrets' names** are the install's own: a till key's secret is `<app>:<key>`, a Desk action's service `<app>:sub:<key>`, a webhook's its name. An integration user's key is named by this contract, since the install makes none today: `user:<email>`, with the value `<api key>:<api secret>`. At most 100, each name up to 200 characters and each value up to 2,048, and the whole call within your app's body limit (the template's is 64 KB).
- **The key check** is `tools/app_template/service/shops.py` `check_key`: the line starts `IVN1-`, its payload is the App library's key (`typ` `applib-key`, `v` 1), its `kid` is one of the two pinned keys and that key may sign its `kind` (`L1` paid keys, `F1` free keys only), its Ed25519 signature verifies, its `app` is `IVN_LIBRARY_APP` and its `host` is the site. The end date and the withdrawn list are not checked: the site checked both at install.
- **Rotation:** a second connect keeps the shop's previous secrets, and a call signed with either is accepted, so the overlap is one connect long. A third connect drops the first set.
- **When iVendNext adds or retires a public key,** add it to or remove it from `LIBRARY_KEYS` in `shops.py`. A retired key stays trusted by your copy until you remove it.
- **Ed25519 without a package:** `ed25519.py` is RFC 8032's reference code, checked against the RFC's test vector and against a line the App library really signed.

## A function or a container

When CitiXsys hosts your app, it runs in one of two ways. Your code is the same in both.

- **A function** for an app that only answers presses: a till key, a check before payment, a webhook. It runs only when a shop calls it, so it costs nothing in between: a million calls cost us about as much as one always-on container costs in a day.
- **A container** for an app with work of its own: it reads the event feed, runs daily jobs, or keeps state between calls. It runs all the time.

**How to choose:** if your app does nothing until a shop calls it, it is a function. If it does anything on its own, it is a container. Sample [S18](../samples/s18_rule_guard/README.md), the members-only rule guard, runs as a function. Sample [S22](../samples/s22_customer_loyalty/README.md), customer-owned loyalty, reads the feed, so it stays a container.

**A function serves many shops** (the handshake above) and keeps no secret of its own: each shop hands over its own when it connects. An app that needs its own secret runs as a container. ⚠ A shop that cannot connect itself (above), such as one your app reaches through its *Made for you* shelf, cannot hand a function its secrets: host a one-shop app as a container.

**Say which in `app.json`:** `"runs": "function"`, with `"handler"` (the file and function the call goes to) and `"package"` (the files it is made from). An app that says nothing runs as a container, exactly as before. `deploy_app` checks it and writes the package; send that file instead of an image.

**Technical notes**

- **The entry:** `tools/app_template/service/function.py` turns the load balancer's call into your app's own `handle(conf, method, path, headers, raw)`, and its answer back. The body reaches the signature check as the exact bytes the shop signed (base64-decoded when the load balancer sends it so, otherwise the UTF-8 text). Headers are found whatever their case. Your settings and the shops table are opened once per copy, on its first call. In `app.py`: `lambda_handler = function.entry(lambda: settings(os.environ), handle)`.
- **`app.json`:** `"runs": "container"` (the default) or `"function"`. A function also has `"handler"` (for example `service/app.lambda_handler`), `"package"` (relative paths of the files and folders it is zipped from; files whose names start with a dot and `__pycache__` are left out), `"shops": true`, and no variable marked `"secret"`. It needs no `Dockerfile`; one that is present is still checked.
- **What we run:** Python 3.13 on ARM64, 512 MB, a 10-second limit per call, at most 10 copies at once (a flood stops there, and so does its cost), behind the same load balancer and address `https://<app>.ivendnext.app`. Its log lines are kept for the plan's days. It has no rights in our cloud except its own shops table.
- **The package:** `python3 tools/deploy_app/deploy_app.py <folder> --zip <file> [--root <folder>] --plan … --partner …` writes the same bytes for the same files, and prints its sha256. `--root` is the folder the package paths start from: for S18, the kit's root, because it uses the template's handshake from there.
- **The first call** of a new copy takes longer than the rest, while it starts. Keep it within your manifest's `timeout_seconds` (S18's check allows 3 seconds).

## Updating without breaking a shop

- **Release the new version beside the old one,** check its health, then move the address to it. Roll back by running the previous version tag.
- **Keep every answer valid for the version the shop calls.** A call names its version (the `X-iVendNext-Point` header, or the till key's `User-Agent`): serve the versions you have told shops you serve.
- **Rotate a secret without a gap.** Set the new secret in the shop, then set the old one as `IVN_POINT_SECRET_PREVIOUS` and the new one as `IVN_POINT_SECRET` in your app. Both are accepted. Remove the old one after a day.
- **Re-run the customer's release gate** (chapter 14) before each of our upgrades reaches that customer.

## What is refused, and why

- **Code inside the customer's site.** Your logic stays on your server (chapter 3).
- **An address on a private network,** and **plain HTTP,** for a till key. The shop calls only a public HTTPS address.
- **A secret in an image or a repository.** The checker above refuses it, and a leaked secret lets anyone call your app as the shop.

## When your server is down

The shop keeps selling. A till key shows the cashier *"⟨key⟩ could not finish. Nothing was added to the sale."* A webhook is tried three times and then dropped; your reconciliation pull catches up when you are back (chapter 5). Chapters 5 and 6 list what the cashier reads in each case.

## The tests

Your app is ready to connect when the template's checks pass for your copy, `validate_app.py` says READY, the stand-in caller gets your answer, a call with the wrong secret gets 401, and the first real press from a sandbox shows one clean log line.

## See also

[Security and the handshake](../site/pages/security.md) · [Host with CitiXsys or run your own](../site/pages/hosting.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [6. Till keys](06_till_keys.md) · [14. Testing and release](14_testing_and_release.md) · [14a. Deploying to a chain of stores](14a_deploying_to_a_chain.md) · [A till key](../recipes/point_handler.md)
