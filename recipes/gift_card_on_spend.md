# A gift card for a big spend, spendable after a hold — the recipe

A shop wants a sale over a set amount to earn the customer the shop's **own** gift card, which can be spent only after a hold (24 hours is common: the customer cannot buy, earn and spend in one visit). This recipe builds it as **an outside app that reads the event feed** and keeps every change of value in the shop's own gift card records. It is for an iVendNext developer who has made an outside app before ([chapter 5](../guide/05_outside_apps_and_event_feed.md)).

**Reference implementation:** `samples/s25_gift_on_spend/` — *Gift card on spend*.

**When to use it.** Any reward of stored value that the shop's own gift cards can carry: a card for a spend over a threshold, one per full threshold, held for a while before it spends. The card is **not on that sale's receipt**: it is made after the sale books. If the shop wants the card in the sale itself (a promotion that gives a gift card), that is the shop's promotion; today iVendNext POS shows such a reward as *earned, complete at the register* rather than issuing it.

## Steps

1. **Read the sales from the feed** ([recipe](event_feed.md)): the shop's feed registration follows **POS Invoice**; your service acts on `sale.booked`, `return.booked` and `sale.cancelled`, reads each sale over the API, and marks the event done. Every other event is marked done unread.
2. **Name each card before you make it.** Your manifest's own record type `<PREFIX> Card` is named by the sale and the card's position (`"autoname": "field:card_key"`, the key `S1:1`). Write it **first**, holding the card's number, value, item and hold. The shop refuses a second record with that name, so a replayed event or a crash never earns a second card.
3. **Make the shop's own gift card at a balance of 0.** Insert the engine's **Gift Card** with your number (16 digits, from a secure random source, never one the shop holds), the shop's gift card item, its total = the card's value, its balance = **0**. The till and the engine refuse a card with nothing on it, so nobody can spend it during the hold.
4. **Release it after the hold with a Gift Card Balance.** Submit the engine's **Gift Card Balance** for the card with its value: on submit it sets the card's balance and writes a comment on the card, and the shop's *Gift Card Ledger* report lists it. ⚠ It **sets** the balance; it does not add. Release only a card that has no submitted Gift Card Balance yet and a balance of exactly 0; anything else goes to the shop to decide.
5. **Read the sale again before every release.** Cancelled since? Returned below what earned this card? Then void it instead. Decide from the sale and every return booked against it **now**, never from the order the events arrived in: a failed event is retried after later ones.
6. **Void what a cancellation or return no longer earns.** A held card is simply never released. A released card still at its full value, and never used at the till (the till's own *redeemed* test, `/api/method/ivendnext_mpos.api.v1.get_gift_card_status`, from POS build 2.0.0.654; before it, `ivendnext_pos.api.pos_invoice.get_gift_card_status`), is set to 0 by a Gift Card Balance of 0. A card already used keeps its balance and goes to the shop to decide: never take back what a customer has spent.
7. **Refuse a gift card item that could turn into money.** A rechargeable card would let a void take money the customer paid in; a cash-back card pays the promotion out as cash; a store-credit card is the returns' own. Check the item's flags before you issue.
8. **Tell staff.** List each card under the customer and the sale (Connections links in the manifest). The kit has no way yet to send the number to the customer: an e-mail needs the product to give the framework's e-mail call an iVendNext name, and a message needs a gateway.

### Settings

One record of your own type `<PREFIX> Settings`, named `Default`, edited by the shop in Desk and read at every pass: enabled, the currency, the threshold, each card's value, the gift card item, the cards per sale, the hold in hours, and the walk-in customers and customer groups that never earn. From POS build 2.0.0.654 a manifest may declare a settings record of its own (`"issingle": 1`, one record with no list, [chapter 7](../guide/07_manifests.md)); S25 keeps a record named `Default` so that it installs on an older shop too.

### Earned gift cards

One record per card, listed under the customer and the sale: its state (*Issuing*, *Held*, *Released*, *Voided*, *Review*), its number and gift card, its value, the threshold and hold it was earned under, when it can be spent (the shop's time), the Gift Card Balance that released it and the one that set it to 0, and a note when the shop must decide.

## What the shop needs from you

- **The role's rights on the shop's own record types** (a manifest grants rights only on its own): read on POS Invoice, Customer and Item; read and create on Gift Card; read, create and submit on Gift Card Balance ([the integration user recipe](integration_user.md)). Say so in the card's setup steps, and say what they reach: the key can make a gift card and set the balance of **any** gift card in the shop.
- **The order of the setup:** switch the app on in its settings before ticking the feed (a sale booked while it is off earns nothing), and, for a hosted service, press *Connect again* once the integration user has its key and is chosen on the feed registration: that is when the site hands the key over. List the service's address in `allowed_urls`: the site connects only to ONE `*.ivendnext.app` address listed there (CitiXsys hosting); a service on your own domain is not connected by the site and takes the shop's key by hand.
- **A never-earn group is only as safe as the customer's group.** The till's edit sheet lets a cashier change it (the shop's cashier role saves customers): a staff customer moved into a group that earns takes a card. The shop closes it by putting *Customer Group* at permission level 1 in *Customize Form* and giving level-1 write only to its managers: the cashier's change then leaves the group as it was ([Customers by store](customers_by_store.md), rule 7). Put that in the setup, with what follows from it: a cashier can no longer choose a group for a new customer (it takes the store's default group), the till still says *Saved* after a group change it dropped, and no cashier's role may keep level-1 write (Sales Master Manager has it by default).
- **What each card costs them.** No sale credits the shop's gift card account when a card is issued, so when it is spent the gift card payment method's account is debited for value the shop gave away. They book it as a promotion.
- **What leaves the shop:** your service reads sales, returns, customers and the gift card item, and writes gift cards and their balances. Never write *nothing leaves your shop* on such an app's card.
- **The bounds:** the card is not on that sale's receipt; a return without the receipt names no sale, so it voids nothing; the hold runs from the card's issue.

## When your service is down, and when the till is offline

Nothing at the till waits for your service: the sale books as before. The feed keeps the events, so the cards are issued when your service is back, and the hold runs from then. A sale rung offline reaches the feed when the till syncs.

## Technical notes

- **Spend** in the sample: the sale's grand total, less its gift card lines (`transaction_mode` *Gift Certificate*, *Gift Certificate Recharge*, *Gift Certificate Cashback*), less what a gift card, store credit, a partner's wallet, loyalty points or the customer's account (*On Account*) paid, and less a tender discount (a write-off; the grand total keeps it); every other line keeps its own sign, so an exchange's *Item Return* line counts against it. A return (its lines are *Sale Return*) takes off what it refunded: its whole value, less its share of a tender discount. A layaway, order or quotation earns nothing (a sale's `transaction_mode` other than *Sale*).
- **Many shops:** /health counts a pass only when the shops store answered and no shop was stuck, so a hung service is restarted.
- **The hold's clock** is your service's own (UTC), written on the card when it is issued; the card also shows *spendable from* in the shop's time (its own creation time plus the hold).

### What was proven where

- **Laptop:** the sample's tests and canaries (`samples/s25_gift_on_spend/tests/`).
- **Our test bench** (the service in its one-shop form): sales rung at the till, a card refused at the till during its hold, released and spent at the till, cards voided by a cancellation and by the till's own return, and the uninstall leaving the schema as found.
