# 17. Submitting, support and feedback

This chapter tells you what to do when your work is ready for a customer, and how to tell us when something in the kit is missing or wrong. It is for a builder ready to deliver, or one who has hit a gap.

You will need [the feedback channel and its six forms](../feedback/README.md) and [the project blueprint](../kit/blueprint.md).

## Read this first

A finished app reaches customers through the iVendNext App library: you publish it with `tools/publish/publish.py` from any computer, its first listing waits for one approval by us, and each customer's site installs it from its App library with the checks of chapter 7 ([*Publish your app*](../site/pages/publish.md)). A manifest for one customer goes to that customer's site, whose administrator installs it. Tell us about anything missing or wrong with the feedback forms, GitHub issue forms in a private repository, `ivendnext-developers/partner-feedback`, for onboarded members: an iVendNext Partner, a licensed customer's IT team and the CitiXsys Consulting Team.

## When to use it

When your work has passed the checks in chapter 14 and you want it in front of a customer. Or at any point when a door, a recipe or a piece of the kit is missing or wrong.

## Steps

1. **Fill the blueprint first,** before you quote a project and before you build it. It is one page. It places every need on the ladder (chapter 3) and states the project's size and what it connects to. Attach it to any form below that concerns the project. Its section (e) says which extra work your needs switch on: work with us on an extension point, a scale run, or the customer's release gate. That list of triggers is a proposal, not yet a rule.
2. **Run the checks you can run yourself.** They are yours, not ours, and none of them certifies your work:

   ```bash
   python3 tools/manifest/validate.py samples/s2_bins/manifest.json      # a manifest (chapters 7 and 14)
   ```

   Also: the local admission check for a sandboxed function (chapter 8), and the customer's release gate in the customer's own pipeline (chapter 14).
3. **Submit.** A manifest is **not** submitted to us: it goes to iVendNext, whose administrator installs it from the install screen, checked by our code (chapter 7); on your sandbox you install it yourself with `deploy`. An app for many customers is published to the App library with `tools/publish/publish.py` ([*Publish your app*](../site/pages/publish.md)). A sandboxed module is certified by us by hand today. Of the two checks planned for a submission, the screen check against the design kit is built as a script you can run yourself (chapter 13a); running it on a submission waits on this step. The check of a remote endpoint is not built.
4. **Choose a feedback form.** Go down this list and send the first that fits:

   | If… | Send |
   |---|---|
   | something the page says should work failed | [Kit defect](../feedback/kit_defect.md) |
   | the page is wrong, missing or confusing | [Recipe or document gap](../feedback/recipe_or_document_gap.md) |
   | you only need to see a pattern done once | [Sample request](../feedback/sample_request.md) |
   | doors you have might be combined to do it (rung 6) | [Sample request](../feedback/sample_request.md) (we show the composition) |
   | no combination of doors meets the need, even after the blueprint | [Extension-point request](../feedback/point_request.md), naming the compositions you tried |

   Each form opens as a short GitHub issue form (a few questions). We ask the rest in the issue. Give evidence, not opinion: the steps, the versions, the kit version, the site you tried it on, the output. One subject per form. Do the blueprint first: an extension-point request without a placed need is hard to answer.
5. **Send it.** Submit the issue in `ivendnext-developers/partner-feedback`. It is given an id and answered in the issue. Every member can read every issue, so leave out secrets, shoppers' personal data and any customer's name the customer has not agreed to. If you are not yet a member, chapter 2 ("Your sandbox", "How to ask") says how to become one.

## Support

**Not decided yet.** The programme lists the support boundaries (what is yours and what is ours when a builder's app breaks a till) as open for later. The feedback forms are not a support route for a live customer's site. The forms' own text points here for support, and there is nothing more to point at today.

## What is refused, and why

- **A secret in a form.** No API key or secret, no password, no signing secret, no token. Black them out of any log you paste.
- **Shoppers' personal data.** Use made-up customers and sales. Describe your own customer in general terms unless the customer has agreed to be named.
- **A request to set aside one of the four rules** (a total changed after the cashier has seen it, an override or patch, your own code inside a customer's site, your JavaScript inside Desk or the till). They are closed by design. A form that needs one is read as a request for an extension point that meets the need another way (chapter 3).
- **A licence or price question.** Not a form's job.

## What the kit does not cover yet

- **Submitting:** how a release reaches us, what we run on it, how an install is scheduled.
- **The remote-endpoint check** for a submission, and running the screen check on one (you can run the screen check yourself, chapter 13a).
- **Support:** what is yours and what is ours.

## Technical notes

### What the kit has proven

- **The checks you run yourself:** the manifest checker, a sandboxed function's local admission and the customer's release gate were each run in this programme's own tests (chapters 7, 8 and 14 say how far).
- **The forms and the blueprint exist,** with a filled example blueprint for an invented chain of phone stores ([Blueprint example](../kit/blueprint_example.md)).

### What it has not

- **A form or a blueprint in use.** They were written and reviewed; nothing in the kit's tests runs them.
- **What the forms promise** after you send one: a reply with an id, an answer of *answered*, *needs more*, *planned* or *declined*, and a roll-up that decides what we build next. That is the design; nothing runs it.
- **Anything in the "does not cover yet" list.**

### Wording kept from the earlier version

- The blueprint's section (e) triggers (work with us on an extension point, a scale run, the customer's release gate) are proposed, not ruled.

## See also

[3. The ladder and the four rules](03_ladder_and_never_list.md) · [9. The extension-point catalogue and requests](09_points_and_requests.md) · [14. Testing and release](14_testing_and_release.md) · [16. Possible, not possible, limits](16_possible_not_possible.md)
