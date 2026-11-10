# Request a sandbox

A sandbox site is an iVendNext site of your company's, hosted by us and full of made-up demo data. It is where you build and test before you touch a customer's site. Any company that builds for an iVendNext customer can ask, partner or not.

- **One free sandbox for your company.** Every developer of your company sees it on **My sites** and tries on it.
- **Your customer's own test site for customer work.** Add it on **My sites** with a key you make there, and Try installs there in one press.
- **A sandbox we hand out goes back if nobody signs in to it for 60 days.** **My sites** shows the date under it, and anyone at work on the site moves it on.

Your site's address looks like `partner-01.sandbox.ivend.co`. We tell you the address when the site is ready.

## How to ask

The sandbox goes to your company, so first sign in to My apps with GitHub once and press **Set up my company**; the person who keeps the site's logins must be on your company's **People** list. Then fill in the sandbox request form on ivendnext.com. Our first reply asks for your company's first word on My apps and the GitHub login of the person who keeps the site's logins. No GitHub account? Make a free one in two minutes with any e-mail. A licensed customer's IT team may use the same form, or ask its account manager; either way its account owner talks to it. Our team talks to every builder first.

[Open the sandbox request form](https://www.ivendnext.com/developers/sandbox/)

## When access comes

Access means a sandbox site, and the kit's GitHub organisation for the feedback forms. It comes with onboarding, once our team has talked to you. When it arrives, Try on My apps names it for every developer of your company, and `ivn sites` lists it: there is no key to paste. It is your default, and its logins (an administrator's, a manager's and two cashiers') wait on **My sites** for the person named in the request: **Show its logins** shows them once, so keep them then. Your colleagues see it under that person's name: ask them for the logins.

## Another sandbox

Your company's sandbox is free. For a customer's work, add your customer's own test site on **My sites**: you test on their data and settings, and it costs you nothing. For another sandbox, press **Ask for another sandbox** on **My sites**: it opens the sandbox request form.

## Sixty days with no sign-in

A sandbox we hand out goes back to us if nobody signs in to it for 60 days, and we make it fresh for the next company. **My sites** and `ivn sites` show the date under it: *Goes back to the pool on ⟨date⟩ unless someone signs in to it.* Anyone at work on the site, a cashier on the till or a manager in Desk, moves the date on. When it goes back, it leaves your list, and so does any key you added for it.

## Your own sites and your customers'

**My sites** lists every site your company tries on and publishes to, and adds any iVendNext site you administer: a customer's test site or their live site. Type its address and paste an API key you make on that site, on your own user, one with System Manager: your *User* record, its *Settings* tab, *API Access*, *Generate Keys*. Never make it on Administrator: making keys there replaces its secret. Without a key, the site's administrator installs from the shelf key Try shows, in **App library**.

Label each site with the customer's name and *test* or *live*. A *test* site gets what you try: with its key, Try installs there in one press. A *live* site (*live*, *prod* or *production* in its label; never one of our sandboxes) gets what you publish, and Try never goes there: label a customer's live site *live* in the same step you add it (**Label** on *Add a site*, or `ivn sites add --label`). On a live site you added with its key, **Install now** shows what installing a published version changes and installs it in one press. In a terminal: `ivn sites add`, `ivn sites label`, `ivn sites use` and `ivn sites remove`.

## What you receive

{{include recipes/hosted_sandbox.md#What you receive}}

## What is on your site

{{include recipes/hosted_sandbox.md#What is on your site}}

## The limits

{{include recipes/hosted_sandbox.md#The limits}}

When it arrives, [build your first app](first_app.md). The full recipe, with your first hour on the site, is [The hosted sandbox site](../../recipes/hosted_sandbox.md).
