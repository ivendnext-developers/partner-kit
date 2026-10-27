# A manifest: your own records and formats, as data (way in 4)

**Goal.** Add your own record types, fields, print formats, notifications and workspaces, and the other kinds the recipe lists (among them reports and dashboards, workflows, webhooks, a remote till key, Desk buttons, save rules and label layouts), to a retailer's iVendNext as one data file the retailer's administrator installs. A manifest runs nothing of yours, except a certified module it carries, which runs in our sandbox (chapter 7).

**Read.** [guide/07_manifests.md](../guide/07_manifests.md) · [recipes/manifest.md](../recipes/manifest.md) (the kinds a manifest may carry, and each rule) · [tools/deploy/README.md](../tools/deploy/README.md).

**Samples to copy.** [samples/s2_bins/manifest.json](../samples/s2_bins/manifest.json) (five record types, a field on Item, a print format, a workspace) · [samples/s1_warranty/manifest.json](../samples/s1_warranty/manifest.json) (one record type a till key reads) · [samples/s11_approvals/manifest.json](../samples/s11_approvals/manifest.json) (all nine permission rights written out; approvals by workflow).

**Steps.**
1. Choose the person's prefix: one to three upper-case words (`ACME WRC`) and the matching app name (`acme_wrc`). Every name you create starts with it. Its first word is their company's first word, which the App library gave them (ask for it): the library publishes their apps only under it.
2. Write `manifest.json` from the nearest sample. Use only kinds the recipe lists; a kind it does not list will be refused. Write all nine rights on every permission row.
3. Run `python3 tools/manifest/validate.py manifest.json` and fix each refusal at its cause. Read its `WARNING` lines to the person. Do not edit the checker.
4. Run `python3 tools/check/check.py <project folder>`.
5. To try it: `BASE=… KEY=… SECRET=… python3 tools/deploy/deploy.py manifest.json` on the person's **own sandbox**. It installs nothing without `--consent`. Show the person the summary it prints (what it makes, every outside address, what runs from install). Add `--consent` only after their yes.
6. Uninstall (`deploy.py uninstall "<app> <version>"`, which writes an export first) and `deploy.py finish` change the sandbox at once and take no `--consent`: run them only on the person's own sandbox, only after their yes for that action.

**Check.** `tools/manifest/validate.py` says `VALID`, then `tools/check/check.py` is green, then the site's own check inside `deploy` (without `--consent`) is clean.

**Done looks like.** Both checkers are green on the same file; the summary was read by the person; nothing was installed without `--consent`; the file contains no code, no script and no address the person did not list.

**Never.** Put a server script, a client script or any code in a manifest; add a field that the server enforces on a retailer's own record type; override a retailer's own record type; use the samples' `pp_` prefix.
