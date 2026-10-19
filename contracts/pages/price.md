<!-- Source: ivendnext/iVendNext_PWA docs/extending/price.md @ 8c955ffd9fcf, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Pricing extension point

**Contract:** [`price.v1.schema.json`](../extension_contracts/price.v1.schema.json)
· samples: [`samples/price/`](../extension_contracts/samples/price/)
(the answers, the inputs, `module_input.json` — the exact bytes a module reads, the same on the server and the
till — and `target_rate.json`) · code: `business_logic/partner_price.py` (`apply_price_point`, `groups_of`,
`module_input`, `validate_answer`, `target_rate`, `offline_price`), the till's twin in
`public/js/mpos_partner_price.js`, the one call site in `mpos_cart._resolved_doc`.

## 1. What it is and when it fires

A price rule the shop's promotions cannot express — a member discount that multiplies with a promotion, a cap
per line from your own tier table — answered by **your sandboxed module** (a WebAssembly function, see the
partner check's section 6 and the Wasm kit). It may only take money **off** a line. It runs:

- on the iVendNext POS server, **after every promotion** (item-level and whole-sale), on the
  promotion-adjusted line, before the line's tax is worked out — at the basket's preview and again at the
  booking, through one shared step, so the customer pays exactly what the till showed;
- on the till itself when it is offline, inside its own price ladder;
- again at the drain, with the version the till used (section 6).

It never runs on a return, and a line carrying an applied pricing rule, a gift card or a price of 0 is never
shown to it.

⚠ **The Desk POS** (the back office's own selling screen) does not run this extension point. A sale rung there
is priced without your module until the platform has its own call for it.

## 2. Version

Version 1 (`price/1`, `v: 1` in the input). A module is admitted for this extension point only under our
certificate (iVendNext signs a module's SHA-256, its extension point, its version and whether it is metered). A module certified by
iVendNext runs once a System Manager adds it in iVendNext Desk; a shop that adds none runs none.

## 3. What your module reads, and what it answers

**It reads** (canonical JSON: sorted keys, no spaces, raw UTF-8; money in the currency's own minor units —
3 digits for KWD, 0 for JPY, never a fixed ×100; quantity in thousandths; no negative number):

```json
{"config":{"rules":[…your own settings…]},"currency":"AED","currency_exponent":2,
 "customer_group":"Select","lines":[{"item":"X","item_group":"Products","line_total_minor":10000,
 "luid":"0@90.00","promotion_discount_minor":1000,"qty_milli":1000,"unit_price_minor":9000}],"v":1}
```

- One module line is every row of **one basket line at one price**, keyed `"<basket line>@<price>"`: two
  lots of one line are one module line; a promotion that splits a line into two prices is two.
- `line_total_minor − promotion_discount_minor` is the line's **current amount**: after every promotion,
  coupon, staff discount, markdown and offer. A line priced above its list reads a promotion of 0.
- `config` is the subscription's own settings object, set by the shop.
- `customer_group` is `null` when the till does not know it offline: a customer its offline customer book
  does not hold (with the store's default book scope, one who has no sale at this store yet) or a book older
  than the snapshot validity. A rule keyed on the group then takes nothing off on the till, and a sale the
  till took nothing off is booked at the drain exactly as charged (section 6).

**It answers** a list, at most one entry per line it was shown; a line not named keeps its price:

```json
[{"luid":"0@90.00","discount_minor":450,"reason":"Select 5%"}]
```

**Judged whole** — one bad entry and nothing is taken off any line:

- each `luid` is one the module was shown, and named once;
- `discount_minor` is a whole number from 0, written as an integer (`450`, never `450.0` or `4.5e2`: the
  server refuses those, and a till cannot tell them apart), no more than the line's current amount, and **no
  more than the shop's limit** (section 5) of it;
- `reason` is plain text of 1 to 40 characters (no `<` or `>`, no control characters);
- then the platform's own save-time judges read the adjusted lines — an item's own discount limit
  (`Item.max_discount`) and the below-cost check. If either would refuse the sale, the whole answer is
  undone: your cut alone never makes a sale the till cannot book. (A whole-sale discount the cashier adds
  later can still meet the below-cost check, exactly as it can with no module.)

The cut is written as the line's price: the new unit price is `(price × quantity − discount) ÷ quantity`,
**rounded up** at the price's grain, so the money taken off is never more than you asked (three of an item
at 33.33 with 4.99 off books 31.67 each: 4.98 off).

## 4. What the cashier sees

| What happened | The till |
|---|---|
| Your module took something off | the basket line names it beside the promotion, *"Member 5% −R 5.00"*, on the phone, the counter and the tablet; the counter's Discount column keeps the promotion's own percent; the receipt (screen and paper) prints the same line under the item, and the offline slip prints the reason |
| Your answer was refused, or your module gave no answer (a trap, its step counter) | nothing — the platform's own price; a flagged row on *Sales to review* when the sale books at the till's payment, its split payment or an order (other doors — a layaway, an order change, a fulfilment, a return or exchange — book the platform's price without the row); offline, the till keeps no record of a refusal |
| Your module ran out of its one-second clock | *"⟨label⟩ took too long to answer. Try again, or get a manager."* (offline: *"… took too long on this till. …"*) — before any money; the clock never decides a price |
| Offline, the till does not hold your module's bytes, or cannot start one | *"This till could not read its pricing. Reconnect, then try again."* |

## 5. The subscription, and the shop's limit

A **Retail Extension Subscription** with extension point `price`, transport `wasm` (the Desk form offers
nothing else and picks it for you; an address is refused: a price cannot wait on a network), the admitted
**Retail Extension Module**, and the settings your module reads. At most one enabled pricing subscription
answers a POS Profile.

⭐ **Most a module may take off a line (%)** (`max_discount_percent`) is set by the shop's System Manager on
the subscription, never by your package. It starts at **0**, and at 0 your module is not even run: a newly
installed module takes nothing off until the shop says how far it may go. A cut over it refuses your whole
answer.

## 6. Offline, and the drain

While online, the till keeps your module's bytes in its own store by SHA-256, named by the boot snapshot with
the label, the shop's limit and your settings. Offline, the till's price ladder runs the same module on its
own composed lines: the lines without your cut give the module's input and the whole-sale promotion's
verdict, then the lines with your cut are priced and taxed. The queued sale carries your module's SHA-256 and
its adjustments.

At the drain the server re-prices with **the version the till used**:

1. that version, re-run on the server's numbers, when it was admitted for this extension point and active at
   some moment of the sale's window (the till's checked capture time, less the store's snapshot validity, plus
   the clock allowance) — the log row says whether it agreed with the till;
2. else, when that version can no longer run (withdrawn, its file deleted 30 days after its window closed):
   the till's own adjustments, judged by section 3's rules on the server's numbers and today's limit, then
   booked and flagged;
3. else the platform's own price: the customer was charged less, so the sale goes to review on *Sales to
   review*.

An online sale whose checkout was interrupted after the money was taken is replayed at the drain with the
module run live; if it runs out of its clock there, that counts as no answer: the sale books at the platform's
price with a flagged row on *Sales to review*, never a refused sale.

⛔ A paid sale is never refused at the drain. A queued sale whose till took nothing off books nothing off.

Offline the till does not hold an item's own discount limit (`Item.max_discount`): a cut over it is charged
on the till, and at the drain the server's judges undo it, so the sale goes to review.

## 7. Money and limits

- Discount only, after the promotions; a module can never raise a price or touch a tax.
- A whole-sale promotion is judged on the lines **before** your cut (your cut never costs a customer a
  promotion they earned), and its percent then applies to the lines it covers **after** your cut: 10% off
  the qualifying items stays 10% of those items, whichever line your module cut.
- Your module's money never counts toward a cashier's own discount limit (the stack threshold).
- A partner's package cannot install a pricing subscription today: the subscription is made in the back
  office. A package kind for it is owed and will never carry the shop's limit.
- Your module sees a line's price however it was set: a list price, a price the cashier typed, or a price
  read from a weighed item's barcode. A shelf label priced at the till shows what a customer with no group
  pays, so a rule for every customer (`"*"`) is on the label and a member rule is not.
- A whole-sale Pricing Rule's minimum is judged after your cut, as the platform judges it at the save.
- The Desk POS limit is stated in section 1.

## 8. Worked example (S1)

A 100.00 line with a 10.00 promotion, a 5% member rule for the *Select* group, the shop's limit 10%: the
module reads `line_total_minor 10000`, `promotion_discount_minor 1000` and answers `450` (5% of 90.00); the
line books at 85.50 with *"Select 5% −4.50"* under it, at the preview, at the booking and offline alike.

## 9. Telling an AI assistant

> Build a `price/1` WebAssembly module with the Wasm kit's template (edit `src/point.rs` only). Read the input
> in `price.v1.schema.json` `$defs.input`; answer a JSON array of `{luid, discount_minor, reason}` for lines
> to take money off, never more than `line_total_minor − promotion_discount_minor`. Integers only, no float.
> Check every published sample in `samples/price/` and keep the reason 1–40 characters. The shop decides how
> far you may go; assume it may be less than you ask, and that an over-limit answer takes nothing off at all.
