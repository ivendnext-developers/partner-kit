# S34 — Purchase orders checked by your ERP (a document check)

A distributor's ERP knows things iVendNext does not: which suppliers are on hold, and how much of its monthly purchasing budget the company has left. This app asks it before every purchase order is submitted, from Desk, an import or the API:

| The ERP says | The buyer sees |
|---|---|
| **The supplier is on hold** | the order is not submitted: *"The ERP holds this supplier: invoice 4471 is unpaid."* It stays a draft |
| **The order is over what the company has left of this month's budget** | *needs approval by Purchase Manager* (*"Over the monthly budget: 7,500.00 USD left."*). Whoever submits it meets this: a user without the role is refused, and a purchase manager is asked to approve, and a yes submits |
| **All clear** | the order is submitted, and its **ERP order number** is filled in by the ERP (`ERP-PO-9912`) |

It uses the **document check** extension point (`doccheck/1`, POS app from train T11). The recipe: [A rule checked before a document is submitted](../../recipes/document_check.md).

## What the shop does

1. **Install the app** from the App library (or paste its manifest into **Retail Extension Package** in Desk), read what it will do and consent. The install adds the field *ERP order number* to Purchase Order and the check, switched off. Nothing changes yet.
2. **Give the role *Purchase Manager*** to the people who may approve an order over the monthly budget.
3. **Switch the check on:** open it (*Retail Extension Subscription*, *ERP purchase order check*), read what is sent, tick the consent and switch it on.

**Where it shows.** In Desk, when a buyer presses **Submit** on a purchase order: a refusal in the ERP's words, or the approval by a purchase manager. An import or an API call that submits is answered the same way. The till never meets it: a document check is back office only.

**What leaves the shop.** When a purchase order is submitted: its name, its supplier, its total, each line's item and quantity, the company and the user submitting. Nothing on a draft's save. The manifest names one address; the shop sees it and the consent on the install screen and on the check before it is switched on.

**When the service does not answer** within 3 seconds, the order is not submitted (*did not answer, so this document can't be submitted yet*): the declared down answer is `refuse`, so nothing reaches the ERP unchecked. A shop that would rather submit and look later changes it to `allow_and_flag` (and reads the note on a copied order below).

## What is in the folder

| File | What it is |
|---|---|
| `manifest.json` | the field `pp_poc_erp_number` on Purchase Order and one service: a `doccheck` subscription on Purchase Order that may fill that field, installed switched off, down answer `refuse` |
| `po_check.py` | the pure core: the signature check (`verify`), the shape check (`check_context`) and the answer (`on_check`) |
| `erp.py` · `erp_standin.json` | the stand-in ERP: suppliers on hold, each company's monthly purchasing budget and what it has ordered, and the ERP's order numbers. Replace `StandIn` with a client of your ERP that has the same three methods |
| `service/app.py` | the service, standard library only: `POST /poc/check`, `GET /health`, and the app template's handshake for many shops; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the rules, the service over the wire (one shop and many), every answer against the published contract, the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s34_po_check/tests -p 'test_*.py'
```
```bash
python3 samples/s34_po_check/tests/canaries.py
```
```bash
python3 samples/s34_po_check/service/app.py samples/s34_po_check/service/.env.local
```

**Settings, one shop** (`service/.env.local`, never committed): `IVN_CHECK_SECRET` (handed back at install as `pp_poc:sub:po_check`), `PORT`. **Many shops** (the [app template](../../tools/app_template/README.md)'s handshake): `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`); each shop hands over its secret when it connects. `POC_PREFIX` names the fill field (`<prefix>_erp_number`, default `pp_poc`). `ERP_STANDIN` points at another stand-in file.

## Technical notes

- **The fill field is the app's own.** The product fills only a field the shop added; a field your package adds counts (it is installed as the shop's own field). A standard field, such as the order's schedule date, is refused when the subscription is saved: *"A service cannot fill …: on Purchase Order it may fill only a field the shop added, never a money field or one a total is computed from."*
- **The order waits for you.** The purchase order's save, its record locked, waits for your answer: at most your time to answer (3 seconds here), and at most 10 seconds for every check on one submit together. Your ERP's three questions must fit inside it.
- **Asked once.** The same order, fields, user and moment within 5 minutes gets your earlier answer, so a buyer pressing Submit again after a refusal does not reach the ERP again. The stand-in also gives one order the same number each time it asks.
- **Approve** names a role of the shop's site (*Purchase Manager*, standard in iVendNext). A user holding it is asked to approve and a yes submits; anyone else is refused.
- **The budget is the company's,** read from the request's `company`, never the submitting user's: whoever submits an order over it meets the approval.
- **Money** arrives as whole minor units with its currency; the budget is compared in the order's own currency. A currency with no budget set is not held by budget.
- **A copied order** carries the ERP number of the order it was copied from until its own submit fills a new one (a manifest cannot mark a field on a shop's record type *No Copy*). With the declared down answer `refuse` it is never submitted with the old number; a shop that switches to `allow_and_flag` should clear the field on a copy, or check the flagged rows.
- **Logs:** one line per call, the route, the status and the milliseconds, never the order.

### What was proven where

- **Laptop:** the tests above (the rules, the shape, the signature, one shop and many, a real call over HTTP, every answer against the published `doccheck/1` contract, the product's own accepted samples, the manifest through the kit's checker: 32 tests) and 13 canaries, each RED with its baseline passing.
- **The sandbox `demo-1`** (2026-10-21, POS app 2.0.0.656): the manifest installed, and the site took its field as one the service may fill; with the service unreachable, a purchase order's submit was refused (*"ERP purchase order check did not answer, so this document can't be submitted yet. Try again."*) and stayed a draft, and the site's *Retail Extension Log* row read `outcome` *unreachable*, `check_answer` *refuse*, flagged; a subscription naming a standard field (`schedule_date`) or a money field (`grand_total`) was refused at its save in the product's words. **Not run on the sandbox:** the service's own refuse, approve and fill answers on a submitted order (our service is not reachable from the sandbox; the laptop tests prove the answers against the product's contract).
