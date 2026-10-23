# S22 — Customer-owned loyalty (`pp_lyl`): your logic outside, the records inside the shop

A retailer that runs its **own** loyalty programme — its own tiers, its own cash back, its own rules — and wants it on iVendNext without putting any code inside the shop. This sample is for a developer, or the CitiXsys Consulting Team, who would otherwise have built an app inside the customer's iVendNext for it.

**When to use it:** the customer owns the rules (you write them in your own service), but staff should see the members, tiers and cash back on iVendNext's own screens, and the till should show a member's status.

The recipe: [`recipes/customer_owned_loyalty.md`](../../recipes/customer_owned_loyalty.md). The receipt check in it: [`recipes/check_by_workflow.md`](../../recipes/check_by_workflow.md).

## What happens

1. A new customer is created at the till. Seconds later your service reads it from the shop's **event feed**, records the member (`PP LYL Member`) and puts the customer in the **Bronze** customer group.
2. **A tier is a customer group.** Each tier's discount is an ordinary promotion for that group, which excludes every other group. So the till prices a member's sale on its own, online or offline, and a walk-in gets no member discount.
3. A sale books. Your service reads it from the feed and writes the cash back to the **ledger** (`PP LYL Ledger`): *Pending* until the return window closes, then *Credited* by a daily job. The cash back is earned on what the customer bought: the sale's total, less any gift card sold on it and less a discount for paying a certain way (a tender discount). A gift card earns when it is spent, not when it is sold. How the sale was paid does not matter, except Member cash (below).
4. A return takes back its share of what that sale earned; a cancelled sale takes back the rest, and takes out of the year's spend only what a return has not already taken out. Never more than was earned.
5. Each day your service moves a member to the tier the year's spend reaches, by moving their customer group.
6. The cashier presses the **Member** till key: your service answers with the plan, the cash-back balance and how much more reaches the next tier.
7. A goods receipt is booked only after your service has checked it (**check by workflow**): its workflow has a *Verified* step only your service can take; a stock manager can *Override*.
8. **Member cash:** a member pays with their cash back at the till. The till shows *Member cash* beside the other payments, asks your service what this member may spend on this sale, and takes it. A return pays it back first. Every payment, refund and reversal is a ledger row named by its reference ([below](#member-cash-spending-the-cash-back-at-the-till)).

Every record is in the shop: staff open members and the ledger in Desk, see them under the Customer (Connections, *Loyalty*), and run the *PP LYL Cash Back* report. Nothing runs inside the shop.

**New, and not yet run on a till:** Member cash (step 8) is adapted from CitiXsys's private reference implementation, which was walked on a sandbox till; this sample's own copy has run only in the laptop tests ([what was proven where](#what-was-proven-where)). The recipe: [A partner wallet at the till](../../recipes/wallet.md).

## What the shop does

1. **Decide the programme with the partner.** Each tier is a plan record (`PP LYL Plan`): its name, its rank, the spend that reaches it, the member discount and the cash back it earns. The programme's rules are one settings record (`PP LYL Settings`): the plan a new customer joins, the return window in days, the days of spend counted for a tier, the currency and its decimal places, the walk-in customers who are never enrolled, and, for Member cash, the payment method, the most of a sale it may pay and whether a sale paid with it earns cash back. The sample's own values are three tiers (Bronze, Silver from 1,000, Gold from 2,500) at 0, 3 and 5% discount and 2% cash back, a 14-day return window and 365 days of spend; they live in `config.json`.
2. **Make the one integration user** (the shop's administrator, or CitiXsys Consulting with the administrator's key). The setup step `prepare`, run before the install, makes one user that holds only the app's own role **PP LYL Integration**, with each right it needs and the reason beside it. If the role is still missing when the app is installed, the install adds it. Then generate the user's API key in Desk (**User > Generate Keys**) and hand it to the partner's service. Never give this role to another app's user: that user could then take the receipt's *Verify* step.
3. **Install the app** (the shop's administrator, from the install screen). It adds `PP LYL Settings`, `PP LYL Plan`, `PP LYL Member` and `PP LYL Ledger`, two Connections links on Customer, the report *PP LYL Cash Back*, the feed registration *PP LYL Loyalty* and the till key *Member*. The feed registration and the till key come in switched off.
4. **Apply the configuration** (the administrator: `apply_config.py apply`). It makes a customer group and a promotion for each tier (each promotion excludes every other group), writes the plans and settings, and sets up the receipt check: a clerk sends a goods receipt for verification, the service takes its *Verify* step, and a Stock Manager can *Override*. The submit right on goods receipts is taken from every role but the Stock Manager's and the service's, so a clerk cannot book a receipt unchecked. Afterwards a System Manager can read and edit the plans and settings in Desk.

   **Then stop cashiers moving a member between tiers.** A tier is a customer group, the till's edit sheet lets a cashier change a customer's group, and the shop's cashier role can save customers: a cashier could move a Bronze member into Gold, and the till would give Gold's discount. In *Customize Form* for *Customer*, set **Customer Group**'s *Perm Level* to 1, and in *Role Permissions* give level 1 *Read* and *Write* on Customer only to the roles that may move customers (your managers) and to **PP LYL Integration**: the service reads and moves members' groups, and a writer without level 1 *Write* has its group change dropped the same quiet way. A cashier's change then leaves the group as it was (measured with [S47](../s47_customers_by_store/) on the programme's bench, run `pp-20261023T115256Z-45139`). Two things follow: a cashier can no longer choose a group for a new customer either (it takes the store's default group, and a manager sets the right one), and the till still says *Saved* after a group change it dropped. Check the level 1 rows already there: Sales Master Manager has one by default, and no cashier's role may hold level 1 *Write*. `apply_config.py` does not make these rows, and `remove` puts Customer's permission rows back as they were before `prepare`, this lock's rows with them: make them again after a remove if another app relies on the lock.

5. **Switch the feed on** (the administrator: `apply_config.py switch-on`, or by hand in Desk). On the registration *PP LYL Loyalty* the integration user is named and each followed record type (Customer, POS Invoice, Purchase Receipt) is ticked on: the shop writes a feed row only for a ticked one.
6. **The Member till key.** From the release that carries it, a till key the manifest declares is ready in **POS Studio > Apps** as soon as the app is installed: the consent the administrator reads on the install screen is the key's consent, and the store switches the key on there and places it on its till. Until then it installs switched off with consent not given, and the shop's administrator ticks both in Desk (**Retail Remote App Key**; `switch-on` does it for the sample). A till whose profile wears no theme offers no key.
7. **The partner's service runs.** It reads the feed every 30 seconds with the integration user's key, runs the daily jobs and answers the Member key. On a service shared by many shops, each shop connects itself after its install and hands over the key's secret and the integration user's key ([one service for many shops](#one-service-for-many-shops)).
8. **Optional: Member cash** (the site's administrator, on screens, with CitiXsys: it needs the remote-wallet payments app on the site). In **Remote Connector**, **Payment Account** and **Payment Connection**, then allow Member cash in the till's payment methods and in returns. The steps are [below](#member-cash-spending-the-cash-back-at-the-till). Member cash answers for one shop and has not yet run on a till.

**Where it shows.** In Desk: members and the ledger as ordinary lists, the Customer's Connections (*Loyalty*), the report *PP LYL Cash Back* (for a Sales Manager, who can read members and the ledger but not change them), and a goods receipt's states (*Pending Verification*, *Verified*, *Overridden*). On the till: a member's own prices (the tier's promotion, online or offline), the **Member** key with the tier, the cash back and what reaches the next tier (online only), and, once set up, *Member cash* beside the other payments (never offered offline). Nothing is added to a print layout.

**What leaves the shop.** One address: the partner's service (the manifest ships an example address; the partner writes its own). At each press of the **Member** key the till sends it, signed, the sale's reference, the store, the POS Profile, the company, the currency, the cashier's login, the customer's id when one is on the sale, and each line's item code, quantity and unit; no price or payment. The answer is a message only. The feed registration *PP LYL Loyalty* offers the customer, POS invoice and purchase receipt events; the service pulls them, nothing is pushed, and they wait if it is down. With the integration user's key the service reads customers, sales, purchase orders and suppliers; moves a customer between tier groups; reads, writes and submits goods receipts (and the batch bundle a batch-tracked receipt makes); and writes members and the ledger. It only reads the plans and settings. There are no webhooks. Member cash adds one more address: the service's own, entered on the Remote Connector. The till's payments app asks it what a member may spend and tells it what is taken, given back or reversed, by payment reference.

To take it out, `apply_config.py remove` puts the permission rows back first, then removes what it made; a tier group that customers are still in, and the integration user and its role once it has verified a receipt, stay (switched off instead). Suspend Member cash's Payment Connection first: it stays on the till until then.

## The files

| File | What |
|---|---|
| `manifest.json` | the settings, plans, members and the ledger (every ledger row named by its unique key), two Connections links, a report, the feed registration and the member key, installed switched off (for when the member key arrives ready, see *What the shop does*, step 6) |
| `config.json`, `apply_config.py` | the configuration as data, applied over the record API: the integration user and its rights, a customer group and promotion per tier, the plans and settings, the receipt's workflow and who may submit (`prepare`, `apply`, `switch-on`, `switch-off`, `remove`, `diff`) |
| `service/money.py` | the money rules, and only there |
| `service/loyalty.py` | enrol, earn, take back, credit, tiers; the lock that keeps one member's cash back to one till at a time |
| `service/receipts.py` | the receipt check and the *Verify* step |
| `service/worker.py` | reads the feed (the kit's `tools/feed_client`) and runs the daily jobs |
| `service/wallet.py` | Member cash: the wallet's answers to the till (preview, authorise, status, reverse, refund) |
| `service/app.py` | the member key (`POST /lyl/member`), the wallet's signed route (`POST /paygw/1/<verb>`) and, for many shops, the template's handshake |
| `Dockerfile`, `app.json` | the service as a container serving many shops (built from the kit's root) |
| `tests/` | laptop tests, and `canaries.py`: each money, replay, permission and many-shops test goes red when its rule is broken |

## Run it

```bash
python3 -m unittest discover -s samples/s22_customer_loyalty/tests -p 'test_*.py'
python3 samples/s22_customer_loyalty/tests/canaries.py
```

On a sandbox, in this order (the administrator's key for the configuration, the integration user's for the service):

```bash
PP_BASE=https://your-sandbox PP_KEY=… PP_SECRET=… python3 samples/s22_customer_loyalty/apply_config.py prepare
#   then generate the integration user's API key in Desk (User → Generate Keys); install manifest.json with tools/deploy/deploy.py (on a customer's site: its install screen)
PP_BASE=… PP_KEY=… PP_SECRET=… python3 samples/s22_customer_loyalty/apply_config.py apply
PP_BASE=… PP_KEY=… PP_SECRET=… python3 samples/s22_customer_loyalty/apply_config.py switch-on
python3 samples/s22_customer_loyalty/service/worker.py run service/.env.local --watch 30
python3 samples/s22_customer_loyalty/service/worker.py daily service/.env.local
python3 samples/s22_customer_loyalty/service/app.py service/.env.local
```

## One service for many shops

The same service can serve every shop that installs the app, with the app template's handshake ([chapter 14b](../../guide/14b_deploying_your_app.md#one-app-many-retailers)). Each shop connects itself after its install and hands over the member key's secret and its integration user's key. Every press names its shop and is answered from that shop's records alone, with that shop's key. The feed worker runs inside the same service: every 30 seconds it reads each connected shop's feed with that shop's key, each shop on its own thread so a slow shop never holds up another, and runs each shop's daily jobs once a day (a job that fails is logged with its error's class and tried again the next day, never on every pass; a customer the shop refuses to save is counted in the log with the shop's status code, never by name, and keeps its plan while the other members still move). Its health address answers 503 when the worker has stalled for three minutes, so the platform restarts it. The plans, rates and windows stay in each shop's own settings record, as before.

```bash
docker build --platform linux/arm64 -f samples/s22_customer_loyalty/Dockerfile -t loyalty:1.1.0 .
```

Its settings: `IVN_LIBRARY_APP` (the App library's id, `ivendnext_lyl`), `LYL_PREFIX` (the record types' prefix, the daily balance rows' included: `IVENDNEXT LYL` for the library's app, `PP LYL` for this sample), `PP_STATE` (a writable folder) and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`). **Member cash is not offered this way.** The till's payments app calls a wallet with its own connector id and secret, not the shop's site, so a wallet answers for one shop (below).

## Member cash: spending the cash back at the till

The till's payment screen offers a **wallet**: a payment the till checks with an outside service before it takes it (the wallet extension point, `wallet/1` on the gateway contract `paygw/1`: [`contracts/pages/wallet.md`](../../contracts/pages/wallet.md)). Your service answers it from the ledger it already keeps, at `POST /paygw/1/<verb>` (`service/wallet.py`):

| The till asks | Your service answers |
|---|---|
| *What may this member spend on this sale?* (preview) | the credited balance and the most this sale may take: *Most of a sale Member cash may pay* × the amount due, never more than the balance (0 % = no limit). A walk-in or a non-member is not eligible. Nothing is written |
| *Take this much* (authorise) | a **Redeem** row (minus the amount) named by the payment's reference, so a repeated call is the same one charge; refused when it is more than the balance |
| *Give it back* (reverse, refund) | a **Redeem reversal** for the whole payment, or a **Redeem refund** under the refund's own reference (a payment may come back in several parts, never more than was paid) |
| *What happened to this reference?* (status) | the payment, or the refund, of exactly that reference; *never received* when the ledger holds neither |

A sale paid with a gift card, store credit or on account earns cash back like any other. The gift card earned nothing when it was sold, and store credit comes from a return that took its cash back away. A sale paid partly with Member cash earns no cash back unless *Earn cash back on a sale paid with Member cash* is ticked; it still counts towards the member's tier (its *Earn* row is written at 0, *Cancelled*).

**Setting it up on your sandbox** (on screens, as the site's administrator; ask CitiXsys to install the remote-wallet payments app on your sandbox site and switch on its payments test mode):

1. Sign the wallet's sandbox certificate: `python3 samples/s22_customer_loyalty/service/wallet.py --declaration > declaration.json`, then `python3 tools/sandbox_cert/sign_sandbox_cert.py --declaration declaration.json --partner <you> --connector <name> > certificate.json` ([the tool](../../tools/sandbox_cert/README.md)). A production certificate is issued by CitiXsys alone. S22 declares the US only, the sandbox shop's country: the declaration's markets must include each shop company's country, or go-live refuses.
2. **Remote Connector → New:** paste the certificate, your service's **bare address** (`https://<service>`: the shop adds `/paygw/1/<verb>` itself, so an address ending in `/paygw/1` doubles it and every call answers 404) and a signing secret you choose. Save; the form shows the **site id**.
3. Put the secret, the site id and a merchant reference you choose (for example `STORE-1`) into the service's settings (`PP_WALLET_SECRET`, `PP_WALLET_SITE`, `PP_WALLET_MERCHANT`) and restart it.
4. **Payment Account** (provider: your connector, environment *test*, the shop's currency, the merchant reference from step 3, and a **liability ledger account** for the cash back: going live refuses an account without one) → **Payment Connection** (rail *wallet*; *Certification required*: *not required* on a sandbox, and if a test already ran, the approver ticks *Change acknowledged*) → **Test connection** (it must pass; for two minutes after your service starts it answers *Inconclusive*) → go live. The payments app makes the *Member cash* payment method and lists it on the till.
5. On the till's payment methods, allow Member cash **in returns**, and allow at least one other method in returns too: a refund pays the Member cash part back first and the rest another way. Then run `apply_config.py apply` again, so the settings name the payment method (until they do, a sale paid with Member cash still earns cash back). The payment method takes the Payment Account's own payment-method name, or else its display name; `config.json`'s `wallet_mode_of_payment` must be that name.
6. S22 declares `payer_required: false`: Member cash asks nothing of the customer's phone, so the till asks for no contact number. (A wallet declaring `true` is refused for a customer with no mobile number or email on record; the reference implementation declared `true`, and its walk met that refusal. CitiXsys's payments team walked a wallet declaring `false` on our test site, with a customer who had a phone; a customer with no contact at all has not been tried.)

**When your service is down.** The wallet is never offered offline. If your service does not answer, the till says so on the wallet's sheet and the cashier takes another payment (the product's wallet page says so; not yet walked). ⚠ If you also run a *check before payment* that runs before every sale, its declared down answer decides the rest: *refuse* stops **every** sale at every till while your service is down, wallet or not. That is the shop's choice to make, with you.

**Bounds.** Member cash answers for one shop, set by `PP_WALLET_*`; a service serving many shops answers its routes 404. The conformance kit's test verbs (`induce`, `settle`) answer 403, as a live connector does, so the kit's verdict on this wallet is *incomplete*, never *certified* ([what that means for certification](../../recipes/wallet.md#certification)). A declined answer is remembered by the running service only. One service answers the wallet, and a lock per member stops two tills spending the same cash at once. For two minutes after the service starts, the till's status question answers *unknown* about anything a refund or reversal does not settle, because a write from before the restart may still land. The status answer is in the programme's currency with the settings' *Decimal places*, so that setting must be the currency's own. A return booked after its cash back was credited and spent can take the balance below zero; the member key then shows it below zero, and the preview offers nothing. *Most of a sale Member cash may pay* at 0 means no limit, and so does a negative number: type it with care. A payment or refund whose write to the shop timed out but may still land is not counted by the next call for that member until it lands (the till's status question answers *unknown* about it meanwhile).

`apply_config.py remove` takes it all back out, permission rows first. Two kinds of record stay, and the line says which: a tier group a customer is still in (move those customers first if it must go), and the integration user and its role once the user has verified a receipt. Those two are switched off instead: the user disabled with new keys no one keeps, the role disabled, and a later `prepare` switches both back on. The shop keeps a record of every workflow step taken, naming who took it, and only the site's Administrator can see or delete those records. `switch-off` switches everything off and removes nothing: run it first if a test of yours fails half-way. ⚠ Neither `switch-off` nor `remove` touches Member cash: it stays on the till until you suspend its Payment Connection on the payments screens, so do that first.

## Before you build on it

- **One connected app, one integration user, one desk licence.** The till's calls to your service (the member key, and Member cash) are each signed with their own secret and need no API key.
- **Seconds, not inside the sale.** Cash back and tier changes arrive seconds after the sale books (the feed). A tier change reaches an offline till at its next start.
- **Combined discounts follow the promotion rules,** not your own arithmetic. If the customer needs member discounts to multiply with other offers, that is an extension point to request.
- **Your choices, with the customer:** the earning base (here the grand total less gift cards sold and the goods' share of a tender discount; `money.earn_base`), what counts as spend for the tiers (here the grand total less gift cards sold; `money.goods_value`), the return window, the thresholds and rates.

## Technical notes

### Why this way

*An app installed inside the shop* (refused: partners ship no code into a shop) · *your own database for members and the ledger* (rejected: staff lose the shop's own screens, reports and audit) · **the records as manifest record types, the rules in your service** (picked: no code inside, native screens, the shop's own audit). Tiers: *a pricing rule per member* (refused: this product refuses selling pricing rules) · **a promotion per customer group** (picked: priced by the till itself, offline too).

### Idempotency

Every ledger row is named by its key — `POS Invoice:<sale>:earn`, `…:<return>:return`, `…:<sale>:cancel` — so the shop refuses a second row for the same event (HTTP 409), and the service treats that as done. The feed client's own note of handled events is only a cache in front of it: `tests/test_service.py` kills the service between the shop's write and that note, replays, and still finds one row.

A return that is itself cancelled is not undone: its *Return* row, and the cash back it took back, stay (the sample does not give them back). Cancelling the sale afterwards takes out only what its returns have left, so the year's spend for it ends at 0 (it can end below 0 only if cancelled returns together exceed the sale).

### Money

`Decimal` throughout, rounded half-up to the currency's decimals. A sale's value (`money.goods_value`) is its grand total less its gift card lines (*Gift Certificate*, *Gift Certificate Recharge*, *Gift Certificate Cashback*) at what each added to it (`net_amount`, plus the tax the sale's tax rows put on it: `item_wise_tax_detail`). The *Earn* row keeps it as `sale_base`; the tiers count it. The sale earns on that value less the goods' share of its tender discount (`custom_tender_discount_amount`, a write-off the grand total keeps, less the gift card lines' `custom_tender_discount_apportioned`). A return takes `earned × the return's grand total ÷ sale_base`, capped at what is left (the engine refuses a gift card on a return, so returns and `sale_base` are on one scale, up to each document's rounding); the return that completes the sale takes exactly what is left. Bounds: where a sale's lines carry different tax, a partial return's share can differ a little from the exact share (the last return evens it out); a sale discount spread over several returns can leave them a cent short of the whole sale, so a cent of cash back stays. While the earning is *Pending*, a return is *Netted* (the earning is reduced); after *Credited* it is a negative row.

### The feed

The worker reads the event feed's door, scoped to your own application, with the kit's feed client (`tools/feed_client`). The door takes POST only, and the client sends POST; the client's own tests hold that.

### What was proven where

- **On the laptop:** 92 tests and 63 canaries, all against in-memory stand-ins for the shop (Member cash: 23 tests and 22 canaries; many shops: 16 tests and 12 canaries, two shops sharing a customer's name, one of them stuck).
- **On a site in the sandbox's shape** (our test bench, 2026-10-09, with manifest 0.1.0, before Member cash was added; Member cash has not run on a bench or a till: a new site with developer mode off and the sandbox template's Demo Retail in US dollars, dropped after; the template's own demo promotion, *10% off the sale*, was switched off for the run, so the member rates are the sample's alone — on your sandbox it stays on and adds to every sale): our installer installed the manifest switched off; `prepare`, `apply` and `switch-on` set the shop up; the service ran beside it on the real event feed. Every check passed: both new customers joined Bronze from the feed; a walk-in and a Bronze member paid no member discount; a big spender moved to Silver at the daily job and then paid 3% only, one tier promotion; the member key answered on the till (*Silver*, the cash back, what reaches Gold) and said *no member* on a walk-in's sale; each earning was 2% of its sale; a partial return took its exact share, netted against the pending earning; every handled event delivered again changed nothing; a receipt the order waited for was *Verified* by the service's user, one that took more stayed waiting with the service's reason; *Verify* was refused for the administrator, and the administrator's submit through the record API was refused. The kit's sandbox check passed 8 of 8 on the same site.
- **What a sandbox walk of the reference implementation taught it** (2026-10-12): a goods receipt for a batch-tracked item makes and submits its batch bundle as the integration user when it is verified, so the integration role needs *create*, *write* and *submit* on *Serial and Batch Bundle* (in `config.json`, held by a test); and steps 2, 4, 5 and 6 of the Member cash set-up above, each of which the first set-up got wrong.
- **What the bench taught this sample** (each now in the files, with a test where a laptop test can hold it): `switch-on` must tick each followed record type of the feed registration, not only name the user; the integration user needs the *Is Desk User* field (`custom_is_desk_user`) when made over the API; reading a receipt needs read on its supplier; the maker's own *Send for Verification* must allow self-approval; the integration role is the app's own (*PP LYL Integration*), never one another app's user holds; `remove` puts every right of every permission row back (*select* included).
