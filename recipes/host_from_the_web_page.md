# Host your app from the web page, screen by screen — the recipe

You can have CitiXsys run your app's outside service with no command: on the developer site's hosting page you sign in with GitHub, say which repository and app, name the customer, choose a plan, pay, and watch the app go live. This recipe walks every screen of that page with a real example, so you know what each box wants before you reach it. It is for anyone whose company has a hosting account with CitiXsys: an iVendNext Partner, a licensed customer's IT team, CitiXsys's own teams.

**The example.** A company whose maker word is `acme` hosts the kit's S18 sample, started as `ACME RLG`, for its customer `acme-stores`. Put your own names where the example has `acme`.

## Before you start

Have these four things ready. The page asks for each one.

1. **Your app, made with the kit.** For the example, from the kit's folder:

   ```bash
   python3 tools/manifest/start.py s18_rule_guard --prefix "ACME RLG"
   ```

   It makes the folder `apps/acme_rlg` in your repository, with the app's `app.json` in it.
2. **Your app in a GitHub repository made from the kit** (your copy of the kit, where `start.py` put the app), with the kit's workflow copied in: `tools/deploy_app/hosting-workflow.yml` goes to `.github/workflows/` in that repository. For the example, the repository is `acme/acme-apps`.
3. **The iVendNext App Hosting GitHub App installed on that repository:** open `https://github.com/apps/ivendnext-app-hosting/installations/new`, choose your account or organisation, choose *Only select repositories*, tick the repository, and press **Install**. The App can write the repository's Actions variables and nothing else; it never reads your code. With it, the page lists your repository, fills in its sign-in subject and sets its Variables for you.
4. **Your settings' values and the customer's code.** Your `app.json` names your app's plain settings; the page shows each with a line saying what it is. The customer's code is the one its *Made for you* shelf goes by in the App library: the code you name when you publish to that customer. Ask your account team if you do not have it.

If your GitHub login is not yet linked to your company's hosting account, the page says so when you sign in: ask your partner manager to link it.

## The page, screen by screen

Open `https://developer.ivendnext.com/hosting`. The form is at the top, under *Order hosting from this page*. After each **Next**, the page brings the next step into view.

### Sign in with GitHub

1. Press **Sign in with GitHub**. The first time, GitHub asks you to authorise *iVendNext App Hosting*: press **Authorize**.
2. Back on the page, the box says **Signed in as** your GitHub login **for** your company. If your login orders for more than one company, choose it under **You order for** and press **Use this one**. What you pay is that company's price.

### 1. Your app

3. **Repository:** choose `acme/acme-apps` from the list. Not in the list? Type it in **Or type it** and press Tab. The page looks it up and fills in **Its sign-in subject**. If it cannot see the repository, it says so: check the name, or install the App on it and press **Look again**, or paste the line the command it shows prints on your computer.
4. **Branch:** `main`, or the branch your workflow pushes from.
5. **Folder that holds app.json:** `apps/acme_rlg`
6. **app.json:** press **Choose file** and pick `apps/acme_rlg/app.json`, or paste the file's text into the box.
7. The page shows the app's name, version and kind, then one box per setting. For the example, the two marked **(required)**:
   - **Setting IVN_LIBRARY_APP (required):** `acme_rlg` (the id you publish the app under in the App library)
   - **Setting RGD_PREFIX (required):** `ACME RLG` (the prefix you gave `start.py`)

   Leave the others empty unless you need them.
8. Press **Next**.

### 2. Your customer

9. Choose **Built for a customer** and type `acme-stores` (or choose **Not for a customer** for an app of your own).
10. Press **Next**.

### 3. Plan, copies and terms

11. Choose the plan. **Starter** runs a production copy and a sandbox copy; **Standard** and **Managed** add a staging copy. One order runs the copies you tick at the plan's one price.
12. Choose how to pay: **Pay monthly by card**, or **An invoice with payment terms** and the address the invoices go to.
13. Read the **App Hosting Schedule** (the link opens it) and tick **I accept the App Hosting Schedule**.
14. Press **Check the order**. The hosting checks it, reserving nothing, and answers with the app's addresses and its price, or names what to change.
15. Press **Next**.

### 4. Pay

16. Press **Order**. With a card, press **Pay by card**: Stripe's checkout opens in a new tab. Pay there, then come back to this tab. With an invoice, it is sent to the address you gave; the app is built once it is paid.

### 5. Follow it to live

17. The page shows each copy and where it stands: *waiting for the payment*, *being built*, *built, waiting for its secrets and its first version*, *live*.
18. **Your GitHub workflow:** press **Set them on your repository**. The page sets the Variables your workflow needs on the order's repository. If it cannot (the App is not installed there), it lists each one with a **Copy** button: set them under *Settings > Secrets and variables > Actions > Variables* in your repository.
19. **Your app's secrets** (a container's `"secret": true` settings): type each value in its box for each copy and press **Set**. The value is sent once and never shown again.
20. Push to your branch. Each copy gets the version in your `app.json` and goes **live**.
21. Once every copy is live, the page shows the **Publish** button and the `publish.py` command: put the app on your customer's shelf from there. The hosting page itself never publishes.

## Later

- **My apps** lists every order with its copies and where each stands. **Follow** opens one. **Cancel at month end** stops a paid order at the end of the month you paid for; on an unpaid order the button reads **Cancel this unpaid order** and gives its names back at once. Ended orders are under *Ended orders*.
- **Sign out** ends your sign-in on the page and at GitHub. A sign-in lasts three hours.

## What is refused, and why

- **An app that runs on a schedule:** CitiXsys puts it live; ask through your partner contact.
- **A required setting left empty:** the app would not start; give it a value.
- **Production for a customer, ordered by one of CitiXsys's own teams:** the customer orders and pays for it, through the account team.
- **A GitHub login with no hosting account, or not in your company's team in the iVendNext Developers organisation:** ask your partner manager.

The same order with the kit's command, and every rule behind these steps: [chapter 14b](../guide/14b_deploying_your_app.md#order-and-pay-online).
