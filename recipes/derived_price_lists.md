# A price list worked out from another, kept in step — the recipe

A retailer wants one price list to follow another: the selling list is one and a half times the buying list, or the wholesale list is nine tenths of the retail list, and when the source price changes the derived price changes by itself. iVendNext's price list has no formula, and a selling pricing rule is the wrong tool (it is a promotion, chapter 4). This recipe builds it as **an outside app on the event feed** that writes the derived list's item prices. It is for an iVendNext developer who has made an outside app before ([chapter 5](../guide/05_outside_apps_and_event_feed.md)).

**Reference implementation:** `samples/s26_derived_prices/` — *Derived price lists*.

**When to use it.** A list that is a fixed multiple of another, plus an optional amount, rounded the way the retailer prices. Not for a price that depends on the customer, the quantity or the day: those are promotions and pricing rules.

## Steps

1. **Keep the formula in the retailer's iVendNext.** Your manifest's own record type holds one rule per derived list (below). The retailer edits it in Desk; your service reads every rule at each pass.
2. **Follow Item Price on the feed** ([recipe](event_feed.md)). iVendNext's feed registration follows **Item Price**. One saved price writes several events (`item_price.after_insert`, `.on_update`, `.on_change`): read the row again for each, which is cheap, and write only when the target is wrong.
3. **Work the price out in decimal arithmetic.** `rate = round(source × factor + offset)` to the rule's step (0.01, 0.05, 0.5 or 1) in its direction (nearest, half up; up; down), then never below the floor, at the rule's decimal places (the retailer's currency precision: iVendNext sizes every price from that system-wide setting, which your service's user may not read, so the rule carries it). Never in binary floating point: 66.67 × 1.5 is 100.005, which is 100.01, and a float rounds it to 100.00.
4. **Stamp what you write.** The target row your service makes carries `PP-DPL ⟨rule⟩ ⟨source row⟩` in its *note*. Find the row by that stamp before every write: a replayed event updates the same row, and an unchanged price is not written at all.
5. **Never overwrite a person's price.** A row on the target list that is still selling and lacks your rule's stamp is a person's price (or another rule's), and so is a stamped row that someone other than your service changed last (its *modified by*). Leave both as they are and list them. Find your own row by its stamp alone, so that when someone corrects the source's item or unit your row moves with it.
6. **Carry a change down a chain yourself.** Your own writes make no event for you (the feed's contract), so after writing list B, apply the rules whose source is B. Refuse a rule that would close a loop, and two rules writing one list.
7. **A deleted source price ends its rows; it never deletes them.** A source price made for one customer, supplier or batch is no longer a source either. The feed sends `item_price.deleted` (read on a sandbox, 2026-10-16). Give each row made from that source an end date of yesterday (*valid upto*), moving its *valid from* back when it is later, and carry the end date down the chain.
8. **Work every price out again when a rule is new, changed, or back from being switched off.** Keep a fingerprint of each rule's numbers, and forget it while the rule is off; when it changes, page through the source list, saving the page cursor after each page, so a crash resumes where it stopped.
9. **Reconcile every night, read-only.** Every target price against its source: a missing price, a wrong price, a row whose source is gone and still sells, and every person's price listed apart. It never changes anything: a difference in price is a person's decision.

### The rule

One record per derived list, of your own type `⟨PREFIX⟩ Rule`, named by a short name (it is written in each price's note): enabled · the source price list · the target price list · the factor · an amount added after it (may be below 0) · round to (0.01, 0.05, 0.5, 1) · rounding (nearest, up, down) · never below · decimal places (the retailer's currency precision, 2 by default). The service refuses, and reports, a rule whose lists are in two currencies, whose step or floor is finer than its decimal places, or whose target another rule writes.

## What iVendNext needs from you

- **The role's rights on the retailer's own record types** (a manifest grants rights only on its own): read on Price List; read, create and write on Item Price ([the integration user recipe](integration_user.md)). Say what they reach: the key can change **any** item price in the retailer's iVendNext.
- **The app's own user on the feed registration** (from POS version 2.1.0.667 the install makes it, `<app>@integration.invalid`, and names it; the retailer ticks Item Price and gives its role the rights above). A key registered to two applications is refused.
- **The rule filled in and enabled**, after the service runs: its first pass writes every target price no person has set. A target list that already has prices keeps them (each is a person's price): to hand a list to the rule, end those prices first, or derive into a new list.

## Bounds — tell the customer

- **Seconds, not instantly.** The new price arrives seconds after the source is saved (14 seconds on a sandbox, polling every 5; about a minute at worst when the retailer's background worker is busy, chapter 5). A sale in those seconds is priced at the old price; a price is never changed after the cashier has seen it.
- **Tills take it at their next sync.** An offline till sells at the list it holds.
- **Only the item price rows.** A promotion or a member discount still applies on top, as always.
- **Prices for everyone only.** A price for one customer, one supplier or one batch is not derived.
- **One copy of the service per retailer.** Two running at once can both write a new row before either sees the other's.
- **A person's price is kept.** It is never silently replaced; the nightly report lists it, and the retailer decides.
- **The decimal places are the rule's.** Set them to the retailer's currency precision.
- **The floor wins over the step.** A floor of 4.99 with a step of 1 gives 4.99 when the worked-out price is lower.
- **Switching a rule off, changing its target list, or uninstalling the app stops the following.** The prices it made stay at their last value, no longer followed or checked: end them, or hand the list to a person, at the same time.
- **The end date is the service's day.** A deleted source ends its rows from yesterday by the service's clock.

## Tell the customer

Before you build, agree in writing: the formula (factor and amount), the rounding step and direction, the floor, and who may overwrite a derived price by hand (a person's price is kept until they remove it).

## Technical notes

- Proven on a sandbox site (2026-10-16, POS 2.0.0.648, `samples/s26_derived_prices/README.md`): install, a 1.5× rule, a source change followed in 14.2 seconds, the retailer's own pricer (`ivendnext_mpos.api.v1.get_item_details`, its `args` sent as JSON text) returning the new price, a repeated event writing nothing, both kinds of person's price held, a deleted source ending its row in 15.3 seconds, the nightly reconcile reading 0, and the uninstall leaving the site as found. A second run after the review (manifest 0.1.1): a change in 12.6 seconds, an ended person's price not blocking, a source moved to another item moving its made row, reconcile 0.
- The service learns its own user once a pass (`ivendnext_mpos.api.v1.get_logged_user`); everything else is the record API (`/api/resource/…`).
