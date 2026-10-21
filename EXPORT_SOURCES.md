# Where this repository's files came from — a history note

**This repository is now the one home of its files.** Until 2026-10-07 every file here was a copy, exported from our
private programme repository by a script, with a one-line header naming its source. On 2026-10-07 the files moved here:
each lost its export header, our private copy was removed, and the export was retired. A file here is now changed only
by a reviewed change in this repository ([CONTRIBUTING.md](CONTRIBUTING.md)). The first export's full list (213 files,
each with its source path and checksum) is in this file's history: `git log -p -- EXPORT_SOURCES.md`.

**Licence of the copies.** The copies listed below, and the other copies of CitiXsys product code that name their source in their own header, are licensed in this repository under the Apache License 2.0, on purpose, by CitiXsys ([NOTICE](NOTICE)). The products they come from keep their own licence.

## The one exception: ten vendored files

These ten files are copies of our WebAssembly spike and of one measurement, which stay in our private repository; the
kit's Wasm tools import them. Each keeps a one-line source header where it can carry a comment; the JSON and lock files
are listed here instead. Our kit check compares each with its source on every change, so the two cannot drift apart. A
defect in one is a defect in its source: report it through the feedback forms ([feedback/README.md](feedback/README.md)).

| File | Source path | Source sha256 at the first export (first 16) | Header | Note |
|---|---|---|---|---|
| `tools/scale_profile/measured_2026-10-04.json` | `evidence/lane4/scale/l4_scale.json` | `d8b520236c5ac447` | no header | vendored |
| `tools/wasm_kit/HOST_CONTRACT.md` | `spikes/wasm/CONTRACT.md` | `a575562c3556d7cf` | yes | vendored |
| `tools/wasm_kit/hosts/client.mjs` | `spikes/wasm/hosts/client.mjs` | `bc91f37f092fa956` | yes | vendored |
| `tools/wasm_kit/hosts/host_core.mjs` | `spikes/wasm/hosts/host_core.mjs` | `5e99216b5691e510` | yes | vendored |
| `tools/wasm_kit/hosts/worker.mjs` | `spikes/wasm/hosts/worker.mjs` | `59bf85e13e1a36e3` | yes | vendored |
| `tools/wasm_kit/vendor/host.py` | `spikes/wasm/pp_wasm/pp_wasm/host.py` | `7e9d5f5af5a3be2c` | yes | vendored |
| `tools/wasm_kit/meter/Cargo.lock` | `spikes/wasm/tools/meter/Cargo.lock` | `53b96cafe5cd805d` | no header | vendored |
| `tools/wasm_kit/meter/Cargo.toml` | `spikes/wasm/tools/meter/Cargo.toml` | `3f06a34d91c502ca` | yes | vendored |
| `tools/wasm_kit/meter/src/main.rs` | `spikes/wasm/tools/meter/src/main.rs` | `f2dbe53d7c2b74cb` | yes | vendored |
| `tools/wasm_kit/vendor/package.py` | `spikes/wasm/tools/package.py` | `9c269d8337e66822` | yes | vendored |

## The contracts: copies of the product's published files

The folder [`contracts/`](contracts/README.md) holds 312 files copied from the iVendNext POS app's repository
(`ivendnext/iVendNext_PWA`) at one commit, so a check runs with this repository alone. POS app commit
`7d47d331a203fd8b2794f83270a4190b3c1908e8` (the merge of the POS app's train T12 into `development`, 2026-10-18, build 2.0.0.654; against the earlier pin (train T11's merge) the copies take what that train added: two new extension points, *fulfil at sale* (a partner's voucher or PIN issued at payment: its page, its schema, fifteen samples and a stand-in voucher service) and the *list mark* (a coloured label on a list row: its page, its schema and ten samples); a page on the *print template readers* (`ivn_rows`, `ivn_value`); a capture when a line's quantity changes and a capture *notice* that warns without stopping the sale (the schema, the page and eleven samples); money columns and totals in field rules (the schema, the page and three samples); four more save-rule forms, a count per day, a total of a document's rows, days between two dates and a limit judged on change or read from a settings record (the schema, the page and twenty-three samples); and a package's report columns from a table, date reminders, print formats that read other records, a settings record of its own and a multi-select field (the manifest schema and fifteen samples). The checker copy `tools/manifest/validate.py` is taken at the same commit. Of the 228 files copied at the earlier pin, nine changed in content (every page's first line names the new commit) and eighty-four are new (273 samples now).
Our kit check
compares every file below with its source at that commit on each change; the only edits are the links inside the eighteen
pages, which point at the files here, four calls the product's pages name by the framework's own name, which the copies name by what they do (the save rules page's submit and cancel, the fiscal reader page's direct write, the template readers page's raw SQL), one customer's name and one reference to our own board on the save rules page, which the copy leaves out, and, in the samples, the product's lane id at the end of a sample's `about` line and the framework's name in one refused print format (its raw query stays, and is refused for the same reason). A defect in one is a defect there: report it through the feedback forms ([feedback/README.md](feedback/README.md)).

| Kit path | Source path in the POS app's repository | Files | Header |
|---|---|---|---|
| `contracts/pages/<point>.md` | `docs/extending/<point>.md` | 18 | yes (first line) |
| `contracts/extension_contract_check.py` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contract_check.py` | 1 | yes (first line) |
| `contracts/extension_contracts/<point>.v1.schema.json` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contracts/<point>.v1.schema.json` | 17 | no header (JSON) |
| `contracts/extension_contracts/samples/<point>/**/*.json` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contracts/samples/<point>/**/*.json` | 273 | no header (JSON) |
| `contracts/extension_contracts/standins/*.py` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contracts/standins/*.py` | 2 | yes (first line) |
| `contracts/gs1_codes.json` | `apps/ivendnext_mpos/ivendnext_mpos/tests/gs1_codes.json` | 1 | no header (JSON) |

`contracts/README.md` is ours, not a copy.

## The payment connector: copies of the payments app's files

Two files come from the payments app's repository (`ivendnext/iVendNext_Payments`), Payments app commit `36385b31a5d05fe032589fe7ab58d44550282d84` (its `development` branch on 2026-10-14; the contract's text is revision 1.0 as approved 2026-10-13, with its note that the certificate service is live). Our kit check compares both with their source at that commit on each change. The page's only edit is its eight links: they point at that repository's other documents, which are not public, so the copy keeps their names and drops the links. A defect in either is a defect there: report it through the feedback forms ([feedback/README.md](feedback/README.md)).

| Kit path | Source path in the payments app's repository | Header |
|---|---|---|
| `contracts/pages/paygw.md` | `docs/contract/PAYGW_1_REMOTE_GATEWAY_CONTRACT.md` | yes (first line) |
| `contracts/paygw/partner_stub.py` | `apps/ivendnext_pay_remote/ivendnext_pay_remote/tests/partner_stub.py` | yes (first line) |

The issue forms in `.github/ISSUE_TEMPLATE/` are generated from the Markdown forms in [`feedback/`](feedback/README.md)
by `.github/scripts/issue_forms.py`, so the two cannot drift apart.
