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

  On Windows, add `partner-kit\tools\ivn` to your `Path`; `ivn` then runs `ivn.cmd`. If you would rather not use a terminal, [My apps](https://developer.ivendnext.com/apps) does every step below in your browser. For step 3 it gives you the folder to download, and takes it back with **Upload a new version**.

## The six steps

### 1. Sign in

On [My apps](https://developer.ivendnext.com/apps), press **Sign in with GitHub**. In a terminal:

```bash
ivn login
```

It opens your browser. The first time only, set up your company: press **Set up my company**, give its name as retailers will see it, take the first word we suggest for your apps (for example `acme`), tick the Hosting Schedule and press **Continue**. Then press **Sign the command in**.

### 2. Make the app from a sample

Start from the [sample](../../samples/) nearest your customer's need. Here it is [S11](../../samples/s11_approvals/README.md), the Purchase Order approval. On My apps: **New app**, tick the sample, **Next**, **Make the app**. In a terminal, from any folder:

```bash
ivn new acme_po_approval --from s11
cd apps/acme_po_approval
```

The name starts with your company's word, and everything in the sample that carried the sample's name now carries yours. In `manifest.json`, `app` is that name and `prefix` is the same words in capitals: `ACME PO APPROVAL`. To put several samples in one app, name them all: `--from s11 --from s22`.

You now have a folder with `manifest.json` (your app), `app.json` (its name, its version and its card in the App library), `tests/` and a `README.md` saying what is in it. `service/` is there for apps that run code. S11 runs none: leave it, and we host nothing for it.

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
     "allowed": "Purchase Manager", "condition": "doc.base_grand_total > 50000"},
    {"state": "Draft", "action": "Submit", "next_state": "Approved",
     "allowed": "Purchase User", "allow_self_approval": 1, "condition": "doc.base_grand_total <= 50000"}
  ]
}]
```

- `document_type` is the record type the workflow runs on. Your customer's own Purchase Order is fine.
- `doc_status` is what a state does to the document: 0 keeps it a draft, 1 submits it, 2 cancels it. So approving this order submits it.
- `allowed` is the role that may press the action. A role the site does not have is made at install, empty, for the customer to give to staff. `condition` decides when the action is offered: `base_grand_total` is the order's total in the company's currency. Nobody may take a step on a document they raised unless the step says `"allow_self_approval": 1`: the buyer's *Submit* needs it, and the approver's *Approve* must not have it.
- `send_email_alert` mails whoever may act next. There is no separate *send for approval* step: as soon as the buyer saves an order over the amount, it is waiting for the approver.

Make your change: your customer's amount, say, in the `condition` of *Approve*, *Reject* and *Submit*. The sample's `README.md` lists what a partner usually changes, and links a recipe when you want to go further. It names the sample's own records with the sample's prefix (`PP TGR Settings`); in your app they carry yours.

Other things you can add here, each one a list in the same file: `custom_fields`, `property_setters` (relabel, hide or require a field), `notifications`, `print_formats`, `naming_rules`, `list_settings`, `doctypes` (a record type of your own). The manifest recipe has [a table of them all](../../recipes/manifest.md). A field on the customer's record type starts with your app's prefix and looks like this:

```json
"custom_fields": [{"dt": "Purchase Order", "fieldname": "acme_po_approval_budget_code", "fieldtype": "Data",
                   "label": "Budget code", "reqd": 1, "insert_after": "supplier"}]
```

And a mail to the person who raised the order, with its print, once it is submitted:

```json
"notifications": [{"name": "ACME PO APPROVAL Submitted", "document_type": "Purchase Order", "event": "Submit", "channel": "Email",
                   "subject": "Purchase Order {{ doc.name }} is submitted", "message": "{{ doc.supplier }}: {{ doc.grand_total }}",
                   "recipients": [{"receiver_by_document_field": "owner"}], "attach_print": 1}]
```

### 4. Check it

```bash
ivn check
```

It runs the checker your customer's install runs on your manifest, then the app's own tests, and gives one line: `CHECK GREEN` and how many tests passed. If something is refused, it says which entry and why.

### 5. Try it on your sandbox

On My apps, **Try on my sandbox**. In a terminal:

```bash
ivn try
```

It uploads your folder, shows what installing it changes, installs it on your sandbox and tests any connection it has. Trying is free. It asks you nothing: no key, no plan, no card.

Now use it. Your sandbox came with an administrator's login, a manager's and two cashiers'. As the administrator, make a **Supplier** if there is none, and on each person's **User** record give *Purchase User* to the one who will be your buyer and *Purchase Manager* to your approver. Sign in as the buyer and raise a Purchase Order over the amount; then sign in as the approver, open it, and under **Actions** press **Approve**. It reads *Approved* and it is submitted. A sandbox sends no mail, so you will not see the mail.

Changed something? Run `ivn try` again. Each try is a new version. Once a field is installed, an update cannot change its type or make it newly required: add a new field instead, and `ivn try` says so if you forget.

### 6. Publish it to your customer

On My apps, **Publish**, then **To a customer**. In a terminal:

```bash
ivn publish --to retailer.ivendnext.com
```

Publishing S11 is free. It puts the version on your customer's shelf and prints the message to send their administrator, with the key in it. Nothing changes on their site until they install it. If your app has a service we host, this is where its plan starts: see below.

## The customer installs it

Your customer's administrator, in iVendNext Desk:

1. Opens **App library** and presses **Open your shelf** at the foot of the page.
2. Pastes the key from your message and presses **Open your shelf** again.
3. Presses **Install** on your app, reads what it will change, ticks **I agree** and presses **Install**.

That is the whole install, one consent and one press. Everything the app adds is on from that moment, for every store: its workflow, its fields, its service if it has one, its Desk buttons, and its till key on every store's till. Only what is the customer's to decide waits, and the install screen lists it: someone to hold a save rule's role, a fiscal reader's keys, a payer's clearing account, a pricing module's limit, a register book's warehouses, a till theme for a POS Profile that has none.

Then they give their staff the roles, on each person's **User** record. In S11 those are the roles a purchasing team holds already, so there may be nothing to do.

If you list your app free for every retailer, there is no shelf and no key: they press **Install** on its card in the App library. Your next version reaches them when you publish it, and they take it the same way.

## What a listed app costs

To list your app for every retailer: on My apps, **Publish**, then **To everyone**, or `ivn publish --public`. You are asked once for what goes on its card (title, one line, what it does, pictures, industries, price, guide link; your repository's README is enough for the guide), and the first version waits for one approval by us. See [Publish your app](publish.md).

- **Trying:** free.
- **An app with no service of ours,** like S11: free. We run nothing for it.
- **An app with a service we host,** per month: Starter $49, Standard $129, Managed $399. Billed monthly by card; cancel at any month end.
- **One that runs only when called,** once it is listed in the App library: free, all its copies, sandbox included. The billing stops at its next renewal, and nothing already paid is refunded. Until it is listed, it pays its plan.
- **An app on your own server:** nothing to us. Run the folder at any public https address.

On its card an app is free or needs a key. For a paid app you make each customer's key with `ivn key <site>`, and what you charge them is between you.

## What an app may not do

Only four things, and the checker tells you in its own words when you meet one:

- **Book a wrong money, tax, stock or fiscal figure.** A default or a precision on the customer's own field of a record that posts. A workflow state that writes one of the customer's own fields. Numbering rules on the sale's own records. A field you add to a customer's record type that does not start with your prefix, because iVendNext could read it as one of its own flags.
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
