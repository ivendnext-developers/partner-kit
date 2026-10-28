# Prompt recipes for an AI assistant

One recipe per way into iVendNext, plus one for building a whole reference app from a brief. Each is written for an assistant that has read [AGENTS.md](../AGENTS.md) and is working with a person. A recipe gives the goal, the files to read, the steps, the check to run and what "done" looks like. Each links the sample whose shape you copy. Each recipe is a short route into the full recipe and chapter it names; read those too.

| Way in | Recipe |
|---|---|
| 1. Configure | [1_configure.md](1_configure.md) |
| 2. Outside app and the event feed | [2_outside_app.md](2_outside_app.md) |
| 3. Till key | [3_till_key.md](3_till_key.md) |
| 4. Manifest | [4_manifest.md](4_manifest.md) |
| 5. Sandboxed function | [5_sandboxed_function.md](5_sandboxed_function.md) |
| A reference app from a brief | [6_build_from_a_brief.md](6_build_from_a_brief.md) |

Before any recipe, if the person asks how an iVendNext app runs, where the data lives, whether customers collide or how many apps to build, answer from [`guide/01a_how_it_all_works.md`](../guide/01a_how_it_all_works.md) and [`site/pages/questions.md`](../site/pages/questions.md); how data travels through an outside system is chapter 1c, [`guide/01c_how_the_data_travels.md`](../guide/01c_how_the_data_travels.md).

Before choosing a recipe, find the need's card in the needs catalogue: `python3 tools/needs/needs.py search <the customer's words>` gives its verdict and its door, and the door picks the recipe below (AGENTS.md, step 2). A need with no card is placed on the ladder by hand.

**What you can use.** Before designing, read the developer's map ([`site/pages/map.md`](../site/pages/map.md), live at [developer.ivendnext.com/map.html](https://developer.ivendnext.com/map.html)): every endpoint in both directions, everything a manifest can add and every screen. A record type's fields, which are required and which read-only, are in [`api/records/`](../api/records/) (one file per record type). Answer *is there an endpoint for X* or *can I add a field to Y* from those, never from memory.

Start any of them by telling the assistant: *"Read AGENTS.md, then follow the recipe in the ai folder that matches this need: …"*.
