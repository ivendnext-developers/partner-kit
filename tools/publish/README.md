# publish — put your app in the App library from any computer

One command checks your project's `library/` folder, signs it with your company's key and uploads it to the iVendNext App library (`https://library.ivendnext.app`). It runs on your laptop or on any build server, with or without GitHub. **We take only the files in `library/`: never your source code.** The developer site's [*Publish your app*](../../site/pages/publish.md) page says what happens to each version and what a retailer sees.

Standard library only (Python 3.10+). Exit code: 0 published (or waiting for our approval) · 1 refused · 2 usage.

## Once: your signing key

```bash
python3 tools/publish/publish.py keygen
```

It writes `~/.ivendnext/library-signing.key` (readable by you only; `--key <file>` to keep it elsewhere) and prints one line, `ivn-ed25519:…`, with its key id. Send that line to iVendNext through Help or your account manager, with your `recipient.pem` and the first word you would like for your company: every app you name under it is yours (`ACME LOYALTY` → `acme_loyalty`), with no reservation. The line is public; the file is not. Back the file up: a lost key means registering a new one.

## Each version

```bash
python3 tools/publish/publish.py publish <your project> --partner <your company's code>
```

1. It runs the kit's checks over `<your project>/library` (`tools/check/check.py`) and the licence check over the project (`tools/check/licence.py`). A refusal stops it: nothing is sent.
2. It reads `library/app.json`, `manifest.json`, `library.json` and `recipient.pem`, and your customers' sites and key requests from `LIBRARY_DELIVERIES` / `LIBRARY_KEYS` or `--deliveries` / `--keys` (JSON; never from your project).
3. It signs the exact bytes it sends, with a time and a one-time number inside them, and uploads them. The library checks the signature before it reads anything, refuses an upload sent twice or more than 5 minutes old, and then applies its own rules.
4. It prints what the library did: your preview shelf, each customer's shelf, the public list (`WAITING for iVendNext's approval` the first time, or when a version does more than the last), the keys. **Keys are written to `library-keys.json`, readable by you only, never printed.**

`--dry-run` checks and signs, prints what would be sent, and sends nothing. `--partner` is your company's code; the library already knows it from your key, and asks for it so that a key used for the wrong company is refused rather than published.

On a build server, put the key file's line in the build system's secrets as `IVN_LIBRARY_KEY`; the command reads it from there when `--key` is not given.

## Opening a key

Each entry in `library-keys.json` holds `sealed`: blocks of base64 joined by `.`, each encrypted to your `recipient.pem` (RSA-OAEP with SHA-256). Open one with your private key:

```bash
for part in $(echo "<the sealed value>" | tr '.' ' '); do
  echo "$part" | openssl base64 -d -A | openssl pkeyutl -decrypt -inkey recipient-private.pem \
    -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
done; echo
```

It prints `{"host": …, "to": …, "key": …}`: the site the key is for, who it names, and the key to send that site's administrator.

## On Windows

Run it with `py -3` where these pages say `python3`. `openssl` comes with Git for Windows (`C:\Program Files\Git\usr\bin\openssl.exe`) or WSL. Windows does not take the Unix file modes the command sets, so keep `library-signing.key`, `recipient-private.pem` and `library-keys.json` in your own user folder.

## If something is refused

The command prints the library's code and its words, for example `REFUSED by the library (403): not_your_app — this app's name is not yours: it is not under your company's first word or reserved to it`. The *Publish your app* page lists the refusals you are most likely to meet. If your computer's clock is off by more than 5 minutes, every upload is refused as `stale`: set the clock and run it again. `not_your_key` means `--partner` is not the code your key is registered to.
