# Request a sandbox

A sandbox site is an iVendNext site of your company's, hosted by us. It is where you build and test before you touch a customer's site. You choose its made-up demo data: [Demo data for your sandbox](demo_data.md). A sandbox comes with the iVendNext partner programme: a company that is not a partner yet can still ask, and when the request names the company it reaches our partner team as a partner application.

- **One free sandbox for your company.** Every developer of your company sees it on **My sites** and tries on it.
- **Your customer's own test site for customer work.** Add it on **My sites** with a key you make there, and Try installs there in one press.
- **A sandbox we hand out goes back if nobody signs in to it for 60 days.** **My sites** shows the date under it, and anyone at work on the site moves it on.

Your site's address looks like `sandbox-partner-13.staging.ivendnext.com`. It is on your partner portal home, and on **My sites** for your developers.

## How to ask

Fill in the sandbox request form on ivendnext.com with your **work e-mail address**. The address you ask with decides what happens next, and the answer comes to it by e-mail within minutes.

| You are | What happens |
|---|---|
| An owner or a member of a partner company, on the partner portal | The e-mail says where your company's sandbox is: on your partner portal home. For another one, an owner presses **Ask for another sandbox** there. |
| A developer at a partner company, asking from an address at your company's own domain | The e-mail carries a link. Open it, enter your GitHub login and confirm it is yours. The next time you sign in to My apps with GitHub you are in your company, and its sandbox is on your **My sites**. Your company's owners are told that you joined, and an owner can remove a developer on the partner portal, under **People**. |
| Anyone else: a personal mailbox such as Gmail, or a company we do not know yet | If you name your company on the form, your request becomes a partner application and our partner team writes to you. If you do not, the e-mail links the partner application. |

Already an iVendNext customer? Ask your account manager for your test site instead of using the form.

If your company already works with us, ask on the form before you press **Set up my company** on My apps. That button makes a new company of your own there, and a person in one company cannot be added to another. The link in the e-mail joins you to your company's own.

A developer whose company's addresses are at a public mailbox, or whose company's domain we do not hold, is added by an owner instead: **People** on the partner portal, **Add a developer**, with the developer's GitHub login. A company that joined before the partner portal is written to by our partner team.

No GitHub account? Make a free one in two minutes with any e-mail.

[Open the sandbox request form](https://www.ivendnext.com/developers/sandbox/)

## When access comes

Your company's first sandbox comes when our partner team approves your partner application. It is on your partner portal home: everyone of your company there sees its address, and your owners see its logins (an administrator's, a store manager's and two cashiers') until one of them presses **I have saved them**, so keep them then. It arrives with the demo pack Multi-category retail loading on it, and is ready to sell a few minutes after the approval; until then the manager's and the cashiers' logins will not sign in. When it is ready, open the site's address, sign in at the till as a cashier with the till ID and password shown, open a day and ring a sale. Your developers can reset or remove that pack, or load another (Electronics and phones only after this one is removed), under **Demo data** on **My sites**. An owner's own further sandbox arrives the same way; a sandbox handed to a developer starts empty, theirs to choose. A referral partner's owner first accepts the iVendNext Developer Terms there. Every developer of your company sees the site on **My sites**, Try on My apps names it, and `ivn sites` lists it: there is no key to paste.

A sandbox handed to you as a developer is yours: it is your default, and **Show its logins** on **My sites** shows its administrator's login once, so keep it then. Press **Demo data** there to load a demo pack; a pack's own logins stay under its **Show its logins**. Your colleagues see it under your name.

## Another sandbox

Your company's sandbox is free. For a customer's work, add your customer's own test site on **My sites**: you test on their data and settings, and it costs you nothing. For another sandbox, press **Ask for another sandbox** on **My sites**, with a line on what it is for if you like. Our partner management team approves it, and it appears on your **My sites** with its logins, shown once, and becomes your default. Until then **My sites** says the day you asked. A company that has no partner account with us yet asks by the sandbox request form instead, and the button opens it. A partner's owner asks on the partner portal home.

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
