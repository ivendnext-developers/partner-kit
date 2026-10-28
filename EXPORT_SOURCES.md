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

The folder [`contracts/`](contracts/README.md) holds 374 files copied from the iVendNext POS app's repository
(`ivendnext/iVendNext_PWA`) at one commit, so a check runs with this repository alone. POS app commit
`60147699cce4f7bd35f73e111649ce108eb2dcc2` (the merge of the POS app's train T19 into `development`, 2026-10-28, build 2.1.0.667; against the earlier pin (train T18's merge, `b453a68ea`, build 2.1.0.666, which took what trains T13 to T18 added: the *payer* and the *register books* extension points, a certified module in a package, a field only named roles read or change, the print-reader refusal, a check's lots and its cashier, customer fields and label placeholders) the copies take what train T19 added: a new extension point, the *open check* (an outside app opens a table's, a tab's or a pre-order's running order and adds lines to it, and the till prices and takes the payment: its page, its schema and nine samples); the manifest schema's one event feed per app (`registered_applications` holds at most one entry, and the install makes the app's own user); and changed words in four pages: the event feed (the app's own user), the check, the payer and the register books (a person's columns read by permission level, and a book's retention). The checker copy `tools/manifest/validate.py` is taken at the same commit. Of the 363 files copied at the earlier pin, five changed in content (every page's first line names the new commit) and eleven are new (329 samples now).
Our kit check
compares every file below with its source at that commit on each change; the only edits are the links inside the twenty-one
pages, which point at the files here, the calls the product's pages name by the framework's own name, which the copies name by what they do (the save rules page's submit and cancel, the fiscal reader page's direct write, the template readers page's raw SQL and its five readers, the open check page's generic record calls, the register books page's two readers), the register books page's decision id and three asks of the framework, one customer's name and one reference to our own board on the save rules page, which the copy leaves out, and, in the samples, the product's lane, row or decision id in a sample's `about` line and the framework's name in two refused print formats. The raw query stays and is still refused. The other reads the Company through the framework's own reader, which the shop refuses only when it is called by the framework's name: without the name, this copy of the sample is warned, not refused, so read its `expect_refusal` as the shop's answer. A defect in one is a defect there: report it through the feedback forms ([feedback/README.md](feedback/README.md)).

| Kit path | Source path in the POS app's repository | Files | Header |
|---|---|---|---|
| `contracts/pages/<point>.md` | `docs/extending/<point>.md` | 21 | yes (first line) |
| `contracts/extension_contract_check.py` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contract_check.py` | 1 | yes (first line) |
| `contracts/extension_contracts/<point>.v1.schema.json` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contracts/<point>.v1.schema.json` | 20 | no header (JSON) |
| `contracts/extension_contracts/samples/<point>/**/*.json` | `apps/ivendnext_mpos/ivendnext_mpos/tests/extension_contracts/samples/<point>/**/*.json` | 329 | no header (JSON) |
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
