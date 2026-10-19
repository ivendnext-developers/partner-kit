# The iVendNext partner guide

**What this is.** The guide for everyone who builds for an iVendNext customer — iVendNext Partners, licensed customers' IT teams, and the CitiXsys Consulting Team. Its outline is the build ladder. Every chapter is written; each says what the kit has proven and what it has not.

Read it before you quote a customer: chapters 1 and 3 first, then the chapter for each rung your project needs.

**The guide's own rules.** iVendNext names only; no customer named. Each chapter is a plain guide first: what it does and who it is for, a picture where a sample was walked, when to use it, the steps with their commands, what is refused, and what happens when the builder's service is down and when the till is offline. A *Technical notes* section at the end keeps every technical fact: the tests, what the kit has proven and what it has not, run ids, pins and design choices.

## Chapters

| # | Chapter | Recipe · sample |
|---|---|---|
| 1 | [Welcome and the one path](01_welcome.md) | — |
| 2 | [Getting started — sandbox, keys, the first call](02_getting_started.md) | `recipes/integration_user.md`, `recipes/connected_app.md` · `api/collection/`, `api/openapi.yaml` |
| 3 | [The ladder and the four rules](03_ladder_and_never_list.md) | one recipe per rung (linked in the chapter) |
| 4 | [Configure first](04_configure_first.md) | `recipes/configure_no_code.md`, `recipes/receipt_format.md` · `samples/s5_config_pack/`, `samples/s4_receipt_pack/` |
| 5 | [Outside apps and the event feed](05_outside_apps_and_event_feed.md) | `recipes/connected_app.md`, `recipes/integration_user.md`, `recipes/event_feed.md` + `tools/feed_client/` · `recipes/webhook_receiver.md` (the nudge) · `recipes/bulk_reads.md` · `samples/s1_warranty/service/`, `samples/s2_bins/service/` |
| 6 | [Till keys](06_till_keys.md) | `recipes/point_handler.md` (step 6, the remote key), `recipes/ai_till_key.md` · `samples/s1_warranty/`, `samples/s2_bins/` · `tools/standin_caller/` |
| 7 | [Manifests](07_manifests.md) | `recipes/manifest.md`, `recipes/approvals.md` · `samples/s11_approvals/manifest.json` (the permission example), `samples/s2_bins/manifest.json` · `samples/s19_unit_codes/`, `samples/s21_field_rules/` (data only) · `tools/manifest/` |
| 8 | [Sandboxed functions](08_sandboxed_functions.md) | `tools/wasm_kit/README.md`, `tools/wasm_kit/CONTRACT.md` |
| 9 | [The extension points, and how to ask for a new one](09_points_and_requests.md) | [extension-point request form](../feedback/point_request.md) |
| 10 | [Integrations](10_integrations.md) | `recipes/system_sync.md`, `recipes/estate_rollout.md`, `recipes/bi_feed.md` · `samples/s7_system_sync/`, `samples/s8_estate_rollout/`, `samples/s9_bi_feed/` |
| 11 | [Payments, fiscal, hardware](11_payments_fiscal_hardware.md) | `recipes/payment_connector.md` with `contracts/paygw/` · `recipes/wallet.md` with `samples/s22_customer_loyalty/` and `tools/sandbox_cert/` · `recipes/manifest.md` (`fiscal_readers`) · `tools/manifest/` |
| 12 | [Handheld and the other apps](12_handheld_and_other_apps.md) | `tools/feed_client/` · `samples/s7_system_sync/` |
| 13 | [AI on iVendNext](13_ai.md) | `recipes/ai_till_key.md`, `recipes/ai_manager.md` · `tools/mcp_server/` · `samples/s6_ai_till_key/`, `samples/s10_ai_manager/` |
| 13a | [Screens and user experience](13a_screens_and_ux.md) | `samples/s2_bins/manifest.json` (native screens) · `samples/s16_pick_route/` (Desk action) · `samples/s17_partner_page/` (page in our frame) · `samples/s13_portal/` (a standalone portal) |
| 14 | [Testing and release](14_testing_and_release.md) | `recipes/release_gate.md` · `samples/s12_release_gate/` · `recipes/money_kit.md` (the idea) · `tools/manifest/` |
| 14a | [Deploying to a chain of stores](14a_deploying_to_a_chain.md) | `recipes/estate_rollout.md` · `recipes/manifest.md` · `recipes/connected_app.md` |
| 14b | [Deploying your app](14b_deploying_your_app.md) | `tools/app_template/` · `tools/standin_caller/` · `recipes/point_handler.md` |
| 15 | [Customer archetypes](15_customer_archetypes.md) | samples named per example · `samples/s22_customer_loyalty/` with `recipes/customer_owned_loyalty.md` and `recipes/check_by_workflow.md` |
| 16 | [Possible, not possible, limits](16_possible_not_possible.md) | the [needs catalogue](../needs/README.md): one card per need, each naming its recipe and sample (the chapter's lists are built from the cards) |
| 17 | [Submitting, support, feedback](17_submit_support_feedback.md) | `feedback/`, `kit/blueprint.md` |
| 18 | [Versioning — how long a version keeps working](18_versioning_and_support.md) | `CHANGELOG.md` |
