# A customer's own loyalty programme: the rules outside, the records inside — the recipe

Many retailers run their own loyalty programme: their own tiers, their own cash back, their own rules. This recipe puts such a programme on iVendNext **without any code inside the retailer's iVendNext**: your service holds the rules, iVendNext holds the records, and the till prices members on its own. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who would otherwise have built an app inside the customer's iVendNext.

**Reference implementation:** `samples/s22_customer_loyalty/` — tiers as customer groups, cash back earned from the event feed with a ledger iVendNext holds, returns and cancellations taken back exactly, tiers moved daily, a member key on the till, the cash back spent at the till as *Member cash* ([a partner wallet](wallet.md)), and a receipt checked before it books ([check by workflow](check_by_workflow.md)).

**When to use it.** The customer owns the rules and will keep changing them; staff must still see members and cash back on iVendNext's own screens, reports and audit; the till must price members offline. If iVendNext's own loyalty does the job, configure it instead (chapter 4).

**How the data travels, hop by hop:** [guide chapter 1c](../guide/01c_how_the_data_travels.md), example 1, follows this recipe's sample from the till to the chain's own loyalty system and back (S22's opt-in adapter), with two chains in the same second.

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

1. **Declare the records** in your manifest: settings, plans, members and the ledger, each with its permission rows written out (`recipes/manifest.md`). Give the ledger a **unique key** field and name each row by it (`"autoname": "field:source_key"`): the document and the event, such as `POS Invoice:<sale>:earn`. Declare the feed registration (the record types you follow) and the member key; both are on from the install.

2. **Name the app's role's rights in the manifest.** From POS version 2.1.0.667 the install makes the one integration user for the feed, `<app>@integration.invalid` (S22's is `pp_lyl@integration.invalid`), holding one narrow role **of this app's own** (*PP LYL Integration*: a role another app's user also holds would hand that user your *Verify* step), and never Workspace Manager. **The install gives the role read on every record type the feed follows** (S22 follows Customer, POS Invoice and Purchase Receipt), so the retailer's administrator grants none. A right beyond those is a `role_rights` entry in the manifest, each for a reason: S22's are write on Customer (enrol a customer into a tier), and read on Purchase Order and Supplier (the receipt check reads what an order waits for and the supplier a receipt names). The tiers' customer groups and plans and the programme's default settings are `records`, made by the install; what differs per retailer stays in `config.json`. The sample's `apply_config.py prepare` runs after the install and makes no user: it grants only what a receipt check, a customer's choice, needs. **This needs POS build `2.1.0.691` or later** (an earlier site skips `role_rights` and `records` and gives the feed's user no read).

3. **Configure the tiers.** One customer group per tier; one promotion per tier, limited to that group by **excluding every other group**. Build the exclusions after every group exists, and rebuild them whenever a group is added, or a new group gets every discount (sample S5's rule). Set the plans and settings records.

4. **Check the till key** (the retailer's administrator): the install puts the member key on every store's till; a till whose profile wears no theme (POS Studio → Apps) offers no key, so give it one.

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
