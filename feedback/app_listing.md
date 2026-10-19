# App listing request — ask us to list your app in the App library, for every shop

**You can publish yourself.** A company we have registered publishes its apps with one kit command, from any computer and wherever it keeps its code (`tools/publish/publish.py`): we take only the manifest and the card, never your source. An app's first listing waits for one approval by us ([Publish your app](../site/pages/publish.md)). **Use this form for your company's first app:** we register your company and give it its own first word, and from then on you name your apps under it and publish them yourself. ⛔ **Do not put your signing key's line or your `recipient.pem` in the form:** send them through Help or your account manager, so we register them for the company you are.

**For:** an iVendNext Partner, a licensed customer's IT team or the CitiXsys Consulting Team who has built an app (a manifest) that any shop could use, and wants it listed in the App library (`https://library.ivendnext.app`), where shops find it and install it from iVendNext Desk. These forms are for onboarded members ([who can file](README.md)). **Reference:** guide chapter 7 ([manifests](../guide/07_manifests.md)) and the developer site's *Publish your app* page.

**An app for one customer only** is not listed here: every member of the programme reads these issues, and the request names the customer's site. Ask through **Help** (`https://help.ivendnext.com`) or your account manager instead, with the customer's site address; the app then appears only in that customer's Desk, on its own *Made for you* shelf.

## When to use it

- Your app works on your sandbox and you want shops to find it in the App library.
- You have a new version of an app that is already listed (send the new manifest and its changelog line).

**Use another form if:** the app needs a door that does not exist → [extension-point request](point_request.md); the kit stopped you building it → [kit defect](kit_defect.md).

## The form

```markdown
# App listing request: <the app's title>

App name: <its name under your company's first word, as in the manifest, for example acme_bins>

## 1. What it does, who uses it and what a shop sets up first
<The card's one line, the roles that use it, and whether it should be free or need a key. Then the steps a shop takes after it installs the app, in the order the shop meets them: the Desk screen to open, what to choose or fill in, who does it.>

## 2. The manifest, its guide page and its changelog
<Attach the manifest (version 1.0.0 or later), the text of its guide page in the five headings of the guide template, and one line on what is new in this version.>

- [ ] It meets the listing bar: its name is under your company's first word, it uninstalls cleanly on a sandbox with developer mode off, the kit's checks pass, the card says how a shop sets the app up and links its guide, and someone answers for it.
```

## What the card and the guide must say

A shop reads two things before and after it installs your app: the **card** in the App library, and your app's **guide page**. The library will not list an app whose card cannot help a shop, so the form asks for both up front.

**The card (`library/app.json`)** carries, besides its title, one line, category, who uses it and changelog:

- `details`: one **lead** sentence in shop words, at least one point under **what** the app does, at least one **step** under **setup** (the steps a shop takes after the install, in the order it meets them), and **notes** (good to know). Each list holds up to ten points of one to 300 characters.
- `docs`: one to six `{title, url}` addresses, the first of them your guide page.

**The guide page** has five headings, in this order, written for the shop's owner or manager, not for a developer:

1. **What it does** — two or three sentences; who uses it.
2. **What you set up first** — numbered; each step names the Desk screen by the name a shop searches for.
3. **Where it shows** — Desk, the till, POS Studio, print layouts.
4. **What leaves your shop** — taken from your manifest: outside addresses, till keys, webhooks, services, event feeds, print and label layouts. *Nothing* only when the manifest names nothing.
5. **How to remove it** — from the app's **Details**, **Export and uninstall**, and what is kept.

An app with **three or more screens a shop opens** (record types that are not a table inside another, reports, Desk pages) gets a **section** of pages in place of one page, with a heading for each screen. The docs site also groups every app as an **App** (it adds records a shop works in every day, or a screen of its own) or a **Rule** (it adds one check, field or layout to a screen the shop already uses, with only the settings it needs). Say which yours is when you describe the app in the listing request. Each of your record types has one `documentation` property setter at its page and heading. The section *What a shop reads: the card and the guide* of the recipe [*Shipping your own data in a manifest*](../recipes/manifest.md) has the shapes and the five refusals the library gives, word for word.

## What we may ask you next, in the issue

Who answers a shop's questions about it · whether it sends anything outside the shop or needs a Desk user · the sandbox run that shows the clean uninstall · the category it belongs in.

## What happens after you send it

- It is given an **id**, which comes back to you in the issue.
- We check the app against the listing bar, on our own bench, with developer mode off.
- It is answered in the issue with one of: **registered** (your company, its signing key and its first word: publish the app with `tools/publish/publish.py`, and its first listing waits for our one approval), **needs more** or **declined** (with the reason).
- A listed app shows your company as its maker. A later version you publish yourself: a new version number and a changelog line, listed at once unless it does more than the one before.
