# Build a reference app from a brief

**Goal.** From a customer's written brief, produce a small working reference app that uses the right way in for each need, with a green check and a plan for what happens next. The person owns the decisions; you do the legwork.

**Read.** [kit/blueprint.md](../kit/blueprint.md) · [guide/03_ladder_and_never_list.md](../guide/03_ladder_and_never_list.md) · [guide/15_customer_archetypes.md](../guide/15_customer_archetypes.md) · the needs catalogue ([needs/README.md](../needs/README.md)) and [guide/16_possible_not_possible.md](../guide/16_possible_not_possible.md) · [guide/09_points_and_requests.md](../guide/09_points_and_requests.md).

**Samples that combine ways in.** [samples/s1_warranty/](../samples/s1_warranty/) (outside service, a record type and a till key) · [samples/s22_customer_loyalty/](../samples/s22_customer_loyalty/) (logic outside, records inside the shop) · [samples/s11_approvals/](../samples/s11_approvals/) (a manifest with a workflow, and a nightly export).

**Steps.**
1. **Fill the blueprint.** Copy `kit/blueprint_template.md` into the project and fill it (`kit/blueprint.md` says how): the project in two lines, then one row per need in the customer's words. Mark a guess as a guess.
2. **Place every need on a way in.** Go down the five ways in; write one line per need saying which, and why the one above it did not fit. A need that fits none alone: combine doors (an outside app with a document check, a Desk button that asks for inputs, a partner page, a capture at the scan, save rules, configuration) and write the combination and its limit in the row. Only a need that no combination meets is a request for an extension point (row marked as such, with the compositions you tried and why each falls short).
3. **Show the person the blueprint** and let them correct it before you build. Stop here if a row depends on a decision only they can make.
4. **Build one need at a time**, using the matching recipe in this folder. After each, run `python3 tools/check/check.py <project folder>` and keep it green.
5. **Wire them together** the way the samples above do (a manifest for the records, an outside service for the logic, a till key for the cashier). Pick your own prefix, starting with your company's first word; never leave the sample's `pp_`.
6. **Write the project's README** for the person: what it does, how to run its tests, which sandbox commands to run and in what order, and what it does not do.

**Check.** Every recipe's check, then `python3 tools/check/check.py <project folder>` over the whole project, green; the project's own unit tests, green.

**Done looks like.** The blueprint is filled and agreed; each need is built on its way in or marked as a request; the check is green; the README tells the person how to put it on their own sandbox; no key, secret or real customer detail is in any file; nothing was written to a shop without a yes.

**Never.** Choose a way in because it is more fun to build. The highest way in that does the job wins.
