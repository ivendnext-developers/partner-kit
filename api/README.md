# The generic kit — an API description and a request collection

Build against iVendNext **from your own server, in any language**. This folder describes the calls the samples make and gives you each one as a request you can read and send. No client library is needed.

**When to use it:** your service reads or writes a shop's sales, items, customers or stock over the API.

| | File | What it gives you |
|---|---|---|
| **API description** | `openapi.yaml` (OpenAPI 3.1, hand-written) | the calls the samples make: sales, items, customers, warehouses, serial numbers and their bundles, stock movements (create and book), comments |
| **Request collection** | `collection/NN_*.http` + `collection/run.sh` | every one of those calls, as plain HTTP files a person can read and any tool can send. `run.sh` sends them with `curl` and checks them with `jq` alone: no client library |
| **Webhook recipe** | `../recipes/webhook_receiver.md` | how to receive iVendNext's signed webhooks safely |

## Steps

1. Send every call in the collection to your sandbox site:

   ```bash
   BASE=https://<your-sandbox-site> KEY=<api key> SECRET=<api secret> bash api/collection/run.sh
   ```

2. Optional: check that the API description is valid.

   ```bash
   bash api/validate.sh
   ```

   `validate.sh` needs a local venv: `python3 -m venv .venv && .venv/bin/pip install openapi-spec-validator==0.7.1 pyyaml`. Never install it globally.

## Things you must know

- Calls other than records go to `/api/method/ivendnext_mpos.api.v1.<name>`: the shop's own functions under iVendNext names, with the same checks and answers. The names: `scan_barcode` · `get_item_details` · `price_check` (both in one call) · `apply_workflow` · `submit` · `bulk_update` · `get_count` · `get_password` · `get_docinfo` · `add_comment` · `generate_keys` · `get_logged_user` · `get_versions` · `get_role_permissions` · `add_role_permission` · `update_role_permission` · `reset_role_permissions`. A call you need that has no name here: read and write records through `/api/resource/…`, or ask for the call with a *Recipe or document gap* form (`feedback/`).
- Authentication is `Authorization: token <key>:<secret>`. A missing key gets `403`, and a wrong one `401`.
- To book a stock movement in one call, send `docstatus: 1`. Send `purpose` as well as `stock_entry_type`: over the API the purpose is not derived. The two-step form (a draft, then `POST /api/v2/document/Stock Entry/<name>/method/submit/`) also works.
- Booking serialised stock creates the serial numbers and their bundle, so the integration role needs create rights on both.
- A sale line's serial numbers are in its **Serial and Batch Bundle** (`items[].serial_and_batch_bundle` → `entries[].serial_no`). The line's `serial_no` text is the fallback.
- No client library is needed. One generated from `openapi.yaml` is optional, and the samples do not need one.

## Technical notes

- The facts under *Things you must know* were measured on our test bench.
- `openapi.yaml` validates (`validate.sh`, with two canaries).
