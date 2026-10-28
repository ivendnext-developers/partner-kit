# The needs catalogue

One short card per thing a retailer asks for, in the retailer's own words. Each card says whether you can build it today, by which door, which recipe and sample to start from, the limits to tell the customer, and a sentence for the proposal. Start here when a customer sends a list of needs; the recipes and samples are how you build each one.

On the partner site the catalogue is the *Needs* page: an A to Z list of what customers ask for, the newest cards (*New and changed*), the same cards by area (grouped by topic), by door and by verdict, one page per card, and a catalogue.json file for assistants. The search box in every page's header finds a card by the customer's own words, a one-letter slip or a word the customer uses for the same thing (`site/synonyms.txt`: "branch" finds "store"); a word customers use that no card or group carries belongs in that file. The site builds all of it, and chapter 16's two lists, from these cards when it is built; nothing generated is committed. At a terminal, or for an assistant:

```bash
python3 tools/needs/needs.py search price list from another     # the cards whose words match, best first
python3 tools/needs/needs.py show member-price-by-tier          # one card
python3 tools/needs/needs.py blueprint line-quantity-cap reason-codes   # the rows for kit/blueprint_template.md section (b)
python3 tools/needs/needs.py check                              # every card against the rules; CI runs it
```

## The verdict, in four words

| Status | Shown as | Meaning |
|---|---|---|
| `ready` | **Ready** | build it today; nothing to caveat |
| `ready-with-limits` | **Ready, with limits** | build it today, and tell the customer the limits the card lists |
| `not-yet` | **Not yet** | needs a new extension point (the card names the request) or product work on our side (the card says what to ask us) |
| `not-possible` | **Not possible** | it breaks one of the four rules (guide chapter 3); the card says what to do instead |

*How* it is built is the card's **door**, a separate tag: `configure`, `outside-app`, `event-feed`, `till-key`, `manifest`, `sandboxed-function`, `check-before-payment`, `document-check`, `capture-on-event`, `field-rules`, `save-rules`, `desk-action`, `partner-page`, `scan-source`, `label-layout`, `wallet`, `fiscal-reader`, `fulfil-at-sale` (a code your service makes for a paid sale line), `payer` (your service pays part of a sale for someone else), `register-books` (the books of a regulated-stock register, declared in your manifest), `open-check` (your app opens a table's, a tab's or a pre-order's running order and adds to it; the till takes the payment), `payment-connector`, `our-connector` (an iVendNext connector), `receipt` (the store's receipt settings), `request` (every *Not yet* card) and `none` (every *Not possible* card).

## The layout

`needs/<area>/<id>.md`, one card per file; the file name is the card's id, and an id is never renamed once published. The eight areas:

| Folder | Area |
|---|---|
| `prices/` | prices and promotions |
| `stock/` | stock and buying |
| `customers/` | customers and loyalty |
| `till/` | till controls and approvals |
| `documents/` | documents and print |
| `reports/` | reports and data |
| `integrations/` | integrations, payments and hardware |
| `setup/` | setup and administration |

`reference.txt` lists the recipes and samples that are reference rather than the answer to a need (a technique, a tool, testing), one path and its reason per line.

The site builds a card for every sample from its README, and two rules of the README come with it: it has a `## Run it` section with a code block, and its door comes from the cards that cite it. A sample no card cites (every sample listed in `reference.txt`) carries a `**Door:**` line holding the door's name; the line is removed as soon as a card cites the sample. A sample that breaks either rule fails the site build.

## A card

```
---
id: line-quantity-cap
title: A limit on the quantity of one item on a line
area: till
topic: limits-on-a-sale
asks: No more than 50 of one item on a line
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/till_guard.md
sample: samples/s23_till_guard
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
Two lines: what you build, pointing to the recipe. A card is never a tutorial.

## Limits
- One line per limit: what differs from what the customer pictures. A limit nobody has run says *not run*.

## Tell the customer
One or two sentences the scoper can paste into the proposal.
```

- `blocked-by` is `extension-point` or `product-work` on a *Not yet* card, `-` otherwise. `request` names one or more request handles (`P-…`), comma-separated: required when the card is blocked by an extension point, allowed on any card. A *Not yet* card blocked by product work has a `- **Ask us:** …` limit line; a *Not possible* card has a `- **Instead:** …` limit line.
- `topic` groups the card on its area's page: one of the area's topics, which `tools/needs/needs.py` holds in `TOPICS` (at most six per area). A new topic is a line there with its label; `needs.py check` warns, and never fails, while a topic has fewer than two cards.
- `recipe` and `sample` name a file or folder in this repository, or `none`.
- `related` (optional) names up to four other cards by id, comma-separated, for the card's *Related needs* list on the site; `needs.py check` refuses an id that is not a card, or the card's own. Most cards need none: the site adds the cards a card's text names (*the card ⟨id⟩*), those that share its sample, those named with it in a row of guide chapter 15, those that share its recipe, and those of its topic, up to four in all.
- `verified` says where and when the card was last checked: `run on a sandbox ⟨date⟩ · POS ⟨version⟩` (naming the claims run when only some were), or `carried ⟨date⟩ · not re-run` for a card moved from an older page. `needs.py stale` lists the old ones; it is a to-do, never a failure.
- At most 40 lines (aim for 25). "Extension point" in full, never shortened. No customer's name, and no name but iVendNext's for the product.

## Adding a card

1. Search first: `needs.py search <the customer's words>`. If a card exists, change that card, under its own id.
2. Copy a card from the same area, give it a new id and file name, a topic from its area's list, and write it in the customer's words.
3. Run `python3 tools/needs/needs.py check` and fix every refusal.
4. Open a pull request; CI runs the same check over every card, and the site build fails on a card that breaks a rule.
