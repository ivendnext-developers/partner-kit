# S46 — Payment method rules (`pp_pmr`): which payment methods each customer group may use

The shop decides which payment methods each group of its customers may use at the till: customers who order through a delivery platform pay only by that platform's method, only account customers may buy on account, a group that settles in dollars pays only in dollars. When the cashier presses **Pay**, the app leaves every other method off that sale's payment screen, dimmed, with the shop's reason beside it.

**When to use it:** a rule about the sale's customer decides which payment methods the till may take, and the shop keeps the rule itself, in Desk.

## What happens

| When | What the cashier sees |
|---|---|
| A sale for a customer whose group's rule leaves methods out | The payment screen opens with those methods dimmed: *"Not for this sale: Talabat customers pay with Talabat."* The cashier takes one that is not |
| A rule that leaves out every method this till offers | *"This sale can't be paid"* and *"Customers in Talabat can't pay at this till: use one with Talabat."* |
| No rule for the customer's group, or for any group above it | The payment screen opens as always |
| A refund, the returned items of an exchange, a return rung without its sale | Not judged: the refund choices open as always |
| An exchange's new items | Judged as a sale. An exchange pays them with store credit: an *Only these* rule that does not list the store-credit method stops that group's exchanges |
| The service down, or the shop's records unreadable | The check's down answer: the sale goes on with every method and is flagged on *Sales to review* |

**Which rule decides.** One rule per customer group, either *Only these payment methods* or *Every payment method but these*. A customer takes their own group's rule; a group with no rule takes the rule of the nearest group above it in the shop's customer group tree. A group's own rule replaces the rule above it entirely: a method the rule above leaves out comes back unless the group's own rule leaves it out too. So two rules cover on-account credit for account customers only:

| Customer group | Rule | Methods |
|---|---|---|
| All Customer Groups | Every payment method but these | On Account |
| Account customers | Only these payment methods | Cash, Credit Card, On Account |

A customer in *Retail* (under *All Customer Groups*) cannot buy on account; a customer in *Account customers*, or a group below it, can.

## What the shop does

1. **Install the app** from the App library (or paste its manifest into **Retail Extension Package** in Desk), read what it will do and consent. The install adds the record type *PP PMR Rule*, the role `PP PMR Integration`, the check and the feed registration, the check switched off. Nothing changes at the till yet.
2. **Make the app's integration user** (the [integration user recipe](../../recipes/integration_user.md)): tick *Is Desk User*, give it the role **PP PMR Integration** alone and generate its API key. In *Role Permissions*, give that role **read on Customer Group** (the service reads the group tree). Choose the user on the feed registration **PP PMR Rules feed**, then press **Connect again** on the app's record, which sends that user's key to the service.
3. **Write the rules** in *PP PMR Rule*: one per customer group that needs one. The payment methods are the shop's own *Mode of Payment* records, as the till offers them (*Cash*, *Credit Card*, *On Account*). *Words the cashier reads* is optional: blank, the app writes *"Customers in ⟨group⟩ pay with ⟨methods⟩."* or *"Not for customers in ⟨group⟩."*
4. **Switch the check on:** open *Payment method rules* in *Retail Extension Subscription*, read what is sent, tick the consent, choose the POS Profiles, and switch it on.

**Where it shows.** The rules are Desk records the shop keeps (its System Manager, or a role the shop gives the rights to in *Role Permissions*: that role also needs *Select* on **Customer Group** and **Mode of Payment**, or the rule's lookups answer nothing). At the till the cashier meets them at **Pay**: the methods left out are dimmed with the rule's words.

**What leaves the shop.** At **Pay**, and before each refund the till pays, the priced basket goes to the service's address: each line's item, group, quantity and amounts, the totals, the store, till, POS day and terminal, the cashier's user, the customer and their customer group, the coupons, the sale details the cashier captured and the payment methods offered; never a card. The service reads the shop's rule records and its customer group tree with the integration user's key, keeps them one minute, and keeps nothing of a sale. It writes nothing. A hosted copy holds each shop's check secret and its user's API key from *Connect again* until the shop removes the app. Say so on your card.

## The files

| File | What it is |
|---|---|
| `manifest.json` | the record type `PP PMR Rule` (one per customer group, named by it) and its table `PP PMR Rule Method`, a feed registration (it names the app's one integration user), a help address, and one `check`, installed switched off; when the service is down the sale goes on, flagged |
| `payrules.py` | the pure core: the signature check (`verify`), the shape check, the shop's rules (`rules_of`) and tree (`tree_of`), the rule that decides (`deciding`) and the answer (`on_check`) |
| `service/app.py` | the service, standard library only: `POST /pmr/check`, `GET /health`, and the app template's handshake for many shops; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the rules, the service over the wire with signed calls (one shop and many), the shop's reads against a stand-in shop, every answer against the published contract, the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s46_payment_method_rules/tests -p 'test_*.py'
```
```bash
python3 samples/s46_payment_method_rules/tests/canaries.py
```
```bash
python3 samples/s46_payment_method_rules/service/app.py samples/s46_payment_method_rules/service/.env.local
```

**Settings, one shop** (`service/.env.local`, never committed): `IVN_CHECK_SECRET` (handed back at install as `pp_pmr:sub:methods`), `IVN_SHOP_URL`, `IVN_SHOP_KEY` (`<api key>:<api secret>` of the integration user), `PORT`. `PMR_PREFIX` names the rule record type (default `PP PMR`).

## Many shops, hosted

The service is the [app template](../../tools/app_template/README.md)'s shape: set `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`). Each shop connects itself after its install and hands over the check's secret; *Connect again* hands over its integration user's key. Until the key arrives the service answers 503 and the down answer applies. Every call names its shop (`X-iVendNext-Site`), and each shop is answered from its own rules with its own key.

## Make it your own

What a partner usually changes:
- **the rule's reach:** a rule per POS Profile or per terminal (the check sends `pos_profile` and `pos_terminal`), or per customer, from a field you add to Customer;
- **amounts:** cash up to a limit, a card above one, on account up to the customer's credit left (read it with the integration user);
- **refunds:** a refund only to the methods that paid the sale (the check sends `return_of.paid_by` on a return); keep store credit open, or every exchange is refused;
- **the prefix:** `tools/manifest/rename.py` makes your copy under your own reserved prefix in one step; the service takes its prefix from `PMR_PREFIX`;
- **its records:** `tools/deploy/copy_records.py` moves the rules between a test site and the shop.

## Before you copy it

- **The first card method.** A card terminal cannot tell a credit card from a debit card before it charges: leaving out the store's **first** card method stops card payments at the till (the check page's warning). Leave out another card method only if the cashier picks it by hand.
- **Nothing left to pay with refuses the sale.** A rule that leaves out every method the till offers answers *refuse* with words that say why; so does a rule that would leave out more than the contract's 20 methods. Never send part of the list: a method left off the list would be taken.
- **Down means every method.** The manifest declares `allow_and_flag`: an outage never stops a shop selling, and a sale the rules could not judge is flagged on *Sales to review*. A shop that must never take a method its rule leaves out (on-account credit, say) sets the check's down answer to `refuse`; every sale then waits on the service. A refused key (401 or 403) is the shop unreadable too, never an allow without the flag.
- **A rule changed in Desk, or a new customer group,** reaches the service within a minute (it keeps the rules and the tree that long): until then a new group's customers keep every method.
- **A new key.** A key withdrawn or a user disabled (401 or 403) is the shop unreadable: every sale goes to the down answer until the user is switched back on or given a new key, and *Connect again* sends it. The log names it `KeyRefused`, apart from an outage.
- **Exchanges.** An exchange's new items are checked as a sale, and an exchange pays them with store credit: an *Only these* rule that does not list your store-credit method (such as *Store Credit*) stops that group's exchanges.
- **Your address.** Write your own address in `allowed_urls`. The shop's server must trust your certificate: a real one for a shop.

## Technical notes

### Why it is built this way

| Option | Cost | Verdict |
|---|---|---|
| Do nothing: one POS Profile per kind of customer, each with its own methods | 0 | a delivery platform's customers need their own till, and an account customer at an ordinary till is still offered *On account* |
| A manifest only: a field on Customer Group naming its methods | ~½ day | nothing reads it at the till; a manifest cannot answer a check |
| **A check before payment, answered by a function that leaves methods out** | ~1 day | **picked**: the rule holds at every door that takes money, on every till the shop switches it on for, in the shop's own words; S32's service shape and S44's group-tree walk reused |

### The answer, exactly

- **The reads:** `GET /api/resource/<prefix> Rule` with `fields` `["name","customer_group","kind","words","methods.mode_of_payment"]` (one row per method), `filters` `[["enabled","=",1]]`, `limit_page_length` 0; and `GET /api/resource/Customer Group` with `["name","lft","rgt"]`. Both at once (each read has its own timeout inside the check's 3 s), kept a minute per shop and per key. Either one failing answers 503: never a decision on half the shop's rules.
- **The rule that decides** is the customer's own group's, else the innermost group whose span (`lft`, `rgt`) holds the group's and that has a switched-on rule. A customer with no group takes the outermost group's rule. A group the tree does not know keeps every method unless it has its own rule.
- **The methods left out** are the offered methods (`offered_tenders`, the till's own order, each once) the rule does not allow: under *Only these*, every offered method not listed; under *Every method but these*, the listed ones offered. None: `allow`. All of them, or more than 20: `refuse` in words.
- **The words** are the rule's own (up to 120 characters), else the app's; every sentence is plain text of 1 to 140 characters.

### Bounds, stated

- **A sale only.** A refund, a return against a sale, the returned items of an exchange and a return without its sale (`stage: "return"`) are allowed without reading the shop, a return without its sale that also sells included (the contract would judge its sold lines). An exchange's replacement basket is `stage: "sale"` and is judged.
- **Methods together.** The check answers before the cashier picks a method, so a rule cannot say *these two not in one sale*.
- **A rule per customer group.** A customer's own rule is a group of their own.
- **Offline,** the till does not call the service: the down answer applies and the sale is flagged when it syncs.
- **Where the check never runs:** a park to a till, a layaway deposit, an account collection (the check page, *Not in this version*) and the Desk's own POS screen.
- **Three checks a POS Profile.** At most three checks answer one POS Profile, ten seconds together; this one asks for 3.
- **Where it runs:** the App library's copy runs in CitiXsys hosting's US region. On CitiXsys hosting the first Pay after a quiet spell starts the function; past 3 s the down answer applies, flagged.
- It logs one line per call: the route, the status and the milliseconds, never the body.
