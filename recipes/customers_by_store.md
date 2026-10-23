# Customers by store: at which stores each customer group may buy — the recipe

A till puts any customer on any store's sale. Shops ask for less: **account customers buy only at the store that holds their account**, **a trade group buys only at the trade counters**, **staff buy only at the staff shop**. This recipe adds that from outside, through the capture on customer select: the shop writes one rule per customer group in Desk, and your service answers each pick of a customer with *on the sale* or *off it, and why*. The shop's server then holds every door that takes payment until your service has let that customer on. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** `samples/s47_customers_by_store/` — *Customers by store*.

**When to use it.** Who the customer is decides where they may buy. A rule about the till alone (this till sells to trade only) still needs a customer to judge, so it is this recipe too: the place is the till's POS Profile.

## What the cashier sees

- A customer the rule lets buy here: on the sale, nothing shown.
- A customer it does not: *"This customer can't be on this sale"*, your sentence and *"Sell without a customer, or pick another one."*, then back to the basket without the customer.
- A customer put on a sale without a pick (an answer lost, a sale picked up hours later): at payment, *"This customer has not been checked. Pick them again, or sell without a customer."*
- The store's walk-in customer: never asked.

![At Store 3 on a demo shop: a customer whose group buys at Store 1 only, taken off the sale with the rule's words](../samples/s47_customers_by_store/screenshots/04_refused.png)

![A customer in a group below one whose rule names Store 3 stays on the sale](../samples/s47_customers_by_store/screenshots/05_allowed.png)

## Rules

1. **Declare the rule record and the capture in your manifest** (`samples/s47_customers_by_store/manifest.json`):
   - a record type `<PREFIX> Rule`, one record per customer group, named by it (`"autoname": "field:customer_group"`, a **Link** to *Customer Group*, unique): *Switched on*, the places (a **Table** of `<PREFIX> Rule Place`, not required: Desk drops a row left blank, so a rule with no row is how a shop stops a group; each row a **Link** to *Warehouse* named *Store*, never a warehouse group, and a **Link** to *POS Profile*, neither required) and the cashier's words (a **Data** field of at most 120 characters). Give **System Manager** the rights to edit it and your integration role **read only**; name the role `<PREFIX> Integration`, so the install makes it;
   - one `capture` subscription with `"settings": {"event": "customer_select"}` at your service's address, and that address alone in `allowed_urls`;
   - a feed registration naming your one integration user (its description at most 140 characters, which the shop's install holds), so the shop's *Connect again* hands that user's key to your service;
   - a help address on the rule record type (a `documentation` property setter).

2. **Choose what happens when your service is down.** Customers by store declares `allow_and_flag`: an outage never stops a shop selling, the customer stays on and the sale is flagged on *Sales to review*. A shop that must never sell to a customer outside their stores changes its subscription to `refuse`, after *Connect again* has sent your user's key; every pick of a customer then waits on your service. A key withdrawn or a user disabled (401 or 403) is the shop unreadable too: log it apart from an outage.

3. **Check every call with the capture's secret** (`<app>:sub:<key>`; the sample's key is `on_select`), and refuse a timestamp more than five minutes from yours.

4. **Read the shop's rules and its group tree at the same time,** with your integration user's key, and keep them a minute (a rule changed, or a group made, reaches you within that minute): `GET /api/resource/<PREFIX> Rule` with `fields` `["name","customer_group","words","places.store","places.pos_profile"]` (the shop answers one row per place), `filters` `[["enabled","=",1]]` and `limit_page_length` 0; and `GET /api/resource/Customer Group` with `["name","lft","rgt"]`. Each read has its own timeout, so two in a row could outrun the select's 3 seconds. The shop gives your role a plain **read on Customer Group**; the rule records are the role's own. If either read fails, answer 503 (the down answer applies), never a decision on half the rules. You never need the customer record: the call carries `customer.customer_group`, read by the shop's server from the record.

5. **Find the rule that decides.** The customer's own group's rule; else the nearest group above it with a rule: the groups whose span holds the group's (`lft` below and `rgt` above), the innermost first. No rule up the tree: allow. One rule decides, whole: a group's own rule replaces the rules above it, so say so to the shop.

6. **Match the place on each side it fills.** A row with a store alone names every till at that store (`context.store`, the till's POS Profile's own warehouse); a row with a POS Profile alone names its tills (`context.pos_profile`); a row with both matches only when that POS Profile's store is that store. Any row that names this till: `{"verdict":"allow"}`. None: `{"verdict":"refuse","reason":"…"}`, a plain reason of 1 to 140 characters. A rule with no place names nowhere: refuse, never allow. A customer whose group your kept tree does not know, while the shop has rules, answers 503 and drops what you kept, so the next pick reads the shop again (a group made within the minute, or a tree read cut short): never an allow past a rule further up.

7. **Tell the shop to lock the customer's group.** Your rule trusts the group the customer record holds, and the till's edit sheet lets a cashier change it (the shop's cashier role saves customers). The shop closes it by putting *Customer Group* at permission level 1 in *Customize Form* and giving level-1 write only to its managers: the cashier's change then leaves the group as it was. Put that in the setup, with what follows from it: a cashier can no longer give a new customer a group (one created at the till takes the default customer group in Selling Settings, or none), the till still says *Saved* after a group change it dropped, and no cashier's role may keep level-1 write (Sales Master Manager has it by default).

8. **Tell the shop to switch it on for every till.** The capture asks only at the POS Profiles its subscription answers: with none chosen, every one. A POS Profile left off a list never asks, and every customer buys there.

9. **Say what the pass covers.** The shop's server records your *allow* for the cashier, the customer and the POS Profile, for twelve hours or until a booking uses it; your *refuse* withdraws an earlier one. A POS Profile has one store, so the pass never carries to another store (unless the shop changes the POS Profile's store within those twelve hours).

## Bounds

- The till's own doors: a sales order or invoice made in iVendNext Desk is not asked. A document check (`recipes/document_check.md`) can hold those.
- What the customer already holds is not a new pick and is not held: a layaway plan's later payment and its settlement, an order's balance, a payment on their account.
- While any customer-add app is switched on for a POS Profile, a customer the cashier added in the last ten minutes goes on the sale without your service being asked, whatever group the cashier gave them.
- One cashier sends at most 60 select rounds in ten minutes.
- One app answers each capture event on a POS Profile: this one takes *customer select* there.
- Offline, the till does not call your service: the down answer applies, and a sale paid offline books when it syncs and is flagged.
- One rule per customer group; a customer's own rule is a group of their own.

## See also

- [A value captured at the scan, and a code before a new customer](capture.md): the capture's events, its answers and its code check.
- [Payment method rules](payment_method_rules.md): the same rule records and group tree, at Pay.
- The capture's page, `contracts/pages/partner_capture.md`: the select's context, the pass and the down answers.
