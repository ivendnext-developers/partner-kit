# App listing request — ask us to list your app in the App library, for every retailer

**You can list it yourself.** `ivn publish --public`, or **Publish** then **To everyone** on [My apps](https://developer.ivendnext.com/apps), lists your app from any computer: the first listing waits for one approval by us, and that is all ([Publish your app](../site/pages/publish.md)). Use this form only if that does not work for you.

**For:** an iVendNext Partner, a licensed customer's IT team or the CitiXsys Consulting Team who has built an app (a manifest) that any retailer could use, and wants it listed in the App library (`https://library.ivendnext.app`), where retailers find it and install it from iVendNext Desk. These forms are for onboarded members ([who can file](README.md)). **Reference:** guide chapter 7 ([manifests](../guide/07_manifests.md)) and the developer site's *Publish your app* page.

**An app for one customer only** is not listed here: every member of the programme reads these issues, and the request names the customer's site. Ask through **Help** (`https://help.ivendnext.com`) or your account manager instead, with the customer's site address; the app then appears only in that customer's Desk, on its own *Made for you* shelf.

## When to use it

- Your app works on your sandbox and you want retailers to find it in the App library.
- You have a new version of an app that is already listed (send the new manifest and its changelog line).

**Use another form if:** the app needs a door that does not exist → [extension-point request](point_request.md); the kit stopped you building it → [kit defect](kit_defect.md).

## The form

```markdown
# App listing request: <the app's title>

App name: <its name under your company's first word, as in the manifest, for example acme_bins>

## 1. What it does, who uses it and what a retailer sets up first
<The card's one line, the roles that use it, and whether it should be free or need a key. Then the steps a retailer takes after it installs the app, in the order the retailer meets them: the Desk screen to open, what to choose or fill in, who does it.>

## 2. The manifest, its guide page and its changelog
<Attach the manifest (version 1.0.0 or later), the text of its guide page in the five headings of the guide template, and one line on what is new in this version.>

- [ ] It meets the listing bar: its name is under your company's first word, it uninstalls cleanly on a sandbox with developer mode off, the kit's checks pass, the card says how a retailer sets the app up and links its guide, and someone answers for it.
```

## What the card and the guide must say

The card is `app.json`'s `card`: `title`, `summary`, `what`, `pictures`, `industries`, `price` and `guide`. The guide link may be any https page; your repository's README is enough. `industries` is `["all"]` for an app every retailer can use, or one to six of the App library's industries.

## What we may ask you next, in the issue

Who answers a retailer's questions about it · whether it sends anything outside the retailer's iVendNext or needs a Desk user · the sandbox run that shows the clean uninstall · the category it belongs in.

## What happens after you send it

- It is given an **id**, which comes back to you in the issue.
- We check the app against the listing bar.
- It is answered in the issue with one of: **listed**, **needs more** or **declined** (with the reason).
- A listed app shows your company as its maker. A later version you publish yourself: a new version number and a changelog line, listed at once unless it does more than the one before.
