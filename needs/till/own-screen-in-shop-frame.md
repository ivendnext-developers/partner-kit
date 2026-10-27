---
id: own-screen-in-shop-frame
title: Your own screen, a pop-up or a new step on the till, in the till's look
area: till
topic: till-screen
asks: Our own screen, a pop-up or a new step on the till, in your design; a delivery partner's screen opened from a key
status: ready-with-limits
door: partner-page
blocked-by: -
recipe: recipes/partner_page.md
sample: samples/s17_partner_page
request: -
related: question-on-flagged-scan, question-on-quantity-change
verified: carried 2026-10-16 · not re-run; the moments table read against chapters 9 and 13a and the product's notes 2026-10-27
---
## What you build
Today a partner can show something on the till at these moments (chapter 13a, *Screens on the till*):
- **A key press:** your page as a sheet over the sale, in the till's own look; in Desk, your page for a record (a partner page, `recipes/partner_page.md`).
- **An item scanned, a customer added or picked, a quantity changed:** the till's own sheet with your question, refusal or notice, or a value on the line (a capture, `recipes/capture.md`; the cards *question-on-flagged-scan*, *question-on-existing-customer*, *question-on-quantity-change*).
- **Extra fields on the till's screens:** field rules (*till-fields-shown-renamed-hidden*).
- **A key press with no page:** a till key answers with a message and values on the sale (*warranty-check-at-till*).
- **Before Pay:** a question, a refusal or a manager's approval (a check before payment, *line-quantity-cap*).
A choice such as an extended warranty needs no screen of yours: the till's item options and cross-sell suggestion draw it (the card *extended-warranty-as-item*).

## Limits
- The page opens from a key, never by itself, and answers once, with a message and sale details, never an item or a price.
- Online only: the key is dimmed offline. Not on the phone frame, which shows no app keys.
- Not on Handheld, which offers no extension point for a screen (the card *extend-handheld*).
- A page that opens on its own at a moment, and a capture that offers a choice, are not available today.
- Your JavaScript inside the till stays refused (rule 4, chapter 3).

## Tell the customer
Our service can show a page of its own as a sheet over the sale when the cashier presses a key, and the till asks our questions in its own sheets when an item is scanned, a customer is picked or a quantity changes.
