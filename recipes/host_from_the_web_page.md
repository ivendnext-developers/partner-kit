# Host your app from the web page, screen by screen — the recipe

You can have CitiXsys run your app's outside service with no command: on the developer site's hosting page you sign in with GitHub, give your app's settings, name the customer, choose a plan, pay, upload your app as a zip, and watch it go live. This recipe walks every screen of that page with a real example, so you know what each box wants before you reach it. It is for anyone who builds for iVendNext: an iVendNext Partner, a licensed customer's IT team, CitiXsys's own teams. You sign in with your own GitHub account; you never need to join our GitHub organisation.

**The example.** A company whose maker word is `acme` hosts the kit's S18 sample, started as `ACME RLG`, for its customer `acme-stores`. Put your own names where the example has `acme`.

## Before you start

Have these three things ready. The page asks for each one.

1. **Your app, made with the kit.** For the example, from the kit's folder:

   ```bash
   python3 tools/manifest/start.py s18_rule_guard --prefix "ACME RLG"
   ```

   It makes the folder `apps/acme_rlg` in your copy of the kit, with the app's `app.json` in it.
2. **Once it is paid, the zip you upload.** No GitHub repository, no workflow and nothing to install: you upload each version and the hosting builds it. For the example, a function made with `start.py`, make the zip from the kit's folder (its package names paths from there) with `python3 tools/deploy_app/deploy_app.py push apps/acme_rlg --root . --partner acme --save acme-rlg-1.1.1.zip`; for a container, a zip of the app's folder is enough.
3. **Your settings' values and the customer's code.** Your `app.json` names your app's plain settings; the page shows each with a line saying what it is. The customer's code is the one on the customer's *Made for you* shelf in the App library: the code you name when you publish to that customer. Ask your account team if you do not have it.

No hosting account yet? Sign in all the same: the page offers **Request access**, and a CitiXsys person approves it on the same page (below).

## The page, screen by screen

Open `https://developer.ivendnext.com/hosting`. The form is at the top, under *Order hosting from this page*. After each **Next**, the page brings the next step into view.

### Sign in with GitHub

1. Press **Sign in with GitHub**. The first time, GitHub asks you to authorise *iVendNext App Hosting*: press **Authorize**.
2. Back on the page, the box says **Signed in as** your GitHub login **for** your company. If your login orders for more than one company, choose it under **You order for** and press **Use this one**. What you pay is that company's price.

**The first time, with no hosting account yet,** the box shows **Request access**. Fill in **Company name** (`Acme Stores`), **Work email** (`dev@acme.example`) and **What you build** (`Rule apps for retail chains`), and press **Request access**. A CitiXsys person sees it on this page and presses **Approve**: your company's hosting account is made, with its own first word from the company's name (`acme`, so the example's app names start `acme-`). Press **Check again**: the box now says **Signed in as** your login **for** your company, and the steps below open. You never join our GitHub organisation. (CitiXsys's own people skip this step: they come straight in.)

### 1. Your app

3. **app.json:** press **Choose file** and pick `apps/acme_rlg/app.json`, or paste the file's text into the box.
4. The page shows the app's name, version and kind, then one box per setting. For the example, the two marked **(required)**:
   - **Setting IVN_LIBRARY_APP (required):** `acme_rlg` (the id you publish the app under in the App library)
   - **Setting RGD_PREFIX (required):** `ACME RLG` (the prefix you gave `start.py`)

   Leave the others empty unless you need them.
5. Press **Next**.

### 2. Your customer

6. Choose **Built for a customer** and type `acme-stores` (or choose **Not for a customer** for an app of your own).
7. Press **Next**.

### 3. Plan, copies and terms

8. Choose the plan. **Starter** runs a production copy and a sandbox copy; **Standard** and **Managed** add a staging copy. One order runs the copies you tick at the plan's one price.
9. Choose how to pay: **Pay monthly by card**, or **An invoice with payment terms** and the address the invoices go to.
10. Read the **App Hosting Schedule** (the link opens it) and tick **I accept the App Hosting Schedule**.
11. Press **Check the order**. The hosting checks it, reserving nothing, and answers with the app's addresses and its price, or names what to change.
12. Press **Next**.

### 4. Pay

13. Press **Order**. With a card, press **Pay by card**: Stripe's checkout opens in a new tab. Pay there, then come back to this tab. With an invoice, it is sent to the address you gave; the app is built once it is paid.

### 5. Follow it to live

14. The page shows each copy and where it stands: *waiting for the payment*, *being built*, *built, waiting for its secrets and its first version*, *live*.
15. **Upload a version:** once every copy is built, choose the zip (for the example, `acme-rlg-1.1.1.zip`). The page reads its version from the zip's `app.json`, uploads it, and the hosting builds it on its side for every copy: the page shows *Building 1.1.1…*, then *Building 1.1.1… Built.* If it did not build, the page shows *⟨version⟩ did not build. The last 50 lines of the build are below.* with those lines: fix it, raise `app.json`'s version, and upload again. A zip over its limit is refused before anything is built (an app that runs only when called at most 50 MB, one that runs all the time at most 1,024 MB).
16. **Your app's secrets** (a container's `"secret": true` settings): type the values you have, for any copy and in any order, and press **Set the values you typed**. Each is sent once and never shown again. Under each box the page says *Has a value* or *No value yet*, so after a reload or a new sign-in you type only what is missing. If you try to leave, reload or move to another step while a box still holds a value, the page asks first.
17. Once every copy is live, the page shows the **Publish** button and the `publish.py` command: put the app on your customer's shelf from there. The hosting page itself never publishes. Then the customer's administrator installs it from *Made for you* on the customer's site, and your app answers there at its address.

## Later

- **My apps** lists every order with its copies and where each stands. **Follow** opens one. **Cancel at month end** stops a paid order at the end of the month you paid for; on an unpaid order the button reads **Cancel this unpaid order** and gives its names back at once. Ended orders are under *Ended orders*.
- **Sign out** ends your sign-in on the page and at GitHub. A sign-in lasts three hours.

## What is refused, and why

- **An app that runs on a schedule:** CitiXsys puts it live; ask through your partner contact.
- **A required setting left empty:** the app would not start; give it a value.
- **Production for a customer, ordered by one of CitiXsys's own teams:** the customer orders and pays for it, through the account team.
- **A GitHub login with no hosting account:** press **Request access** on the page and wait for the answer there. If it is declined, **Check again** says so: ask your CitiXsys contact.

The same order with the kit's command, and every rule behind these steps: [chapter 14b](../guide/14b_deploying_your_app.md#order-and-pay-online).
