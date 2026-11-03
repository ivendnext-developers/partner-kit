# A manifest: your own records and formats, as data (way in 4)

**Goal.** Add your own record types, fields, print formats, notifications and workspaces, and the other kinds the recipe lists (among them reports and dashboards, workflows, webhooks, a remote till key, Desk buttons, save rules and label layouts), to a retailer's iVendNext as one data file the retailer's administrator installs. A manifest runs nothing of yours, except a certified module it carries, which runs in our sandbox.

**Read.** [Build your first app](../site/pages/first_app.md) · [guide/07_manifests.md](../guide/07_manifests.md) · [recipes/manifest.md](../recipes/manifest.md) (the kinds a manifest may carry, and each rule).

**Samples to copy.** [samples/s2_bins/manifest.json](../samples/s2_bins/manifest.json) (five record types, a field on Item, a print format, a workspace) · [samples/s1_warranty/manifest.json](../samples/s1_warranty/manifest.json) (one record type a till key reads) · [samples/s11_approvals/manifest.json](../samples/s11_approvals/manifest.json) (an approval workflow on the customer's own Purchase Order).

**Steps.**
1. Make the app from the nearest sample: `ivn new <app> --from sNN`, in the person's own repository. The app's name starts with their company's first word (ask for it). Read its `README.md`.
2. Change `manifest.json`. An app may do what the customer's administrator can do in Desk, on the customer's own record types too. A field you add to one of those starts with the app's prefix; no other name needs it.
3. Run `ivn check` and fix each refusal at its cause. Read its notes to the person. Do not edit the checker.
4. To try it: `ivn try`, on the person's **own sandbox**. It installs at once and asks nothing, so show the person what you are about to install and get their yes first.
5. Publishing (`ivn publish --to <site>`, `ivn publish --public`) needs their yes for that action.

**Check.** `ivn check` is green.

**Done looks like.** `ivn check` is green; the person read what `ivn try` said it changes; the file contains no code, no script and no address the person did not list.

**Never.** Put a server script, a client script or any code in a manifest; refuse work the list in [What an app may not do](../contracts/pages/what_an_app_may_not_do.md) allows; use the samples' `pp_` prefix.
