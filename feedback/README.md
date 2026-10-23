# The feedback channel — six short forms, and which one to use

If you build for an iVendNext customer and find something missing or broken, these forms are how you tell us; the fifth asks us to list an app you built, and the sixth claims a need from our roadmap. Each is a short GitHub issue form: a few questions, and for two of them a tick box for money or the till.

## Who can file

The forms are for **onboarded members**: an iVendNext Partner, a licensed customer's IT team, and the CitiXsys Consulting Team. Onboarding invites your GitHub account to one of three teams, and the team can then open the forms in a private repository, `ivendnext-developers/partner-feedback`. Anyone else sees "page not found" there. Access comes with onboarding. **Not yet a member?** Become an iVendNext Partner through the partner form at <https://www.ivendnext.com/partners/apply/>. A licensed customer's IT team may use that form or ask its account manager.

**Every member can read every issue**, other partners' and other customers' teams too. See "Before you fill one in" below.

**When to use it:** a piece of the kit failed, a page is wrong, you want a worked example, or no extension point meets your need.

**Reference:** the six forms in this folder; guide chapter 17 ([Submitting, support, feedback](../guide/17_submit_support_feedback.md)); the extension-point catalogue (guide chapter 9, [The extension points, and how to ask for a new one](../guide/09_points_and_requests.md)).

We do not interview builders or customers. The analysis we already hold is the evidence, and **a form is how a new need reaches us**. The forms ask only what we need to start. Anything else we need, we ask in the issue.

## Which form for what

| Form | Use it when | Not this form if… |
|---|---|---|
| [Extension-point request](point_request.md) | Your blueprint has a need that no rung of the ladder, alone or combined with others, can meet, or a published extension point is missing something you need. | A recipe or page is wrong or unclear → *recipe or document gap*. Something that should work does not → *kit defect*. |
| [Recipe or document gap](recipe_or_document_gap.md) | A guide chapter, recipe or reference page is missing, wrong, out of date, unclear or has a broken link. | The page is right but the kit behaves differently → *kit defect*. |
| [Sample request](sample_request.md) | You want a worked example of a pattern we do not show yet, a variant of one we do, or a manifest installed on your sandbox. | You want a new way in, not an example of an existing one → *extension-point request*. |
| [Kit defect](kit_defect.md) | A piece of the kit does not do what its recipe says: event feed client, manifest, Wasm kit, MCP server, design kit, sign-in recipe, scale-profile kit. | The kit does what it says but you want it to do more → *extension-point request* or *sample request*. |
| [App listing request](app_listing.md) | Your company's first app works on your sandbox: ask us to register your company and give it its first word. From then on you publish yourself with the kit's publish command (*Publish your app*). | It is for one customer only → ask through Help, with the customer's site address (it goes on that customer's private shelf, not in an issue every member reads). |
| [Claim a need](claim_a_need.md) | You will build and sell something on our roadmap's *next* list ([What iVendNext builds](../site/pages/roadmap.md)): claim it, and once we accept the claim we do not start it for 90 days. | The need is already being built or listed (it has started, or it is answered), or is on the roadmap's *you build* list (it is yours already). |

**Not sure?** Ask in this order:
1. Did something that the page says should work fail? → *kit defect*.
2. Is the page itself wrong, missing or confusing? → *recipe or document gap*.
3. Do you only need to see the pattern done once? → *sample request*.
4. Can doors you have be combined to do it (rung 6: an outside app with a document check, a Desk button that asks for inputs, a partner page, a capture, save rules, configuration)? → a *sample request* (we show the composition) or a *recipe or document gap* (the page should have said so).
5. Does the ladder have no door for the need, even after you tried to combine doors, and does the combination not meet the customer's outcome? → *extension-point request*, naming the compositions you tried and why each falls short.

If one problem fits two forms, send the one that names the cause. If you send two, say so in each.

## Before you fill one in

- **Do the blueprint first** ([`../kit/blueprint.md`](../kit/blueprint.md)). A request without a placed need is hard to answer, and most needs turn out to be configuration, an outside app or a manifest.
- **One subject per form.** Two needs mean two forms.
- **Never put a secret in a form.** No API key or secret, no password, no signing secret, no token. Black them out of any log you paste.
- **Every member reads every issue.** Do not name your customer unless the customer has agreed; describe them in general terms ("a forty-store pharmacy chain").
- **No shoppers' personal data.** Use made-up customers and made-up sales.
- **Say where you tried it:** your sandbox site, or the customer's staging site, or that you were only reading.

## What a form is not

- Not a support request for a customer's live site. Support is not decided yet; guide chapter 17 says what is open.
- Not a licence or price question.
- Not a way to ask us to set aside one of the four rules: a total changed after the cashier has seen it, overrides or patches, outside code inside a customer's site, your JavaScript inside Desk or the till. Those are closed by design. A request that needs one of them is read as a request for an extension point that meets the need another way.

## What happens after you send one

Every form says the same in its own words:
- It is given an **id**, which comes back to you in the issue.
- It is answered in the issue with one of: **answered** (a door already exists), **needs more** (a question back to you), **planned** (it joins the work we do and you can follow it) or **declined** (with the reason).
- Requests of the same kind are collected into a periodic roll-up that decides what we build next. We give no date.

## If you change a form (for the kit's code owners)

Edit the Markdown form here, then run `python3 .github/scripts/issue_forms.py` from the repository's root: it rewrites the issue forms in `.github/ISSUE_TEMPLATE/`, and `--check` fails when the two differ. The forms are filed in the private `partner-feedback` repository, so copy the seven generated files (the six forms and `config.yml`) into that repository's `.github/ISSUE_TEMPLATE/` unchanged and compare them byte for byte.

*Form version 2 · 2026-10-08. Shortened from the first version: each form lists what we may ask next, so nothing is lost, only moved to the issue's thread. A field you think is missing goes in a recipe-or-document-gap form.*
