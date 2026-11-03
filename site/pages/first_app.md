# Build your first app

From one of the kit's samples to your customer's App library in six steps. This page is all you need to read: it builds the commonest first app there is, an approval on a Purchase Order, and every other sample goes the same way.

**What an app is.** A file, `manifest.json`, that says what to add to your customer's iVendNext: workflows, fields, roles, notifications, print formats, Desk screens. An app may do anything your customer's administrator can do in iVendNext Desk, on the customer's own record types too. You need a service of your own only when the app has to run code. This one does not.

## Before you start

- **A GitHub account.** You sign in with it. No account? Make a free one in two minutes with any e-mail.
- **A sandbox site** to try your app on: your own iVendNext site, full of made-up demo data. [Request a sandbox](sandbox.md). It is ready for you when it arrives: there is no key to paste.
- **For the `ivn` command,** also your copy of the kit and Python 3.10 or newer:

  ```bash
  git clone https://github.com/ivendnext-developers/partner-kit.git
  export PATH="$PWD/partner-kit/tools/ivn:$PATH"
  ```

  On Windows, add `partner-kit\tools\ivn` to your `Path`; `ivn` then runs `ivn.cmd`. If you would rather not use a terminal, [My apps](https://developer.ivendnext.com/apps) does every step below in your browser, except the change in step 3, which you make in the folder it lets you download.

## The six steps

### 1. Sign in

On [My apps](https://developer.ivendnext.com/apps), press **Sign in with GitHub**. In a terminal:

```bash
ivn login
```

It opens your browser; press **Sign the command in**. The first time only, set up your company: press **Set up my company**, give its name as retailers will see it, take the first word we suggest for your apps (for example `acme`), tick the Hosting Schedule and press **Continue**.

### 2. Make the app from a sample

Start from the [sample](../../samples/) nearest your customer's need. Here it is [S11](../../samples/s11_approvals/README.md), the Purchase Order approval. On My apps: **New app**, tick the sample, **Next**, **Make the app**. In a terminal, from any folder that is a git repository or an empty one:

```bash
ivn new acme_po_approval --from s11
cd apps/acme_po_approval
```

The name starts with your company's word. To put several samples in one app, name them all: `--from s11 --from s22`.

You now have a folder with `manifest.json` (your app), `app.json` (its name, its version and its card in the App library), `tests/` and a `README.md` saying what is in it. If the app has a `service/` folder, it is there for the samples that run code. S11 runs none, so we host nothing for it.

### 3. Change it

Open `manifest.json`. This is the part that matters in S11:

```json
"workflows": [{
  "name": "ACME PO APPROVAL Purchase Order Approval",
  "document_type": "Purchase Order",
  "send_email_alert": 1,
  "states": [
    {"state": "Draft",    "doc_status": 0, "allow_edit": "Purchase User"},
    {"state": "Approved", "doc_status": 1, "allow_edit": "Purchase Manager"}
  ],
  "transitions": [
    {"state": "Draft", "action": "Approve", "next_state": "Approved",
     "allowed": "Purchase Manager", "condition": "doc.grand_total > 50000"}
  ]
}]
```

- `document_type` is the record type the workflow runs on. Your customer's own Purchase Order is fine.
- `doc_status` is what a state does to the document: 0 keeps it a draft, 1 submits it, 2 cancels it. So approving this order submits it.
- `allowed` is the role that may press the action. `condition` decides when the action is offered.
- `send_email_alert` mails whoever may act next.

Make your change: your customer's amount, say, in the `condition` of *Approve* and *Reject* and of *Submit*. The sample's `README.md` lists what a partner usually changes, and each sample's page links a recipe when you want to go further.

Other things you can add here, each one a list in the same file: `custom_fields` (a field on the customer's record type; its name starts with your app's prefix, so `acme_po_approval_budget_code`), `property_setters` (relabel, hide or require a field), `notifications`, `print_formats`, `naming_rules`, `list_settings`, `doctypes` (a record type of your own). The manifest recipe has [a table of them all](../../recipes/manifest.md).

### 4. Check it

```bash
ivn check
```

It runs the same checker your customer's install runs, and the app's own tests, and gives one line: `CHECK GREEN · 6 tests run, 6 passed`. If you changed the amount, S11's tests still pass: they read the number from your manifest. If something is refused, the line says which entry and why.

### 5. Try it on your sandbox

On My apps, **Try on my sandbox**. In a terminal:

```bash
ivn try
```

It uploads your folder, shows what installing it changes, installs it on your sandbox and tests any connection it has. Trying is free. It asks you nothing: no key, no plan, no card.

Now use it. Sign in to your sandbox as the buyer and raise a Purchase Order over the amount; then sign in as the approver, open it and press **Approve**. It reads *Approved* and it is submitted. Give the roles first if you need to: on each person's **User** record in Desk, *Purchase User* for the buyer and *Purchase Manager* for the approver.

Changed something? Run `ivn try` again. Each try is a new version.

### 6. Publish it to your customer

On My apps, **Publish**, then **To a customer**. In a terminal:

```bash
ivn publish --to retailer.ivendnext.com
```

Publishing is free. It puts the version on your customer's shelf and prints the message to send their administrator, with the key in it. Nothing changes on their site until they install it.

## The customer installs it

Your customer's administrator, in iVendNext Desk:

1. Opens **App library** and presses **Open your shelf** at the foot of the page.
2. Pastes the key from your message and presses **Open your shelf** again.
3. Presses **Install** on your app, reads what it will change, ticks **I agree** and presses **Install**.

That is the whole install, one consent and one press. Everything the app adds is on from that moment, for every store: its workflow, its fields, its service if it has one, its Desk buttons, and its till key on every store's till. A save rule limited to a role stays off until the customer names the role.

Then they give their staff the roles, on each person's **User** record. In S11 those are the roles a purchasing team holds already, so there may be nothing to do.

If you list your app for every retailer, there is no key: they press **Install** on its card in the App library. Your next version reaches their shelf when you publish it, and they take it the same way.

## What a listed app costs

To list your app for every retailer: on My apps, **Publish**, then **To everyone**, or `ivn publish --public`. You are asked once for what goes on its card (title, one line, what it does, pictures, industries, price, guide link; your repository's README is enough for the guide), and the first version waits for one approval by us. See [Publish your app](publish.md).

- **Trying and publishing:** free.
- **An app with no service of ours,** like S11: free. We run nothing for it.
- **An app that runs only when called,** once listed in the App library: free, all its copies, sandbox included. If it was already billing, the billing stops at its next renewal, and nothing already paid is refunded.
- **An app that runs all the time, or on a schedule of its own,** per month: Starter $49, Standard $129, Managed $399. Billed monthly by card; cancel at any month end.
- **An app on your own server:** nothing to us. Run the folder at any public https address.

The price your app sells for is yours to set on its card.

## What an app may not do

Only four things, and the checker tells you in its own words when you meet one:

- **Book a wrong money, tax, stock or fiscal figure.** A default or a precision on a field of a record that posts. A workflow state that writes one of the customer's own fields. Numbering rules on the sale's own records. A field you add to a customer's record type that does not start with your prefix, because iVendNext could read it as one of its own flags.
- **Stop the till saving a sale, the day's close or a new customer.** A workflow on the till's own records (POS Invoice, the day's opening and closing, Customer, and what the till books). A required, unique or limited field on them. A notification or a webhook condition that runs inside their save.
- **Send the customer's data somewhere they did not see.** A webhook or a service reaches only an https address the consent shows. Notifications go to the customer's own people, by role or by a field of the record, never to an address written in the manifest. A print format that loads from outside or runs raw queries. A report that runs SQL.
- **Let someone act as someone else, or run code in the customer's saves or browser.** Server scripts, client scripts, web pages, script reports, HTML fields, JavaScript in a display condition.

Everything else, iVendNext itself checks when the install saves it, in its own words. The full list, with the reason for each refusal, is [What an app may not do](../../contracts/pages/what_an_app_may_not_do.md).

## Where next

- [Samples](../../samples/): 61 working apps to start from.
- [What customers need](../../needs/README.md): a customer's need, and the sample or recipe that answers it.
- [The extension points](map.md): everything an app can plug into, at the till and in Desk.
- [Publish your app](publish.md): listing it, going back a version, a build server, handing the app over.

Stuck, or found something wrong on this page? [Tell us](feedback.md#open-a-form).
