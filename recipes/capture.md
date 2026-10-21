# A value captured at the scan, and a code before a new customer (capture) — the recipe

![A warranty reference captured at the scan, and a one-time code before a new customer](../samples/s20_capture/screenshots/s20_flow.gif)

A capture asks your HTTPS service at a moment the cashier did not choose, at one of four events:

- **On scan** of an item your filter names (its item group, or an item field that is set), **before** its line goes on the sale: you can let it on, put a value on the line (a warranty reference, a registration number), ask a yes/no question, or refuse it.
- **On customer add**, **before** a new customer is created: you can allow it, refuse it, or **challenge** — you send the customer a one-time code and the till shows a code field. The customer is created only after you say the code is right.
- **On customer select** (POS app from train T11, 2026-10-16), when the cashier puts an **existing** customer on the sale: allow, refuse (the customer is taken off the sale), or challenge with a one-time code, as on customer add (step 5b).
- **On a quantity change** (POS build 2.0.0.654 on), when the quantity of a line your filter names changes: allow, confirm, refuse (the last allowed quantity goes back), or put a value on the line (step 5c).

From POS build 2.0.0.654 any of them may also answer with a **notice**: the sale goes on with no tap, and your sentence shows (step 6b).

This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, building one.

**Reference implementation:** `samples/s20_capture/` — *Warranty capture and a member code*: a warranty reference on every handset line, and a code by text message before a member is added.

**When to use it.** On scan you **shape the cashier's flow**; you are not a booking gate (for a rule that must hold when the sale is booked, use a check before payment, `recipes/rule_guard.md`). On customer add the **server is the gate** on the till's own doors: no customer is created there until it has recorded your answer for that cashier, that name and that phone. Two exceptions, both flagged on the *Sales to review* report and never refused, because the customer has already paid: a customer added offline is created when the sale syncs, and the receipt's *add a contact* after a walk-in sale (one customer per paid sale) is created too. A customer made in iVendNext Desk or through another API is outside the gate. A rule that must never let a barred number in needs your own reconciliation as well.

**The four rules, here.** **No answer writes a customer field**, and none moves money: no price, total or tender is sent, and nothing you answer changes one. A value you put on a line is annotation. A failed capture **never fails the scan**.

## Steps

1. **Declare one service per event in your manifest**, each at its own address: the address then tells your service which secret to check the signature with, before it reads the body.

   ```json
   "extension_subscriptions": [
     {"key": "on_scan", "point": "capture", "label": "Warranty capture", "endpoint_url": "https://your.server/cap/scan",
      "timeout_seconds": 1.5, "down_answer": "allow_and_flag", "settings": {"event": "scan", "item_groups": ["iPhone", "iPad"]}},
     {"key": "on_customer", "point": "capture", "label": "Member code", "endpoint_url": "https://your.server/cap/customer",
      "timeout_seconds": 3, "down_answer": "refuse", "settings": {"event": "customer_add"}}]
   ```

   - On scan: `item_groups` (at most 50; a group names every group below it) and/or `item_field` (an Item field that is set); 1.5 seconds unless raised, 3 at most.
   - On customer add: 3 seconds unless raised, 10 at most.
   - `down_answer`: `allow_and_flag` (the default: the scan goes on, or the customer may be created, and the log row is flagged) or `refuse`.
   - Both install **switched off**; each signing secret is handed back **once**.

2. **What the shop does after install.** A System Manager reads what each service is sent, ticks the consent, chooses the POS Profiles and switches it on. For a value on the line, the shop keeps an **active line attribute** (*Transaction Item Attribute*) and tells you its name.

3. **Check every call is the shop's** — the same signature as every extension point (base64 HMAC-SHA256 of `<timestamp>.<raw body>`), with **each subscription's own secret**, over the raw bytes, before you parse anything (`samples/s20_capture/service/app.py`).

4. **On scan: answer from the scan's own values.** You receive the line's item code, item group, quantity in thousandths, unit, batch, serial and the code scanned — **and no line id**: the line does not exist until your answer lets it on. Two units of one model scanned by their item barcode look the same, so S20 makes a new reference for every scan. A value for the line:

   ```json
   {"verdict": "allow", "line_attributes": [{"name": "Warranty ref", "value": "WR-3F9A0C21B7"}]}
   ```

   The cashier sees it on a confirm sheet first; on *Add with these details* it lands on that line, which is then its own line (a later scan of the same item never merges into it).

5. **On customer add: refuse, allow or challenge.**

   ```json
   {"verdict": "challenge", "prompt": "Ask the customer for the 6-digit code we just sent.", "length": 6}
   ```

   Keep the code against `context.challenge_id` and send it to the customer through your own gateway (S20's sample writes it to a file; your service calls its SMS or WhatsApp provider). The till sends what the customer reads out as `{"event": "verify", "challenge_id": …, "code": …}`; you answer `{"verdict": "ok"}` or `{"verdict": "refuse", "reason": "That code is not right."}`. **The product counts the tries**: three wrong codes end the check, and a challenge lives ten minutes. Keep your codes for at most ten minutes too.

5b. **On customer select: the same three answers, and the server holds the payment.** Declare a third service with `"settings": {"event": "customer_select"}` (3 seconds unless raised, 10 at most). You are sent the cashier, the store and POS Profile, and the customer's id, name, phone, email and customer group; no price, total or tender. `{"verdict": "refuse", "reason": "This customer buys at the Sandton store only."}` shows your sentence and takes the customer off the sale, which goes on without one or with another. While a select service is switched on, **every door that charges or books the sale refuses until the server has recorded your *allow*, or a checked code, for that cashier, that customer, that POS Profile and your service**; the booking spends it, so one check pays one sale. You are never asked about the store's walk-in customer, nor about a customer this cashier added in the last ten minutes while a customer-add service is on. A payment pressed before your answer arrives is refused with *"This customer has not been checked. Pick them again, or sell without a customer."* Offline you are not asked: the declared down answer applies, and a sale paid offline with a customer you were not asked about is flagged when it syncs. One cashier sends you at most 60 select rounds in ten minutes. The product's [capture page](../contracts/pages/partner_capture.md) has the request, the answers and every sentence.

5c. **On a quantity change: judge the new quantity** (POS build 2.0.0.654 on). Declare a service with `"settings": {"event": "qty_change", "item_groups": ["iPad"]}` (the scan's filter and rules, and a group sold without serial numbers or lots: those lines are never asked; 1.5 seconds unless raised, 3 at most). A burst of presses is asked **once, 600 ms after the last**, with the final quantity. You are sent the till's own id for the line (`line.line_ref`, stable while the sale stays on the till), its last allowed quantity (`qty_milli_answered`) and the new one (`qty_milli`), in thousandths; judge the new one:

   ```json
   {"verdict": "confirm", "question": "4 of iPad Air 64GB on one line. Has a manager agreed to more than 3?"}
   ```

   *allow* keeps the new quantity (values may go on the line, never on the sale); *confirm* beeps and asks; *refuse* shows your sentence. A refusal or a *No* puts back the **last allowed** quantity, never the one just before the change. Pay, Hold, Save as quote, a layaway plan, an order and an exchange's settle each ask any line not yet allowed first, and wait. **Never asked (version 1):** a serial- or lot-tracked line, a return's quantities, an order's change, an offer's companion item, a weighed line, a set, a gift card. A held, parked or converted sale comes back rebuilt, each line at the quantity it arrives with. Offline, or when your answer never comes, the declared down answer applies; with `allow_and_flag` the change is flagged when the sale is paid online or synced. S20's *Handset count* is a worked service (`capture.on_qty`, on *iPad*): up to three on a line allowed, four or five asked about, more refused.

6. **What the cashier sees.**

   | Your answer | The till |
   |---|---|
   | scan · `allow` with values | a confirm sheet, then the item with your value on its line |
   | scan · `confirm` + `question` | a beep and the question; *No* leaves the item off |
   | scan · `refuse` + `reason` | *"This item can't be added"* and your sentence |
   | customer · `refuse` + `reason` | *"This customer can't be added"* and your sentence |
   | customer · `challenge` | a code field with your prompt; a wrong code: your reason and *"⟨n⟩ tries left."* |
   | a create without your recorded answer | refused by the server: *"Check the customer's code first."* — the till then asks you |
   | quantity change · `confirm` + `question` | a beep and the question; *No* puts back the last allowed quantity |
   | quantity change · `refuse` + `reason` | your sentence, and the last allowed quantity back on the line |
   | scan · `notice` + `message` | the item goes on; *"⟨label⟩: your sentence"* shows for 8 s (POS build 2.0.0.654 on) |

   On the till: the scan's confirmation ![warranty capture](../samples/s20_capture/screenshots/01_warranty_capture_sheet.png) and the line carrying the reference ![the line](../samples/s20_capture/screenshots/02_the_line_carries_the_reference.png); the code sheet for a new customer ![member code](../samples/s20_capture/screenshots/03_member_code_sheet.png), a wrong code ![wrong code](../samples/s20_capture/screenshots/04_a_wrong_code.png), and the customer created after the right one ![customer created](../samples/s20_capture/screenshots/05_customer_created_and_attached.png). On the phone: the capture sheet ![phone: warranty capture](../samples/s20_capture/screenshots/06_phone_warranty_capture_sheet.png) and the customer attached ![phone: customer attached](../samples/s20_capture/screenshots/07_phone_customer_attached.png).

6b. **Warn without stopping: `notice`** (POS build 2.0.0.654 on). `{"verdict": "notice", "message": "MILK-1: sell batch B-1102 first. It expires 2026-11-02."}` is *allow* plus a sentence: the item goes on (or the customer is created, or stays on the sale, or the quantity stands) with no tap, and the till shows *"⟨label⟩: your sentence"* below its own warnings for 8 seconds; under the camera, in the run's pause with *Got it*. Use it for what the cashier should know but need not answer: a shorter-dated batch in stock, points about to expire, a promotion one unit away. Something that must stop the cashier, such as a recall, is a *confirm* or a *refuse*. Bounds: the till's own warning wins over your notice, in either order; a second notice replaces the first; the camera's pause names your label, not the item, so name the item in your sentence; the sentence is never logged. A notice is never a down answer, and offline you are not asked. **An older build refuses `notice`** as an unknown answer and applies your down answer (with `refuse` declared, the item is blocked): don't send it to a shop before build 2.0.0.654. S23's *Warn of a shorter-dated batch* is a worked service ([`samples/s23_till_guard`](../samples/s23_till_guard/README.md)).

7. **When your service is down or slow.** On scan, `allow_and_flag` lets the line on and flags it; `refuse` keeps the item off. On customer add, `refuse` reads *"⟨label⟩ did not answer. The customer can't be added until it does."* The scan never fails because of you: a capture that cannot run applies your declared answer.

8. **Test it.** Unit-test the core and the service with calls signed the way the shop signs them (`samples/s20_capture/tests/`), and check every answer against the contract. Then scan and add a customer on a sandbox.

## Technical notes

### What was proven where

- **Screenshots** (our test bench, 2026-10-10, the iVendNext POS app `87812e141`, the kit's demo shop *Demo Retail*; frames: the till's counter frame, 1440 wide, light mode, and the phone frame, a 390 × 844 phone viewport): the bench's handset item scanned; a new customer (*Nandi Zungu*, a made-up phone number) asked for the code the sample's stand-in gateway had sent, a wrong code first, then the right one (typed from the stand-in's file; it is in no picture). A real browser drove the till; the checks below drove its calls.

Proven on our test bench on 2026-10-08 (iVendNext POS app at `577a8d41`), **16 of 16** checks, over HTTPS, through the till's own calls as the cashier (`api.mpos_cart.scan`, `api.capture.customer_add`, `api.capture.verify`, `api.customer.quick_create`):

| Case | Result |
|---|---|
| Install | two services **switched off**, one per event; each secret handed back once |
| A handset of the named groups scanned | the service's reference lands as a value of the shop's attribute (`{"transaction_item_attribute": "Warranty ref", "attribute_value": "WR-CED7D457F2"}`) — the product hands it to the till in that shape |
| An item outside the groups | nobody is called, no log row |
| The service down · the capture itself failing | the scan still finds the item and the line goes on, flagged (`allow_and_flag`) |
| A new customer without a phone · with a barred phone | refused in the service's words |
| A new phone | challenged: *"Ask the customer for the 6-digit code we just sent."*, a code sent to that phone |
| A wrong code | refused, *two tries left* |
| The create before the right code | refused by the server: *"Check the customer's code first."* — no customer |
| The right code | *ok*, with the create's token |
| That token offered for **another name** | refused — no customer of that name |
| The create with the token | the customer is created, name and phone as typed |
| The same phone again | challenged again (no phone skips the code) |
| Three wrong codes | the check ends; even the right code is then refused (*"This code check has ended. Add the customer again."*) |

The captured reference on a **booked** sale: the money kit's label for this sample. Results: **GREEN** on 2026-10-08: the booked line carries the service's reference; every other sale as the baseline. With S20 left off, the line carries none and the label goes RED.

Not run here: a quantity change or a notice on a till (both walked by the product at POS train T12, counter, phone and tablet frames; S20's quantity service and S23's notice run in their laptop tests); a customer added offline (created at sync, flagged) and the receipt's contact after payment; a *confirm* or *refuse* on scan; the camera's pause.
