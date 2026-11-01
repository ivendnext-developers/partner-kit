# deploy_app — plan, order and run your app on CitiXsys App Hosting

If you would rather not run a server, CitiXsys can host your app for you. This command checks your app the way the
hosting service does, and shows what it would create: the address, the size, what your plan includes. **Planning
changes nothing.** Then `deploy_app.py order …` orders it online, signed with your publishing key and paid through
Stripe, and the hosting builds it with no person ([Order online](#order-online)).

**It is for** a builder whose app follows the template in [`../app_template/`](../app_template/README.md) (guide
[chapter 14b](../../guide/14b_deploying_your_app.md)) and who wants it hosted by CitiXsys instead of on their own cloud.

## Use it

1. Check your app with the template's checker first: `python3 tools/app_template/validate_app.py <your app folder>`.
2. Build your image **for ARM64** (`docker build --platform linux/arm64`) and tag it with the version in your `app.json` (for example `1.0.0`). Never `latest`.
3. See the plan:

   ```bash
   python3 tools/deploy_app/deploy_app.py <your app folder> --image <registry>/<repository>:1.0.0 --plan starter --partner <your name>
   ```

   A staging copy: add `--env staging`. As JSON: add `--json`.

   **An app that only answers presses** (its `app.json` says `"runs": "function"`) is hosted as a function, run only when called: give `--zip <file>` instead of `--image`, and this writes the package to send us (`--root <folder>` when its `package` paths start above the app's folder). Chapter 14b, *A function or a container*.

It prints `PLANNED:` and what would be created, or one `REFUSED:` line per problem. Exit code: 0 planned · 1 refused · 2 usage.

## Order online

```bash
python3 tools/deploy_app/deploy_app.py order <your app folder> --plan starter --partner <your code> --accept-schedule
python3 tools/deploy_app/deploy_app.py push <your app folder> --partner <your code> --order <id>
python3 tools/deploy_app/deploy_app.py back --partner <your code> --order <id> --to <earlier version>
python3 tools/deploy_app/deploy_app.py status --partner <your code>
python3 tools/deploy_app/deploy_app.py secret --partner <your code> --order <id> --env sandbox --name IVN_POINT_SECRET   # value on stdin
python3 tools/deploy_app/deploy_app.py cancel --partner <your code> --order <id>
```

- `order` runs the planning checks, then sends one request signed with your App library key (`tools/publish`
  `keygen`, default `~/.ivendnext/library-signing.key`, or `--key`, or `IVN_LIBRARY_KEY`). It prints a Stripe checkout
  address, or with `--invoice --email <address>` says an invoice is on its way. Plain settings: `--set NAME=VALUE`, each
  one your `app.json` names. One order runs every copy the plan has (production and its sandbox, and staging on
  Standard and Managed) at the plan's one price; fewer: `--copies prod,sandbox`. `--dry-run` sends nothing. An order
  names no GitHub repository: each version is uploaded (`push`).
- Your app's name starts with your maker word (`acme` → `acme-points`).
- Once it is paid, the hosting builds each copy; `status` shows each copy's state (building, waiting for its
  secrets, live, a version refused or one that did not start, held, stopped), its address, the versions it has had, and
  the latest upload's build: *Building 1.0.1…*, *Building 1.0.1… Built.*, or, when it did not build, the hosting's
  words and the build's last 50 lines. Secrets are set per copy (`secret --env <copy>`).
- `push` zips the app's folder (every file but `.git`, `.env…` files, `.samples` and `__pycache__`; a function: its
  `app.json` and its package, from `--root` as `--zip` reads it; the same bytes for the same files), asks
  the hosting for the upload's address with a signed request to `https://hosting.ivendnext.app/v1/upload`, and uploads
  the zip there. The hosting builds it on its side for every copy: a container's image for ARM64 from its Dockerfile,
  or a function's package from its `package` paths (inside the folder), zipped as `--zip` does. Raise `app.json`'s
  `"version"` for each upload; a version is never built twice. An upload over its limit is refused before anything is
  built (a function's package 50 MB, a container's image 1,024 MB).
- `back --to <earlier version>` puts an earlier version live again under a new, higher number (the next one after your
  newest, or `--version`): the hosting copies that version's image or package; nothing is built.
- Exit code: 0 done · 1 refused · 2 usage. The signed request uses its own signing domain
  (`ivendnext-hosting-order/1`), so it can never be replayed as a library upload, nor an upload as an order.

## The plans

| Plan | For | The platform sets |
|---|---|---|
| **Starter** | a till key or check handler, low volume | size small · one instance · logs kept 14 days |
| **Standard** | a connected app | size small or medium · one instance · logs kept 30 days · a staging copy |
| **Managed** | apps built by the CitiXsys Consulting Team, and anyone who wants us to run it | any size · two instances · logs kept 90 days · CitiXsys checks the app before it is connected, tests it before each iVendNext upgrade, and patches the apps whose source it holds (monitoring and on-call: not offered yet) |

What each plan includes, and what is not offered yet, is in [`plans.json`](plans.json), with each plan's price per app per month in US dollars (`price_usd_month`) and how it is billed (`billing`). This tool prints no price.

## What is refused, and why

- **An image tagged `latest`, or with a tag other than your app's version.** What runs must be what your settings file says.
- **A size your plan does not allow,** and a region we do not serve yet (other countries' regions on request).
- **A reserved name** (such as `admin`, `api` or `www`), and a name ending in `-staging`, `-sandbox` or `-prod`, which would take another app's address.
- **A function given an image, or no `--zip`,** and a `package` path that is not in the folder it starts from.
- **Everything the template's checker refuses:** a container that runs as root, no health check, a secret in the image, a value in `app.json`.

## Technical notes

- Your app gets `https://<app>.ivendnext.app` (or `https://<app>-<env>.ivendnext.app`), a container on ARM64 with the size's CPU and memory, a firewall that admits only our load balancer, its own image registry and secrets, and no rights in our cloud.
- Secrets you mark `"required": true` are asked for when the app is put live; an optional one (such as `IVN_POINT_SECRET_PREVIOUS`) is added when you rotate.
- The root filesystem is read-only. An app that writes working files says `"scratch": true` in `app.json`: it gets a writable `/scratch`, lost when the container restarts, and runs as one copy, stopped before its new version starts (so not on Managed, which runs two). Its image makes `/scratch` itself, owned by its user, and declares it a `VOLUME`.
- A function gets the same address, Python 3.13 on ARM64 with 512 MB, at most 10 copies at once, its own shops table, and no other rights. The block it prints uses the hosting's `modules/function`; the package is copied into the hosting's code bucket as `<app>/<version>.zip`, never overwritten.
- The last thing planning prints is the block CitiXsys adds to its hosting infrastructure for an app put live by hand; an online order needs none of it.
- Standard library only. It reuses the template's checker (`../app_template/validate_app.py`), never a copy.
