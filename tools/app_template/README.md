# The app template — a service you can deploy

A small service that does what every deployable app does ([guide chapter 14b](../../guide/14b_deploying_your_app.md)): it checks each call's signature and time, answers inside the deadline, logs one line per call without shop data, has a health address, runs as a user that is not root, stops cleanly, and refuses to start without its signing secret. It answers one remote till key (`POST /point/hello`) so you can see the whole path. Standard library only.

**It is for** a builder who has an outside app (chapters 5 and 6) and wants it running on a server a shop can reach. Copy this folder, replace `service/core.py` with your own logic, and keep the rest.

**One shop or many.** Run it for one shop with that shop's secret (`IVN_POINT_SECRET`). Or, for an app in the App library, run it for many: each shop connects itself after its install, and every call is checked with that shop's own secret ([chapter 14b, One app, many shops](../../guide/14b_deploying_your_app.md#one-app-many-shops)). A library key works like a password for its shop: whoever holds it can connect as that shop and replace its secrets, and the shop's next install connects it again.

| File | What it is |
|---|---|
| `service/core.py` | **your logic**: a pure function, `answer(context)`, no web code, no shop |
| `service/app.py` | the web part: signature check, size cap, health address, one log line per call, clean stop, secret rotation |
| `service/shops.py` | many shops: the handshake (`/ivendnext/connect`, `/ivendnext/disconnect`), the library key check, and the shops kept in a file |
| `service/function.py` | on CitiXsys hosting, an app that only answers presses runs as a function, paid per call: this turns the load balancer's call into `handle` and back (chapter 14b, *A function or a container*) |
| `service/dynamo.py` | on CitiXsys hosting: the shops kept in the app's own encrypted table, with the standard library only |
| `service/ed25519.py` | the key's signature check (RFC 8032's reference code), so the template needs no package |
| `Dockerfile` · `docker-compose.yml` | the container, and a one-command run on your laptop |
| `app.json` | the settings file: name, port, health address, size, region and the **names** of the environment variables. Never a value |
| `validate_app.py` | checks `app.json` and the `Dockerfile` before you deploy |
| `local_key.py` | local mode: a key pair of your own, and a library key it signs for a shop on your machine |
| `tests/` | the service, the handshake and the checker, with no cloud and no shop; `canaries.py` removes each check of the handshake and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s tools/app_template/tests -p 'test_*.py' -v
```
```bash
python3 tools/app_template/tests/canaries.py
```
```bash
IVN_POINT_SECRET=any-long-random-string docker compose up --build
```
```bash
python3 tools/app_template/validate_app.py
```
As a function on CitiXsys hosting (`app.json` `"runs": "function"`, many shops): see what would be created, and write the package to send:
```bash
python3 tools/deploy_app/deploy_app.py tools/app_template --zip my-app-1.0.0.zip --plan starter --partner <your name>
```

Then call it with the stand-in caller (`tools/standin_caller/`) at `http://localhost:8080/point/hello` with the same secret. A call with any other secret gets 401.

## Settings (environment variables)

| Name | Needed | What |
|---|---|---|
| `IVN_POINT_SECRET` | one shop | the signing secret you and the shop both hold |
| `IVN_POINT_SECRET_PREVIOUS` | no | the old secret, accepted while you rotate (chapter 14b) |
| `IVN_LIBRARY_APP` | many shops | your app's id in the App library. The key a shop connects with must name it |
| `IVN_SHOPS_FILE` | many shops, not hosted | a file the app may write, where it keeps the shops and their secrets (readable by the app's user alone) |
| `IVN_SHOPS_TABLE` | many shops, hosted | set by CitiXsys hosting when `app.json` says `"shops": true` |
| `IVN_LOCAL` | no | `1`: local mode (below). Never with `IVN_SHOPS_TABLE` |
| `IVN_LOCAL_LIBRARY_KEYS` | no, local mode only | the public keys file `local_key.py keygen` wrote |
| `PORT` | no | default 8080 |

The app does not start without one of `IVN_POINT_SECRET` or `IVN_LIBRARY_APP` (with its store). Secrets come from your host's secret store, or from each shop at connect. They are never in the image, the repository or `app.json`.

## Local mode: many shops on your laptop

A shop's site on your own machine (a local bench at `http://shop.localhost:8000`, say) has no certificate and a port, so the
handshake would refuse it and the app would call it back at `https://`. With `IVN_LOCAL=1` and the file store, a shop
on this machine (`localhost`, `<name>.localhost`, `127.0.0.1` or `[::1]`, with or without a port) may connect, and the
app, and every sample built on this template, calls it back over plain `http`. Every other site keeps `https` and the two
pinned keys, and local mode refuses to start with the hosting's table. A shop connected in local mode is ignored when the
app runs without it.

The App library signs keys only for real sites, so you sign your own, with a key pair that is accepted for a shop on this
machine and no other:

```bash
python3 tools/app_template/local_key.py keygen --out .local-keys
python3 tools/app_template/local_key.py sign --secret .local-keys/library.secret \
    --app ivendnext_hello --site shop.localhost:8000          # prints the "IVN1-…" key the shop connects with
IVN_LOCAL=1 IVN_LIBRARY_APP=ivendnext_hello IVN_SHOPS_FILE=shops.local.json \
    IVN_LOCAL_LIBRARY_KEYS=.local-keys/library_keys.json python3 tools/app_template/service/app.py
```

**You send the connect yourself.** A shop's site connects by itself only to an app at an `*.ivendnext.app` address, so
a site on your machine never calls your laptop's app. Send the call it would send, with the key you signed and the
secrets its install made: the till key's secret (Desk shows it once, on the till key's record), named
`<IVN_LIBRARY_APP>:<KEY>` (`KEY` in `app.py`), and, if your app calls the shop back, its user's key, named `user:<email>`
with the value `<api key>:<api secret>` (chapter 14b, *The handshake*):

```bash
curl -s http://localhost:8080/ivendnext/connect -H 'X-iVendNext-Site: shop.localhost:8000' \
    -H 'Content-Type: application/json' \
    -d '{"key": "IVN1-…", "site": "shop.localhost:8000", "secrets": {"ivendnext_hello:hello": "<the till key secret>"}}'
```

The same call to `/ivendnext/disconnect`, with the same `X-iVendNext-Site` header and the body without `secrets`, forgets
the shop.

Your key pair and the shops file hold secrets, so they never go to git: the template's own `.gitignore` (and
`.dockerignore`) keeps `.local-keys/` and `*.local.json` out, but only inside your app's own folder. In your copy, run these commands from
that folder (`python3 local_key.py …`, `python3 service/app.py`), so the files land where it ignores them; in this
repository, its root `.gitignore` covers them. `keygen` refuses to replace a pair it made before unless you add `--force`, since every key the old pair
signed stops working.

For one shop you need none of this: `IVN_POINT_SECRET`, and a sample's `IVN_SHOP_URL=http://localhost:8000`, already
work on your laptop.

## Technical notes

- The signature check is the one in `samples/s6_ai_till_key/service.py` (a defect there is a defect here).
- The answer follows the published remote till key contract (`contracts/`); the tests check it.
- `app.json` is the input a host reads to run your image: port, health address, size, region, which variables to supply, and `shops` (true: the hosting makes the app its own shops table). `runs` says how CitiXsys hosts it: a `container` (the default) or a `function` (an app that only answers presses, many shops, no secret of its own), which also names its `handler` (`service/app.lambda_handler`) and its `package` (`["service"]`).
- `service/app.py`'s `handle` answers every call; the web server and the function entry (`lambda_handler`) both call it, so the two ways of running behave the same.
- Many shops: the till key's secret is the one the install made, named `<IVN_LIBRARY_APP>:<KEY>` (`KEY` in `app.py`, your manifest's `remote_keys[].key`). Another of the shop's secrets does not sign this route.
- The public keys `L1` and `F1` in `shops.py` are the ones the POS app pins. When iVendNext adds a key, add it here too; when iVendNext retires one, remove it here, or your copy keeps trusting it.
- A connect replaces the shop's secrets and keeps the old ones until the next connect, so a leaked secret stops working after the shop connects twice.
