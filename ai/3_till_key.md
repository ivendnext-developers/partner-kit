# A till key: the cashier taps, your server answers (way in 3)

**Goal.** A key on the till. When the cashier presses it during a sale, the till calls your HTTPS service, and your answer is a message for the cashier or details added to the sale. Your service runs on your own server.

**Read.** [guide/06_till_keys.md](../guide/06_till_keys.md) · [recipes/point_handler.md](../recipes/point_handler.md) · the contract: [contracts/pages/remote_till_key.md](../contracts/pages/remote_till_key.md) · for an AI hint: [recipes/ai_till_key.md](../recipes/ai_till_key.md) and [guide/13_ai.md](../guide/13_ai.md).

**Samples to copy.** [samples/s1_warranty/](../samples/s1_warranty/) (`core.py` and the remote binding in `remote/`) · [samples/s2_bins/](../samples/s2_bins/) (`service/`) · [samples/s6_ai_till_key/](../samples/s6_ai_till_key/) (a hint from the customer's own AI model).

**Steps.**
1. Write the logic as a pure core: `answer(context, your reference data) → result`. It imports nothing from iVendNext and returns a message (title up to 60 characters, body up to 280) or sale details. **One bad part refuses the whole answer.**
2. Write the binding around it: verify the signature against the **raw body** first, then call the core, then answer a small JSON object well inside the time to answer (design for 3 seconds). The recipe has the headers and the signature.
3. Declare the key as a remote key in a manifest (way 4), as `samples/s2_bins/manifest.json` does. The retailer's administrator gives consent and the store switches it on (from the release that carries it, the key is ready in POS Studio > Apps once the app is installed); you do not.
4. Test with recorded contexts and with the stand-in caller [tools/standin_caller/](../tools/standin_caller/), which calls your endpoint the way the till does.
5. Answer your service being down the way the recipe lists. The cashier reads fixed sentences and nothing is added to the sale.

**Check.** The core's tests; a sample answer file in `contract_samples/` for each kind of answer you return (`"extension_point": "remote_till_key"`; copy a file from `contracts/extension_contracts/samples/remote_till_key/` as the shape); and `python3 tools/check/check.py <project folder>`, which checks the manifest and those answers.

**Done looks like.** The check prints a green verdict; a wrong or old signature is refused; a slow or failing service gives the cashier the published sentence; the answer never carries a price, total or payment; the person has seen the manifest before it was installed.

**Never.** Return money, call out to a customer's data without the retailer granting it, or make the till wait for you. For an AI hint, bring the customer's own model and key; ship none and charge for none.
