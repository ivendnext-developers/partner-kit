# The extension points' contracts

What each iVendNext POS extension point accepts and refuses, as the product publishes it: one page and one machine-readable
schema per point, with accepted and refused sample files. A partner's service, and the AI assistant that helps build it,
can check an answer against these before it reaches a shop. They are what the [samples](../samples/) and the
[recipes](../recipes/) are tested against.

| Point | Page | Schema |
|---|---|---|
| Desk action | [pages/desk_action.md](pages/desk_action.md) | [desk_action.v1.schema.json](extension_contracts/desk_action.v1.schema.json) |
| Document check (`doccheck/1`: your answer before a back-office document is submitted) | [pages/doccheck.md](pages/doccheck.md) | [doccheck.v1.schema.json](extension_contracts/doccheck.v1.schema.json) |
| Event feed | [pages/event_feed.md](pages/event_feed.md) | [event_feed.v1.schema.json](extension_contracts/event_feed.v1.schema.json) |
| Field rules (fields) | [pages/fields.md](pages/fields.md) | [fields.v1.schema.json](extension_contracts/fields.v1.schema.json) |
| Fiscal reader | [pages/fiscal_reader.md](pages/fiscal_reader.md) | [fiscal_reader.v1.schema.json](extension_contracts/fiscal_reader.v1.schema.json) |
| Fulfil at sale (`fulfil/1`: a code your service makes for a paid sale line) | [pages/partner_fulfil.md](pages/partner_fulfil.md) | [partner_fulfil.v1.schema.json](extension_contracts/partner_fulfil.v1.schema.json); a stand-in voucher service, [standins/voucher_service.py](extension_contracts/standins/voucher_service.py); the conformance check the page names, ported to the kit as [tools/contracts/tests/test_fulfil_conformance.py](../tools/contracts/tests/test_fulfil_conformance.py): run it against your own service with `FULFIL_URL` and `FULFIL_SECRET` |
| Label layout | [pages/label_layout.md](pages/label_layout.md) | [label_layout.v1.schema.json](extension_contracts/label_layout.v1.schema.json) |
| List mark (a coloured label on a Desk list row, a manifest kind) | [pages/list_mark.md](pages/list_mark.md) | [list_mark.v1.schema.json](extension_contracts/list_mark.v1.schema.json) |
| Print template readers (`ivn_rows`, `ivn_value`: what a manifest's print format may read) | [pages/print_template_readers.md](pages/print_template_readers.md) | none: the manifest's schema and its samples |
| Receipt (store settings: the shop's own lines, WhatsApp, a checked layout) | [pages/receipt.md](pages/receipt.md) | none: store settings, not a declaration |
| Capture at the till | [pages/partner_capture.md](pages/partner_capture.md) | [partner_capture.v1.schema.json](extension_contracts/partner_capture.v1.schema.json) |
| Check at the till | [pages/partner_check.md](pages/partner_check.md) | [partner_check.v1.schema.json](extension_contracts/partner_check.v1.schema.json) |
| Partner page | [pages/partner_page.md](pages/partner_page.md) | [partner_page.v1.schema.json](extension_contracts/partner_page.v1.schema.json) |
| Price module (`price/1`: a discount after the promotions) | [pages/price.md](pages/price.md) | [price.v1.schema.json](extension_contracts/price.v1.schema.json) |
| Remote till key | [pages/remote_till_key.md](pages/remote_till_key.md) | [remote_till_key.v1.schema.json](extension_contracts/remote_till_key.v1.schema.json) |
| Save rules | [pages/save_rules.md](pages/save_rules.md) | [save_rules.v1.schema.json](extension_contracts/save_rules.v1.schema.json) |
| Scan source | [pages/scan_source.md](pages/scan_source.md) | [scan_source.v1.schema.json](extension_contracts/scan_source.v1.schema.json) |
| App wallet (`wallet/1`: a payment the till checks with your service) | [pages/wallet.md](pages/wallet.md) | [wallet.v1.schema.json](extension_contracts/wallet.v1.schema.json) |
| Payment connector (`paygw/1`, revision 1.0: card, push and wallet connectors on your own server) | [pages/paygw.md](pages/paygw.md) | none: the conformance kit on your sandbox is the check; the payments team's stand-in connector is [paygw/partner_stub.py](paygw/partner_stub.py) |

Samples for each point are in [`extension_contracts/samples/<point>/`](extension_contracts/samples/): `accepted/` files
the product takes, `refused/` files it turns away. The folder also holds the manifest's own schema,
[package_manifest.v1.schema.json](extension_contracts/package_manifest.v1.schema.json), with its samples.

## Check an answer yourself

```python
import sys; sys.path.insert(0, "tools/contracts")
from check import errors
errors("desk_action", "answer", {"message": {"title": "Route assigned", "body": "14 lines across 3 aisles.", "level": "success"}})   # [] when it holds
errors("desk_action", "answer", {"message": "Route assigned"})                                  # ['$.message: not object']
```

(A sample file wraps the value as `payload`; the value alone is what you check.) This runs with this repository alone; `jsonschema` is not needed.

## Where these files come from

They are **copies** of files in the product's repository (`ivendnext/iVendNext_PWA`), taken at one commit (the payment connector's two files come from the payments app's repository, `ivendnext/iVendNext_Payments`, at one commit of its own); the commit
and every file's source path are in [EXPORT_SOURCES.md](../EXPORT_SOURCES.md). Each page and the checker carries a
header naming its source; the schemas and samples are JSON and cannot, so they are listed there. Only the links inside
the pages were changed, so they point at the files here; four calls are named by what they do rather than by the framework's own name, one customer's name and one reference to our own board are left out, and the samples' lane ids and one refused sample's framework name are dropped. Our own kit check compares every file with its source on each
change, so a copy cannot drift. **A defect in one is a defect in the product's file:** report it with a *Kit defect*
issue (members) or the partner form, and we take it to the product's board.
