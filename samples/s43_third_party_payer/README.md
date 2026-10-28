# S43 — Third-party payer (`pp_icp`): an insurer, or anyone else, paying part of a sale

*Start from this sample: `python3 tools/manifest/start.py s43_third_party_payer --prefix "ACME ICP"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

In many markets a pharmacy cannot sell to most of its patients without their insurer: the insurer pays part of the sale and the patient pays the rest. The same shape serves an optical plan, and a company paying for what its staff buy. This app is **one payer service for any third party that pays part of a sale**. Its payers, plans, formularies and members are records the retailer fills; it answers the POS app's **payer door** line by line, makes a **claim** from each sale the door books, files claims as a file, and follows each claim to payment.

Its first data set is **one generic insurer**, with the co-pay rules of an iVend Retail add-on we built for a pharmacy chain and an insurer price-list rule a pharmacy customer ran. A second data set, **a company paying 70% of what its staff buy**, loads and answers with no code change.

⚠ **The generic insurer is a sample, not a real insurer.** A partner replaces it with each real payer's terms, and writes each payer's own claim link (NHIF/SHA, NPHIES, eClaimLink, Shafafiya, NHIA) against the same door.

**When to use it:** a third party pays part of a sale, the retailer claims it afterwards, and the customer pays only their share at the till.

## The payer door

The payer's share must be **owed by the payer**, booked as money the payer owes the retailer, never as money already taken (a wallet leg reads *paid*). An app installed from a manifest cannot book that, so the POS app carries a **payer door** (iVendNext POS 2.1.0 build 666 or later; [the recipe](../../recipes/third_party_payer.md)). The door asks this service which covers the customer holds and what the picked cover pays, line by line, before the tender; books the payer's share against the payer's own customer record; prints *Billed to* and *Paid by you* on the receipt; gives the payer's share back on a return; and bills a rejected claim back to the customer on their own sale.

| Part | What it is |
|---|---|
| `manifest.json` | the payer service the door calls (`point: "payer"`, the `payer/1` contract, installed switched off), the records (Payer, Plan, Formulary, Member, Claim, Claim Batch, Remittance), the tick *Barred from sales a third party pays* on Customer, the roles **PP ICP Claims Clerk** and **PP ICP Integration**, six Desk buttons (*Build claims*, *Make the claims file*, *Match*, *Mark ready*, *Settle as it stands*, *Bill to the customer*), four reports and two charts |
| `service/app.py` | the service: the door's two calls, `covers` and `coverage`, answered in the contract's own shape (money in whole minor units of the sale's currency, each line's quantity in its own unit), and the six buttons |
| `copay.py` · `claims.py` | the plan's rules and the claims, as pure functions over plain data |

**What the shop sets before it switches the payer service on** (the door refuses the switch until each is there; `docs/extending/payer.md` §2):

1. **The clearing mode**: the shop's own mode of payment of type Custom, on its own balance sheet account, named in the subscription's settings as `clearing_mode`. A manifest never carries it: the account is on the shop's books. It carries the payer's share for an instant, until the door moves it onto the payer.
2. **The clearing mode on each payer till's POS Profile**, with *Allow in Returns* ticked and never as the default: a return gives the payer's share back on it. The till never shows it as a tender.
3. **The right to sell on a payer** (`payer-sale`) on the cashiers' Retail Permission.
4. **No plan's price list as a customer group's default**: it would price every sale of the member, insured or not. The door switches the sale to the plan's list when the cashier picks the cover.
5. **The prescription, where the payer needs one.** This version sends none (the subscription's `prescription` setting is empty). The pharmacy counter app ([S39](../s39_pharmacy_counter/README.md)) keeps a prescription's number, prescriber and the prescriber's licence as sale details; with it installed, the administrator adds `"prescription": {"reference": "<its number detail>", "prescriber": "<its prescriber detail>", "prescriber_licence": "<its licence detail>"}` to the payer service's settings, each the name of a sale detail on the site, and ticks consent again (the consent text then names them). The door refuses a name the site does not have, so this version cannot carry S39's names for a shop without S39.

## How a sale is split

The plan's rules, all data (`copay.py`, the tests' 1,728 combinations):

| Rule | What it does |
|---|---|
| **Co-pay %** | the customer's share of the covered amount inside the limit |
| **Invoice upper limit** | the payer covers at most this much of one sale; the rest of the covered amount is the customer's (0: none) |
| **Maximum co-pay** | the co-pay never exceeds it (0: none). The excess over the limit and extra-item pay are not co-pay |
| **Extra-item pay** (a formulary row) | a fixed amount per stock unit the customer always pays, at face, before anything else |
| **The limit is compared with the amount** before or after the sale's discount | *Before the limit*: after the discount · *After the limit*: before it |
| **The co-pay % is taken** before or after the discount | *Before*: the payer keeps the whole discount · *After*: the customer shares it |
| **Returned whole or not at all** | a sale on the plan is returned whole, or not at all |
| **Most units on a sale** (a formulary row) | units past it are the customer's |
| **Covers** formulary items or every item | a line the plan does not cover is the customer's |
| **Price list** | when set, a sale on the plan is priced on it, and an item it does not carry, or carries at zero, **cannot be sold on the plan** (a row counts only as the engine applies it: in force today, in the line's unit or none, for no other customer, for no batch) |
| **The shop's own promotions apply** | off: the payer door prices a sale on the plan with the retailer's promotions switched off, so a retail promotion is not stacked on the payer's list (the add-on cleared them on every insured line). A coupon or a staff discount the cashier chose still applies, and so can an old-style pricing rule (`payer.md` §7) |

⭐ **The payer's share plus the customer's always equals the sale, to the minor unit**, and the payer's share is spread over the covered lines in proportion. **The sale's prices are never changed here**: the retailer's own pricing (the plan's price list, its pricing rules) prices the sale, and these rules only split it. So the excess over the limit carries the sale's own discount. (The original add-on re-priced each line and added a surcharge so the patient paid the excess undiscounted; a retailer wanting that sets it in its pricing.)

⚠ **The price-list rule reads the plan's list itself, never the line's price.** The door keeps the price the till would otherwise give a line the plan's list does not carry (the customer's own default list, else the store's), so a line's price proves nothing: the service reads the retailer's Item Prices on the plan's list and answers `refuse` with `not_on_list` or `zero_on_list` for that line. The cashier takes it off, or sells the whole sale without the payer.

**What the door is answered, beside the rules:** the payer's share is never more than the sale's rounded total (the rounding is always the customer's); a sale the plan would pay nothing on is answered *no cover* (the door takes no cover that pays nothing); where the prices exclude tax, a line's discount is read with its tax (the line's amount includes it), so the limit and a co-pay taken before the discount compare like with like; the extra-item pay stays inside the customer's share (the contract carries no key for it).

## Claims

1. The door books a sale with its payer details (its claim reference, the cover, each line's two shares, the prescription details it sent). The event feed says so.
2. **Build claims** (a button on the Payer list) reads the feed and makes one **Claim** per booked sale, named by its claim reference, so a sale is never claimed twice. A return reduces its claim's lines by what it gave back to the payer, once.
3. A claim missing what its payer needs (the payer's ticks: member number, card serial, prescription, each line's GTIN, dose and frequency) is **Incomplete**: the claims clerk fills it on the Desk and presses **Mark ready**, which is refused while anything is still missing. A claim's status is never typed: the claims file, *Match*, *Mark ready* and *Settle as it stands* (a short-paid claim closed with its shortfall left on the payer's account) move it. ⚠ The pharmacy counter-rules app (S39) keeps a prescription's directions as free text, so the clerk types the dose and frequency where a payer asks for them (Abu Dhabi's Shafafiya does, on every line).
4. **Make the claims file** (a button on a Payer) puts every Ready claim of that payer into one **Claim Batch**: a CSV, one row per claim line, the file you send to the payer. Each claim becomes **Submitted** (**Resubmitted** when it was corrected after a rejection). A cell is never written so that a spreadsheet runs it as a formula.
5. The payer's **Remittance** is entered line by line (claim, paid, rejected, the payer's reason); **Match** sums every line of one claim, then compares it with what the claim is still owed, so a payer paying a claim line by line, or in parts over several remittances, is followed to the cent: **Paid**, **Short paid**, **Rejected**, or *Unmatched* (a reference the payer sent that is not ours, or a claim of another payer). The money itself is the retailer's own payment from the payer's customer record, allocated against what the door booked.
6. A rejected claim is corrected and made Ready again with *Mark ready* (the next file sends it as *Resubmitted*), or **billed to the customer** with *Bill to the customer* (on a rejected or short-paid claim): the door books what the payer did not pay against the customer's own sale, which the till's *Take a payment* then lists for them. A till sale is billed back only after the day it was sold on is closed (the door says so in its own words, and the claim stays as it was); the app's user bills it, with the role **PP ICP Integration** the payer service's settings name (`bill_back_role`).

Reports: *PP ICP Claims*, *PP ICP Rejected and short-paid claims*, *PP ICP Incomplete claims*, *PP ICP Remittances*; charts *PP ICP Payer share by month* and *PP ICP Claims by status*.

## What leaves the retailer's iVendNext

The service reads iVendNext with its integration user's key and answers the door. ⚠ **Members and claims are health data for a pharmacy**: run the service in the retailer's own region. The claims file goes to the payer, which is the point of a claim; send it nowhere else. The service keeps nothing between calls. A member number reaches the till only masked to its last four characters.

## What the retailer does (now)

**Before you install:** every `host.docker.internal` address in `manifest.json` (in `allowed_urls`, and where the manifest calls it) is our test bench's own address for the sample's service, and it resolves only where Docker provides it. Replace it with your own service's address first, or iVendNext's calls never reach your service; if this manifest is already installed, raise its `version` and install it again ([the manifest recipe](../../recipes/manifest.md), step 6).

1. **Install the app** (the retailer's administrator; iVendNext POS 2.1.0 build 666 or later). Then set up and switch on the payer service (*The payer door* above).
2. **Give the role PP ICP Claims Clerk** to whoever sets up payers and files claims. Members and claims are read by that role and the service's user only, never by a till role. ⚠ The *Barred* tick is on Customer, so anyone who can edit a customer can clear it; to stop a cover for certain, the clerk also switches the customer's Member off.
3. **Make each payer**: its own **Customer record** first (what it owes is booked against it), then the Payer, its formulary, and each plan with its rules and price list. A data set file (`datasets/`) loads a payer in one go: `python3 dataset.py records datasets/generic_insurer.json` lists the records it makes.
4. **Make each customer's cover**: a Member per policy (customer, plan, member number exactly as on the card).
5. **Give the price list its prices**: the retailer's own Item Prices on the plan's list. ⚠ Do not make the plan's list a customer group's default: it would price every sale of the member, insured or not; the door switches the sale to the plan's list when a cover is picked.
6. **Switch its record types on (POS Invoice, Sales Invoice) and save, ask iVendNext support to set the app's user as its Application User (a user made for the app alone, never a person's), then press Connect again** (each button says so until you do). That user reads POS Invoices, Sales Invoices, Items, Item Prices, Price Lists and Customers, writes the app's own records, and bills a rejected claim back: give it the role **PP ICP Integration**.

## Data sets

A data set is a JSON file: its payer (code, title, kind, its customer record, what a claim needs), its price list's name, its formularies and its plans. `dataset.py`'s `check()` is the whole format: it refuses a plan naming a formulary the file does not have, a co-pay outside 0–100, an unknown key, a payer kind or claims format the standard version does not know, each in words.

| File | Payer | Shows |
|---|---|---|
| `datasets/generic_insurer.json` | *Generic Insurer* | two plans (Gold: 10% after the discount, at most 500; Silver: 20% before the discount, a 5,000 limit), a formulary by item group with extra-item pay and a quantity limit on over-the-counter medicine, the insurer's price list |
| `datasets/corporate_account.json` | *Acme Ltd (staff purchases)* | a company paying 70% of every item, up to 2,000 a sale: no price list, no formulary |

## Run it

```bash
python3 -m unittest discover -s samples/s43_third_party_payer/tests -p 'test_*.py'
python3 samples/s43_third_party_payer/tests/canaries.py
python3 tools/check/check.py samples/s43_third_party_payer
```

The service: `python3 samples/s43_third_party_payer/service/app.py service/.env.local` (one retailer; the file holds `IVN_SHOP_URL`, `IVN_SHOP_KEY` and `IVN_SECRET_CLAIMS`, `_FILE`, `_REMIT`), or many retailers through the app template's handshake. It runs as a function: it only answers calls and presses.

Recipe: [`recipes/third_party_payer.md`](../../recipes/third_party_payer.md).
