# Request a sandbox

A sandbox site is your own iVendNext site, hosted by us and full of made-up demo data. It is where you build and test before you touch a customer's site. Any developer who builds for an iVendNext customer can ask, partner or not.

Your site's address looks like `yourcompany.sandbox.ivend.co`. We tell you the address when the site is ready.

## How to ask

Fill in the sandbox request form on ivendnext.com. Our first reply asks for your GitHub login, so Try installs on your sandbox in one press when you sign in with it on My apps. No account? Make a free one in two minutes with any e-mail. A licensed customer's IT team may use the same form, or ask its account manager; either way its account owner talks to it. Our team talks to every builder first.

[Open the sandbox request form](https://www.ivendnext.com/developers/sandbox/)

## When access comes

Access means a sandbox site, and the kit's GitHub organisation for the feedback forms. It comes with onboarding, once our team has talked to you. When it arrives, Try on My apps names it, and `ivn sites` lists it: there is no key to paste.

## A sandbox of your own, in one press

Once your company has one of our sandboxes, any of your developers gets one of their own on **My sites** (on My apps): press **Get a sandbox**. It is ready at once and becomes your default, so Try installs there in one press. Its logins (an administrator's, a manager's and two cashiers') show once, on that screen: keep them then. If none is ready, the screen says so and offers this form.

## Your own sites and your customers'

**My sites** lists every site your company tries on and publishes to, and adds any iVendNext site you administer: a customer's test site or their live site. Type its address and paste an API key you make on that site, on your own user, one with System Manager: *User*, *API Access*, *Generate Keys*. Never make it on Administrator: making keys there replaces its secret. Without a key, the site's administrator installs from the shelf key Try shows, in **App library**.

Label each site with the customer's name and *test* or *live*. A *test* site gets what you try: with its key, Try installs there in one press. A *live* site (*live*, *prod* or *production* in its label; never one of our sandboxes) gets what you publish, and Try never goes there: label a customer's live site *live* in the same step you add it (**Label** on *Add a site*, or `ivn sites add --label`). On a live site you added with its key, **Install now** shows what installing a published version changes and installs it in one press. In a terminal: `ivn sites add`, `ivn sites label`, `ivn sites use` and `ivn sites remove`.

## What you receive

{{include recipes/hosted_sandbox.md#What you receive}}

## What is on your site

{{include recipes/hosted_sandbox.md#What is on your site}}

## The limits

{{include recipes/hosted_sandbox.md#The limits}}

When it arrives, [build your first app](first_app.md). The full recipe, with your first hour on the site, is [The hosted sandbox site](../../recipes/hosted_sandbox.md).
