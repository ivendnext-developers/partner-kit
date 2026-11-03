# The iVendNext partner guide

**What this is.** The guide for everyone who builds for an iVendNext customer — iVendNext Partners, licensed customers' IT teams, and the CitiXsys Consulting Team. Its outline is the build ladder. Every chapter is written; each says what the kit has proven and what it has not.

New to iVendNext? Start with [1a. How it all works](01a_how_it_all_works.md), a ten-minute read, and [1b](../site/pages/first_app.md), one app end to end. Read the guide before you quote a customer: chapters 1 and 3 first, then the chapter for each rung your project needs.

**The guide's own rules.** iVendNext names only; no customer named. Each chapter is a plain guide first: what it does and who it is for, a picture where a sample was walked, when to use it, the steps with their commands, what is refused, and what happens when the builder's service is down and when the till is offline. A *Technical notes* section at the end keeps every technical fact: the tests, what the kit has proven and what it has not, run ids, pins and design choices.

## Chapters

| # | Chapter | Recipe · sample |
|---|---|---|
| 1 | [Welcome and the one path](01_welcome.md) | — |
| 1a | [How it all works — where your app runs, where the data lives, why customers never collide](01a_how_it_all_works.md) | [Questions developers ask](01a_how_it_all_works.md) |
| 1b | [One app from your laptop to the till — sample S18, step by step](../site/pages/first_app.md) | `samples/s18_rule_guard/` · `tools/manifest/start.py`, `tools/publish/`, `tools/deploy_app/` |
| 1c | [How the data travels: loyalty and telecom plan integrations, hop by hop with two chains at once](01c_how_the_data_travels.md) | `samples/s22_customer_loyalty/` (its loyalty adapter) · `samples/s52_phone_plans/` |
| 2 | [Getting started — sandbox, keys, the first call](../site/pages/first_app.md) | `recipes/integration_user.md`, `recipes/connected_app.md` · `api/collection/`, `api/openapi.yaml` |
| 3 | [The ladder and the four rules](03_ladder_and_never_list.md) | one recipe per rung (linked in the chapter) |
| 4 | [Configure first](04_configure_first.md) | `recipes/configure_no_code.md`, `recipes/receipt_format.md` · `samples/s5_config_pack/`, `samples/s4_receipt_pack/` |
| 5 | [Outside apps and the event feed](../recipes/event_feed.md) | `recipes/connected_app.md`, `recipes/integration_user.md`, `recipes/event_feed.md` + `tools/feed_client/` · `recipes/webhook_receiver.md` (the nudge) · `recipes/bulk_reads.md` · `samples/s1_warranty/service/`, `samples/s2_bins/service/` |
| 6 | [Till keys](../contracts/pages/remote_till_key.md) | `recipes/point_handler.md` (step 6, the remote key), `recipes/ai_till_key.md` · `samples/s1_warranty/`, `samples/s2_bins/` · `tools/standin_caller/` |
| 7 | [Manifests](07_manifests.md) | `recipes/manifest.md`, `recipes/approvals.md` · `samples/s11_approvals/manifest.json` (the permission example), `samples/s2_bins/manifest.json` · `samples/s19_unit_codes/`, `samples/s21_field_rules/` (data only) · `tools/manifest/` |
| 8 | [Sandboxed functions](../tools/wasm_kit/README.md) | `tools/wasm_kit/README.md`, `tools/wasm_kit/CONTRACT.md` |
| 9 | [The extension points, and how to ask for a new one](09_points_and_requests.md) | [extension-point request form](../feedback/point_request.md) |
| 10 | [Integrations](10_integrations.md) | `recipes/system_sync.md`, `recipes/estate_rollout.md`, `recipes/bi_feed.md` · `samples/s7_system_sync/`, `samples/s8_estate_rollout/`, `samples/s9_bi_feed/` |
| 11 | [Payments, fiscal, hardware](../recipes/payment_connector.md) | `recipes/payment_connector.md` with `contracts/paygw/` · `recipes/wallet.md` with `samples/s22_customer_loyalty/` and `tools/sandbox_cert/` · `recipes/manifest.md` (`fiscal_readers`) · `tools/manifest/` |
| 12 | [Handheld and the other apps](12_handheld_and_other_apps.md) | `tools/feed_client/` · `samples/s7_system_sync/` |
| 13 | [AI on iVendNext](../ai/README.md) | `recipes/ai_till_key.md`, `recipes/ai_manager.md` · `tools/mcp_server/` · `samples/s6_ai_till_key/`, `samples/s10_ai_manager/` |
| 13a | [Screens and user experience](../site/pages/map.md) | `samples/s2_bins/manifest.json` (native screens) · `samples/s16_pick_route/` (Desk action) · `samples/s17_partner_page/` (page in our frame) · `samples/s13_portal/` (a standalone portal) |
| 14 | [Testing and release](../site/pages/first_app.md) | `recipes/release_gate.md` · `samples/s12_release_gate/` · `recipes/money_kit.md` (the idea) · `tools/manifest/` |
| 14a | [Deploying to a chain of stores](../site/pages/publish.md) | `recipes/estate_rollout.md` · `recipes/manifest.md` · `recipes/connected_app.md` |
| 14b | [Deploying your app](../site/pages/publish.md) | `tools/app_template/` · `tools/standin_caller/` · `recipes/point_handler.md` |
| 15 | [Customer archetypes](../needs/README.md) | samples named per example · `samples/s22_customer_loyalty/` with `recipes/customer_owned_loyalty.md` and `recipes/check_by_workflow.md` |
| 16 | [Possible, not possible, limits](16_possible_not_possible.md) | the [needs catalogue](../needs/README.md): one card per need, each naming its recipe and sample (the chapter's lists are built from the cards) |
| 17 | [Submitting, support, feedback](../site/pages/feedback.md) | `feedback/`, `kit/blueprint.md` |
| 18 | [Versioning — how long a version keeps working](../CHANGELOG.md) | `CHANGELOG.md` |
