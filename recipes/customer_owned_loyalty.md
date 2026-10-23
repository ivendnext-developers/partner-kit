# A customer's own loyalty programme: the rules outside, the records inside — the recipe

Many retailers run their own loyalty programme: their own tiers, their own cash back, their own rules. This recipe puts such a programme on iVendNext **without any code inside the retailer's iVendNext**: your service holds the rules, iVendNext holds the records, and the till prices members on its own. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who would otherwise have built an app inside the customer's iVendNext.

**Reference implementation:** `samples/s22_customer_loyalty/` — tiers as customer groups, cash back earned from the event feed with a ledger iVendNext holds, returns and cancellations taken back exactly, tiers moved daily, a member key on the till, the cash back spent at the till as *Member cash* ([a partner wallet](wallet.md)), and a receipt checked before it books ([check by workflow](check_by_workflow.md)).

**When to use it.** The customer owns the rules and will keep changing them; staff must still see members and cash back on iVendNext's own screens, reports and audit; the till must price members offline. If iVendNext's own loyalty does the job, configure it instead (chapter 4).

## If you would have built an app inside the retailer's iVendNext, do this instead

| Inside the retailer's iVendNext, the old way | Here |
|---|---|
| Your own record types for members, plans and a ledger | the same record types, declared in your **manifest** (data, no code); your service writes them through the API |
| Code that runs when a customer is created or a sale is booked | your **service**, reading the **event feed** (`customer.created`, `sale.booked`, `return.booked`, `sale.cancelled`) |
| A member discount worked out in the till's browser | **a tier is a customer group** with its own **promotion** (configuration); your service moves the customer between groups |
| Scheduled jobs inside the retailer's iVendNext (credit, upgrade, expiry) | your service's own scheduler |
| A balance panel added to the till's screen | a **remote till key**: your service answers with a message |
| A check that blocks a back-office document at submit | **check by workflow**: a *Verified* step only your service can take |
| A rule checked when a record is saved (a format, a limit) | a **save rule** in your manifest (chapter 7) |
| A rule checked before the customer pays | a **check before payment** ([recipe](rule_guard.md)) |
| A unit's own barcode recognised at the scan | a **scan source** over your record type ([recipe](unit_codes.md)) |
| A button on a Desk form that runs your logic | a **Desk action** ([recipe](desk_action.md)) |
| Workflows, notifications and numbering on the retailer's own documents | **configuration** over the API, with an undo (sample S5's shape) |
| A patch or override of the product | never: request an extension point (chapter 9) |
| Paying with the cash back at the till | the **wallet extension point**: your service answers the till ([a partner wallet at the till](wallet.md)) |

## Steps

1. **Declare the records** in your manifest: settings, plans, members and the ledger, each with its permission rows written out (`recipes/manifest.md`). Give the ledger a **unique key** field and name each row by it (`"autoname": "field:source_key"`): the document and the event, such as `POS Invoice:<sale>:earn`. Declare the feed registration (the record types you follow) and the member key; both install **switched off**.

2. **Make the one integration user** before install (`recipes/integration_user.md`): one desk user, one licence, one narrow role **of this app's own** (S22's is *PP LYL Integration*: a role another app's user also holds would hand that user your *Verify* step), holding only what your service reads and writes, never Workspace Manager. The sample's `apply_config.py prepare` does it and writes each right with its reason. Over the API the user needs `custom_is_desk_user: 1` (the screen's *Is Desk User*), and reading a record type also needs read on the records it names.

3. **Configure the tiers.** One customer group per tier; one promotion per tier, limited to that group by **excluding every other group**. Build the exclusions after every group exists, and rebuild them whenever a group is added, or a new group gets every discount (sample S5's rule). Set the plans and settings records. **Then tell iVendNext to lock the tiers.** A tier is the customer's group, and the till's edit sheet lets a cashier change it (the retailer's cashier role saves customers): a member moved into a higher tier takes its discount. The retailer closes it by putting *Customer Group* at permission level 1 in *Customize Form* and giving level-1 read and write only to its managers **and your integration role** (your service reads and moves the tier groups, and a writer without level-1 write has its change dropped the same quiet way): the cashier's change then leaves the group as it was ([Customers by store](customers_by_store.md), rule 7). Put that in the setup, with what follows from it: a cashier can no longer choose a group for a new customer (it takes the store's default group), the till still says *Saved* after a group change it dropped, and no cashier's role may keep level-1 write (Sales Master Manager has it by default).

4. **Switch it on** (the retailer's administrator): the feed registration's user is your integration user, **and each record type it follows ticked on** (iVendNext writes a feed row only for a ticked one; the installer leaves them unticked); the member key's consent; the key on the store's till theme (POS Studio → Apps). A till whose profile wears no theme offers no key.

5. **Read the feed.** Pull your events, act on the labels you need, mark the rest done. Write every ledger row **named by its key**: when iVendNext answers *409* (the name is taken), the event was already handled — treat it as done. Your own note of handled events is only a cache in front of that.

6. **Get the money right**, in one place: `Decimal`, rounded half-up to the currency's decimals. Earn on what the customer bought: the sale's total less any gift card sold on it, which earns when it is spent, and less the goods' share of a tender discount. Keep the sale's value without its gift cards on the earning row: the tiers count it, and each return is measured against it. A return takes back its share of what the sale earned, never more than is left; the return that completes the sale takes exactly what is left. While the earning is still *Pending*, reduce it; after it is *Credited*, write a negative row. A cancelled sale takes back the rest.

7. **Run the daily jobs:** credit what the return window has closed on; move each member to the tier the year's spend reaches, by moving their customer group.

   **A balance report with opening and closing figures** is one more daily job. Your service writes one balance row per member per day for the day that ended (S22's `PP LYL Balance`, named `balance:<customer>:<day>`):
   - the **opening** is that member's last row's closing;
   - the **closing** is what the member can spend now;
   - the **change** is the difference.

   A Report Builder report over the rows (S22's *PP LYL Member cash by day*), filtered by date, reads the opening of the first day and the closing of the last. S22's `loyalty.daily_balances`, two tests; a second run of the day writes nothing. **The limit:** the closing is taken when the job runs (the first pass after 02:00 UTC), so a move between midnight and the run counts in the day that ended. A day the job did not run has no row: the next row's opening still follows from the last closing.

8. **Answer the member key:** the plan, the balance (and what is pending), and how much more reaches the next tier. Verify iVendNext's signature over the raw body first (sample S18's `verify`).

## What iVendNext needs from you, and what it checks

- The manifest passes `tools/manifest/validate.py`; the retailer's administrator installs it from the install screen (`recipes/manifest.md` step 4).
- The integration user holds one role; each right has a reason; `apply_config.py diff` shows every permission table against its state before.
- `apply_config.py remove` puts every permission row back first, then removes what it made.

## When your service is down, and when the till is offline

- **Down:** your events wait in the feed, undone, until you come back; nothing is lost. The member key reads *"⟨label⟩ could not finish"* and the sale goes on.
- **Offline till:** member prices still apply (they are promotions); a tier change made while a till is offline reaches it at its next start. The member key is not offered offline.

## Technical notes

### Bounds

- Cash back and tier changes arrive **seconds after** the sale books, not inside it.
- Combined discounts follow the promotion rules; multiplying a member discount with other offers needs an extension point.
- Spending the cash back at the till is the wallet extension point ([a partner wallet at the till](wallet.md)); S22's *Member cash* has run only in its laptop tests.

### What was proven where

- **Laptop:** the sample's 70 tests and 47 canaries against an in-memory stand-in for iVendNext (money, replay after a crash, permissions, the receipt check, the member key, Member cash, many retailers).
- **Test bench** (2026-10-09, before Member cash was added): the sample on a site in the sandbox's shape, and a fuller customer build on a second site, each through our installer, the configuration over the API and the service on the real event feed. Proven there: enrolment and tiers by customer group (a walk-in pays no member discount; each tier its own rate only), earnings of 2% in `Decimal`, partial returns taking their exact share (netted while pending, a negative row after the credit), the service killed between iVendNext's write and its own note and replayed (one row), every event delivered again (nothing changes), the member key on the till, and check by workflow.
