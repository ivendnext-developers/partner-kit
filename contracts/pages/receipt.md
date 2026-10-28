<!-- Source: ivendnext/iVendNext_PWA docs/extending/receipt.md @ 60147699cce4, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Receipt: the shop's own lines, WhatsApp, a checked layout

**Contract:** none. These are store settings on the register, not a declaration a manifest carries.
· code: `business_logic/receipt_additions.py` (`receipt_shop_additions`),
`business_logic/receipt_format_check.py` (`receipt_format_check`, `check_profile_print_format`),
`business_logic/fiscal_finalize.py` (`deliver_receipt`, `_whatsapp_channel_config`, `_dispatch_whatsapp`),
`business_logic/receipt_fiscal_mark.py` (the tax authority's QR and seal — [the fiscal reader](fiscal_reader.md)),
the till's `public/js/mpos_fiscal.js` (the Print sheet).

## 1. What it is and when it fires

Three things a shop wants on its receipt without copying the receipt layout (a copied layout stops receiving
our fixes):

- **Its own lines on the shipped receipt.** Lines under the store's name (an address, a tax number, a
  slogan) and lines at the very end (a returns policy, a thank-you in a second language). They print on every
  receipt of that register, on every print route and in the Print sheet's preview, in every frame.
- **WhatsApp on the Print sheet**, beside email and SMS, where the store has the WhatsApp app.
- **A layout checked before a register uses it.** When a manager changes a register's receipt layout, it must
  be a layout for POS sales and it must print a sale already booked; otherwise the save is refused with the
  reason.

## 2. Version

Version 1 (lane `preceipt2`, 2026-10-09).

## 3. What you set

On the **POS Profile** (the register), in iVendNext Desk, beside **Print Format**:

| Field | What it holds |
|---|---|
| Receipt Header | lines printed under the store's name |
| Receipt Footer | lines printed after *"Thank you for your purchase!"* |

The lines print as typed, one per line, in every paper language: write both languages if the store needs
both. Each line is trimmed and blank lines are dropped. They are printed as text: markup and `{{ … }}` print
as the characters you typed.

**WhatsApp** needs the WhatsApp app (`ivend_whatsapp`) installed on the site, then on the register the
engine's own **WhatsApp** box ticked and a **WhatsApp Notification** chosen (the same settings the Desk POS
sends with).

## 4. What the till does

- **The shipped receipt (`mPOS Receipt`)** prints the register's header and footer. A register that sets
  neither prints exactly what it printed before. Your **own** receipt layout prints them only if it calls
  `receipt_shop_additions(doc)` (a Jinja method returning `{"header": [lines], "footer": [lines]}`).
- **A sale's delivery** (items that arrived later, nothing to pay) prints *DELIVERY* with no totals on the
  shipped receipt. Your own layout does the same only if it asks `receipt_handover(doc)` (a Jinja method
  returning `true` for that delivery); an order's delivery is the tax sale and keeps its totals.
- **WhatsApp** is a chip on the Print sheet, on the phone, the counter and the tablet. It sends to the
  customer's **stored** mobile, the same number SMS uses. On a walk-in sale the cashier types a name and a
  number, a customer is created with that number, and the receipt goes to it: a typed number never reaches
  the sender on its own, and a stored number is never changed from the receipt. The send is the WhatsApp
  app's own, queued: the outcome reads *queued*, never *sent*.
- **Not installed, the box not ticked, or no notification chosen:** no WhatsApp chip; email and SMS work as
  before, and a refusal names WhatsApp only when it can send.

## 5. Refusals

| When | Words |
|---|---|
| a register's layout made for another document | *The receipt layout {0} is for {1}, not for a POS sale.* |
| a register's layout that fails on a booked sale | *The receipt layout {0} can't print sale {1}: {2}* |
| WhatsApp asked for where it is off | *WhatsApp receipts aren't set up for this register. Ask an admin.* |

The layout check renders the register's latest booked sale (else its company's) the way every print route
does. A company with no booked sale yet gets the document check only. A layout that is not changed is never
re-checked.

## 6. What it does not do (cut, with the reason)

- **No logo.** An image on the paper (any `src=`) sends a register that prints through the helper app to the
  device's print dialog instead — no paper cut, no cash-drawer kick — and the counter printer renders the
  receipt with no address to load an image from. A logo waits on those print routes carrying an image inside
  the receipt. Boarded as its own row. ⚠ The same holds for header or footer text that happens to read like
  markup (`src=`, `href=`, `url(`): avoid those characters in the lines.
- **No positions, per-language blocks, QR or barcode blocks** (the spec's *Retail Receipt Block* table): the
  two fields cover the tax number, address and footer a shop asks for. Boarded as its own row.
- **No manifest kind**: `receipt_blocks` stays refused by the manifest checker; a partner sets the two fields
  as it sets any register field (`custom_mpos_receipt_header`, `custom_mpos_receipt_footer`). A manifest that sets a register's layout is not built yet; when it is, it
  calls `receipt_format_check` first.
- **A WhatsApp send whose register is turned off while the Print sheet is open** is refused by the server,
  but on a walk-in the customer the cashier typed is already created, as for email.
- **Not on the gift copy, not on the on-screen receipt.** The gift receipt keeps its own layout; the receipt
  screen shows the sale, the Print sheet's preview shows the paper.
- **No dimmed WhatsApp chip on a walk-in**: the walk-in captures a customer first, as SMS does.
- **The check covers the register's receipt layout only** — not its gift or suspended-sale layouts, which
  are set on the same form.
- **WhatsApp is not offered offline**: the chip needs the server's answer, so an offline receipt offers
  email and SMS as before.
- **The register's `letter_head` and `tc_name` are not read**: the engine hides both on purpose.
