# Publish your app

Make your app, try it on your sandbox, send it to your customer and list it for every retailer, on [My apps](https://developer.ivendnext.com/apps) or with the `ivn` command. New to it? [Build your first app](first_app.md) takes you from a sample to your customer in six steps.

## The steps

**Make it.** On My apps, **New app**, or from a terminal:

```bash
ivn new acme_bins --from s2
```

It makes one app from one sample or several.

**Try it on your sandbox.** On My apps, **Try on my sandbox**, or `ivn try`. It shows what installing it changes, installs it on your sandbox and tests each connection. Trying is free, and it asks for no key, no plan and no card. No sandbox yet? [Request one](sandbox.md).

**Publish it to a customer.** On My apps, **Publish**, then **To a customer**, or:

```bash
ivn publish --to retailer.ivendnext.com
```

It puts the version on the customer's own shelf and prints the message to send their administrator, with the key in it. An app that CitiXsys hosts connects by itself when the customer installs it. Add a site later with the same command.

**List it for every retailer.** On My apps, **Publish**, then **To everyone**, or:

```bash
ivn publish --public
```

It lists the app in the [App library](https://library.ivendnext.app). The first time, the listing waits for one approval by us; the command says so. The card's fields go in `app.json`'s `card`: you are asked once. For the guide link, any https page will do: your repository's README is enough. A later version is listed at once, unless it does more than the one before (a new outside address, an outside service with its own user), which waits for one approval again.

A version that has reached a customer never changes: any change to what it installs is a higher version.

## What a retailer sees

Each listed app has a card in the App library: what it does, who uses it, whether it is free or needs a key, whether anything leaves the retailer's iVendNext, the industries it is for, and a link to the app's guide. Browse the cards at [library.ivendnext.app](https://library.ivendnext.app).

The retailer's administrator presses **Install**, reads what it will change, ticks **I agree** and presses **Install**. Everything the app adds is on from that moment, for every store, and they give their staff the roles. Only what is theirs to decide waits, and the install screen lists it. A paid app asks for its key first.

## What it costs

- **Trying:** free.
- **An app with no service of ours** (lists, fields, workflows, Desk settings): free. We run nothing for it.
- **An app with a service we host,** per month: Starter $49, Standard $129, Managed $399. Billed monthly by card; cancel at any month end. Production for a customer may be ordered by the customer through their account team.
- **One that runs only when called** (a till key, a check at Pay, a webhook), once it is listed in the App library: free, all its copies, sandbox included. The billing stops at its next renewal, and nothing already paid is refunded. Until it is listed, it pays its plan.
- **An app on your own server:** nothing to us. Run the folder at any public https address (`ivn package` writes `package.zip` for your own function host).

## More you can do

- **Copy and sell one of our apps.** Most apps iVendNext lists in the App library start as working code in this kit, and each such app's page links that code: copy it, change it, put your company's name on it, and sell it. [Build your business on iVendNext's apps](business.md).
- **Publish from a build server.** `ivn token new <name>` makes a token, shown once; on the server it goes in `IVN_TOKEN`. A token you lose is revoked on My apps > Tokens, in one press.
- **Go back to an earlier version.** `ivn rollback <version>` publishes an earlier version's content as a new, higher version. It asks for the app's name first, and each customer's administrator presses **Update**.
- **Keep your copy up to date.** `ivn pull` brings in the server's latest draft and keeps your changes. `ivn take <sample>` takes a sample's newer version.
- **Hand the app to another company.** `ivn handover <word>` asks for the app's name first; the other company accepts on their My apps, and their card pays from the next month.
- **Everything else `ivn` does** is in [its README](../../tools/ivn/README.md).
