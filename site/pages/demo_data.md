# Demo data for your sandbox

A sandbox handed to a developer starts empty: no company, no store, no item. You choose what goes on it. A **demo pack** is one made-up retail chain, ready to sell: its company, stores, tills, people, catalogue with photos, stock, customers and a few past sales. Load one pack, or several side by side (Electronics and phones is the one that needs a sandbox to itself). Put one back before a demo, or take it off again. Each pack lives in a company of its own: your own companies, items, users and apps are never touched.

**A sandbox a partner's owner receives arrives loaded.** The sandbox an owner receives on the partner portal has Multi-category retail loaded about three minutes after the approval. The portal home's **Your sandbox** says *Getting your demo chain ready*, then *Ready to sell*, and then shows the manager's and cashiers' logins, each with its role and till ID, above the administrator's, until an owner presses **I have saved it**. **Show its logins** on the pack shows them again, to an owner or a developer.

Demo packs are for the sandboxes we hand out. A site you added yourself on **My sites**, such as a customer's test site, is not offered one: made-up sales do not belong in a customer's books.

## Load, reset, refresh, remove

On **My sites**, press **Demo data** on your sandbox. In a terminal, use `ivn demo`. A partner's owner finds the same packs under **Demo data** on the partner portal home's **Your sandbox**, with **Load**, **Reset**, **Remove** and **Show its logins** (**Refresh** is for a developer's vertical apps, on **My sites**). So an owner or a developer can reset a pack before a demo, remove it or load another (Electronics and phones only after the others are removed).

| You want to | On My sites · in a terminal |
|---|---|
| See the packs, and which are on your sandbox | **Demo data** · `ivn demo` |
| Load a pack | **Load** · `ivn demo load multi-category` |
| Put it back to the start of its demo script | **Reset** · `ivn demo reset multi-category` |
| Fill the fields of the vertical apps installed now | **Refresh** · `ivn demo refresh multi-category` |
| Take it off the site | **Remove** · `ivn demo remove multi-category` |
| See its logins again | **Show its logins** · `ivn demo logins multi-category` |

`ivn demo` acts on your default site; `--site` names another by its address or its label.

**Load** takes a few minutes (about three for Multi-category retail) and runs on our side: you can leave the page and come back, and `ivn demo` follows a load that is still running. The screen shows the stage it has reached (*Stores*, *Catalogue*, *Stock*, *People*, *Past sales*, *Checking*), with the pack's own notes under **Details**, then the pack's logins: each person's till ID and password. **Then sell:** open the till: your sandbox's address followed by `/pos`. It asks for an *Associate ID* and an *Associate PIN*, and a pack's people have no PIN: tap **Use your password instead**, sign in as `cashier1` with that password, open a day (`Till-1` asks for a counted float) and ring a sale. If a load stops part-way, the pack reads **Partly loaded** and says what to do: **Load** finishes it, making only what is missing, and **Remove** takes it off.

**Reset** closes any till day left open on the pack's tills, tops its stock up, and puts its prices and card balances back. The sales you rang stay in the books.

**Refresh** is for vertical apps, the App library apps made for one industry. See *Trying one vertical app after another* below.

**Remove** deletes the pack's company with everything in it, and cannot be undone: its stores, tills, stock, items, customers and logins, and every sale rung in that company, yours included. It takes two to five minutes, and the screen shows nothing new until it ends: wait, it has not stopped. The page asks you once before it starts; `ivn demo remove` does not ask. A setting the pack changed is put back to what it was. Your own company, items, users and apps stay as they are.

One pack is worked on at a time on a site. While one runs, the buttons wait.

**A sandbox you were given before 24 November 2026** already holds a *Demo Retail*, made the earlier way with a smaller catalogue. It shows as Multi-category retail, and it keeps working as it did. To get the pack described here, **Remove** it, then **Load**.

## Multi-category retail

**Start with this one.** One department-store chain, **Demo Retail**, whose catalogue has a department for each retail industry. It gives every app something to work on, whatever it is for.

| Part | What it holds |
|---|---|
| Company | **Demo Retail**: a US chain in US dollars. Prices exclude sales tax, and 8% is added at checkout |
| Stores | **Demo Retail — Store 1, Store 2, Store 3**. Each has its own stock and one till profile, which serves the phone, the counter till and the tablet alike |
| Tills | two per store. `Till-1` has a cash drawer: it asks for a counted float when the day opens and a count when it closes. `Term-2` has none, so you can try both |
| Catalogue | about 220 items in ten departments: Apparel and footwear, Grocery and supermarket, Electronics and phones, Hardware and DIY, Beauty and cosmetics, Liquor and wine, Optical, Thrift and resale, Travel retail, Distribution. Each item has a barcode, a price, a cost and stock in every store; most have a photo |
| Price list | **Demo Retail Price List** |
| Promotion | **DEMO-10-OFF**: 10% off the sale, in every store, switched on |
| Customers | a walk-in customer and two members of the loyalty programme, **Demo VIP Customer** (with 500 points) and **Demo Repeat Customer** |
| Cards | a gift card with $100 on it (`DEMO-GC-0001`) and a store credit of $50 (`DEMO-SC-0001`) |
| History | two past purchases by the VIP customer, so returns and reports have something to read |

**Its people.** The logins show on the screen when the load ends, and under **Show its logins** afterwards.

| Who | Till ID | Sign-in in Desk | What for |
|---|---|---|---|
| Store manager | `manager` | `manager@demo-retail.example` | a manager's work at the till: approvals, returns, closing the day |
| Cashier 1 | `cashier1` | `cashier1@demo-retail.example` | selling at the till, in any of the three stores |
| Cashier 2 | `cashier2` | `cashier2@demo-retail.example` | the same |

Each signs in at the till with its till ID and the password the screen showed. Your own administrator login came with the sandbox and is not part of a pack.

Every item is returnable for 30 days, and Cash pays refunds in every store.

### Trying one vertical app after another

A vertical app adds its own fields to items and item groups: the age a buyer must be, a duty-free allowance, a bottle's strength. Multi-category retail knows the values for three of iVendNext's own apps, and **Refresh** writes them on the department each app serves:

| App | Department | What Refresh fills |
|---|---|---|
| Age-restricted sale check | Liquor and wine | the age a buyer must be: 21 |
| Duty-free allowance and boarding pass | Travel retail | the allowance, 4 litres a passenger, and what each bottle counts as |
| Liquor excise returns | Liquor and wine | each item's millilitres and strength |

So you can install one app, press **Refresh**, try it at the till, uninstall it, install another, press **Refresh** again, and keep the same stores, tills and people throughout. A field whose app is not installed is skipped, and Refresh says so in one line. Load and Reset run Refresh too.

If an app that checks every sale is already installed when you load a pack, the pack leaves its past sales out and says so, because a past sale cannot go through a till; Electronics and phones asks you to uninstall the app first. An installed app's check then runs at the till as it would for a retailer. With the duty-free app installed, the till asks for a boarding pass in **Sale details** before it takes payment: [the duty-free recipe](../../recipes/duty_free_allowance.md) says how a pass is read.

An app of your own carries your own field names, which a pack cannot know. Fill those yourself; the departments, items and stock are there for it.

## Travel retail

**Corvane Travel Retail**, an airport chain at New York's JFK: the chain to test a duty-free allowance or an age check on.

| Part | What it holds |
|---|---|
| Company | **Corvane Travel Retail**: US dollars |
| Stores | a duty-free store airside, where nothing is taxed, and a store landside at New York City's 8.875%; a bonded warehouse and a returns room |
| Tills | two airside, one landside |
| Catalogue | 60 items in eight groups, from spirits, wine and tobacco to fragrance, confectionery and travel essentials, with photos |
| Money | euro and sterling cash at the airside tills, with change given in dollars |
| Customers | a walk-in customer and three members of Corvane Rewards |
| History | eight sales in the week before the load |

Its five people (two cashiers, a store manager, a stock officer and an owner) show with their till IDs and passwords when the load ends, and under **Show its logins** afterwards.

With **Duty-free allowance and boarding pass** and **Age-restricted sale check** installed, **Refresh** fills each group's allowance and age and what each item counts as.

Beside another company on the same site, Travel retail leaves the site's own settings alone: the site's default company, clock, number and date formats stay as they are.

## Electronics and phones

**Voltmere Electronics & Mobile**, a US chain that sells phones and laptops by serial number.

| Part | What it holds |
|---|---|
| Company | **Voltmere Electronics & Mobile**: US dollars |
| Stores | Houston, at Texas's 8.25%, and Queens, at New York City's 8.875%; a warehouse in Dallas that takes goods in, and a repairs and returns room |
| Tills | two in each selling store: `Till-1` with a cash drawer, `Term-2` without |
| Catalogue | 54 items, 22 of them tracked by serial number or IMEI: phones, laptops, tablets, TVs, wearables, audio and accessories, protection plans, and a phone-and-plan set |
| Stock | by named serial number: received at the warehouse and moved to the stores by serial |
| Customers | a walk-in customer and four members of VME Rewards, one holding a gift card |
| Orders | four pickup orders waiting, two at each store |
| History | earlier sales, so a return by serial number has a sale to find |

Its six people (a cashier in each store, a store manager, a stock clerk, someone at the repair counter and an owner) show with their till IDs and passwords when the load ends, and under **Show its logins** afterwards.

**Electronics and phones loads only on a sandbox with no other company**, because its pickup and store-to-store orders need two site-wide settings. Choose it instead of Multi-category retail, or **Remove** the other pack first; the screen says so when another company is there.

## More packs

Each of our other industries has a demo chain of its own on its demo site: fashion, grocery, hardware, beauty, liquor, optical, thrift, distribution, hospitality and pharmacy. They are not packs yet. The ten retail industries' departments are in Multi-category retail today. If you need one of those chains as a pack, [ask us](feedback.md#open-a-form): the first ask is what starts it.
