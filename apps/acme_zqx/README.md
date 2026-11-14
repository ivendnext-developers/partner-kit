# ACME ZQX

Lucky draw: one app made by New app from 1 sample of the iVendNext partner kit (S44 Lucky draw). Its names start with `ACME ZQX` and `acme_zqx`.

## What is in this folder

| Folder or file | What it is |
|---|---|
| `service/ldw/` | Lucky draw |
| `service/app.py` | the one service: it sends each call to its sample's part, under `/<tag>/` |
| `manifest.json` | the lists, fields, keys and points the site installs |
| `app.json` | the app's name, version, settings and card |
| `tests/` | each sample's own tests, under this app's names (`tests/<tag>/`), and the app's own (`tests/test_app.py`) |
| `service/_kit/` | the kit's helpers the service needs, copied, so this folder runs on its own |
| `LICENSE`, `THIRD_PARTY.md` | your app's licence, and the notices of what it was made from |

## What you can change safely

Your own code in `service/`, the titles and words in `manifest.json`, the card.

## What to leave alone

Names already installed at a site; the samples record in `app.json`; `service/_kit/`. *Add a sample* keeps what you changed, and stops and says what when it would have to change it.

## Run it on your laptop

Nothing to install: the samples use Python's standard library.

```
python3 -m unittest discover -s apps/acme_zqx/tests
python3 apps/acme_zqx/service/app.py --local
```

It reads test values from .env.local, which New app wrote for you; put your own outside keys there. It answers on http://localhost:8000.

## Run it on your own server

For one that runs only when called: `ivn package` writes `package.zip` for your own function host. It reads these settings: `IVN_LIBRARY_APP`: Your app's id in the App library, like acme_pts for the prefix ACME PTS. Give it a public https address and put that address on Where the service runs.

## Change it with your AI assistant

Change it with your AI assistant: open your copy of the kit in it. It reads AGENTS.md, which knows this folder.
