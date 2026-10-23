# S44 — Lucky draw (`pp_ldw`): entries by spend, and a fair draw of the winners

A shop runs a *shop and win* campaign: every 200 spent at its tills during the campaign is one entry, say, and after the last day the winners are drawn. The shop makes a **campaign** in Desk: its days, its tills, the spend for one entry, the customer groups that take part, how many winners and reserves, and the prize. During the campaign a manager presses **Count entries** to see how it is going. After the last day the manager presses **Draw winners** once: the app draws the winners and reserves from the entries, one prize per customer, each entry with the same chance, and writes the results and a record of the draw on the campaign. This sample is for a developer who wants buttons on a record of the app's own whose service **reads the shop's sales and writes its answer back on that record**.

**When to use it:** a rule the shop keeps decides something from many of its own records (here, a campaign's sales), a person decides when, and the answer belongs on one record the shop can keep and show.

## What happens

1. The campaign's manager (the role **PP LDW Manager**) makes a campaign: *Summer draw 2026*, from 1 to 31 October, 200 for one entry, at most 10 entries a sale, the *Members* customer group, 3 winners, 2 reserves, *a gift card of 500*.
2. Cashiers sell as always. A sale counts when the cashier has added the customer: a sale on a till's walk-in customer is never an entry.
3. **Count entries**, any time: the shop sends your service, signed, the campaign's name. Your service reads, **with its own key**, the campaign, its days' submitted till sales, the returns made against them, every till's walk-in customer and the customer group tree. It writes the count on the campaign and answers: *"412 sales by 297 customers: 1,036 entries so far."*
4. **Draw winners**, after the last day: the service counts again, draws, and writes the results (rank, winner or reserve, customer, their entries, the entry number drawn and the sale that holds it), the draw's record (when, who, the entries, their fingerprint, the numbers drawn) and *Drawn*. *"Drew 3 winners and 2 reserves from 1,036 entries. The results are on the campaign."* The shop fills in each winner's name, mobile and e-mail from its own customer record.
5. The manager calls the winners (a reserve when a winner cannot be reached), hands over the prizes and ticks *Handed over*.

The **Draw winners** button is gone once the campaign is drawn, the form locks its rule, and the app never draws it again.

## What the shop does

1. **Install the app** (the shop's administrator). It comes in switched off: both services have no consent and are off, and both buttons are off. The install adds the campaign record type **PP LDW Campaign** (and its three tables) and makes the roles **PP LDW Manager** and **PP LDW Integration**.
2. **Give the app a user** (as in the [integration user recipe](../../recipes/integration_user.md)): tick **Is Desk User**, set no password and no User Permissions, give it the role **PP LDW Integration** alone, and generate its API key. In **Role Permissions**, give that role these rights (measured on our test bench: the shop refused the app's user each one until it was given):

   | Record type | Right | Why |
   |---|---|---|
   | POS Invoice | Read | the campaign's till sales and their returns: customer, customer group, total, date, time and till |
   | POS Profile | Read | each till's walk-in customer, whose sales are never entries |
   | Customer Group | Read | the group tree, so a group takes the groups below it |

   The app's user reads every till sale on the site, with its customer: give the role to the app's user and no one else. The install gives the role read and write on the campaign itself. A service for one shop takes the key in its settings. A service for many shops receives it from the shop: choose the user as the *Application User* of the feed **PP LDW Draw feed**, then press **Connect again** on the app (*Many shops, hosted* below).
3. **Give the manager role** to whoever runs the campaigns (marketing, the head of stores). In **Role Permissions**, give **PP LDW Manager** *Select* on **Company**, **POS Profile** and **Customer Group**: the campaign form's lookups for them answer nothing to the role alone (measured on our test bench).
4. **Switch the services on** (the System Manager): **Retail Extension Subscription**, the records *Lucky draw count* and *Lucky draw*: read what each is sent, tick the consent, switch it on. Then **Retail Desk Action**, the records *Count entries* and *Draw winners*: switch them on.

**Where it shows.** In Desk: the campaign's list and form, with the two buttons on the form. At the till: nothing new; the cashier adds the customer to the sale as always.

**What leaves the shop.** One address: your service (the manifest ships a test address; you write your own). Each press sends the campaign's name, the pressing user (an e-mail address) and the language. Your service then reads the campaign's sales (each sale's number, customer, customer group, total, date, time and till), their returns, the tills' walk-in customers and the customer group tree, and writes the campaign. It keeps nothing of a press; a hosted copy holds each shop's press secrets and its user's API key from *Connect again* until the shop removes the app. Say so on your card.

## The files

| File | What |
|---|---|
| `manifest.json` | the campaign record type and its three tables (tills, customer groups, results), the two services (`extension_subscriptions`, extension point `desk_action`), the two buttons (`desk_actions`, on the campaign's form; *Draw winners* only while not *Drawn*), the feed whose user is the app's, a help address; installed **switched off** |
| `draw.py` | **the pure core**: the signature check, the press's campaign, the campaign's rule, each sale's entries net of its returns, the group tree, the draw, the fingerprint, the answers |
| `service/app.py` | the HTTP service (standard library): `POST /press/count`, `POST /press/draw`, `GET /health`; the record API as the app's user; one shop or many |
| `tests/test_service.py` | laptop tests: the real service, a stand-in record API, presses signed as the shop signs them |
| `tests/test_rules.py` | the core: entries, money exact, the order, the group tree, the draw's fairness (20,000 draws) and numbering, the fingerprint, the answers |
| `tests/test_many_shops.py` | many shops: each shop's own secret for each button and its own key, a press before *Connect again*, the record type under the library's prefix, the record API's errors, the function entry |
| `tests/test_manifest.py` · `tests/test_contract.py` | the manifest's shape; every answer, and every press our test shop recorded, against the published contract (`desk_action.v1.schema.json`) |
| `tests/canaries.py` | each test that guards a secret, a key, the walk-in customer, a return, the days, tills and groups, a customer winning once, the fairness, a draw never repeated or written over an edit goes RED when its check is removed |
| `app.json` | how CitiXsys hosting runs it: a function, paid per call, packaging only the files it needs |

The recipe is [Lucky draw](../../recipes/lucky_draw.md). The buttons' own recipe is [`recipes/desk_action.md`](../../recipes/desk_action.md).

## Run it

```bash
cd samples/s44_lucky_draw
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/canaries.py
python3 service/app.py service/.env.local      # PP_BASE, PP_KEY, PP_SECRET, PP_COUNT_SECRET, PP_DRAW_SECRET, PP_PORT
```

## Many shops, hosted

The App library's *Lucky draw* runs this same `service/app.py` for every shop that installs it, as a function on CitiXsys hosting (`app.json`): it costs nothing between presses. Set `IVN_LIBRARY_APP` (the library's id), a shops store (`IVN_SHOPS_TABLE` on hosting, `IVN_SHOPS_FILE` on your own server) and `LDW_PREFIX` (`IVENDNEXT LDW`: the record type is then *IVENDNEXT LDW Campaign*).

1. After its install the shop's site connects itself (the app template's handshake, guide chapter 14b): the service stores the shop with its library key and the two presses' secrets, `<app>:sub:count` and `<app>:sub:draw`.
2. The shop chooses its app user on the feed and presses *Connect again*: the service receives that user's key (`user:<email>`).
3. Each press names its shop (`X-iVendNext-Site`); it is checked with **that shop's** secret for **that button**, and the shop is read and written with **that shop's** user's key. Another shop's secret, another button's, or a shop the service does not know, is refused (401).
4. A press before step 2 is answered in words: *Lucky draw is not set up yet.*

## Make it your own

What a partner usually changes:
- **the rule:** entries per item bought or per brand; double entries on some days; entries for Desk sales or web orders too; one entry per customer per day;
- **the prize:** issue each winner a gift card (the shop's own Gift Card, as S25 does) or loyalty points, instead of a prize the shop hands over;
- **instant win:** a sale that wins at the till, at times the shop does not know (a check before payment answering *ask* with the news), on top of the draw;
- **telling the winners:** a message to each winner from your own service after the draw (the shop's own Notification reads only the campaign's own fields, so it cannot send to each result's mobile); or each customer's entries on their receipt (a print format of yours);
- **the prefix:** `tools/manifest/rename.py` makes your copy under your own reserved prefix in one step; the service takes its prefix from `LDW_PREFIX`;
- **its records:** `tools/deploy/copy_records.py` moves campaigns between a test site and the shop.

## Before you copy it

- **A draw is never repeated by the app.** The service reads the campaign first and answers *Already drawn* when it reads *Drawn* or carries any part of a draw's record or results (a status set back to *Open* by hand does not open a second draw); the button also shows only while it is not drawn, and the shop checks that again at the press. The manager role cannot delete a campaign. A person with write on campaigns can still add or remove a result row in the form, or change a drawn campaign through the API, and a System Manager can delete one and draw again; the campaign's history (its version log) shows every such change. Give the manager role only to people you trust.
- **An edit is never overwritten.** The write carries the campaign's `modified` as read; the shop refuses a stale write (`TimestampMismatchError`), and the answer asks for another press. Two presses of *Draw winners* at once: one writes, the other is refused.
- **A count after the draw** writes the counts only: the draw's record and the results stay as drawn.
- **The random source** is the service's own (`secrets.randbelow`), never a seed anyone chose. Keep it so in your copy, and keep the record: the entries' fingerprint and the numbers drawn let anyone holding the sales check which sale each drawn number is.
- **The shop's own words never reach the user.** The service branches on the error's type (`exc_type`), never shows its message.
- **Removing the app removes its campaigns** (they are the app's own records). Export a drawn campaign first if you need to keep it.
- **Test routes.** Delete `/test/received` from your copy.
- **Your address.** Write your own address in `allowed_urls`. The shop's server must trust your certificate: a real one for a shop.

## Technical notes

### Why it is built this way

| Option | Cost | Verdict |
|---|---|---|
| Do nothing: a report of the campaign's sales, then a spreadsheet and a hand-picked name | 0 | no entries per spend, returns missed, walk-in sales mixed in, and a draw nobody can check |
| A manifest only: the campaign record and a Report Builder report of its sales | ~½ day | shows the sales; a report computes no entries per sale, and the draw is still by hand |
| **Two Desk buttons on the campaign, answered by a press-only service** | ~1½ days | **picked**: entries by the shop's rule, returns netted, one fair recorded draw that cannot be drawn twice; S38's service shape and S40's table write reused |
| A service on the event feed writing each sale's entries as it books | a server that stays up | an entry number at the sale; a monthly cost for a campaign a shop runs twice a year, and the draw is the same |

### Entries, exactly

- **A sale** is a submitted POS Invoice of the campaign's company, dated inside the campaign's days, on one of its tills (every till when none is listed), by a named customer (never a till's walk-in customer, read from each POS Profile), in one of its customer groups or a group below one (every customer when none is listed). The group is the one the sale recorded, as it was at the sale.
- **Its entries** are its total in the company's currency as the customer paid it (`base_rounded_total`, or `base_grand_total` when the shop does not round), less every submitted till return made against it so far, divided by the spend for one entry, rounded down, at most the campaign's *most entries per sale*. The arithmetic is exact (decimal, never a float).
- **The numbering**: entries are numbered 1, 2, 3 … through the sales in order of date, time and number. The fingerprint is the SHA-256 of the list, one `sale<TAB>customer<TAB>entries` line each.
- **The draw** picks one entry of those still in the pool, each with the same chance; that entry's customer takes the place, and all their entries leave the pool; then the next place. Winners first, then reserves.

### Bounds, stated

- **Till sales only.** Desk sales (Sales Invoice) and web orders do not count.
- **The campaign's last day** ends at midnight by the campaign's *hours from UTC*; the draw is refused before. Draw once every till has sent its sales: a till that was offline sends its last day's sales when it reconnects, and a sale that arrives after the draw is not in it.
- **One press reads the whole campaign** in one read of its sales. On our test bench the shop answered that read for 12,157 sales (2.7 MB) in under a fifth of a second, to a service beside it; a hosted service reads across the internet, which was not measured at that size. A press stops reading after 7 seconds and then writes nothing (the shop's words: *did not answer in time*): split a campaign that large into more than one, by till.
- **Every till sale counts**, a gift card sold or a sale paid by gift card or points included: the rule is the spend.
- **The campaign's hours from UTC:** blank reads as UTC, so a shop west of UTC that leaves it blank can draw before its last day has ended there; set it, and change it when the clocks change.
- **A slow shop:** *did not answer in time* can come after the draw's write has landed; open the campaign before you press again (a second press finds it drawn).
- **Where it runs:** the App library's copy runs in CitiXsys hosting's US region.
- **The law.** A draw for customers may need a permit where you sell (a promotion permit in the UAE, for example), and some countries require a free way to enter; both are the shop's. The app counts sales only.
- **Returns** are the till's returns made against the sale. A credit note made in Desk against the day's closing invoice does not take entries off.
- **A customer's own entries** are not shown at the till or on the receipt; a count gives the totals.
- **Removing the app** removes its campaigns.
