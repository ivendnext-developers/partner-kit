# deploy_app — see what CitiXsys hosting would run for your app

If you would rather not run a server, CitiXsys can host your app for you. This command checks your app the way the
hosting service does, and shows what it would create: the address, the size, what your plan includes. **It changes
nothing.** CitiXsys reviews the request and puts the app live.

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

   **An app that only answers presses** (its `app.json` says `"runs": "function"`) is hosted as a function, paid per call: give `--zip <file>` instead of `--image`, and this writes the package to send us (`--root <folder>` when its `package` paths start above the app's folder). Chapter 14b, *A function or a container*.

It prints `PLANNED:` and what would be created, or one `REFUSED:` line per problem. Exit code: 0 planned · 1 refused · 2 usage.

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
- The root filesystem is read-only. If your app writes temporary files, say so in your request.
- A function gets the same address, Python 3.13 on ARM64 with 512 MB, at most 10 copies at once, its own shops table, and no other rights. The block it prints uses the hosting's `modules/function`; the package is copied into the hosting's code bucket as `<app>/<version>.zip`, never overwritten.
- The last thing it prints is the block CitiXsys adds to its hosting infrastructure; you do not need it.
- Standard library only. It reuses the template's checker (`../app_template/validate_app.py`), never a copy.
