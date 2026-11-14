# S43 — Third-party payer (`pp_icp`): an insurer, or anyone else, paying part of a sale

In many markets a pharmacy cannot sell to most of its patients without their insurer: the insurer pays part of the sale and the patient pays the rest. The same shape serves an optical plan, and a company paying for what its staff buy. This app is one payer service for any third party that pays part of a sale. Its payers, plans, formularies and members are records the retailer fills. It answers the till's payer door line by line, so the customer pays only their share, makes a claim from each sale, files the claims as a file, and follows each claim to payment. The payer's share plus the customer's always equals the sale, to the minor unit.

**Industries:** Optical, Pharmacy

The first data set is one generic insurer, a sample and not a real insurer: a partner replaces it with each real payer's terms. A second data set, a company paying 70% of what its staff buy, loads with no code change.

**When to use it:** a third party pays part of a sale, the retailer claims it afterwards, and the customer pays only their share at the till.

## Start from it

```bash
ivn new acme_payer --from s43
```

## What to change

What a partner usually changes:

- the payers, plans and formularies: the data set files in `datasets/` (`generic_insurer.json`, `corporate_account.json`); `python3 samples/s43_third_party_payer/dataset.py records datasets/generic_insurer.json` lists the records a set makes;
- how a sale is split: `copay.py`;
- how claims are made, filed and matched: `claims.py` and `service/app.py`;
- the service's address: `allowed_urls` and the payer service's endpoint in `manifest.json` name the sample's test address; write your own.

More: the [recipe](../../recipes/third_party_payer.md).

**The customer sets:** the clearing mode (its own mode of payment of type Custom, named in the payer service's settings as `clearing_mode`, and on each payer till's POS Profile), *May Sell on a Payer* on the cashiers' Retail Permission, and the payers and members. The role **PP ICP Integration** needs no read from the retailer's administrator: the install gives it read on POS Invoice and Sales Invoice, the two record types the feed follows, and the manifest's `role_rights` give read on Retail Payer Record, Item, Item Price, Price List and Customer. **Needs POS build `2.1.0.691` or later:** on an earlier site the install warns `role_rights` as unknown and skips it, and gives the feed's user no read, so the events wait (a build older still stops the install at the payer service, whose `line_net` it does not know); the service's log says which record type was refused (`ivn logs`). Members and claims are health data for a pharmacy: run the service where the retailer's country's law lets that data go.

**Switching the payer on (once, after the install):** the install leaves the payer service off until the store names its clearing mode, which a manifest may not carry. In Desk, open **Retail Extension Subscription** *Third-party payer* and add `clearing_mode` to **Settings for this extension point**, naming the store's own mode of payment. Keep the two settings already there (`bill_back_role`, `line_net`) as they are: changing `line_net` clears the consent. The settings then read:

```json
{"bill_back_role": "PP ICP Integration", "line_net": true, "clearing_mode": "Billed to payer"}
```

Then tick **Enabled** and save. Only one payer service may answer a POS Profile: if another payer service is on for the same tills, give each its own tills in **Only for these POS Profiles**, or switch the other off; otherwise the save says *One payer service per POS Profile*.

**A discount on the whole sale:** on prices without tax the service asks the till for each line's net (`line_net` in `manifest.json`) and puts the discount on the amount's basis with the line's own ratio, so the plan is billed to the cent. This is exact when every tax on the line is a percentage of its net; a fixed charge's share over-states the discount's tax. A till that does not send the net gets the older reading, which under-reads the discount's tax by up to the co-pay on it.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- Choose an insured customer, press Pay, then press Payer on the payment screen.
- The payer's share is taken as one line; the customer pays the rest.
- Close the till day when you are done.

## Versions

### 0.5.1

- **Make the claims file** also attaches the file to its claims batch as a private file named after the batch (`<batch>.csv`), so the claims clerk downloads it from the batch's attachments instead of copying it out of the field. The field keeps the same text. A site whose allowed file types leave out csv still gets the batch, and the press says to copy the file from the field.
- The README shows the exact settings line that switches the payer on, and what to do when a second payer service answers the same tills.

### 0.5.0

- Asks the till for each line's net (`line_net`), so a discount on the whole sale bills the plan to the cent: on a 50.60 sale at a 20% co-pay, 15% tax and 20% off, the plan was billed 0.33 too much before and nothing too much now.
- **The consent text changes.** It now also says *each line's amount before tax and charges*: the service gets each line's net, which the price, discount and amount it already had imply. Updating from the App library keeps the payer service on, and its consent carries over with the new words recorded. Only a store whose administrator edits the payer service's settings by hand in Desk has its consent cleared and ticks it again.
- *Store* where the manifest said *shop*.

### 0.4.0

- The role's reads beyond the feed's (Retail Payer Record, Item, Item Price, Price List, Customer) move into the manifest (`role_rights`), and the install gives the feed's user its two reads, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 0.3.1

- The claims file writes each value as it is.

### 0.3.0

- Reads a payer sale's details from its payer record (POS 2.1.0 build 672 or later): the sale, then the Retail Payer Record it names, each record line matched to its sale line by position. Asks for a read on seven record types.

### 0.2.0

- Installs the payer service on the POS app's payer door (POS 2.1.0 build 667 or later) and the claims clerk's Bill to the customer button, in one manifest.
- Answers in the shipped payer contract, money in whole minor units, checked against the contract's own schema.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.

### 0.1.0

- First version in the kit: an insurer's or a company's share of a sale, split by the plan's rules and claimed from the sales.
