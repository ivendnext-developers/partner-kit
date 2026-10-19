# Contributing to the partner kit

Thank you for helping. Proposed changes are welcome on the guide, the recipes, the samples, the design kit, the tools and the AI (MCP) server. Who may propose what is set out first.

## Who can propose what

Anyone may read this kit, clone it and fork it. To get a sandbox or build for an iVendNext customer, [become an iVendNext Partner](https://www.ivendnext.com/partner/#be-a-partner).

- **Anyone** may propose a fix to a text or a link: a typo, a broken link, a sentence that is wrong. Sign it off (below); the code owners review it.
- **Members** (an iVendNext Partner, a licensed customer's IT team, the CitiXsys Consulting Team, once onboarded) may also propose code and samples, after agreeing the shape in a feedback issue in the private `partner-feedback` repository ([how](feedback/README.md)).
  A new sample's README has a `## Run it` section with a code block, and its door comes from the needs cards that cite it (or a `**Door:**` line, see `needs/README.md`); the site build fails without them.
- Any other proposal is closed politely, with a pointer to the partner form above.
- **A security problem** is never a proposal or an issue: use [SECURITY.md](SECURITY.md).

## Before you start

- **One subject per change.** A fix and a new feature are two proposals.
- **Keep the four rules** ([guide ch. 3](guide/03_ladder_and_never_list.md)). A change that needs one of them set aside is read as a request for an extension point; open a *Point request* issue instead.
- **Never commit a secret** (an API key, a signing secret, a password, a token) or a shopper's personal data. Use made-up customers and sales.
- **A new need, not a fix?** Members open a feedback issue with the matching form first, in the private `partner-feedback` repository (this repository has no Issues tab), so we can agree the shape before you build.

## Sign-off — the Developer Certificate of Origin

Every commit carries a `Signed-off-by:` line with your real name and email, which certifies the [Developer Certificate of Origin 1.1](https://developercertificate.org/): that you wrote the change, or have the right to submit it under this repository's licence (Apache License 2.0). Add it with `git commit -s`. A proposal with an unsigned commit is not merged. This is the contributor agreement until a separate agreement is published here; if that changes, this file says so first.

- **Written with an AI assistant?** Welcome. Your sign-off then certifies that you reviewed the change, that you take responsibility for it as your own, and that your assistant's terms let you contribute its output under Apache 2.0. Do not submit output you have reason to think copies someone else's code.
- **Employed, or contributing for a company?** If your employer may own your work, your sign-off confirms it has authorised the contribution under Apache 2.0.

## How a change is reviewed

- The code owners (`CODEOWNERS`) review every proposal.
- **This repository is the one home of its files** (since 2026-10-07; [EXPORT_SOURCES.md](EXPORT_SOURCES.md) is the history). A change lands here, and only here, as a reviewed change: a proposal that a code owner approves. The exceptions are the ten vendored files listed in that note and the copies in `contracts/`: a defect in one is fixed at its source, so a member reports it with a *Kit defect* issue (anyone else may propose a fix to a link or a sentence in a copy, and a code owner takes it to the source), and the copy comes back in a reviewed change.
- **Checks run on every proposal** ([`ci.yml`](.github/workflows/ci.yml)): every sample's and tool's tests, the contracts' checks, the issue-form check, the API description's validator, the design kit's checks, a secrets scan over the files and the commits, and a check that every commit is signed off. All of them must pass. Nothing in them uses a secret. **A first-time outside contributor's checks wait for a maintainer to approve the run.** Our team also checks links and scans for names that should not be public before review.
- **Run them first.** From the repository root: `python3 .github/scripts/run_tests.py` (every test folder; or one, for example `python3 -m unittest discover -s tools/manifest/tests -p 'test_*.py'`), `python3 .github/scripts/issue_forms.py --check` (if you changed a feedback form, [feedback/README.md](feedback/README.md) says how the issue forms follow it), and `python3 .github/scripts/dco_check.py origin/main` (your commits are signed off). A recipe change names the step it corrects.

## The site

The partner site (`developer.ivendnext.com`) is built from this repository by `site/build.py` and checked by `site/check_links.py` and `site/test_site.py`; run `python3 site/test_site.py` before you propose a change to it. Its rules: a script is one of our own files or comes from a host on `ALLOWED_HOSTS` in `site/check_links.py` (CitiXsys adds a host, one line with the reason); no inline script and no inline event handler (a data block such as `application/ld+json` is fine); every page carries a content policy built from that same list. These are the site's rules only: the four rules of [guide ch. 3](guide/03_ladder_and_never_list.md) and the rules about what a generated PDF holds (the PDF lane's) are not site rules; this change does not touch them.

## Reporting instead of changing

**Members** use the feedback forms ([feedback/README.md](feedback/README.md) says where they are filed):
- A defect in the kit → a *Kit defect* issue.
- A page that is wrong, missing or unclear → a *Recipe or document gap* issue.
- A worked example you want → a *Sample request* issue.
- A way in that does not exist → a *Point request* issue.

**Everyone else:** [become an iVendNext Partner](https://www.ivendnext.com/partner/#be-a-partner) to use them.
- A security problem → **never an issue**; see [SECURITY.md](SECURITY.md).
