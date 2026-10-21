<!-- Source: ivendnext/iVendNext_PWA docs/extending/fields.md @ 4c3f11b550f1, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Field rules

**Contract:** [`fields.v1.schema.json`](../extension_contracts/fields.v1.schema.json)
· samples: [`samples/fields/`](../extension_contracts/samples/fields/)
· code: `business_logic/pos_fields.py` (`validate_field_rules` at the theme's save; `refuse_missing_required`
in the new-customer write; `show_fields` in the offline snapshot; `receipt_item_fields` on the receipt) · the
till: `public/js/mpos_fields.js`.

## 1. What it is and when it fires

A shop's own say over the fields the till shows, per POS Studio theme, with no code. **Hide** a field
nobody uses, **relabel** it in the shop's own word, **require** it on a new customer, or **show** up to
three more Item fields and three more Customer fields — on the screens, and Item fields on the receipt too.
The rules are rows of the theme's **Fields** tab
(`Retail POS Theme Field`), so every till whose outlet wears the theme follows them, in every frame —
phone, counter and tablet.

They fire when the till lights up: the rules ride the theme the till reads at boot, and each screen asks
them as it draws. **Require** fires again on the server, at the till's own new-customer write, whatever
the till sent — refused live, flagged after payment or in the offline drain. ⚠ It governs that door only,
for a session bound to an outlet whose profile wears the theme (the drain reads the cashier's outlet at
drain time): a customer created another way (iVendNext Desk, an import, a REST insert of Customer, another
app's own create call, a session with no bound outlet) is not checked. A theme with no rule draws every screen exactly as it ships.

## 2. Version

Version 1: four actions on six screens. `receipt_preview` (the receipt) joined on 2026-10-09 (lane
`pfields2`), `show` only. A new screen or a new field on a screen's list is added in version 1; an action
never changes what it does.

## 3. What you declare

One row per rule on the theme (a shop's manager in POS Studio's **Fields** tab, or a partner through the
REST API or an import — the theme is one Desk record):

| Screen (`surface`) | `hide` | `relabel` | `require` | `show` (≤ 3 more of) |
|---|---|---|---|---|
| `customer_create` — the new-customer sheet | `phone` · `email` · `more_details` (type and group) | `customer_name` · `phone` · `email` | `phone` · `email` | — |
| `customer_card` — the customer's card | `phone` · `member_since` · `lifetime` · `visits` · `points` | `member_since` · `lifetime` · `visits` · `points` | — | Customer fields |
| `cart_line` — a line of the sale | — | `item_name` · `qty` (the column headings) | — | Item fields |
| `item_result` — an item in search and browse | `item_code` | `item_code` (the word *SKU*) | — | Item fields |
| `sale_details` — the sale-details sheet | an optional Sale Attribute (by its name) | a Sale Attribute | — | — |
| `receipt_preview` — the receipt: on screen, on paper and on the offline slip | — | — | — | Item fields |

Each row: `surface`, `field`, `action`, and for `relabel` / `show` a `label` (the shop's text, shown
exactly as typed, up to 40 characters; for `show`, the line's heading) with an optional `language` (blank =
everyone; a cashier's language picks its own row first, as button names do), and `sequence` for the order of
`show` lines. One action per screen and field. A shown field is an **Item** or **Customer** field of type
Data, Select, Int or Check, at most **three more of each** across the theme (a field shown on two screens
counts once).

## 4. Every refusal, in the product's words

**When the theme is saved:**

- *"⟨screen⟩ is not a till screen field rules apply to."* · *"⟨action⟩ is not a field action."* · *"Name the
  field each rule applies to."*
- *"⟨field⟩ on ⟨screen⟩ can't take this rule."* — the field is not on that screen's list for that action
- *"⟨field⟩ can't be hidden: the sale needs it."* — the customer's name, or a required Sale Attribute
- *"Nothing more can be shown on ⟨screen⟩."* · *"⟨DocType⟩ has no field ⟨field⟩."* · *"⟨field⟩ is a ⟨type⟩
  field. Only Data, Select, Int and Check fields can be shown."*
- *"Up to 3 more ⟨DocType⟩ fields can be shown. This theme shows ⟨n⟩."*
- *"On the receipt a rule can only show an item field. Money, tax and the receipt's own lines print as they
  are."* — a `hide`, `relabel` or `require` on `receipt_preview`
- *"⟨field⟩ on ⟨screen⟩ has two different rules. Keep one."* · *"⟨field⟩ on ⟨screen⟩ has the same rule
  twice."*
- *"A label is at most 40 characters."* · *"Give ⟨field⟩ its new label."*
- a theme that came with the till: *"⟨theme⟩ came with the till and stays as it ships. Use Save as a new
  theme."* — a shipped theme carries no field rules

**When a new customer is added** without a field the theme requires: *"Phone is required here."* ·
*"Email is required here."* — from the till before it sends, and from the server whatever was sent.

*Reset to original* in POS Studio restores the theme's look and button settings; its field rules stay as
they are.

A rule already saved stays saveable when its field later goes (the shop deletes its own field, or a
release changes a screen): the theme still saves. Online the till stops showing the field at once; a till
offline keeps the last value it stored until its catalogue or book is next walked in full.

## 5. Consent, and the down answer

Nothing leaves the shop and nothing is called, so no consent is recorded and there is no service to be
down. Who may edit a theme is POS Studio's own permission.

## 6. Offline

The rules ride the theme in the till's boot snapshot, so hide, relabel and require work with the network
off. A **shown** field rides the offline snapshot by name — the catalogue for Item fields, the customer
book for Customer fields — so its line works offline too. A field the theme does not show is never in the
snapshot. Changing which fields a theme shows makes each till pull its catalogue (or its customer book)
again once, at its next sync.

⚠ A shown Customer field widens a book that otherwise carries only a customer's name, phone, tax id and
group: it is the shop's choice to put more of a customer on its tills. With the book's at-rest encryption
setting on, the whole book is withheld from the device, shown fields included.

⛔ **Require through the offline drain is a flag, never a refusal:** a customer added offline without a
required field is created when the sale drains (the customer paid hours ago), and the *Sales to review*
report lists it.

## 7. Money and limits

No price, amount, tax or tender field is on any screen's list, and a shown field cannot be Currency,
Float or Percent. A rule changes what the till shows and asks for, never what it charges.

Limits: label 40 characters · 3 more Item fields and 3 more Customer fields per theme · six screens.

## 7a. The receipt (`receipt_preview`)

A shown Item field prints one line under each item that has a value — *Pack: 12 × 500 ml* — on the receipt
screen, on the paper (the shipped `mPOS Receipt`, every print route and the Print sheet's preview) and on the
offline slip, in the same words. Nothing else on the receipt takes a rule: money, tax, totals, tenders, the
tax authority's marks, the receipt number, the buyer's tax id, the reprint and duplicate marks and the till
time print as they are. A shop's own words go in the register's header and footer ([receipt](receipt.md)).

- **Which theme:** the one the SALE's register wears, whichever till reprints it.
- **Which language:** the paper's — the language the receipt prints in (the sale's, else the receipt
  layout's, else the site's), never the cashier's. The offline slip uses the store's language (the
  layout's, else the site's); a till that has not started online since this release uses its cashier's
  language on the slip until it next does, as the slip's own words do.
- **Which value:** the Item's as it reads when the receipt is printed; a reprint after the Item changed
  prints the new value.
- **Your own receipt layout** prints the line only if it calls `receipt_item_fields(doc)` (a Jinja method
  returning `{item row name: "Label: value · …"}`); the on-screen receipt and the slip follow the theme
  whatever layout the register uses. ⚠ The same holds for a shipped receipt a site had customised before
  this release: its update is declined at migrate (an Error Log row says so), and that site's paper lacks
  the line until the layout calls the method.
- **What a value prints as:** as stored — a Check field prints `0` or `1`, a Select its option as typed.
  Data and Select fields read best on paper.
- **Not on the gift receipt**, which keeps its own layout, and not in the text the slip's Share sends.

## 7b. Requiring a sale detail per register

`require` stays on the new-customer sheet. A Sale Attribute's *Required* switch is the engine's, and it
applies to every register; a line detail has no switch at all. A shop that must refuse a sale missing a
detail on some registers only does it with a [check service](partner_check.md): the `check/1` context
carries the sale's `sale_attributes` and each line's `line_attributes`, and the check runs at Pay and again
at every door that moves money. Answer `refuse` with a reason the cashier can act on at this till, such as
*"Add the prescription number to finish the sale."*. An offline sale is flagged when it drains, never
refused. ⚠ Set the check's down answer to *refuse*: with *allow and flag*, a sale passes while the
service is down. The cost is the shop's own check service (with the consent the check records), not a
till setting.

## 7c. The points rule beyond the card

A `customer_card · points` rule reaches every place the till shows the customer's points: the card's
loyalty row, the customer chip on the sale, the phone's facts sheet, the counter and tablet card, and the
customer search row. A `relabel` uses the shop's word there; a `hide` removes the figure there too. Not
the payment screen's redeem controls, nor the finished sale's *points redeemed* line: they read the
loyalty programme's own points as an amount the sale spent. A `relabel` on the card's loyalty row also
drops its *redeem at payment* hint.

## 8. Worked examples

**A shop that never takes emails, but always takes a phone.** Two rows: `customer_create · email · hide`
and `customer_create · phone · require`. The new-customer sheet has no email field, and adding a customer
without a phone at the till is refused with *"Phone is required here."* — by the server too, so an older
till cannot get round it. (A customer added in iVendNext Desk or through an import is not a till's, and is not
checked.)

**A pack size on every line.** Add a Data field `custom_pack_size` to Item, then `cart_line ·
custom_pack_size · show · Pack`. Each line reads *Pack: 12 × 500 ml* under the item, online and offline;
add `item_result · custom_pack_size · show · Pack` to show it in search too (still one of the three).

**The shop's own word.** `customer_card · points · relabel · Stars` (blank language) and a second row
with `Estrellas` for `es`: an English cashier sees *Stars*, a Spanish one *Estrellas*.

## 9. Telling an AI assistant

> Write field rules for an iVendNext POS theme, version 1, as JSON matching
> `fields.v1.schema.json#/$defs/declaration`; the samples under `samples/fields/` show accepted and
> refused themes. Use only the screens and fields this page's table lists, one action per screen and field,
> `require` only for a new customer's phone or email, labels of at most 40 characters, and `show` only for
> an Item or Customer field of type Data, Select, Int or Check — at most three of each. On
> `receipt_preview` use `show` only, with an Item field. Never a price, amount, tax or tender field. Name
> only fields that exist.
