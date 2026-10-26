# The generic kit — an API description and a request collection

Build against iVendNext **from your own server, in any language**. This folder describes the calls the samples make and gives you each one as a request you can read and send. No client library is needed.

**When to use it:** your service reads or writes a retailer's sales, items, customers or stock over the API.

| | File | What it gives you |
|---|---|---|
| **API description** | `openapi.yaml` (OpenAPI 3.1, hand-written) | the calls the samples make: sales, items, customers, warehouses, serial numbers and their bundles, stock movements (create and book), comments |
| **Request collection** | `collection/NN_*.http` + `collection/run.sh` | every one of those calls, as plain HTTP files a person can read and any tool can send. `run.sh` sends them with `curl` and checks them with `jq` alone: no client library |
| **Webhook recipe** | `../recipes/webhook_receiver.md` | how to receive iVendNext's signed webhooks safely |

## Steps

1. **Before the first run, make sure iVendNext has the item `PP-WRC-PHONE`**, a stock item with serial numbers. Files 05 and 06 receive it, and six more files read what those two made, so without it eight files fail (*PP-WRC-PHONE is not a stock Item*). The integration user may not make items, so make it once with your administrator's key:

   ```bash
   curl -s -X POST "https://<your-sandbox-site>/api/resource/Item" -H "Authorization: token <admin key>:<admin secret>" \
     -H "Content-Type: application/json" \
     -d '{"item_code": "PP-WRC-PHONE", "item_name": "PP Warranty Phone", "item_group": "All Item Groups",
          "stock_uom": "Nos", "is_stock_item": 1, "has_serial_no": 1}'
   ```

   Or in Desk: Item → New, code `PP-WRC-PHONE`, *Maintain Stock* and *Has Serial No* ticked.

2. Send every call in the collection to your sandbox site:

   ```bash
   BASE=https://<your-sandbox-site> KEY=<api key> SECRET=<api secret> bash api/collection/run.sh
   ```

3. Optional: check that the API description is valid.

   ```bash
   bash api/validate.sh
   ```

   `validate.sh` needs a local venv: `python3 -m venv .venv && .venv/bin/pip install openapi-spec-validator==0.7.1 pyyaml`. Never install it globally.

## Things you must know

- Calls other than records go to `/api/method/ivendnext_mpos.api.v1.<name>`: the engine's own functions under iVendNext names, with the same checks and answers. The names: `scan_barcode` · `get_item_details` · `price_check` (both in one call) · `apply_workflow` · `submit` · `bulk_update` · `get_count` · `get_password` · `get_docinfo` · `add_comment` · `generate_keys` · `get_logged_user` · `get_versions` · `get_role_permissions` · `add_role_permission` · `update_role_permission` · `reset_role_permissions` · and, from POS build 2.0.0.654: `run_report` · `prepare_report` · `get_gift_card_status` · `material_request_to_stock_entry` · `sales_order_to_delivery_note` · `sales_order_to_sales_invoice` · `get_batch_qty`; from POS version 2.1.0.666: `payer_coverage` · `payer_bill_back`. A call you need that has no name here: read and write records through `/api/resource/…`, or ask for the call with a *Recipe or document gap* form (`feedback/`).
- **The seven names added at POS build 2.0.0.654**, each the engine's own function with the rights iVendNext gives it:
  - `run_report`: run one of the retailer's reports by name, with filters, as Desk runs it. ⚠ A caller who names another `user` reads **as that user**, and a prepared report's named run is read whole by its record name: [`recipes/shop_reports.md`](../recipes/shop_reports.md).
  - `prepare_report`: queue a background run of a prepared report; it answers the run's record name. ⚠ It checks no right: any signed-in user may queue any report and read its output, filtered only by their own User Permissions (the same recipe).
  - `get_gift_card_status`: a gift card's status as the till reads it (its balance, whether it has expired, whether a payment has used it).
  - `material_request_to_stock_entry`, `sales_order_to_delivery_note`, `sales_order_to_sales_invoice`: an unsaved document built from its submitted source, as Desk's *Create* menu builds it; you save it as a record (`POST /api/resource/…`).
  - `get_batch_qty`: a batch's quantity in a store, or, given an item and a store, that store's batches of the item with stock.
- **The two names added at POS version 2.1.0.666**, the payer's ([the payer page](../contracts/pages/payer.md) §4c and §4d; chapter 9):
  - `payer_coverage` (POST): with `doctype` and `name` of a saved draft Sales Invoice, the customer's covers, each with a `ticket`; with a cover's ticket in `cover`, asks your payer service what it pays and seals its answer into the invoice. A till sale's payer is asked at the till, never here.
  - `payer_bill_back` (POST): with `sale`, `claim_ref`, `amount` (in the company's currency) and `reason`, bills a claim the payer rejected back to the customer and answers `{"journal": "<name>"}`. The same sale, claim, reason and amount answer the journal booked the first time. It needs a user who may submit a journal, or the role the payer service names.
- **A till sale at a POS Profile with a partner's check in scope** (from POS version 2.1.0.666): `submit` refuses a POS Invoice there, as every door but the till's own does, until the check holds (*"This sale needs a partner's check before it is paid. Ring it up on a till."*, chapter 9). Book such a sale from a till.
- Authentication is `Authorization: token <key>:<secret>`. A missing key gets `403`, and a wrong one `401`.
- To book a stock movement in one call, send `docstatus: 1`. Send `purpose` as well as `stock_entry_type`: over the API the purpose is not derived. The two-step form (a draft, then `POST /api/v2/document/Stock Entry/<name>/method/submit/`) also works.
- Booking serialised stock creates the serial numbers and their bundle, so the integration role needs create rights on both.
- **A lot that may not leave the shop** (from POS version 2.1.0.666): a Stock Entry, Delivery Note, stock-moving Sales Invoice or POS Invoice you create that takes a recalled lot, an expired one, or one from a quarantine store (*Is Rejected Warehouse*) out of its store is refused at the booking, with the row, the lot and the reason; a Material Issue, a move into a quarantine store and a return to the supplier are let through (chapter 9).
- **A register book's line** (from POS version 2.1.0): a receipt, stock entry or other stock document you submit for an item a register book takes is refused when it leaves a column the book requires empty or takes the book's balance below zero (chapter 7); a background job's post is flagged instead.
- A sale line's serial numbers are in its **Serial and Batch Bundle** (`items[].serial_and_batch_bundle` → `entries[].serial_no`). The line's `serial_no` text is the fallback.
- No client library is needed. One generated from `openapi.yaml` is optional, and the samples do not need one.

## Technical notes

- The facts under *Things you must know* were measured on our test bench.
- `openapi.yaml` validates (`validate.sh`, with two canaries).
