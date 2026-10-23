# 1. Welcome — one path for everyone who builds for iVendNext

This guide shows how to build a customer's own behaviour on iVendNext without changing iVendNext itself. It is for anyone who builds for an iVendNext customer: an iVendNext Partner, a licensed customer's IT team, and the CitiXsys Consulting Team, our own team, which uses this same guide.

## When to use this guide

Before you quote a customer. Place every need on the ladder (chapter 3) first: most needs are configuration or an outside app, and a few need an extension point (chapter 9). The worked examples by customer size are in chapter 15, the [needs catalogue](../needs/README.md) answers need by need what is possible, and chapter 16 gives the limits for every project.

## What you can build

A customer's own behaviour, without changing iVendNext itself:
- the customer's rules at the till — a warranty check, a member's balance, a refusal before payment;
- the customer's own records in iVendNext Desk — warranties, bins, a loyalty ledger — with native screens;
- links to the customer's own systems — an ERP, a web store, a warehouse system, a loyalty programme;
- reports, approvals, print formats, labels;
- an AI assistant that works with the customer's data on the user's own key.

Your work keeps working when we upgrade iVendNext, because it uses only published doors. How long a version of a door is served is in chapter 18. We upgrade every customer together, so a change that reaches inside our code breaks on the next release. That is why the doors exist.

## The path, in nine steps

1. Ask to become a builder, through the iVendNext Partner form (chapter 2).
2. Get a sandbox site. We talk to you first, then host one for you, with demo stores, tills and users and an admin login. You make your own API key. Nothing to install. Access comes with onboarding (chapter 2).
3. Learn the ladder: the six ways in, in order, and what is never allowed (chapter 3).
4. Blueprint the project. For each need, write down its rung on the ladder. Add a scale profile (stores × tills × products × sales a day) and a map of the systems it connects.
5. Build with the recipes and samples, and run the checks locally (chapter 14).
6. Try it on your own sandbox: `deploy` installs your manifest there, after you consent to the summary the site writes (chapter 7).
7. The customer's own administrator installs it on their site, from that same summary, checked by our code (chapter 7).
8. Before every upgrade, the customer's own gate runs against the new release (chapter 14).
9. Tell us what is missing: an extension point, a recipe, a sample, a defect (chapter 17).

The path is the same for a three-store retailer and for a fifty-store chain. A large project's blueprint adds a scale proof, a release gate in the customer's own CI and, where an extension point is missing, joint work with us on that extension point. The project's needs decide that, not its size.

## What is refused, and why

You never put your own server code inside a customer's iVendNext site, and you never change money, overrides or our code (the full list is in chapter 3). Your logic runs on your own server, or as data the retailer installs, checked by our code (a manifest), or, at the extension points that take one (the check before payment and pricing), as a sandboxed function we certify (chapter 8). That keeps every customer on the same product and every upgrade safe.

## When your service is down, and when the till is offline

Design for both from the first day:
- **Your service down or slow:** the till carries on. For a till key you answer, the cashier reads that your app could not finish and that nothing was added to the sale (chapter 6). Each extension point states up front what the till does without your answer (chapter 9).
- **The till offline:** your remote answers are not asked for; the key is dimmed and the sale goes on. Your service catches up from the event feed once the sale reaches the server (chapter 5).

## Checking your work

Every chapter ends with the tests for its door, in its Technical notes. The checks you can run yourself are in chapter 14 (the manifest checker, the money kit, the customer's release gate); iVendNext's install runs the same manifest checker again, inside the site (chapter 7).

**Read next:** [2. Getting started](02_getting_started.md) · [3. The ladder and the four rules](03_ladder_and_never_list.md).
