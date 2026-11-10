# The iVendNext partner kit

Build the app a retail chain needs (a rule at the till, a record of its own, a link to its systems) without changing iVendNext itself.

**Start here: [Build your first app](site/pages/first_app.md)** ([on the site](https://developer.ivendnext.com/first_app.html)). It takes you from one of the kit's samples to your customer's App library in six steps, and it is all you need to read to build one.

Nothing of iVendNext goes on your computer: your sites are ours, in the cloud. For the terminal you need git and Python 3.9 or newer, and one line (on Windows, `irm https://developer.ivendnext.com/install.ps1 | iex`):

```bash
curl -fsSL https://developer.ivendnext.com/install.sh | sh
ivn login
ivn new acme_store_rules                    # a blank app, or: ivn new acme_po_approval --from s11
```

**Who it is for:** iVendNext Partners, licensed customers' IT teams and the CitiXsys Consulting Team. Anyone may read the kit. To get a sandbox, [request one](https://developer.ivendnext.com/sandbox.html); to build for an iVendNext customer, [become an iVendNext Partner](https://www.ivendnext.com/partners/apply/).

**Building with an AI assistant?** Point it at [AGENTS.md](AGENTS.md) first.

> **Generally released.** iVendNext POS 2.0.0.652 (18 October 2026) is the general release of the extension points, the API calls the kit describes and the manifest format. From the general release, each version is served for 12 months after its successor ships. Every change is a dated entry in [the changelog](CHANGELOG.md).

## When you go further

| You want | Look in |
|---|---|
| To go from a customer's list of needs to what to build | [`needs/`](needs/README.md) |
| A working app to start from | [`samples/`](samples/): 61 of them, each with its tests |
| The steps for one job | [`recipes/`](recipes/) |
| Everything an app can plug into | [What you can use](site/pages/map.md) · [`contracts/`](contracts/README.md), the extension points' pages and schemas |
| Every call and every record type | [`api/`](api/README.md) |
| How it all works, and the reference chapters | [`guide/`](guide/README.md) |
| To publish, list, go back a version, or hand an app over | [Publish your app](site/pages/publish.md) · [`tools/ivn/`](tools/ivn/README.md) |

## Feedback, contributing and security

- **Found a gap or a defect?** Onboarded members (an iVendNext Partner, a licensed customer's IT team, the CitiXsys Consulting Team) file it with one of the feedback forms in the private `partner-feedback` repository ([how](feedback/README.md)). One subject per form; never a secret or a shopper's personal data. Everyone else: [become an iVendNext Partner](https://www.ivendnext.com/partners/apply/), or propose a fix to a text or a link (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md). Contributions are signed off under the Developer Certificate of Origin.
- **A security problem:** never in an issue — see [SECURITY.md](SECURITY.md).
- **Where every file comes from:** [EXPORT_SOURCES.md](EXPORT_SOURCES.md).

## Licence

Apache License 2.0, Copyright 2026 CitiXsys — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Legal information: <https://legal.ivend.com>.

- **It covers this repository's files only.** A tool that runs inside a site, such as the money kit, calls iVendNext code; the licence grants nothing in the code it calls.
- **Copies of our product's files** (the manifest checker, the contracts, three lints, the design tokens and a few others, each with its source named) are licensed here under Apache 2.0 on purpose; [NOTICE](NOTICE) lists them.
- **Copying a sample into your product:** if you ship it to someone, keep the licence and the `NOTICE`, and mark the files you changed; if it only runs on your own server, there is nothing to do.
- **Not under Apache 2.0:** the iVendNext name and logo (`site/assets-src/logo*.svg`) are trademarks of CitiXsys and are not licensed for reuse — the partner terms (at <https://legal.ivend.com>, once published) say how you may refer to iVendNext; the fonts in `site/assets-src/fonts/` are under the SIL Open Font License 1.1 (`site/assets-src/fonts/OFL.txt`); `tools/app_template/service/ed25519.py` is adapted from RFC 8032's reference code, under the IETF Trust's BSD licence.
