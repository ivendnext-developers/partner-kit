# A rule checked before payment (a check before payment) — the recipe

![A members-only sale refused at Pay, a member's larger sale asking for ID, then paid](../samples/s18_rule_guard/screenshots/s18_flow.gif)

A check before payment is the last word on a sale before money is taken. When the cashier presses **Pay**, the iVendNext POS server prices the basket itself and asks your HTTPS service: allow it, refuse it in your own words, or ask the cashier a yes/no question. Examples: *members-only items*, *a prescription number for pharmacy items*, *ID above a sale amount*. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, building one.

**Reference implementation:** `samples/s18_rule_guard/` — *Members-only rule guard*: it refuses a sale that holds a members-only item for a customer who is not a member, and asks the cashier for ID above the shop's limit.

**When to use it.** Use it for a rule that must hold **when the sale is booked**, whatever the till did. The till's own screens show your sentence; **you ship no screen**. For a rule about the moment an item is scanned (a beep, a yes/no before the line goes on), use a capture on scan instead (`recipes/capture.md`): that one shapes the cashier's flow; this one is enforced by the server at every door that moves money.

**The four rules, here.** Your answer **never moves money**: no price, no line, no payment. It changes nothing in the shop. It is **safe to ask twice** (the same basket gets the same answer). It never decides after money is taken: once a card is charged nothing is refused.

## Steps

1. **Declare it in your manifest** (`recipes/manifest.md`, `guide/07_manifests.md`):

   ```json
   "extension_subscriptions": [{"key": "guard", "point": "check", "label": "Member rule guard",
                                "endpoint_url": "https://your.server/rgd/check", "timeout_seconds": 3,
                                "down_answer": "refuse"}]
   ```

   - `label` is what the cashier reads when your service is down (*"Member rule guard did not answer. …"*).
   - `down_answer`: what the till does when your service is down, slow or answers what it cannot use — `allow_and_flag` (the default: the sale goes on and is flagged on the *Sales to review* report), `refuse` (no sale until you answer), or `ask` (the cashier decides). A rule that must hold even in an outage declares `refuse`.
   - `timeout_seconds`: 3 unless you raise it, 10 at most. At most three checks answer one POS Profile, ten seconds together.
   - The manifest installs it **switched off**. A manager's approval (`may_approve`) is the shop's choice, never the manifest's. The signing secret is handed back **once**, at install.

2. **What the shop does after install.** A System Manager opens your service (*Retail Extension Subscription*), reads what is sent (the consent text lists every field), ticks the consent, chooses the POS Profiles it answers (none = all) and switches it on.

3. **Your service checks every call is the shop's.** One POST per Pay, body `{"point": "check/1", "context": {…}}`, with `X-iVendNext-Timestamp` and `X-iVendNext-Signature` = base64 HMAC-SHA256 of `<timestamp>.<raw body>` with the secret. Check it over the raw bytes before you decide anything, and refuse a timestamp more than five minutes from yours (`samples/s18_rule_guard/rule.py`, `verify`).

4. **Decide from what you are sent.** The context is the **server's** priced basket: each line's item code, item group, quantity in thousandths and money in whole minor units (`currency_exponent` says how many digits), the sale's totals, the customer and their customer group, the coupon codes, the sale details the cashier captured, and the tenders offered. Never the till's own figures, never a card. Since the POS app's train T11 (2026-10-16) it also names the POS day and its terminal (`pos_opening`, `pos_terminal`), so one rule can hold per terminal without a POS Profile per terminal; both are among the fields the shop consents to send, so a consent ticked before the shop's site took that release lapses until the shop ticks it again. Validate against the kit's current copy of the contract: an older copy refuses the two fields.

   ```python
   if not member and any(line["item_code"] in members_only for line in ctx["lines"]):
       return {"verdict": "refuse", "reason": "WINE-RESERVE is for members only. Add the member's customer to the sale first."}
   if ctx["totals"]["grand_minor"] >= round(limit * 10 ** ctx["currency_exponent"]):
       return {"verdict": "ask", "question": "This sale is 5,000.00 AED or more. Has the customer shown ID?"}
   return {"verdict": "allow"}
   ```

   Every sentence is plain text of 1 to 140 characters: no `<` or `>`, no control characters. One bad key or value refuses your **whole** answer, and your down answer applies.

   **Where the shop's rule lives.** The call carries the basket, not your rule, so a service that answers many shops keeps each shop's rule **in that shop**: S18's manifest adds a record type, `PP RGD Rule`, one rule per record (a members-only item, a members-only item group, a member customer group, or the amount at or above which the cashier is asked for ID), and a feed whose *Application User* is the app's integration user. After *Connect again* the service holds that user's key (`user:<email>`) and reads the switched-on records with one call (`GET /api/resource/PP RGD Rule`, every switched-on record, no page limit), **only after the call's signature holds**, and keeps them a minute, so a changed rule applies within a minute (`service/app.py`, `rules_for`; `rule.py`, `rules_of`). A shop that cannot be read is your service down (a 503: the shop's down answer applies); a shop that has not handed over its user yet, or that refuses its key, gets a refusal that says so. A return is judged for the items it sells (lines with a positive `qty_milli`: an exchange rung without its sale) by the members-only rule, with no ID question, never for what it takes back, and a return that sells nothing reads nothing.

5. **What the cashier sees, and what books.**

   | Your answer | The till | The booking |
   |---|---|---|
   | `allow` | the payment sheet opens | books as always |
   | `refuse` + `reason` | *"This sale can't be paid"* and your sentence; back to the basket | **nothing is paid**: the door before any money (the card push; a gift card, store credit or cash at the booking) refuses a sale without an allowing answer for exactly this basket — *"The sale changed after the check. Press Pay again."* |
   | `ask` + `question` | Yes / No; *No* goes back to the basket | paid only after the cashier's Yes |
   | `allow` + `exclude_tenders` + `reason` | those tenders drawn dimmed, *"Not for this sale: …"* | refused for an excluded tender |

   A basket changed after your answer (a line added, a price changed) is refused before money until the cashier presses Pay again, which asks you again. Once a card is charged nothing is refused: the sale books and is flagged.

   On the till: the refusal ![the sale can't be paid](../samples/s18_rule_guard/screenshots/02_this_sale_cant_be_paid.png), the question ![asks for ID](../samples/s18_rule_guard/screenshots/04_asks_for_id.png), and the sale paid after *Yes* ![paid and booked](../samples/s18_rule_guard/screenshots/06_paid_and_booked.png). On the phone: the refusal ![phone: can't be paid](../samples/s18_rule_guard/screenshots/07_phone_this_sale_cant_be_paid.png) and the question ![phone: asks for ID](../samples/s18_rule_guard/screenshots/08_phone_asks_for_id.png).

6. **When your service is down or slow.** The till waits your timeout, then applies your declared down answer. With `refuse` the cashier reads *"⟨label⟩ did not answer. This sale can't be paid until it does. Try again, or get a manager."*; with `allow_and_flag` the sale books and the round is flagged on the *Extension Log*. Offline, the till applies the down answer from its start-of-day snapshot and the sale is flagged when it syncs, never refused.

7. **Test it.** Unit-test your rule and your service on your laptop with calls signed the way the shop signs them (`samples/s18_rule_guard/tests/`), and check every answer against the contract. Then press Pay on a sandbox. The money kit (`recipes/money_kit.md`) rings every basket through your check: an allowed sale must book exactly as without it, and a refused one must book nothing.

## A coupon, and what the check receives for it

A coupon is **configuration**, not something your service owns: the shop makes a *Coupon* record in Desk (or a configuration script makes it over the record API). Your check only reads what the sale carries. Three things a partner who has not seen one would trip on:

- **A coupon is refused until it is set up.** It must list what it applies to (`table_get_items`: an Item, an Item Group or a Brand) or the shop answers *"Coupon is not setup."*; it must name the stores it applies on; and its applicability must hold exactly seven day rows (*"Missing day in Coupon applicability."* otherwise). Set a `trigger_quantity` for the quantity that earns it. An **item group matches exactly**: a parent group, or "all items", does not reach its children, so a coupon for the whole catalogue lists every leaf group.
- ***Apply Once Per Customer* is the product's rule, applied before your check.** A customer who already used the coupon is refused it (*"The coupon is restricted to a single use per customer"*), so no coupon reaches your check and the sale goes on at full price. ⚠ The field is **hidden** on the Coupon form: a shop shows it with *Customize Form*. It counts every coupon row for the customer, a draft or a cancelled sale included. A "first purchase only" rule is not the same: it refuses a customer who has bought anything before, with or without this coupon (sample S32).
- **What `coupon_codes` carries.** For each coupon on the sale, the coupon record's **ID** (its name: the `id` it was created with, which is not the same field as its `coupon_code`; if it has none, its serial number), plus the sale's own `coupon_code` field when set: a sorted list of text, empty when the sale has no coupon. On iVendNext POS the engine always fills the record's name and the till never sets `coupon_code`, so in practice each entry is a coupon's record name (read at the pins of 2026-10-17; S32's bench recorded only names). So compare against the coupon's ID, not against a code a cashier types or a discount rate. ([The check page](../contracts/pages/partner_check.md) lists the field.)

S18's rule does not read coupons. **Sample S32** (*Coupon rules*, [recipe](coupon_rules.md)) does: the shop writes one rule per coupon (first purchase only; only for one customer group) and the check refuses a coupon its rule does not allow.

## What the shop needs from you, and what it checks

| You give | The shop checks |
|---|---|
| an **HTTPS** address its server trusts (a real certificate) | the address is consented; a private address is refused on a customer's site |
| a signature check on every call | — (yours to do) |
| an answer within your timeout | your declared down answer applies otherwise, and one log row is written (no body, no secret) |
| plain sentences of 1 to 140 characters | the whole answer is judged; one bad value refuses all of it |

## Technical notes

### What was proven where

- The coupon section: read in the product at the heads of 2026-10-10 (the value `coupon_codes` carries; the engine's *Coupon is not setup* and single-use rules) and measured on a test shop while building a loyalty service; re-read at the bench's pins of 2026-10-17 (the hidden *Apply Once Per Customer*). Run as a check on our bench by S32 on 2026-10-18 (its recipe).

- **Screenshots** (our test bench, 2026-10-10, the iVendNext POS app `87812e141`, the kit's demo shop *Demo Retail*; frames: the till's counter frame, 1440 wide, light mode, and the phone frame, a 390 × 844 phone viewport): the cashier *Thabo Nkosi* pressed Pay for a walk-in (refused), then for the bench's member *PP SET5 Member* (asked, *Yes*, booked as `ACC-PSINV-2026-08670` on the simulated card); on the phone the same refusal and question. A real browser drove the till; the checks below drove its calls.

Proven on our test bench on 2026-10-08 (iVendNext POS app at `577a8d41`), **22 of 22** checks: install 3, the payment door and the failure cases 18, uninstall 1.

- Install, step 1. **On the bench:** the manifest installed **switched off** — no consent, *May ask for a manager's approval* off, down answer `refuse`, 3 seconds — and the secret was handed back once, as `pp_rgd:sub:guard`. The shop switched it on for one POS Profile; the product then selected it for that profile and no other.
- The till's own payment door, step 5. **On the bench**, as the cashier, over HTTPS (the till's own calls: `check_before_tender`, `confirm_check`, the card push, `submit_tender`):

  | Case | Result |
  |---|---|
  | A walk-in buys the members-only item | the check returns the service's own sentence; the card push for the same sale is refused before any money — *"The sale changed after the check. Press Pay again."*; **0 POS Invoices** (counted before and after) |
  | A member's sale of 300.00 ZAR (the ID limit 250) | the cashier is asked *"This sale is 250.00 ZAR or more. Has the customer shown ID?"*; before the Yes the push is refused and nothing books; after the Yes the push passes and **one** sale books |
  | A member buys the item | allowed; the push passes; it books |
  | What the service received | the server's priced basket, three calls, money in minor units (a 100.00 ZAR sale: `grand_minor` 10000, `tax_minor` 1304); every call holds the published contract (the sample's own test replays them) |

- Down, slow or not a valid answer, step 6. **On the bench**, each case under both declared down answers:

  | Case | Down answer `refuse` | Down answer `allow_and_flag` | The log |
  |---|---|---|---|
  | slower than the deadline (the service waits 5 s) | *"Member rule guard did not answer. This sale can't be paid until it does. Try again, or get a manager."*; the push refused; 0 POS Invoices; **3.1 s** (the deadline, not the service's 5 s) | the sale books; the round flagged | `timeout`, flagged |
  | down (nothing listens) | the same | the same | `unreachable`, flagged |
  | not JSON · a refusal without its reason | the same | the same | `answer refused`, flagged |

  **The canary:** the same slow answer with the deadline lifted for one check comes back as the service's own refusal, not flagged — so it was the deadline that refused it.

- The signature check, step 3: the laptop tests refuse a wrong secret, a changed body and an old timestamp; with the check removed they go RED (a mutation run, 9 of 9 mutants killed).
- **One thing to know about card sales:** the booking itself never refuses a card sale whose check does not hold — the card is charged by then, so the sale books and is flagged on the *Sales to review* report. The refusal is at the card push, before any money moves; that is the door this proof uses. A sale settled first by cash, a gift card or store credit is refused at the booking itself (the product's code; not run on our bench).

### The money kit

The money kit rings every basket through the till's check round when a check is switched on (`tools/moneykit/till.py`: the check, the cashier's Yes to a question, then the card push's own gate). Its label for this sample switches S18 on for the kit's till, so **every** basket meets the check: an allowed or asked sale must book exactly as without it, a member's sale of the probe item books, and a walk-in's is refused and books nothing. Results: **GREEN** on 2026-10-08: every one of the 69 baseline sales booked exactly as the baseline through the check round, the member's sale booked at its price, and the walk-in's was refused and booked nothing. With S18 left switched off, the same walk-in sale booked — the label went RED, as its canary must.
