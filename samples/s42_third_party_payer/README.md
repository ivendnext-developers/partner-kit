# S42 — Third-party payer (`pp_icp`): an insurer, or anyone else, paying part of a sale

In many markets a pharmacy cannot sell to most of its patients without their insurer: the insurer pays part of the sale and the patient pays the rest. The same shape serves an optical plan, and a company paying for what its staff buy. This app is **one payer service for any third party that pays part of a sale**. Its payers, plans, formularies and members are records the shop fills; it answers the POS app's **payer door** line by line, makes a **claim** from each sale the door books, files claims as a file, and follows each claim to payment.

Its first data set is **one generic insurer**, with the co-pay rules we built for a pharmacy chain in Egypt on iVend Retail and the insurer price-list rule a pharmacy in Kenya ran. A second data set, **a company paying 70% of what its staff buy**, loads and answers with no code change.

⚠ **The generic insurer is a sample, not a real insurer.** A partner replaces it with each real payer's terms, and writes each payer's own claim link (NHIF/SHA, NPHIES, eClaimLink, Shafafiya, NHIA) against the same door.

**Door:** Manifest + the payer door (⏳ requested from the POS team) + Desk buttons + the event feed

**When to use it:** a third party pays part of a sale, the shop claims it afterwards, and the customer pays only their share at the till.

## The payer door: what is here now, and what waits for it

The payer's share must be **owed by the payer**, booked as money the payer owes the shop, never as money already taken (a wallet leg reads *paid*). An app installed from a manifest cannot book that, so the POS app carries a **payer door** for it. The door asks this service what the cover pays before the tender, books the payer's share against the payer's own customer record, prints the claim reference and the split on the receipt, and gives the payer's share back on a return. ⚠ **The door is not in the POS app yet.** Its specification is written and requested on the POS team's board.

| Part | Installs | What it is |
|---|---|---|
| `manifest.json` | ✅ **now** | the records (Payer, Plan, Formulary, Member, Claim, Claim Batch, Remittance), the tick *Barred from sales a third party pays* on Customer, the roles **PP ICP Claims Clerk** and **PP ICP Integration**, three Desk buttons (*Build claims*, *Make the claims file*, *Match*), four reports and two charts |
| `door_declaration.json` | ⏳ **after the door** | the door's subscription (`point: "payer"`, the `payer/1` contract) and the claims clerk's *Bill to the customer* button, whose service calls the door's `payer_bill_back`. The shop's checker refuses the point until the door is there; this app's next version (0.2.0) installs both |

Until the door is there, nothing is sold on a payer. Setting the app up now (payers, plans, formularies, members) means the door's first sale has them.

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
| **Price list** | when set, a sale on the plan is priced on it, and an item it does not carry, or carries at zero, **cannot be sold on the plan** |

⭐ **The payer's share plus the customer's always equals the sale, to the cent**, and the payer's share is spread over the covered lines in proportion. **The sale's prices are never changed here**: the shop's own pricing (the plan's price list, its pricing rules) prices the sale, and these rules only split it. So the excess over the limit carries the sale's own discount. (The original add-on re-priced each line and added a surcharge so the patient paid the excess undiscounted; a shop wanting that sets it in its pricing.)

⚠ **The price-list rule reads the plan's list itself, never the line's price.** The till re-prices an item missing from the sale's list, or at zero on it, from the store's list without a word; so a line's price proves nothing, and the service reads the shop's Item Prices on the plan's list.

## Claims

1. The door books a sale with its payer details (its claim reference, the cover, each line's two shares, the prescription details it sent). The event feed says so.
2. **Build claims** (a button on the Payer list) reads the feed and makes one **Claim** per booked sale, named by its claim reference, so a sale is never claimed twice. A return reduces its claim's lines by what it gave back to the payer, once.
3. A claim missing what its payer needs (the payer's ticks: member number, card serial, prescription, each line's GTIN, dose and frequency) is **Incomplete**: the claims clerk fills it on the Desk and sets it **Ready**. ⚠ The pharmacy counter-rules app (S39) keeps a prescription's directions as free text, so the clerk types the dose and frequency where a payer asks for them (Abu Dhabi's Shafafiya does, on every line).
4. **Make the claims file** (a button on a Payer) puts every Ready claim of that payer into one **Claim Batch**: a CSV, one row per claim line, the file you send to the payer. Each claim becomes **Submitted** (**Resubmitted** when it was corrected after a rejection). A cell is never written so that a spreadsheet runs it as a formula.
5. The payer's **Remittance** is entered line by line (claim, paid, rejected, the payer's reason); **Match** compares each line with its claim: **Paid**, **Short paid**, **Rejected**, or *Unmatched* (a reference the payer sent that is not ours, or a claim of another payer). The money itself is the shop's own payment from the payer's customer record, allocated against what the door booked.
6. A rejected claim is corrected and made Ready again, or **billed to the customer**: ⏳ the *Bill to the customer* button installs with the door, which books it.

Reports: *PP ICP Claims*, *PP ICP Rejected and short-paid claims*, *PP ICP Incomplete claims*, *PP ICP Remittances*; charts *PP ICP Payer share by month* and *PP ICP Claims by status*.

## What leaves the shop

The service reads the shop with its integration user's key and answers the door. ⚠ **Members and claims are health data for a pharmacy**: run the service in the shop's own region. The claims file goes to the payer, which is the point of a claim; send it nowhere else. The service keeps nothing between calls. A member number reaches the till only masked to its last four characters.

## What the shop does (now)

1. **Install the app** (the shop's administrator).
2. **Give the role PP ICP Claims Clerk** to whoever sets up payers and files claims. Members and claims are read by that role and the service's user only, never by a till role.
3. **Make each payer**: its own **Customer record** first (what it owes is booked against it), then the Payer, its formulary, and each plan with its rules and price list. A data set file (`datasets/`) loads a payer in one go: `python3 dataset.py records datasets/generic_insurer.json` lists the records it makes.
4. **Make each customer's cover**: a Member per policy (customer, plan, member number exactly as on the card).
5. **Give the price list its prices**: the shop's own Item Prices on the plan's list. ⚠ Do not make the plan's list a customer group's default: it would price every sale of the member, insured or not; the door switches the sale to the plan's list when a cover is picked.
6. **Choose the app's user on its feed, then press Connect again** (each button says so until you do). That user reads POS Invoices, Sales Invoices, Items, Item Prices and Customers, and writes the app's own records.

## Data sets

A data set is a JSON file: its payer (code, title, kind, its customer record, what a claim needs), its price list's name, its formularies and its plans. `dataset.py`'s `check()` is the whole format: it refuses a plan naming a formulary the file does not have, a co-pay outside 0–100, an unknown key, a payer kind or claims format the standard version does not know, each in words.

| File | Payer | Shows |
|---|---|---|
| `datasets/generic_insurer.json` | *Generic Insurer* | two plans (Gold: 10% after the discount, at most 500; Silver: 20% before the discount, a 5,000 limit), a formulary by item group with extra-item pay and a quantity limit on over-the-counter medicine, the insurer's price list |
| `datasets/corporate_account.json` | *Acme Ltd (staff purchases)* | a company paying 70% of every item, up to 2,000 a sale: no price list, no formulary |

## Run it

```bash
python3 -m unittest discover -s samples/s42_third_party_payer/tests -p 'test_*.py'
python3 samples/s42_third_party_payer/tests/canaries.py
python3 tools/check/check.py samples/s42_third_party_payer
```

The service: `python3 samples/s42_third_party_payer/service/app.py service/.env.local` (one shop; the file holds `IVN_SHOP_URL`, `IVN_SHOP_KEY` and `IVN_SECRET_CLAIMS`, `_FILE`, `_REMIT`), or many shops through the app template's handshake. It runs as a function: it only answers calls and presses.

Recipe: [`recipes/third_party_payer.md`](../../recipes/third_party_payer.md).
