# The retailer's own fields on the till (field rules) — the recipe

![Field rules: the line reads Product, the card says Stars, no email, a phone is required](../samples/s21_field_rules/screenshots/s21_flow.gif)

Field rules give a retailer its own say over the fields the till shows, per till theme, with no code: **hide** a field nobody uses, **relabel** it in the retailer's own word, **require** a phone or an email on a new customer, or **show** up to three more Item fields and three more Customer fields. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, shipping them in a manifest.

**Reference implementation:** `samples/s21_field_rules/` — the sale's line reads *Product*, the customer's card says *Stars*, the new-customer sheet has no email, and a new customer needs a phone.

**When to use it.** It is step 1 of the screen ladder — configuration. Reach for it before any screen of your own. A retailer's manager can do the same in POS Studio's **Fields** tab; a manifest is for an iVendNext Partner who ships the same rules to many retailers.

**The four rules, here.** Nothing is called and nothing leaves the retailer's iVendNext. A rule changes what the till **shows and asks for**, never what it charges: from POS build 2.0.0.654 a money column may be shown or called by the retailer's word (step 3b), and no rule moves, rounds, hides or replaces a figure.

## Steps

1. **Declare the rules in your manifest**, each naming the retailer's till theme:

   ```json
   "field_rules": [
     {"theme": "PP Partner Till", "surface": "cart_line", "field": "item_name", "action": "relabel", "label": "Product"},
     {"theme": "PP Partner Till", "surface": "customer_card", "field": "points", "action": "relabel", "label": "Stars"},
     {"theme": "PP Partner Till", "surface": "customer_create", "field": "email", "action": "hide"},
     {"theme": "PP Partner Till", "surface": "customer_create", "field": "phone", "action": "require"}]
   ```

   The screens and what each takes: `customer_create` (hide phone, email, more details; relabel name, phone, email; require phone, email), `customer_card` (hide or relabel member since, lifetime, visits, points; hide phone; show Customer fields), `cart_line` (relabel item name, quantity; show Item fields), `item_result` (hide or relabel the item code; show Item fields), `sale_details` (hide or relabel an optional sale detail). One action per screen and field; a label is at most 40 characters.

2. **They are live at install.** Field rules have **no switch**: a *require* rule is enforced by the server as soon as the manifest installs, and the others reach each till that wears the theme at its next start. Tell iVendNext before you install.

3. **What the cashier sees.** The till's start reads the rules with its theme; each screen asks them as it draws, online and offline. A new customer without a required phone is refused by the till **and by the server**: *"Phone is required here."* — an older till cannot get round it. A customer added offline without it is created when the sale syncs and flagged on the *Sales to review* report, never refused (the customer has paid). (A customer made in iVendNext Desk or by an import is not a till's, and is not checked.)

   On the till: the line heading ![Product](../samples/s21_field_rules/screenshots/01_the_line_heading_reads_product.png), the card ![Stars](../samples/s21_field_rules/screenshots/02_stars_on_the_customers_card.png), the new-customer sheet ![no email](../samples/s21_field_rules/screenshots/03_new_customer_without_an_email_field.png), and the phone rule ![phone required](../samples/s21_field_rules/screenshots/04_phone_is_required_here.png). On the phone: the heading ![phone: Product](../samples/s21_field_rules/screenshots/05_phone_the_line_heading_reads_product.png) and the phone rule ![phone: phone required](../samples/s21_field_rules/screenshots/06_phone_phone_is_required_here.png).

3b. **The money words** (POS build 2.0.0.654 on). Two rows show a line's price before any cut and give the total the retailer's word:

   ```json
   {"theme": "PP Partner Till", "surface": "cart_line", "field": "list_price", "action": "show", "label": "List price"},
   {"theme": "PP Partner Till", "surface": "totals", "field": "grand_total", "action": "relabel", "label": "Total incl. VAT"}
   ```

   - `cart_line`: `price`, `discount` and `amount` take `relabel` only; `list_price` takes `show` only. The counter grows a *List price* column; on the phone and the tablet it leads each line's sub-line, struck through only when the charged price is below it.
   - `totals`: `discount`, `charges`, `delivery`, `tax` and `grand_total` take `relabel` only. `hide` is refused on every money figure.
   - **Tell iVendNext:** the paper keeps its own words (*Total*, *Tax (incl.)*), so a retailer that wants its word on the receipt names its own print format. A label may not hold digits or signs, but a claim in words passes: *Price incl. VAT* is false on a profile whose prices exclude tax, so word a money label for every POS profile the theme serves. A line sold at a cross-sell offer's price shows no struck price. The customer display, POS Studio's previews, the screens of a sale already made and the charges sheet's heading keep the shipped words.
   - They joined version 1 at POS build 2.0.0.654: an older build's lists do not hold them, so check iVendNext's build before you ship them. The rules page: [`contracts/pages/fields.md`](../contracts/pages/fields.md), *The money words*.

4. **Uninstalling** removes exactly your rows and leaves the theme as the retailer had it, even if the retailer renamed the theme meanwhile.

5. **Test it.** The manifest passes the kit's checker, which refuses in the product's own words what the product would (a field a screen does not take, a label over 40 characters, two rules for one field) — `samples/s21_field_rules/tests/`. Then start a till on a sandbox.

## Technical notes

### What was proven where

- **Screenshots** (our test bench, 2026-10-10, the iVendNext POS app `87812e141`, the kit's demo site *Demo Retail*; frames: the till's counter frame, 1440 wide, light mode, and the phone frame, a 390 × 844 phone viewport): the bench's theme `PP Partner Till`, the rules installed, the till started afresh. A real browser drove the till; the checks below drove its calls.

Proven on our test bench on 2026-10-08 (iVendNext POS app at `577a8d41`), **6 of 6** checks:

- Install: the four rows on the named theme.
- The till's start (`pos_fields.rules_for_boot` over the till's own POS Profile) reads all four.
- A new customer without a phone, through the till's own create as the cashier: refused at once by the server — *"Phone is required here."*; with a phone, created.
- Uninstall: exactly these rows removed; the theme's rows as before and the till's profile wearing what it wore.

Not run here: how each screen draws the rules (a browser walk), a rule in a cashier's own language, `show`, a theme renamed before uninstall (proved on a test site on 2026-10-08). Field rules change no booked value, so there is no money-kit label.
