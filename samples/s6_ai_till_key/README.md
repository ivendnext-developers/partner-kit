# S6 — the AI till key: a short hint from the customer's own AI model

![The AI tip key pressed on a real till, the hint in the till's own sheet](screenshots/s6_flow.gif)

*A cashier presses **AI tip** on a sale, and a short hint comes back in the till's own sheet; then the key's record in Desk.*

A remote till key. The till calls this small service during a sale; the service builds a prompt from the sale's item codes, quantities and the store name, asks **a provider the customer configures**, and answers a **message only**. It is for a developer who wants to add a key to the till that is answered by their own service — here, a hint from an AI model the customer chooses and pays for. The recipe is [`recipes/ai_till_key.md`](../../recipes/ai_till_key.md).

**When to use it:** the cashier needs an answer, during the sale, that only your service can give.

**Door:** Till key

## What it looks like

The hint comes from the sample's stand-in AI service (no real AI model), and it names the sample's own test item.

| Step | Frame | Screenshot |
|---|---|---|
| 1. A sale on the till, with the **AI tip** key among the store's keys | the till, 1440 wide | ![](screenshots/01_till_ai_tip_key.png) |
| 2. Pressed: the hint, in the till's own sheet (the till draws it; the service sends only words) | the till | ![](screenshots/02_hint_in_the_tills_sheet.png) |
| 3. The key's record in Desk: enabled, message only (cut above the partner's HTTPS address and the signing secret) | Desk | ![](screenshots/03_the_key_in_desk.png) |

## What the retailer does

A retailer that wants an AI hint key at its till does this, in the order it meets it:

1. **Choose the AI model.** The retailer uses a provider it already has or pays for: a model on its own machine, or the assistant it already pays for. The sample also ships a stand-in that needs no account. Whoever runs the service sets that provider and a signing secret in the service's settings and puts the service behind **HTTPS**.
2. **Register the key in Desk.** A System Manager adds a **Retail Remote App Key** record: the partner's name, an app name, the key, its label (here *AI tip*), *message* as the only thing it may return, the service's HTTPS address (`…/point/ai_tip`), the signing secret both sides hold, and the time to answer (3 seconds unless raised, at most 10 on this record). The same System Manager ticks **the customer's consent**, pastes the consent text the sample prints (it lists what is sent) and ticks the key enabled.
3. **Switch it on in the store.** In Desk, **POS Studio**, open the theme, **Apps** tab, tick the key and **Save**. Every till whose profile wears that theme shows the key.
4. **Press it.** The cashier presses **AI tip** on a sale and the hint comes back in the till's own sheet. If the service is slow or down, the cashier reads the till's own sentence and the sale goes on with nothing added.

**Where it shows.** At the till: the **AI tip** key among the store's keys, and the hint in the till's own sheet (its title is the key's label; the service's message is titled *Suggestion*). In Desk: the key's record. In POS Studio: the key, under **Apps**. The key works online only, and never changes a price, a total, a payment or stock. No report or print layout.

**What leaves the retailer's iVendNext.** The sample has no manifest and no integration user: it is a service the till calls, and it holds no key to iVendNext and writes nothing there. Two hops leave the retailer's iVendNext:
- each press makes the till's server send the service the sale's context: the item codes, quantities and units, the store, the customer on the sale and the cashier, the sale's reference, the register's profile, the company and the currency. No prices, totals or payment details;
- the service forwards only the item codes with quantities and the store's name to the AI provider the retailer configured. The customer, the cashier and everything else stop at the service.

## The files

| File | What |
|---|---|
| `core.py` | the pure core: `SENT_FIELDS` (the one list of what is sent), `consent_text()`, `build_prompt()`, `message_from()` |
| `providers.py` | `stub` (no network, no account) and `chat` (any chat-completions service the customer runs or pays for) |
| `service.py` | the HTTP service (standard library): signature check, size cap, one route `POST /point/ai_tip`, a log with no secret and no prompt |
| `stub_provider.py` | a local stand-in AI service for the sample and its tests (markers make it slow or failing) |
| — | start the service and the stub provider on your server, under your own process manager |
| `tests/` | `test_core.py`, `test_service.py` (on a laptop, no account needed) |

## Run it

```bash
python3 -m unittest discover -s samples/s6_ai_till_key/tests -v
```

## What is refused, and why

The service refuses a call whose signature does not check, and a call larger than its size cap: only the retailer may ask it, and only for a small answer. It sends the AI provider only what `SENT_FIELDS` lists. Its log keeps no secret and no prompt.

## Technical notes

### The walk

The GIF: after a cashier presses **AI tip** on a sale (the key is shown in still 1; every GIF frame is cut above the key row), the till's server calls this service over HTTPS, and the hint comes back in the till's own sheet. Then the key's record in Desk (our bench run saved it, consent ticked, as a System Manager does there). Frames: the till (`/pos?frame=terminal`, 1440 wide), then Desk. Walked on our test bench on 2026-10-10, iVendNext POS app at `87812e141`. Built from the same screens as the stills below; every frame is cut above the record's address and signing secret.

The stills: walked in a real browser on our test bench, 2026-10-10, iVendNext POS app at `87812e141`: a press of this key from a real till through the released Retail Remote App Key, the till's server calling the service over HTTPS (the first such press was on 2026-10-07; `recipes/ai_till_key.md`, *What was proven where*). The sheet's title is the key's label, *AI tip*; the service's message is titled *Suggestion*. The cashier is the bench's *Thabo Nkosi*, the customer *Naledi Khumalo*; the hint is the stub provider's (no real AI model), and it names the sample's own test item.

### The tests and the ports

Our test bench runs the service and the stub provider on ports 8126 and 8127. Beside the laptop tests (`test_core.py`, `test_service.py`, no account), our test bench has its own run, with the till's real validator; it is not in the kit.

### Why this way (R6)

*Pure core + a tiny service, provider behind one function* (picked: ~240 lines in all; a developer reads it unaided; the same shape as S1) · *a provider SDK* (rejected: ties the sample to one vendor and adds an install) · *the model call inside the retailer's iVendNext as a hosted key* (rejected: partner Python in the tenant, and no deadline on the call).
