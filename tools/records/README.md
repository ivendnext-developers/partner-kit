# The record-type reference — what your app can read and write

**What it gives you.** One page per record type an app most often reads or writes in a retailer's iVendNext (a sale, a till sale, an item, a customer, stock, lots and serial numbers, loyalty, gift cards, coupons, payments, purchase documents and your app's own user), each with its fields: their type, which are required, which are read-only or hidden, and what each links to, with the address to read and write it. The pages are on the developer site at [developer.ivendnext.com/records/](https://developer.ivendnext.com/records/index.html), and the data behind them is in [`api/records/`](../../api/records/), one JSON file per record type, for you or your assistant to read.

**Where the fields come from.** The product itself, at the kit's pinned release: each record type's definition, the fields iVendNext adds to it and iVendNext's changes to those fields, merged as the site shows them. The pages are read again at every release.

**Which record types.** Every record type of the site that a sample, a recipe, a needs card, a contract page or the API description names, and the retail core. The list, and why each is on it, is `RECORDS` in [`records.py`](records.py); `census` fails when the kit names one of the site's record types (in an address, a manifest, code font, italics or a quoted string) that is neither listed, shown as a table on a listed one, nor set aside in `SKIP` with its reason. Every record type on the site is named in [`api/records/site_record_types.json`](../../api/records/site_record_types.json). Any other record type is reached the same way, at `/api/resource/⟨Record Type⟩`.

## Steps

1. **Read the reference:** open the site's [record types](https://developer.ivendnext.com/records/index.html), or `api/records/⟨record_type⟩.json`.
2. **Read it again from a site** (a maintainer, at each release; it changes nothing on the site). Sign in with an administrator's key or password:

   ```bash
   IVN_BASE=https://⟨your-sandbox⟩ IVN_KEY=⟨admin key⟩ IVN_SECRET=⟨admin secret⟩ IVN_RELEASE="POS ⟨build⟩" python3 tools/records/records.py fetch
   ```

3. **Check** that the snapshots match the list and hold no word they must not:

   ```bash
   python3 tools/records/records.py check
   ```

## Technical notes

- `fetch` reads `GET /api/resource/DocType/⟨name⟩`, then `Custom Field` and `Property Setter` filtered to that record type, and the record types of its tables, through the API alone. Layout rows (section, column and tab breaks) and rows that hold no value are dropped.
- Text naming an upstream product is rewritten to iVendNext's word where the name is a word, or dropped and logged where it is code; the writer refuses a snapshot that still names one.
- Needs only Python 3 and its standard library.

### Tests

`python3 -m unittest discover -s tools/records/tests -p 'test_*.py'`: 16 tests, offline, over a recorded definition with one added field and one change: the merge, the words refused, the census and the snapshot check (also over the kit's own `api/records/`), each with a planted fault that turns it red.
