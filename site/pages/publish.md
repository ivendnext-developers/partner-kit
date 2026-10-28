# Publish your app

**Starting from one of our apps?** Copy it, make it your customer's, and sell it as yours: [Build your business on iVendNext's apps](business.md).

This site helps you **build** an app. The **App library** (`https://library.ivendnext.app`) is where retailers **find** it and install it from iVendNext Desk. You publish it yourself, with one command from any computer (your laptop or your own build server, with or without GitHub, whatever language your app is written in), or [from the web page](#from-the-web-page) in your browser, with no command at all.

**We take only your app's files for the library:** its manifest and its card (and, if CitiXsys hosts your app, its built image). We never take or keep your source code, and your repository stays wherever you keep it.

## How it works

1. **Make your signing key, once.** On your computer, from the kit's folder:

   ```bash
   python3 tools/publish/publish.py keygen
   ```

   It keeps the private half in `~/.ivendnext/library-signing.key` and prints one line starting `ivn-ed25519:`. That line is public.
2. **We register your company once.** Send us, through Help (`https://help.ivendnext.com`) or your account manager: your company's name as retailers see it, the line `keygen` printed, your `recipient.pem` (below) and the first word you would like for your company (for example `acme`: letters and digits, starting with a letter, 2 to 12 in all; not one that is ours or another company's, and not one of the 22 words iVendNext's checker refuses as a prefix's first word, listed on the save rules page: `is`, `for`, `set`, `base`, `free`, `price` …). We give each company its own word, once, and a company registered before we gave words asks for its word through Help; you then name every app under it yourself (`ACME LOYALTY` becomes `acme_loyalty`), with no wait on us, and no other company can take a name under it. The *App listing request* form is for your first app's listing; send the key line and `recipient.pem` through Help, not in the form.
3. **You publish.** From your project's folder:

   ```bash
   python3 <the kit>/tools/publish/publish.py publish . --partner <your company's code>
   ```

   It runs the kit's checks on your `library/` folder and your licence files, signs what it sends with your key, and uploads it. Nothing is sent if a check refuses. Or publish [from the web page](#from-the-web-page), with the same files and keys.
4. **Your preview shelf** has the version at once. Only the test sites you name see it: each one opens it with its shelf key, pasted once under *App library > Open your shelf*.
5. **The App library, for every retailer:** your app is listed with your company as its maker.
   - **The first time**, the listing waits for one approval by us. The command says so, with the request's id.
   - **A later version** is listed at once, unless it does more than the one before: a new outside address, an outside service with its own user, or more Desk users. That waits for one approval again.
6. **An app made for one customer** goes to that customer's own *Made for you* shelf, with **no approval by us**. Their administrator pastes the shelf key you send them, once on their test site and once on their live site, and agrees to each install.
   - **An app hosted by CitiXsys** carries its own key for the customer's sites on the shelf, so the site connects it by itself, as an app from the public list. A site the customer adds later gets its key the next time you publish that app to the shelf; a site that installed the app before its key arrived connects once you publish a higher version and the retailer takes the update.
   - **A site can hold several shelves**, from several companies: each opens with its own shelf key and shows as its own section. Your app takes its updates only from your shelf.

A listed version never changes: any change, even a word, is a higher version with a changelog line.

## What goes in your project

- **A `library/` folder** — the only files the command uploads:
  - `app.json`, the card: title, one-line summary, category, who uses it, changelog, **and what a retailer needs to set the app up and find its guide** (the next section);
  - `manifest.json`, your app;
  - `library.json`: `{"public": true, "preview_sites": ["your-test-site.staging.ivendnext.com"]}` (`public: false` for an app made for one customer only);
  - `recipient.pem`, your sealing key's public half, so keys reach only you. Make the pair with `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out recipient-private.pem`, then `openssl pkey -in recipient-private.pem -pubout -out library/recipient.pem`. Keep `recipient-private.pem` out of the project. On Windows, `openssl` comes with Git for Windows or WSL, and `python3` is `py -3`.
- **A licence file and a list of third-party components** at your project's root: `LICENSE` (your choice of licence; the App library shows it on your card) and `THIRD_PARTY.md`, one line per component your app ships with its licence, or `None`. The command refuses a project without them, or with an empty one (`tools/check/licence.py`).

## What a retailer must be able to read

A retailer decides from your card and finds its way from your guide, so the library lists an app only when both can help. **Write them before you publish,** in a retailer's words, for the owner or the manager.

- **Setup steps on the card.** `details` in `app.json`: one lead sentence, at least one point under **what** the app does, **at least one step under setup** (what a retailer does after the install, in the order it meets it, naming the Desk screen as a retailer searches for it), and notes.
- **The industries it is for.** `industries` in `app.json`, required on a public card. Either `["all"]`, for an app every retailer can use, standing alone, or **one to six** of these industries, for an app made especially for them: `fashion`, `grocery`, `pharmacy`, `beauty-and-cosmetics`, `electronics-and-phones`, `hardware-and-diy`, `liquor-and-wine`, `hospitality`, `travel-retail`, `distribution-and-warehousing`, `optical`, `thrift-and-resale`. Your app then shows on each of those industries' pages in the App library, and your company shows as a partner who builds for them. Name an industry only where your app is especially used; a card for one customer's shelf needs none.
- **A guide page.** `docs` in `app.json` links it. It has five headings, in this order: **What it does** · **What you set up first** · **Where it shows** · **What leaves your iVendNext** · **How to remove it**. An app that adds three or more screens a retailer opens gets a **section** of pages, with a heading for each screen. The docs site also groups every app as an **App** (it adds records a retailer works in every day, or a screen of its own) or a **Rule** (it adds one check, field or layout to a screen the retailer already uses, with only the settings it needs). Say which yours is when you describe the app in the listing request.
- **An address for each screen.** Each record type your manifest adds, other than a table inside another, has one `documentation` property setter at its page and heading. The install makes only the roles that start with your prefix.
- **Where the page lives.** The library accepts a guide address on `docs.ivendnext.com`, `developer.ivendnext.com`, `help.ivendnext.com` or `www.ivendnext.com`. Send the page's text with your listing request ([the form](../../feedback/app_listing.md)); we put it on the docs site and send you its address. Until you have it, publish with `"public": false` in `library.json`: that goes to your preview shelf and is not checked this way; a `public: true` upload is checked before anything is written.

The shapes, the template and the exact words are in the manifest recipe, [*What a retailer reads: the card and the guide*](../../recipes/manifest.md).

## Your customers' sites and your keys

Never in your project or the kit: give them to the command from the environment or from a file you name.

- **A customer's shelf:** `LIBRARY_DELIVERIES` (or `--deliveries <file>`), for example `[{"customer": "shop-a", "name": "Shop A", "sites": ["shop-a-test.staging.ivendnext.com", "shop-a.ivendnext.com"]}]`.
- **Remembered for the next update:** after a publish that names customers, your computer keeps that list for the app (in `~/.ivendnext/deliveries/`, beside your signing key, readable by you only), and a later publish with no list includes those customers and says how many. A list you give replaces it; `--no-remembered-deliveries` publishes to none. So an update with the command cannot leave a customer on the old version because you forgot to name them, as long as every publish keeps that one file up to date (the web page offers you the updated file to save over it). A build server has no such folder between runs: keep the customers in `LIBRARY_DELIVERIES` there. The web page remembers nothing: give it that file ([From the web page](#from-the-web-page)).
- **Keys:** every app is free unless you choose `access: key`; a retailer then presses *Get a free key* in its Desk. For an app that needs a key, `LIBRARY_KEYS` (or `--keys <file>`), for example `[{"app": "acme_bins", "host": "shop-a.ivendnext.com", "to": "customer:shop-a", "expires": "2027-10-31"}]`. Keys are issued for your own apps only.
- **Keys and shelf keys come back sealed** to your `recipient.pem`. With the command they go to `library-keys.json` (readable by you only), never on the screen: open each with your private key (`tools/publish/README.md` has the command). On the web page they are opened in your browser with your private key and shown once, each with a copy button. Send each to its customer.

## From the web page

You can publish without a command. The App library's **Publish** page, at `https://library.ivendnext.app/publish`, does in your browser what the command does on your computer: it signs your app with your company's key, puts it on your preview shelf, on each customer's shelf you name and, if you choose, on the public list, and opens the keys that come back so you can give each one to its customer.

{{publish: button}}

- **What you give it:** the files in your project's `library/` folder (`app.json`, `manifest.json`, `library.json`, `recipient.pem`), your licence file and your list of third-party components, your partner code, your signing key file (`library-signing.key`, which the command's `keygen` wrote in `~/.ivendnext/`) and, when keys will come back (a preview site, a customer or a key request), your sealing key's private half (`recipient-private.pem`, as `openssl genpkey` made it; a file with a passphrase cannot be used). It needs a browser that signs with Ed25519: Chrome or Edge 137 or later, Firefox 129 or later, or Safari 17 or later.
- **Your keys stay in your browser.** The page reads each key file once, keeps a key it cannot read back, and sends only the signed upload, to the App library itself. Nothing is stored: leaving the page forgets everything, keys included. The page's code is served by the App library, and it is what holds your keys while you publish; if you would rather no served code ever held them, publish with the command.
- **What it checks:** the App library checks every upload the same way, from the page or the command: your key, the manifest, the rules a shop's install applies, your card. The page checks your licence files itself; it sends neither. It does not show the manifest checker's warnings, which never stop a publish: run the kit's `tools/check/check.py` for those.
- **Your customers on an update.** The command remembers the customers of your last publish that named them; the page remembers nothing. Give the page this app's remembered customers file, `~/.ivendnext/deliveries/<partner>.<app>.json`, and it names any customer in it you leave out before you publish (it refuses another app's file). After the publish it offers the updated file: save it as that same file (make the folder if it is not there; on a Mac or Linux, `chmod 600` it, as the command keeps it), so the command and the page keep one list. Without the file the page cannot tell which customers your earlier publishes reached, and says so: a customer you leave out stays on the old version. A publish to no customer at all needs a tick, so it is never by omission.
- **The keys are shown on the page,** each once, with a copy button and who it is for: give each site key to that customer's administrator, who pastes it under *App library > Open your shelf*. Copy them before you leave the page; publishing the same version again returns the same keys.
- **If the page cannot read the answer** (the library was busy, or the connection dropped), it says it does not know whether the app was published: publish again, and the keys come back the same.

## From a build server

The same command runs in any build system. Keep the key's line (the content of `~/.ivendnext/library-signing.key`) in the build system's secrets as `IVN_LIBRARY_KEY`, and the customers' sites as `LIBRARY_DELIVERIES` and `LIBRARY_KEYS`. Keep `library-keys.json` out of anything others can read.

## What we check, and what we refuse

Our service checks your app again when you publish, whatever your computer says. The refusals you are most likely to meet:

- a key we did not register to your company, a `--partner` that is not the code your key is registered to, or an upload changed after it was signed;
- an upload sent twice, or with a time more than 5 minutes from ours (check your computer's clock);
- an app name not under your company's first word (nor reserved to you before you had one);
- a card whose maker is another company;
- a version that is not the manifest's;
- a version lower than, or the same as, one already listed with other content;
- a site address that is not an iVendNext site;
- a `recipient.pem` other than the one we registered (ask us to register the new one);
- more than 10 sites, 10 customers or 20 keys in one upload.

Each refusal is printed by the command, or shown on the web page, in words. A public listing is also refused, in these words, when it cannot help a retailer (`<app>` is your app's name; the recipe has the same table):

- `help_details`: *<app>: the card must say what the app does and how to set it up: details needs a lead, at least one point under what and at least one step under setup* (with ` (in es)` or ` (in ar)` added when that language is the short one);
- `help_guide`: *<app>: the card must link its guide: docs is one to six {title, url} addresses on docs.ivendnext.com, developer.ivendnext.com, help.ivendnext.com, www.ivendnext.com*;
- `help_nothing_leaves`: *<app>: the card says nothing leaves the shop, but the app has <an outside address (host) · webhooks · till keys · event feeds · extensions · print formats · label layouts · an outside service that signs in to read and write>: say what it sends or runs outside, or take that line out*;
- `help_roles`: *<app>: a setup step tells the shop to create the app's own roles ('<the step>'): the install makes them, so say which roles the install adds and make the step giving them to people*;
- `help_record_guide`: *<app>: the record type <name> has no guide address: add a property setter {doc_type: '<name>', property: 'documentation', value: <https address of its page in your guide>} on docs.ivendnext.com, developer.ivendnext.com, help.ivendnext.com, www.ivendnext.com* (and, when a setter exists but its address is off those hosts, ` (its address '<value>' is not https on one of them)`).

A public card with no industries is refused as `bad_entry`: *<app>: a public card names its industries: industries is ["all"] for every retailer, or one to six of fashion, grocery, pharmacy, beauty-and-cosmetics, electronics-and-phones, hardware-and-diy, liquor-and-wine, hospitality, travel-retail, distribution-and-warehousing, optical, thrift-and-resale*. A card naming an industry not in that list, or `all` beside another, is refused the same way.

A guide address on any other site is refused as `bad_entry`.

## If your key is lost or copied

Tell us at once through Help. We register a new key for your company, and the old one stops working the moment we do. We confirm every new or changed key (signing key or `recipient.pem`) with your company's registered contact, and read its key id back to you, before we register it. You can hold up to three keys (one per build server, say) and we remove any of them on request.

## What a retailer sees

Each listed app has a card in the App library: what it does, who uses it, whether it is free or needs a key, whether anything leaves the retailer's iVendNext, the industries it is for, **the steps a retailer takes first, and a link to the app's guide**. Browse the cards at [library.ivendnext.app](https://library.ivendnext.app).
