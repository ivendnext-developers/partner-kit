# A rule checked before a document is submitted (document check) — the recipe

Some back-office documents must not become final until an outside system agrees: a purchase order to a supplier the ERP holds, a goods receipt against the supplier's terms, a stock transfer against stock held elsewhere. The **document check** asks your HTTPS service when such a document is submitted, from every door (the Desk form or list, a data import, the API), and the submit waits for one answer from a closed list. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, building one.

**Reference implementation:** `samples/s34_po_check/` — *Purchase orders checked by your ERP*: a held supplier refused, an order over the company's monthly budget approved by a purchase manager, a clear order filled with the ERP's own number.

**When to use it.** The check reads data your system holds, and the person submitting can wait a few seconds. **Back office only:** never a till sale, and never a record the till's own booking writes (a layaway's order, a delivery's invoice, the backing records of the till's quote edit and quote cancel, an offline sale reaching the server); those are logged *not asked*. For the till's sale use a check before payment ([recipe](rule_guard.md)); for a format or a limit on one record's own fields, a save rule ([recipe](save_rules.md)). On a POS app from before train T11 (2026-10-16), which has no document check, a workflow step only your service can take does the same job ([recipe](check_by_workflow.md)).

**The four rules, here.** Your service's code never runs inside the shop's site: our code asks your service and applies your answer from a closed list. **No answer writes money,** and `fill` writes only the fields the subscription names, each one the shop added.

## Steps

1. **Declare the check in your manifest,** with the field your answer may fill, if any:

   ```json
   "custom_fields": [
     {"dt": "Purchase Order", "fieldname": "acme_erp_number", "fieldtype": "Data", "label": "ERP order number", "insert_after": "supplier"}],
   "extension_subscriptions": [
     {"key": "po_check", "point": "doccheck", "label": "ERP purchase order check", "endpoint_url": "https://your.server/poc/check",
      "timeout_seconds": 3, "down_answer": "refuse",
      "settings": {"record_type": "Purchase Order", "send_fields": "name, supplier, grand_total, items(item_code, qty)",
                   "on_validate": false, "fill_fields": ["acme_erp_number"]}}]
   ```

   - `record_type`: one record type that is submitted. A till's own record (POS Invoice, the POS day's opening and close) is refused.
   - `send_fields`: the Desk action's grammar (40 fields, 5 tables, 500 rows a table). Send only what your check reads; the shop consents to that list.
   - `fill_fields`: at most 10, each a field **the shop added**: a field your manifest adds counts. Text, a number, a date, a choice or a link; never money, never read-only. A standard field is refused when the subscription is saved: *"A service cannot fill schedule_date: on Purchase Order it may fill only a field the shop added, never a money field or one a total is computed from."*
   - `on_validate: true` asks you at a draft's save too. Not on Sales Order, Sales Invoice, Delivery Note, Payment Entry or Journal Entry, which the till's booking also writes.
   - `down_answer`: `allow_and_flag` (the submit goes on, flagged), `refuse` (nothing is submitted unchecked) or `ask` (the user decides).
2. **Answer.** Verify the signature (base64 HMAC-SHA256 of `<timestamp>.<raw body>` with the subscription's secret), read `context.fields` (money as minor units with its currency, quantities in thousandths), and answer within your time:

   | Answer | The user sees |
   |---|---|
   | `{"verdict": "allow"}` | the submit goes on |
   | `{"verdict": "refuse", "reason": "The ERP holds this supplier: invoice 4471 is unpaid."}` | the reason; the document stays a draft |
   | `{"verdict": "ask", "question": "The ERP shows 40 on order already. Go on?"}` | the question in Desk; *Yes* submits |
   | `{"verdict": "approve", "role": "Purchase Manager", "reason": "Over the monthly budget."}` | *needs approval by* the role; a user who holds it submits and approves |
   | `{"verdict": "fill", "fields": {"acme_erp_number": "ERP-PO-9912"}}` | the document is submitted carrying the value |

   Every sentence is plain text of 1 to 140 characters. Check each answer against the contract before you ship (`tools/contracts/check.py`, `errors("doccheck", "answer", value)`).
3. **Test it** on the laptop (S34's tests: every answer against the contract, a canary that answers wrong), then on your sandbox: install, tick the consent and switch the check on, submit a document with your service down and read the declared down answer in Desk and on the *Retail Extension Log*.

## What is refused, and why

- **A till's sale as the record type,** and any record the till's booking writes: the cashier has no screen for your question, and the customer is waiting. The till's door is the check before payment.
- **A fill field that is standard or money:** your answer arrives after the record's own checks ran, so a ledger account or a total written then would never be checked.
- **`ask` or `approve` on a submit that runs in the background** (an import, a large bulk submit): nobody can answer, so it is refused in words that say so. For such records answer `allow` or `refuse`.

## When your service is down, and when the till is offline

- **Down or slow:** the answer you declared applies (`refuse` reads *"… did not answer, so this document can't be submitted yet. Try again."*). The document waits for you, its record locked: at most your time to answer, and at most 10 seconds for all of one submit's checks (3 services per record type at most).
- **Offline:** none. Back-office documents are submitted on the server; a sale the till made offline never reaches you.

## Technical notes

### Bounds

- **Asked once:** the same document, fields, user and moment within 5 minutes gets your earlier answer, so a resubmit after a refusal does not reach you again.
- **A save rule that would refuse the submit runs first,** so a submit a house rule refuses never reaches you. After a `fill`, the shop's save rules run once more over the filled record (a flag rule can write a second row).
- **The log row of a refused submit is written later:** the product queues it outside the refused transaction, and a scheduled job writes it (every 15 minutes on our sandbox), so the row's time is the job's, not the submit's. The product calls it best effort: a cache clear or a restart before the job runs loses the row (the refusal itself is not affected).
- **Consent:** the consent text is built from the record type, the moment, the fields sent and the fields an answer may fill; a change to any of them clears the consent and stops the calls until the shop ticks it again.

### What was proven where

- **Laptop:** S34's 32 tests and 13 canaries; the product's accepted samples pass the kit's contract check, and an answer with no fill fields or an unknown verdict is refused by it.
- **The sandbox `demo-1`** (2026-10-21, POS app 2.0.0.656): S34's manifest installed, its field taken by the site as one a service may fill; with the service unreachable and `refuse` declared, a purchase order's submit was refused in the words above and stayed a draft, and the *Retail Extension Log* row (`outcome` *unreachable*, `check_answer` *refuse*, flagged) was written by the next 15-minute job; a subscription naming a standard field (`schedule_date`) or a money field (`grand_total`) was refused at its save. **Not run on the sandbox:** a service's own refuse, approve and fill answers on a submitted document (no service of ours is reachable from the sandbox); the laptop tests prove those answers against the product's contract.
