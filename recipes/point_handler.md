# A till key: one pure core, answered from your own server — the recipe

A till key is a button on the till, an extension point the retailer switches on. When the cashier presses it during a sale, your own server answers: the warranty on each item, the bin each item sits in. It is for iVendNext Partners, and for the CitiXsys Consulting Team. **Your code runs on your own server, never inside a customer's iVendNext.** **Reference implementation:** `samples/s1_warranty/` (the core `core.py`; the remote binding `remote/wrapper.py`) and `samples/s2_bins/` (`core.py`, the service's `/point/where_is_it`, declared as a remote key in its manifest).

**When to use it.** Rung 3 of the build ladder, after configuration and a connected app. Use it when the cashier needs your answer at the till. The answer is a **message** for the cashier, or **sale details** the cashier applies (one value per detail per sale). It never changes a price, a total or a payment.

**A till key that asks an outside system:** [guide chapter 1c](../guide/01c_how_the_data_travels.md) traces two (a chain's loyalty system, and a telecom company's plans with sample S52) hop by hop, with each chain's own account for the outside system.

**The shape.** Write your logic once as a **pure core**: `answer(context, your reference data) → result`, importing nothing from iVendNext. Then add a few lines around it — the **remote binding** — on your own server. Keeping the core pure lets you test it without a running iVendNext (step 3).

## Steps

1. **Know what the till sends you: the context.** It is read-only:

   ```json
   {"sale_ref": "…", "store": "<warehouse>", "pos_profile": "…", "company": "…", "currency": "ZAR",
    "operator": "<user>", "customer": "<customer or null>",
    "lines": [{"item_code": "…", "qty": 1.0, "uom": "Nos", "luid": "l0"}]}
   ```

   ⛔ **No prices, no totals, no serial numbers.** If you need a serial, ask the cashier on your own page, or read the booked sale afterwards (connected app). The till sends what is on the device, so never grant value on the context alone.

2. **Answer in the till's closed vocabulary.** Two kinds, nothing else:

   ```json
   {"message": {"title": "Warranty", "body": "PP-WRC-PHONE: 24 months; AIRPODS-3: 12 months", "level": "success"}}
   {"sale_attributes": [{"sale_attribute": "<an active Sale Attribute>", "attribute_value": "…"}]}
   ```

   Title up to 60 characters, body up to 280, level `info` · `success` · `warning`, at most 20 sale details. **One bad part refuses the whole answer**: the till never applies half. Keep a long answer inside the cap yourself (S1 ends with "… and N more").

3. **Test the core without a retailer's iVendNext.** Record a few real contexts once, then unit-test against them: `python3 -m unittest discover -s samples/s1_warranty/tests -p 'test_core.py'`.

4. **Switch the key on — the retailer decides.** iVendNext Desk → **POS Studio** → open the theme → **Apps** tab → tick the key → **Save**. Every till whose profile wears that theme shows the key on the counter layout; the phone layout shows none. A press for a key that is not switched on is refused.

5. **Press it the way the till does.** The till calls `POST /api/method/ivendnext_mpos.api.app_button.press` with `app`, `key`, the basket and its device id. The press needs the sell permission, an enrolled device and (where seats are enforced) an open day. A press with no device is refused.

6. **Remote binding — the same core on your own server, with nothing installed in the retailer's iVendNext.** The retailer sets it up in two places:
   - a **System Manager** opens **Retail Remote App Key** in Desk and adds one record per key: your name as the partner, an app name, the key, its label, what it may return, your **HTTPS** address, a signing secret you both hold, and the time to answer — 3 seconds unless raised, at most 10 on this record; a manifest may declare at most 5 (`recipes/manifest.md`). The System Manager also ticks **the customer's consent** to send the listed sale details to that address;
   - then the store switches the key on in **POS Studio → Apps**, like any other key.

   Your side is about ten lines around the core, behind your HTTPS endpoint:

   ```python
   def answer(context):          # the whole binding
       codes = sorted({l["item_code"] for l in context.get("lines") or []})
       terms = {**MY_TERMS, "item_group": tenant.item_groups(codes)}   # your own store + one API read
       return core.warranty_answer(context, terms)
   ```

   Each call is one `POST` with the headers `X-iVendNext-Timestamp`, `X-iVendNext-Signature` and `X-iVendNext-Request-Id` and the body `{"app", "key", "returns", "context"}`.
   - Verify every call against the **raw body** before parsing. The signature is the base64 HMAC-SHA256 of `<timestamp>.<raw body>` with the shared secret. A timestamp more than five minutes from your clock is refused.
   - Answer a JSON object of at most 64 KB, well inside the time to answer.
   - Only **HTTPS** is called, with the certificate checked against your host name. An address that resolves to a private network is refused unless the retailer's site sets `mpos_remote_app_allow_private` (for test sites).

7. **Test the remote binding with the same cases as the core.** Call your endpoint the way the till does (step 6), with the recorded contexts, and check the answers match the core's. Our stand-in caller (`tools/standin_caller/`) signs and judges a call the way the released key does. The sample wrapper has test-only fault routes, on only when a test starts it with `PP_WRAPPER_FAULTS=1`: your copy deletes them.

## What is refused, and why

- **A method outside your own app's package.** The till runs only code the declaring app ships.
- **Any answer kind but a message and sale details.** Nothing else reaches the sale.
- **Money.** No price, discount, tax or total, ever.

## When your service is down, and when the till is offline

The till refuses in words, with **nothing added to the sale**, never a partial answer. The words below are the ones the released remote key publishes:

| What happens | The cashier reads |
|---|---|
| Your service takes longer than the deadline — or trickles its reply | "*Warranty* did not answer in time. Nothing was added to the sale." |
| Service down, a non-2xx status, a redirect, a bad signature | "*Warranty* could not finish. Nothing was added to the sale." |
| Not JSON, not HTTP at all, oversize, a malformed or partial answer, an undeclared kind | "*Warranty* answered in a way this till cannot use. Nothing was added to the sale." |

**Offline:** the key is online-only. On an offline till it is dimmed and the sale goes on without it.

## What is coming

- **Keys declared from data:** a System Manager adds the Retail Remote App Key record by hand (step 6), or your manifest declares it (`remote_keys`: `recipes/manifest.md`). **From POS build 2.0.0.646** a key your manifest declares is ready in POS Studio > Apps once the app is installed: the consent on the install screen is the key's consent, and the store switches the key on there. On an older build it installs switched off with consent not given.
- **Shipped since:** a check before tender that may allow, refuse with a reason, or ask the cashier, before payment: its own door ([the till guard recipe](till_guard.md), `samples/s23_till_guard/`).

## Technical notes

### What was proven where

- Proven on our test bench (2026-10-03 and 2026-10-04): **you build the remote form — your code runs on your own server, never inside a customer's iVendNext.**
- Step 4: on the bench the same switch was made as data (a theme carrying the key, worn by one till profile), and a press for a key that is not switched on is refused.
- Step 5, **on the bench:** signed in as a cashier, enrolled a device, bound the outlet, pressed → a success message; the same press with no device was refused. Through the real press, S1 passed all six test cases, and S2's "Where is it?" named each line's bin.
- `mpos_remote_app_allow_private` is for test benches.
- ⚠ **What was proven where.** The remote key was released (merged) on 2026-10-03, after these tests ran. On the bench this binding was called by our stand-in caller, which follows that key's published contract (the same headers, signature, size cap and refusals), and judged by the till's own validator. Since then the released key has answered presses on our test bench, 2026-10-07, over HTTPS with a certificate trusted for the run: S1's *Warranty* through the till's own press endpoint, called from the bench's console as the cashier, not from a screen; S6's *AI tip* pressed by a cashier on the till's screen, the iVendNext POS app in a desktop browser. A press from a physical till device was not tried.
- **The title's one binding.** This recipe covers the remote binding only. The earlier binding of the same core inside iVendNext (a hosted app inside it, proven on our test bench on 2026-10-03) is not offered: outsiders never write Python inside a retailer's site (`samples/s1_warranty/README.md`, *The two forms*).
- When your service is down: the till's **stated answer** is a refusal in words, with nothing added to the sale; our stand-in caller writes the same words as the released remote key.
- **Offline:** per the till's own documentation the key is dimmed on an offline till and the sale goes on without it; this was not run here (no offline till on the bench).

### Bench results for each failure

| What happens | Bench result |
|---|---|
| Your service takes longer than the deadline — or trickles its reply | refused at 3.01 s although the service slept 5 s; refused at 3.01 s when it sent its headers a byte a second |
| Service down, a non-2xx status, a redirect, a bad signature | refused |
| Not JSON, not HTTP at all, oversize, a malformed or partial answer, an undeclared kind | refused, whole |

### Tests

- `samples/s1_warranty/tests/test_core.py` — the core, without a retailer's iVendNext.
- On our test bench, every failure case in the table above ended in the stated answer: **34 of 34 green**, including canaries that prove the checks can fail. The sample wrapper's test-only fault routes are on only when the test starts it with `PP_WRAPPER_FAULTS=1`; your copy deletes them.
