<!-- Source: ivendnext/iVendNext_PWA docs/extending/print_template_readers.md @ 60147699cce4, copied unchanged except the links, the framework's raw SQL and its readers, named by what they are: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Print template readers — `ivn_rows` and `ivn_value`

**Samples:** [`samples/package_manifest/`](../extension_contracts/samples/package_manifest/)
(`accepted/07_a_print_format_reading_rows.json` · `refused/10_…` · `refused/11_…` · `refused/27_…`)
· code: `business_logic/template_readers.py` (the readers), `business_logic/template_requester.py` (who asked),
the print-format rules in `business_logic/manifest_check.py` · tests: `tests/test_template_readers.py`.

## 1. What it is

A print format that shows more than its own record: a price list printed with its item prices and each
item's photo, an invoice showing each line's batch expiry, a customer's open orders. Two readers a print
template may call do that, with the rights of the person viewing the print:

| Reader | Arguments | Returns |
|---|---|---|
| `ivn_rows` | the record type, then by name: `fields` (a list of plain field names), `filters` (a list of `[field, operator, value]`, or a dict of `field: value` or `field: [operator, value]`), `order_by` (one field, `asc` or `desc`; none = the record type's own order), `limit` (1 to 200, default 50), `start` (0 or more) | a list of rows |
| `ivn_value` | the record type, then by name: `field`, and `name` or `filters` | one value, or nothing |

```jinja
{% for r in ivn_rows("Item Price", filters={"price_list": doc.name},
                     fields=["item_code", "price_list_rate", "uom"]) %}
  {% set photo = ivn_value("Item", name=r.item_code, field="image") %}
  <p><img src="{{ photo }}"> {{ r.item_code }} {{ r.price_list_rate }} / {{ r.uom }}</p>
{% endfor %}
```

A price list of 600 items is three calls (`start` 0, 200, 400), or one print per item group.

## 2. Whose rights

Both readers read as the person viewing the print, the way a Desk list does: their roles, their user
permissions (a branch user with one store sees that store's rows only), the record type's own permission
rules and the field levels they may read. A field they may not read is left out of each row, and a filter
or a sort on such a field is refused.

They answer only for **the person who asked for the page**. Every web request stores who signed in (by
the session, an OAuth token or an API key) before its handler runs, tied to that request; the readers
answer nothing when the current user is anyone else, or when the stored value belongs to another request. So, in practice:

| The print is… | The readers show |
|---|---|
| opened in Desk, or downloaded by a program with a user's API key | what that user may read |
| opened through a portal account | what the portal user may read (usually none of these record types: empty) |
| opened through a share key, a published web form, or by a visitor not signed in | nothing |
| rendered as another user inside a request (the customer's receipt download behind a QR code renders as the administrator) | nothing |
| rendered later, from the e-mail queue or a background job (Desk's **Background Print**) | nothing |

**Bound:** a print rendered inside the sender's own request carries the sender's view. A Desk e-mail sent at
once renders as the sender, and so does the till's e-receipt when no Notification is linked to it (with a
Notification linked, the print is rendered at the queue flush and the readers show nothing). The same template
therefore shows different related rows by how it was sent: write a template meant to be sent so that it reads
well with its related tables empty. Two more renders run inside a person's request: **Send Now** on a queued
e-mail renders the attachment as whoever presses it (a manager retrying a customer's e-receipt sends the
manager's view), a Notification's subject and message render as the person whose save sent it, and Desk's
bulk print of up to 25 records from a list renders as the person who pressed it.

## 3. What they read

Record types of the iVendNext layer, the engine and the POS app only. Never the framework's own record types
(users, roles, sessions, logs, e-mail, keys, versions …), and never a single, virtual, table, log or custom
record type, or one holding a password field.

**Bounds (v0):** a partner package's own record types are not served yet, nor another record's table rows; and
the framework types prints often show — Address, Contact, File, Currency, Country — are refused with the rest.
A secret a record type keeps in an ordinary field (a gift card's barcode) is printable to a viewer who may read
it in Desk, and goes out with an e-mail sent in their request.

## 4. A refusal never breaks the print

A refused call answers an empty list (or nothing) and the print renders. Each refusal by shape, record type or
rights writes one Error Log line per record type per request, naming the reason and never a filter's value;
a Guest, a switched user or a queued render writes none. An argument the readers do not take (`user`,
`ignore_permissions` …) is a template error: no argument can widen a read. A page that calls a reader is never
kept in the website cache.

A call with both `name` and `filters` answers nothing and writes no log line (it is refused before the
fence). Refused shapes: a field that is not a plain name (`item_group.name`, `count(name)`); a filter that is not three
parts, or a filter string; an operator outside `=`, `!=`, `<`, `<=`, `>`, `>=`, `like`, `not like`, `in`,
`not in`, `is`, `between` (the tree operators such as `descendants of` read a hierarchy without rights); a list
value except for `in`, `not in` and `between`; two sort fields; `limit` outside 1–200; `start` below 0.

## 5. The checker's print-format rules — a tripwire, not a control

When a manifest installs a print format, the checker
(see the *Installing a manifest* page) also:

- **refuses** the framework's raw SQL (`db.sql`), its query builder and its outside fetchers (`make_*_request`);
- **refuses** template syntax inside an address the print loads (`src`, `href`, `srcset`, `poster`, `background`,
  `action`, `formaction`, `url(`, `@import`) unless the whole value is one plain reference such as `{{ photo }}`
  or `{{ row.image }}` — so `data-src=` is read too, and a filtered `{{ a.b | e }}` or a
  `href="mailto:{{ doc.email_id }}"` is refused, and so is ordinary text that reads like one of those names
  followed by `=` (*Corrective action = {{ doc.remark }}*, a `data-action=` value) — a bound, never loosened;
- **warns** on the framework's template helpers that read records without the viewer's rights (`get_all`,
  `get_list`, `get_doc`, `get_mapped_doc`, `get_value`, `get_print`, `call`, anything under `db.` …) and on
  `receipt_partner_code` (a partner's code, printed with no rights check), naming `ivn_rows`; formatting helpers such as `format_value` are not warned;
- **refuses**, since version 2.1.0 of the POS app, a row or value read called on the framework —
  `get_all`, `get_list`, `db.get_value`, `db.get_all`, `db.get_list`, each called on the framework's own object — whose
  record type, written as a quoted first argument (`'Item Price'` or `doctype='Item Price'`), is one `ivn_rows` serves
  (`get_all('Item Price')`, `db.get_value("Company", …)` …, on that object): read it through `ivn_rows` or
  `ivn_value`, or show the printed record's own fields. These stay a warning, because `ivn_rows` has no
  replacement for them: a read of a type it does not serve (the framework's Address, Contact, Letter Head …, a
  child table, a settings record); a whole-record read such as `get_doc` (its child rows are out of
  `ivn_rows`' reach), a render, a map or a count; and a read whose record type is not one quoted name, or that
  reaches the reader through an alias (its `db` object given another name with `{% set %}`) or a subscript (`['get_all']` on that object), or names it
  as a later keyword (`get_all(fields=[…], doctype='Item Price')`).
  Remember that `ivn_rows` and `ivn_value` return nothing to a share-key visitor or in a mail; a receipt that
  must show a value there prints it from the record's own fields.

It reads the template's text, so it catches the obvious only. Six known evasions pass it, each a known-pass test:
the raw SQL reached by indexing (`db["sql"]`), the `attr` filter with a name built at render time, `render_template` on a built string, a
whole tag printed from a string, a `<meta http-equiv=refresh>`, and an address set with `{% set %}` then printed
as `{{ u }}`. The framework's own helpers stay available, warned, for every record type `ivn_rows` does not serve. Treat the readers as the way to read
other records with the viewer's rights, not as a guarantee about every template a site holds.

On the framework our sites run, every template gets the same restricted helper set; there is no setting that
widens it.

## 6. Not covered

- The till's screen receipt: drawn on the device, it never calls a template reader. A server print needs the
  server, as before.
- A template's `doc` is the live record, and its methods can read around any reader (a stated limit of the
  design, outside the readers' fence).
