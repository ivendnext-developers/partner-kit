# S25 — Gift card on spend (a big sale earns the shop's own gift card, spendable after a hold)

## What the shop does

A customer's sale reaches the shop's threshold. Within the next half a minute the app gives them the shop's **own** gift card, of the value the shop chose, from the shop's own gift card item. The card can be spent once the hold has passed (24 hours by default), at the till, like any other gift card. Nothing changes at the till: the cashier rings the sale as before.

| What happens | When |
|---|---|
| A gift card is made, at a balance of **0**, and listed under the customer and the sale (*Gift cards*) as *Held* | a booked sale whose spend reaches the threshold, for a customer who may earn one |
| The card is raised to its value by a **Gift Card Balance** entry (`GC-BAL-…`) and listed as *Released* | the hold has passed |
| The till refuses the card: *"Insufficient balance: R 0.00 left."* (the bench's words, in its currency) | a customer tries it during the hold |
| A held card is never released; a released card never used at the till is set to 0 by a Gift Card Balance entry; both are listed as *Voided* | the sale is cancelled, or its returns take its spend below what earned the card (the last card first). The service reads the sale again just before each release, so this holds whichever event comes first |
| Nothing is taken from the card; it is listed as *Review* for the shop to decide | the card was already used at the till before that cancellation or return |
| Nothing | a sale under the threshold, a walk-in, a customer group the shop excludes, a sale in another currency, a layaway, an order or a quotation, or a gift card item that could turn into money (rechargeable, paid out as cash, store credit) or expires inside the hold |

**Spend** is what the customer paid for the sale, tax included, less any gift card sold, recharged or paid out on it, less anything paid on it with a gift card, store credit, a partner's wallet, loyalty points or on account, and less a tender discount, so stored value and credit never earn a gift card. An exchange earns on the net the customer paid. Each return takes off what it refunded (its whole value, less its share of a tender discount). **Cards per sale:** 1 gives one card per sale; a higher number gives one card for each full threshold, up to that number.

**What it costs the shop.** Each card is a promotion: no sale credits the shop's gift card account when the card is issued, so when it is spent the gift card payment method's account is debited for value the shop gave away. Book it as you book any promotion.

**How the customer learns the number.** Staff read it under the customer (or the sale) in Desk, *Gift cards*. Nothing sends it to the customer yet: an e-mail or a message is a later version (it needs the product to give the framework's e-mail call an iVendNext name, or a message gateway).

**Bounds, said plainly.**
- The card is not on the sale's receipt: it is issued after the sale books. A sale made offline earns its card when the till syncs.
- The hold runs from the moment the card is issued, by the service's clock; *Spendable from* on the card is about that time, in the shop's clock. A service that was down issues late and holds from then.
- A sale booked while the app is switched off earns nothing, even after it is switched on.
- A return **without the receipt** (an *Item Return*, which names no sale) cannot be matched to the sale that earned a card, so it voids nothing. A cancelled return gives no card back.
- A partial return counts at its whole value, even when part of the sale was paid with a gift card.
- A void reads the card, then sets it to 0: a customer spending it in that same second keeps what they spent, and the card is marked *Voided* (or *Review*, if the service restarted between the two writes; the card is at 0 either way).
- Run the service as one container: two running at once (an overlapping deploy) could each release the same card. On CitiXsys hosting the app is planned with its scratch folder, with which a deploy stops the old copy before the new one starts.
- Switching the app off stops **new** cards only: cards already held are still released after their hold. Release or void held cards before you uninstall: the uninstall removes the Card records, and a card still held stays at 0.

## What the shop does to set it up

⚠ **The shop's site needs iVendNext POS build 2.0.0.654 or later** (the void reads the card's status by a name that build added; see *Technical notes*).

1. Install `manifest.json` (the shop's administrator, on the install screen; on your sandbox, `tools/deploy/deploy.py`). It adds `PP GCS Settings`, `PP GCS Card`, the *Gift cards* links under Customer and POS Invoice, the feed registration *PP GCS Sales* (switched off) and the role **PP GCS Integration** (empty).
2. In **Role Permissions**, give PP GCS Integration **read** on POS Invoice, Customer and Item; **read and create** on Gift Card; **read, create and submit** on Gift Card Balance. A manifest can grant rights only on its own record types ([the integration user recipe](../../recipes/integration_user.md)). ⚠ With these rights the key can make a gift card and set the balance of **any** gift card in the shop, not only this app's: give the role to this app's user alone.
3. Make the app's integration user with that role and generate its API key.
4. Open **PP GCS Settings**, record `Default`: the currency, the threshold, each card's value, the gift card item (a gift card item that is not rechargeable, not paid out as cash and not store credit), the cards per sale, the hold in hours, and the walk-in customers and customer groups that never earn. Tick **Enabled** — before step 5, so no sale is booked while the app is off.

   **If your settings name customer groups that never earn, stop cashiers moving a customer out of one.** The till's edit sheet lets a cashier change a customer's group, and the shop's cashier role can save customers: a cashier could move a staff customer into a group that earns, and the sale would earn a card. In *Customize Form* for *Customer*, set **Customer Group**'s *Perm Level* to 1, and in *Role Permissions* give level 1 *Write* on Customer only to the roles that may move customers (your managers). A cashier's change then leaves the group as it was (measured with [S47](../s47_customers_by_store/) on the programme's bench, run `pp-20261023T115256Z-45139`). Two things follow: a cashier can no longer give a new customer a group either: a customer created at the till then has no group until a manager sets one (measured on the programme's bench, run `pp-20261023T160427Z-38473`, with a default group set and without), and the till still says *Saved* after a group change it dropped. Check the level 1 rows already there: Sales Master Manager has one by default, and no cashier's role may hold level 1 *Write*.

5. Choose the integration user on the feed registration *PP GCS Sales* and tick **POS Invoice**. For a hosted service, press **Connect again** on the app's package record now: the site hands the service the user's key only once the user has its key and is chosen here.
6. Run the service with the integration user's key (below). Staff see each card under the customer and the sale.

**What leaves the shop.** The shop calls nothing outside but the service's own address (`allowed_urls`: the hosted handshake, which carries the integration user's key). The service **reads** the shop with that key: each booked, returned or cancelled sale from the event feed, the sale itself, its returns, the customer's group and the gift card item. It **writes**: gift cards, gift card balances and the app's own Card records.

## Run it

```bash
python3 -m unittest discover -s samples/s25_gift_on_spend/tests -p 'test_*.py'
python3 samples/s25_gift_on_spend/tests/canaries.py
```

On a sandbox, with the integration user's key in `service/.env.local` (never committed: `PP_BASE`, `PP_KEY`, `PP_SECRET`, `PP_STATE`, `GCS_PREFIX=PP GCS`):

```bash
python3 samples/s25_gift_on_spend/service/worker.py run samples/s25_gift_on_spend/service/.env.local --watch 30
#   or the service with its /health beside the worker:
python3 samples/s25_gift_on_spend/service/app.py samples/s25_gift_on_spend/service/.env.local
```

Many shops (the app template's handshake, [chapter 14b](../../guide/14b_deploying_your_app.md#one-app-many-shops)): set `IVN_LIBRARY_APP` and a shops store; each shop's site connects itself to the app's one `*.ivendnext.app` address in `allowed_urls` after its install (the site connects to no other address, and refuses a manifest naming two) and hands over its integration user's key (once the shop has made it and pressed *Connect again*, step 5), and the worker reads each shop's feed with that shop's key, each on its own thread. It is background work, so it runs as a **container**, never a function:

```bash
docker build --platform linux/arm64 -f samples/s25_gift_on_spend/Dockerfile -t gift-card-on-spend:1.0.0 .
```

## Technical notes

- **Why a balance of 0.** The engine's Gift Card has an expiry but no *valid from*: its controller sets `expired` from the expiry date on every save, so a card cannot be held by marking it expired. The till's and the engine's own gift card checks refuse a card whose balance is 0 or less than the amount. So the card is issued at 0 and raised by the engine's own **Gift Card Balance**, which sets the balance on submit and writes a comment on the card; the *Gift Card Ledger* report lists it.
- **A Gift Card Balance sets the balance; it does not add.** A second one would put back what the customer has spent. So the release never submits one when the card already has a submitted Gift Card Balance or a balance other than 0 (*Review* instead), and a crash between the release and its record is finished, on the next pass, from the entry the shop already holds.
- **Never twice.** Each Card record is named by the sale and the card's position (`S1:1`): the shop refuses a second, so a replayed event or a crash never earns a second card. The record is written first, holding the card's number, value, item and hold; the gift card is made from it.
- **The card number** is 16 digits from `secrets` (a gift card number is a bearer credential), never one a gift card in the shop already holds.
- **Net spend, read now.** Every decision (issue, release, return) reads the sale and every return booked against it at that moment, never the order the events came in: a sale handled after its own return (a failed event retried) earns only what its net earns, and a release just before which the sale was cancelled voids instead.
- **POS build 2.0.0.654 or later** (since the kit's change of 2026-10-21): the void reads the card's status by its iVendNext name, which older builds do not have; on an older shop, set `CARD_STATUS` back to the engine's path below.
- **Used at the till** is the till's own test (`/api/method/ivendnext_mpos.api.v1.get_gift_card_status`, *redeemed*: a payment row names the card; the name exists from POS build 2.0.0.654, and before it the call is the engine's own path, `ivendnext_pos.api.pos_invoice.get_gift_card_status`); a void sets to 0 only a card at its full value that was never used.
- **Many shops and /health:** a pass counts only when the shops store answered and no shop was still stuck in an earlier pass; a shop is stuck when its pass has taken up no event and no release for 15 minutes (a slow shop catching up is not stuck); /health turns 503 after three minutes without a healthy pass and the platform restarts the service.

### What was proven where

- **The laptop tests** (`tests/`): the rules, the card's life against a stand-in shop that sets a card's balance on a submitted Gift Card Balance as the engine does, the worker, many shops and the manifest; `canaries.py` turns each rule off in turn and its test goes RED.
- **The test bench** (the programme's bench, against a real shop at the bench's pins, the service in its one-shop form): sales rung at the till, a card held at 0 and refused at the till, released after a short hold and spent at the till, a cancelled sale's cards never released, a sale returned through the till's own return voided, and the uninstall leaving the schema as found. The run's record is in the programme's evidence. The many-shops form (the handshake, the shops store) is proven by the laptop tests only.
