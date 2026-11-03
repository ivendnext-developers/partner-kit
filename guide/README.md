# The iVendNext partner guide

**What this is.** The guide for everyone who builds for an iVendNext customer — iVendNext Partners, licensed customers' IT teams, and the CitiXsys Consulting Team. Its outline is the build ladder. Every chapter is written; each says what the kit has proven and what it has not.

To build an app, you need only [Build your first app](../site/pages/first_app.md). These chapters are the reference behind it. [1a. How it all works](01a_how_it_all_works.md) is the one to read first, in ten minutes. Before you quote a customer, read chapters 1 and 3 too.

**The guide's own rules.** iVendNext names only; no customer named. Each chapter is a plain guide first: what it does and who it is for, a picture where a sample was walked, when to use it, the steps with their commands, what is refused, and what happens when the builder's service is down and when the till is offline. 

## Chapters

| # | Chapter | Recipe · sample |
|---|---|---|
| 1 | [Welcome and the one path](01_welcome.md) | — |
| 1a | [How it all works — where your app runs, where the data lives, why customers never collide](01a_how_it_all_works.md) | — |
| 1c | [How the data travels: loyalty and telecom plan integrations, hop by hop with two chains at once](01c_how_the_data_travels.md) | `samples/s22_customer_loyalty/` (its loyalty adapter) · `samples/s52_phone_plans/` |
| 3 | [The ladder and the four rules](03_ladder_and_never_list.md) | one recipe per rung (linked in the chapter) |
| 4 | [Configure first](04_configure_first.md) | `recipes/configure_no_code.md`, `recipes/receipt_format.md` · `samples/s5_config_pack/`, `samples/s4_receipt_pack/` |
| 7 | [Manifests](07_manifests.md) | `recipes/manifest.md`, `recipes/approvals.md` · `samples/s11_approvals/manifest.json` (an approval workflow), `samples/s2_bins/manifest.json` · `samples/s19_unit_codes/`, `samples/s21_field_rules/` (data only) · `tools/manifest/` |
| 9 | [The extension points, and how to ask for a new one](09_points_and_requests.md) | [extension-point request form](../feedback/point_request.md) |
| 10 | [Integrations](10_integrations.md) | `recipes/system_sync.md`, `recipes/estate_rollout.md`, `recipes/bi_feed.md` · `samples/s7_system_sync/`, `samples/s8_estate_rollout/`, `samples/s9_bi_feed/` |
| 12 | [Handheld and the other apps](12_handheld_and_other_apps.md) | `tools/feed_client/` · `samples/s7_system_sync/` |
| 16 | [Possible, not possible, limits](16_possible_not_possible.md) | the [needs catalogue](../needs/README.md): one card per need, each naming its recipe and sample (the chapter's lists are built from the cards) |
