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

Before choosing a recipe, find the need's card in the needs catalogue: `python3 tools/needs/needs.py search <the customer's words>` gives its verdict and its door, and the door picks the recipe below (AGENTS.md, step 2). A need with no card is placed on the ladder by hand.

Start any of them by telling the assistant: *"Read AGENTS.md, then follow the recipe in the ai folder that matches this need: …"*.
