# AGENTS.md — read this first if you are an AI assistant working in this repository

This is the iVendNext partner kit. A person is using you to build something for an iVendNext customer: a retailer that runs iVendNext, a retail system with a till (the point of sale), a back office called Desk, and an API. Your job is to build it **without changing iVendNext itself**. This file is short on purpose. The guide in `guide/` is the full text; when this file and the guide disagree, the guide is right and the person should be told.

## When the person asks how iVendNext apps work

Where an app runs, whether it is Docker, where the customer's data lives, whether two customers collide, how many apps or containers to build, what publishing and hosting hand over: answer from `guide/01a_how_it_all_works.md` (the plain answers, each proved in its Technical notes) and the questions page, `site/pages/questions.md`, never from what another platform does. How the data travels through a link to an outside system is chapter 1c, [`guide/01c_how_the_data_travels.md`](guide/01c_how_the_data_travels.md). One app end to end, with every command: `guide/01b_one_app_end_to_end.md`. What an app can call, change and add (every endpoint in both directions, every manifest kind, every screen, every record type with its fields): the developer's map, `site/pages/map.md`, and `api/records/`.

## What you may rely on

- You work on the person's own laptop and, when they say so, their own **sandbox** site. A customer's live site is the person's to touch, not yours: see "Ask the person before any write to a live site" below.
- The kit runs with Python 3 and its standard library. Nothing here needs a paid service, and no assistant is required: any assistant that can read files and run commands can follow this file.
- Most of what follows is checked by a command, so run it instead of guessing. A green check means the kit's checkers found no refusal. It is not permission, and it does not replace the person's own review.

## The five ways in, highest first

Take the first one that does the job. Go down only when the one above cannot. Most needs stop at 1 or 2.

| # | Way in | Your code runs | Recipe for you | Guide |
|---|---|---|---|---|
| 1 | **Configure** what iVendNext already has: pricing, promotions, coupons, reasons, till keys and layouts, receipt formats, workflows, numbering, permissions, reports | nowhere | `ai/1_configure.md` | `guide/04_configure_first.md` |
| 2 | **Outside app**: your service reads and writes records over the API and reacts to the event feed | your server or the customer's | `ai/2_outside_app.md` | `guide/05_outside_apps_and_event_feed.md` |
| 3 | **Till key**: the cashier taps a key; the till calls your HTTPS service and shows your message or sale details | your server | `ai/3_till_key.md` | `guide/06_till_keys.md` |
| 4 | **Manifest**: your own record types, fields, print formats, notifications and workspaces, and the other kinds `recipes/manifest.md` lists (among them reports and dashboards, workflows, webhooks, a remote till key, Desk buttons, save rules and label layouts), declared as data and installed by the retailer's administrator | nowhere: it is data (a print format is a template the server runs when it prints; webhooks, a remote till key and Desk buttons call your service; a module it carries runs in our sandbox) | `ai/4_manifest.md` | `guide/07_manifests.md` |
| 5 | **Sandboxed function**: a compiled WebAssembly function at an extension point that offers one | a sandbox we run. **Two extension points take one, the check before payment and pricing, and only a module we have certified runs** (`guide/08_sandboxed_functions.md`): read the chapter before you start | `ai/5_sandboxed_function.md` | `guide/08_sandboxed_functions.md` |

If no single door fits, **compose doors** before you ask for one. An outside app with a document check, a Desk button that asks for inputs, a partner page opened from a button, a capture at the scan, save rules and configuration combine to meet most needs. A composition with its limit stated (a separate screen, a tap, seconds of delay) is the answer to give, never a workaround to hide. Request an extension point only when no composition meets the customer's outcome, and say in the request which compositions you tried and why each falls short. Composing keeps the four rules: it is never code inside the retailer's iVendNext, a script in Desk, or a price changed after the cashier has seen it. The sixth step is to **request an extension point** (`guide/09_points_and_requests.md`, the form in `feedback/point_request.md`). Tell the person which compositions you tried.

To build a whole reference app from a customer's brief, use `ai/6_build_from_a_brief.md`; it uses all of the above.

## The four rules

These are copied from `guide/03_ladder_and_never_list.md`. Every build keeps all four.

1. **Money enters the sale visibly, before payment.** A price or discount may come from your service, but never change a price, tax or total after the cashier has seen it. On a back-office document (a purchase order, a receipt), a price from your service shows on the document before it is submitted, and is never changed after.
2. **Don't override or patch iVendNext.**
3. **Your code runs on your server.** Inside the customer's site you ship data, not code — no server code of yours, no server scripts.
4. **Your screens come through our doors.** On the till: your page as a sheet over the sale, the till's own sheets when an item is scanned, a customer is picked or a quantity changes, and extra fields. In Desk: buttons, your pages and native screens. What you can't do is put your JavaScript inside our screens.

What this means for what you write:

- Never write code that overrides, monkey-patches or replaces iVendNext's own code, or hooks into a sale's own save.
- Never put your code in a retailer's site: no server script, no custom script, no client script, no code in a manifest.
- Never write JavaScript into Desk or the till. A screen is a native one a manifest declares, a Desk action, or your own page in our frame (`recipes/desk_action.md`, `recipes/partner_page.md`).
- Never change a price, tax or total after the cashier has seen it. A till key answers with a message or sale details, never a price, total or payment.
- Never build a way for the cashier to wait on your service. The till is never held for a service it cannot reach: design for your service being down (each recipe says what the cashier reads).

## Ask the person before any write to a live site

- **Read first, write second.** Reading records is fine on any retailer the person gives you a key for. Anything that creates, changes or deletes a record, installs a manifest, or sends a message to a customer needs the person's **yes, in this conversation, for that one action**. Show what you are about to send first.
- **Writes go to the person's own sandbox.** Run the request collection (`api/collection/run.sh`), `tools/deploy/deploy.py` with `--consent`, `uninstall` or `finish`, and any MCP server with `--writes`, only against the sandbox the person names. A write to any other retailer needs the person's yes for that one action, and you never do it on your own.
- **Keys and secrets stay out of files, logs and chat.** Take them from the environment; never write one into a file you create, a commit, a screenshot or a message. Use made-up customers and sales in everything you write.
- **The MCP server is read-only by default** (`tools/mcp_server/README.md`). Start it with `--writes` only if the person asks for a write, and set `confirm: true` on a call only after the person has said yes to that exact change.

## Commands

Run all of these from the repository root. Nothing below needs a network except the sandbox ones.

| To | Run |
|---|---|
| **Check your whole project** (manifests, app code, sandboxed builds, sample answers) before anything is installed | `python3 tools/check/check.py <your project folder>` |
| Find the card for a customer's need (its verdict, door, recipe and limits) | `python3 tools/needs/needs.py search <words>`, then `show <id>` |
| Check one manifest and read its refusals | `python3 tools/manifest/validate.py <manifest.json>` |
| Check app code the way our intake does | `python3 tools/selfcheck/selfcheck.py <app folder>` |
| Check an answer against an extension point's contract | `python3 -c "import sys; sys.path.insert(0,'tools/contracts'); from check import errors; print(errors('desk_action','answer',{...}))"` (the points and their schemas: `contracts/README.md`) |
| Install your manifest on **your own sandbox** (check only, nothing installed) | `BASE=https://<sandbox> KEY=<key> SECRET=<secret> python3 tools/deploy/deploy.py manifest.json` |
| Install it for real, after the person has read the summary it printed and said yes | the same command with `--consent` |
| Send the example API calls to your sandbox | `BASE=… KEY=… SECRET=… bash api/collection/run.sh` (it **writes** test records: sandbox only) |
| Let an assistant read a retailer's records | `IVN_BASE=… IVN_KEY=… IVN_SECRET=… python3 tools/mcp_server/server.py` (read-only; the person's own key; `tools/mcp_server/README.md`) |
| Read the events a retailer's iVendNext produces | `tools/feed_client/README.md` |
| Start from one of our samples under the person's own prefix, in one command (copies it into `apps/`, renames it, checks it; refuses to finish while any of our names is left) | `python3 tools/manifest/start.py <sample folder> --prefix "<THEIR PREFIX>"` ([recipe](recipes/make_it_your_own.md)) |
| Make a copy of one of our apps the person's own (their company's prefix; iVendNext's checker runs on the result) | `python3 tools/manifest/rename.py <copy>/manifest.json --prefix "<THEIR PREFIX>" --write` ([recipe](recipes/make_it_your_own.md)) |
| Move a retailer's records from our app to the person's version of it (only after the person has said yes: it **writes** to that site) | `BASE=… KEY=… SECRET=… python3 tools/deploy/copy_records.py <our app> <their app> --write` |
| Publish to the App library (only after the person has said yes: it lists the app or sends it to a customer's shelf) | `python3 tools/publish/publish.py publish <project> --partner <code>` (`tools/publish/README.md`) |
| Run a many-retailer app against an iVendNext site on the person's own machine (plain http, a key they sign themselves) | From the repository root: `python3 tools/app_template/local_key.py keygen --out .local-keys`; `python3 tools/app_template/local_key.py sign --secret .local-keys/library.secret --app <app> --site <name>.localhost:<port>`; `IVN_LOCAL=1 IVN_LIBRARY_APP=<app> IVN_SHOPS_FILE=shops.local.json IVN_LOCAL_LIBRARY_KEYS=.local-keys/library_keys.json python3 tools/app_template/service/app.py`; then send the connect yourself, as `tools/app_template/README.md` (*Local mode*) shows |
| Run a sample's tests (samples that have a `tests` folder) | `python3 -m unittest discover -s samples/<name>/tests` |

`tools/manifest/validate.py` is a **copy** of iVendNext's own checker, refusing the same manifests in the same words. **Never edit it** (or any file with a "COPY — source" header, or anything in `contracts/`): a defect in one is a defect in the product's file. Report it with a *Kit defect* form (`feedback/`).

`tools/check/check.py` finds what it checks by name:

- a file whose name ends in `manifest.json`;
- any folder holding a `hooks.py` (app code);
- a `*.wasm` file;
- an answer file: `*.contract.json`, or any JSON under a `contract_samples/` folder, shaped `{"extension_point": "...", "contract": "...", "payload": {...}}`, with `"expect_refusal": "why"` for one that must be turned away (to test how your own service handles a refusal; never to hide an answer you got wrong). The samples in `contracts/extension_contracts/samples/` show the shape.

It prints one verdict line and exits non-zero on any refusal. **Report that line to the person. A green verdict is required before you say anything is ready, and before anything is deployed.** Exit code 2, `NOTHING FOUND`, is not a verdict: it means nothing in the project was checkable (a configuration-only project, or a service outside the retailer's iVendNext). Say so plainly, and name the tests you ran instead. A line marked `NOTE` is for a person to read; an app (a folder with a `hooks.py`) always carries one, because app code runs inside the retailer's site and a person reviews it.

## Where things live

| You need | Look in |
|---|---|
| Whether a customer's need can be built, by which door, from which recipe, with which limits | the needs catalogue: `needs/` (one card per need; `python3 tools/needs/needs.py search <words>`; the format: `needs/README.md`) |
| The whole guide, one chapter per way in, plus limits, testing and versioning | `guide/` (start at `guide/README.md`; the limits that apply to every project: `guide/16_possible_not_possible.md`) |
| A recipe per task | `recipes/` |
| A worked, tested sample per recipe | `samples/` (each has a README; the tests are in `samples/<name>/tests`) |
| What each extension point accepts and refuses, as a schema with accepted and refused examples | `contracts/` |
| The API: every call the samples make | `api/openapi.yaml`, `api/collection/` |
| **Everything you can use on one map:** every endpoint your app calls and every one iVendNext calls on your service, everything a manifest can add, every screen | the developer's map, `site/pages/map.md` ([developer.ivendnext.com/map.html](https://developer.ivendnext.com/map.html)); read it before you design |
| Every record type an app reads or writes, with its fields: type, required, read-only, what it links to | `api/records/<record type>.json` (one per record type; the list and why each is on it: `tools/records/records.py`), shown at [developer.ivendnext.com/records/](https://developer.ivendnext.com/records/index.html) |
| The project blueprint to fill in first | `kit/blueprint.md` (how to fill it), `kit/blueprint_template.md` (the copy you fill) |
| The extension points that exist today | `guide/09_points_and_requests.md` |
| Sign in with iVendNext, receiving webhooks, the integration user | `recipes/sign_in.md`, `recipes/webhook_receiver.md`, `recipes/integration_user.md` |
| The design kit for your own screens | `kit/design/` |

## How to start a task

1. Ask the person for the customer's need in the customer's own words (or read their brief). Copy `kit/blueprint_template.md` into the project's own folder and fill that copy (`kit/blueprint.md` says how): one row per need. The kit's file stays a template. Fill each row's way in once steps 2 and 3 have placed it; `python3 tools/needs/needs.py blueprint <id> …` prints the rows for the needs that have a card.
2. **Search the catalogue before choosing a rung.** For each need, run `python3 tools/needs/needs.py search <the customer's words>` and read the best card with `needs.py show <id>`. A card gives the verdict (*Ready*, *Ready, with limits*, *Not yet*, *Not possible*), the door, the recipe and sample, and the limits to tell the person. `search` always lists the closest cards, so first check that the card answers the need as the customer asked it; if none does, the need has no card. Use a matching card's door; go down the ways in yourself only for a need with no card. A *Not yet* card, or a need with no card that no single door meets, is not the end: compose doors first (the rule under the ways in), give the composition with its limit, and ask for an extension point (`feedback/point_request.md`) only when no composition meets the customer's outcome.
3. For each need with no card, go down the five ways in as above. Say which way you chose and why the one above it did not fit, in one line. If no single way in fits, say which doors you combined and the limit of the combination.
4. Open the recipe for that way in (`ai/`), read the sample it links, and copy the sample's shape, not its names: the samples' `pp_` prefix belongs to the samples only. Use the person's own prefix, starting with their company's first word (the App library publishes their apps only under it; ask them for it).
5. Run `python3 tools/check/check.py <project folder>` after every change that matters, and fix every refusal at its cause. Do not edit a checker or a contract to make a refusal go away.
6. Test your service the way the samples do: a pure core that imports nothing from iVendNext, with tests that need no retailer.
7. Show the person the check's verdict and what you built. Install on the sandbox only after they say yes.

## Names and words

- Call the product **iVendNext**. Do not name the framework it is built on, in text you write for the person, in a README, a comment or a message; code identifiers that a checker or the API requires stay as they are.
- Call iVendNext by its iVendNext names: records at `/api/resource/<record type>`, and every other call at `/api/method/ivendnext_mpos.api.v1.<name>` (the names: `api/README.md`). Never write an upstream package path into a call, except the sign-in addresses in `recipes/sign_in.md`.
- Prefix every name you create with the person's prefix (for example `ACME WRC` for record types, `acme_wrc` for the app and for fields added to the retailer's own record types).
- In a sandboxed function money is whole numbers in minor units and quantity is whole thousandths (`guide/08_sandboxed_functions.md`). Elsewhere, follow the recipe's own figures.

## When you are stuck

- A refusal from a checker says why in words. Read it, then read the chapter it names. Do not try a variation to slip past it.
- If no single door fits, compose doors and give the composition with its limit stated: that is the answer, not a workaround to hide. Only when no composition meets the customer's outcome without breaking a rule is the answer "this needs an extension point": use the request form, and name in it the compositions you tried and why each falls short. The catalogue's *Not yet* and *Not possible* cards say which: a *Not yet* card names the extension point to ask for, or says what to ask us when it is product work (`needs.py search <words>`); a *Not possible* card says what to do instead.
- If something in the kit is wrong or missing, say so to the person and point them to the forms in `feedback/`.
