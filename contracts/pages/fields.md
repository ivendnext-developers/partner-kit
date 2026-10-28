<!-- Source: ivendnext/iVendNext_PWA docs/extending/fields.md @ 60147699cce4, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Field rules

**Contract:** [`fields.v1.schema.json`](../extension_contracts/fields.v1.schema.json)
· samples: [`samples/fields/`](../extension_contracts/samples/fields/)
· code: `business_logic/pos_fields.py` (`validate_field_rules` at the theme's save; `refuse_missing_required`
in the new-customer write; `input_fields` / `input_values` for the fields asked at customer add and edit;
`show_fields` in the offline snapshot; `receipt_item_fields` on the receipt) · the
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

Version 1: four actions on seven screens. `receipt_preview` (the receipt) joined on 2026-10-09, `show` only. The money words joined on 2026-10-16: four figures on
`cart_line` and the `totals` screen, relabel only, with the list price shown (§7d). `show` on `customer_create` (the shop's own
customer fields asked for at add and edit, §7e) joined on 2026-10-25. A new screen or a new field on a screen's list is added in version 1; an action
never changes what it does.

## 3. What you declare

One row per rule on the theme (a shop's manager in POS Studio's **Fields** tab, or a partner through the
REST API or an import — the theme is one Desk record):

| Screen (`surface`) | `hide` | `relabel` | `require` | `show` (≤ 3 more of) |
|---|---|---|---|---|
| `customer_create` — the new-customer sheet and the till's customer edit | `phone` · `email` · `more_details` (type and group) | `customer_name` · `phone` · `email` | `phone` · `email` | the shop's own Customer fields, asked for (§7e) |
| `customer_card` — the customer's card | `phone` · `member_since` · `lifetime` · `visits` · `points` | `member_since` · `lifetime` · `visits` · `points` | — | Customer fields |
| `cart_line` — a line of the sale | — | `item_name` · `qty` (the column headings) · the money figures `price` · `discount` · `amount` (§7d) | — | Item fields · the figure `list_price` (§7d) |
| `item_result` — an item in search and browse | `item_code` | `item_code` (the word *SKU*) | — | Item fields |
| `sale_details` — the sale-details sheet | an optional Sale Attribute (by its name) | a Sale Attribute | — | — |
| `receipt_preview` — the receipt: on screen, on paper and on the offline slip | — | — | — | Item fields |
| `totals` — the basket's totals words, online (§7d) | — | `discount` · `charges` · `delivery` · `tax` · `grand_total` | — | — |

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
- asking for a customer field (§7e): *"⟨field⟩ is not one of the shop's own fields. Only a field the shop or
  an app added can be asked for."* · *"⟨field⟩ is a ⟨type⟩ field. Only Data, Select, Int and Date fields can be
  asked for."* · *"⟨field⟩ is filled in by the system, so the till can't ask for it."* · *"Up to 3 customer
  fields can be asked for. This theme asks for ⟨n⟩."* · *"⟨field⟩ belongs to the till itself, so it can't be
  asked for."*
- *"On the receipt a rule can only show an item field. Money, tax and the receipt's own lines print as they
  are."* — a `hide`, `relabel` or `require` on `receipt_preview`
- *"⟨field⟩ on ⟨screen⟩ has two different rules. Keep one."* · *"⟨field⟩ on ⟨screen⟩ has the same rule
  twice."*
- *"A label is at most 40 characters."* · *"Give ⟨field⟩ its new label."*
- *"A money label can't carry a digit, a % or a currency sign: the figure beside it is the till's."* — a
  label on a money figure or a `totals` field with a digit of any script, a `%`, a currency symbol, or one of
  the site's own currency signs as a word, in any case (the rand's *R* or *r*). This one binds a saved row too: its label is
  checked again at every save unless it is saved word for word as before.
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

**A field only some roles read** (one at a permission level above 0: set by the shop in Customize Form, or by
an app's `read_roles` / `write_roles`, `package_install.md`): a shown **Customer** field
reaches the card, the search and the scan only for a cashier whose roles read its level, online; for anyone
else it is left out, as if the theme did not show it. It never rides the offline book, for anyone (the book is
the device's, and a teammate who takes the till offline reads it), so a till that starts offline draws
nothing for it. The book's page
names it as withheld, and a device holding a copy from before clears its customer book and fills it again. A
shown **Item** field above level 0 never reaches a till, its catalogue or a receipt, for anyone (one everyone
reads but only some change included), and a till stops drawing it at its next start. ⚠ The customer fields the till always carries (name, phone, email, tax id, group) are read as
they are: put one of them at a level and the till still shows and searches it.

⛔ **Require through the offline drain is a flag, never a refusal:** a customer added offline without a
required field is created when the sale drains (the customer paid hours ago), and the *Sales to review*
report lists it.

## 7. Money and limits

No price, amount, tax or tender FIELD is on any screen's list, and a shown field cannot be Currency,
Float or Percent. The money words of §7d name four FIGURES the till already prices, never a field, and
take a new word only. A rule changes what the till shows and asks for, never what it charges.

Limits: label 40 characters · 3 more Item fields and 3 more Customer fields per theme (the list price
takes no place) · seven screens.

## 7a. The receipt (`receipt_preview`)

A shown Item field prints one line under each item that has a value — *Pack: 12 × 500 ml* — on the receipt
screen, on the paper (the shipped `mPOS Receipt`, every print route and the Print sheet's preview) and on the
offline slip, in the same words. Nothing else on the receipt takes a rule: money, tax, totals, tenders, the
tax authority's marks, the receipt number, the buyer's tax id, the reprint and duplicate marks and the till
time print as they are. A shop's own words go in the register's header and footer ([receipt](receipt.md)).

The same shown Item fields print on a **kitchen ticket**, one line under the dish (an *Allergens* field
the theme shows reaches the kitchen this way); the ticket takes no other rule. Offline the till prints
the ticket itself, from the same shown fields in its own copy of the catalogue, and routes each dish to
its kitchen from the till's boot snapshot (`kitchen`: the Items that name a kitchen, every item group's
kitchen resolved up the tree, the till's default) — a kitchen set on the Item or item group reaches the
device at its next connected start.

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

## 7d. The money words (`cart_line` figures, `totals`)

A shop can call the basket's money by its own words, and show what a line's price was before any cut.

- **The line's figures** (`cart_line`): `price` is the charged unit price (the *Price* column), `discount`
  the cut (*Discount*), `amount` the line total (*Total*; *Line total* in the till's item panel, *Total* in
  the quote-to-sale basket). Each takes `relabel` only. `list_price` is the unit price before any cut —
  the price list's price online, the till's own price basis offline — and takes `show` only, its `label` the
  heading (*List price* when blank). On the counter it is a sixth column after *Price*; on the phone and the
  tablet it leads each line's sub-line, struck through only when the charged price is below it (a markup
  is never drawn as a reduction), and the till's item panel shows it too. A line with no list price shows
  *—*.
- **The totals** (`totals`): `discount`, `charges`, `delivery`, `tax` and `grand_total` take `relabel`
  only. The word reaches the basket's totals box, the till drawn behind other screens (*Grand Total*) and
  the payment screen's sale panel on the counter and tablet (*Discount*, *Charges*, *Delivery*, *Tax*).
  *Item Qty* is not money and keeps its word.
- **What never changes:** a figure — no rule moves, rounds, hides or replaces one, and no money cell
  becomes an input. ⛔ `hide` is refused on every money figure and every `totals` field; `show` on
  `totals`.
- **Left alone on purpose:** offline, the basket's and the payment sheet's *provisional* words (*Total.
  Includes tax*), which keep a provisional figure from being read as ex-tax; the payment screen's *Due*,
  a different figure once redeems are taken off; the receipt on screen, on paper and on the offline slip,
  whose money words are its print format's. These keep the shipped words too: the customer display (the
  shopper's own screen), POS Studio's preview pictures, the screens of a sale already made (held sales,
  Find a sale, fulfilment, returns), the charges sheet's heading (*Charges on this sale*) and the total a
  screen reader speaks.
- **Stated bound — the paper:** the till's screen can say *Total incl. VAT* while the receipt says
  *Total* (and *Tax (incl.)*). A shop that wants its word on paper names its own print format.
- **Stated bound — the quote-to-sale basket:** its line figure is the line total without any charge on
  the line, so on a converted quote whose line carries a charge the shop's word for *Total* heads that
  figure, not the charged one the basket grid shows.
- **Stated bound — claims:** the money rule blocks digits and signs, not number words or claims. *Total
  incl. fifteen percent VAT* passes, and so does *Price incl. VAT*, which is false on a profile whose prices
  exclude tax. One theme can serve several tills: word a money label for every POS profile the theme serves.
- **Stated bound — offer lines:** on an item sold at a cross-sell offer's special price, the list price is
  the offer's own base price, as the back office prices it, so that line shows no struck price.

## 7e. Asking for the shop's own customer fields (`show` on `customer_create`)

A pharmacy records a patient's ID before it sells a controlled medicine; a liquor or duty-free shop records the
buyer's ID or date of birth. A `show` rule on `customer_create` puts one of the shop's own Customer fields on
the till's **new-customer sheet** and on its **customer edit** — both, from the one rule — so the cashier
types it where the sale happens, in every frame. The till sends what was typed with the create or the edit.

- **Which fields:** one the shop or an app added to Customer (never one the record comes with, and never one
  the platform's own apps own — the phone and email the sheet already asks, a staff id, and the loyalty app's
  date of birth and anniversary, which award its special-day points: *"⟨field⟩ belongs to the till itself, so
  it can't be asked for."* A shop that must record a buyer's date of birth asks for its own Date field), of type Data, Select, Int or Date, that
  a person types (not read-only, not fetched, not virtual). An Int holds up to 2,147,483,647, so an ID
  number is a Data field. Up to **three**,
  counted apart from the three more Customer fields the card may show. The `label` is the shop's word for it;
  with none, the field's own label.
- **Required is a Save Rule, never a field rule.** To make the field required, add a Retail Save Rule of kind
  `required_when` on Customer ([`save_rules.md`](save_rules.md)). The till's create and edit then refuse a
  customer without it in the rule's words (*"ID number is required."*), so the cashier types it and saves
  again. After payment (the receipt's contact capture) and through the offline drain the customer is
  created and the *Sales to review* report lists it — never refused: the sale is paid.
- ⛔ **Not the Desk's Mandatory flag.** A field made Mandatory in Customize Form refuses every till create and
  edit in raw words, and a customer added offline then fails its sale when it drains. Use the Save Rule.
- **Only these fields:** the till's create and edit take the fields the theme asks for and refuse any other
  (*"Can't change ⟨field⟩ from the till."*); the drain drops any other, and a value the record refuses there
  (a Select choice that no longer exists) is left out, the customer created as before.
- **A field only some roles write** (above level 0): asked only of a cashier whose roles write its level,
  online. Offline the sheet never asks for it, and the drain never stores it. ⚠ Made required by a Save Rule
  too, it refuses every customer a cashier without that level adds or edits, with no box to type it in, and a
  customer added offline is created and listed for review. Put a required field at a level only when every
  cashier at those tills may write it.
- **Through the drain**, a customer the store already holds (found by phone and name) stays as stored, and
  the *Sales to review* list names the fields typed for them — never the values.
- **Offline:** the sheet asks for a level-0 field and the value rides the sale; the customer is created
  with it when the sale drains.
- ⚠ A **Select** left unanswered takes its first choice when the customer is created (the record's own
  default, as in iVendNext Desk). Give the field an empty first choice if "not answered" must stay possible.
- ⚠ A customer the phone finds already is attached as they are: what was typed is not written onto them,
  and the sheet says so (*"The other details typed here were not saved on them. Edit the customer to add
  them."*).
- ⚠ A **unique** Save Rule's own words name the value (*"ID number P1234567 is already on another
  Customer."*), and the *Sales to review* report keeps that sentence. On a personal field, give the rule its
  own message.
- An Int cleared at the till reads 0 afterwards (the column keeps a number).

## 8. Worked examples

**A shop that never takes emails, but always takes a phone.** Two rows: `customer_create · email · hide`
and `customer_create · phone · require`. The new-customer sheet has no email field, and adding a customer
without a phone at the till is refused with *"Phone is required here."* — by the server too, so an older
till cannot get round it. (A customer added in iVendNext Desk or through an import is not a till's, and is not
checked.)

**A pack size on every line.** Add a Data field `custom_pack_size` to Item, then `cart_line ·
custom_pack_size · show · Pack`. Each line reads *Pack: 12 × 500 ml* under the item, online and offline;
add `item_result · custom_pack_size · show · Pack` to show it in search too (still one of the three).

**A list price and a gross total.** `cart_line · list_price · show · List price` and `totals ·
grand_total · relabel · Total incl. VAT`. The counter grows a *List price* column; on the phone a
discounted line reads *List price ~~12.00~~ · 9.60*. A label *Total incl. 5% VAT* is refused: on a store
whose rate is not 5 % it would print a false number on every sale.

**The shop's own word.** `customer_card · points · relabel · Stars` (blank language) and a second row
with `Estrellas` for `es`: an English cashier sees *Stars*, a Spanish one *Estrellas*.

## 9. Telling an AI assistant

> Write field rules for an iVendNext POS theme, version 1, as JSON matching
> `fields.v1.schema.json#/$defs/declaration`; the samples under `samples/fields/` show accepted and
> refused themes. Use only the screens and fields this page's table lists, one action per screen and field,
> `require` only for a new customer's phone or email, labels of at most 40 characters, and `show` only for
> an Item or Customer field of type Data, Select, Int or Check — at most three of each. On
> `receipt_preview` use `show` only, with an Item field. Never a price, amount, tax or tender field. The
> money words take `relabel` only (`cart_line` `price` · `discount` · `amount`; `totals` `discount` ·
> `charges` · `delivery` · `tax` · `grand_total`), `list_price` takes `show` only, and a money label has no
> digit, no `%` and no currency sign (a site's letter sign such as *R* counts, in any case). Name only
> fields that exist.
