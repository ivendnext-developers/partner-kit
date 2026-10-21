# 3. The ladder and the four rules

The ladder is the order in which you try the ways into iVendNext; the four rules are what every project keeps. Every builder reads this before every project.

**Reference implementation:** one recipe per rung, linked in the table below.

**Download:** [the ladder and the four rules](https://developer.ivendnext.com/downloads/ladder_and_four_rules.pdf) (PDF, one sheet printed on both sides: the ladder on the front, the four rules on the back).

## When to use it

For each need in a project's blueprint. Start at rung 1 and go down only when the rung above cannot do the job. Most needs stop at rung 1 or 2.

## The ladder

| Rung | Way in | What it is | Your code runs | Recipe |
|---|---|---|---|---|
| 1 | Configure | pricing, promotions, coupons, sale details, line details, till keys and layouts, receipt formats (label layouts printed from the till are an extension point), workflows, numbering, permissions, reports, notifications — set in iVendNext Desk | nowhere | [4. Configure first](04_configure_first.md) |
| 2 | Outside app | your service reads and writes records over the API and reacts to the event feed; any language | your server or the customer's | [Building a connected app](../recipes/connected_app.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) |
| 3 | Till key | the cashier taps a key; the till calls your HTTPS service; you answer with a message or sale details | your server | [A till key](../recipes/point_handler.md) · [6. Till keys](06_till_keys.md) |
| 4 | Manifest | your own record types, fields, print formats, notifications and workspaces, declared as data and installed by the shop's administrator, checked by our code | nowhere: it is data; a print format is a template the server runs when it prints | [Shipping your own data in a manifest](../recipes/manifest.md) · [7. Manifests](07_manifests.md) |
| 5 | Sandboxed function | a compiled WebAssembly function at a published extension point that offers one (the check before payment and pricing do); the same answer on the server and on an offline till | inside a sandbox we run | [8. Sandboxed functions](08_sandboxed_functions.md) · [the Wasm kit](../tools/wasm_kit/README.md) |
| 6 | Compose doors, then request | If no single door fits, **compose doors** before you ask for one. An outside app with a document check, a Desk button that asks for inputs, a partner page opened from a button, a capture at the scan, save rules and configuration combine to meet most needs. A composition with its limit stated (a separate screen, a tap, seconds of delay) is the answer to give, never a workaround to hide. Request an extension point only when no composition meets the customer's outcome, and say in the request which compositions you tried and why each falls short. | — | [9. The extension-point catalogue](09_points_and_requests.md) |

**Combine rungs.** A real project is usually several (and rung 6 is the same idea for one need: combine the doors you have before you ask for another): a manifest for the records, configuration for the screens and approvals, an outside service for the logic, a till key for the cashier. Chapter 15 shows the combinations by customer size.

## The steps, for each need

1. **Can configuration do it?** Look in chapter 4 and the [needs catalogue](../needs/README.md) (`python3 tools/needs/needs.py search <words>`). If yes, stop.
2. **Can it happen outside the sale?** Before it (prepare prices, promotions, customer groups) or after it (react to a sale, sync a system, send a message). If yes, an outside app.
3. **Does the cashier need an answer during the sale?** A till key. If your service must have the last word before money is taken (allow, refuse, ask, call a manager), that is the check before payment; if it must be asked when an item is scanned or a customer is added, the capture (both extension points, chapter 9).
4. **Do you need your own records in iVendNext?** A manifest. Their screens are the native ones (chapter 13a).
5. **Must logic run inside the sale, the same online and offline?** A sandboxed function, at an extension point that offers one.
6. **None of these?** Check chapter 9. An extension point may already do it: a scan source for a unit's own barcode, field rules for what the till shows, a check before payment, a capture, a document check before a back-office document is submitted. If no single one does, combine them (rung 6): state the limit of the combination to the person, and request an extension point only if no combination meets the customer's outcome.

## The four rules — what every build keeps, and why

Four rules, each with what to do instead. They are short on purpose: anything they do not forbid is open to you.

| Rule | Why | Instead |
|---|---|---|
| **1. Money enters the sale visibly, before payment.** A price or discount may come from your service, but never change a price, tax or total after the cashier has seen it. On a back-office document (a purchase order, a receipt), a price from your service shows on the document before it is submitted, and is never changed after. | The cashier, the receipt and the books must show the same amount. A total changed behind the till disagrees with what the cashier charged, and the sale is stopped — possibly after the card was taken | prices, promotions and coupons (configuration); a check before payment; a live price or discount through the deal extension point (being specified), within the shop's limits |
| **2. Don't override or patch iVendNext.** | We upgrade every customer together. An override or a patch is a private copy of our code that the next release moves under, and on the till it is not even reached | an extension point; if none fits, request one |
| **3. Your code runs on your server.** Inside the customer's site you ship data, not code — no server code of yours, no server scripts | Many customers share one installation, so code inside one site is code on all of them, and a script can send data anywhere with no review. Data installs into one site and touches no one else's | an outside app, a till key, a payment connector on your server; a manifest inside the site, or a sandboxed function at an extension point that takes one (the check before payment and pricing) |
| **4. Your screens use our doors.** Never your JavaScript inside Desk forms or the till | A script on a form runs in every user's browser, administrators included. The till loads only its own code | native screens, declared buttons, your page inside our frame, or your own app with Sign in with iVendNext (chapter 13a) |

## When your service is down, and when the till is offline

Each rung answers this in its own chapter. The rule across all of them: the till never waits on a builder's service it cannot reach.
- **Outside apps** catch up from the event feed.
- **Till keys** are dimmed offline, and refused in words when your service is down.
- **A check before payment and a capture** are not called offline: the till applies the answer you declared for when your service is down.
- **A sandboxed function** runs on the till, offline too (the check before payment and pricing take one, and only one we have certified runs).

Offline behaviour is described here from the product's design. The kit has tried it only for a sandboxed function (chapter 8). Chapter 16 states the product's own offline limits.

## Technical notes

### Offline evidence

The kit did not run offline for any rung, apart from one browser test of a sandboxed function (chapter 8; the product's own walk of a pricing module offline is there too; chapter 16 states the product's own offline limits).

### The tests

- Every need in your blueprint has one rung, and the rung's recipe.
- Your build keeps all four rules. The manifest checker refuses a manifest that declares code (chapter 14); the shop's install runs that checker again inside the site; what we run on a sandboxed function or an endpoint before a customer uses it is not covered by the kit yet (chapter 17).
