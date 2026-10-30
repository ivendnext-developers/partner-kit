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

- Calls other than records go to `/api/method/ivendnext_mpos.api.v1.<name>`: the engine's own functions under iVendNext names, with the same checks and answers (from POS version 2.1.0.667, also the POS app's own open-check calls, and from 2.1.0.669 its station-ticket and item-availability calls). The names: `scan_barcode` · `get_item_details` · `price_check` (both in one call) · `apply_workflow` · `submit` · `bulk_update` · `get_count` · `get_password` · `get_docinfo` · `add_comment` · `generate_keys` · `get_logged_user` · `get_versions` · `get_role_permissions` · `add_role_permission` · `update_role_permission` · `reset_role_permissions` · and, from POS build 2.0.0.654: `run_report` · `prepare_report` · `get_gift_card_status` · `material_request_to_stock_entry` · `sales_order_to_delivery_note` · `sales_order_to_sales_invoice` · `get_batch_qty`; from POS version 2.1.0.666: `payer_coverage` · `payer_bill_back`; from POS version 2.1.0.667, the open check's: `check_open` · `check_add_lines` · `check_change_line` · `check_remove_line` · `check_move` · `check_move_lines` · `check_merge` · `check_split_line` · `check_transfer_server` · `check_edit` · `check_close` · `check_mark_sent` · `check_void_line` · `check_comp_line` · `check_get` · `floor_status` · `check_preview`, and a till's own: `check_claim` · `check_release` · `check_note_pending` · `check_clear_pending` · `check_break_claim` · `check_print`; from POS version 2.1.0.669, the station ticket's: `station_tickets` · `station_ticket_move` · `item_availability` · `set_item_availability`. A call you need that has no name here: read and write records through `/api/resource/…`, or ask for the call with a *Recipe or document gap* form (`feedback/`).
- **The seven names added at POS build 2.0.0.654**, each the engine's own function with the rights iVendNext gives it:
  - `run_report`: run one of the retailer's reports by name, with filters, as Desk runs it. ⚠ A caller who names another `user` reads **as that user**, and a prepared report's named run is read whole by its record name: [`recipes/shop_reports.md`](../recipes/shop_reports.md).
  - `prepare_report`: queue a background run of a prepared report; it answers the run's record name. ⚠ It checks no right: any signed-in user may queue any report and read its output, filtered only by their own User Permissions (the same recipe).
  - `get_gift_card_status`: a gift card's status as the till reads it (its balance, whether it has expired, whether a payment has used it).
  - `material_request_to_stock_entry`, `sales_order_to_delivery_note`, `sales_order_to_sales_invoice`: an unsaved document built from its submitted source, as Desk's *Create* menu builds it; you save it as a record (`POST /api/resource/…`).
  - `get_batch_qty`: a batch's quantity in a store, or, given an item and a store, that store's batches of the item with stock.
- **The two names added at POS version 2.1.0.666**, the payer's ([the payer page](../contracts/pages/payer.md) §4c and §4d; chapter 9):
  - `payer_coverage` (POST): with `doctype` and `name` of a saved draft Sales Invoice, the customer's covers, each with a `ticket`; with a cover's ticket in `cover`, asks your payer service what it pays and seals its answer into the invoice. A till sale's payer is asked at the till, never here.
  - `payer_bill_back` (POST): with `sale`, `claim_ref`, `amount` (in the company's currency) and `reason`, bills a claim the payer rejected back to the customer and answers `{"journal": "<name>"}`. The same sale, claim, reason and amount answer the journal booked the first time. It needs a user who may submit a journal, or the role the payer service names.
- **The 23 names added at POS version 2.1.0.667**, the open check's ([the open check page](../contracts/pages/open_check.md); chapter 9). Every one is `POST` (the three reads, `check_get`, `floor_status` and `check_preview`, take `GET` too), and each asks its own right (the page's §2 table names it), which the retailer grants in a Retail Permission linked to your app's user:
  - **17 your app may call:** `check_open` (open a check at a place, or a tab or pre-order by its label), `check_add_lines`, `check_change_line`, `check_remove_line`, `check_move`, `check_move_lines`, `check_merge`, `check_split_line`, `check_transfer_server`, `check_edit`, `check_close` (an empty check), `check_mark_sent` (to the kitchen), `check_void_line` (a line the kitchen has) and `check_comp_line` (any line; for either, a manager's sign-in sent by your app is refused), `check_get`, `floor_status` (the store's sections, places and tabs) and `check_preview` (the shop's price of the open lines, never stored). Ask the retailer only for *open a check*, *add to a check* and *see the checks*: the rest are a person's decisions. Your app's user needs the store and one register there on its user record; `pos_profile` is that register.
  - **6 a till's own, refused to your app whatever it is granted:** `check_claim`, `check_release`, `check_note_pending`, `check_clear_pending`, `check_break_claim` (paying a check) and `check_print` (the printed check).
  - Every write carries `key`, a fresh random value per press of your button (a retry re-sends the same key and the same arguments); a change carries the `version` you last read. A line with a `rate`, `price`, `amount` or `discount`, or a `concession_note`, is refused: the shop prices a check only when the table pays it at a till.
  - The check's records are written only through these calls: `/api/resource/…` on them is refused (`WrittenOutsideDoorError`).
- **The four names added at POS version 2.1.0.669**, the station ticket's ([the station ticket page](../contracts/pages/station_ticket.md); chapter 9), the POS app's own calls for a kitchen screen:
  - `station_tickets` (`GET` or `POST`): with `store` and, optionally, `station`, that station's board now (every station's when none is named): every ticket sent in the last 12 hours that is not bumped, and those bumped in the last 30 minutes, oldest first. It asks *May Work a Kitchen Screen* in the Retail Permission linked to your app's user, and is fenced to that user's stores.
  - `station_ticket_move` (`POST`): with `store`, `kitchen_order`, `ticket` and `state`, moves one ticket one step (`new` to `started` to `ready` to `bumped`); the same step again answers `"already": true`, and a skip or a step back is refused. The same right and fence.
  - `item_availability` (`GET` or `POST`, with `warehouse` and, optionally, `item_code`) and `set_item_availability` (`POST`, with `item_code`, `warehouse` and what changes: `sold_out`, `sold_out_until`, `available_from`, `available_to`; one left out keeps its value): read, and mark, an item sold out at one store (until a time or until cleared) or the hours it is sold. ⚠ They answer to the item-availability rights (read or write on Retail Item Availability) for every store, not to your user's stores: ask for them only where your app may mark every store's items.
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
